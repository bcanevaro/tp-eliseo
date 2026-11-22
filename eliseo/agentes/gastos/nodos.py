"""Nodos del agente Gastos para el grafo de conversación (se registran en eliseo/grafo/nodos.py).

    gastos            rama GASTOS: agente con LLM (validado) o modo sin LLM
    responder_gastos  arma el mensaje con las líneas y sus comprobantes (código, no LLM)

Modo (`GASTOS_MODO`): "agente" usa el LLM y cae al modo "codigo" si el proxy falla o si la
respuesta trae un monto que no devolvió ninguna tool. Pedir datos de otra unidad se corta por
código antes de llamar al modelo.
"""
import logging

import openai
from pydantic import ValidationError

from eliseo.agentes.gastos.agente import MontoNoRespaldado, correr_agente, otra_unidad, respuesta_codigo, solo_su_cuenta
from eliseo.config import env
from eliseo.formato import pesos
from eliseo.plataforma import escritura
from eliseo.plataforma.db import get_conn
from eliseo.schemas import MensajeSaliente

log = logging.getLogger(__name__)

SIN_COMPROBANTE = ("Hay gastos sin comprobante cargado: le pedí a la administración que lo suba y te avisamos "
                   "por acá.")


def modo() -> str:
    return env("GASTOS_MODO", default="agente")


def _modelo():
    from eliseo import llm

    try:
        return llm.get_model()
    except KeyError:
        return None


def gastos(state: dict) -> dict:
    ident, msg = state["identidad"], state["mensaje"]
    if otra := otra_unidad(ident, msg.texto):
        return {"gastos": solo_su_cuenta(ident, otra)}
    if modo() == "agente" and (modelo := _modelo()):
        try:
            return {"gastos": correr_agente(ident, msg.texto, modelo)}
        except MontoNoRespaldado as e:
            log.warning("Gastos: respuesta descartada (%s); uso el modo sin LLM", e)
        except (openai.APIError, ValidationError) as e:
            log.warning("Gastos: el agente falló (%s); uso el modo sin LLM", e)
    return {"gastos": respuesta_codigo(ident, msg.texto)}


def responder_gastos(state: dict) -> dict:
    g, ident = state["gastos"], state["identidad"]
    lineas = [f"• {l.concepto}: {pesos(l.monto)}" + (f" ({l.comprobante})" if l.comprobante else " (sin comprobante cargado)")
              for l in g.lineas]
    faltantes = [l for l in g.lineas if not l.comprobante and not l.concepto.startswith(("Expensa", "Pago"))
                 and "fondo de reserva" not in l.concepto.lower() and "sueldo" not in l.concepto.lower()]
    texto = "\n".join([g.respuesta, *lineas])
    if faltantes:
        escritura.crear_derivacion(get_conn(), "sin_fuente", msg_texto(state), consorcio_id=ident.consorcio_id,
                                   unidad_id=ident.unidad_id, telefono=ident.telefono,
                                   detalle={"comprobantes_faltantes": [l.concepto for l in faltantes]})
        texto += f"\n\n{SIN_COMPROBANTE}"
    return {"salidas": [MensajeSaliente(texto=texto)]}


def msg_texto(state: dict) -> str:
    return state["mensaje"].texto or "(consulta de gastos)"
