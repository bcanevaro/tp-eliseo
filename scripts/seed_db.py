"""Carga la demo (data/consorcios/*/plataforma.json y la cuenta de prueba) en la base configurada.

    python scripts/seed_db.py           # no borra nada: agrega solo lo que falte
    python scripts/seed_db.py --reset   # borra TODA la base (y los checkpoints) y la recrea

Con Postgres (Supabase), --reset pide escribir el host de la base para confirmar.
"""
import json
import re
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eliseo.config import CONSORCIOS_DIR, checkpoint_db_path, db_url, env  # noqa: E402
from eliseo.cuentas import crear_administracion, crear_administrador  # noqa: E402
from eliseo.plataforma.db import borrar_todo, conectar, crear_esquema  # noqa: E402

CENTAVO = Decimal("0.01")


def _prorratear(total: Decimal, unidades: list[dict]) -> dict[str, Decimal]:
    """Reparto simple para generar los datos de demo (el motor oficial es de agente-gastos):
    redondeo por unidad y la diferencia de centavos a la última unidad."""
    partes = {u["unidad_id"]: (total * Decimal(u["coeficiente"])).quantize(CENTAVO, ROUND_HALF_UP) for u in unidades}
    ultima = unidades[-1]["unidad_id"]
    partes[ultima] += total - sum(partes.values())
    return partes


def cargar_consorcio(conn, datos: dict) -> None:
    c = datos["consorcio"]
    cid = c["consorcio_id"]
    aid = crear_administracion(c["administracion"], conn)
    conn.execute(
        """INSERT INTO consorcios (consorcio_id, nombre, direccion, administracion, administradora,
                                   telefono_emergencias, administracion_id)
           VALUES (:consorcio_id, :nombre, :direccion, :administracion, :administradora, :telefono_emergencias, :aid)""",
        {**c, "aid": aid})
    for u in datos["unidades"]:
        conn.execute("INSERT INTO unidades VALUES (:unidad_id, :consorcio_id, :unidad, :piso, :depto, :coeficiente)",
                     {**u, "consorcio_id": cid})
    for v in datos["vecinos"]:
        conn.execute("INSERT INTO vecinos VALUES (:telefono, :unidad_id, :nombre)", v)
    for f in datos["facturas"]:
        conn.execute("INSERT INTO facturas VALUES (:fac_id, :consorcio_id, :proveedor, :concepto, :monto, :fecha, :periodo)",
                     {**f, "consorcio_id": cid})

    for liq in datos["liquidaciones"]:
        total = sum(Decimal(l["monto"]) for l in liq["lineas"])
        conn.execute("INSERT INTO liquidaciones VALUES (?, ?, ?, ?, ?, ?)",
                     (liq["liq_id"], cid, liq["periodo"], liq["fecha_emision"], liq["vencimiento"], f"{total:.2f}"))
        for orden, l in enumerate(liq["lineas"], 1):
            conn.execute("INSERT INTO lineas_liquidacion (liq_id, orden, rubro, concepto, monto, comprobante) VALUES (?, ?, ?, ?, ?, ?)",
                         (liq["liq_id"], orden, l["rubro"], l["concepto"], l["monto"], l["comprobante"]))

        impagas = set(datos["pagos"].get(liq["liq_id"], []))
        mes = liq["periodo"][5:] + "/" + liq["periodo"][:4]
        pago = liq["vencimiento"][:8] + "08"
        for unidad_id, parte in _prorratear(total, datos["unidades"]).items():
            conn.execute("INSERT INTO movimientos_cc (unidad_id, fecha, concepto, debe, comprobante) VALUES (?, ?, ?, ?, ?)",
                         (unidad_id, liq["fecha_emision"], f"Expensa {mes}", f"{parte:.2f}", liq["liq_id"]))
            if unidad_id not in impagas:
                conn.execute("INSERT INTO movimientos_cc (unidad_id, fecha, concepto, haber) VALUES (?, ?, ?, ?)",
                             (unidad_id, pago, f"Pago expensa {mes}", f"{parte:.2f}"))

    for p in datos["precedentes"]:
        conn.execute(
            """INSERT INTO precedentes (prec_id, consorcio_id, unidad_id, tipo, ubicacion, descripcion, resolucion,
                                        responsable, fecha, procedencia)
               VALUES (:prec_id, :consorcio_id, :unidad_id, :tipo, :ubicacion, :descripcion, :resolucion,
                       :responsable, :fecha, :procedencia)""",
            {**p, "consorcio_id": cid})


TABLAS_CHECKPOINT = ("checkpoint_writes", "checkpoint_blobs", "checkpoints")

# Cuenta de prueba de la Administración Méndez (spec datos-ficticios). Ficticia: se puede cambiar
# con ELISEO_DEMO_ADMIN_EMAIL y ELISEO_DEMO_ADMIN_PASSWORD. Usa el login local (bcrypt), así la
# demo entra aunque Supabase Auth no esté configurado.
DEMO_ADMINISTRACION = "administracion-mendez"


def cuenta_demo() -> tuple[str, str]:
    return (env("ELISEO_DEMO_ADMIN_EMAIL", default="admin@demo.eliseo.test"),
            env("ELISEO_DEMO_ADMIN_PASSWORD", default="eliseo-demo"))


def cargar_cuenta_demo(conn) -> None:
    email, password = cuenta_demo()
    if conn.execute("SELECT 1 FROM administradores WHERE email = ?", (email,)).fetchone() is None:
        crear_administrador(DEMO_ADMINISTRACION, email, "Laura Méndez", password, conn, con_supabase=False)


def seed(destino: Path | str | None = None, raiz: Path = CONSORCIOS_DIR, reset: bool = False) -> Path | str:
    """Carga la demo en la base. `destino`: la ruta de un SQLite, una URL, o None para la configurada.

    Sin `reset` (spec datos-ficticios, "Siembra no destructiva") no borra nada: crea las tablas que
    falten y carga solo los consorcios y la cuenta de demo que no existan, así lo que se cargó desde
    el panel queda intacto. Con `reset` borra la base entera (y los checkpoints) y la vuelve a cargar."""
    destino = destino or db_url()
    conn = conectar(destino)
    if reset:
        borrar_todo(conn)
    crear_esquema(conn)
    for archivo in sorted(raiz.glob("*/plataforma.json")):
        datos = json.loads(archivo.read_text(encoding="utf-8"))
        if conn.execute("SELECT 1 FROM consorcios WHERE consorcio_id = ?",
                        (datos["consorcio"]["consorcio_id"],)).fetchone() is None:
            cargar_consorcio(conn, datos)
    cargar_cuenta_demo(conn)
    if not reset:
        conn.close()
        return destino
    if conn.dialecto == "postgresql":
        # Los checkpoints viven en la misma base: se vacían (sin borrar las tablas, que el
        # checkpointer ya creó) para que no apunten a casos que ya no existen.
        existentes = {f[0] for f in conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = current_schema()").fetchall()}
        for tabla in TABLAS_CHECKPOINT:
            if tabla in existentes:
                conn.execute(f"DELETE FROM {tabla}")
    else:
        checkpoints = checkpoint_db_path()
        for sufijo in ("", "-wal", "-shm"):
            Path(f"{checkpoints}{sufijo}").unlink(missing_ok=True)
    conn.close()
    return destino


def _mostrar(destino) -> str:
    """La URL sin la contraseña, para imprimirla."""
    return re.sub(r"://([^:/@]+):[^@]+@", r"://\1:***@", str(destino))


def main(argv: list[str] | None = None, entrada=input) -> int:
    import argparse

    p = argparse.ArgumentParser(description="Carga los datos de demo sin borrar nada (o recrea la base con --reset).")
    p.add_argument("--reset", action="store_true", help="Borra TODA la base y la vuelve a cargar con la demo")
    a = p.parse_args(argv)
    destino = db_url()
    if a.reset and destino.startswith("postgresql"):
        host = re.sub(r"^.*@", "", destino).split("/")[0].split(":")[0]
        print(f"Vas a BORRAR todos los datos de {_mostrar(destino)} (casos, vecinos, edificios y cuentas).")
        if entrada(f"Para confirmar, escribí el host ({host}): ").strip() != host:
            print("No se borró nada.")
            return 1
    seed(destino, reset=a.reset)
    print(f"{'Base recreada' if a.reset else 'Demo cargada (sin borrar nada)'} en {_mostrar(destino)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
