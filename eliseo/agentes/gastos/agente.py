"""El agente Gastos (con LLM) y su modo sin LLM.

- `correr_agente`: loop con las tools de solo lectura y salida estructurada `RespuestaGastos`.
  Después se valida que cada monto y comprobante de la respuesta lo haya devuelto una tool; si
  no, se descarta (`MontoNoRespaldado`) y se usa el modo sin LLM.
- `respuesta_codigo`: sin LLM. Resuelve los casos frecuentes (suba de la expensa, un gasto
  puntual, la cuenta corriente) con las mismas funciones que las tools.
"""
import logging
import re
from decimal import Decimal

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from eliseo.agentes.gastos.tools import Registro, comparacion, crear_tools
from eliseo.formato import MESES, nombre_periodo, normalizar, pesos
from eliseo.plataforma import lectura
from eliseo.plataforma.db import get_conn
from eliseo.prompts import cargar
from eliseo.schemas import Identidad, LineaGasto, RespuestaGastos

log = logging.getLogger(__name__)

MAX_ITERACIONES = 5
PEDIR_FINAL = "Devolvé ahora la respuesta final. Copiá los montos y comprobantes tal cual los devolvieron las tools."
_MONTO = re.compile(r"\$\s?(\d{1,3}(?:\.\d{3})*,\d{2})")
_FACTURA = re.compile(r"\bFAC-\d+\b")
_UNIDAD = re.compile(r"\b(\d{1,2})(?:\s*[°º]\s*)?([a-hA-H])\b")
_TODAS = ["todas las unidades", "todos los departamentos", "otras unidades", "los demas vecinos", "cada unidad"]

# Palabras del vecino → texto del concepto en la liquidación.
CONCEPTOS = {
    "luz": "electricidad", "electricidad": "electricidad", "ascensor": "ascensor", "botonera": "botonera",
    "plomer": "montante", "montante": "montante", "cano": "montante", "perdida": "montante",
    "limpieza": "limpieza", "encargado": "encargado", "portero": "encargado", "sueldo": "encargado",
    "honorario": "honorarios", "administracion": "honorarios", "fondo de reserva": "fondo de reserva",
}


class MontoNoRespaldado(ValueError):
    pass


# ---------------------------------------------------------------- validación de salida

def a_decimal(texto: str) -> Decimal:
    """'615.000,00' → Decimal('615000.00')."""
    return Decimal(texto.replace(".", "").replace(",", "."))


def validar(respuesta: RespuestaGastos, registro: Registro) -> list[str]:
    """Todo monto y comprobante de la respuesta tiene que haberlo devuelto una tool."""
    errores = []
    montos = [a_decimal(m) for m in _MONTO.findall(respuesta.respuesta)] + [l.monto for l in respuesta.lineas]
    errores += [f"monto sin respaldo: {pesos(m)}" for m in montos if m not in registro.montos]
    comprobantes = set(_FACTURA.findall(respuesta.respuesta)) | {l.comprobante for l in respuesta.lineas if l.comprobante}
    errores += [f"comprobante sin respaldo: {c}" for c in sorted(comprobantes - registro.comprobantes)]
    return errores


# ---------------------------------------------------------------- con LLM

def correr_agente(ident: Identidad, pregunta: str, modelo) -> RespuestaGastos:
    registro = Registro()
    tools = crear_tools(ident, registro)
    por_nombre = {t.name: t for t in tools}
    conn = get_conn()
    periodos = lectura.periodos_liquidados(conn, ident.consorcio_id)
    sistema = (cargar("gastos").replace("{consorcio_nombre}", lectura.consorcio(conn, ident.consorcio_id)["nombre"])
               .replace("{unidad}", ident.unidad).replace("{ultimo_periodo}", periodos[-1] if periodos else "—"))
    mensajes = [SystemMessage(sistema), HumanMessage(f"<pregunta_vecino>{pregunta}</pregunta_vecino>")]
    con_tools = modelo.bind_tools(tools)
    for _ in range(MAX_ITERACIONES):
        ai = con_tools.invoke(mensajes)
        mensajes.append(ai)
        if not ai.tool_calls:
            break
        for llamada in ai.tool_calls:
            tool = por_nombre.get(llamada["name"])
            salida = tool.invoke(llamada["args"]) if tool else f"No existe la tool {llamada['name']}."
            mensajes.append(ToolMessage(content=str(salida), tool_call_id=llamada["id"]))
    respuesta = modelo.with_structured_output(RespuestaGastos).invoke([*mensajes, HumanMessage(PEDIR_FINAL)])
    if errores := validar(respuesta, registro):
        raise MontoNoRespaldado("; ".join(errores))
    log.info("Gastos: %d llamadas a tools", registro.llamadas)
    return respuesta


# ---------------------------------------------------------------- sin LLM

def otra_unidad(ident: Identidad, texto: str) -> str | None:
    """La unidad ajena que menciona el vecino ('3°A', '3A'), o 'todas' si pide las de todos."""
    t = normalizar(texto)
    if any(p in t for p in _TODAS):
        return "todas"
    propias = normalizar(ident.unidad).replace("°", "")
    for piso, depto in _UNIDAD.findall(texto):
        if f"{piso}{depto.lower()}" != propias.lower():
            return f"{piso}°{depto.upper()}"
    return None


def solo_su_cuenta(ident: Identidad, otra: str) -> RespuestaGastos:
    que = "de otras unidades" if otra == "todas" else f"del {otra}"
    return RespuestaGastos(respuesta=(
        f"No puedo mostrarte datos {que}: solo puedo compartir la cuenta de tu unidad ({ident.unidad}) y los "
        "gastos generales del consorcio. Si querés, te muestro tu saldo."))


def periodo_mencionado(ident: Identidad, texto: str) -> str | None:
    t = normalizar(texto)
    periodos = lectura.periodos_liquidados(get_conn(), ident.consorcio_id)
    for i, mes in enumerate(MESES, 1):
        if re.search(rf"\b{mes}\b", t):
            candidatos = [p for p in periodos if int(p[5:]) == i]
            return candidatos[-1] if candidatos else f"sin-liquidar-{i:02d}"
    return None


def respuesta_codigo(ident: Identidad, texto: str) -> RespuestaGastos:
    conn, t = get_conn(), normalizar(texto)
    if otra := otra_unidad(ident, texto):
        return solo_su_cuenta(ident, otra)

    if any(p in t for p in ["debo", "deuda", "saldo", "mi cuenta", "cuenta corriente", "adeudo", "estoy al dia"]):
        cc = lectura.cuenta_corriente(conn, ident)
        ultimo = cc["movimientos"][-1]
        estado = "estás al día" if cc["saldo_deudor"] <= 0 else f"tenés un saldo deudor de {pesos(cc['saldo_deudor'])}"
        return RespuestaGastos(
            respuesta=f"En la cuenta de tu unidad ({ident.unidad}) {estado}. Último movimiento:",
            lineas=[LineaGasto(concepto=f"{ultimo['concepto']} ({ultimo['fecha']})",
                               monto=ultimo["debe"] or ultimo["haber"], comprobante=None)])

    periodos = lectura.periodos_liquidados(conn, ident.consorcio_id)
    periodo = periodo_mencionado(ident, texto)
    if periodo and periodo.startswith("sin-liquidar"):
        return RespuestaGastos(respuesta=f"Ese mes todavía no está liquidado. El último liquidado es "
                                         f"{nombre_periodo(periodos[-1])}.")
    elegido = periodo or periodos[-1]
    aviso = "" if periodo else f" (te muestro {nombre_periodo(elegido)}, el último liquidado; si querés otro mes, decime cuál)"

    concepto = next((c for clave, c in CONCEPTOS.items() if clave in t), None)
    if concepto:
        liq = lectura.liquidacion(conn, ident.consorcio_id, elegido)
        lineas = [l for l in liq["lineas"] if concepto in normalizar(l.concepto)]
        if lineas:
            return RespuestaGastos(respuesta=f"En la liquidación de {nombre_periodo(elegido)}{aviso}:", lineas=lineas)

    c = comparacion(ident, elegido, Registro())
    if c is None:
        liq = lectura.liquidacion(conn, ident.consorcio_id, elegido)
        return RespuestaGastos(respuesta=f"La expensa de {nombre_periodo(elegido)} fue {pesos(liq['total'])}{aviso}.",
                               lineas=liq["lineas"])
    if c["diferencia"] <= 0:
        return RespuestaGastos(respuesta=(f"La expensa de {nombre_periodo(elegido)} fue {pesos(c['total'])}, "
                                          f"sin suba respecto de {nombre_periodo(c['anterior'])}{aviso}."))
    parte = f" A tu unidad le tocan {pesos(c['parte_unidad'])} de esa diferencia." if c["parte_unidad"] else ""
    return RespuestaGastos(
        respuesta=(f"La expensa de {nombre_periodo(elegido)} fue {pesos(c['total'])}, {pesos(c['diferencia'])} más que "
                   f"{nombre_periodo(c['anterior'])}{aviso}.{parte} Los gastos que explican la suba:"),
        lineas=c["nuevas"])
