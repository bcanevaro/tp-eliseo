"""Padrón de consorcios, unidades y vecinos desde el panel (spec padron-consorcios, design D11).

Como `servicio.py`, sin Streamlit y con la `Sesion` como primer argumento: todo lo que se lee o
se cambia tiene que ser de un consorcio activo de la administración de la sesión, y lo ajeno se
trata como inexistente (`NoEncontrado`).

Lo que el bot ve de un vecino depende solo del padrón vigente (identidad por teléfono), así que
estos cambios valen desde el próximo mensaje sin reiniciar nada.
"""
import logging
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from eliseo.cuentas import Sesion
from eliseo.panel.servicio import NoEncontrado, _consorcio_de, _conn
from eliseo.plataforma import escritura
from eliseo.plataforma.db import slug_administracion
from eliseo.schemas import Caso, EstadoCaso

log = logging.getLogger(__name__)

TOLERANCIA_COEFICIENTES = Decimal("0.0001")
TELEFONO_REGISTRADO = "Ese teléfono ya está registrado."


class DatoInvalido(ValueError):
    """Un dato del formulario que no se puede guardar; el mensaje es para mostrarle al administrador."""


@dataclass
class UnidadNueva:
    piso: int
    depto: str
    coeficiente: Decimal | str
    unidad_id: str | None = None  # None: unidad nueva


# ---------------------------------------------------------------- teléfonos

def normalizar_telefono_ar(numero: str) -> str:
    """Un celular argentino en formato internacional de WhatsApp/Telegram: '+549' + 10 dígitos.

    '11 5555-1234', '011 5555 1234', '+54 11 5555 1234' y '+54 9 11 5555-1234' → '+5491155551234'.
    """
    d = re.sub(r"\D", "", numero or "")
    if d.startswith("549") and len(d) == 13:
        nacional = d[3:]
    elif d.startswith("54") and len(d) == 12:
        nacional = d[2:]
    elif d.startswith("0") and len(d) == 11:
        nacional = d[1:]
    elif len(d) == 10:
        nacional = d
    else:
        raise DatoInvalido(f"«{numero}» no es un celular argentino válido (código de área y número, 10 dígitos).")
    if nacional.startswith("0"):
        raise DatoInvalido(f"«{numero}» no es un celular argentino válido.")
    return "+549" + nacional


# ---------------------------------------------------------------- consorcios y unidades

def _coeficiente(valor) -> Decimal:
    try:
        c = Decimal(str(valor).replace(",", "."))
    except InvalidOperation:
        raise DatoInvalido(f"«{valor}» no es un coeficiente válido.") from None
    if c <= 0:
        raise DatoInvalido("Los coeficientes tienen que ser mayores que cero.")
    return c


def validar_coeficientes(unidades: list[UnidadNueva]) -> None:
    if not unidades:
        raise DatoInvalido("El edificio necesita al menos una unidad.")
    suma = sum((_coeficiente(u.coeficiente) for u in unidades), Decimal("0"))
    if abs(suma - 1) > TOLERANCIA_COEFICIENTES:
        raise DatoInvalido(f"Los coeficientes suman {suma.normalize():f} y tienen que sumar 1.")
    vistos = set()
    for u in unidades:
        clave = (int(u.piso), u.depto.strip().upper())
        if clave in vistos:
            raise DatoInvalido(f"La unidad {etiqueta_unidad(*clave)} está repetida.")
        vistos.add(clave)


def etiqueta_unidad(piso: int, depto: str) -> str:
    return f"{'PB' if int(piso) == 0 else f'{int(piso)}°'}{depto.strip().upper()}"


def _nuevo_consorcio_id(conn, nombre: str) -> str:
    """'Consorcio Corrientes 1200' → 'CORRIENTES-1200' (con sufijo si ya existe)."""
    base = slug_administracion(re.sub(r"(?i)^\s*consorcio\s+", "", nombre)).upper()[:24] or "CONSORCIO"
    cid, n = base, 2
    while conn.execute("SELECT 1 FROM consorcios WHERE consorcio_id = ?", (cid,)).fetchone():
        cid, n = f"{base}-{n}", n + 1
    return cid


def _texto(valor: str, campo: str) -> str:
    valor = (valor or "").strip()
    if not valor:
        raise DatoInvalido(f"Falta {campo}.")
    return valor


def alta_consorcio(sesion: Sesion, nombre: str, direccion: str, telefono_emergencias: str,
                   unidades: list[UnidadNueva], conn=None) -> str:
    """Crea el consorcio con sus unidades en la administración de la sesión. Devuelve su id."""
    conn = _conn(conn)
    nombre, direccion = _texto(nombre, "el nombre"), _texto(direccion, "la dirección")
    telefono_emergencias = _texto(telefono_emergencias, "el teléfono de emergencias")
    validar_coeficientes(unidades)
    cid = _nuevo_consorcio_id(conn, nombre)
    conn.execute(
        """INSERT INTO consorcios (consorcio_id, nombre, direccion, administracion, administradora,
                                   telefono_emergencias, administracion_id, activo)
           VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
        (cid, nombre, direccion, sesion.administracion, sesion.nombre, telefono_emergencias,
         sesion.administracion_id))
    for u in unidades:
        _insertar_unidad(conn, cid, u)
    return cid


def _insertar_unidad(conn, cid: str, u: UnidadNueva) -> str:
    piso, depto = int(u.piso), u.depto.strip().upper()
    unidad_id = f"{cid}-{'PB' if piso == 0 else piso}{depto}"
    conn.execute("INSERT INTO unidades (unidad_id, consorcio_id, unidad, piso, depto, coeficiente) VALUES (?, ?, ?, ?, ?, ?)",
                 (unidad_id, cid, etiqueta_unidad(piso, depto), piso, depto, f"{_coeficiente(u.coeficiente):.4f}"))
    return unidad_id


def consorcio(sesion: Sesion, consorcio_id: str, conn=None) -> dict:
    conn = _conn(conn)
    _consorcio_de(conn, sesion, consorcio_id)
    return dict(conn.execute("SELECT consorcio_id, nombre, direccion, telefono_emergencias FROM consorcios "
                             "WHERE consorcio_id = ?", (consorcio_id,)).fetchone())


def unidades(sesion: Sesion, consorcio_id: str, conn=None) -> list[dict]:
    conn = _conn(conn)
    _consorcio_de(conn, sesion, consorcio_id)
    filas = conn.execute(
        """SELECT u.unidad_id, u.unidad, u.piso, u.depto, u.coeficiente,
                  (SELECT COUNT(*) FROM vecinos v WHERE v.unidad_id = u.unidad_id) AS vecinos,
                  (SELECT COUNT(*) FROM casos c WHERE c.unidad_id = u.unidad_id) AS casos
           FROM unidades u WHERE u.consorcio_id = ? ORDER BY u.piso, u.depto""", (consorcio_id,)).fetchall()
    return [dict(f, coeficiente=Decimal(f["coeficiente"])) for f in filas]


def editar_consorcio(sesion: Sesion, consorcio_id: str, nombre: str, direccion: str, telefono_emergencias: str,
                     conn=None) -> None:
    conn = _conn(conn)
    _consorcio_de(conn, sesion, consorcio_id)
    conn.execute("UPDATE consorcios SET nombre = ?, direccion = ?, telefono_emergencias = ? WHERE consorcio_id = ?",
                 (_texto(nombre, "el nombre"), _texto(direccion, "la dirección"),
                  _texto(telefono_emergencias, "el teléfono de emergencias"), consorcio_id))


def guardar_unidades(sesion: Sesion, consorcio_id: str, unidades_finales: list[UnidadNueva], conn=None) -> None:
    """Deja el consorcio con exactamente estas unidades: edita las que traen `unidad_id`, crea las
    nuevas y quita las que faltan. No guarda nada si los coeficientes no suman 1 o si se quita una
    unidad con vecinos o casos."""
    conn = _conn(conn)
    _consorcio_de(conn, sesion, consorcio_id)
    validar_coeficientes(unidades_finales)
    actuales = {u["unidad_id"]: u for u in unidades(sesion, consorcio_id, conn)}
    for u in unidades_finales:
        if u.unidad_id and u.unidad_id not in actuales:
            raise NoEncontrado(f"No existe la unidad {u.unidad_id}")
    quitadas = set(actuales) - {u.unidad_id for u in unidades_finales if u.unidad_id}
    for uid in sorted(quitadas):
        a = actuales[uid]
        if a["vecinos"]:
            raise DatoInvalido(f"El {a['unidad']} tiene vecinos registrados: primero hay que darlos de baja.")
        if a["casos"]:
            raise DatoInvalido(f"El {a['unidad']} tiene casos en el historial y no se puede quitar.")
    for uid in quitadas:
        conn.execute("DELETE FROM unidades WHERE unidad_id = ?", (uid,))
    for u in unidades_finales:
        if u.unidad_id:
            conn.execute("UPDATE unidades SET coeficiente = ? WHERE unidad_id = ?",
                         (f"{_coeficiente(u.coeficiente):.4f}", u.unidad_id))
        else:
            _insertar_unidad(conn, consorcio_id, u)


def baja_consorcio(sesion: Sesion, consorcio_id: str, conn=None, index=None) -> None:
    """Baja lógica: el historial queda, sus vecinos dejan de poder usar el bot y sus documentos y
    precedentes salen de la búsqueda (si Pinecone no responde, queda en el log para reintentar)."""
    conn = _conn(conn)
    _consorcio_de(conn, sesion, consorcio_id)
    conn.execute("UPDATE consorcios SET activo = 0 WHERE consorcio_id = ?", (consorcio_id,))
    sacar_de_busqueda(consorcio_id, index)


def sacar_de_busqueda(consorcio_id: str, index=None) -> bool:
    from eliseo.agentes.documental.ingesta import sincronizar
    from eliseo.vectores import NS_DOCUMENTOS, NS_PRECEDENTES, get_index, hay_pinecone

    if index is None:
        if not hay_pinecone():
            return False
        index = get_index()
    try:
        for ns in (NS_DOCUMENTOS, NS_PRECEDENTES):
            sincronizar(index, ns, consorcio_id, [])
        return True
    except Exception:
        log.exception("no se pudieron borrar de Pinecone los records de %s", consorcio_id)
        return False


# ---------------------------------------------------------------- vecinos

def _unidad_de(conn, sesion: Sesion, unidad_id: str) -> dict:
    fila = conn.execute("SELECT unidad_id, consorcio_id, unidad FROM unidades WHERE unidad_id = ?",
                        (unidad_id,)).fetchone()
    try:
        _consorcio_de(conn, sesion, fila["consorcio_id"] if fila else None)
    except NoEncontrado:
        raise NoEncontrado(f"No existe la unidad {unidad_id}") from None
    return dict(fila)


def _vecino_de(conn, sesion: Sesion, telefono: str) -> dict:
    fila = conn.execute("SELECT telefono, unidad_id, nombre FROM vecinos WHERE telefono = ?", (telefono,)).fetchone()
    try:
        _unidad_de(conn, sesion, fila["unidad_id"] if fila else "")
    except NoEncontrado:
        raise NoEncontrado(f"No existe el vecino {telefono}") from None
    return dict(fila)


def _telefono_libre(conn, telefono: str) -> None:
    if conn.execute("SELECT 1 FROM vecinos WHERE telefono = ?", (telefono,)).fetchone():
        raise DatoInvalido(TELEFONO_REGISTRADO)  # sin decir de qué consorcio ni a nombre de quién


def alta_vecino(sesion: Sesion, unidad_id: str, nombre: str, telefono: str, conn=None) -> str:
    """Devuelve el teléfono normalizado con el que quedó registrado."""
    conn = _conn(conn)
    _unidad_de(conn, sesion, unidad_id)
    nombre, telefono = _texto(nombre, "el nombre"), normalizar_telefono_ar(telefono)
    _telefono_libre(conn, telefono)
    conn.execute("INSERT INTO vecinos (telefono, unidad_id, nombre) VALUES (?, ?, ?)", (telefono, unidad_id, nombre))
    return telefono


def editar_vecino(sesion: Sesion, telefono_actual: str, nombre: str, unidad_id: str, telefono: str,
                  conn=None) -> str:
    """Cambia nombre, unidad o teléfono. Si cambia el teléfono, se borra el vínculo de Telegram
    anterior y el vecino tiene que volver a compartir su contacto."""
    conn = _conn(conn)
    _vecino_de(conn, sesion, telefono_actual)
    _unidad_de(conn, sesion, unidad_id)
    nombre, telefono = _texto(nombre, "el nombre"), normalizar_telefono_ar(telefono)
    if telefono != telefono_actual:
        _telefono_libre(conn, telefono)
        _cerrar_reclamo_en_curso(conn, telefono_actual)
        conn.execute("DELETE FROM vinculos_canal WHERE telefono = ?", (telefono_actual,))
    elif conn.execute("SELECT unidad_id FROM vecinos WHERE telefono = ?", (telefono_actual,)).fetchone()[0] != unidad_id:
        _cerrar_reclamo_en_curso(conn, telefono_actual)
    conn.execute("UPDATE vecinos SET telefono = ?, unidad_id = ?, nombre = ? WHERE telefono = ?",
                 (telefono, unidad_id, nombre, telefono_actual))
    return telefono


def baja_vecino(sesion: Sesion, telefono: str, conn=None) -> None:
    """Le corta el acceso al bot desde su próximo mensaje. Sus casos quedan en el historial (los
    casos son de la unidad); un reclamo que tenía a medio cargar queda en el panel como incompleto."""
    conn = _conn(conn)
    _vecino_de(conn, sesion, telefono)
    _cerrar_reclamo_en_curso(conn, telefono)
    conn.execute("DELETE FROM vinculos_canal WHERE telefono = ?", (telefono,))
    conn.execute("DELETE FROM vecinos WHERE telefono = ?", (telefono,))


def _cerrar_reclamo_en_curso(conn, telefono: str) -> None:
    """Si el vecino tenía un reclamo a medio cargar, lo registra como INCOMPLETO y lo saca del hilo."""
    from eliseo.grafo import runtime
    from eliseo.plataforma import lectura

    ident = lectura.identidad_por_telefono(conn, telefono)
    if ident is None:
        return
    conversacion, _ = runtime.grafos()
    config = {"configurable": {"thread_id": f"{ident.telefono}:{ident.consorcio_id}"}}
    try:
        borrador = conversacion.get_state(config).values.get("reclamo_en_curso")
    except Exception:
        log.exception("no se pudo leer el hilo de %s", telefono)
        return
    if borrador and (borrador.descripcion or borrador.ambiente or borrador.fotos):
        escritura.registrar_caso(conn, Caso(consorcio_id=ident.consorcio_id, unidad_id=ident.unidad_id,
                                            reclamo=borrador, estado=EstadoCaso.INCOMPLETO))
        conversacion.update_state(config, {"reclamo_en_curso": None})
