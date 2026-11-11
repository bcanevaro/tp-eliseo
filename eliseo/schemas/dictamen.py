"""Dictamen del Mediador (master prompt v1) y decisión del administrador."""
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from eliseo.schemas.citas import tipo_de_referencia


class Hipotesis(BaseModel):
    id: str = Field(description="A, B, C…")
    responsable: Literal["unidad", "consorcio"]
    descripcion: str
    citas: list[str] = Field(description="Ids canónicos que la sostienen (REG-, ACTA-, PREC-…)")
    a_favor: list[str] = Field(default_factory=list)
    en_contra: list[str] = Field(default_factory=list)
    confirmaria: str = Field(description="Qué dato la confirmaría")

    @field_validator("citas")
    @classmethod
    def _ids_canonicos(cls, citas: list[str]) -> list[str]:
        malas = [c for c in citas if tipo_de_referencia(c) is None]
        if malas:
            raise ValueError(f"ids de cita con formato inválido: {malas}")
        return citas


class Recomendacion(BaseModel):
    tipo: Literal["asignar", "inspeccion"]
    hipotesis: str | None = Field(default=None, description="Id de la hipótesis si tipo=asignar")
    accion: str

    @model_validator(mode="after")
    def _asignar_exige_hipotesis(self) -> "Recomendacion":
        if self.tipo == "asignar" and not self.hipotesis:
            raise ValueError("recomendar 'asignar' exige indicar la hipótesis")
        return self


class Dictamen(BaseModel):
    hechos: list[str]
    afirmaciones_sin_evidencia: list[str] = Field(default_factory=list)
    hipotesis: list[Hipotesis] = Field(default_factory=list, max_length=3)
    recomendacion: Recomendacion
    mensaje_vecino: str

    @model_validator(mode="after")
    def _hipotesis_recomendada_existe(self) -> "Dictamen":
        ids = {h.id for h in self.hipotesis}
        if len(ids) != len(self.hipotesis):
            raise ValueError("ids de hipótesis repetidos")
        if self.recomendacion.hipotesis and self.recomendacion.hipotesis not in ids:
            raise ValueError(f"la recomendación apunta a la hipótesis {self.recomendacion.hipotesis}, que no existe")
        return self

    def todas_las_citas(self) -> set[str]:
        return {c for h in self.hipotesis for c in h.citas}


class AccionAdmin(str, Enum):
    APROBAR = "APROBAR"
    MODIFICAR = "MODIFICAR"
    RECHAZAR = "RECHAZAR"


class DecisionAdmin(BaseModel):
    accion: AccionAdmin
    admin_id: str
    mensaje_final: str | None = Field(
        default=None, description="Texto que recibe el vecino; obligatorio al modificar"
    )
    motivo: str | None = Field(default=None, description="Obligatorio al rechazar")

    @model_validator(mode="after")
    def _campos_por_accion(self) -> "DecisionAdmin":
        if self.accion is AccionAdmin.RECHAZAR and not (self.motivo and self.motivo.strip()):
            raise ValueError("rechazar exige un motivo")
        if self.accion is AccionAdmin.MODIFICAR and not (self.mensaje_final and self.mensaje_final.strip()):
            raise ValueError("modificar exige el mensaje final editado")
        return self
