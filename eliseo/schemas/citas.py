"""Citas y respuestas de los agentes de consulta.

Ids canónicos (los mismos en el corpus, en Pinecone y en la base):
  REG-<n>                    artículo del reglamento
  ACTA-<AAAA-MM-DD>[#<p>]    acta de asamblea, opcionalmente un punto
  LIQ-<AAAA-MM>              liquidación de expensas
  FAC-<n>                    factura
  PREC-<n>                   precedente aprobado
"""
import re
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

TipoDocumento = Literal["Reglamento", "Acta", "Liquidacion", "Factura", "Precedente"]

PATRONES_REF: dict[str, re.Pattern] = {
    "Reglamento": re.compile(r"^REG-\d+$"),
    "Acta": re.compile(r"^ACTA-\d{4}-\d{2}-\d{2}(#\d+)?$"),
    "Liquidacion": re.compile(r"^LIQ-\d{4}-\d{2}$"),
    "Factura": re.compile(r"^FAC-\d+$"),
    "Precedente": re.compile(r"^PREC-\d+$"),
}


def tipo_de_referencia(ref: str) -> TipoDocumento | None:
    """El tipo de documento de un id canónico, o None si no tiene formato válido."""
    for tipo, patron in PATRONES_REF.items():
        if patron.match(ref):
            return tipo  # type: ignore[return-value]
    return None


class Cita(BaseModel):
    documento: TipoDocumento
    referencia: str = Field(description="Id canónico, p. ej. REG-22 o ACTA-2024-11-10#3")
    fragmento: str = Field(description="Texto literal de la fuente")

    @model_validator(mode="after")
    def _formato(self) -> "Cita":
        # Solo el formato: que el id exista en el corpus lo comprueba el verificador.
        if not PATRONES_REF[self.documento].match(self.referencia):
            raise ValueError(f"'{self.referencia}' no es un id válido para {self.documento}")
        return self


class RespuestaDocumental(BaseModel):
    respuesta: str
    citas: list[Cita] = Field(default_factory=list)
    suficiente: bool = Field(description="False si no hay evidencia que responda la pregunta")


class LineaGasto(BaseModel):
    concepto: str
    monto: Decimal = Field(description="Copiado de la base, nunca calculado por el LLM")
    comprobante: str | None = Field(default=None, description="Id FAC-<n>, si está cargado")


class RespuestaGastos(BaseModel):
    respuesta: str
    lineas: list[LineaGasto] = Field(default_factory=list)


class RespuestaVecino(BaseModel):
    """Formato del master prompt 'Respuestas al vecino'."""

    respuesta: str = Field(max_length=600)
    citas: list[Cita] = Field(default_factory=list)
    derivar: bool = False
    motivo_derivacion: str | None = None

    @field_validator("respuesta")
    @classmethod
    def _no_vacia(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("la respuesta no puede estar vacía")
        return v

    @model_validator(mode="after")
    def _fuente_o_derivacion(self) -> "RespuestaVecino":
        if self.derivar and not self.motivo_derivacion:
            raise ValueError("una derivación lleva motivo")
        if not self.derivar and not self.citas:
            raise ValueError("sin citas no hay respuesta: hay que derivar")
        return self
