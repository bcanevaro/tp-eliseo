"""Tests de la spec padron-consorcios (change cuentas-administracion)."""
from pathlib import Path

import pytest

from eliseo import cuentas, textos
from eliseo.grafo import runtime
from eliseo.panel import padron, servicio
from eliseo.panel.padron import DatoInvalido, UnidadNueva
from eliseo.plataforma import escritura, lectura
from eliseo.plataforma.db import get_conn
from eliseo.schemas import EstadoCaso, MensajeEntrante
from tests.cuentas_demo import app_logueada, sesion_demo

APP = str(Path(__file__).resolve().parent.parent / "eliseo" / "panel" / "app.py")
TEL_3A = "+5491100000301"


def _unidades(n=8):
    """n unidades de dos por piso cuyos coeficientes suman 1."""
    coef = f"{1 / n:.4f}"
    us = [UnidadNueva(piso=1 + i // 2, depto="AB"[i % 2], coeficiente=coef) for i in range(n)]
    us[-1].coeficiente = f"{1 - float(coef) * (n - 1):.4f}"
    return us


@pytest.fixture
def bot(db_path):
    runtime._grafos.cache_clear()
    runtime._checkpointer.cache_clear()

    def enviar(texto="", usuario="u-1", **kw) -> list[str]:
        msg = MensajeEntrante(chat_id=f"chat-{usuario}", usuario_canal_id=usuario, texto=texto, **kw)
        return [s.texto for s in runtime.procesar_mensaje(msg)]

    return enviar


class IndiceFalso:
    """Lo mínimo de un índice de Pinecone que usa `ingesta.sincronizar`."""

    def __init__(self, ids):
        self.ids = {ns: set(v) for ns, v in ids.items()}

    def list(self, prefix, namespace):
        return [[i for i in self.ids.get(namespace, set()) if i.startswith(prefix)]]

    def upsert_records(self, namespace, records):
        self.ids.setdefault(namespace, set()).update(r["_id"] for r in records)

    def delete(self, ids, namespace):
        self.ids[namespace] -= set(ids)


# ---------------------------------------------------------------- consorcios y unidades

# Scenario: Edificio nuevo
def test_alta_de_edificio(db_path):
    sesion = sesion_demo()
    cid = padron.alta_consorcio(sesion, "Consorcio Corrientes 1200", "Corrientes 1200, CABA", "911", _unidades(8))
    assert cid == "CORRIENTES-1200"
    assert {c["consorcio_id"] for c in servicio.consorcios(sesion)} == {"R4520", cid}
    us = padron.unidades(sesion, cid)
    assert [u["unidad"] for u in us][:3] == ["1°A", "1°B", "2°A"] and len(us) == 8
    assert sum(u["coeficiente"] for u in us) == 1
    # No aparece en otra administración.
    aid = cuentas.crear_administracion("Administración Pérez")
    cuentas.crear_administrador(aid, "p@eliseo.test", "Pedro", "clave-segura-1")
    assert servicio.consorcios(cuentas.autenticar("p@eliseo.test", "clave-segura-1")) == []


# Scenario: Coeficientes que no cierran
def test_coeficientes_que_no_cierran(db_path):
    us = _unidades(4)
    us[0].coeficiente = "0.22"  # 0.22 + 0.25 * 3 = 0.97
    with pytest.raises(DatoInvalido, match=r"suman 0\.97 y tienen que sumar 1"):
        padron.alta_consorcio(sesion_demo(), "Consorcio Mal", "Calle 1", "911", us)
    assert get_conn().execute("SELECT COUNT(*) FROM consorcios").fetchone()[0] == 1


def test_unidad_repetida_y_datos_faltantes(db_path):
    us = _unidades(2)
    us[1].depto = "a"
    us[1].piso = us[0].piso
    with pytest.raises(DatoInvalido, match="repetida"):
        padron.alta_consorcio(sesion_demo(), "Consorcio X", "Calle 1", "911", us)
    with pytest.raises(DatoInvalido, match="nombre"):
        padron.alta_consorcio(sesion_demo(), "  ", "Calle 1", "911", _unidades(2))


# Scenario: Unidad con vecino
def test_no_se_quita_una_unidad_con_vecino(db_path):
    sesion = sesion_demo()
    actuales = padron.unidades(sesion, "R4520")
    sin_4b = [UnidadNueva(u["piso"], u["depto"], u["coeficiente"], u["unidad_id"])
              for u in actuales if u["unidad"] != "4°B"]
    sin_4b[0].coeficiente += next(u["coeficiente"] for u in actuales if u["unidad"] == "4°B")  # sigue sumando 1
    with pytest.raises(DatoInvalido, match="4°B tiene vecinos registrados"):
        padron.guardar_unidades(sesion, "R4520", sin_4b)
    assert len(padron.unidades(sesion, "R4520")) == 12


def test_editar_unidades_y_datos_del_consorcio(db_path):
    sesion = sesion_demo()
    cid = padron.alta_consorcio(sesion, "Consorcio Corrientes 1200", "Corrientes 1200", "911", _unidades(2))
    (a, b) = padron.unidades(sesion, cid)
    padron.guardar_unidades(sesion, cid, [UnidadNueva(a["piso"], a["depto"], "0.5", a["unidad_id"]),
                                          UnidadNueva(0, "c", "0.5")])  # quita 1°B, agrega PB C
    assert [(u["unidad"], str(u["coeficiente"])) for u in padron.unidades(sesion, cid)] == [("PBC", "0.5000"), ("1°A", "0.5000")]
    padron.editar_consorcio(sesion, cid, "Consorcio Corrientes 1200 bis", "Corrientes 1200", "0800")
    assert padron.consorcio(sesion, cid)["nombre"] == "Consorcio Corrientes 1200 bis"


# Scenario: Baja confirmada
def test_baja_de_consorcio(bot):
    sesion = sesion_demo()
    bot(telefono_compartido=TEL_3A)
    caso = escritura.registrar_caso(get_conn(), escritura.Caso(
        consorcio_id="R4520", unidad_id="R4520-3A", reclamo=escritura.ReclamoBorrador(descripcion="x")))
    indice = IndiceFalso({"documentos": {"R4520:REG-1", "R4520:REG-2", "OTRO:REG-1"},
                          "precedentes": {"R4520:PREC-2195"}})

    padron.baja_consorcio(sesion, "R4520", index=indice)

    assert servicio.consorcios(sesion) == []
    assert indice.ids == {"documentos": {"OTRO:REG-1"}, "precedentes": set()}
    # El vínculo de Telegram sigue, pero el teléfono ya no da una identidad.
    assert bot("hola") == [textos.TELEFONO_NO_REGISTRADO]
    # El historial queda en la base.
    assert escritura.obtener_caso(get_conn(), caso.caso_id) is not None
    with pytest.raises(servicio.NoEncontrado):
        servicio.bandeja(sesion, "R4520")


# ---------------------------------------------------------------- vecinos

@pytest.mark.parametrize("entrada", ["11 5555-1234", "011 5555 1234", "+54 11 5555 1234", "+54 9 11 5555-1234"])
def test_normalizar_telefono(entrada):
    assert padron.normalizar_telefono_ar(entrada) == "+5491155551234"


# Scenario: Teléfono inválido
@pytest.mark.parametrize("entrada", ["", "1234", "abc", "+1 555 123 4567", "0000000000"])
def test_telefono_invalido(entrada):
    with pytest.raises(DatoInvalido):
        padron.normalizar_telefono_ar(entrada)


# Scenario: Vecino nuevo
def test_alta_de_vecino_y_saludo_en_el_bot(bot):
    sesion = sesion_demo()
    cid = padron.alta_consorcio(sesion, "Consorcio Corrientes 1200", "Corrientes 1200", "911", _unidades(4))
    unidad_2a = next(u["unidad_id"] for u in padron.unidades(sesion, cid) if u["unidad"] == "2°A")
    tel = padron.alta_vecino(sesion, unidad_2a, "Ana Pérez", "11 5555-1234")
    assert tel == "+5491155551234"
    (saludo,) = bot(telefono_compartido=tel, usuario="u-ana")
    assert "Ana" in saludo and "2°A" in saludo


# Scenario: Teléfono ya registrado
def test_telefono_ya_registrado_no_revela_donde(db_path):
    sesion = sesion_demo()
    with pytest.raises(DatoInvalido) as e:
        padron.alta_vecino(sesion, "R4520-1A", "Otra Persona", TEL_3A)
    assert str(e.value) == padron.TELEFONO_REGISTRADO
    assert "3°A" not in str(e.value) and "Rivadavia" not in str(e.value)


def test_vecino_en_unidad_ajena(db_path):
    aid = cuentas.crear_administracion("Administración Pérez")
    cuentas.crear_administrador(aid, "p@eliseo.test", "Pedro", "clave-segura-1")
    otra = cuentas.autenticar("p@eliseo.test", "clave-segura-1")
    for llamada in (lambda: padron.alta_vecino(otra, "R4520-1A", "Intruso", "11 4444-0000"),
                    lambda: padron.baja_vecino(otra, TEL_3A),
                    lambda: padron.unidades(otra, "R4520"),
                    lambda: padron.baja_consorcio(otra, "R4520", index=IndiceFalso({}))):
        with pytest.raises(servicio.NoEncontrado):
            llamada()
    assert lectura.identidad_por_telefono(get_conn(), TEL_3A) is not None


# Scenario: Cambio de teléfono
def test_cambio_de_telefono_borra_el_vinculo(bot):
    sesion = sesion_demo()
    assert "Carlos" in bot(telefono_compartido=TEL_3A)[0]
    padron.editar_vecino(sesion, TEL_3A, "Carlos Medina", "R4520-3A", "11 4444-3333")
    assert bot("hola") == [textos.PEDIR_CONTACTO]
    (saludo,) = bot(telefono_compartido="+5491144443333")
    assert "Carlos" in saludo


# Scenario: Vecino dado de baja
def test_baja_de_vecino(bot):
    sesion = sesion_demo()
    bot(telefono_compartido=TEL_3A)
    caso = escritura.registrar_caso(get_conn(), escritura.Caso(
        consorcio_id="R4520", unidad_id="R4520-3A", reclamo=escritura.ReclamoBorrador(descripcion="viejo")))
    padron.baja_vecino(sesion, TEL_3A)
    assert bot("hola") == [textos.PEDIR_CONTACTO]
    assert bot(telefono_compartido=TEL_3A) == [textos.TELEFONO_NO_REGISTRADO]
    assert any(h["caso_id"] == caso.caso_id for h in servicio.historial(sesion, "R4520")) or \
        escritura.obtener_caso(get_conn(), caso.caso_id).unidad_id == "R4520-3A"


# Scenario: Conversación en curso
def test_baja_con_reclamo_a_medio_cargar(bot):
    sesion = sesion_demo()
    bot(telefono_compartido=TEL_3A)
    bot("Hay humedad en el techo del baño")  # el bot pide más datos
    padron.baja_vecino(sesion, TEL_3A)
    (item,) = servicio.bandeja(sesion, "R4520")["incompletos"]
    assert "humedad" in item.detalle.lower()
    assert escritura.obtener_caso(get_conn(), item.id).estado is EstadoCaso.INCOMPLETO
    assert bot("es en el baño") == [textos.PEDIR_CONTACTO]  # no le repregunta más


# Scenario: Mudanza a otro edificio de la misma administración
def test_mudanza_cambia_el_consorcio_del_vecino(bot):
    sesion = sesion_demo()
    cid = padron.alta_consorcio(sesion, "Consorcio Corrientes 1200", "Corrientes 1200", "911", _unidades(2))
    nueva = padron.unidades(sesion, cid)[0]["unidad_id"]
    bot(telefono_compartido=TEL_3A)
    padron.editar_vecino(sesion, TEL_3A, "Carlos Medina", nueva, TEL_3A)
    ident = lectura.identidad_por_telefono(get_conn(), TEL_3A)
    assert ident.consorcio_id == cid and ident.unidad == "1°A"
    # Sin reiniciar nada y con el mismo vínculo de Telegram, sus mensajes van al hilo del consorcio nuevo.
    msg = MensajeEntrante(chat_id="chat-u-1", usuario_canal_id="u-1", texto="hola")
    assert runtime.thread_conversacion(msg) == f"{TEL_3A}:{cid}"


# ---------------------------------------------------------------- interfaz

def test_vistas_edificios_y_vecinos(db_path):
    at = app_logueada(APP).run()
    at.sidebar.radio[0].set_value("Edificios").run()
    assert not at.exception
    assert any("Consorcio Rivadavia 4520" in s.value for s in at.subheader)
    assert any(f.label == "Nombre" and f.value == "Consorcio Rivadavia 4520" for f in at.text_input)
    at.sidebar.radio[0].set_value("Vecinos").run()
    assert not at.exception
    assert any("Carlos Medina" in str(df.value) for df in at.dataframe)
