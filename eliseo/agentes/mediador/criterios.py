"""Criterios procedimentales de la administración: memoria editable a mano (design D7).

Un archivo por administración en `data/administraciones/<slug>/criterios.md`, con
`slug = normalizar(administracion).replace(" ", "-")`. Se lee en cada llamada (sin caché).
"""
import logging

from eliseo.config import ADMINISTRACIONES_DIR
from eliseo.formato import normalizar
from eliseo.prompts import escapar

log = logging.getLogger(__name__)

SIN_CRITERIOS = "Esta administración no cargó criterios."


def slug(administracion: str) -> str:
    """'Administración Méndez' → 'administracion-mendez'."""
    return normalizar(administracion).replace(" ", "-")


def cargar_criterios(administracion: str) -> str:
    """Texto de los criterios de la administración, o "" (con un aviso en el log) si no tiene archivo."""
    ruta = ADMINISTRACIONES_DIR / slug(administracion) / "criterios.md"
    if not ruta.is_file():
        log.warning("la administración %r no tiene criterios cargados (%s)", administracion, ruta)
        return ""
    return ruta.read_text(encoding="utf-8").strip()


def bloque_criterios(administracion: str) -> str:
    """Valor para `{criterios_procedimentales}`: los criterios escapados o el aviso de que no hay."""
    return escapar(cargar_criterios(administracion)) or SIN_CRITERIOS
