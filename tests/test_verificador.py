"""Un test por scenario de la spec verificador-citas."""
from datetime import date

import pytest

from eliseo.schemas import Cita, Dictamen, Hipotesis, Recomendacion
from eliseo.verificador import fragmento_en_texto, verificar_citas, verificar_dictamen

CID = "R4520"


def _cita(ref, fragmento, doc="Reglamento"):
    return Cita(documento=doc, referencia=ref, fragmento=fragmento)


# Scenario: Cita válida
def test_cita_valida(conn):
    r = verificar_citas(CID, [_cita("REG-15", "Las cañerías de uso exclusivo de cada unidad, desde su ingreso a ella, son a cargo de su propietario")], conn=conn)
    assert r == {"ok": True, "fallas": []}


def test_normaliza_mayusculas_tildes_y_puntuacion(conn):
    r = verificar_citas(CID, [_cita("REG-15", "LAS CANERIAS de uso exclusivo de cada unidad desde su ingreso a ella")], conn=conn)
    assert r["ok"]


# Scenario: Fragmento inventado
def test_fragmento_inventado(conn):
    r = verificar_citas(CID, [_cita("REG-15", "Las cañerías son siempre a cargo del consorcio")], conn=conn)
    assert r["fallas"] == [{"cita": "REG-15", "motivo": "fragmento no encontrado", "vigente": None}]


# Scenario: Fragmento recortado
def test_fragmento_recortado_con_puntos_suspensivos(conn):
    ok = verificar_citas(CID, [_cita("REG-22", "Ningún propietario podrá modificar la fachada...")], conn=conn)
    en_orden = verificar_citas(CID, [_cita("REG-22", "Ningún propietario… sin aprobación de la asamblea")], conn=conn)
    desordenado = verificar_citas(CID, [_cita("REG-22", "sin aprobación de la asamblea... Ningún propietario")], conn=conn)
    assert ok["ok"] and en_orden["ok"] and not desordenado["ok"]


def test_fragmento_vacio_no_vale():
    assert not fragmento_en_texto("...", "cualquier texto")


# Scenario: Artículo derogado
def test_articulo_derogado_sugiere_el_acta(conn):
    r = verificar_citas(CID, [_cita("REG-14", "Las obras y reparaciones en las unidades")], conn=conn)
    (falla,) = r["fallas"]
    assert falla["motivo"].startswith("no vigente") and falla["vigente"] == "ACTA-2025-08-20#3"


def test_vigencia_a_la_fecha_del_caso(conn):
    # Antes del acta del 20/08/2025, el REG-14 estaba vigente.
    r = verificar_citas(CID, [_cita("REG-14", "Las obras y reparaciones en las unidades")], fecha=date(2025, 1, 10), conn=conn)
    assert r["ok"]


def test_referencia_inexistente(conn):
    (falla,) = verificar_citas(CID, [_cita("REG-99", "x")], conn=conn)["fallas"]
    assert falla["motivo"] == "referencia inexistente"


@pytest.mark.parametrize("cita", [
    Cita(documento="Factura", referencia="FAC-0107", fragmento="Plomería Hnos. Ruiz"),
    Cita(documento="Liquidacion", referencia="LIQ-2026-10", fragmento="Reemplazo de la botonera del ascensor"),
    Cita(documento="Precedente", referencia="PREC-2201", fragmento="originada en la montante de agua de la columna B"),
    Cita(documento="Acta", referencia="ACTA-2025-03-14", fragmento="reemplazo parcial de la montante de agua"),
])
def test_referencias_de_la_base_y_actas_completas(conn, cita):
    assert verificar_citas(CID, [cita], conn=conn)["ok"]


def test_factura_de_otro_consorcio_no_existe(conn):
    assert not verificar_citas("OTRO", [Cita(documento="Factura", referencia="FAC-0107", fragmento="x")], conn=conn)["ok"]


# Requirement: Abstención — Scenario: Una de dos citas inválida
def test_una_de_dos_citas_invalida(conn):
    r = verificar_citas(CID, [_cita("REG-18", "Se permite la tenencia de animales domésticos"),
                              _cita("REG-18", "Se prohíben los perros")], conn=conn)
    assert not r["ok"] and len(r["fallas"]) == 1


# Requirement: Uso en el loop del Mediador — Scenario: Dictamen con una hipótesis sin respaldo
def test_dictamen_con_hipotesis_sin_respaldo(conn):
    d = Dictamen(
        hechos=["mancha"], mensaje_vecino="x",
        recomendacion=Recomendacion(tipo="inspeccion", accion="x"),
        hipotesis=[Hipotesis(id="A", responsable="unidad", descripcion="x", citas=["REG-99"], confirmaria="x"),
                   Hipotesis(id="B", responsable="consorcio", descripcion="x", citas=["REG-16", "PREC-2201"], confirmaria="x")],
    )
    r = verificar_dictamen(CID, d, conn=conn)
    assert r["fallas"] == [{"cita": "REG-99", "motivo": "referencia inexistente", "vigente": None, "hipotesis": "A"}]
