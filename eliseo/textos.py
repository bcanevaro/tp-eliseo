"""Textos fijos del bot (los que no escribe un LLM)."""

BOTON_RECLAMO = "Hacer un reclamo"
BOTON_REGLAMENTO = "Consultar el reglamento"
BOTON_EXPENSAS = "Mis expensas"
BOTON_HABLAR = "Hablar con la administración"

BOTONES_INICIO = [BOTON_RECLAMO, BOTON_REGLAMENTO, BOTON_EXPENSAS, BOTON_HABLAR]

PEDIR_CONTACTO = (
    "Hola, soy Eliseo, el asistente de la administración de tu consorcio. "
    "Para saber de qué unidad sos, necesito tu número: tocá el botón para compartirlo."
)
TELEFONO_NO_REGISTRADO = (
    "Tu número no figura en el registro de la administración. Le pedí que lo valide y te "
    "avisamos por acá. Mientras tanto no puedo mostrarte datos del consorcio."
)
SALUDO = "Hola, {nombre} ({unidad}). Soy Eliseo, el asistente de la administración. ¿En qué te ayudo?"
DERIVADO_SIN_FUENTE = (
    "No encontré nada en el reglamento ni en las actas que responda eso, así que no quiero "
    "contestarte sin fuente. Le pasé tu consulta a la administración y te responden por acá."
)
DERIVADO_HABLAR = "Listo, le aviso a la administración para que te contacte una persona por acá."
REPREGUNTA = "No estoy seguro de haberte entendido. ¿Me decís si es alguna de estas?"
DERIVADO_NO_ENTENDIDO = (
    "Perdón, no logro entenderte. Le pasé tu mensaje a la administración para que te responda una persona."
)
URGENCIA = (
    "Esto parece una urgencia: ya le avisé a la administración. Si hay riesgo para alguien, "
    "llamá ahora: {telefono_emergencias}."
)
CASO_REGISTRADO = (
    "Registré tu reclamo con el número #{caso_id}. La administración lo va a revisar y te "
    "avisamos por acá con la respuesta y su fundamento."
)

PREGUNTAS_RECLAMO = {
    "ambiente": "¿En qué ambiente es? (baño, cocina, living…)",
    "foto": "¿Me mandás una foto?",
    "desde_cuando": "¿Desde cuándo pasa?",
    "gotea": "¿Gotea o es solo una mancha?",
}
