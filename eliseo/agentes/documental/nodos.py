"""Nodos del agente Documental para los grafos (se registran en eliseo/grafo/nodos.py).

    documental            rama REGLAMENTO del grafo de conversación
    verificar_consulta    descarta citas inválidas; sin citas válidas → derivar (D7)
    responder_reglamento  redacta con el master prompt "vecino" (o plantilla sin LLM)
    documental_caso       paquete de citas para el Mediador en el grafo de caso (D8)

Modo (`DOCUMENTAL_MODO`): "agente" usa el LLM y, si el proxy falla, cae al modo "retriever"
(sin LLM). La abstención es la misma en los dos modos.
"""
import logging

import openai

from eliseo.agentes.documental import retriever
from eliseo.agentes.documental.agente import citas_de, correr_agente, respuesta_retriever
from eliseo.config import env
from eliseo.corpus import cargar_corpus
from eliseo.formato import normalizar
from eliseo.plataforma import lectura
from eliseo.plataforma.db import get_conn
from eliseo.prompts import cargar
from eliseo.schemas import MensajeSaliente, RespuestaDocumental, RespuestaVecino
from eliseo.verificador import verificar_citas

log = logging.getLogger(__name__)


def modo() -> str:
    return env("DOCUMENTAL_MODO", default="agente")


def _modelo(cual: str):
    """El modelo del proxy, o None si no está configurado (se usa el modo retriever)."""
    from eliseo import llm

    try:
        return llm.get_fast_model() if cual == "rapido" else llm.get_model()
    except KeyError:
        return None


def documental(state: dict) -> dict:
    ident, msg = state["identidad"], state["mensaje"]
    consulta = state["intake"].pregunta_reescrita or msg.texto
    if modo() == "agente" and (modelo := _modelo("principal")):
        try:
            return {"documental": correr_agente(ident.consorcio_id, consulta, modelo, pregunta_original=msg.texto)}
        except openai.APIError as e:
            log.warning("Proxy no disponible para Documental (%s); uso el modo retriever", e)
    return {"documental": respuesta_retriever(ident.consorcio_id, consulta)}


def verificar_consulta(state: dict) -> dict:
    cid, doc = state["identidad"].consorcio_id, state["documental"]
    if not doc.suficiente or not doc.citas:
        return {"verificacion_consulta": {"ok": False, "fallas": [], "motivo": "sin evidencia"}}
    resultados = [(c, verificar_citas(cid, [c])) for c in doc.citas]
    validas = [c for c, r in resultados if r["ok"]]
    fallas = [f for _, r in resultados for f in r["fallas"]]
    return {
        "documental": doc.model_copy(update={"citas": validas}),
        "verificacion_consulta": {"ok": bool(validas), "fallas": fallas, "descartadas": len(doc.citas) - len(validas)},
    }


def _fuentes(cid: str, refs: list[str]) -> str:
    corpus = cargar_corpus(cid)
    return "\n".join(f"[{r}] {corpus.get(r).texto}" for r in refs)


def _con_fuentes(texto: str, refs: list[str]) -> str:
    return f"{texto}\n\nFuente: {', '.join(refs)}"


def _derivar(state: dict) -> dict:
    from eliseo.grafo.nodos import NODOS_CONVERSACION  # import tardío: nodos.py importa este módulo

    return NODOS_CONVERSACION["derivar_sin_fuente"](state)


def redactar(state: dict, modelo) -> RespuestaVecino:
    cid, doc = state["identidad"].consorcio_id, state["documental"]
    refs = list(dict.fromkeys(c.referencia for c in doc.citas))
    sistema = cargar("vecino").replace("{consorcio_nombre}", lectura.consorcio(get_conn(), cid)["nombre"])
    entrada = (f"<mensaje_vecino>{state['mensaje'].texto}</mensaje_vecino>\n"
               f"<fuentes>\n{_fuentes(cid, refs)}\n</fuentes>")
    return modelo.with_structured_output(RespuestaVecino).invoke([("system", sistema), ("human", entrada)])


def responder_reglamento(state: dict) -> dict:
    cid, doc = state["identidad"].consorcio_id, state["documental"]
    permitidas = {c.referencia for c in doc.citas}
    if modo() == "agente" and (modelo := _modelo("rapido")):
        try:
            r = redactar(state, modelo)
            ajenas = {c.referencia for c in r.citas} - permitidas
            if r.derivar or ajenas or not verificar_citas(cid, r.citas)["ok"]:
                log.info("Redacción derivada (derivar=%s, citas ajenas=%s)", r.derivar, ajenas)
                return _derivar(state)
            return {"salidas": [MensajeSaliente(texto=_con_fuentes(r.respuesta, [c.referencia for c in r.citas]))]}
        except openai.APIError as e:
            log.warning("Proxy no disponible para redactar (%s); uso la plantilla", e)
    r = RespuestaVecino(respuesta=doc.respuesta[:600], citas=doc.citas)
    return {"salidas": [MensajeSaliente(texto=_con_fuentes(r.respuesta, list(dict.fromkeys(c.referencia for c in r.citas))))]}


# El Mediador tiene que poder plantear hipótesis de los dos lados: unidad y consorcio.
CONSULTAS_RESPONSABILIDAD = [
    "cañerías e instalaciones de uso exclusivo de la unidad a cargo del propietario",
    "montantes y cañerías generales partes comunes a cargo del consorcio",
]


def documental_caso(state: dict) -> dict:
    caso = state["caso"]
    r = caso.reclamo
    consultas = [f"{r.ambiente or ''} {r.descripcion}", *CONSULTAS_RESPONSABILIDAD]
    documentos, vistos = [], set()
    for consulta in consultas:
        for d in retriever.buscar(caso.consorcio_id, consulta, k=2).documentos:
            if d.ref not in vistos:
                vistos.add(d.ref)
                documentos.append(d)
    # Actas que hablan de la misma columna (p. ej. una obra aprobada sobre la montante).
    columna = f"columna {caso.unidad_id[-1].lower()}"
    documentos += [a for a in cargar_corpus(caso.consorcio_id).actas()
                   if columna in normalizar(a.texto) and a.ref not in vistos]
    citas = citas_de(documentos)
    return {"documental": RespuestaDocumental(respuesta="", citas=citas, suficiente=bool(citas))}
