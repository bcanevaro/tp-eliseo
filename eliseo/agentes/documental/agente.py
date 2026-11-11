"""El agente Documental y su modo sin LLM (design D4 y D5).

- `correr_agente`: loop explícito con tools; corta a las 3 búsquedas y pide la salida final
  estructurada (`RespuestaDocumental`).
- `respuesta_retriever`: sin LLM. Las citas salen del retriever (k=1, vigencia resuelta) y la
  suficiencia del score del reranker o, sin reranker, de cuántos términos coinciden.
"""
import logging

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from eliseo.agentes.documental import retriever
from eliseo.agentes.documental.tools import crear_tools
from eliseo.corpus import Documento
from eliseo.plataforma import lectura
from eliseo.plataforma.db import get_conn
from eliseo.prompts import cargar
from eliseo.schemas import Cita, RespuestaDocumental

log = logging.getLogger(__name__)

MAX_ITERACIONES = 6  # vueltas del loop (cada una puede pedir varias tools)
MIN_COINCIDENCIAS = 2  # términos de la consulta que tienen que estar en el documento (modo sin reranker)
PEDIR_FINAL = "Devolvé ahora la respuesta final con las citas literales de las fuentes que usaste."


def correr_agente(consorcio_id: str, consulta: str, modelo, pregunta_original: str | None = None) -> RespuestaDocumental:
    tools, contador = crear_tools(consorcio_id)
    por_nombre = {t.name: t for t in tools}
    nombre = lectura.consorcio(get_conn(), consorcio_id)["nombre"]
    mensajes = [
        SystemMessage(cargar("documental").replace("{consorcio_nombre}", nombre)),
        HumanMessage(f"<pregunta_vecino>{pregunta_original or consulta}</pregunta_vecino>\n"
                     f"<pregunta_reescrita>{consulta}</pregunta_reescrita>"),
    ]
    con_tools = modelo.bind_tools(tools)
    for _ in range(MAX_ITERACIONES):
        ai = con_tools.invoke(mensajes)
        mensajes.append(ai)
        if not ai.tool_calls:
            break
        for llamada in ai.tool_calls:
            tool = por_nombre.get(llamada["name"])
            salida = tool.invoke(llamada["args"]) if tool else f"No existe la tool {llamada['name']}."
            mensajes.append(ToolMessage(content=salida, tool_call_id=llamada["id"]))
    log.info("Documental: %d búsquedas", contador.busquedas)
    return modelo.with_structured_output(RespuestaDocumental).invoke([*mensajes, HumanMessage(PEDIR_FINAL)])


def primera_oracion(texto: str) -> str:
    return texto.split(". ")[0].rstrip(".") + "."


def citas_de(documentos: list[Documento]) -> list[Cita]:
    return [Cita(documento=d.tipo, referencia=d.ref, fragmento=primera_oracion(d.texto)) for d in documentos]


def _suficiente(resultado: retriever.Resultado, consulta: str) -> bool:
    if not resultado.documentos:
        return False
    if resultado.score is not None:
        return resultado.score >= retriever.umbral_suficiente()
    # Sin reranker: el mejor documento (antes de resolver vigencia) tiene que compartir términos.
    mejor = resultado.etapas["rrf"][0] if resultado.etapas.get("rrf") else None
    if mejor is None:
        return False
    from eliseo.corpus import cargar_corpus

    doc = cargar_corpus(resultado.documentos[0].consorcio_id).get(mejor)
    comunes = set(retriever.tokenizar(consulta)) & set(retriever.tokenizar(f"{doc.titulo} {doc.texto}"))
    return len(comunes) >= MIN_COINCIDENCIAS


def respuesta_retriever(consorcio_id: str, consulta: str) -> RespuestaDocumental:
    resultado = retriever.buscar(consorcio_id, consulta, k=1)
    if not _suficiente(resultado, consulta):
        return RespuestaDocumental(respuesta="", citas=[], suficiente=False)
    citas = citas_de(resultado.documentos)
    respuesta = " ".join(f"Según {c.referencia}: {c.fragmento}" for c in citas)
    return RespuestaDocumental(respuesta=respuesta[:600], citas=citas, suficiente=True)
