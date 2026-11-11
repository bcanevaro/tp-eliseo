"""Estado de los dos grafos (design D2), armado con los contratos compartidos."""
from datetime import datetime
from typing import Annotated, TypedDict

from eliseo.schemas import (
    Caso,
    DecisionAdmin,
    Dictamen,
    Identidad,
    MensajeEntrante,
    MensajeSaliente,
    ReclamoBorrador,
    RespuestaDocumental,
    RespuestaGastos,
    ResultadoIntake,
)

REINICIAR = None  # devolver {"salidas": REINICIAR} vacía la lista al empezar cada turno


def _salidas(previas: list[MensajeSaliente] | None, nuevas: list[MensajeSaliente] | None) -> list[MensajeSaliente]:
    """Acumula los mensajes del turno (las ramas del fan-out suman en paralelo)."""
    if nuevas is None:
        return []
    return [*(previas or []), *nuevas]


class EstadoConversacion(TypedDict, total=False):
    """Un hilo por vecino: thread_id = '<telefono>:<consorcio_id>'."""

    # Del turno actual
    mensaje: MensajeEntrante
    salidas: Annotated[list[MensajeSaliente], _salidas]
    intake: ResultadoIntake | None
    documental: RespuestaDocumental | None
    verificacion_consulta: dict | None
    gastos: RespuestaGastos | None
    casos_lanzados: list[int]  # el runtime arranca su grafo de caso al terminar el turno

    # Persisten entre turnos (hasta el TTL)
    identidad: Identidad | None
    reclamo_en_curso: ReclamoBorrador | None
    no_entendidos_seguidos: int
    ultimo_mensaje: datetime | None


class EstadoGrafoCaso(TypedDict, total=False):
    """Un hilo por reclamo: thread_id = 'caso:<caso_id>'."""

    caso: Caso
    telefono: str
    documental: RespuestaDocumental | None
    precedentes: list[dict]
    dictamen: Dictamen | None
    verificacion: dict | None  # {"ok": bool, "fallas": [{"hipotesis", "cita", "motivo"}]}
    vueltas: int  # rechazos del verificador al Mediador (máximo 2)
    dictamen_id: int | None
    decision: DecisionAdmin | None
