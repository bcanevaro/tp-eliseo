"""Tests de la spec documentos-consorcio (change cuentas-administracion)."""
from pathlib import Path

import pytest

from eliseo import cuentas
from eliseo import documentos as docs
from eliseo.agentes.documental import retriever
from eliseo.config import CONSORCIOS_DIR
from eliseo.corpus import cargar_corpus, fuentes_de_directorio
from eliseo.panel import documentos as panel_docs
from eliseo.panel import padron, servicio
from eliseo.plataforma.db import get_conn
from tests.cuentas_demo import app_logueada, sesion_demo
from tests.test_padron import IndiceFalso

APP = str(Path(__file__).resolve().parent.parent / "eliseo" / "panel" / "app.py")

REGLAMENTO = """# Reglamento — Consorcio Corrientes 1200

<!-- fecha: 2001-03-01 -->

## REG-1 · Objeto
Rige las relaciones entre los propietarios del edificio de Corrientes 1200.

## REG-14 · Horario de obras
Las obras ruidosas solo pueden hacerse de lunes a viernes de 9 a 18 horas.

## REG-18 · Animales
Se permiten animales domésticos que no molesten a los vecinos.
"""

ACTA = """# Acta de Asamblea — 10/05/2024

<!-- fecha: 2024-05-10 -->

## ACTA-2024-05-10#1 · Firmantes
Firman el acta los propietarios del 1°A y del 2°B.

## ACTA-2024-05-10#2 · Nuevo horario de obras
<!-- modifica: REG-14 · efecto: reemplaza -->
Desde ahora las obras ruidosas solo pueden hacerse de lunes a viernes de 10 a 17 horas.
"""


@pytest.fixture
def edificio(db_path):
    """Un consorcio nuevo de la Administración Méndez, todavía sin documentos."""
    return padron.alta_consorcio(sesion_demo(), "Consorcio Corrientes 1200", "Corrientes 1200", "911",
                                 [padron.UnidadNueva(1, "A", "1")])


def _subir(cid, tipo, texto, index=None, nombre=None):
    return panel_docs.confirmar(sesion_demo(), cid, tipo, texto.encode("utf-8"), nombre or f"{tipo}.md", index=index)


def _errores(cid, tipo, texto) -> list[str]:
    return [str(e) for e in panel_docs.revisar(sesion_demo(), cid, tipo, texto.encode("utf-8")).errores]


# ---------------------------------------------------------------- Carga de documentos

# Scenario: Primer reglamento de un edificio nuevo
def test_primer_reglamento_de_un_edificio_nuevo(edificio):
    assert len(cargar_corpus(edificio)) == 0
    assert retriever.buscar(edificio, "animales").documentos == []
    _subir(edificio, "Reglamento", REGLAMENTO)
    r = retriever.buscar(edificio, "¿puedo tener animales?")
    assert r.documentos[0].ref == "REG-18" and r.documentos[0].consorcio_id == edificio


def test_los_documentos_de_la_demo_pasan_la_validacion(db_path):
    """La siembra los cargó con la misma validación que el panel."""
    filas = get_conn().execute("SELECT tipo, ref, estado FROM documentos WHERE consorcio_id = 'R4520'").fetchall()
    assert len(filas) == len(fuentes_de_directorio(CONSORCIOS_DIR / "rivadavia-4520")) == 5
    assert {f["estado"] for f in filas} == {"activo"}
    assert len(cargar_corpus("R4520")) == 43


# ---------------------------------------------------------------- Validación antes de guardar

# Scenario: Acta que modifica un artículo inexistente
def test_acta_que_modifica_un_articulo_inexistente(edificio):
    _subir(edificio, "Reglamento", REGLAMENTO)
    mala = ACTA.replace("modifica: REG-14", "modifica: REG-40")
    (error,) = _errores(edificio, "Acta", mala)
    assert "REG-40" in error and "no existe" in error and error.startswith("Línea 9:")  # la del comentario
    with pytest.raises(docs.DocumentoInvalido):
        _subir(edificio, "Acta", mala)
    assert get_conn().execute("SELECT COUNT(*) FROM documentos WHERE consorcio_id = ?", (edificio,)).fetchone()[0] == 1


# Scenario: Archivo que no es del formato
def test_pdf_y_markdown_sin_secciones(edificio):
    pdf = panel_docs.revisar(sesion_demo(), edificio, "Reglamento", b"%PDF-1.7 binario")
    assert not pdf.ok and "Markdown" in str(pdf.errores[0])
    (error,) = _errores(edificio, "Reglamento", "# Reglamento\n\n<!-- fecha: 2001-03-01 -->\n\nTexto suelto.\n")
    assert "plantilla" in error


@pytest.mark.parametrize("cambio, esperado", [
    (("## REG-14 · Horario de obras", "## Art 14 · Horario de obras"), "no es un id válido"),
    (("## REG-18 · Animales", "## REG-14 · Animales"), "está repetido"),
    (("## REG-18 · Animales", "## REG-18 - Animales"), "encabezado tiene que ser"),
    (("<!-- fecha: 2001-03-01 -->", ""), "Falta la fecha"),
    (("<!-- fecha: 2001-03-01 -->", "<!-- consorcio_id: R4520 · fecha: 2001-03-01 -->"), "no de este"),
    (("Se permiten animales domésticos que no molesten a los vecinos.", ""), "REG-18 no tiene texto"),
])
def test_reglas_del_reglamento(edificio, cambio, esperado):
    errores = _errores(edificio, "Reglamento", REGLAMENTO.replace(*cambio))
    assert any(esperado in e for e in errores), errores


@pytest.mark.parametrize("cambio, esperado", [
    (("## ACTA-2024-05-10#1", "## ACTA-2024-05-11#1"), "no tiene la fecha del acta"),
    (("efecto: reemplaza", "efecto: deroga"), "el efecto tiene que ser"),
])
def test_reglas_del_acta(edificio, cambio, esperado):
    _subir(edificio, "Reglamento", REGLAMENTO)
    errores = _errores(edificio, "Acta", ACTA.replace(*cambio))
    assert any(esperado in e for e in errores), errores


def test_acta_repetida_y_reglamento_que_borra_un_articulo_modificado(edificio):
    _subir(edificio, "Reglamento", REGLAMENTO)
    _subir(edificio, "Acta", ACTA)
    assert any("Ya hay un acta del 2024-05-10" in e for e in _errores(edificio, "Acta", ACTA))
    sin_14 = REGLAMENTO.replace("## REG-14 · Horario de obras\nLas obras ruidosas solo pueden hacerse de lunes a "
                                "viernes de 9 a 18 horas.\n\n", "")
    assert any("ACTA-2024-05-10#2 modifica el REG-14" in e for e in _errores(edificio, "Reglamento", sin_14))


# ---------------------------------------------------------------- Vista previa y confirmación

# Scenario: Confirmar después de revisar
def test_vista_previa_no_guarda_nada(edificio):
    _subir(edificio, "Reglamento", REGLAMENTO)
    rev = panel_docs.revisar(sesion_demo(), edificio, "Acta", ACTA.encode())
    assert rev.ok and rev.ref == "ACTA-2024-05-10"
    assert [(s.ref, s.modifica) for s in rev.secciones] == [("ACTA-2024-05-10#1", None), ("ACTA-2024-05-10#2", "REG-14")]
    assert cargar_corpus(edificio).get("ACTA-2024-05-10#2") is None  # todavía no está disponible


# Scenario: Acta que reemplaza un artículo
def test_acta_que_reemplaza_un_articulo(edificio):
    _subir(edificio, "Reglamento", REGLAMENTO)
    assert retriever.buscar(edificio, "horario de obras ruidosas").documentos[0].ref == "REG-14"
    _subir(edificio, "Acta", ACTA)
    corpus = cargar_corpus(edificio)
    assert corpus.get("REG-14").reemplazado_por == "ACTA-2024-05-10#2"
    assert retriever.buscar(edificio, "horario de obras ruidosas").documentos[0].ref == "ACTA-2024-05-10#2"


# Scenario: Servicio de búsqueda caído
def test_pinecone_caido_deja_el_documento_pendiente(edificio):
    class Caido:
        def __getattr__(self, _):
            raise ConnectionError("Pinecone no responde")

    _subir(edificio, "Reglamento", REGLAMENTO, index=Caido())
    (doc,) = panel_docs.listar(sesion_demo(), edificio)
    assert doc["estado"] == "activo" and doc["indexado"] == 0
    assert retriever.buscar(edificio, "animales").documentos[0].ref == "REG-18"  # BM25 lo encuentra igual
    indice = IndiceFalso({})
    assert panel_docs.reintentar_indexacion(sesion_demo(), edificio, index=indice)
    assert indice.ids["documentos"] == {f"{edificio}:REG-1", f"{edificio}:REG-14", f"{edificio}:REG-18"}
    assert panel_docs.listar(sesion_demo(), edificio)[0]["indexado"] == 1


# ---------------------------------------------------------------- Reemplazo y baja

def test_reemplazo_del_reglamento(edificio):
    _subir(edificio, "Reglamento", REGLAMENTO)
    nuevo = REGLAMENTO.replace("Se permiten animales domésticos", "Se permiten solo perros y gatos")
    indice = IndiceFalso({})
    _subir(edificio, "Reglamento", nuevo, index=indice)
    estados = [(d["tipo"], d["estado"]) for d in panel_docs.listar(sesion_demo(), edificio)]
    assert estados == [("Reglamento", "activo"), ("Reglamento", "reemplazado")]
    assert "perros y gatos" in cargar_corpus(edificio).get("REG-18").texto


# Scenario: Baja de un acta citada en un caso viejo
def test_baja_de_un_acta_citada(edificio):
    _subir(edificio, "Reglamento", REGLAMENTO)
    acta_id = _subir(edificio, "Acta", ACTA)
    panel_docs.dar_de_baja(sesion_demo(), edificio, acta_id, index=IndiceFalso({}))
    assert cargar_corpus(edificio).get("ACTA-2024-05-10#2") is None  # no se cita en consultas nuevas
    texto = servicio._texto_fuente(get_conn(), edificio, "ACTA-2024-05-10#2")
    assert "de 10 a 17 horas" in texto  # el caso viejo sigue mostrando lo que se citó


# Scenario: Acta de la que depende la vigencia
def test_baja_del_acta_devuelve_la_vigencia(edificio):
    _subir(edificio, "Reglamento", REGLAMENTO)
    acta_id = _subir(edificio, "Acta", ACTA)
    assert not cargar_corpus(edificio).get("REG-14").vigente
    panel_docs.dar_de_baja(sesion_demo(), edificio, acta_id, index=IndiceFalso({}))
    assert cargar_corpus(edificio).get("REG-14").vigente
    assert retriever.buscar(edificio, "horario de obras ruidosas").documentos[0].ref == "REG-14"


def test_el_reglamento_no_se_da_de_baja(edificio):
    reg_id = _subir(edificio, "Reglamento", REGLAMENTO)
    with pytest.raises(ValueError, match="reemplazarlo"):
        panel_docs.dar_de_baja(sesion_demo(), edificio, reg_id)


# ---------------------------------------------------------------- Aislamiento

# Scenario: Mismo id en dos edificios
def test_mismo_id_en_dos_edificios_de_administraciones_distintas(edificio):
    aid = cuentas.crear_administracion("Administración Pérez")
    cuentas.crear_administrador(aid, "p@eliseo.test", "Pedro", "clave-segura-1")
    otra = cuentas.autenticar("p@eliseo.test", "clave-segura-1")
    otro_cid = padron.alta_consorcio(otra, "Consorcio Belgrano 300", "Belgrano 300", "911", [padron.UnidadNueva(1, "A", "1")])
    _subir(edificio, "Reglamento", REGLAMENTO)
    panel_docs.confirmar(otra, otro_cid, "Reglamento",
                         REGLAMENTO.replace("de 9 a 18 horas", "de 8 a 20 horas").encode(), "r.md")
    assert "9 a 18" in cargar_corpus(edificio).get("REG-14").texto
    assert "8 a 20" in cargar_corpus(otro_cid).get("REG-14").texto
    for llamada in (lambda: panel_docs.listar(otra, edificio),
                    lambda: panel_docs.original(otra, panel_docs.listar(sesion_demo(), edificio)[0]["doc_id"]),
                    lambda: panel_docs.confirmar(otra, edificio, "Acta", ACTA.encode(), "a.md")):
        with pytest.raises(servicio.NoEncontrado):
            llamada()


# ---------------------------------------------------------------- Archivo original

# Scenario: Descarga del original
def test_descarga_del_original(edificio):
    original = REGLAMENTO.replace("\n", "\r\n").encode("utf-8")  # tal cual lo subió, con CRLF de Windows
    doc_id = panel_docs.confirmar(sesion_demo(), edificio, "Reglamento", original, "reglamento-corrientes.md")
    (doc,) = panel_docs.listar(sesion_demo(), edificio)
    assert doc["subido_por"] == sesion_demo().email and doc["creado"]
    assert panel_docs.original(sesion_demo(), doc_id) == ("reglamento-corrientes.md", original)


# ---------------------------------------------------------------- interfaz

def test_vista_documentos(edificio):
    at = app_logueada(APP).run()
    at.sidebar.radio[0].set_value("Documentos").run()
    at.sidebar.selectbox[0].set_value(edificio).run()
    assert not at.exception
    assert any("no tiene reglamento" in w.value for w in at.warning)
    at.sidebar.selectbox[0].set_value("R4520").run()
    assert not at.exception
    assert sum("**Acta**" in m.value for m in at.markdown) == 4
    assert any("**Reglamento** · REGLAMENTO" in m.value for m in at.markdown)
