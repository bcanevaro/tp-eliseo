"""Tests de la spec canal-administracion (change cuentas-administracion)."""
from datetime import timedelta
from pathlib import Path

import pytest

from eliseo import cuentas, ejecucion, textos
from eliseo.agentes.mediador import agente as mediador
from eliseo.agentes.mediador.criterios import SIN_CRITERIOS
from eliseo.canal import bot
from eliseo.grafo import runtime
from eliseo.panel import documentos as panel_docs
from eliseo.panel import padron
from eliseo.plataforma import escritura
from eliseo.plataforma.db import get_conn
from eliseo.schemas import MensajeEntrante
from tests.cuentas_demo import app_logueada, sesion_demo, vincular_chat_demo
from tests.test_documentos import REGLAMENTO

APP = str(Path(__file__).resolve().parent.parent / "eliseo" / "panel" / "app.py")
TEL_4B = "+5491100000402"


@pytest.fixture
def enviar(db_path):
    runtime._grafos.cache_clear()
    runtime._checkpointer.cache_clear()

    def _enviar(texto="", usuario="u-1", **kw) -> list[str]:
        msg = MensajeEntrante(chat_id=f"chat-{usuario}", usuario_canal_id=usuario, texto=texto, **kw)
        return [s.texto for s in runtime.procesar_mensaje(msg)]

    return _enviar


@pytest.fixture
def otra(db_path):
    """La Administración Pérez con un edificio, un reglamento propio y una vecina."""
    aid = cuentas.crear_administracion("Administración Pérez")
    cuentas.crear_administrador(aid, "p@eliseo.test", "Pedro Pérez", "clave-segura-1")
    sesion = cuentas.autenticar("p@eliseo.test", "clave-segura-1")
    cid = padron.alta_consorcio(sesion, "Consorcio Corrientes 1200", "Corrientes 1200", "911",
                                [padron.UnidadNueva(1, "A", "1")])
    panel_docs.confirmar(sesion, cid, "Reglamento", REGLAMENTO.encode(), "reglamento.md")
    tel = padron.alta_vecino(sesion, f"{cid}-1A", "Ana Pérez", "11 0000-7777")
    return {"sesion": sesion, "consorcio_id": cid, "telefono": tel}


def _enviados() -> list[tuple[str, str]]:
    enviados = []
    ejecucion.enviar_pendientes(lambda chat, m: enviados.append((chat, m.texto)))
    return enviados


# ---------------------------------------------------------------- Un bot para todas las administraciones

# Scenario: Vecinos de dos administraciones
def test_vecinos_de_dos_administraciones_en_el_mismo_bot(enviar, otra):
    enviar(telefono_compartido=TEL_4B, usuario="u-4b")
    enviar(telefono_compartido=otra["telefono"], usuario="u-ana")
    rivadavia = enviar("¿Puedo tener un perro?", usuario="u-4b")[-1]
    corrientes = enviar("¿Puedo tener un perro?", usuario="u-ana")[-1]
    assert "REG-18" in rivadavia and "REG-18" in corrientes
    assert "animales domésticos que no molesten" in corrientes  # el texto del reglamento de Corrientes
    assert "animales domésticos que no molesten" not in rivadavia


# ---------------------------------------------------------------- Presentación con la administración

# Scenario: Saludo
def test_saludo_con_la_administracion_del_vecino(enviar, otra):
    (saludo,) = enviar(telefono_compartido=TEL_4B, usuario="u-4b")
    assert "4°B" in saludo and "asistente de Administración Méndez" in saludo
    (saludo,) = enviar(telefono_compartido=otra["telefono"], usuario="u-ana")
    assert "asistente de Administración Pérez" in saludo


# ---------------------------------------------------------------- Vinculación del chat de la administración

# Scenario: Vincular el chat
def test_vincular_el_chat_con_un_codigo(db_path):
    codigo = cuentas.generar_codigo_avisos(sesion_demo())
    assert len(codigo) == 8
    assert get_conn().execute("SELECT COUNT(*) FROM codigos_vinculacion WHERE codigo_hash = ?",
                              (codigo,)).fetchone()[0] == 0  # en la base queda el hash, no el código
    texto = bot.respuesta_admin(codigo.lower(), "chat-admin")
    assert "Listo" in texto and "Administración Méndez" in texto
    assert cuentas.chat_avisos("administracion-mendez") == "chat-admin"


def test_el_codigo_sirve_una_sola_vez_y_el_nuevo_chat_reemplaza_al_anterior(db_path):
    codigo = cuentas.generar_codigo_avisos(sesion_demo())
    assert cuentas.vincular_chat_avisos(codigo, "chat-1") == "Administración Méndez"
    assert cuentas.vincular_chat_avisos(codigo, "chat-2") is None  # ya usado
    assert cuentas.chat_avisos("administracion-mendez") == "chat-1"
    assert cuentas.vincular_chat_avisos(cuentas.generar_codigo_avisos(sesion_demo()), "chat-2")
    assert cuentas.chat_avisos("administracion-mendez") == "chat-2"


# Scenario: Código vencido
def test_codigo_vencido_o_inexistente(db_path, monkeypatch):
    codigo = cuentas.generar_codigo_avisos(sesion_demo())
    ahora = cuentas._ahora_utc()
    monkeypatch.setattr(cuentas, "_ahora_utc", lambda: ahora + timedelta(minutes=16))
    assert bot.respuesta_admin(codigo, "chat-x").startswith("Ese código no es válido")
    assert bot.respuesta_admin("NOEXISTE", "chat-x").startswith("Ese código no es válido")
    assert bot.respuesta_admin("", "chat-x").startswith("Ese código no es válido")
    assert cuentas.chat_avisos("administracion-mendez") is None


# ---------------------------------------------------------------- Avisos al chat de su administración

# Scenario: Urgencia en un consorcio
def test_urgencia_llega_solo_al_chat_de_su_administracion(enviar, otra):
    vincular_chat_demo("chat-mendez")
    assert cuentas.vincular_chat_avisos(cuentas.generar_codigo_avisos(otra["sesion"]), "chat-perez")
    enviar(telefono_compartido=TEL_4B, usuario="u-4b")
    enviar("hay mucho olor a gas en el palier", usuario="u-4b")
    avisos = [(chat, t) for chat, t in _enviados() if chat.startswith("chat-") and "gas" in t and "4°B" in t]
    assert [chat for chat, _ in avisos] == ["chat-mendez"]


# Scenario: Administración sin chat vinculado
def test_urgencia_sin_chat_vinculado_queda_pendiente(enviar):
    enviar(telefono_compartido=TEL_4B, usuario="u-4b")
    enviar("hay mucho olor a gas en el palier", usuario="u-4b")
    assert all(not chat.startswith("admin") for chat, _ in _enviados())
    assert any(d.startswith("admin:R4520") for _, d, _ in escritura.outbox_pendientes(get_conn()))
    at = app_logueada(APP).run()
    assert not at.exception
    assert any("no tiene un chat de avisos vinculado" in w.value for w in at.warning)
    assert any("sin vincular" in e.label for e in at.sidebar.expander)


def test_panel_genera_el_codigo(db_path):
    at = app_logueada(APP).run()
    at.button(key="codigo-avisos").click().run()
    assert not at.exception
    (instruccion,) = [m.value for m in at.sidebar.markdown if "/admin" in m.value]
    codigo = instruccion.split("/admin ")[1].strip("` \n")
    assert cuentas.vincular_chat_avisos(codigo, "chat-panel") == "Administración Méndez"


# ---------------------------------------------------------------- Chats separados de vecino y administración

# Scenario: Administradora que escribe consultas
def test_el_chat_de_avisos_no_da_acceso_a_datos(enviar):
    vincular_chat_demo("chat-u-laura")
    assert enviar("¿cuánto debo?", usuario="u-laura") == [textos.PEDIR_CONTACTO]
    assert enviar(telefono_compartido="+5491199990000", usuario="u-laura") == [textos.TELEFONO_NO_REGISTRADO]


# ---------------------------------------------------------------- tarea 5.5

def test_mediador_para_una_administracion_sin_criterios(otra):
    prompt = mediador.sistema("Administración Pérez")
    assert SIN_CRITERIOS in prompt and "Administración Pérez" in prompt
