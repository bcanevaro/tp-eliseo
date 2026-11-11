"""Grafo de caso: un hilo por reclamo, con aprobación humana (spec grafo-orquestacion).

    iniciar_analisis → [documental_caso ‖ precedentes] → mediador → verificar_dictamen
        ─┬─ ok ─────────────────────────────────────────────→ a_aprobacion
         ├─ falla y vueltas < 2 → mediador (con los motivos)
         └─ falla y vueltas = 2 → fallback_inspeccion ──────→ a_aprobacion
    a_aprobacion → panel (interrupt: espera la DecisionAdmin) → registrar_decision
        ─┬─ APROBAR / MODIFICAR → ejecucion → END
         └─ RECHAZAR ───────────→ rechazo → END

Secuencia fija: los pasos del reclamo se conocen de antemano, así que no hay Supervisor.
"""
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from eliseo.grafo.estado import EstadoGrafoCaso
from eliseo.grafo.nodos import NODOS_CASO
from eliseo.plataforma import escritura
from eliseo.plataforma.db import get_conn
from eliseo.schemas import AccionAdmin, DecisionAdmin, Dictamen, EstadoCaso, Recomendacion

MAX_VUELTAS = 2


def iniciar_analisis(state: EstadoGrafoCaso) -> dict:
    caso = escritura.cambiar_estado(get_conn(), state["caso"].caso_id, EstadoCaso.EN_ANALISIS)
    return {"caso": caso, "vueltas": 0}


def fallback_inspeccion(state: EstadoGrafoCaso) -> dict:
    """Tras 2 rechazos del verificador: se descartan las hipótesis sin respaldo y se recomienda inspección."""
    malas = {f["cita"] for f in state["verificacion"]["fallas"]}
    d = state["dictamen"]
    hipotesis = [h for h in d.hipotesis if not set(h.citas) & malas]
    dictamen = Dictamen(
        hechos=d.hechos,
        afirmaciones_sin_evidencia=d.afirmaciones_sin_evidencia,
        hipotesis=hipotesis,
        recomendacion=Recomendacion(
            tipo="inspeccion",
            accion="Inspección técnica: no se pudieron verificar las citas de " + ", ".join(sorted(malas))),
        mensaje_vecino=d.mensaje_vecino,
    )
    return {"dictamen": dictamen}


def a_aprobacion(state: EstadoGrafoCaso) -> dict:
    """Guarda el borrador y deja el caso esperando al administrador. Va separado de `panel`
    porque al retomar un interrupt el nodo se vuelve a ejecutar desde el principio."""
    conn, caso = get_conn(), state["caso"]
    dictamen_id = escritura.guardar_dictamen(conn, caso.caso_id, state["dictamen"], state.get("verificacion"))
    return {"dictamen_id": dictamen_id, "caso": escritura.cambiar_estado(conn, caso.caso_id, EstadoCaso.PENDIENTE_APROBACION)}


def panel(state: EstadoGrafoCaso) -> dict:
    decision = interrupt({"caso_id": state["caso"].caso_id, "dictamen_id": state["dictamen_id"]})
    return {"decision": DecisionAdmin.model_validate(decision)}


def registrar_decision(state: EstadoGrafoCaso) -> dict:
    escritura.guardar_decision(get_conn(), state["dictamen_id"], state["caso"].caso_id, state["decision"])
    return {}


def _despues_de_verificar(state: EstadoGrafoCaso) -> str:
    if state["verificacion"]["ok"]:
        return "a_aprobacion"
    return "mediador" if state["vueltas"] < MAX_VUELTAS else "fallback_inspeccion"


def _despues_de_decidir(state: EstadoGrafoCaso) -> str:
    return "rechazo" if state["decision"].accion is AccionAdmin.RECHAZAR else "ejecucion"


def construir(checkpointer=None, nodos: dict | None = None):
    n = {**NODOS_CASO, **(nodos or {})}
    g = StateGraph(EstadoGrafoCaso)
    for nombre, fn in [("iniciar_analisis", iniciar_analisis), ("fallback_inspeccion", fallback_inspeccion),
                       ("a_aprobacion", a_aprobacion), ("panel", panel), ("registrar_decision", registrar_decision)]:
        g.add_node(nombre, fn)
    for nombre, fn in n.items():
        g.add_node(nombre, fn)

    g.add_edge(START, "iniciar_analisis")
    g.add_edge("iniciar_analisis", "documental_caso")
    g.add_edge("iniciar_analisis", "precedentes")
    g.add_edge(["documental_caso", "precedentes"], "mediador")  # espera a los dos (Parallel)
    g.add_edge("mediador", "verificar_dictamen")
    g.add_conditional_edges("verificar_dictamen", _despues_de_verificar,
                            ["a_aprobacion", "mediador", "fallback_inspeccion"])
    g.add_edge("fallback_inspeccion", "a_aprobacion")
    g.add_edge("a_aprobacion", "panel")
    g.add_edge("panel", "registrar_decision")
    g.add_conditional_edges("registrar_decision", _despues_de_decidir, ["ejecucion", "rechazo"])
    g.add_edge("ejecucion", END)
    g.add_edge("rechazo", END)
    return g.compile(checkpointer=checkpointer)
