"""Carga de los master prompts versionados (design D8)."""
from eliseo.config import PROMPTS_DIR, version_prompt


def cargar(nombre: str, version: str | None = None) -> str:
    """Texto de prompts/<nombre>.<version>.md; la versión por defecto sale de PROMPT_<NOMBRE>_VERSION.

    Los placeholders ({consorcio_nombre}, {criterios_procedimentales}…) se completan con
    str.replace o con un PromptTemplate: el JSON de ejemplo tiene llaves, así que no usar .format().
    """
    return (PROMPTS_DIR / f"{nombre}.{version or version_prompt(nombre)}.md").read_text()
