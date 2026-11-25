"""La sesión de la cuenta de prueba de la demo, para los tests que usan el panel."""
from eliseo import cuentas
from scripts.seed_db import cuenta_demo


def sesion_demo() -> cuentas.Sesion:
    sesion = cuentas.autenticar(*cuenta_demo())
    assert sesion is not None, "la siembra no creó la cuenta de demo"
    return sesion


def app_logueada(ruta: str):
    """El panel (Streamlit AppTest) con la cuenta de demo ya logueada."""
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(ruta, default_timeout=30)
    at.session_state["admin_id"] = sesion_demo().admin_id
    return at
