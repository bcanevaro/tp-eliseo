"""Alta de una administración y de una cuenta de administrador (spec cuentas-admin, "Alta de cuentas").

    python scripts/alta_administracion.py "Administración Pérez" pedro@ejemplo.com "Pedro Pérez"

Crea la administración si no existe (sin consorcios) y le agrega la cuenta. Con Supabase
configurado (SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY en el .env), la cuenta se crea en Supabase
Auth: con `--password` queda con esa contraseña; sin ella, Supabase le manda un mail de
invitación para que la elija. Sin Supabase, pide la contraseña por consola y guarda su hash.
"""
import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eliseo import cuentas  # noqa: E402
from eliseo.config import env  # noqa: E402
from eliseo.plataforma.db import get_conn  # noqa: E402


def alta(administracion: str, email: str, nombre: str, password: str | None = None,
         con_supabase: bool | None = None) -> tuple[str, int]:
    conn = get_conn()
    aid = cuentas.crear_administracion(administracion, conn)
    admin_id = cuentas.crear_administrador(aid, email, nombre, password, conn, con_supabase=con_supabase)
    return aid, admin_id


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("administracion", help='Nombre de la administración, p. ej. "Administración Pérez"')
    p.add_argument("email", help="Email del administrador (es su usuario)")
    p.add_argument("nombre", help="Nombre y apellido del administrador")
    p.add_argument("--password", help="Contraseña inicial (si no se pasa: invitación por mail o se pide por consola)")
    p.add_argument("--sin-supabase", action="store_true", help="Crear la cuenta con login local aunque haya Supabase")
    a = p.parse_args(argv)

    con_supabase = False if a.sin_supabase else bool(env("SUPABASE_URL", default="")
                                                       and env("SUPABASE_SERVICE_ROLE_KEY", default=""))
    password = a.password
    if not con_supabase and not password:
        password = getpass.getpass("Contraseña (mínimo 8 caracteres): ")
        if password != getpass.getpass("Repetila: "):
            print("Las contraseñas no coinciden.")
            return 1
    try:
        aid, admin_id = alta(a.administracion, a.email, a.nombre, password, con_supabase)
    except (ValueError, KeyError) as e:
        print(f"No se creó la cuenta: {e}")
        return 1
    forma = ("Supabase Auth, " + ("con la contraseña indicada" if password else "con invitación por mail")
             if con_supabase else "login local")
    print(f"Listo: cuenta {cuentas.normalizar_email(a.email)} (id {admin_id}) en la administración {aid}, {forma}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
