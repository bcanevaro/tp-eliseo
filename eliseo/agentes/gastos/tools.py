"""Tools de solo lectura del agente Gastos (spec agente-gastos).

Mínimo privilegio impuesto por código: las tools se construyen con la `Identidad` del estado
(resuelta por teléfono) y ninguna recibe una unidad ni un consorcio como argumento. Aunque el
LLM pida "la cuenta del 3°A", no hay forma de que una tool la devuelva.

Cada tool anota en el `Registro` los montos y comprobantes que devolvió: la validación de
salida exige que todo monto de la respuesta esté ahí (los montos se copian, no se calculan).
"""
from dataclasses import dataclass, field
from decimal import Decimal

from langchain_core.tools import StructuredTool

from eliseo import motor
from eliseo.formato import nombre_periodo, pesos
from eliseo.plataforma import lectura
from eliseo.plataforma.db import get_conn
from eliseo.schemas import Identidad

MAX_LLAMADAS = 6


@dataclass
class Registro:
    """Lo que las tools le mostraron al agente en esta consulta."""
    montos: set[Decimal] = field(default_factory=set)
    comprobantes: set[str] = field(default_factory=set)
    llamadas: int = 0

    def anotar(self, *montos: Decimal, comprobante: str | None = None) -> None:
        self.montos |= {Decimal(m) for m in montos}
        if comprobante:
            self.comprobantes.add(comprobante)


def _linea(concepto: str, monto: Decimal, comprobante: str | None) -> str:
    return f"- {concepto}: {pesos(monto)} " + (f"(comprobante {comprobante})" if comprobante else "(sin comprobante cargado)")


def liquidacion_texto(ident: Identidad, periodo: str, registro: Registro, conn=None) -> str:
    conn = conn or get_conn()
    liq = lectura.liquidacion(conn, ident.consorcio_id, periodo)
    if liq is None:
        disponibles = ", ".join(lectura.periodos_liquidados(conn, ident.consorcio_id))
        return f"No hay liquidación de {periodo}. Períodos liquidados: {disponibles}."
    registro.anotar(liq["total"])
    for l in liq["lineas"]:
        registro.anotar(l.monto, comprobante=l.comprobante)
    lineas = "\n".join(_linea(l.concepto, l.monto, l.comprobante) for l in liq["lineas"])
    return (f'<liquidacion ref="LIQ-{periodo}" periodo="{nombre_periodo(periodo)}" vencimiento="{liq["vencimiento"]}">\n'
            f"{lineas}\nTotal del consorcio: {pesos(liq['total'])}\n</liquidacion>")


def comparacion(ident: Identidad, periodo: str, registro: Registro, conn=None) -> dict | None:
    """Diferencia con el período anterior, calculada por código, y la parte de la unidad."""
    conn = conn or get_conn()
    periodos = lectura.periodos_liquidados(conn, ident.consorcio_id)
    if periodo not in periodos or periodos.index(periodo) == 0:
        return None
    anterior = periodos[periodos.index(periodo) - 1]
    actual, previa = (lectura.liquidacion(conn, ident.consorcio_id, p) for p in (periodo, anterior))
    ya = {(l.concepto, l.monto) for l in previa["lineas"]}
    nuevas = [l for l in actual["lineas"] if (l.concepto, l.monto) not in ya]
    diferencia = actual["total"] - previa["total"]
    coefs = {u["unidad_id"]: u["coeficiente"] for u in lectura.unidades(conn, ident.consorcio_id)}
    parte = motor.prorratear(diferencia, coefs)[ident.unidad_id] if diferencia >= 0 else None
    registro.anotar(actual["total"], previa["total"], diferencia, *( [parte] if parte is not None else []))
    for l in nuevas:
        registro.anotar(l.monto, comprobante=l.comprobante)
    return {"periodo": periodo, "anterior": anterior, "total": actual["total"], "total_anterior": previa["total"],
            "diferencia": diferencia, "nuevas": nuevas, "parte_unidad": parte, "coeficiente": coefs[ident.unidad_id]}


def crear_tools(ident: Identidad, registro: Registro) -> list[StructuredTool]:
    conn = get_conn()

    def _limite() -> str | None:
        registro.llamadas += 1
        return "Límite de consultas alcanzado. Respondé con lo que ya tenés." if registro.llamadas > MAX_LLAMADAS else None

    def get_periodos() -> str:
        """Lista los períodos liquidados del consorcio (AAAA-MM), del más viejo al más nuevo."""
        if aviso := _limite():
            return aviso
        return ", ".join(lectura.periodos_liquidados(conn, ident.consorcio_id))

    def get_liquidacion(periodo: str) -> str:
        """Devuelve la liquidación de expensas del consorcio de un período 'AAAA-MM', línea por línea con su comprobante."""
        return _limite() or liquidacion_texto(ident, periodo, registro, conn)

    def comparar_con_anterior(periodo: str) -> str:
        """Explica la diferencia de la liquidación 'AAAA-MM' con el período anterior: los gastos nuevos o distintos,
        la diferencia total y cuánto le toca a la unidad del vecino. Los cálculos los hace el sistema."""
        if aviso := _limite():
            return aviso
        c = comparacion(ident, periodo, registro, conn)
        if c is None:
            return f"No hay un período anterior a {periodo} para comparar."
        lineas = "\n".join(_linea(l.concepto, l.monto, l.comprobante) for l in c["nuevas"])
        parte = (f"\nParte de la unidad {ident.unidad} (coeficiente {c['coeficiente']}): {pesos(c['parte_unidad'])}"
                 if c["parte_unidad"] is not None else "")
        return (f'<comparacion periodo="{nombre_periodo(c["periodo"])}" anterior="{nombre_periodo(c["anterior"])}">\n'
                f"Total {nombre_periodo(c['periodo'])}: {pesos(c['total'])}\nTotal {nombre_periodo(c['anterior'])}: "
                f"{pesos(c['total_anterior'])}\nDiferencia: {pesos(c['diferencia'])}\nGastos nuevos o distintos:\n{lineas}"
                f"{parte}\n</comparacion>")

    def get_factura(fac_id: str) -> str:
        """Devuelve una factura del consorcio por su id (FAC-<n>): proveedor, concepto, monto y fecha."""
        if aviso := _limite():
            return aviso
        f = lectura.factura(conn, ident.consorcio_id, fac_id)
        if f is None:
            return f"No existe la factura {fac_id} en este consorcio."
        registro.anotar(f["monto"], comprobante=f["fac_id"])
        return (f'<factura ref="{f["fac_id"]}">{f["proveedor"]} · {f["concepto"]} · {pesos(f["monto"])} · '
                f'{f["fecha"]}</factura>')

    def get_cuenta_corriente() -> str:
        """Devuelve los movimientos y el saldo de la cuenta corriente de la unidad del vecino que pregunta (solo la suya)."""
        if aviso := _limite():
            return aviso
        cc = lectura.cuenta_corriente(conn, ident)
        registro.anotar(cc["saldo_deudor"])
        movs = []
        for m in cc["movimientos"]:
            registro.anotar(m["debe"], m["haber"], comprobante=m["comprobante"])
            importe = f"debe {pesos(m['debe'])}" if m["debe"] else f"pagó {pesos(m['haber'])}"
            movs.append(f"- {m['fecha']} · {m['concepto']} · {importe}")
        return (f'<cuenta_corriente unidad="{ident.unidad}">\n' + "\n".join(movs)
                + f"\nSaldo deudor: {pesos(cc['saldo_deudor'])}\n</cuenta_corriente>")

    return [StructuredTool.from_function(f) for f in
            (get_periodos, get_liquidacion, comparar_con_anterior, get_factura, get_cuenta_corriente)]
