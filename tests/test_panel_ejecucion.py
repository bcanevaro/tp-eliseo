"""Specs panel-admin y ejecucion: lógica del panel, ejecución idempotente y envío de la outbox. Sin LLM ni red."""
from pathlib import Path

import pytest
from pydantic import ValidationError

from eliseo import ejecucion
from eliseo.grafo import runtime
from eliseo.panel import servicio
from eliseo.plataforma import escritura
from eliseo.plataforma.db import get_conn
from eliseo.schemas import AccionAdmin, Adjunto, EstadoCaso, MensajeEntrante

TEL_4B = "+5491100000402"
APP = str(Path(__file__).resolve().parent.parent / "eliseo" / "panel" / "app.py")


@pytest.fixture
def bot(db_path):
    runtime._grafos.cache_clear()
    runtime._checkpointer.cache_clear()

    def enviar(texto="", usuario="u-4b", **kw) -> list[str]:
        msg = MensajeEntrante(chat_id=f"chat-{usuario}", usuario_canal_id=usuario, texto=texto, **kw)
        return [s.texto for s in runtime.procesar_mensaje(msg)]

    enviar(telefono_compartido=TEL_4B)
    return enviar


def _caso(bot) -> int:
    bot("Hay humedad en el techo del baño")
    bot("gotea desde hace una semana")
    bot(adjuntos=[Adjunto(tipo="foto", file_id="f1")])
    (caso_id,) = get_conn().execute("SELECT MAX(caso_id) FROM casos").fetchone()
    return caso_id


def _al_vecino():
    return [m for _, d, m in escritura.outbox_pendientes(get_conn()) if d == f"vecino:{TEL_4B}"]


def _pedidos(caso_id):
    return get_conn().execute("SELECT tipo FROM pedidos WHERE caso_id = ?", (caso_id,)).fetchall()


# ---------------------------------------------------------------- panel-admin

# Requirement: Bandeja por estado — Scenario: Llega una urgencia
def test_urgencia_primero_en_la_bandeja(bot):
    caso_id = _caso(bot)
    bot("hay olor a gas en el palier")
    grupos = servicio.bandeja("R4520")
    assert [g for g, _ in servicio.GRUPOS][0] == "urgencias"
    (urgencia,) = grupos["urgencias"]
    assert "gas" in urgencia.detalle and "4°B" in urgencia.titulo
    assert [i.id for i in grupos["pendientes"]] == [caso_id]


def test_bandeja_separa_derivaciones_e_incompletos(bot):
    bot("¿Puedo poner una pileta en la terraza?")
    bot(texto="Hablar con la administración")
    grupos = servicio.bandeja("R4520")
    assert len(grupos["sin_fuente"]) == 1 and "pileta" in grupos["sin_fuente"][0].detalle
    assert len(grupos["hablar"]) == 1
    assert servicio.bandeja("OTRO")["sin_fuente"] == []  # nada de otros consorcios


# Requirement: Lo escrito por la IA, marcado — Scenario: Revisión de un dictamen
def test_detalle_con_hipotesis_y_fuentes(bot):
    det = servicio.detalle_caso(_caso(bot))
    assert det.esperando_decision and det.caso.estado is EstadoCaso.PENDIENTE_APROBACION
    assert {h.responsable for h in det.dictamen.hipotesis} == {"unidad", "consorcio"}
    assert det.dictamen.recomendacion.tipo == "inspeccion"
    assert "REG-15" in det.fuentes and "uso exclusivo" in det.fuentes["REG-15"].lower()
    assert any(r.startswith("PREC-") for r in det.fuentes)
    assert det.verificacion is None or det.verificacion["ok"]


# Requirement: Aprobar, Modificar o Rechazar — Scenario: Rechazo sin motivo
def test_rechazo_exige_motivo():
    with pytest.raises(ValidationError):
        servicio.armar_decision(AccionAdmin.RECHAZAR, "laura", motivo="   ")


# Scenario: Modificar
def test_modificar_envia_el_texto_editado_y_registra_los_dos(bot):
    caso_id = _caso(bot)
    original = servicio.detalle_caso(caso_id).dictamen.mensaje_vecino
    editado = "Vamos a mandar un plomero esta semana para revisar tu baño y el del 5°B."
    servicio.decidir(caso_id, servicio.armar_decision("MODIFICAR", "laura", mensaje_final=editado))
    (m,) = _al_vecino()
    assert editado in m.texto and original not in m.texto and f"#{caso_id}" in m.texto
    det = servicio.detalle_caso(caso_id)
    assert det.decisiones[0]["mensaje_final"] == editado and det.dictamen.mensaje_vecino == original


# Requirement: Respuesta manual a derivaciones — Scenario: Consulta sin fuente
def test_respuesta_manual_a_consulta_sin_fuente(bot):
    bot("¿Puedo poner una pileta en la terraza?")
    (item,) = servicio.bandeja("R4520")["sin_fuente"]
    servicio.responder_derivacion(item.id, "No está permitido: requiere aprobación de asamblea.", "laura")
    (m,) = _al_vecino()
    assert m.de_la_administracion and "asamblea" in m.texto
    assert servicio.bandeja("R4520")["sin_fuente"] == []
    with pytest.raises(ValueError):
        servicio.responder_derivacion(item.id, "  ", "laura")


# ---------------------------------------------------------------- ejecucion

# Requirement: Confirmación antes de lo irreversible — Scenario: Cancelar en la confirmación
def test_vista_previa_no_ejecuta_nada(bot):
    caso_id = _caso(bot)
    det = servicio.detalle_caso(caso_id)
    prev = servicio.vista_previa(det, servicio.armar_decision("APROBAR", "laura"))
    assert "Sofía" in prev.destinatario and "4°B" in prev.destinatario and prev.canal_vinculado
    assert f"#{caso_id}" in prev.mensaje and "Fuente:" in prev.mensaje and prev.pedido.startswith("inspección")
    # Cancelar = no llamar a decidir: no salió nada y el caso sigue esperando.
    assert _al_vecino() == [] and not _pedidos(caso_id)
    assert escritura.obtener_caso(get_conn(), caso_id).estado is EstadoCaso.PENDIENTE_APROBACION


# Requirement: Idempotencia por dictamen — Scenario: Doble click en Aprobar
def test_doble_aprobacion_no_duplica(bot):
    caso_id = _caso(bot)
    decision = servicio.armar_decision("APROBAR", "laura")
    servicio.decidir(caso_id, decision)
    with pytest.raises(ValueError):
        servicio.decidir(caso_id, decision)
    assert len(_al_vecino()) == 1 and len(_pedidos(caso_id)) == 1


def test_reejecutar_el_nodo_no_duplica(bot):
    caso_id = _caso(bot)
    servicio.decidir(caso_id, servicio.armar_decision("APROBAR", "laura"))
    estado = runtime.estado_caso(caso_id)["valores"]
    ejecucion.ejecucion(estado)  # p. ej. un reintento tras una caída
    assert len(_al_vecino()) == 1 and len(_pedidos(caso_id)) == 1
    assert get_conn().execute("SELECT COUNT(*) FROM precedentes WHERE caso_id = ?", (caso_id,)).fetchone()[0] == 1


# Requirement: Envío y cierre — Scenario: Aprobación de inspección
def test_aprobacion_de_inspeccion_y_precedente(bot):
    caso_id = _caso(bot)
    caso = servicio.decidir(caso_id, servicio.armar_decision("APROBAR", "laura"))
    assert caso.estado is EstadoCaso.APROBADO
    (m,) = _al_vecino()
    assert f"#{caso_id}" in m.texto and "Fuente:" in m.texto and "REG-15" in m.texto
    assert [p["tipo"] for p in _pedidos(caso_id)] == ["inspeccion"]
    prec = get_conn().execute("SELECT * FROM precedentes WHERE caso_id = ?", (caso_id,)).fetchone()
    assert prec["prec_id"].startswith("PREC-") and f"caso {caso_id}" in prec["procedencia"]
    assert "laura" in prec["procedencia"] and prec["tipo"] == "filtracion" and "columna B" in prec["ubicacion"]


# spec precedentes — Scenario: Dictamen rechazado
def test_rechazo_no_crea_precedente(bot):
    caso_id = _caso(bot)
    servicio.decidir(caso_id, servicio.armar_decision("RECHAZAR", "laura", motivo="falta inspección"))
    assert get_conn().execute("SELECT COUNT(*) FROM precedentes WHERE caso_id = ?", (caso_id,)).fetchone()[0] == 0
    assert not _pedidos(caso_id) and _al_vecino() == []


# Requirement: Aviso de urgencias — Scenario: Olor a gas
def test_urgencia_llega_al_chat_de_la_administracion(bot, monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHAT_ADMIN_ID", "chat-admin")
    bot("hay mucho olor a gas en el palier")
    enviados = []
    assert ejecucion.enviar_pendientes(lambda chat, m: enviados.append((chat, m.texto))) == 1
    ((chat, texto),) = enviados
    assert chat == "chat-admin" and "4°B" in texto and "gas" in texto
    assert ejecucion.enviar_pendientes(lambda chat, m: enviados.append(chat)) == 0  # no se reenvía


def test_outbox_va_al_chat_vinculado_del_vecino(bot):
    caso_id = _caso(bot)
    servicio.decidir(caso_id, servicio.armar_decision("APROBAR", "laura"))
    enviados = []
    ejecucion.enviar_pendientes(lambda chat, m: enviados.append(chat))
    assert enviados == ["chat-u-4b"]


def test_falla_de_envio_queda_pendiente(bot, monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHAT_ADMIN_ID", "chat-admin")
    bot("hay olor a gas")

    def falla(chat, m):
        raise RuntimeError("Telegram caído")

    assert ejecucion.enviar_pendientes(falla) == 0
    assert len(escritura.outbox_pendientes(get_conn())) == 1


# ---------------------------------------------------------------- interfaz (Streamlit AppTest)

def test_panel_aprobar_con_confirmacion(bot):
    from streamlit.testing.v1 import AppTest

    caso_id = _caso(bot)
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    at.button(key=f"caso-{caso_id}").click().run()
    assert any("Hipótesis A" in m.value for m in at.markdown)
    at.button(key=f"rev-{caso_id}").click().run()
    assert any("Confirmá antes de ejecutar" in s.value for s in at.subheader)
    assert _al_vecino() == []  # todavía no salió nada
    at.button(key=f"conf-{caso_id}").click().run()
    assert not at.exception
    assert escritura.obtener_caso(get_conn(), caso_id).estado is EstadoCaso.APROBADO
    assert len(_al_vecino()) == 1


def test_panel_rechazo_bloqueado_sin_motivo(bot):
    from streamlit.testing.v1 import AppTest

    caso_id = _caso(bot)
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.button(key=f"caso-{caso_id}").click().run()
    at.radio(key=f"accion-{caso_id}").set_value("Rechazar").run()
    assert at.button(key=f"rev-{caso_id}").disabled


def test_simulador_de_vecino(db_path):
    from streamlit.testing.v1 import AppTest

    runtime._grafos.cache_clear()
    runtime._checkpointer.cache_clear()
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.sidebar.radio[0].set_value("Simulador de vecino").run()
    assert not at.exception
    at.chat_input[0].set_value("¿Puedo tener un perro?").run()
    assert any("REG-18" in m.value for m in at.markdown)


# ---------------------------------------------------------------- evaluacion-e2e

def test_evaluacion_e2e_corre_los_12_casos(db_path, monkeypatch):
    from evaluation.e2e import correr

    # correr() cambia la base por caso: monkeypatch restaura las variables al terminar.
    monkeypatch.setenv("ELISEO_DB_PATH", str(db_path))

    filas = correr.correr()
    assert len(filas) == 12 and {f["tipo"] for f in filas} == {"uso", "borde", "neg"}
    assert all("refs_esperadas" in f["resultado"] for f in filas)
