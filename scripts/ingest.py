"""Ingesta del reglamento, las actas y los precedentes de un consorcio en Pinecone.

    python scripts/ingest.py R4520

Crea el índice si no existe. Se puede correr varias veces: no duplica records. Los precedentes
salen de SQLite (la fuente de verdad), así que esto también repara un upsert fallido al aprobar.
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eliseo.agentes.documental.ingesta import ingerir  # noqa: E402
from eliseo.agentes.mediador import precedentes  # noqa: E402

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    consorcio = sys.argv[1] if len(sys.argv) > 1 else "R4520"
    print(ingerir(consorcio))
    print(precedentes.ingerir(consorcio))
