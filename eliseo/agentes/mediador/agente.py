"""El Mediador con LLM: una llamada con salida estructurada `Dictamen`, sin tools (design D1).

- `redactar`: arma el contexto (orden de D3, todo dato escapado), llama al modelo de razonamiento y,
  si la salida no valida, pide una sola reparación de formato (D5). Si vuelve a fallar, lanza
  `FormatoInvalido` y el nodo usa el modo sin LLM.
- `guarda_recomendacion`: código sobre la salida del modelo, antes del verificador (D4).
"""
import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage

from eliseo.agentes.mediador.codigo import mensaje_inspeccion
from eliseo.agentes.mediador.criterios import bloque_criterios
from eliseo.config import env
from eliseo.corpus import cargar_corpus
from eliseo.plataforma import lectura
from eliseo.plataforma.db import get_conn
from eliseo.prompts import cargar, escapar
from eliseo.schemas import Caso, Dictamen, Recomendacion, RespuestaDocumental

log = logging.getLogger(__name__)

REPARAR_FORMATO = ("Tu respuesta anterior no es un dictamen válido. Devolvé el dictamen completo otra vez respetando "
                   "el formato: cada hipótesis con al menos una cita y, si recomendás asignar, el id de una "
                   "hipótesis que exista.")


class FormatoInvalido(ValueError):
    """El modelo devolvió dos veces seguidas una salida que no es un `Dictamen` válido."""


def version_prompt() -> str:
    """v2 por defecto (solo para el Mediador: los demás prompts siguen en v1)."""
    return env("PROMPT_MEDIADOR_VERSION", default="v2")


def sistema(administracion: str, version: str | None = None) -> str:
    # El prompt trae JSON con llaves: str.replace, nunca .format().
    return (cargar("mediador", version or version_prompt())
            .replace("{administracion_nombre}", administracion)
            .replace("{criterios_procedimentales}", bloque_criterios(administracion)))


# ---------------------------------------------------------------- contexto (D3)

def _fuentes(caso: Caso, documental: RespuestaDocumental | None) -> tuple[list[str], list[str]]:
    """Líneas de <reglamento> y <actas>: el texto completo del corpus, o el fragmento del paquete."""
    try:
        corpus = cargar_corpus(caso.consorcio_id)
    except KeyError:
        corpus = None
    reglamento, actas = [], []
    for c in documental.citas if documental else []:
        doc = corpus.get(c.referencia) if corpus else None
        texto = f"{doc.titulo}. {doc.texto}" if doc else c.fragmento
        (reglamento if c.documento == "Reglamento" else actas).append(f"[{c.referencia}] {escapar(texto)}")
    return reglamento, actas


def _precedente(p: dict) -> str:
    return f"[{p['prec_id']} · {p['fecha']}] {escapar(p['descripcion'])} Resuelto: {escapar(p['resolucion'])}"


def _caso(caso: Caso) -> str:
    r = caso.reclamo
    gotea = {True: "gotea", False: "no gotea", None: "sin dato de goteo"}[r.gotea]
    partes = [f"reclamo #{caso.caso_id}", f"unidad {caso.unidad_id}", f"ambiente: {r.ambiente or 'sin indicar'}",
              gotea, f"desde: {r.desde_cuando or 'sin indicar'}", f"fotos: {len(r.fotos)}"]
    return escapar(" · ".join(partes))


def _bloque(etiqueta: str, lineas: list[str], vacio: str) -> str:
    return f"<{etiqueta}>\n" + ("\n".join(lineas) or vacio) + f"\n</{etiqueta}>"


def contexto(caso: Caso, documental: RespuestaDocumental | None, precedentes: list[dict],
             anterior: Dictamen | None = None, fallas: list[dict] | None = None) -> str:
    """Mensaje humano: evidencia antes que el relato (los criterios ya van en el prompt de sistema)."""
    reglamento, actas = _fuentes(caso, documental)
    partes = [
        _bloque("reglamento", reglamento, "(sin artículos)"),
        _bloque("actas", actas, "(sin actas)"),
        _bloque("precedentes", [_precedente(p) for p in precedentes or []], "(sin precedentes)"),
        f"<relato_vecino>\n{escapar(caso.reclamo.descripcion) or '(sin relato)'}\n</relato_vecino>",
        f"<caso>\n{_caso(caso)}\n</caso>",
    ]
    if anterior is not None:
        partes += [f"<dictamen_anterior>\n{escapar(anterior.model_dump_json())}\n</dictamen_anterior>",
                   f"<fallas>\n{escapar(json.dumps(fallas or [], ensure_ascii=False))}\n</fallas>"]
    return "\n".join(partes)


# ---------------------------------------------------------------- llamada (D1, D5)

def redactar(modelo, caso: Caso, documental: RespuestaDocumental | None, precedentes: list[dict],
             anterior: Dictamen | None = None, fallas: list[dict] | None = None) -> Dictamen:
    administracion = lectura.consorcio(get_conn(), caso.consorcio_id)["administracion"]
    mensajes = [SystemMessage(sistema(administracion)),
                HumanMessage(contexto(caso, documental, precedentes, anterior, fallas))]
    estructurado = modelo.with_structured_output(Dictamen)
    for intento in (1, 2):
        try:
            salida = estructurado.invoke(mensajes)
            return salida if isinstance(salida, Dictamen) else Dictamen.model_validate(salida)
        except ValueError as e:  # ValidationError y OutputParserException son ValueError
            log.warning("Mediador: salida con formato inválido (intento %d): %s", intento, e)
            error = escapar(str(e)[:1000])
            mensajes = [*mensajes, HumanMessage(f"{REPARAR_FORMATO}\n<error_formato>\n{error}\n</error_formato>")]
    raise FormatoInvalido(f"caso {caso.caso_id}: dos salidas seguidas que no son un Dictamen")


# ---------------------------------------------------------------- guarda de recomendación (D4)

def guarda_recomendacion(dictamen: Dictamen, caso: Caso) -> Dictamen:
    """`asignar` solo si la hipótesis elegida tiene cita y ninguna otra hipótesis citada con otro
    responsable la contradice. Si no, pasa a inspección y deja un aviso neutral al vecino."""
    rec = dictamen.recomendacion
    if rec.tipo != "asignar":
        return dictamen
    elegida = next(h for h in dictamen.hipotesis if h.id == rec.hipotesis)  # el schema garantiza que existe
    contrarias = [h.id for h in dictamen.hipotesis
                  if h.id != elegida.id and h.citas and h.responsable != elegida.responsable]
    if elegida.citas and not contrarias:
        return dictamen
    log.warning("Mediador: 'asignar' a %s descartado por la guarda (sin citas=%s, contradicha por %s); paso a inspección",
                elegida.id, not elegida.citas, contrarias)
    accion = "Inspección técnica antes de asignar. Verificar: " + "; ".join(
        f"{h.id} ({h.responsable}): {h.confirmaria}" for h in dictamen.hipotesis)
    return dictamen.model_copy(update={
        "recomendacion": Recomendacion(tipo="inspeccion", hipotesis=None, accion=accion),
        "mensaje_vecino": mensaje_inspeccion(caso),
    })
