"""Pinecone: un índice con namespaces por tipo de contenido (design D5).

El consorcio no es un namespace sino un filtro de metadata (`consorcio_id`), que las tools
fijan desde el estado del grafo y nunca toman del LLM.
"""
from functools import lru_cache

from pinecone import Pinecone, ServerlessSpec

from eliseo.config import env

NS_DOCUMENTOS = "documentos"
NS_PRECEDENTES = "precedentes"
DIMENSION = 1536  # text-embedding-3-small


@lru_cache(maxsize=1)
def get_client() -> Pinecone:
    return Pinecone(api_key=env("PINECONE_API_KEY"))


def get_index(crear: bool = False):
    """Devuelve el índice configurado; con crear=True lo crea si no existe."""
    pc = get_client()
    nombre = env("PINECONE_INDEX_NAME", default="eliseo")
    if crear and not pc.has_index(nombre):
        pc.create_index(
            name=nombre,
            dimension=DIMENSION,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region=env("PINECONE_REGION", default="us-east-1")),
        )
    return pc.Index(nombre)


def filtro_consorcio(consorcio_id: str, **extra) -> dict:
    """Filtro de metadata obligatorio en toda consulta."""
    return {"consorcio_id": {"$eq": consorcio_id}, **extra}
