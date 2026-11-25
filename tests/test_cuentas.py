"""Tests de la spec cuentas-admin (change cuentas-administracion)."""
from pathlib import Path

import pytest

from eliseo import cuentas
from eliseo.panel import servicio
from eliseo.plataforma import escritura
from eliseo.plataforma.db import conectar, crear_esquema, get_conn
from eliseo.schemas import AccionAdmin, Caso, ReclamoBorrador
from scripts.seed_db import cuenta_demo
from tests.cuentas_demo import app_logueada, sesion_demo

APP = str(Path(__file__).resolve().parent.parent / "eliseo" / "panel" / "app.py")
OTRA_EMAIL, OTRA_PASSWORD = "admin@otra.eliseo.test", "otra-clave-123"


def _app_de(admin_id: int):
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(APP, default_timeout=30)
    at.session_state["admin_id"] = admin_id
    return at


@pytest.fixture
def otra_administracion(db_path):
    """Una segunda administración con su edificio, un vecino, un caso y una derivación."""
    conn = get_conn()
    aid = cuentas.crear_administracion("Administración Pérez", conn)
    cuentas.crear_administrador(aid, OTRA_EMAIL, "Pedro Pérez", OTRA_PASSWORD, conn)
    conn.execute("""INSERT INTO consorcios (consorcio_id, nombre, direccion, administracion, administradora,
                                            telefono_emergencias, administracion_id)
                    VALUES ('C1200', 'Consorcio Corrientes 1200', 'Corrientes 1200', 'Administración Pérez',
                            'Pedro Pérez', '911', ?)""", (aid,))
    conn.execute("INSERT INTO unidades VALUES ('C1200-1A', 'C1200', '1°A', 1, 'A', '1.0000')")
    conn.execute("INSERT INTO vecinos VALUES ('+5491100009901', 'C1200-1A', 'Ana Otra')")
    caso = escritura.registrar_caso(conn, Caso(consorcio_id="C1200", unidad_id="C1200-1A",
                                               reclamo=ReclamoBorrador(descripcion="Humedad en el living")))
    der = escritura.crear_derivacion(conn, "sin_fuente", "¿Puedo tener una pileta?", consorcio_id="C1200",
                                     unidad_id="C1200-1A", telefono="+5491100009901")
    return {"administracion_id": aid, "caso_id": caso.caso_id, "derivacion_id": der}


# ---------------------------------------------------------------- Login obligatorio en el panel

# Scenario: Ingreso correcto
def test_ingreso_correcto_ve_solo_sus_consorcios(otra_administracion):
    sesion = cuentas.autenticar(*cuenta_demo())
    assert sesion.administracion == "Administración Méndez"
    assert [c["consorcio_id"] for c in servicio.consorcios(sesion)] == ["R4520"]


def test_email_sin_distinguir_mayusculas(db_path):
    email, password = cuenta_demo()
    assert cuentas.autenticar(f"  {email.upper()} ", password) is not None


# Scenario: Contraseña incorrecta
def test_contrasena_incorrecta_y_email_inexistente_dan_lo_mismo(db_path):
    email, _ = cuenta_demo()
    assert cuentas.autenticar(email, "otra-cosa") is None
    assert cuentas.autenticar("nadie@eliseo.test", "otra-cosa") is None
    assert cuentas.autenticar(email, "") is None


# Scenario: Sin sesión
def test_panel_sin_sesion_muestra_solo_el_ingreso(db_path):
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert [t.value for t in at.text_input] == ["", ""]  # email y contraseña
    assert not any("Bandeja" in s.value for s in at.subheader)
    assert not at.sidebar.selectbox


def test_panel_ingreso_por_formulario(db_path):
    from streamlit.testing.v1 import AppTest

    email, password = cuenta_demo()
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.text_input(key="login-email").set_value(email)
    at.text_input(key="login-password").set_value("mal")
    at.button[0].click().run()
    assert any(cuentas.ERROR_LOGIN in e.value for e in at.error)
    at.text_input(key="login-password").set_value(password)
    at.button[0].click().run()
    assert not at.exception
    assert any("Bandeja" in s.value for s in at.subheader)


# ---------------------------------------------------------------- Cierre de sesión

def test_cerrar_sesion(db_path):
    at = app_logueada(APP).run()
    assert any("Bandeja" in s.value for s in at.subheader)
    at.button(key="logout").click().run()
    assert not any("Bandeja" in s.value for s in at.subheader)
    at.run()  # recargar
    assert not any("Bandeja" in s.value for s in at.subheader)


# ---------------------------------------------------------------- Aislamiento por administración

# Scenario: Caso de otra administración
def test_caso_de_otra_administracion_no_existe(otra_administracion):
    sesion, caso_id = sesion_demo(), otra_administracion["caso_id"]
    with pytest.raises(servicio.NoEncontrado, match="No existe el caso"):
        servicio.detalle_caso(sesion, caso_id)
    with pytest.raises(servicio.NoEncontrado, match="No existe el caso"):
        servicio.decidir(sesion, caso_id, servicio.armar_decision(AccionAdmin.APROBAR, sesion))
    assert get_conn().execute("SELECT COUNT(*) FROM decisiones").fetchone()[0] == 0
    # El mismo mensaje que un caso que no existe en ningún lado.
    with pytest.raises(servicio.NoEncontrado, match="No existe el caso"):
        servicio.detalle_caso(sesion, 99999)


def test_derivacion_y_consorcio_de_otra_administracion(otra_administracion):
    sesion, der_id = sesion_demo(), otra_administracion["derivacion_id"]
    for llamada in (lambda: servicio.derivacion(sesion, der_id),
                    lambda: servicio.responder_derivacion(sesion, der_id, "hola"),
                    lambda: servicio.descartar_derivacion(sesion, der_id),
                    lambda: servicio.bandeja(sesion, "C1200"),
                    lambda: servicio.historial(sesion, "C1200"),
                    lambda: servicio.vecinos(sesion, "C1200")):
        with pytest.raises(servicio.NoEncontrado):
            llamada()
    assert get_conn().execute("SELECT estado FROM derivaciones WHERE id = ?", (der_id,)).fetchone()[0] == "pendiente"
    assert get_conn().execute("SELECT COUNT(*) FROM outbox").fetchone()[0] == 0


# Scenario: Selector de consorcio
def test_selector_ofrece_exactamente_sus_consorcios(otra_administracion):
    otra = cuentas.autenticar(OTRA_EMAIL, OTRA_PASSWORD)
    assert [c["consorcio_id"] for c in servicio.consorcios(otra)] == ["C1200"]
    assert [c["consorcio_id"] for c in servicio.consorcios(sesion_demo())] == ["R4520"]
    assert servicio.bandeja(otra, "C1200")["sin_fuente"]


def test_panel_de_otra_administracion(otra_administracion):
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(APP, default_timeout=30)
    at.session_state["admin_id"] = cuentas.autenticar(OTRA_EMAIL, OTRA_PASSWORD).admin_id
    at.run()
    assert not at.exception
    assert at.sidebar.selectbox[0].options == ["Consorcio Corrientes 1200"]


# ---------------------------------------------------------------- Decisión firmada por la cuenta

# El scenario "Autor de una aprobación" está en test_panel_ejecucion.py (necesita un caso esperando decisión).


def test_panel_no_pide_quien_decide(db_path):
    at = app_logueada(APP).run()
    assert not any(t.label == "Quién decide" for t in at.sidebar.text_input)


# ---------------------------------------------------------------- Alta de cuentas

def test_cuenta_nueva_sin_consorcios(db_path):
    conn = get_conn()
    aid = cuentas.crear_administracion("Administración Nueva", conn)
    cuentas.crear_administrador(aid, "nueva@eliseo.test", "Nora Nueva", "clave-segura-1", conn)
    sesion = cuentas.autenticar("nueva@eliseo.test", "clave-segura-1")
    assert sesion.administracion_id == "administracion-nueva" and servicio.consorcios(sesion) == []

    at = _app_de(sesion.admin_id).run()
    assert not at.exception
    assert any("todavía no tiene edificios" in i.value for i in at.sidebar.info)


def test_alta_rechaza_duplicados_y_contrasenas_cortas(db_path):
    conn = get_conn()
    with pytest.raises(ValueError, match="Ya existe"):
        cuentas.crear_administrador("administracion-mendez", cuenta_demo()[0], "Otra", "clave-segura-1", conn)
    with pytest.raises(ValueError, match="8 caracteres"):
        cuentas.crear_administrador("administracion-mendez", "x@eliseo.test", "X", "corta", conn)
    with pytest.raises(KeyError):
        cuentas.crear_administrador("no-existe", "y@eliseo.test", "Y", "clave-segura-1", conn)


def test_sesion_de_una_cuenta_borrada_deja_de_valer(db_path):
    sesion = sesion_demo()
    get_conn().execute("DELETE FROM administradores WHERE admin_id = ?", (sesion.admin_id,))
    assert cuentas.sesion_de(sesion.admin_id) is None


# ---------------------------------------------------------------- migración de bases viejas

def test_base_vieja_queda_con_su_administracion(tmp_path):
    """Una base creada antes del change (consorcios sin administracion_id) se migra sola."""
    import sqlite3

    vieja = tmp_path / "vieja.db"
    c = sqlite3.connect(vieja)
    c.execute("""CREATE TABLE consorcios (consorcio_id TEXT PRIMARY KEY, nombre TEXT NOT NULL, direccion TEXT NOT NULL,
                 administracion TEXT NOT NULL, administradora TEXT NOT NULL, telefono_emergencias TEXT NOT NULL)""")
    c.execute("INSERT INTO consorcios VALUES ('R4520', 'Rivadavia', 'Riv 4520', 'Administración Méndez', 'Laura', '911')")
    c.commit()
    c.close()

    conn = conectar(vieja)
    crear_esquema(conn)
    fila = conn.execute("SELECT administracion_id, activo FROM consorcios").fetchone()
    assert tuple(fila) == ("administracion-mendez", 1)
    assert conn.execute("SELECT nombre FROM administraciones").fetchone()[0] == "Administración Méndez"
    crear_esquema(conn)  # idempotente
    assert conn.execute("SELECT COUNT(*) FROM administraciones").fetchone()[0] == 1
    conn.close()


# ---------------------------------------------------------------- script de alta

# Scenario: Alta de una administración nueva
def test_script_de_alta(db_path, capsys):
    from scripts.alta_administracion import main

    assert main(["Administración Gómez", "Gaby@Eliseo.test", "Gaby Gómez", "--password", "clave-segura-2"]) == 0
    assert "administracion-gomez" in capsys.readouterr().out
    sesion = cuentas.autenticar("gaby@eliseo.test", "clave-segura-2")
    assert sesion.administracion == "Administración Gómez" and servicio.consorcios(sesion) == []
    # Una segunda cuenta en la misma administración no la duplica.
    assert main(["Administración Gómez", "otro@eliseo.test", "Otro", "--password", "clave-segura-3"]) == 0
    assert get_conn().execute("SELECT COUNT(*) FROM administraciones WHERE nombre = 'Administración Gómez'").fetchone()[0] == 1
    # Repetir el email falla sin romper nada.
    assert main(["Administración Gómez", "gaby@eliseo.test", "Gaby", "--password", "clave-segura-2"]) == 1


# ---------------------------------------------------------------- RLS (design D5), solo en Postgres

def test_rol_anon_no_lee_ninguna_tabla(db_path):
    """Simula la clave pública de Supabase: el rol `anon`, aun con permiso de SELECT, no ve filas."""
    conn = get_conn()
    if conn.dialecto != "postgresql":
        pytest.skip("RLS solo existe en Postgres (corre en el job tests-postgres del CI)")
    conn.execute("DO $$ BEGIN CREATE ROLE anon NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$")
    conn.execute("GRANT USAGE ON SCHEMA public TO anon")
    conn.execute("GRANT SELECT ON vecinos, administradores, consorcios TO anon")
    with conn.engine.connect() as c:
        from sqlalchemy import text

        c.execute(text("SET ROLE anon"))
        for tabla in ("vecinos", "administradores", "consorcios"):
            assert c.execute(text(f"SELECT COUNT(*) FROM {tabla}")).scalar() == 0
        c.execute(text("RESET ROLE"))
    assert conn.execute("SELECT COUNT(*) FROM vecinos").fetchone()[0] == 12  # el backend sí ve todo
