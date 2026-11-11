"""Punto de entrada a los grafos para el canal y el panel.

    from eliseo.grafo.runtime import procesar_mensaje, retomar_caso

- El bot llama a `procesar_mensaje(msg)` por cada mensaje y manda las salidas que devuelve.
- El panel llama a `retomar_caso(caso_id, decision)` para destrabar un caso.
- Los mensajes fuera de turno (resolución de un caso, avisos al administrador) quedan en la
  outbox de la base y los envía el proceso del bot (ver escritura.outbox_pendientes).
"""
import sqlite3
from functools import lru_cache

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

import eliseo.schemas as schemas
from eliseo.config import checkpoint_db_path
from eliseo.grafo import caso as grafo_caso
from eliseo.grafo import conversacion as grafo_conversacion
from eliseo.plataforma import escritura, lectura
from eliseo.plataforma.db import get_conn
from eliseo.schemas import DecisionAdmin, MensajeEntrante, MensajeSaliente


def _tipos_serializables() -> list[tuple[str, str]]:
    """Los contratos que viajan en el estado, permitidos explícitamente en el checkpoint."""
    tipos = [getattr(schemas, nombre) for nombre in schemas.__all__]
    return [(t.__module__, t.__name__) for t in tipos if isinstance(t, type)]


@lru_cache(maxsize=None)
def _checkpointer(path: str) -> SqliteSaver:
    serde = JsonPlusSerializer(allowed_msgpack_modules=_tipos_serializables())
    return SqliteSaver(sqlite3.connect(path, check_same_thread=False), serde=serde)


@lru_cache(maxsize=None)
def _grafos(path: str):
    cp = _checkpointer(path)
    return grafo_conversacion.construir(cp), grafo_caso.construir(cp)


def grafos():
    """(conversación, caso) compilados sobre el checkpointer configurado."""
    return _grafos(str(checkpoint_db_path()))


def thread_conversacion(msg: MensajeEntrante) -> str:
    """'<telefono>:<consorcio_id>' si el usuario ya está identificado; si no, un hilo provisorio."""
    conn = get_conn()
    telefono = msg.telefono_compartido or lectura.telefono_vinculado(conn, msg.canal, msg.usuario_canal_id)
    identidad = lectura.identidad_por_telefono(conn, telefono) if telefono else None
    if identidad:
        return f"{identidad.telefono}:{identidad.consorcio_id}"
    return f"sin-identificar:{msg.canal}:{msg.usuario_canal_id}"


def thread_caso(caso_id: int) -> str:
    return f"caso:{caso_id}"


def procesar_mensaje(msg: MensajeEntrante) -> list[MensajeSaliente]:
    conversacion, _ = grafos()
    config = {"configurable": {"thread_id": thread_conversacion(msg)}}
    resultado = conversacion.invoke({"mensaje": msg}, config)
    identidad = resultado.get("identidad")
    for caso_id in resultado.get("casos_lanzados") or []:
        iniciar_caso(caso_id, identidad.telefono)
    return resultado.get("salidas", [])


def iniciar_caso(caso_id: int, telefono: str) -> dict:
    """Corre el grafo de caso hasta que queda esperando al administrador."""
    _, caso = grafos()
    registrado = escritura.obtener_caso(get_conn(), caso_id)
    return caso.invoke({"caso": registrado, "telefono": telefono},
                       {"configurable": {"thread_id": thread_caso(caso_id)}})


def retomar_caso(caso_id: int, decision: DecisionAdmin) -> dict:
    _, caso = grafos()
    config = {"configurable": {"thread_id": thread_caso(caso_id)}}
    if "panel" not in caso.get_state(config).next:
        raise ValueError(f"El caso {caso_id} no está esperando una decisión")
    return caso.invoke(Command(resume=decision.model_dump(mode="json")), config)


def estado_caso(caso_id: int) -> dict:
    """Estado del grafo del caso (para el panel): valores y próximo paso."""
    _, caso = grafos()
    snap = caso.get_state({"configurable": {"thread_id": thread_caso(caso_id)}})
    return {"valores": snap.values, "siguiente": snap.next}
