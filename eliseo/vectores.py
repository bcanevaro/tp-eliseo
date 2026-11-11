"""Pinecone: un índice con embedding integrado y namespaces por tipo de contenido.

Design D1 de agente-documental: Pinecone vectoriza el texto del lado del servidor
(`multilingual-e5-large`, 1024 dimensiones), así la ingesta y la búsqueda no dependen de los
embeddings del proxy. Los records llevan el texto en el campo `texto`.

El consorcio no es un namespace sino un filtro de metadata (`consorcio_id`), que las tools
fijan desde el estado del grafo y nunca toman del LLM.
"""
from functools import lru_cache

from pinecone import Pinecone

from eliseo.config import env

NS_DOCUMENTOS = "documentos"
NS_PRECEDENTES = "precedentes"
CAMPO_TEXTO = "texto"
MODELO_EMBEDDING = "multilingual-e5-large"
DIMENSION = 1024
MODELO_RERANK = "bge-reranker-v2-m3"


class IndiceIncompatible(RuntimeError):
    pass


def hay_pinecone() -> bool:
    try:
        env("PINECONE_API_KEY")
        return True
    except KeyError:
        return False


@lru_cache(maxsize=1)
def get_client() -> Pinecone:
    return Pinecone(api_key=env("PINECONE_API_KEY"))


def nombre_indice() -> str:
    return env("PINECONE_INDEX_NAME", default="eliseo")


def get_index(crear: bool = False):
    """El índice configurado. Con crear=True lo crea si no existe; si existe, valida que sea
    un índice con embedding integrado de la dimensión esperada."""
    pc, nombre = get_client(), nombre_indice()
    if not pc.has_index(nombre):
        if not crear:
            raise IndiceIncompatible(f"No existe el índice '{nombre}': corré scripts/ingest.py")
        pc.create_index_for_model(
            name=nombre,
            cloud="aws",
            region=env("PINECONE_REGION", default="us-east-1"),
            embed={"model": MODELO_EMBEDDING, "field_map": {"text": CAMPO_TEXTO}},
        )
    else:
        desc = pc.describe_index(nombre)
        if desc.dimension != DIMENSION or not getattr(desc, "embed", None):
            raise IndiceIncompatible(
                f"El índice '{nombre}' existe pero no es de embedding integrado con {MODELO_EMBEDDING} "
                f"({desc.dimension} dimensiones). Borralo desde la consola de Pinecone o usá otro PINECONE_INDEX_NAME."
            )
    return pc.Index(nombre)


def filtro_consorcio(consorcio_id: str, **extra) -> dict:
    """Filtro de metadata obligatorio en toda consulta."""
    return {"consorcio_id": {"$eq": consorcio_id}, **extra}
