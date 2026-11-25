"""Tests de la spec datos-ficticios."""
import json
import re
from decimal import Decimal

from eliseo.config import CONSORCIOS_DIR
from eliseo.corpus import cargar_corpus
from eliseo.plataforma import lectura
from eliseo.plataforma.db import TABLAS, conectar

CID = "R4520"


# Cambian en cada siembra sin cambiar el estado: la sal de bcrypt y la hora de creación.
_VOLATILES = {"password_hash", "creado"}


def _volcado(path):
    c = conectar(path)
    datos = {}
    for t in TABLAS:
        filas = c.execute(f"SELECT * FROM {t} ORDER BY 1").fetchall()
        datos[t] = [tuple(v for k, v in zip(f.keys(), f) if k not in _VOLATILES) for f in filas]
    c.close()
    return datos


# Requirement: Consorcio de demo — Scenario: Revisión de datos personales
def test_telefonos_en_rango_ficticio():
    datos = json.loads((CONSORCIOS_DIR / "rivadavia-4520" / "plataforma.json").read_text(encoding="utf-8"))
    telefonos = [v["telefono"] for v in datos["vecinos"]] + datos["telefonos_no_registrados_para_tests"]
    assert all(re.fullmatch(r"\+54911000\d{5}", t) for t in telefonos)


# Requirement: Corpus documental — scenarios
def test_corpus_minimo():
    corpus = cargar_corpus(CID)
    assert len(corpus.articulos()) >= 25
    assert len({a.ref.split("#")[0] for a in corpus.actas()}) >= 4
    assert all(d.consorcio_id == CID and d.fecha for d in corpus)


def test_articulo_modificado_por_acta():
    corpus = cargar_corpus(CID)
    modificadoras = [a for a in corpus.actas() if a.modifica]
    assert modificadoras
    reemplazado = corpus.get("REG-14")
    assert not reemplazado.vigente and reemplazado.reemplazado_por == "ACTA-2025-08-20#3"
    assert corpus.get("REG-22").vigente and "ACTA-2024-11-10#3" in corpus.get("REG-22").modificado_por


def test_temas_de_los_casos_de_test():
    texto = " ".join(d.texto.lower() for d in cargar_corpus(CID))
    for tema in ["animales domésticos", "fachada", "toldos", "cañerías de uso exclusivo", "partes comunes"]:
        assert tema in texto, tema
    assert "pileta" not in texto  # caso "sin fuente"


# Requirement: Base de la plataforma simulada
def test_reseed_idempotente(db_path):
    from scripts.seed_db import seed

    antes = _volcado(db_path)
    seed(db_path)
    assert _volcado(db_path) == antes


# Requirement: Siembra no destructiva — Scenario: Seed sobre una base con datos del panel
def test_seed_no_borra_lo_cargado_desde_el_panel(db_path):
    from eliseo.panel import padron
    from scripts.seed_db import seed
    from tests.cuentas_demo import sesion_demo

    cid = padron.alta_consorcio(sesion_demo(), "Consorcio Corrientes 1200", "Corrientes 1200", "911",
                                [padron.UnidadNueva(1, "A", "1")])
    antes = _volcado(db_path)
    seed(db_path)
    assert _volcado(db_path) == antes
    c = conectar(db_path)
    assert c.execute("SELECT COUNT(*) FROM consorcios WHERE consorcio_id IN ('R4520', ?)", (cid,)).fetchone()[0] == 2
    c.close()


# Requirement: Siembra no destructiva — Scenario: Recrear la base
def test_reset_en_postgres_pide_confirmacion(monkeypatch, capsys):
    import scripts.seed_db as s

    llamadas = []
    monkeypatch.setenv("ELISEO_DB_URL", "postgresql+psycopg://u:clave@db.ejemplo.supabase.co:5432/postgres")
    monkeypatch.setattr(s, "seed", lambda *a, **k: llamadas.append(k))
    assert s.main(["--reset"], entrada=lambda _: "otra-cosa") == 1
    salida = capsys.readouterr().out
    assert llamadas == [] and "No se borró nada" in salida
    assert "clave" not in salida  # la contraseña de la URL no se imprime
    assert s.main(["--reset"], entrada=lambda _: "db.ejemplo.supabase.co") == 0
    assert llamadas == [{"reset": True}]
    assert s.main([]) == 0 and llamadas[-1] == {"reset": False}


def test_coeficientes_suman_uno(conn):
    total = sum(u["coeficiente"] for u in lectura.unidades(conn, CID))
    assert abs(total - Decimal("1")) < Decimal("0.0001")


# Requirement: Datos que ejercitan las ramas
def test_suba_de_octubre_explicable(conn):
    sep = lectura.liquidacion(conn, CID, "2026-09")
    oct_ = lectura.liquidacion(conn, CID, "2026-10")
    previas = {(l.concepto, l.monto) for l in sep["lineas"]}
    nuevas = [l for l in oct_["lineas"] if (l.concepto, l.monto) not in previas]
    assert sum(l.monto for l in nuevas) == oct_["total"] - sep["total"] > 0
    assert all(l.comprobante and lectura.factura(conn, CID, l.comprobante) for l in nuevas)


def test_telefono_no_registrado(conn):
    assert lectura.identidad_por_telefono(conn, "+5491100009999") is None


def test_precedente_y_acta_de_la_montante(conn):
    assert any(p["prec_id"] == "PREC-2201" and "montante" in p["descripcion"] for p in lectura.precedentes(conn, CID))
    assert "montante de agua de la columna B" in cargar_corpus(CID).get("ACTA-2025-03-14#2").texto


def test_unidad_con_deuda_y_cuentas_aisladas(conn):
    vecino_3a = lectura.identidad_por_telefono(conn, "+5491100000301")
    vecino_4b = lectura.identidad_por_telefono(conn, "+5491100000402")
    assert lectura.cuenta_corriente(conn, vecino_3a)["saldo_deudor"] > 0
    cc_4b = lectura.cuenta_corriente(conn, vecino_4b)
    assert cc_4b["saldo_deudor"] == 0 and cc_4b["unidad"] == "4°B"


def test_expensas_prorrateadas_suman_el_total(conn):
    for periodo, mes in [("2026-09", "09/2026"), ("2026-10", "10/2026")]:
        (suma,) = conn.execute(
            "SELECT SUM(CAST(debe AS REAL)) FROM movimientos_cc WHERE concepto = ?", (f"Expensa {mes}",)
        ).fetchone()
        assert round(Decimal(str(suma)), 2) == lectura.liquidacion(conn, CID, periodo)["total"]
