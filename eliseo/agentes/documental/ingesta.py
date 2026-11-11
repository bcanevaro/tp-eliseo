"""Del corpus de un consorcio a records de Pinecone (spec ingesta-documental, design D2).

Un record por artículo o punto de acta. Id `<consorcio_id>:<ref>`, texto `<título>. <texto>`
(el campo que vectoriza Pinecone) y la metadata de vigencia. Pinecone no acepta metadata
None, así que los campos vacíos se omiten.
"""
import logging
import time

from eliseo.corpus import Corpus, Documento, cargar_corpus
from eliseo.vectores import CAMPO_TEXTO, NS_DOCUMENTOS, get_index

log = logging.getLogger(__name__)
LOTE = 90  # upsert_records acepta hasta 96 records con embedding integrado


def id_record(consorcio_id: str, ref: str) -> str:
    return f"{consorcio_id}:{ref}"


def a_record(doc: Documento) -> dict:
    record = {
        "_id": id_record(doc.consorcio_id, doc.ref),
        CAMPO_TEXTO: f"{doc.titulo}. {doc.texto}",
        "consorcio_id": doc.consorcio_id,
        "doc_tipo": doc.tipo,
        "ref": doc.ref,
        "titulo": doc.titulo,
        "fecha": doc.fecha,
        "vigente": doc.vigente,
        "modifica": doc.modifica,
        "efecto": doc.efecto,
        "modificado_por": doc.modificado_por or None,
        "reemplazado_por": doc.reemplazado_por,
    }
    return {k: v for k, v in record.items() if v is not None}


def records(corpus: Corpus) -> list[dict]:
    return [a_record(doc) for doc in corpus]


def _ids_existentes(index, consorcio_id: str) -> set[str]:
    return {i for lote in index.list(prefix=f"{consorcio_id}:", namespace=NS_DOCUMENTOS) for i in lote}


def ingerir(consorcio_id: str, index=None, espera_max: float = 60) -> dict:
    """Upsert idempotente de todo el corpus del consorcio; borra los records que ya no están
    en el corpus y espera a que el índice muestre exactamente los records esperados."""
    index = index or get_index(crear=True)
    nuevos = records(cargar_corpus(consorcio_id))
    for i in range(0, len(nuevos), LOTE):
        index.upsert_records(NS_DOCUMENTOS, nuevos[i:i + LOTE])

    esperados = {r["_id"] for r in nuevos}
    sobrantes = _ids_existentes(index, consorcio_id) - esperados
    if sobrantes:
        index.delete(ids=list(sobrantes), namespace=NS_DOCUMENTOS)

    limite = time.monotonic() + espera_max
    while (presentes := _ids_existentes(index, consorcio_id)) != esperados:
        if time.monotonic() > limite:
            raise TimeoutError(f"Pinecone muestra {len(presentes)} records de {len(esperados)} esperados")
        time.sleep(2)
    log.info("Ingeridos %d records de %s", len(esperados), consorcio_id)
    return {"consorcio_id": consorcio_id, "records": len(esperados), "borrados": len(sobrantes)}
