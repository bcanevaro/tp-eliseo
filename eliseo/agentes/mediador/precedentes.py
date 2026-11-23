"""Tool de precedentes: memoria episódica del Mediador (spec precedentes, design D8 y D9).

    get_precedentes(consorcio_id, unidad_id, tipo, descripcion) -> [precedente]

Es código, sin LLM. Con Pinecone: búsqueda semántica en el namespace `precedentes` filtrada por
consorcio y tipo, rerank, umbral, la misma columna primero y hasta 3, hidratados desde SQLite.
Sin API key o si Pinecone falla: SQLite con los mismos filtros, misma columna primero y después
más nuevo. SQLite es la fuente de verdad; Pinecone es una copia que `ingerir` reconstruye.
"""
import logging

from eliseo.agentes.documental.ingesta import sincronizar
from eliseo.agentes.documental.retriever import rerank_pinecone
from eliseo.config import env
from eliseo.formato import normalizar
from eliseo.plataforma import lectura
from eliseo.plataforma.db import get_conn
from eliseo.schemas import Caso
from eliseo.vectores import CAMPO_TEXTO, NS_PRECEDENTES, filtro_consorcio, get_index, hay_pinecone

log = logging.getLogger(__name__)

TOP_CANDIDATOS = 10
MAX_PRECEDENTES = 3
_FILTRACION = ["humedad", "filtra", "gotea", "goteo", "llueve", "mancha", "agua", "perdida"]


def tipo_reclamo(caso: Caso) -> str:
    """Clasificador compartido con `ejecucion`: el tipo con que se guarda y se busca un precedente."""
    texto = normalizar(f"{caso.reclamo.descripcion} {caso.reclamo.ambiente or ''}")
    return "filtracion" if caso.reclamo.gotea or any(p in texto for p in _FILTRACION) else "otro"


def umbral() -> float:
    """Score mínimo del reranker (se calibra en la evaluación de recuperación)."""
    return float(env("PRECEDENTES_UMBRAL_RERANK", default="0.1"))


def _columna(p: dict) -> str | None:
    """La letra de la unidad es la columna (misma convención que el stub y `ejecucion`)."""
    if p.get("unidad_id"):
        return p["unidad_id"][-1].upper()
    ubic = normalizar(p.get("ubicacion") or "")
    return ubic.split("columna ", 1)[1][:1].upper() if "columna " in ubic else None


def _misma_columna_primero(precs: list[dict], unidad_id: str) -> list[dict]:
    columna = unidad_id[-1].upper()
    return sorted(precs, key=lambda p: _columna(p) != columna)  # sorted es estable


def _texto(p: dict) -> str:
    return f"{p['descripcion']} {p['resolucion']}"


# ---------------------------------------------------------------- búsqueda

def _desde_sqlite(conn, consorcio_id: str, unidad_id: str, tipo: str | None) -> list[dict]:
    nuevos_primero = sorted(lectura.precedentes(conn, consorcio_id, tipo), key=lambda p: p["fecha"], reverse=True)
    return _misma_columna_primero(nuevos_primero, unidad_id)[:MAX_PRECEDENTES]


def _desde_pinecone(conn, consorcio_id: str, unidad_id: str, tipo: str | None, descripcion: str) -> list[dict]:
    filtro = filtro_consorcio(consorcio_id, **({"tipo": {"$eq": tipo}} if tipo else {}))
    r = get_index().search(namespace=NS_PRECEDENTES, fields=["prec_id", "consorcio_id"],
                           query={"inputs": {"text": descripcion}, "top_k": TOP_CANDIDATOS, "filter": filtro})
    # Defensa en profundidad: aunque el filtro falle, nunca entra otro consorcio. Se hidrata
    # desde SQLite, así un record que ya no está en la base no se devuelve.
    base = {p["prec_id"]: p for p in lectura.precedentes(conn, consorcio_id, tipo)}
    candidatos = [base[h.fields["prec_id"]] for h in r.result.hits
                  if h.fields.get("consorcio_id") == consorcio_id and h.fields.get("prec_id") in base]
    if not candidatos:
        return []
    orden = rerank_pinecone(descripcion, [_texto(p) for p in candidatos], len(candidatos))
    pasan = [candidatos[i] for i, score in orden if score >= umbral()]
    return _misma_columna_primero(pasan, unidad_id)[:MAX_PRECEDENTES]


def get_precedentes(consorcio_id: str, unidad_id: str, tipo: str | None, descripcion: str) -> list[dict]:
    """Hasta 3 precedentes del consorcio, con la misma forma de dict que la tabla `precedentes`.
    `consorcio_id` y `unidad_id` los fija el código desde el estado del grafo, nunca el LLM."""
    conn = get_conn()
    if hay_pinecone():
        try:
            return _desde_pinecone(conn, consorcio_id, unidad_id, tipo, descripcion)
        except Exception as e:  # Pinecone caído o sin cuota: degradamos a SQLite
            log.warning("Precedentes en Pinecone no disponibles (%s); uso SQLite", e)
    return _desde_sqlite(conn, consorcio_id, unidad_id, tipo)


# ---------------------------------------------------------------- índice (copia de SQLite)

def a_record(p: dict) -> dict:
    """Record de Pinecone. Pinecone no acepta metadata None, así que los campos vacíos se omiten."""
    record = {
        "_id": f"{p['consorcio_id']}:{p['prec_id']}",
        CAMPO_TEXTO: _texto(p),
        "prec_id": p["prec_id"],
        "consorcio_id": p["consorcio_id"],
        "unidad_id": p.get("unidad_id"),
        "tipo": p["tipo"],
        "ubicacion": p.get("ubicacion"),
        "fecha": p["fecha"],
    }
    return {k: v for k, v in record.items() if v is not None}


def ingerir(consorcio_id: str, index=None, conn=None, espera_max: float = 60) -> dict:
    """Reconstruye el namespace `precedentes` del consorcio desde SQLite: idempotente y borra sobrantes."""
    index = index or get_index(crear=True)
    recs = [a_record(p) for p in lectura.precedentes(conn or get_conn(), consorcio_id)]
    return sincronizar(index, NS_PRECEDENTES, consorcio_id, recs, espera_max)


def indexar(conn, consorcio_id: str, prec_id: str) -> bool:
    """Copia a Pinecone un precedente recién aprobado. Nunca bloquea la aprobación: si falla, lo
    loguea y la próxima corrida de `scripts/ingest.py` lo indexa."""
    if not hay_pinecone():
        return False
    try:
        p = next(p for p in lectura.precedentes(conn, consorcio_id) if p["prec_id"] == prec_id)
        get_index().upsert_records(NS_PRECEDENTES, [a_record(p)])
        return True
    except Exception:
        log.exception("No se pudo indexar %s en Pinecone; se repara con scripts/ingest.py", prec_id)
        return False
