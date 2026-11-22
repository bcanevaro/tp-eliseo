"""Seguimiento de reclamos a medio completar (spec intake-router, "Sin respuesta en 24 horas").

Lo corre el bot cada tantos minutos:
- 24 h sin respuesta a un pedido de datos → un único recordatorio (outbox con clave).
- 24 h más sin respuesta → el reclamo se registra como INCOMPLETO (visible en el panel) y se
  saca del hilo, así el bot deja de pedir datos.
"""
from datetime import datetime, timedelta, timezone

from eliseo import textos
from eliseo.grafo import runtime
from eliseo.plataforma import escritura, lectura
from eliseo.plataforma.db import get_conn
from eliseo.schemas import Caso, EstadoCaso, MensajeSaliente

RECORDATORIO = timedelta(hours=24)
INCOMPLETO = timedelta(hours=48)

TEXTO_RECORDATORIO = ("Hola, quedó tu reclamo a medio cargar. {pregunta} "
                      "Si ya no hace falta, ignorá este mensaje.")
TEXTO_INCOMPLETO = ("Guardé tu reclamo como incompleto y se lo pasé a la administración. "
                    "Si querés completarlo, escribime cuando quieras.")


def revisar(ahora: datetime | None = None) -> dict:
    """Recorre los hilos de los vecinos vinculados. Devuelve cuántos recordatorios e incompletos hubo."""
    ahora, conn = ahora or datetime.now(timezone.utc), get_conn()
    conversacion, _ = runtime.grafos()
    resumen = {"recordatorios": 0, "incompletos": 0}
    for fila in conn.execute("SELECT DISTINCT telefono FROM vinculos_canal").fetchall():
        ident = lectura.identidad_por_telefono(conn, fila["telefono"])
        if ident is None:
            continue
        config = {"configurable": {"thread_id": f"{ident.telefono}:{ident.consorcio_id}"}}
        valores = conversacion.get_state(config).values
        borrador, ultimo = valores.get("reclamo_en_curso"), valores.get("ultimo_mensaje")
        if not borrador or not ultimo or not borrador.faltantes():
            continue
        quieto = ahora - ultimo
        clave = f"{ident.telefono}:{ultimo.isoformat()}"
        if quieto >= INCOMPLETO:
            escritura.registrar_caso(conn, Caso(consorcio_id=ident.consorcio_id, unidad_id=ident.unidad_id,
                                                       reclamo=borrador, estado=EstadoCaso.INCOMPLETO))
            conversacion.update_state(config, {"reclamo_en_curso": None})
            escritura.encolar_mensaje(conn, f"vecino:{ident.telefono}", MensajeSaliente(texto=TEXTO_INCOMPLETO),
                                      clave=f"incompleto:{clave}")
            resumen["incompletos"] += 1
        elif quieto >= RECORDATORIO:
            pregunta = textos.PREGUNTAS_RECLAMO[borrador.faltantes()[0].value]
            if escritura.encolar_mensaje(conn, f"vecino:{ident.telefono}",
                                         MensajeSaliente(texto=TEXTO_RECORDATORIO.format(pregunta=pregunta)),
                                         clave=f"recordatorio:{clave}"):
                resumen["recordatorios"] += 1
    return resumen
