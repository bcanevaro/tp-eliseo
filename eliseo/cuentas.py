"""Cuentas de administración y login del panel (spec cuentas-admin, design D4).

Una cuenta pertenece a una sola administración. Se autentica de una de dos formas, según cómo se
dio de alta:
- con Supabase Auth, si tiene `auth_user_id` y el `.env` tiene SUPABASE_URL y SUPABASE_ANON_KEY;
- con un hash bcrypt guardado en la base (tests, demo local y cuentas creadas sin Supabase).

Las administraciones y las cuentas se crean con `scripts/alta_administracion.py`, no desde el panel.
"""
import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import bcrypt

from eliseo.config import env
from eliseo.plataforma.db import Conexion, get_conn, slug_administracion

log = logging.getLogger(__name__)

ERROR_LOGIN = "Email o contraseña incorrectos"


@dataclass(frozen=True)
class Sesion:
    """Quién está usando el panel. Todo filtro por administración sale de acá, nunca de la interfaz."""
    admin_id: int
    administracion_id: str
    administracion: str
    email: str
    nombre: str


def normalizar_email(email: str) -> str:
    return (email or "").strip().lower()


def hashear(password: str) -> str:
    # ELISEO_BCRYPT_ROUNDS solo baja en los tests (cada siembra crea la cuenta de demo).
    rondas = int(env("ELISEO_BCRYPT_ROUNDS", default="12"))
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rondas)).decode("ascii")


def _password_ok(password: str, hash_: str | None) -> bool:
    if not hash_:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hash_.encode("ascii"))
    except ValueError:  # hash corrupto
        return False


def supabase_configurado() -> bool:
    return bool(env("SUPABASE_URL", default="") and env("SUPABASE_ANON_KEY", default=""))


def _cliente_supabase(clave: str = "SUPABASE_ANON_KEY"):
    from supabase import create_client

    return create_client(env("SUPABASE_URL"), env(clave))


def _auth_supabase(email: str, password: str) -> str | None:
    """El id de usuario de Supabase Auth si el email y la contraseña son correctos."""
    try:
        r = _cliente_supabase().auth.sign_in_with_password({"email": email, "password": password})
        return r.user.id if r and r.user else None
    except Exception as e:  # credenciales inválidas o Supabase caído: para el panel es lo mismo
        log.info("login con Supabase rechazado para %s: %s", email, type(e).__name__)
        return None


def _sesion(fila) -> Sesion:
    return Sesion(admin_id=fila["admin_id"], administracion_id=fila["administracion_id"],
                  administracion=fila["administracion"], email=fila["email"], nombre=fila["nombre"])


_SELECT = """SELECT a.admin_id, a.administracion_id, a.email, a.nombre, a.password_hash, a.auth_user_id,
                    ad.nombre AS administracion
             FROM administradores a JOIN administraciones ad USING (administracion_id)"""


def autenticar(email: str, password: str, conn: Conexion | None = None) -> Sesion | None:
    """La sesión si el email y la contraseña son correctos; None si no (sin decir qué falló)."""
    conn = conn or get_conn()
    email = normalizar_email(email)
    if not email or not password:
        return None
    fila = conn.execute(_SELECT + " WHERE a.email = ?", (email,)).fetchone()
    if fila is None:
        _password_ok(password, hashear("x"))  # mismo tiempo de respuesta que con un email existente
        return None
    if fila["auth_user_id"] and supabase_configurado():
        return _sesion(fila) if _auth_supabase(email, password) == fila["auth_user_id"] else None
    return _sesion(fila) if _password_ok(password, fila["password_hash"]) else None


def sesion_de(admin_id: int, conn: Conexion | None = None) -> Sesion | None:
    """Relee la sesión desde la base (si la cuenta se borró, ya no hay sesión)."""
    fila = (conn or get_conn()).execute(_SELECT + " WHERE a.admin_id = ?", (admin_id,)).fetchone()
    return _sesion(fila) if fila else None


# ---------------------------------------------------------------- chat de avisos (spec canal-administracion)

VIGENCIA_CODIGO = timedelta(minutes=15)
_ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sin 0/O ni 1/I, que se confunden al tipear


def _hash_codigo(codigo: str) -> str:
    return hashlib.sha256(codigo.strip().upper().encode("utf-8")).hexdigest()


def _ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


def _texto_fecha(d: datetime) -> str:
    return d.strftime("%Y-%m-%d %H:%M:%S")


def generar_codigo_avisos(sesion: Sesion, conn: Conexion | None = None) -> str:
    """Un código de un solo uso para la administración de la sesión. Se muestra una vez en el panel;
    en la base queda solo su hash."""
    conn = conn or get_conn()
    codigo = "".join(secrets.choice(_ALFABETO) for _ in range(8))
    conn.execute("INSERT INTO codigos_vinculacion (codigo_hash, administracion_id, vence) VALUES (?, ?, ?)",
                 (_hash_codigo(codigo), sesion.administracion_id, _texto_fecha(_ahora_utc() + VIGENCIA_CODIGO)))
    return codigo


def vincular_chat_avisos(codigo: str, chat_id: str, conn: Conexion | None = None) -> str | None:
    """Deja `chat_id` como chat de avisos de la administración del código (reemplaza al anterior).
    Devuelve el nombre de la administración, o None si el código no existe, venció o ya se usó."""
    conn = conn or get_conn()
    fila = conn.execute(
        """UPDATE codigos_vinculacion SET usado = 1
           WHERE codigo_hash = ? AND usado = 0 AND vence > ?
           RETURNING administracion_id""",
        (_hash_codigo(codigo or ""), _texto_fecha(_ahora_utc()))).fetchone()
    if fila is None:
        return None
    conn.execute("UPDATE administraciones SET chat_avisos_id = ? WHERE administracion_id = ?",
                 (str(chat_id), fila["administracion_id"]))
    return conn.execute("SELECT nombre FROM administraciones WHERE administracion_id = ?",
                        (fila["administracion_id"],)).fetchone()["nombre"]


def chat_avisos(administracion_id: str, conn: Conexion | None = None) -> str | None:
    fila = (conn or get_conn()).execute("SELECT chat_avisos_id FROM administraciones WHERE administracion_id = ?",
                                        (administracion_id,)).fetchone()
    return fila["chat_avisos_id"] if fila else None


# ---------------------------------------------------------------- altas (script de operación)

def crear_administracion(nombre: str, conn: Conexion | None = None) -> str:
    """Crea la administración si no existe. Devuelve su id (el slug del nombre)."""
    conn = conn or get_conn()
    nombre = nombre.strip()
    if not nombre:
        raise ValueError("La administración necesita un nombre")
    aid = slug_administracion(nombre)
    conn.execute("INSERT INTO administraciones (administracion_id, nombre) VALUES (?, ?) "
                 "ON CONFLICT (administracion_id) DO NOTHING", (aid, nombre))
    return aid


def crear_administrador(administracion_id: str, email: str, nombre: str, password: str | None = None,
                        conn: Conexion | None = None, con_supabase: bool | None = None) -> int:
    """Da de alta una cuenta en una administración existente.

    Con Supabase (por defecto, si hay SUPABASE_SERVICE_ROLE_KEY): crea el usuario en Supabase Auth,
    con la contraseña si se pasa o mandándole una invitación por mail si no. Sin Supabase: exige
    la contraseña y guarda su hash."""
    conn = conn or get_conn()
    email, nombre = normalizar_email(email), nombre.strip()
    if "@" not in email or not nombre:
        raise ValueError("La cuenta necesita un email válido y un nombre")
    if conn.execute("SELECT 1 FROM administraciones WHERE administracion_id = ?", (administracion_id,)).fetchone() is None:
        raise KeyError(f"No existe la administración {administracion_id}")
    if conn.execute("SELECT 1 FROM administradores WHERE email = ?", (email,)).fetchone():
        raise ValueError(f"Ya existe una cuenta con el email {email}")
    if con_supabase is None:
        con_supabase = bool(env("SUPABASE_URL", default="") and env("SUPABASE_SERVICE_ROLE_KEY", default=""))

    auth_user_id, password_hash = None, None
    if con_supabase:
        admin = _cliente_supabase("SUPABASE_SERVICE_ROLE_KEY").auth.admin
        if password:
            r = admin.create_user({"email": email, "password": password, "email_confirm": True})
        else:
            r = admin.invite_user_by_email(email)
        auth_user_id = r.user.id
    else:
        if not password or len(password) < 8:
            raise ValueError("Sin Supabase, la cuenta necesita una contraseña de al menos 8 caracteres")
        password_hash = hashear(password)
    fila = conn.execute(
        "INSERT INTO administradores (administracion_id, email, nombre, password_hash, auth_user_id) "
        "VALUES (?, ?, ?, ?, ?) RETURNING admin_id",
        (administracion_id, email, nombre, password_hash, auth_user_id)).fetchone()
    return fila["admin_id"]
