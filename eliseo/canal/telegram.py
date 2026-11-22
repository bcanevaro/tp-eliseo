"""Traducción entre Telegram y los contratos del grafo (spec canal-telegram). Sin red.

El bot (`bot.py`) solo mueve mensajes; acá está lo que se testea: cómo se arma el
`MensajeEntrante`, cuándo se acepta un contacto, qué teclado ve el vecino y qué estado se
muestra mientras corre el grafo.
"""
import re

from eliseo import textos
from eliseo.schemas import Intent, MensajeSaliente

TEXTOS_ESTADO = {
    Intent.REGLAMENTO: "🔎 Buscando en el reglamento…",
    Intent.GASTOS: "📒 Revisando tu cuenta…",
    Intent.RECLAMO: "📝 Registrando tu reclamo…",
}
CONTACTO_AJENO = ("Ese contacto no es el tuyo. Para identificar tu unidad necesito tu propio número: "
                  "tocá el botón para compartirlo.")
AUDIO_NO_SOPORTADO = "Por ahora no puedo escuchar audios. ¿Me lo escribís?"
BOTON_CONTACTO = "📱 Compartir mi número"


def normalizar_telefono(numero: str) -> str:
    """Telegram manda el número con o sin '+', a veces con espacios: '549 11…' → '+54911…'."""
    return "+" + re.sub(r"\D", "", numero)


def contacto_propio(contact_user_id: int | None, from_user_id: int) -> bool:
    """Solo vale el contacto que comparte el propio usuario con el botón (no uno reenviado)."""
    return contact_user_id is not None and contact_user_id == from_user_id


def estado_visible(nodo: str, actualizacion: dict | None) -> str | None:
    """Texto de estado después del intake, según el intent principal (o None si no corresponde)."""
    if nodo != "intake" or not actualizacion or not actualizacion.get("intake"):
        return None
    r = actualizacion["intake"]
    if r.urgencia:
        return None  # la respuesta de urgencia sale enseguida
    return TEXTOS_ESTADO.get(r.intent)


def botones(m: MensajeSaliente) -> list[list[str]]:
    """Filas del teclado: los botones del mensaje y, siempre, "Hablar con la administración"."""
    if m.pedir_contacto:
        return [[BOTON_CONTACTO]]
    filas = [[b] for b in m.botones if b != textos.BOTON_HABLAR]
    return [*filas, [textos.BOTON_HABLAR]]


def texto_saliente(m: MensajeSaliente) -> str:
    return f"👤 Administración:\n{m.texto}" if m.de_la_administracion else m.texto
