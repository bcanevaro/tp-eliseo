"""Nodos del flujo de reclamo (flujo-reclamo-mediador) que se enchufan en `eliseo/grafo/nodos.py`."""
from eliseo.agentes.mediador.precedentes import get_precedentes, tipo_reclamo


def precedentes(state: dict) -> dict:
    """Los ids salen del caso del estado del grafo; el tipo, del mismo clasificador que `ejecucion`."""
    caso = state["caso"]
    descripcion = f"{caso.reclamo.descripcion} {caso.reclamo.ambiente or ''}".strip()
    return {"precedentes": get_precedentes(caso.consorcio_id, caso.unidad_id, tipo_reclamo(caso), descripcion)}
