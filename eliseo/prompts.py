"""Carga de los master prompts versionados (design D8) y escape del texto que se les inyecta."""
from eliseo.config import PROMPTS_DIR, version_prompt


def cargar(nombre: str, version: str | None = None) -> str:
    """Texto de prompts/<nombre>.<version>.md; la versión por defecto sale de PROMPT_<NOMBRE>_VERSION.

    Los placeholders ({consorcio_nombre}, {criterios_procedimentales}…) se completan con
    str.replace o con un PromptTemplate: el JSON de ejemplo tiene llaves, así que no usar .format().
    """
    return (PROMPTS_DIR / f"{nombre}.{version or version_prompt(nombre)}.md").read_text(encoding="utf-8")


def escapar(texto: str) -> str:
    """Neutraliza `<` y `>` (→ `&lt;` y `&gt;`) en un texto que va dentro de una etiqueta del prompt.

    Todo dato inyectado (relato del vecino, fuentes, precedentes, criterios) pasa por acá, así nadie
    puede cerrar la etiqueta que lo contiene (`</relato_vecino>`) ni abrir una falsa (`<criterios>`)
    desde adentro del dato. El texto se conserva legible y no se toca nada más: `&` queda igual, así
    que un `&lt;` que ya venía en el dato tampoco abre ni cierra nada. Se aplica al contenido, nunca
    a las etiquetas que arma el código.
    """
    return texto.replace("<", "&lt;").replace(">", "&gt;")
