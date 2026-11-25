"""Consultas de solo lectura a la plataforma simulada.

Mínimo privilegio impuesto por código: las consultas de datos de una unidad reciben la
`Identidad` resuelta por teléfono (no un id que pueda generar el LLM), y las de datos del
consorcio reciben el `consorcio_id` que fija el estado del grafo.
"""
from decimal import Decimal

from eliseo.plataforma.db import Conexion
from eliseo.schemas import Identidad, LineaGasto


def identidad_por_telefono(conn: Conexion, telefono: str) -> Identidad | None:
    fila = conn.execute(
        # Un consorcio dado de baja (activo = 0) deja a sus vecinos sin acceso (spec padron-consorcios).
        """SELECT v.telefono, v.nombre, u.unidad_id, u.unidad, u.consorcio_id
           FROM vecinos v JOIN unidades u USING (unidad_id) JOIN consorcios c ON c.consorcio_id = u.consorcio_id
           WHERE v.telefono = ? AND c.activo = 1""",
        (telefono,),
    ).fetchone()
    return Identidad(**dict(fila)) if fila else None


def telefono_vinculado(conn: Conexion, canal: str, usuario_canal_id: str) -> str | None:
    fila = conn.execute(
        "SELECT telefono FROM vinculos_canal WHERE canal = ? AND usuario_canal_id = ?",
        (canal, usuario_canal_id),
    ).fetchone()
    return fila["telefono"] if fila else None


def chat_de_telefono(conn: Conexion, telefono: str, canal: str = "telegram") -> str | None:
    """Para que la ejecución pueda escribirle al vecino por el canal."""
    fila = conn.execute(
        "SELECT chat_id FROM vinculos_canal WHERE canal = ? AND telefono = ?", (canal, telefono)
    ).fetchone()
    return fila["chat_id"] if fila else None


def consorcio(conn: Conexion, consorcio_id: str) -> dict:
    return dict(conn.execute("SELECT * FROM consorcios WHERE consorcio_id = ?", (consorcio_id,)).fetchone())


def unidades(conn: Conexion, consorcio_id: str) -> list[dict]:
    filas = conn.execute(
        "SELECT * FROM unidades WHERE consorcio_id = ? ORDER BY piso, depto", (consorcio_id,)
    ).fetchall()
    return [dict(f, coeficiente=Decimal(f["coeficiente"])) for f in filas]


def cuenta_corriente(conn: Conexion, identidad: Identidad) -> dict:
    """Movimientos y saldo de la unidad del vecino (y de ninguna otra)."""
    filas = conn.execute(
        "SELECT fecha, concepto, debe, haber, comprobante FROM movimientos_cc WHERE unidad_id = ? ORDER BY fecha, id",
        (identidad.unidad_id,),
    ).fetchall()
    movimientos = [dict(f, debe=Decimal(f["debe"]), haber=Decimal(f["haber"])) for f in filas]
    saldo = sum((m["debe"] - m["haber"] for m in movimientos), Decimal("0.00"))
    return {"unidad": identidad.unidad, "movimientos": movimientos, "saldo_deudor": saldo}


def periodos_liquidados(conn: Conexion, consorcio_id: str) -> list[str]:
    filas = conn.execute(
        "SELECT periodo FROM liquidaciones WHERE consorcio_id = ? ORDER BY periodo", (consorcio_id,)
    ).fetchall()
    return [f["periodo"] for f in filas]


def liquidacion(conn: Conexion, consorcio_id: str, periodo: str) -> dict | None:
    """Liquidación de un período ('AAAA-MM') del consorcio, con sus líneas."""
    cab = conn.execute(
        "SELECT * FROM liquidaciones WHERE consorcio_id = ? AND periodo = ?", (consorcio_id, periodo)
    ).fetchone()
    if not cab:
        return None
    lineas = conn.execute(
        "SELECT concepto, monto, comprobante FROM lineas_liquidacion WHERE liq_id = ? ORDER BY orden",
        (cab["liq_id"],),
    ).fetchall()
    return dict(
        cab,
        total=Decimal(cab["total"]),
        lineas=[LineaGasto(concepto=l["concepto"], monto=Decimal(l["monto"]), comprobante=l["comprobante"])
                for l in lineas],
    )


def factura(conn: Conexion, consorcio_id: str, fac_id: str) -> dict | None:
    fila = conn.execute(
        "SELECT * FROM facturas WHERE consorcio_id = ? AND fac_id = ?", (consorcio_id, fac_id)
    ).fetchone()
    return dict(fila, monto=Decimal(fila["monto"])) if fila else None


def precedentes(conn: Conexion, consorcio_id: str, tipo: str | None = None) -> list[dict]:
    sql, args = "SELECT * FROM precedentes WHERE consorcio_id = ?", [consorcio_id]
    if tipo:
        sql += " AND tipo = ?"
        args.append(tipo)
    return [dict(f) for f in conn.execute(sql + " ORDER BY fecha", args).fetchall()]
