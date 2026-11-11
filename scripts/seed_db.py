"""Crea desde cero la base de la plataforma simulada a partir de data/consorcios/*/plataforma.json.

Es idempotente: borra las tablas y las vuelve a cargar. También borra los checkpoints de los
grafos, porque quedarían apuntando a casos que ya no existen.

    python scripts/seed_db.py
"""
import json
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eliseo.config import CONSORCIOS_DIR, checkpoint_db_path, db_path  # noqa: E402
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
    conn.execute("INSERT INTO consorcios VALUES (:consorcio_id, :nombre, :direccion, :administracion, :administradora, :telefono_emergencias)", c)
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


def seed(path: Path | None = None, raiz: Path = CONSORCIOS_DIR) -> Path:
    path = Path(path or db_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = conectar(path)
    borrar_todo(conn)
    crear_esquema(conn)
    for archivo in sorted(raiz.glob("*/plataforma.json")):
        cargar_consorcio(conn, json.loads(archivo.read_text()))
    conn.commit()
    conn.close()
    checkpoints = checkpoint_db_path()
    for sufijo in ("", "-wal", "-shm"):
        Path(f"{checkpoints}{sufijo}").unlink(missing_ok=True)
    return path


if __name__ == "__main__":
    print(f"Base creada en {seed()}")
