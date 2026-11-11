"""Escrituras a la plataforma simulada: casos, dictámenes, decisiones, derivaciones y pedidos.

Ningún agente llama a estas funciones directamente: las usan los nodos de código del grafo
(registrar caso, panel, ejecución). La única excepción prevista es la escritura aditiva del
borrador de dictamen.
"""
import json
import sqlite3
from datetime import datetime, timezone

from eliseo.schemas import Caso, DecisionAdmin, Dictamen, EstadoCaso, MensajeSaliente, ReclamoBorrador


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def vincular_canal(conn: sqlite3.Connection, canal: str, usuario_canal_id: str, telefono: str,
                   chat_id: str | None = None) -> None:
    conn.execute(
        """INSERT INTO vinculos_canal (canal, usuario_canal_id, telefono, chat_id) VALUES (?, ?, ?, ?)
           ON CONFLICT (canal, usuario_canal_id) DO UPDATE SET telefono = excluded.telefono, chat_id = excluded.chat_id""",
        (canal, usuario_canal_id, telefono, chat_id),
    )
    conn.commit()


def registrar_caso(conn: sqlite3.Connection, caso: Caso) -> Caso:
    ahora = _ahora()
    cur = conn.execute(
        "INSERT INTO casos (consorcio_id, unidad_id, reclamo_json, estado, creado, actualizado) VALUES (?, ?, ?, ?, ?, ?)",
        (caso.consorcio_id, caso.unidad_id, caso.reclamo.model_dump_json(), caso.estado.value, ahora, ahora),
    )
    conn.commit()
    return caso.model_copy(update={"caso_id": cur.lastrowid})


def obtener_caso(conn: sqlite3.Connection, caso_id: int) -> Caso | None:
    f = conn.execute("SELECT * FROM casos WHERE caso_id = ?", (caso_id,)).fetchone()
    if not f:
        return None
    return Caso(caso_id=f["caso_id"], consorcio_id=f["consorcio_id"], unidad_id=f["unidad_id"],
                reclamo=ReclamoBorrador.model_validate_json(f["reclamo_json"]), estado=EstadoCaso(f["estado"]),
                creado=f["creado"], actualizado=f["actualizado"])


def cambiar_estado(conn: sqlite3.Connection, caso_id: int, nuevo: EstadoCaso) -> Caso:
    """Valida la transición con la máquina de estados del contrato antes de escribir."""
    caso = obtener_caso(conn, caso_id)
    if caso is None:
        raise KeyError(f"No existe el caso {caso_id}")
    caso = caso.transicionar(nuevo)
    conn.execute("UPDATE casos SET estado = ?, actualizado = ? WHERE caso_id = ?",
                 (caso.estado.value, _ahora(), caso_id))
    conn.commit()
    return caso


def guardar_dictamen(conn: sqlite3.Connection, caso_id: int, dictamen: Dictamen,
                     verificacion: dict | None = None) -> int:
    """Escritura aditiva: cada vuelta del Mediador es una versión nueva, nunca se pisa."""
    (version,) = conn.execute(
        "SELECT COALESCE(MAX(version), 0) + 1 FROM dictamenes WHERE caso_id = ?", (caso_id,)
    ).fetchone()
    cur = conn.execute(
        "INSERT INTO dictamenes (caso_id, version, dictamen_json, verificacion_json) VALUES (?, ?, ?, ?)",
        (caso_id, version, dictamen.model_dump_json(), json.dumps(verificacion) if verificacion else None),
    )
    conn.commit()
    return cur.lastrowid


def guardar_decision(conn: sqlite3.Connection, dictamen_id: int, caso_id: int, decision: DecisionAdmin) -> None:
    conn.execute(
        "INSERT INTO decisiones (dictamen_id, caso_id, accion, admin_id, mensaje_final, motivo) VALUES (?, ?, ?, ?, ?, ?)",
        (dictamen_id, caso_id, decision.accion.value, decision.admin_id, decision.mensaje_final, decision.motivo),
    )
    conn.commit()


def crear_derivacion(conn: sqlite3.Connection, tipo: str, texto: str, *, consorcio_id: str | None = None,
                     unidad_id: str | None = None, telefono: str | None = None, detalle: dict | None = None) -> int:
    cur = conn.execute(
        "INSERT INTO derivaciones (consorcio_id, unidad_id, telefono, tipo, texto, detalle_json) VALUES (?, ?, ?, ?, ?, ?)",
        (consorcio_id, unidad_id, telefono, tipo, texto, json.dumps(detalle, default=str) if detalle else None),
    )
    conn.commit()
    return cur.lastrowid


def encolar_mensaje(conn: sqlite3.Connection, destino: str, mensaje: MensajeSaliente,
                    clave: str | None = None) -> bool:
    """Deja un mensaje para que lo envíe el bot. Con `clave`, encolar dos veces no duplica.
    Devuelve True si quedó encolado ahora."""
    cur = conn.execute(
        "INSERT OR IGNORE INTO outbox (destino, mensaje_json, clave) VALUES (?, ?, ?)",
        (destino, mensaje.model_dump_json(), clave),
    )
    conn.commit()
    return cur.rowcount == 1


def outbox_pendientes(conn: sqlite3.Connection) -> list[tuple[int, str, MensajeSaliente]]:
    filas = conn.execute("SELECT id, destino, mensaje_json FROM outbox WHERE enviado IS NULL ORDER BY id").fetchall()
    return [(f["id"], f["destino"], MensajeSaliente.model_validate_json(f["mensaje_json"])) for f in filas]


def marcar_enviado(conn: sqlite3.Connection, outbox_id: int) -> None:
    conn.execute("UPDATE outbox SET enviado = ? WHERE id = ?", (_ahora(), outbox_id))
    conn.commit()


def crear_pedido(conn: sqlite3.Connection, caso_id: int, dictamen_id: int, tipo: str, descripcion: str) -> tuple[int, bool]:
    """Idempotente por (dictamen_id, tipo). Devuelve (id, creado_ahora)."""
    cur = conn.execute(
        "INSERT OR IGNORE INTO pedidos (caso_id, dictamen_id, tipo, descripcion) VALUES (?, ?, ?, ?)",
        (caso_id, dictamen_id, tipo, descripcion),
    )
    conn.commit()
    (pid,) = conn.execute("SELECT id FROM pedidos WHERE dictamen_id = ? AND tipo = ?", (dictamen_id, tipo)).fetchone()
    return pid, cur.rowcount == 1
