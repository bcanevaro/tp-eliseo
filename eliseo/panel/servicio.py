"""Lógica del panel del administrador, sin Streamlit (spec panel-admin).

La interfaz (`app.py`) solo dibuja lo que devuelve este módulo, así que todo lo que importa
(qué ve el administrador, qué se manda y a quién) se testea acá.

El panel es el único approval boundary: es el único lugar del sistema que retoma un caso
con una `DecisionAdmin`.

Aislamiento por administración (spec cuentas-admin, design D5): toda función recibe la `Sesion`
y filtra por su administración dentro de la consulta. Un caso, una derivación o un consorcio de
otra administración se trata como inexistente (`NoEncontrado`), sin distinguir "no existe" de
"no es tuyo".
"""
import json
from dataclasses import dataclass, field

from eliseo import documentos
from eliseo.corpus import cargar_corpus
from eliseo.cuentas import Sesion
from eliseo.ejecucion import con_numero_de_caso, mensaje_aprobado, tipo_pedido
from eliseo.grafo import runtime
from eliseo.plataforma import escritura, lectura
from eliseo.plataforma.db import Conexion, get_conn
from eliseo.schemas import AccionAdmin, Caso, DecisionAdmin, Dictamen, EstadoCaso, MensajeSaliente, tipo_de_referencia

# Orden de la bandeja: las urgencias siempre primero.
GRUPOS = [
    ("urgencias", "🚨 Urgencias"),
    ("pendientes", "📝 Dictámenes pendientes de aprobación"),
    ("sin_fuente", "❓ Consultas sin fuente"),
    ("hablar", "🙋 Piden hablar con una persona"),
    ("incompletos", "⏳ Reclamos incompletos"),
]
_TIPOS_HABLAR = ("hablar_con_admin", "no_entendido")
_NOMBRE_PEDIDO = {"inspeccion": "inspección", "trabajo": "trabajo"}


@dataclass
class Item:
    tipo: str  # "caso" o "derivacion"
    id: int
    titulo: str
    detalle: str
    creado: str


@dataclass
class DetalleCaso:
    caso: Caso
    vecino: dict
    dictamen: Dictamen | None
    dictamen_id: int | None
    version: int | None
    verificacion: dict | None
    fuentes: dict[str, str]  # ref → texto de la fuente, para mostrar al lado de cada cita
    decisiones: list[dict] = field(default_factory=list)
    pedidos: list[dict] = field(default_factory=list)
    precedente: dict | None = None
    esperando_decision: bool = False


@dataclass
class VistaPrevia:
    """Lo que la confirmación muestra antes de ejecutar: exactamente qué sale y a quién."""
    destinatario: str
    canal_vinculado: bool
    mensaje: str | None
    pedido: str | None
    de_la_administracion: bool


class NoEncontrado(KeyError):
    """No existe, o es de otra administración (para el panel es lo mismo)."""


def _conn(conn: Conexion | None) -> Conexion:
    return conn or get_conn()


def consorcios(sesion: Sesion, conn=None) -> list[dict]:
    """Los consorcios activos de la administración de la sesión."""
    return [dict(f) for f in _conn(conn).execute(
        "SELECT consorcio_id, nombre FROM consorcios WHERE administracion_id = ? AND activo = 1 ORDER BY nombre",
        (sesion.administracion_id,))]


def _consorcio_de(conn, sesion: Sesion, consorcio_id: str | None) -> str:
    """El mismo consorcio_id si es de la sesión y está activo; si no, NoEncontrado."""
    ok = consorcio_id and conn.execute(
        "SELECT 1 FROM consorcios WHERE consorcio_id = ? AND administracion_id = ? AND activo = 1",
        (consorcio_id, sesion.administracion_id)).fetchone()
    if not ok:
        raise NoEncontrado(f"No existe el consorcio {consorcio_id}")
    return consorcio_id


def _caso_de(conn, sesion: Sesion, caso_id: int) -> Caso:
    caso = escritura.obtener_caso(conn, caso_id)
    if caso is None:
        raise NoEncontrado(f"No existe el caso {caso_id}")
    try:
        _consorcio_de(conn, sesion, caso.consorcio_id)
    except NoEncontrado:
        raise NoEncontrado(f"No existe el caso {caso_id}") from None
    return caso


def _derivacion_de(conn, sesion: Sesion, derivacion_id: int):
    d = conn.execute("SELECT * FROM derivaciones WHERE id = ?", (derivacion_id,)).fetchone()
    try:
        _consorcio_de(conn, sesion, d["consorcio_id"] if d else None)
    except NoEncontrado:
        raise NoEncontrado(f"No existe la derivación {derivacion_id}") from None
    return d


def vecinos(sesion: Sesion, consorcio_id: str, conn=None) -> list[dict]:
    """Vecinos de un consorcio de la sesión (para el simulador y el padrón)."""
    conn = _conn(conn)
    _consorcio_de(conn, sesion, consorcio_id)
    return [dict(f) for f in conn.execute(
        """SELECT v.telefono, v.nombre, u.unidad, u.unidad_id FROM vecinos v JOIN unidades u USING (unidad_id)
           WHERE u.consorcio_id = ? ORDER BY u.piso, u.depto""", (consorcio_id,))]


def _vecino(conn, unidad_id: str | None, telefono: str | None = None) -> dict:
    sql = """SELECT v.nombre, v.telefono, u.unidad FROM vecinos v JOIN unidades u USING (unidad_id)
             WHERE {} LIMIT 1"""
    fila = (conn.execute(sql.format("v.telefono = ?"), (telefono,)).fetchone() if telefono else None) or \
           (conn.execute(sql.format("v.unidad_id = ?"), (unidad_id,)).fetchone() if unidad_id else None)
    return dict(fila) if fila else {"nombre": "?", "telefono": telefono, "unidad": unidad_id or "?"}


def bandeja(sesion: Sesion, consorcio_id: str, conn=None) -> dict[str, list[Item]]:
    conn = _conn(conn)
    _consorcio_de(conn, sesion, consorcio_id)
    grupos: dict[str, list[Item]] = {g: [] for g, _ in GRUPOS}

    derivaciones = conn.execute(
        "SELECT * FROM derivaciones WHERE consorcio_id = ? AND estado = 'pendiente' ORDER BY creado DESC, id DESC",
        (consorcio_id,)).fetchall()
    for d in derivaciones:
        grupo = {"urgencia": "urgencias", "sin_fuente": "sin_fuente"}.get(
            d["tipo"], "hablar" if d["tipo"] in _TIPOS_HABLAR else None)
        if grupo:
            v = _vecino(conn, d["unidad_id"], d["telefono"])
            grupos[grupo].append(Item("derivacion", d["id"], f"{v['unidad']} · {v['nombre']}", d["texto"], d["creado"]))

    casos = conn.execute(
        "SELECT * FROM casos WHERE consorcio_id = ? AND estado IN (?, ?) ORDER BY actualizado DESC",
        (consorcio_id, EstadoCaso.PENDIENTE_APROBACION.value, EstadoCaso.INCOMPLETO.value)).fetchall()
    for c in casos:
        caso = escritura.obtener_caso(conn, c["caso_id"])
        v = _vecino(conn, caso.unidad_id)
        grupo = "pendientes" if caso.estado is EstadoCaso.PENDIENTE_APROBACION else "incompletos"
        grupos[grupo].append(Item("caso", caso.caso_id, f"Caso #{caso.caso_id} · {v['unidad']} · {v['nombre']}",
                                  caso.reclamo.descripcion, c["actualizado"]))
    return grupos


def historial(sesion: Sesion, consorcio_id: str, conn=None, limite: int = 20) -> list[dict]:
    """Casos ya decididos o en análisis, para consulta."""
    conn = _conn(conn)
    _consorcio_de(conn, sesion, consorcio_id)
    filas = conn.execute(
        """SELECT caso_id, unidad_id, estado, actualizado FROM casos
           WHERE consorcio_id = ? AND estado NOT IN (?, ?) ORDER BY actualizado DESC LIMIT ?""",
        (consorcio_id, EstadoCaso.PENDIENTE_APROBACION.value, EstadoCaso.INCOMPLETO.value, limite)).fetchall()
    return [dict(f) for f in filas]


def _texto_fuente(conn, consorcio_id: str, ref: str) -> str:
    tipo = tipo_de_referencia(ref)
    if tipo in ("Reglamento", "Acta"):
        # Si ya no está vigente (acta dada de baja, reglamento reemplazado), el texto que se citó.
        doc = cargar_corpus(consorcio_id).get(ref) or documentos.texto_historico(conn, consorcio_id, ref)
        return f"{doc.titulo}. {doc.texto}" if doc else "(no existe en el corpus)"
    if tipo == "Precedente":
        p = next((p for p in lectura.precedentes(conn, consorcio_id) if p["prec_id"] == ref), None)
        return f"{p['descripcion']} Resolución: {p['resolucion']} ({p['fecha']})" if p else "(no existe)"
    if tipo == "Factura":
        f = lectura.factura(conn, consorcio_id, ref)
        return f"{f['proveedor']} · {f['concepto']} · $ {f['monto']} · {f['fecha']}" if f else "(no existe)"
    return ""


def detalle_caso(sesion: Sesion, caso_id: int, conn=None) -> DetalleCaso:
    conn = _conn(conn)
    caso = _caso_de(conn, sesion, caso_id)
    fila = conn.execute(
        "SELECT * FROM dictamenes WHERE caso_id = ? ORDER BY version DESC LIMIT 1", (caso_id,)).fetchone()
    dictamen = Dictamen.model_validate_json(fila["dictamen_json"]) if fila else None
    verificacion = json.loads(fila["verificacion_json"]) if fila and fila["verificacion_json"] else None
    fuentes = {ref: _texto_fuente(conn, caso.consorcio_id, ref)
               for ref in sorted(dictamen.todas_las_citas())} if dictamen else {}
    decisiones = [dict(d) for d in conn.execute(
        "SELECT accion, admin_id, mensaje_final, motivo, creado FROM decisiones WHERE caso_id = ? ORDER BY id",
        (caso_id,))]
    pedidos = [dict(p) for p in conn.execute(
        "SELECT tipo, descripcion, creado FROM pedidos WHERE caso_id = ? ORDER BY id", (caso_id,))]
    prec = conn.execute("SELECT prec_id, resolucion FROM precedentes WHERE caso_id = ?", (caso_id,)).fetchone()
    try:
        esperando = "panel" in runtime.estado_caso(caso_id)["siguiente"]
    except Exception:  # sin checkpoint (p. ej. base recién sembrada)
        esperando = False
    return DetalleCaso(
        caso=caso, vecino=_vecino(conn, caso.unidad_id), dictamen=dictamen,
        dictamen_id=fila["dictamen_id"] if fila else None, version=fila["version"] if fila else None,
        verificacion=verificacion, fuentes=fuentes, decisiones=decisiones, pedidos=pedidos,
        precedente=dict(prec) if prec else None, esperando_decision=esperando)


def armar_decision(accion: AccionAdmin | str, sesion: Sesion, mensaje_final: str | None = None,
                   motivo: str | None = None) -> DecisionAdmin:
    """Valida con el contrato: rechazar exige motivo y modificar exige el mensaje editado.
    El autor es la cuenta de la sesión (spec cuentas-admin, "Decisión firmada por la cuenta")."""
    accion = AccionAdmin(accion)
    return DecisionAdmin(
        accion=accion, admin_id=sesion.email,
        mensaje_final=(mensaje_final or None) if accion is not AccionAdmin.APROBAR else None,
        motivo=(motivo or None) if accion is AccionAdmin.RECHAZAR else None,
    )


def vista_previa(detalle: DetalleCaso, decision: DecisionAdmin, conn=None) -> VistaPrevia:
    conn = _conn(conn)
    v = detalle.vecino
    destinatario = f"{v['nombre']} ({v['unidad']}) por Telegram"
    vinculado = bool(v.get("telefono") and lectura.chat_de_telefono(conn, v["telefono"]))
    if decision.accion is AccionAdmin.RECHAZAR:
        texto = con_numero_de_caso(decision.mensaje_final, detalle.caso.caso_id) if decision.mensaje_final else None
        return VistaPrevia(destinatario, vinculado, texto, None, True)
    d = detalle.dictamen
    return VistaPrevia(destinatario, vinculado, mensaje_aprobado(detalle.caso, d, decision.mensaje_final),
                       f"{_NOMBRE_PEDIDO[tipo_pedido(d)]}: {d.recomendacion.accion}", False)


def decidir(sesion: Sesion, caso_id: int, decision: DecisionAdmin) -> Caso:
    """Retoma el grafo del caso. Un segundo intento (doble click) falla sin ejecutar nada.
    El autor queda siempre como la cuenta de la sesión, aunque la decisión diga otro."""
    _caso_de(get_conn(), sesion, caso_id)
    decision = decision.model_copy(update={"admin_id": sesion.email})
    final = runtime.retomar_caso(caso_id, decision)
    return final["caso"]


def responder_derivacion(sesion: Sesion, derivacion_id: int, texto: str, conn=None) -> bool:
    """Respuesta manual al vecino por el mismo canal, marcada como de la administración."""
    conn = _conn(conn)
    if not texto.strip():
        raise ValueError("La respuesta no puede estar vacía")
    d = _derivacion_de(conn, sesion, derivacion_id)
    if not d["telefono"]:
        raise NoEncontrado(f"La derivación {derivacion_id} no tiene teléfono")
    encolado = escritura.encolar_mensaje(conn, f"vecino:{d['telefono']}",
                                         MensajeSaliente(texto=texto.strip(), de_la_administracion=True),
                                         clave=f"derivacion:{derivacion_id}:respuesta")
    escritura.resolver_derivacion(conn, derivacion_id, f"respondida por {sesion.email}")
    return encolado


def descartar_derivacion(sesion: Sesion, derivacion_id: int, conn=None) -> None:
    conn = _conn(conn)
    _derivacion_de(conn, sesion, derivacion_id)
    escritura.resolver_derivacion(conn, derivacion_id, f"descartada por {sesion.email}")


def derivacion(sesion: Sesion, derivacion_id: int, conn=None) -> dict:
    conn = _conn(conn)
    d = dict(_derivacion_de(conn, sesion, derivacion_id))
    d["vecino"] = _vecino(conn, d["unidad_id"], d["telefono"])
    d["detalle"] = json.loads(d["detalle_json"]) if d.get("detalle_json") else None
    return d
