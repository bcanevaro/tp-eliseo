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
from eliseo.config import checkpoint_db_path, db_url, es_postgres
from eliseo.grafo import caso as grafo_caso
from eliseo.grafo import conversacion as grafo_conversacion
from eliseo.plataforma import escritura, lectura
from eliseo.plataforma.db import activar_rls, get_conn
from eliseo.schemas import DecisionAdmin, MensajeEntrante, MensajeSaliente


def _tipos_serializables() -> list[tuple[str, str]]:
    """Los contratos que viajan en el estado, permitidos explícitamente en el checkpoint."""
    tipos = [getattr(schemas, nombre) for nombre in schemas.__all__]
    return [(t.__module__, t.__name__) for t in tipos if isinstance(t, type)]


@lru_cache(maxsize=None)
def _checkpointer(destino: str):
    """Con Postgres, los checkpoints van a la misma base (design D10 de cuentas-administracion),
    así el bot y el panel pueden correr en máquinas distintas; con SQLite, a su archivo aparte."""
    serde = JsonPlusSerializer(allowed_msgpack_modules=_tipos_serializables())
    if es_postgres(destino):
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg import Connection
        from psycopg.rows import dict_row

        # prepare_threshold=None: el pooler de Supabase no admite sentencias preparadas.
        conn = Connection.connect(destino.replace("postgresql+psycopg://", "postgresql://"),
                                  autocommit=True, prepare_threshold=None, row_factory=dict_row)
        saver = PostgresSaver(conn, serde=serde)
        saver.setup()
        activar_rls(get_conn(), ("checkpoints", "checkpoint_blobs", "checkpoint_writes", "checkpoint_migrations"))
        return saver
    return SqliteSaver(sqlite3.connect(destino, check_same_thread=False), serde=serde)


@lru_cache(maxsize=None)
def _grafos(destino: str):
    cp = _checkpointer(destino)
    return grafo_conversacion.construir(cp), grafo_caso.construir(cp)


def destino_checkpoints() -> str:
    url = db_url()
    return url if es_postgres(url) else str(checkpoint_db_path())


def grafos():
    """(conversación, caso) compilados sobre el checkpointer configurado."""
    return _grafos(destino_checkpoints())


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


def procesar_mensaje(msg: MensajeEntrante, al_avanzar=None, lanzar_caso=None) -> list[MensajeSaliente]:
    """`al_avanzar(nodo, actualizacion)`, si se pasa, se llama después de cada nodo (el canal lo
    usa para mostrar el estado, p. ej. "Buscando en el reglamento…").
    `lanzar_caso(caso_id, telefono)`, si se pasa, reemplaza a `iniciar_caso`: el bot lo usa para
    correr el análisis del reclamo después de contestarle al vecino."""
    conversacion, _ = grafos()
    config = {"configurable": {"thread_id": thread_conversacion(msg)}}
    if al_avanzar is None:
        resultado = conversacion.invoke({"mensaje": msg}, config)
    else:
        for paso in conversacion.stream({"mensaje": msg}, config, stream_mode="updates"):
            for nodo, actualizacion in paso.items():
                al_avanzar(nodo, actualizacion)
        resultado = conversacion.get_state(config).values
    identidad = resultado.get("identidad")
    for caso_id in resultado.get("casos_lanzados") or []:
        (lanzar_caso or iniciar_caso)(caso_id, identidad.telefono)
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
