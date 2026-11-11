"""Retriever híbrido del agente Documental (spec agente-documental, design D3).

    buscar(consorcio_id, consulta, k) -> Resultado

1. dense:  búsqueda en Pinecone (embedding integrado), filtrada por consorcio
2. léxico: BM25 en memoria sobre el corpus del consorcio, con stemming en español
3. fusión: Reciprocal Rank Fusion
4. rerank: bge-reranker-v2-m3 hospedado en Pinecone
5. vigencia: los artículos reemplazados se sustituyen por el acta vigente y a los
   complementados se les suman sus actas (en código, no como filtro de la búsqueda)

Si Pinecone no responde, sigue solo con BM25 (degrada, no se cae). Los tests reemplazan el
dense y el reranker con `configurar(...)`.
"""
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Callable

import snowballstemmer
from rank_bm25 import BM25Okapi

from eliseo.config import env
from eliseo.corpus import Documento, cargar_corpus
from eliseo.formato import normalizar

log = logging.getLogger(__name__)

TOP_CANDIDATOS = 10
RRF_K = 60

# (consorcio_id, consulta, top_k) -> refs ordenados
Dense = Callable[[str, str, int], list[str]]
# (consulta, textos, top_n) -> [(índice, score)] ordenado de mayor a menor
Reranker = Callable[[str, list[str], int], list[tuple[int, float]]]

_STOPWORDS = set("""
a al algo algun alguna algunas alguno algunos ante antes como con contra cual cuales cuando de del desde donde
durante e el ella ellas ellos en entre era es esa esas ese eso esos esta estas este esto estos fue ha hay la las
le les lo los mas me mi mis mucho muy nada ni no nos o otra otro para pero poco por porque que quien se sea ser
si sin sobre su sus tambien te tengo tiene toda todo todos tu tus un una uno unos y ya yo puedo puede poner
quiero saber hacer
""".split())
_stemmer = snowballstemmer.stemmer("spanish")


def tokenizar(texto: str) -> list[str]:
    palabras = [p for p in "".join(c if c.isalnum() else " " for c in normalizar(texto)).split()
                if p not in _STOPWORDS and len(p) > 1]
    return _stemmer.stemWords(palabras)


# ------------------------------------------------------------------ léxico

@dataclass
class _IndiceBM25:
    refs: list[str]
    bm25: BM25Okapi


@lru_cache(maxsize=None)
def _bm25(consorcio_id: str) -> _IndiceBM25:
    docs = list(cargar_corpus(consorcio_id))
    return _IndiceBM25([d.ref for d in docs], BM25Okapi([tokenizar(f"{d.titulo} {d.texto}") for d in docs]))


def buscar_bm25(consorcio_id: str, consulta: str, top_k: int = TOP_CANDIDATOS) -> list[str]:
    indice = _bm25(consorcio_id)
    scores = indice.bm25.get_scores(tokenizar(consulta))
    orden = sorted(range(len(scores)), key=lambda i: -scores[i])
    return [indice.refs[i] for i in orden[:top_k] if scores[i] > 0]


# ------------------------------------------------------------------ Pinecone

def dense_pinecone(consorcio_id: str, consulta: str, top_k: int) -> list[str]:
    from eliseo.vectores import NS_DOCUMENTOS, filtro_consorcio, get_index

    r = get_index().search(namespace=NS_DOCUMENTOS, fields=["ref", "consorcio_id"],
                           query={"inputs": {"text": consulta}, "top_k": top_k, "filter": filtro_consorcio(consorcio_id)})
    # Defensa en profundidad: aunque el filtro falle, nunca se devuelve otro consorcio.
    return [h.fields["ref"] for h in r.result.hits if h.fields.get("consorcio_id") == consorcio_id]


def rerank_pinecone(consulta: str, textos: list[str], top_n: int) -> list[tuple[int, float]]:
    from eliseo.vectores import MODELO_RERANK, get_client

    r = get_client().inference.rerank(model=MODELO_RERANK, query=consulta, documents=textos,
                                      top_n=top_n, return_documents=False)
    return [(d.index, d.score) for d in r.data]


def _por_defecto() -> tuple[Dense | None, Reranker | None]:
    from eliseo.vectores import hay_pinecone

    return (dense_pinecone, rerank_pinecone) if hay_pinecone() else (None, None)


_config: dict = {}


def configurar(dense: Dense | None = None, reranker: Reranker | None = None) -> None:
    """Reemplaza el dense y el reranker (None = no usar). Sin llamar, usa Pinecone si hay API key."""
    _config.update(dense=dense, reranker=reranker)


def _componentes() -> tuple[Dense | None, Reranker | None]:
    if _config:
        return _config["dense"], _config["reranker"]
    return _por_defecto()


# ------------------------------------------------------------------ fusión y vigencia

def rrf(listas: list[list[str]], k: int = RRF_K) -> list[str]:
    puntaje: dict[str, float] = {}
    for lista in listas:
        for pos, ref in enumerate(lista):
            puntaje[ref] = puntaje.get(ref, 0) + 1 / (k + pos + 1)
    return sorted(puntaje, key=lambda r: -puntaje[r])


def resolver_vigencia(consorcio_id: str, refs: list[str]) -> list[Documento]:
    """Reemplazados → el acta vigente; complementados → el artículo y sus actas. Sin repetidos."""
    corpus = cargar_corpus(consorcio_id)
    salida, vistos = [], set()
    for ref in refs:
        doc = corpus.get(ref)
        cadena = [doc.reemplazado_por] if doc.reemplazado_por else [doc.ref, *doc.modificado_por]
        for r in cadena:
            if r not in vistos:
                vistos.add(r)
                salida.append(corpus.get(r))
    return salida


@dataclass
class Resultado:
    documentos: list[Documento]  # con la vigencia ya resuelta
    score: float | None  # score del reranker del mejor candidato (None si no hubo rerank)
    etapas: dict[str, list[str]] = field(default_factory=dict)  # para la evaluación por paso

    @property
    def refs(self) -> list[str]:
        return [d.ref for d in self.documentos]


def buscar(consorcio_id: str, consulta: str, k: int = 3) -> Resultado:
    dense, reranker = _componentes()
    etapas = {"bm25": buscar_bm25(consorcio_id, consulta)}
    if dense:
        try:
            etapas["dense"] = dense(consorcio_id, consulta, TOP_CANDIDATOS)
        except Exception as e:  # Pinecone caído o sin cuota: degradamos a BM25
            log.warning("Búsqueda densa no disponible (%s); sigo solo con BM25", e)
    etapas["rrf"] = rrf([etapas[e] for e in ("dense", "bm25") if e in etapas])
    candidatos = etapas["rrf"][:TOP_CANDIDATOS]

    score = None
    if reranker and candidatos:
        corpus = cargar_corpus(consorcio_id)
        try:
            orden = reranker(consulta, [f"{corpus.get(r).titulo}. {corpus.get(r).texto}" for r in candidatos], k)
            etapas["rerank"] = [candidatos[i] for i, _ in orden]
            score = orden[0][1] if orden else None
        except Exception as e:
            log.warning("Rerank no disponible (%s); uso el orden de RRF", e)
    finales = etapas.get("rerank", candidatos)[:k]
    return Resultado(resolver_vigencia(consorcio_id, finales), score, etapas)


def umbral_suficiente() -> float:
    """Score mínimo del reranker para considerar que hay evidencia (calibrado en la evaluación)."""
    return float(env("DOCUMENTAL_UMBRAL_RERANK", default="0.25"))
