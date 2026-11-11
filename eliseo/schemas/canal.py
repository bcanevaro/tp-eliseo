"""Lo que entra por el canal y la identidad del vecino."""
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


class Adjunto(BaseModel):
    tipo: Literal["foto", "audio", "documento"]
    file_id: str = Field(description="Id del archivo en el canal (p. ej. file_id de Telegram)")
    ruta_local: str | None = Field(default=None, description="Dónde quedó guardado, si se descargó")
    mime: str | None = None


class MensajeEntrante(BaseModel):
    canal: Literal["telegram"] = "telegram"
    chat_id: str
    usuario_canal_id: str
    texto: str = ""
    adjuntos: list[Adjunto] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    telefono_compartido: str | None = Field(
        default=None,
        description="Teléfono del contacto que compartió el propio usuario (botón de Telegram)",
    )


class MensajeSaliente(BaseModel):
    """Lo que el sistema le manda a una persona por el canal."""

    texto: str
    botones: list[str] = Field(default_factory=list, description="Respuestas rápidas")
    pedir_contacto: bool = Field(default=False, description="Mostrar el botón de compartir número")
    de_la_administracion: bool = Field(
        default=False, description="True si lo escribió una persona de la administración, no la IA"
    )


class Identidad(BaseModel):
    """Se resuelve por código a partir del teléfono registrado, nunca del texto del vecino."""

    telefono: str
    unidad_id: str = Field(description="Id interno de la unidad, p. ej. 'R4520-4B'")
    unidad: str = Field(description="Cómo la nombra el vecino, p. ej. '4°B'")
    consorcio_id: str
    nombre: str
