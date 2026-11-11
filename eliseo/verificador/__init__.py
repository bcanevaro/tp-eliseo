"""Verificador de citas determinístico (spec verificador-citas, design D6).

No usa LLM: un critic LLM con los mismos sesgos que el agente no garantiza corrección.

    verificar_citas(consorcio_id, citas, fecha) -> {"ok": bool, "fallas": [...]}
    verificar_dictamen(consorcio_id, dictamen, fecha) -> ídem, con la hipótesis de cada falla

Cada falla es {"cita": ref, "motivo": str, "vigente": ref | None} (más "hipotesis" en los
dictámenes). Es la forma de dict que usa el grafo de caso.
"""
import re
import sqlite3
from datetime import date

from eliseo.corpus import Corpus, cargar_corpus
from eliseo.formato import normalizar
from eliseo.plataforma import lectura
from eliseo.plataforma.db import get_conn
from eliseo.schemas import Cita, Dictamen, tipo_de_referencia

_PUNTUACION = re.compile(r"[^\w\s]")
_ELIPSIS = re.compile(r"\.\.\.|…")


def _limpio(texto: str) -> str:
    """Minúsculas, sin tildes, sin puntuación y con espacios simples."""
    return " ".join(_PUNTUACION.sub(" ", normalizar(texto)).split())


def fragmento_en_texto(fragmento: str, texto: str) -> bool:
    """El fragmento aparece literal (normalizado) en el texto. Si tiene "..." o "…", cada
    tramo tiene que aparecer y en el mismo orden."""
    tramos = [t for t in (_limpio(p) for p in _ELIPSIS.split(fragmento)) if t]
    if not tramos:
        return False
    texto = _limpio(texto)
    pos = 0
    for tramo in tramos:
        encontrado = texto.find(tramo, pos)
        if encontrado < 0:
            return False
        pos = encontrado + len(tramo)
    return True


def _texto_de_base(conn: sqlite3.Connection, consorcio_id: str, ref: str) -> str | None:
    """Texto contra el que se comparan los fragmentos de facturas, liquidaciones y precedentes."""
    tipo = tipo_de_referencia(ref)
    if tipo == "Factura":
        f = lectura.factura(conn, consorcio_id, ref)
        return f and f"{f['proveedor']} {f['concepto']} {f['monto']} {f['fecha']}"
    if tipo == "Liquidacion":
        liq = lectura.liquidacion(conn, consorcio_id, ref.removeprefix("LIQ-"))
        return liq and " ".join(f"{l.concepto} {l.monto} {l.comprobante or ''}" for l in liq["lineas"]) + f" {liq['total']}"
    if tipo == "Precedente":
        p = next((p for p in lectura.precedentes(conn, consorcio_id) if p["prec_id"] == ref), None)
        return p and f"{p['descripcion']} {p['resolucion']}"
    return None


def _verificar_ref(corpus: Corpus | None, conn: sqlite3.Connection, consorcio_id: str, ref: str,
                   fragmento: str | None, fecha: date) -> dict | None:
    """None si la referencia es válida; si no, la falla."""
    tipo = tipo_de_referencia(ref)
    if tipo is None:
        return {"cita": ref, "motivo": "formato de referencia inválido", "vigente": None}

    if tipo in ("Reglamento", "Acta"):
        doc = corpus.get(ref) if corpus else None
        if doc is None:
            return {"cita": ref, "motivo": "referencia inexistente", "vigente": None}
        if doc.reemplazado_por:
            acta = corpus.get(doc.reemplazado_por)
            if date.fromisoformat(acta.fecha) <= fecha:
                return {"cita": ref, "motivo": f"no vigente: reemplazado por {acta.ref}", "vigente": acta.ref}
        texto = doc.texto
    else:
        texto = _texto_de_base(conn, consorcio_id, ref)
        if texto is None:
            return {"cita": ref, "motivo": "referencia inexistente", "vigente": None}

    if fragmento is not None and not fragmento_en_texto(fragmento, texto):
        return {"cita": ref, "motivo": "fragmento no encontrado", "vigente": None}
    return None


def _corpus(consorcio_id: str) -> Corpus | None:
    try:
        return cargar_corpus(consorcio_id)
    except KeyError:  # consorcio sin documentos
        return None


def verificar_citas(consorcio_id: str, citas: list[Cita | str], fecha: date | None = None,
                    conn: sqlite3.Connection | None = None) -> dict:
    """Valida existencia, vigencia a `fecha` (hoy por defecto) y, para las `Cita`, el fragmento.
    Los ids sueltos (str) se validan sin fragmento."""
    corpus, conn, fecha = _corpus(consorcio_id), conn or get_conn(), fecha or date.today()
    fallas = []
    for c in citas:
        ref, fragmento = (c, None) if isinstance(c, str) else (c.referencia, c.fragmento)
        falla = _verificar_ref(corpus, conn, consorcio_id, ref, fragmento, fecha)
        if falla:
            fallas.append(falla)
    return {"ok": not fallas, "fallas": fallas}


def verificar_dictamen(consorcio_id: str, dictamen: Dictamen, fecha: date | None = None,
                       conn: sqlite3.Connection | None = None) -> dict:
    """Valida los ids citados en cada hipótesis; cada falla dice a qué hipótesis pertenece."""
    fallas = []
    for h in dictamen.hipotesis:
        for f in verificar_citas(consorcio_id, h.citas, fecha, conn)["fallas"]:
            fallas.append({**f, "hipotesis": h.id})
    return {"ok": not fallas, "fallas": fallas}
