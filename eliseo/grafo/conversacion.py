"""Grafo de conversación: un hilo por vecino (spec grafo-orquestacion).

    inicio → identificar ─┬─ (sin identidad) ────────────────→ END
                          ├─ "Hablar con la administración" ─→ hablar_con_admin → END
                          ├─ (sin texto) ────────────────────→ saludar → END
                          └─ intake → despachar ─┬─ (urgencia) → avisar_urgencia ─┐
                                                 └────────────────────────────────┴→ fan-out por intent:
        REGLAMENTO → documental → verificar_consulta → responder_reglamento | derivar_sin_fuente
        GASTOS     → gastos → responder_gastos
        RECLAMO    → completar_datos → (completo) registrar_caso
        UNKNOWN    → no_entendido (repregunta una vez; la segunda deriva)

El siguiente paso lo decide este workflow según el ResultadoIntake, nunca un LLM.
"""
from datetime import datetime, timedelta, timezone

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from eliseo import textos
from eliseo.config import ttl_hilo_dias
from eliseo.formato import normalizar
from eliseo.grafo.estado import REINICIAR, EstadoConversacion
from eliseo.grafo.nodos import NODOS_CONVERSACION
from eliseo.plataforma import escritura, lectura
from eliseo.plataforma.db import get_conn
from eliseo.schemas import Caso, EstadoCaso, Intent, MensajeSaliente

RAMA_POR_INTENT = {
    Intent.REGLAMENTO: "documental",
    Intent.GASTOS: "gastos",
    Intent.RECLAMO: "completar_datos",
    Intent.UNKNOWN: "no_entendido",
}


# ------------------------------------------------------------------ nodos de código (bootstrap)

def inicio(state: EstadoConversacion) -> dict:
    """Limpia lo del turno anterior y aplica el TTL del hilo."""
    ahora = datetime.now(timezone.utc)
    update = {"salidas": REINICIAR, "intake": None, "documental": None, "verificacion_consulta": None,
              "gastos": None, "casos_lanzados": [], "ultimo_mensaje": ahora}
    ultimo = state.get("ultimo_mensaje")
    if ultimo and ahora - ultimo > timedelta(days=ttl_hilo_dias()):
        update |= {"reclamo_en_curso": None, "no_entendidos_seguidos": 0}
    return update


def identificar(state: EstadoConversacion) -> dict:
    """La identidad sale del teléfono registrado, nunca del texto (spec contratos-compartidos)."""
    conn, msg = get_conn(), state["mensaje"]
    if msg.telefono_compartido:
        # El canal solo completa telefono_compartido si el contacto es del propio usuario.
        escritura.vincular_canal(conn, msg.canal, msg.usuario_canal_id, msg.telefono_compartido, msg.chat_id)
    telefono = lectura.telefono_vinculado(conn, msg.canal, msg.usuario_canal_id)
    if telefono is None:
        return {"identidad": None, "salidas": [MensajeSaliente(texto=textos.PEDIR_CONTACTO, pedir_contacto=True)]}
    identidad = lectura.identidad_por_telefono(conn, telefono)
    if identidad is None:
        escritura.crear_derivacion(conn, "telefono_no_registrado", msg.texto or "(sin texto)", telefono=telefono)
        return {"identidad": None, "salidas": [MensajeSaliente(texto=textos.TELEFONO_NO_REGISTRADO)]}
    return {"identidad": identidad}


def saludar(state: EstadoConversacion) -> dict:
    i = state["identidad"]
    return {"salidas": [MensajeSaliente(texto=textos.SALUDO.format(nombre=i.nombre.split()[0], unidad=i.unidad),
                                        botones=textos.BOTONES_INICIO)]}


def pedir_consulta(state: EstadoConversacion) -> dict:
    return {"salidas": [MensajeSaliente(texto="Dale, ¿qué querés consultar del reglamento o de las actas?")]}


def despachar(state: EstadoConversacion) -> dict:
    """Lleva la cuenta de los no entendidos seguidos para la repregunta única."""
    if state["intake"].intent is not Intent.UNKNOWN:
        return {"no_entendidos_seguidos": 0}
    return {}


def no_entendido(state: EstadoConversacion) -> dict:
    seguidos = state.get("no_entendidos_seguidos", 0) + 1
    if seguidos < 2:
        return {"no_entendidos_seguidos": seguidos,
                "salidas": [MensajeSaliente(texto=textos.REPREGUNTA, botones=textos.BOTONES_INICIO)]}
    i = state["identidad"]
    escritura.crear_derivacion(get_conn(), "no_entendido", state["mensaje"].texto, consorcio_id=i.consorcio_id,
                               unidad_id=i.unidad_id, telefono=i.telefono)
    return {"no_entendidos_seguidos": 0, "salidas": [MensajeSaliente(texto=textos.DERIVADO_NO_ENTENDIDO)]}


def registrar_caso(state: EstadoConversacion) -> dict:
    i = state["identidad"]
    caso = Caso(consorcio_id=i.consorcio_id, unidad_id=i.unidad_id, reclamo=state["reclamo_en_curso"])
    caso = escritura.registrar_caso(get_conn(), caso.transicionar(EstadoCaso.REGISTRADO))
    return {"reclamo_en_curso": None, "casos_lanzados": [caso.caso_id],
            "salidas": [MensajeSaliente(texto=textos.CASO_REGISTRADO.format(caso_id=caso.caso_id))]}


# ------------------------------------------------------------------ ruteo

def _despues_de_identificar(state: EstadoConversacion) -> str:
    if state.get("identidad") is None:
        return END
    msg = state["mensaje"]
    t = normalizar(msg.texto)
    if t == normalizar(textos.BOTON_HABLAR):
        return "hablar_con_admin"
    if t == normalizar(textos.BOTON_REGLAMENTO):
        return "pedir_consulta"
    if not t and not msg.adjuntos:
        return "saludar"
    return "intake"


def _fan_out(state: EstadoConversacion):
    intents = state["intake"].intents()
    if state["intake"].urgencia and intents == [Intent.UNKNOWN]:
        return END  # la urgencia ya se respondió; no hace falta repreguntar
    return [Send(RAMA_POR_INTENT[i], state) for i in intents]


def _despues_de_despachar(state: EstadoConversacion):
    return "avisar_urgencia" if state["intake"].urgencia else _fan_out(state)


def _despues_de_verificar(state: EstadoConversacion) -> str:
    return "responder_reglamento" if state["verificacion_consulta"]["ok"] else "derivar_sin_fuente"


def _despues_de_completar(state: EstadoConversacion) -> str:
    borrador = state.get("reclamo_en_curso")
    return "registrar_caso" if borrador and not borrador.faltantes() else END


# ------------------------------------------------------------------ armado

def construir(checkpointer=None, nodos: dict | None = None):
    n = {**NODOS_CONVERSACION, **(nodos or {})}
    g = StateGraph(EstadoConversacion)
    for nombre, fn in [("inicio", inicio), ("identificar", identificar), ("saludar", saludar),
                       ("pedir_consulta", pedir_consulta), ("despachar", despachar),
                       ("no_entendido", no_entendido), ("registrar_caso", registrar_caso)]:
        g.add_node(nombre, fn)
    for nombre, fn in n.items():
        g.add_node(nombre, fn)

    ramas = list(RAMA_POR_INTENT.values())
    g.add_edge(START, "inicio")
    g.add_edge("inicio", "identificar")
    g.add_conditional_edges("identificar", _despues_de_identificar,
                            ["hablar_con_admin", "pedir_consulta", "saludar", "intake", END])
    g.add_edge("intake", "despachar")
    g.add_conditional_edges("despachar", _despues_de_despachar, ["avisar_urgencia", *ramas])
    g.add_conditional_edges("avisar_urgencia", _fan_out, [*ramas, END])
    g.add_edge("documental", "verificar_consulta")
    g.add_conditional_edges("verificar_consulta", _despues_de_verificar, ["responder_reglamento", "derivar_sin_fuente"])
    g.add_edge("gastos", "responder_gastos")
    g.add_conditional_edges("completar_datos", _despues_de_completar, ["registrar_caso", END])
    for fin in ["responder_reglamento", "derivar_sin_fuente", "responder_gastos", "registrar_caso",
                "no_entendido", "saludar", "pedir_consulta", "hablar_con_admin"]:
        g.add_edge(fin, END)
    return g.compile(checkpointer=checkpointer)
