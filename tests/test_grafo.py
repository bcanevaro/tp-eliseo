"""Test de humo de punta a punta con stubs (spec grafo-orquestacion). Sin LLM ni red."""
import pytest

from eliseo.grafo import runtime
from eliseo.plataforma import escritura
from eliseo.plataforma.db import get_conn
from eliseo.schemas import AccionAdmin, Adjunto, DecisionAdmin, EstadoCaso, MensajeEntrante

TEL_4B = "+5491100000402"


@pytest.fixture
def bot(db_path):
    """Envía mensajes como un usuario de Telegram ya vinculado al 4°B; devuelve los textos de respuesta."""
    runtime._grafos.cache_clear()
    runtime._checkpointer.cache_clear()

    def enviar(texto="", usuario="u-4b", **kw) -> list[str]:
        msg = MensajeEntrante(chat_id=f"chat-{usuario}", usuario_canal_id=usuario, texto=texto, **kw)
        return [s.texto for s in runtime.procesar_mensaje(msg)]

    enviar(telefono_compartido=TEL_4B)
    return enviar


def _derivaciones(tipo):
    return get_conn().execute("SELECT * FROM derivaciones WHERE tipo = ?", (tipo,)).fetchall()


def _reclamo_completo(bot) -> int:
    bot("Hay humedad en el techo del baño")
    bot("gotea desde hace una semana")
    (resp,) = bot(adjuntos=[Adjunto(tipo="foto", file_id="f1")])
    assert "#" in resp
    (caso_id,) = get_conn().execute("SELECT MAX(caso_id) FROM casos").fetchone()
    return caso_id


# Requirement: Identificación antes que todo
def test_pide_contacto_al_usuario_nuevo(db_path):
    msg = MensajeEntrante(chat_id="c", usuario_canal_id="nuevo", texto="hola")
    (salida,) = runtime.procesar_mensaje(msg)
    assert salida.pedir_contacto


def test_telefono_no_registrado_no_corre_intake(db_path, monkeypatch):
    llamado = []
    monkeypatch.setitem(runtime.grafo_conversacion.NODOS_CONVERSACION, "intake", lambda s: llamado.append(1) or {})
    runtime._grafos.cache_clear()
    msg = MensajeEntrante(chat_id="c", usuario_canal_id="x", texto="hola", telefono_compartido="+5491100009999")
    (salida,) = runtime.procesar_mensaje(msg)
    assert "no figura" in salida.texto and not llamado
    assert _derivaciones("telefono_no_registrado")


def test_saludo_con_nombre_y_unidad(bot):
    (saludo,) = bot()
    assert "Sofía" in saludo and "4°B" in saludo


# Requirement: Ruteo por intent decidido por el workflow
def test_consulta_con_cita(bot):
    (r,) = bot("¿Puedo tener un perro?")
    assert "REG-18" in r


def test_consulta_cita_el_acta_que_modifica(bot):
    (r,) = bot("¿Puedo poner un toldo en el balcón?")
    assert "REG-22" in r and "ACTA-2024-11-10#3" in r


def test_consulta_sin_fuente_deriva(bot):
    (r,) = bot("¿Puedo poner una pileta en la terraza?")
    assert "administración" in r and "Fuente" not in r
    assert _derivaciones("sin_fuente")


def test_gastos_con_montos_de_la_base(bot):
    (r,) = bot("¿Por qué subió la expensa de octubre?")
    assert "$ 615.000,00" in r and "FAC-0107" in r and "FAC-0108" in r


def test_multi_intent_responde_por_separado(bot):
    respuestas = bot("Se me llueve el baño y quiero saber cuánto se pagó de expensa")
    assert len(respuestas) == 2
    assert any("$" in r for r in respuestas) and any("reclamo" in r for r in respuestas)


def test_no_se_entiende_dos_veces(bot):
    (primera,) = bot("asdf qwer")
    (segunda,) = bot("zxcv")
    assert "entendido" in primera and "administración" in segunda
    assert len(_derivaciones("no_entendido")) == 1


# Requirement: Urgencias sin espera
def test_urgencia_avisa_y_da_emergencias(bot):
    (r,) = bot("hay mucho olor a gas en el palier")
    assert "911" in r
    destinos = [d for _, d, _ in escritura.outbox_pendientes(get_conn())]
    assert "admin:R4520" in destinos


# Requirement: Grafo de conversación por vecino — Scenario: Reclamo en varios mensajes (y reinicio)
def test_reclamo_en_varios_mensajes_sobrevive_reinicio(bot):
    (r,) = bot("Hay humedad")
    assert "ambiente" in r
    runtime._grafos.cache_clear()
    runtime._checkpointer.cache_clear()  # simula reiniciar el proceso
    (r,) = bot("en el baño, gotea desde hace una semana")
    assert "foto" in r


# Requirement: Grafo de caso con aprobación humana
def test_nada_sale_sin_decision(bot):
    caso_id = _reclamo_completo(bot)
    estado = runtime.estado_caso(caso_id)
    assert estado["siguiente"] == ("panel",)
    assert escritura.obtener_caso(get_conn(), caso_id).estado is EstadoCaso.PENDIENTE_APROBACION
    assert not [d for _, d, _ in escritura.outbox_pendientes(get_conn()) if d.startswith("vecino:")]


def test_vecino_escribe_mientras_el_caso_espera(bot):
    caso_id = _reclamo_completo(bot)
    (r,) = bot("¿Puedo tener un perro?")
    assert "REG-18" in r
    assert runtime.estado_caso(caso_id)["siguiente"] == ("panel",)


def test_corrida_de_punta_a_punta_hasta_ejecucion(bot):
    caso_id = _reclamo_completo(bot)
    final = runtime.retomar_caso(caso_id, DecisionAdmin(accion=AccionAdmin.APROBAR, admin_id="laura"))
    assert final["caso"].estado is EstadoCaso.APROBADO
    pedidos = get_conn().execute("SELECT tipo FROM pedidos WHERE caso_id = ?", (caso_id,)).fetchall()
    assert [p["tipo"] for p in pedidos] == ["inspeccion"]
    assert any(d == f"vecino:{TEL_4B}" for _, d, _ in escritura.outbox_pendientes(get_conn()))


def test_rechazo(bot):
    caso_id = _reclamo_completo(bot)
    final = runtime.retomar_caso(caso_id, DecisionAdmin(accion=AccionAdmin.RECHAZAR, admin_id="laura",
                                                        motivo="falta inspección previa"))
    assert final["caso"].estado is EstadoCaso.RECHAZADO
    (fila,) = get_conn().execute("SELECT motivo FROM decisiones WHERE caso_id = ?", (caso_id,)).fetchall()
    assert fila["motivo"] == "falta inspección previa"


def test_no_se_puede_retomar_un_caso_que_no_espera(bot):
    caso_id = _reclamo_completo(bot)
    runtime.retomar_caso(caso_id, DecisionAdmin(accion=AccionAdmin.APROBAR, admin_id="laura"))
    with pytest.raises(ValueError):
        runtime.retomar_caso(caso_id, DecisionAdmin(accion=AccionAdmin.APROBAR, admin_id="laura"))


# Requirement: Mensajes fuera de turno por outbox
def test_outbox_idempotente(conn):
    from eliseo.schemas import MensajeSaliente

    m = MensajeSaliente(texto="Resolución del caso 17")
    assert escritura.encolar_mensaje(conn, f"vecino:{TEL_4B}", m, clave="dictamen:17:vecino")
    assert not escritura.encolar_mensaje(conn, f"vecino:{TEL_4B}", m, clave="dictamen:17:vecino")
    assert len(escritura.outbox_pendientes(conn)) == 1


def test_respuesta_de_la_administracion_marcada(bot):
    caso_id = _reclamo_completo(bot)
    runtime.retomar_caso(caso_id, DecisionAdmin(accion=AccionAdmin.RECHAZAR, admin_id="laura", motivo="otro",
                                                mensaje_final="Lo revisamos y corresponde a tu unidad."))
    (mensaje,) = [m for _, d, m in escritura.outbox_pendientes(get_conn()) if d.startswith("vecino:")]
    assert mensaje.de_la_administracion


# Loop Mediador ⇄ verificador: máximo 2 vueltas y fallback a inspección
def test_mediador_con_citas_invalidas_pasa_a_inspeccion(bot, monkeypatch):
    from eliseo.grafo import stubs
    from eliseo.schemas import Hipotesis

    llamadas = []

    def mediador_que_inventa(state):
        llamadas.append(state.get("verificacion"))
        d = stubs.mediador(state)["dictamen"]
        d.hipotesis.append(Hipotesis(id="C", responsable="unidad", descripcion="inventada",
                                     citas=["REG-99"], confirmaria="x"))
        return {"dictamen": d}

    monkeypatch.setitem(runtime.grafo_caso.NODOS_CASO, "mediador", mediador_que_inventa)
    runtime._grafos.cache_clear()
    caso_id = _reclamo_completo(bot)
    dictamen = runtime.estado_caso(caso_id)["valores"]["dictamen"]
    assert len(llamadas) == 2 and llamadas[1]["fallas"][0]["cita"] == "REG-99"  # la 2.ª vuelta recibe los motivos
    assert "C" not in {h.id for h in dictamen.hipotesis}
    assert dictamen.recomendacion.tipo == "inspeccion"
