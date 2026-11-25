"""Ingesta del reglamento, las actas y los precedentes de un consorcio en Pinecone.

    python scripts/ingest.py R4520

Crea el índice si no existe. Se puede correr varias veces: no duplica records y borra los que ya
no están activos. Los documentos y los precedentes salen de la base (la fuente de verdad), así que
esto también repara una indexación fallida desde el panel; al terminar marca los documentos como
indexados.
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eliseo.agentes.documental.ingesta import ingerir  # noqa: E402
from eliseo.agentes.mediador import precedentes  # noqa: E402
from eliseo.plataforma.db import get_conn  # noqa: E402

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    consorcio = sys.argv[1] if len(sys.argv) > 1 else "R4520"
    print(ingerir(consorcio))
    get_conn().execute("UPDATE documentos SET indexado = 1 WHERE consorcio_id = ? AND estado = 'activo'", (consorcio,))
    print(precedentes.ingerir(consorcio))
