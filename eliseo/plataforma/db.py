"""SQLite que simula la plataforma de gestión (design D4).

Los montos se guardan como TEXT con dos decimales y se leen como Decimal, para no perder
exactitud: los números salen de acá, nunca del LLM.
"""
import sqlite3
from pathlib import Path

from eliseo.config import db_path

ESQUEMA = """
CREATE TABLE IF NOT EXISTS consorcios (
    consorcio_id TEXT PRIMARY KEY,
    nombre TEXT NOT NULL,
    direccion TEXT NOT NULL,
    administracion TEXT NOT NULL,
    administradora TEXT NOT NULL,
    telefono_emergencias TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS unidades (
    unidad_id TEXT PRIMARY KEY,
    consorcio_id TEXT NOT NULL REFERENCES consorcios,
    unidad TEXT NOT NULL,
    piso INTEGER NOT NULL,
    depto TEXT NOT NULL,
    coeficiente TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS vecinos (
    telefono TEXT PRIMARY KEY,
    unidad_id TEXT NOT NULL REFERENCES unidades,
    nombre TEXT NOT NULL
);
-- design D7: Telegram no da el teléfono; se vincula una vez al compartir el contacto.
CREATE TABLE IF NOT EXISTS vinculos_canal (
    canal TEXT NOT NULL,
    usuario_canal_id TEXT NOT NULL,
    telefono TEXT NOT NULL,
    chat_id TEXT,
    creado TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (canal, usuario_canal_id)
);
CREATE TABLE IF NOT EXISTS facturas (
    fac_id TEXT PRIMARY KEY,
    consorcio_id TEXT NOT NULL REFERENCES consorcios,
    proveedor TEXT NOT NULL,
    concepto TEXT NOT NULL,
    monto TEXT NOT NULL,
    fecha TEXT NOT NULL,
    periodo TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS liquidaciones (
    liq_id TEXT PRIMARY KEY,
    consorcio_id TEXT NOT NULL REFERENCES consorcios,
    periodo TEXT NOT NULL,
    fecha_emision TEXT NOT NULL,
    vencimiento TEXT NOT NULL,
    total TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS lineas_liquidacion (
    id INTEGER PRIMARY KEY,
    liq_id TEXT NOT NULL REFERENCES liquidaciones,
    orden INTEGER NOT NULL,
    rubro TEXT NOT NULL,
    concepto TEXT NOT NULL,
    monto TEXT NOT NULL,
    comprobante TEXT REFERENCES facturas
);
CREATE TABLE IF NOT EXISTS movimientos_cc (
    id INTEGER PRIMARY KEY,
    unidad_id TEXT NOT NULL REFERENCES unidades,
    fecha TEXT NOT NULL,
    concepto TEXT NOT NULL,
    debe TEXT NOT NULL DEFAULT '0.00',
    haber TEXT NOT NULL DEFAULT '0.00',
    comprobante TEXT
);
CREATE TABLE IF NOT EXISTS casos (
    caso_id INTEGER PRIMARY KEY AUTOINCREMENT,
    consorcio_id TEXT NOT NULL REFERENCES consorcios,
    unidad_id TEXT NOT NULL REFERENCES unidades,
    reclamo_json TEXT NOT NULL,
    estado TEXT NOT NULL,
    creado TEXT NOT NULL,
    actualizado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dictamenes (
    dictamen_id INTEGER PRIMARY KEY AUTOINCREMENT,
    caso_id INTEGER NOT NULL REFERENCES casos,
    version INTEGER NOT NULL,
    dictamen_json TEXT NOT NULL,
    verificacion_json TEXT,
    creado TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS decisiones (
    id INTEGER PRIMARY KEY,
    dictamen_id INTEGER NOT NULL REFERENCES dictamenes,
    caso_id INTEGER NOT NULL REFERENCES casos,
    accion TEXT NOT NULL,
    admin_id TEXT NOT NULL,
    mensaje_final TEXT,
    motivo TEXT,
    creado TEXT NOT NULL DEFAULT (datetime('now'))
);
-- Toda abstención, urgencia o pedido de hablar con una persona cae acá (bandeja del panel).
CREATE TABLE IF NOT EXISTS derivaciones (
    id INTEGER PRIMARY KEY,
    consorcio_id TEXT,
    unidad_id TEXT,
    telefono TEXT,
    tipo TEXT NOT NULL CHECK (tipo IN ('urgencia', 'sin_fuente', 'hablar_con_admin', 'no_entendido', 'telefono_no_registrado')),
    texto TEXT NOT NULL,
    detalle_json TEXT,
    estado TEXT NOT NULL DEFAULT 'pendiente',
    creado TEXT NOT NULL DEFAULT (datetime('now'))
);
-- Idempotencia de la ejecución (spec ejecucion): una acción por dictamen y tipo.
CREATE TABLE IF NOT EXISTS pedidos (
    id INTEGER PRIMARY KEY,
    caso_id INTEGER NOT NULL REFERENCES casos,
    dictamen_id INTEGER NOT NULL REFERENCES dictamenes,
    tipo TEXT NOT NULL CHECK (tipo IN ('inspeccion', 'trabajo', 'mensaje_vecino')),
    descripcion TEXT NOT NULL,
    creado TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (dictamen_id, tipo)
);
-- Mensajes que salen fuera del turno de conversación (resolución de un caso, aviso de urgencia
-- al administrador, respuesta manual desde el panel). El proceso del bot los envía.
-- destino: 'vecino:<telefono>' o 'admin:<consorcio_id>'. clave: idempotencia.
CREATE TABLE IF NOT EXISTS outbox (
    id INTEGER PRIMARY KEY,
    destino TEXT NOT NULL,
    mensaje_json TEXT NOT NULL,
    clave TEXT UNIQUE,
    enviado TEXT,
    creado TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS precedentes (
    prec_id TEXT PRIMARY KEY,
    consorcio_id TEXT NOT NULL REFERENCES consorcios,
    unidad_id TEXT REFERENCES unidades,
    tipo TEXT NOT NULL,
    ubicacion TEXT,
    descripcion TEXT NOT NULL,
    resolucion TEXT NOT NULL,
    responsable TEXT NOT NULL,
    fecha TEXT NOT NULL,
    caso_id INTEGER REFERENCES casos,
    dictamen_id INTEGER REFERENCES dictamenes,
    procedencia TEXT NOT NULL
);
"""

TABLAS = [
    "outbox", "pedidos", "decisiones", "dictamenes", "derivaciones", "precedentes", "casos",
    "movimientos_cc", "lineas_liquidacion", "liquidaciones", "facturas",
    "vinculos_canal", "vecinos", "unidades", "consorcios",
]


def conectar(path: Path | str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path or db_path()), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")  # el bot y el panel son procesos distintos
    return conn


_conexiones: dict[str, sqlite3.Connection] = {}


def get_conn() -> sqlite3.Connection:
    """Conexión del proceso a la base configurada (los nodos del grafo usan esta)."""
    path = str(db_path())
    if path not in _conexiones:
        conn = conectar(path)
        crear_esquema(conn)
        _conexiones[path] = conn
    return _conexiones[path]


def crear_esquema(conn: sqlite3.Connection) -> None:
    conn.executescript(ESQUEMA)


def borrar_todo(conn: sqlite3.Connection) -> None:
    for tabla in TABLAS:
        conn.execute(f"DROP TABLE IF EXISTS {tabla}")
    conn.commit()
