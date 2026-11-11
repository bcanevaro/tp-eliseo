"""Registro de nodos reemplazables: el único archivo que tocás para enchufar tu implementación.

Para reemplazar un stub, cambiá su línea por tu función, p. ej.:

    from eliseo.agentes.documental import nodos as documental
    ...
    "documental": documental.documental,

La función tiene que respetar el mismo contrato que el stub (ver eliseo/grafo/stubs.py).
La estructura del grafo (qué nodo sigue a cuál) vive en conversacion.py y caso.py.
"""
from eliseo.agentes.documental import nodos as documental
from eliseo.grafo import stubs

NODOS_CONVERSACION = {
    # canal-telegram-intake
    "intake": stubs.intake,
    "completar_datos": stubs.completar_datos,
    # agente-documental
    "documental": documental.documental,
    "verificar_consulta": documental.verificar_consulta,
    "responder_reglamento": documental.responder_reglamento,
    # agente-gastos
    "gastos": stubs.gastos,
    "responder_gastos": stubs.responder_gastos,
    # panel-admin-ejecucion
    "avisar_urgencia": stubs.avisar_urgencia,
    "derivar_sin_fuente": stubs.derivar_sin_fuente,
    "hablar_con_admin": stubs.hablar_con_admin,
}

NODOS_CASO = {
    # agente-documental
    "documental_caso": documental.documental_caso,
    # flujo-reclamo-mediador
    "precedentes": stubs.precedentes,
    "mediador": stubs.mediador,
    "verificar_dictamen": stubs.verificar_dictamen,
    # panel-admin-ejecucion
    "ejecucion": stubs.ejecucion,
    "rechazo": stubs.rechazo,
}
