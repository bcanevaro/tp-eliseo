"""Intake + Router (spec intake-router): un único LLM step con structured output.

No tiene tools ni permisos y no elige el siguiente nodo: devuelve un `ResultadoIntake` y el
workflow (conversacion.py) decide. Si el modelo devuelve algo inválido, reintenta una vez y
después devuelve UNKNOWN. Si el proxy no está disponible, usa las reglas por palabras clave
del bootstrap.

La urgencia se marca si la marca el LLM **o** las palabras clave: ante la duda, se avisa
(el recall de urgencias tiene que ser 1).

Modo (`INTAKE_MODO`): "llm" (por defecto) o "reglas" (sin LLM; lo usan los tests).
"""
import logging

import openai
from pydantic import ValidationError

from eliseo.config import env
from eliseo.formato import normalizar
from eliseo.grafo import stubs
from eliseo.plataforma import lectura
from eliseo.plataforma.db import get_conn
from eliseo.prompts import cargar
from eliseo.schemas import Intent, ReclamoBorrador, ResultadoIntake

log = logging.getLogger(__name__)

URGENCIA_PALABRAS = ["gas", "encerrad", "atrapad", "incendio", "fuego", "humo", "chispa", "electrocut",
                     "inund", "cable pelado", "cables pelados", "no para de salir agua", "se cae el techo"]


def modo() -> str:
    return env("INTAKE_MODO", default="llm")


def _modelo():
    from eliseo import llm

    try:
        return llm.get_fast_model()
    except KeyError:
        return None


def es_urgencia_por_palabras(texto: str) -> bool:
    t = normalizar(texto)
    return any(p in t for p in URGENCIA_PALABRAS)


def entrada(state: dict) -> str:
    """El mensaje y el contexto del hilo, como datos delimitados."""
    msg = state["mensaje"]
    partes = [f"<mensaje_vecino>{msg.texto or '(sin texto)'}</mensaje_vecino>"]
    if msg.adjuntos:
        partes.append(f"<adjuntos>{', '.join(a.tipo for a in msg.adjuntos)}</adjuntos>")
    borrador: ReclamoBorrador | None = state.get("reclamo_en_curso")
    if borrador:
        faltan = ", ".join(f.value for f in borrador.faltantes()) or "nada"
        partes.append(f"<reclamo_en_curso>{borrador.model_dump_json(exclude={'fotos'})} · "
                      f"fotos: {len(borrador.fotos)} · faltan: {faltan}</reclamo_en_curso>")
    return "\n".join(partes)


def clasificar(state: dict, modelo) -> ResultadoIntake:
    ident = state["identidad"]
    sistema = cargar("intake").replace("{consorcio_nombre}", lectura.consorcio(get_conn(), ident.consorcio_id)["nombre"])
    estructurado = modelo.with_structured_output(ResultadoIntake)
    mensajes = [("system", sistema), ("human", entrada(state))]
    for intento in range(2):
        try:
            return estructurado.invoke(mensajes)
        except (ValidationError, ValueError) as e:
            log.warning("Intake: salida inválida (intento %d): %s", intento + 1, e)
    return ResultadoIntake(intent=Intent.UNKNOWN)


def intake(state: dict) -> dict:
    texto = state["mensaje"].texto
    resultado = None
    if modo() == "llm" and (modelo := _modelo()):
        try:
            resultado = clasificar(state, modelo)
        except openai.APIError as e:
            log.warning("Intake: proxy no disponible (%s); uso las reglas", e)
    if resultado is None:
        resultado = stubs.intake(state)["intake"]
    if es_urgencia_por_palabras(texto) and not resultado.urgencia:
        resultado = resultado.model_copy(update={"urgencia": True})
    # Si hay un reclamo en curso y el mensaje trae una foto sin texto, es un dato del reclamo.
    if state.get("reclamo_en_curso") and resultado.intent is Intent.UNKNOWN and state["mensaje"].adjuntos:
        resultado = ResultadoIntake(intent=Intent.RECLAMO, reclamo=ReclamoBorrador(), urgencia=resultado.urgencia)
    if resultado.reclamo:
        completo = (state.get("reclamo_en_curso") or ReclamoBorrador()).completar(resultado.reclamo)
        resultado = resultado.model_copy(update={"campos_faltantes": completo.faltantes()})
    return {"intake": resultado}
