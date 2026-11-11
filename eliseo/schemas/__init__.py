"""Contratos compartidos: todo lo que cruza una frontera entre componentes.

Si un componente necesita un campo nuevo, se agrega acá en su change (ver la spec
contratos-compartidos). Ningún componente define su propia versión de estos tipos.
"""
from eliseo.schemas.canal import Adjunto, Identidad, MensajeEntrante, MensajeSaliente
from eliseo.schemas.caso import TRANSICIONES, Caso, EstadoCaso, TransicionInvalida
from eliseo.schemas.citas import (
    PATRONES_REF,
    Cita,
    LineaGasto,
    RespuestaDocumental,
    RespuestaGastos,
    RespuestaVecino,
    TipoDocumento,
    tipo_de_referencia,
)
from eliseo.schemas.dictamen import AccionAdmin, DecisionAdmin, Dictamen, Hipotesis, Recomendacion
from eliseo.schemas.intake import CampoReclamo, Intent, ReclamoBorrador, ResultadoIntake

__all__ = [
    "Adjunto", "Identidad", "MensajeEntrante", "MensajeSaliente",
    "Caso", "EstadoCaso", "TRANSICIONES", "TransicionInvalida",
    "Cita", "LineaGasto", "RespuestaDocumental", "RespuestaGastos", "RespuestaVecino",
    "TipoDocumento", "PATRONES_REF", "tipo_de_referencia",
    "AccionAdmin", "DecisionAdmin", "Dictamen", "Hipotesis", "Recomendacion",
    "CampoReclamo", "Intent", "ReclamoBorrador", "ResultadoIntake",
]
