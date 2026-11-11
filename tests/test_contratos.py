"""Un test por scenario de la spec contratos-compartidos."""
import pytest
from pydantic import ValidationError

from eliseo.schemas import (
    AccionAdmin,
    Caso,
    Cita,
    DecisionAdmin,
    Dictamen,
    EstadoCaso,
    Intent,
    ReclamoBorrador,
    Recomendacion,
    RespuestaVecino,
    ResultadoIntake,
    TransicionInvalida,
    tipo_de_referencia,
)


# Requirement: Resultado del intake — Scenario: Mensaje con dos temas
def test_intake_multi_intent():
    r = ResultadoIntake(
        intent=Intent.RECLAMO,
        multi=[Intent.GASTOS],
        reclamo=ReclamoBorrador(ambiente="baño", descripcion="se me llueve el baño"),
    )
    assert r.intents() == [Intent.RECLAMO, Intent.GASTOS]


def test_intake_multi_sin_duplicados_ni_unknown():
    r = ResultadoIntake(
        intent=Intent.GASTOS, multi=[Intent.GASTOS, Intent.UNKNOWN, Intent.REGLAMENTO]
    )
    assert r.multi == [Intent.REGLAMENTO]


def test_intake_reclamo_exige_borrador():
    with pytest.raises(ValidationError):
        ResultadoIntake(intent=Intent.RECLAMO)


def test_borrador_faltantes_y_completar():
    b = ReclamoBorrador(descripcion="hay humedad")
    assert [c.value for c in b.faltantes()] == ["ambiente", "foto", "desde_cuando", "gotea"]
    b = b.completar(ReclamoBorrador(ambiente="baño", gotea=True))
    assert [c.value for c in b.faltantes()] == ["foto", "desde_cuando"]
    assert b.ambiente == "baño" and b.descripcion == "hay humedad"


# Requirement: Cita verificable — Scenario: Cita con referencia inexistente
def test_cita_inexistente_se_construye():
    c = Cita(documento="Reglamento", referencia="REG-99", fragmento="texto")
    assert c.referencia == "REG-99"  # que exista lo decide el verificador, no el modelo


@pytest.mark.parametrize(
    "ref,tipo",
    [("REG-22", "Reglamento"), ("ACTA-2024-11-10#3", "Acta"), ("ACTA-2025-03-14", "Acta"),
     ("LIQ-2026-10", "Liquidacion"), ("FAC-0042", "Factura"), ("PREC-2201", "Precedente"),
     ("#2201", None), ("Art. 22", None)],
)
def test_ids_canonicos(ref, tipo):
    assert tipo_de_referencia(ref) == tipo


def test_cita_con_formato_de_otro_tipo_falla():
    with pytest.raises(ValidationError):
        Cita(documento="Acta", referencia="REG-22", fragmento="x")


# Requirement: Respuestas de los agentes de consulta — Scenario: Respuesta demasiado larga
def test_respuesta_vecino_demasiado_larga():
    cita = Cita(documento="Reglamento", referencia="REG-1", fragmento="x")
    with pytest.raises(ValidationError):
        RespuestaVecino(respuesta="a" * 800, citas=[cita])


def test_respuesta_sin_citas_tiene_que_derivar():
    with pytest.raises(ValidationError):
        RespuestaVecino(respuesta="Sí, podés.")
    ok = RespuestaVecino(respuesta="Le paso tu consulta a la administración.", derivar=True,
                         motivo_derivacion="sin fuentes")
    assert ok.derivar


# Requirement: Caso y estados — Scenario: Transición inválida
def test_transicion_invalida():
    caso = Caso(consorcio_id="R4520", unidad_id="R4520-4B", reclamo=ReclamoBorrador(),
                estado=EstadoCaso.REGISTRADO)
    with pytest.raises(TransicionInvalida):
        caso.transicionar(EstadoCaso.APROBADO)
    assert caso.estado is EstadoCaso.REGISTRADO


def test_recorrido_valido_hasta_cerrado():
    caso = Caso(consorcio_id="R4520", unidad_id="R4520-4B", reclamo=ReclamoBorrador())
    for e in [EstadoCaso.REGISTRADO, EstadoCaso.EN_ANALISIS, EstadoCaso.PENDIENTE_APROBACION,
              EstadoCaso.APROBADO, EstadoCaso.CERRADO]:
        caso = caso.transicionar(e)
    assert caso.estado is EstadoCaso.CERRADO


# Requirement: Dictamen y decisión — Scenario: Recomendación de asignar sin hipótesis
def test_asignar_sin_hipotesis_falla():
    with pytest.raises(ValidationError):
        Recomendacion(tipo="asignar", hipotesis=None, accion="asignar")


def test_dictamen_recomienda_hipotesis_inexistente():
    with pytest.raises(ValidationError):
        Dictamen(
            hechos=["mancha"],
            hipotesis=[],
            recomendacion=Recomendacion(tipo="asignar", hipotesis="A", accion="x"),
            mensaje_vecino="x",
        )


def test_hipotesis_con_cita_mal_formada_falla():
    with pytest.raises(ValidationError):
        Dictamen.model_validate({
            "hechos": [], "mensaje_vecino": "x",
            "recomendacion": {"tipo": "inspeccion", "accion": "x"},
            "hipotesis": [{"id": "A", "responsable": "consorcio", "descripcion": "x",
                           "citas": ["#2201"], "confirmaria": "x"}],
        })


# Scenario: Rechazo sin motivo
def test_rechazo_sin_motivo_falla():
    with pytest.raises(ValidationError):
        DecisionAdmin(accion=AccionAdmin.RECHAZAR, admin_id="laura")
    assert DecisionAdmin(accion=AccionAdmin.RECHAZAR, admin_id="laura", motivo="hipótesis floja")


def test_modificar_exige_mensaje():
    with pytest.raises(ValidationError):
        DecisionAdmin(accion=AccionAdmin.MODIFICAR, admin_id="laura")
