"""Configuración del proyecto: el único lugar que lee variables de entorno."""
import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
DATA_DIR = RAIZ / "data"
CONSORCIOS_DIR = DATA_DIR / "consorcios"
PROMPTS_DIR = RAIZ / "prompts"


@lru_cache(maxsize=1)
def _cargar() -> None:
    load_dotenv(RAIZ / ".env")


def env(*nombres: str, default: str | None = None) -> str:
    """Devuelve la primera variable definida de `nombres`; si no hay ninguna, `default` o error."""
    _cargar()
    for nombre in nombres:
        valor = os.environ.get(nombre)
        if valor:
            return valor
    if default is not None:
        return default
    raise KeyError(f"Falta la variable de entorno {' o '.join(nombres)}")


def db_path() -> Path:
    """Base SQLite que simula la plataforma (y guarda los checkpoints de los grafos)."""
    return Path(env("ELISEO_DB_PATH", default=str(DATA_DIR / "eliseo.db")))


def checkpoint_db_path() -> Path:
    """Checkpoints de LangGraph, compartidos por el bot y el panel (design D3)."""
    return Path(env("ELISEO_CHECKPOINT_DB", default=str(DATA_DIR / "grafos.db")))


def ttl_hilo_dias() -> int:
    return int(env("ELISEO_TTL_HILO_DIAS", default="7"))


def version_prompt(nombre: str) -> str:
    """Versión configurada de un master prompt, p. ej. PROMPT_VECINO_VERSION=v1."""
    return env(f"PROMPT_{nombre.upper()}_VERSION", default="v1")
