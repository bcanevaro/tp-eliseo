"""Base que simula la plataforma de gestión (design D4 de bootstrap, D3 de cuentas-administracion).

Puede ser Postgres (Supabase, con ELISEO_DB_URL) o un SQLite local. El resto del código no se
entera: `get_conn()` devuelve una `Conexion` con la interfaz de `sqlite3.Connection` que se usa en
el proyecto (`execute` con `?` o `:nombre`, filas accesibles por nombre o posición, `commit`).
El SQL del proyecto se escribe en el subconjunto que entienden los dos motores (`ON CONFLICT`,
`RETURNING`, `CURRENT_DATE`); solo el esquema tiene variantes por motor.

Los montos se guardan como TEXT con dos decimales y se leen como Decimal, para no perder
exactitud: los números salen de acá, nunca del LLM.
"""
import re
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine

from eliseo.config import db_url

# {id}: entero autoincremental sin garantía de no reuso; {id_auto}: con AUTOINCREMENT en SQLite.
# {ahora}: fecha y hora UTC como texto 'AAAA-MM-DD HH:MM:SS', igual en los dos motores.
ESQUEMA = """
-- Cuentas (spec cuentas-admin): cada administración tiene sus consorcios y sus administradores.
-- administracion_id es el slug del nombre (el mismo que usan los criterios del Mediador).
CREATE TABLE IF NOT EXISTS administraciones (
    administracion_id TEXT PRIMARY KEY,
    nombre TEXT NOT NULL UNIQUE,
    chat_avisos_id TEXT,
    creado TEXT NOT NULL DEFAULT {ahora}
);
-- password_hash: login local (bcrypt). auth_user_id: login con Supabase Auth (design D4).
CREATE TABLE IF NOT EXISTS administradores (
    admin_id {id},
    administracion_id TEXT NOT NULL REFERENCES administraciones,
    email TEXT NOT NULL UNIQUE,
    nombre TEXT NOT NULL,
    password_hash TEXT,
    auth_user_id TEXT UNIQUE,
    creado TEXT NOT NULL DEFAULT {ahora}
);
-- administracion y administradora (texto) quedan por compatibilidad: los leen el Mediador y los
-- mensajes; administracion_id es la que define quién ve el consorcio. activo = 0: baja lógica.
CREATE TABLE IF NOT EXISTS consorcios (
    consorcio_id TEXT PRIMARY KEY,
    nombre TEXT NOT NULL,
    direccion TEXT NOT NULL,
    administracion TEXT NOT NULL,
    administradora TEXT NOT NULL,
    telefono_emergencias TEXT NOT NULL,
    administracion_id TEXT REFERENCES administraciones,
    activo INTEGER NOT NULL DEFAULT 1
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
    creado TEXT NOT NULL DEFAULT {ahora},
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
    id {id},
    liq_id TEXT NOT NULL REFERENCES liquidaciones,
    orden INTEGER NOT NULL,
    rubro TEXT NOT NULL,
    concepto TEXT NOT NULL,
    monto TEXT NOT NULL,
    comprobante TEXT REFERENCES facturas
);
CREATE TABLE IF NOT EXISTS movimientos_cc (
    id {id},
    unidad_id TEXT NOT NULL REFERENCES unidades,
    fecha TEXT NOT NULL,
    concepto TEXT NOT NULL,
    debe TEXT NOT NULL DEFAULT '0.00',
    haber TEXT NOT NULL DEFAULT '0.00',
    comprobante TEXT
);
CREATE TABLE IF NOT EXISTS casos (
    caso_id {id_auto},
    consorcio_id TEXT NOT NULL REFERENCES consorcios,
    unidad_id TEXT NOT NULL REFERENCES unidades,
    reclamo_json TEXT NOT NULL,
    estado TEXT NOT NULL,
    creado TEXT NOT NULL,
    actualizado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dictamenes (
    dictamen_id {id_auto},
    caso_id INTEGER NOT NULL REFERENCES casos,
    version INTEGER NOT NULL,
    dictamen_json TEXT NOT NULL,
    verificacion_json TEXT,
    creado TEXT NOT NULL DEFAULT {ahora}
);
CREATE TABLE IF NOT EXISTS decisiones (
    id {id},
    dictamen_id INTEGER NOT NULL REFERENCES dictamenes,
    caso_id INTEGER NOT NULL REFERENCES casos,
    accion TEXT NOT NULL,
    admin_id TEXT NOT NULL,
    mensaje_final TEXT,
    motivo TEXT,
    creado TEXT NOT NULL DEFAULT {ahora}
);
-- Toda abstención, urgencia o pedido de hablar con una persona cae acá (bandeja del panel).
CREATE TABLE IF NOT EXISTS derivaciones (
    id {id},
    consorcio_id TEXT,
    unidad_id TEXT,
    telefono TEXT,
    tipo TEXT NOT NULL CHECK (tipo IN ('urgencia', 'sin_fuente', 'hablar_con_admin', 'no_entendido', 'telefono_no_registrado')),
    texto TEXT NOT NULL,
    detalle_json TEXT,
    estado TEXT NOT NULL DEFAULT 'pendiente',
    creado TEXT NOT NULL DEFAULT {ahora}
);
-- Idempotencia de la ejecución (spec ejecucion): una acción por dictamen y tipo.
CREATE TABLE IF NOT EXISTS pedidos (
    id {id},
    caso_id INTEGER NOT NULL REFERENCES casos,
    dictamen_id INTEGER NOT NULL REFERENCES dictamenes,
    tipo TEXT NOT NULL CHECK (tipo IN ('inspeccion', 'trabajo', 'mensaje_vecino')),
    descripcion TEXT NOT NULL,
    creado TEXT NOT NULL DEFAULT {ahora},
    UNIQUE (dictamen_id, tipo)
);
-- Mensajes que salen fuera del turno de conversación (resolución de un caso, aviso de urgencia
-- al administrador, respuesta manual desde el panel). El proceso del bot los envía.
-- destino: 'vecino:<telefono>' o 'admin:<consorcio_id>'. clave: idempotencia.
CREATE TABLE IF NOT EXISTS outbox (
    id {id},
    destino TEXT NOT NULL,
    mensaje_json TEXT NOT NULL,
    clave TEXT UNIQUE,
    enviado TEXT,
    creado TEXT NOT NULL DEFAULT {ahora}
);
-- Reglamento y actas de cada consorcio, cargados desde el panel (spec documentos-consorcio, design D6).
-- contenido_md: el Markdown validado, del que sale el corpus. archivo_path: el original (Storage o disco).
-- estado: activo | reemplazado | baja (lo no activo queda para mostrar citas viejas).
CREATE TABLE IF NOT EXISTS documentos (
    doc_id {id},
    consorcio_id TEXT NOT NULL REFERENCES consorcios,
    tipo TEXT NOT NULL CHECK (tipo IN ('Reglamento', 'Acta')),
    ref TEXT NOT NULL,
    fecha TEXT NOT NULL,
    contenido_md TEXT NOT NULL,
    nombre_archivo TEXT,
    archivo_path TEXT,
    estado TEXT NOT NULL DEFAULT 'activo' CHECK (estado IN ('activo', 'reemplazado', 'baja')),
    indexado INTEGER NOT NULL DEFAULT 0,
    subido_por TEXT,
    creado TEXT NOT NULL DEFAULT {ahora},
    actualizado TEXT NOT NULL DEFAULT {ahora}
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

_DIALECTOS = {
    "sqlite": {"id": "INTEGER PRIMARY KEY", "id_auto": "INTEGER PRIMARY KEY AUTOINCREMENT",
               "ahora": "(datetime('now'))"},
    "postgresql": {"id": "SERIAL PRIMARY KEY", "id_auto": "SERIAL PRIMARY KEY",
                   # `\:` porque text() tomaría `:MI` y `:SS` como parámetros.
                   "ahora": "(to_char(now() AT TIME ZONE 'utc', 'YYYY-MM-DD HH24\\:MI\\:SS'))"},
}

TABLAS = [
    "documentos", "outbox", "pedidos", "decisiones", "dictamenes", "derivaciones", "precedentes", "casos",
    "movimientos_cc", "lineas_liquidacion", "liquidaciones", "facturas",
    "vinculos_canal", "vecinos", "unidades", "consorcios", "administradores", "administraciones",
]

# Columnas agregadas después de que la tabla ya existía en bases creadas antes (tabla → [(columna, tipo)]).
_COLUMNAS_NUEVAS = {
    "consorcios": [("administracion_id", "TEXT REFERENCES administraciones"),
                   ("activo", "INTEGER NOT NULL DEFAULT 1")],
}


def esquema(dialecto: str) -> list[str]:
    """Las sentencias del esquema para un motor ('sqlite' o 'postgresql')."""
    sin_comentarios = re.sub(r"--[^\n]*", "", ESQUEMA.format(**_DIALECTOS[dialecto]))
    return [s.strip() for s in sin_comentarios.split(";") if s.strip()]


class Fila:
    """Una fila como `sqlite3.Row`: `fila["col"]`, `fila[0]`, `dict(fila)` y desempaquetado."""
    __slots__ = ("_claves", "_valores")

    def __init__(self, claves: tuple[str, ...], valores: tuple):
        self._claves, self._valores = claves, valores

    def keys(self) -> list[str]:
        return list(self._claves)

    def __getitem__(self, clave):
        if isinstance(clave, str):
            return self._valores[self._claves.index(clave)]
        return self._valores[clave]

    def __iter__(self):
        return iter(self._valores)

    def __len__(self) -> int:
        return len(self._valores)

    def __eq__(self, otra) -> bool:
        return tuple(self) == tuple(otra)

    def __repr__(self) -> str:
        return f"Fila({dict(zip(self._claves, self._valores))})"


class Cursor:
    """Resultado ya leído de un `execute` (la conexión vuelve al pool enseguida)."""

    def __init__(self, filas: list[Fila], rowcount: int):
        self._filas, self.rowcount = filas, rowcount

    def fetchone(self) -> Fila | None:
        return self._filas.pop(0) if self._filas else None

    def fetchall(self) -> list[Fila]:
        filas, self._filas = self._filas, []
        return filas

    def __iter__(self):
        return iter(self.fetchall())

    @property
    def lastrowid(self):
        raise AttributeError("Usá INSERT ... RETURNING <id>: lastrowid no existe en Postgres")


_PREGUNTA = re.compile(r"\?")


def _a_nombrados(sql: str, params) -> tuple[str, dict]:
    """`?` posicionales → `:p0, :p1…` (SQLAlchemy usa parámetros con nombre en los dos motores)."""
    if params is None:
        return sql, {}
    if isinstance(params, dict):
        return sql, params
    params = list(params)
    contador = iter(range(len(params)))
    return _PREGUNTA.sub(lambda _: f":p{next(contador)}", sql), {f"p{i}": v for i, v in enumerate(params)}


class Conexion:
    """La base del proceso. Cada `execute` toma una conexión del pool y la confirma al terminar
    (autocommit): un pooler de Supabase puede cortar conexiones ociosas, así que no se retiene
    ninguna. `commit()` queda por compatibilidad y no hace nada."""

    def __init__(self, engine: Engine):
        self.engine = engine
        self.dialecto = engine.dialect.name

    def execute(self, sql: str, params=None) -> Cursor:
        sql, nombrados = _a_nombrados(sql, params)
        with self.engine.connect() as c:
            r = c.execute(text(sql), nombrados)
            if r.returns_rows:
                claves = tuple(r.keys())
                return Cursor([Fila(claves, tuple(f)) for f in r.fetchall()], r.rowcount)
            return Cursor([], r.rowcount)

    def commit(self) -> None:
        pass

    def close(self) -> None:
        self.engine.dispose()


def crear_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        engine = create_engine(url, isolation_level="AUTOCOMMIT",
                               connect_args={"check_same_thread": False, "timeout": 30})

        @event.listens_for(engine, "connect")
        def _pragmas(dbapi_conn, _):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys = ON")
            cur.execute("PRAGMA journal_mode = WAL")  # el bot y el panel son procesos distintos
            cur.close()

        return engine
    return create_engine(url, isolation_level="AUTOCOMMIT", pool_pre_ping=True, pool_recycle=300)


def _url(destino: Path | str | None) -> str:
    if destino is None:
        return db_url()
    destino = str(destino)
    if "://" in destino:
        return destino
    return f"sqlite:///{Path(destino).as_posix()}"


def conectar(destino: Path | str | None = None) -> Conexion:
    """Una conexión nueva a la base: una URL, la ruta de un SQLite, o la configurada."""
    Path(_ruta_sqlite(_url(destino)) or ".").parent.mkdir(parents=True, exist_ok=True)
    return Conexion(crear_engine(_url(destino)))


def _ruta_sqlite(url: str) -> str | None:
    return url.removeprefix("sqlite:///") if url.startswith("sqlite:///") else None


_conexiones: dict[str, Conexion] = {}


def get_conn() -> Conexion:
    """Conexión del proceso a la base configurada (los nodos del grafo usan esta)."""
    url = db_url()
    if url not in _conexiones:
        conn = conectar(url)
        crear_esquema(conn)
        _conexiones[url] = conn
    return _conexiones[url]


def crear_esquema(conn: Conexion) -> None:
    for sentencia in esquema(conn.dialecto):
        conn.execute(sentencia)
    migrar(conn)
    activar_rls(conn, TABLAS)


def activar_rls(conn: Conexion, tablas) -> None:
    """Postgres (design D5): RLS activado y sin políticas. La clave pública de Supabase (rol `anon`)
    no puede leer ni escribir ninguna fila; el backend se conecta como dueño de las tablas, que no
    está sujeto a RLS. En SQLite no hace nada."""
    if conn.dialecto != "postgresql":
        return
    for tabla in tablas:
        conn.execute(f"ALTER TABLE IF EXISTS {tabla} ENABLE ROW LEVEL SECURITY")


def columnas(conn: Conexion, tabla: str) -> set[str]:
    if conn.dialecto == "sqlite":
        return {f["name"] for f in conn.execute(f"PRAGMA table_info({tabla})").fetchall()}
    return {f["column_name"] for f in conn.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = ?",
        (tabla,)).fetchall()}


def slug_administracion(nombre: str) -> str:
    """'Administración Méndez' → 'administracion-mendez' (el mismo slug que los criterios del Mediador)."""
    from eliseo.formato import normalizar

    return normalizar(nombre).replace(" ", "-")


def migrar(conn: Conexion) -> None:
    """Lleva una base creada antes de cuentas-administracion al esquema actual: agrega las columnas
    nuevas y crea la administración de cada consorcio a partir de su texto `administracion`."""
    for tabla, nuevas in _COLUMNAS_NUEVAS.items():
        existentes = columnas(conn, tabla)
        for columna, tipo in nuevas:
            if columna not in existentes:
                conn.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {tipo}")
    for f in conn.execute("SELECT consorcio_id, administracion FROM consorcios WHERE administracion_id IS NULL").fetchall():
        aid = slug_administracion(f["administracion"])
        conn.execute("INSERT INTO administraciones (administracion_id, nombre) VALUES (?, ?) "
                     "ON CONFLICT (administracion_id) DO NOTHING", (aid, f["administracion"]))
        conn.execute("UPDATE consorcios SET administracion_id = ? WHERE consorcio_id = ?", (aid, f["consorcio_id"]))


def borrar_todo(conn: Conexion) -> None:
    cascada = " CASCADE" if conn.dialecto == "postgresql" else ""
    for tabla in TABLAS:
        conn.execute(f"DROP TABLE IF EXISTS {tabla}{cascada}")
