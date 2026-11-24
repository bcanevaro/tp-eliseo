"""Nodos del flujo de reclamo (flujo-reclamo-mediador) que se enchufan en `eliseo/grafo/nodos.py`.

    precedentes         tool de precedentes (código): ids fijados desde el estado del grafo
    mediador            dictamen con el modelo de razonamiento, guarda de recomendación, o modo sin LLM
    verificar_dictamen  rechaza las citas no provistas y verifica las demás (sin duplicar fallas)

Modo (`MEDIADOR_MODO`): "agente" usa el LLM y cae al modo "codigo" si el proxy falla o si el modelo
devuelve dos veces seguidas una salida que no es un `Dictamen` (design D5 y D6).
"""
import logging

import openai

from eliseo import verificador
from eliseo.agentes.mediador.agente import FormatoInvalido, guarda_recomendacion, redactar
from eliseo.agentes.mediador.codigo import dictamen_codigo
from eliseo.agentes.mediador.precedentes import get_precedentes, tipo_reclamo
from eliseo.config import env

log = logging.getLogger(__name__)

NO_PROVISTA = "cita no provista en el contexto"


def precedentes(state: dict) -> dict:
    """Los ids salen del caso del estado del grafo; el tipo, del mismo clasificador que `ejecucion`."""
    caso = state["caso"]
    descripcion = f"{caso.reclamo.descripcion} {caso.reclamo.ambiente or ''}".strip()
    return {"precedentes": get_precedentes(caso.consorcio_id, caso.unidad_id, tipo_reclamo(caso), descripcion)}


def modo() -> str:
    return env("MEDIADOR_MODO", default="agente")


def _modelo():
    from eliseo import llm

    try:
        return llm.get_reasoning_model()
    except KeyError:
        return None


def mediador(state: dict) -> dict:
    caso, doc, precs = state["caso"], state.get("documental"), state.get("precedentes", [])
    if modo() == "agente" and (modelo := _modelo()):
        # En la vuelta siguiente a un rechazo, el Mediador recibe su dictamen anterior y los motivos.
        rechazo = state.get("vueltas", 0) > 0 and not (state.get("verificacion") or {}).get("ok", True)
        anterior = state.get("dictamen") if rechazo else None
        fallas = state["verificacion"]["fallas"] if rechazo else None
        try:
            return {"dictamen": guarda_recomendacion(redactar(modelo, caso, doc, precs, anterior, fallas), caso)}
        except FormatoInvalido as e:
            log.warning("Mediador: %s; uso el modo sin LLM", e)
        except openai.OpenAIError as e:
            log.warning("Mediador: proxy no disponible (%s); uso el modo sin LLM", e)
    return {"dictamen": dictamen_codigo(caso, doc, precs)}


def citas_provistas(state: dict) -> set[str]:
    """Lo que el Mediador recibió: el paquete de Documental y los precedentes."""
    doc = state.get("documental")
    return ({c.referencia for c in doc.citas} if doc else set()) | {p["prec_id"] for p in state.get("precedentes", [])}


def verificar_dictamen(state: dict) -> dict:
    d, provistas = state["dictamen"], citas_provistas(state)
    fallas = [{"hipotesis": h.id, "cita": c, "motivo": NO_PROVISTA, "vigente": None}
              for h in d.hipotesis for c in h.citas if c not in provistas]
    # El verificador corre solo sobre las citas provistas: una no provista e inexistente da una sola falla.
    solo_provistas = d.model_copy(update={"hipotesis": [
        h.model_copy(update={"citas": [c for c in h.citas if c in provistas]})
        for h in d.hipotesis if any(c in provistas for c in h.citas)]})
    fallas += verificador.verificar_dictamen(state["caso"].consorcio_id, solo_provistas)["fallas"]
    v = {"ok": not fallas, "fallas": fallas}
    return {"verificacion": v, "vueltas": state.get("vueltas", 0) + (0 if v["ok"] else 1)}
