"""Ejecución de lo que aprueba el administrador y avisos a la administración (spec ejecucion).

Es código, sin LLM: son las únicas acciones irreversibles del sistema, así que ninguna depende
de lo que escriba un modelo. Todo lo que sale hacia una persona pasa por la outbox con una
clave de idempotencia; el proceso del bot la vacía con `enviar_pendientes`.

    ejecucion        caso aprobado → mensaje al vecino + pedido + precedente + APROBADO
    rechazo          caso rechazado → mensaje manual (si lo hay) + RECHAZADO
    avisar_urgencia  bandeja + aviso inmediato al chat de la administración
    derivar_sin_fuente, hablar_con_admin   bandeja del panel
"""
import logging
import re
from typing import Callable

from eliseo import textos
from eliseo.agentes.mediador import precedentes
from eliseo.config import env
from eliseo.plataforma import escritura, lectura
from eliseo.plataforma.db import get_conn
from eliseo.schemas import Caso, Dictamen, EstadoCaso, MensajeSaliente

log = logging.getLogger(__name__)


def con_fuentes(texto: str, refs: list[str]) -> str:
    return f"{texto}\n\nFuente: {', '.join(refs)}" if refs else texto


def con_numero_de_caso(texto: str, caso_id: int) -> str:
    """El vecino siempre recibe el número de su reclamo, aunque el administrador lo haya borrado al editar."""
    return texto if re.search(rf"#\s*{caso_id}\b", texto) else f"Reclamo #{caso_id}: {texto}"


def mensaje_aprobado(caso: Caso, dictamen: Dictamen, mensaje_final: str | None) -> str:
    """Exactamente lo que recibe el vecino al aprobar (lo usa también la confirmación del panel)."""
    texto = con_numero_de_caso(mensaje_final or dictamen.mensaje_vecino, caso.caso_id)
    return con_fuentes(texto, sorted(dictamen.todas_las_citas()))


def tipo_pedido(dictamen: Dictamen) -> str:
    return "inspeccion" if dictamen.recomendacion.tipo == "inspeccion" else "trabajo"


def _precedente(conn, caso: Caso, dictamen: Dictamen, dictamen_id: int, admin_id: str, modificado: bool) -> str:
    rec = dictamen.recomendacion
    if rec.tipo == "asignar":
        h = next(h for h in dictamen.hipotesis if h.id == rec.hipotesis)
        responsable, resolucion = h.responsable, f"{h.descripcion}. {rec.accion}"
    else:
        responsable, resolucion = "a determinar", f"Se ordenó inspección: {rec.accion}"
    citas = sorted(dictamen.todas_las_citas())
    if citas:
        resolucion += f" ({', '.join(citas)})"
    columna = caso.unidad_id[-1]
    prec_id, _ = escritura.crear_precedente(
        conn, consorcio_id=caso.consorcio_id, unidad_id=caso.unidad_id, tipo=precedentes.tipo_reclamo(caso),
        ubicacion=f"columna {columna}, {caso.reclamo.ambiente}" if caso.reclamo.ambiente else f"columna {columna}",
        descripcion=f"{caso.reclamo.descripcion} ({caso.reclamo.ambiente or 'ambiente sin indicar'})",
        resolucion=resolucion, responsable=responsable, caso_id=caso.caso_id, dictamen_id=dictamen_id,
        procedencia=f"caso {caso.caso_id}, dictamen {dictamen_id}, "
                    f"{'modificado y aprobado' if modificado else 'aprobado'} por {admin_id}",
    )
    # SQLite es la verdad; la copia en Pinecone es best effort y no bloquea la aprobación (design D9).
    precedentes.indexar(conn, caso.consorcio_id, prec_id)
    return prec_id


def ejecucion(state: dict) -> dict:
    """Corre solo después de APROBAR o MODIFICAR. Reintentarla no duplica nada: cada acción
    lleva el id del dictamen como clave."""
    conn, caso, decision = get_conn(), state["caso"], state["decision"]
    dictamen, dictamen_id = state["dictamen"], state["dictamen_id"]

    escritura.encolar_mensaje(conn, f"vecino:{state['telefono']}",
                              MensajeSaliente(texto=mensaje_aprobado(caso, dictamen, decision.mensaje_final)),
                              clave=f"dictamen:{dictamen_id}:vecino")
    escritura.crear_pedido(conn, caso.caso_id, dictamen_id, tipo_pedido(dictamen), dictamen.recomendacion.accion)
    _precedente(conn, caso, dictamen, dictamen_id, decision.admin_id, decision.mensaje_final is not None)

    actual = escritura.obtener_caso(conn, caso.caso_id)
    if actual.estado is EstadoCaso.PENDIENTE_APROBACION:
        actual = escritura.cambiar_estado(conn, caso.caso_id, EstadoCaso.APROBADO)
    return {"caso": actual}


def rechazo(state: dict) -> dict:
    """El rechazo no se convierte en precedente; el motivo ya quedó en la decisión."""
    conn, caso, decision = get_conn(), state["caso"], state["decision"]
    if decision.mensaje_final:
        escritura.encolar_mensaje(conn, f"vecino:{state['telefono']}",
                                  MensajeSaliente(texto=con_numero_de_caso(decision.mensaje_final, caso.caso_id),
                                                  de_la_administracion=True),
                                  clave=f"dictamen:{state['dictamen_id']}:rechazo")
    actual = escritura.obtener_caso(conn, caso.caso_id)
    if actual.estado is EstadoCaso.PENDIENTE_APROBACION:
        actual = escritura.cambiar_estado(conn, caso.caso_id, EstadoCaso.RECHAZADO)
    return {"caso": actual}


# ---------------------------------------------------------------- derivaciones (rama de conversación)

def avisar_urgencia(state: dict) -> dict:
    ident, conn = state["identidad"], get_conn()
    texto = state["mensaje"].texto
    der_id = escritura.crear_derivacion(conn, "urgencia", texto, consorcio_id=ident.consorcio_id,
                                        unidad_id=ident.unidad_id, telefono=ident.telefono)
    escritura.encolar_mensaje(conn, f"admin:{ident.consorcio_id}",
                              MensajeSaliente(texto=f"🚨 URGENCIA en {ident.unidad} ({ident.nombre}, {ident.telefono}): {texto}"),
                              clave=f"urgencia:{der_id}")
    tel = lectura.consorcio(conn, ident.consorcio_id)["telefono_emergencias"]
    return {"salidas": [MensajeSaliente(texto=textos.URGENCIA.format(telefono_emergencias=tel))]}


def derivar_sin_fuente(state: dict) -> dict:
    ident = state["identidad"]
    escritura.crear_derivacion(get_conn(), "sin_fuente", state["mensaje"].texto, consorcio_id=ident.consorcio_id,
                               unidad_id=ident.unidad_id, telefono=ident.telefono,
                               detalle={"verificacion": state.get("verificacion_consulta")})
    return {"salidas": [MensajeSaliente(texto=textos.DERIVADO_SIN_FUENTE)]}


def hablar_con_admin(state: dict) -> dict:
    ident = state["identidad"]
    escritura.crear_derivacion(get_conn(), "hablar_con_admin", state["mensaje"].texto, consorcio_id=ident.consorcio_id,
                               unidad_id=ident.unidad_id, telefono=ident.telefono)
    return {"salidas": [MensajeSaliente(texto=textos.DERIVADO_HABLAR)]}


# ---------------------------------------------------------------- envío de la outbox (lo llama el bot)

def chat_de_destino(conn, destino: str) -> str | None:
    """'vecino:<telefono>' → chat de Telegram vinculado; 'admin:<consorcio>' → TELEGRAM_CHAT_ADMIN_ID."""
    tipo, _, valor = destino.partition(":")
    if tipo == "vecino":
        return lectura.chat_de_telefono(conn, valor)
    if tipo == "admin":
        return env("TELEGRAM_CHAT_ADMIN_ID", default="") or None
    return None


def enviar_pendientes(enviar: Callable[[str, MensajeSaliente], None], conn=None) -> int:
    """Manda los mensajes pendientes con `enviar(chat_id, mensaje)` y los marca enviados.
    Los que no tienen chat (vecino sin vincular, admin sin configurar) quedan pendientes."""
    conn = conn or get_conn()
    enviados = 0
    for outbox_id, destino, mensaje in escritura.outbox_pendientes(conn):
        chat = chat_de_destino(conn, destino)
        if not chat:
            continue
        try:
            enviar(chat, mensaje)
        except Exception:  # se reintenta en la próxima pasada
            log.exception("No se pudo enviar el mensaje %s a %s", outbox_id, destino)
            continue
        escritura.marcar_enviado(conn, outbox_id)
        enviados += 1
    return enviados
