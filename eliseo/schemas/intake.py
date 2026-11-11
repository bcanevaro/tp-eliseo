"""Salida del Intake + Router (LLM step)."""
from enum import Enum

from pydantic import BaseModel, Field, model_validator

from eliseo.schemas.canal import Adjunto


class Intent(str, Enum):
    REGLAMENTO = "REGLAMENTO"
    GASTOS = "GASTOS"
    RECLAMO = "RECLAMO"
    UNKNOWN = "UNKNOWN"


class CampoReclamo(str, Enum):
    AMBIENTE = "ambiente"
    FOTO = "foto"
    DESDE_CUANDO = "desde_cuando"
    GOTEA = "gotea"


class ReclamoBorrador(BaseModel):
    ambiente: str | None = Field(default=None, description="Dónde está el problema, p. ej. 'baño'")
    descripcion: str = Field(default="", description="El problema en palabras del vecino")
    desde_cuando: str | None = None
    gotea: bool | None = None
    fotos: list[Adjunto] = Field(default_factory=list)

    def faltantes(self) -> list[CampoReclamo]:
        """Campos del checklist que todavía faltan, en el orden en que se piden."""
        faltan = []
        if not self.ambiente:
            faltan.append(CampoReclamo.AMBIENTE)
        if not self.fotos:
            faltan.append(CampoReclamo.FOTO)
        if not self.desde_cuando:
            faltan.append(CampoReclamo.DESDE_CUANDO)
        if self.gotea is None:
            faltan.append(CampoReclamo.GOTEA)
        return faltan

    def completar(self, otro: "ReclamoBorrador") -> "ReclamoBorrador":
        """Combina con lo extraído de un mensaje posterior: lo nuevo no pisa lo ya cargado."""
        return ReclamoBorrador(
            ambiente=self.ambiente or otro.ambiente,
            descripcion=" ".join(x for x in (self.descripcion, otro.descripcion) if x).strip(),
            desde_cuando=self.desde_cuando or otro.desde_cuando,
            gotea=self.gotea if self.gotea is not None else otro.gotea,
            fotos=[*self.fotos, *otro.fotos],
        )


class ResultadoIntake(BaseModel):
    intent: Intent
    multi: list[Intent] = Field(default_factory=list, description="Otros temas del mismo mensaje")
    campos_faltantes: list[CampoReclamo] = Field(default_factory=list)
    urgencia: bool = Field(default=False, description="Riesgo para personas o el edificio")
    pregunta_reescrita: str | None = Field(
        default=None, description="La consulta en lenguaje de reglamento o de liquidación"
    )
    reclamo: ReclamoBorrador | None = None

    @model_validator(mode="after")
    def _coherencia(self) -> "ResultadoIntake":
        # multi no repite el intent principal ni trae duplicados ni UNKNOWN.
        vistos = {self.intent}
        multi = []
        for i in self.multi:
            if i not in vistos and i is not Intent.UNKNOWN:
                multi.append(i)
                vistos.add(i)
        self.multi = multi
        if Intent.RECLAMO in vistos and self.reclamo is None:
            raise ValueError("un intake con RECLAMO tiene que traer el reclamo extraído")
        return self

    def intents(self) -> list[Intent]:
        return [self.intent, *self.multi]
