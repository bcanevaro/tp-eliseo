"""El reclamo registrado y su máquina de estados."""
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from eliseo.schemas.intake import ReclamoBorrador


class EstadoCaso(str, Enum):
    INCOMPLETO = "INCOMPLETO"
    REGISTRADO = "REGISTRADO"
    EN_ANALISIS = "EN_ANALISIS"
    PENDIENTE_APROBACION = "PENDIENTE_APROBACION"
    APROBADO = "APROBADO"
    RECHAZADO = "RECHAZADO"
    CERRADO = "CERRADO"


# Única fuente de verdad de las transiciones válidas.
TRANSICIONES: dict[EstadoCaso, set[EstadoCaso]] = {
    EstadoCaso.INCOMPLETO: {EstadoCaso.REGISTRADO, EstadoCaso.CERRADO},
    EstadoCaso.REGISTRADO: {EstadoCaso.EN_ANALISIS},
    EstadoCaso.EN_ANALISIS: {EstadoCaso.PENDIENTE_APROBACION},
    EstadoCaso.PENDIENTE_APROBACION: {EstadoCaso.APROBADO, EstadoCaso.RECHAZADO},
    # Un rechazo puede reclasificarse y volver a analizarse, o cerrarse con la decisión manual.
    EstadoCaso.RECHAZADO: {EstadoCaso.EN_ANALISIS, EstadoCaso.CERRADO},
    EstadoCaso.APROBADO: {EstadoCaso.CERRADO},
    EstadoCaso.CERRADO: set(),
}


class TransicionInvalida(ValueError):
    pass


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


class Caso(BaseModel):
    caso_id: int | None = Field(default=None, description="Lo asigna la base al registrar")
    consorcio_id: str
    unidad_id: str
    reclamo: ReclamoBorrador
    estado: EstadoCaso = EstadoCaso.INCOMPLETO
    creado: datetime = Field(default_factory=_ahora)
    actualizado: datetime = Field(default_factory=_ahora)

    def transicionar(self, nuevo: EstadoCaso) -> "Caso":
        """Devuelve el caso en el nuevo estado; lanza TransicionInvalida si no está permitido."""
        if nuevo not in TRANSICIONES[self.estado]:
            raise TransicionInvalida(f"{self.estado.value} → {nuevo.value} no es una transición válida")
        return self.model_copy(update={"estado": nuevo, "actualizado": _ahora()})
