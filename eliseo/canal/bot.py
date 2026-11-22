"""Bot de Telegram de Eliseo (spec canal-telegram). Correr con:

    python -m eliseo.canal.bot

Necesita TELEGRAM_BOT_TOKEN en el .env. Comandos:
    /start          saluda (o pide el número la primera vez)
    /chatid         devuelve el id del chat (para TELEGRAM_CHAT_ADMIN_ID)
    /demo 4°B       solo con ELISEO_DEMO=1: vincula tu Telegram con un vecino de demo de esa unidad

Todo el trabajo del grafo corre en un único hilo de fondo (SQLite y los checkpoints no se
comparten entre hilos a la vez). Además, cada pocos segundos el bot vacía la outbox
(resoluciones aprobadas en el panel, avisos de urgencia, respuestas manuales) y cada 10
minutos revisa los reclamos a medio completar.
"""
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from telegram import KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from eliseo import ejecucion
from eliseo.canal import seguimiento
from eliseo.canal.telegram import (
    AUDIO_NO_SOPORTADO,
    BOTON_CONTACTO,
    CONTACTO_AJENO,
    botones,
    contacto_propio,
    estado_visible,
    normalizar_telefono,
    texto_saliente,
)
from eliseo.config import DATA_DIR, env
from eliseo.grafo import runtime
from eliseo.plataforma.db import get_conn
from eliseo.schemas import Adjunto, MensajeEntrante, MensajeSaliente

log = logging.getLogger("eliseo.bot")
EJECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="grafo")
FOTOS_DIR = DATA_DIR / "fotos"
CADA_OUTBOX_S = 3
CADA_SEGUIMIENTO_S = 600


def teclado(m: MensajeSaliente) -> ReplyKeyboardMarkup:
    filas = [[KeyboardButton(b, request_contact=(b == BOTON_CONTACTO)) for b in fila] for fila in botones(m)]
    return ReplyKeyboardMarkup(filas, resize_keyboard=True, one_time_keyboard=m.pedir_contacto)


async def en_hilo(fn, *args):
    return await asyncio.get_running_loop().run_in_executor(EJECUTOR, fn, *args)


async def responder(update: Update, context: ContextTypes.DEFAULT_TYPE, msg: MensajeEntrante) -> None:
    loop = asyncio.get_running_loop()
    chat_id = update.effective_chat.id
    await context.bot.send_chat_action(chat_id, ChatAction.TYPING)

    def al_avanzar(nodo, actualizacion):
        if texto := estado_visible(nodo, actualizacion):
            asyncio.run_coroutine_threadsafe(context.bot.send_message(chat_id, texto), loop)

    casos = []
    salidas = await en_hilo(lambda: runtime.procesar_mensaje(msg, al_avanzar, lambda c, t: casos.append((c, t))))
    for s in salidas:
        await context.bot.send_message(chat_id, texto_saliente(s), reply_markup=teclado(s))
    for caso_id, telefono in casos:  # el análisis del reclamo corre después de contestar
        loop.run_in_executor(EJECUTOR, analizar_caso, caso_id, telefono)


def analizar_caso(caso_id: int, telefono: str) -> None:
    try:
        runtime.iniciar_caso(caso_id, telefono)
        log.info("Caso %s listo para el panel", caso_id)
    except Exception:  # noqa: BLE001 — el caso queda EN_ANALISIS y se ve en el historial del panel
        log.exception("Falló el análisis del caso %s", caso_id)


def _base(update: Update, **kw) -> MensajeEntrante:
    return MensajeEntrante(chat_id=str(update.effective_chat.id), usuario_canal_id=str(update.effective_user.id), **kw)


async def on_texto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await responder(update, context, _base(update, texto=update.message.text or ""))


async def on_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await responder(update, context, _base(update))


async def on_contacto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    c = update.message.contact
    if not contacto_propio(c.user_id, update.effective_user.id):
        await update.message.reply_text(CONTACTO_AJENO, reply_markup=teclado(MensajeSaliente(texto="", pedir_contacto=True)))
        return
    await responder(update, context, _base(update, telefono_compartido=normalizar_telefono(c.phone_number)))


async def on_foto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    foto = update.message.photo[-1]  # la de mayor resolución
    FOTOS_DIR.mkdir(parents=True, exist_ok=True)
    ruta = FOTOS_DIR / f"{foto.file_unique_id}.jpg"
    try:
        await (await context.bot.get_file(foto.file_id)).download_to_drive(ruta)
    except Exception:  # noqa: BLE001 — sin la copia local, igual queda el file_id
        log.exception("No se pudo descargar la foto")
        ruta = None
    adjunto = Adjunto(tipo="foto", file_id=foto.file_id, ruta_local=str(ruta) if ruta else None, mime="image/jpeg")
    await responder(update, context, _base(update, texto=update.message.caption or "", adjuntos=[adjunto]))


async def on_audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(AUDIO_NO_SOPORTADO)


async def on_chatid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f"El id de este chat es {update.effective_chat.id}.\n"
                                    "Para recibir acá las urgencias: TELEGRAM_CHAT_ADMIN_ID=" f"{update.effective_chat.id}")


async def on_demo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Para la demo: tu Telegram pasa a ser el vecino de demo de la unidad que digas."""
    if env("ELISEO_DEMO", default="0") != "1":
        await update.message.reply_text("El modo demo está apagado (ELISEO_DEMO=1 en el .env).")
        return
    pedida = "".join(context.args).upper().replace("°", "").replace("º", "")
    fila = await en_hilo(lambda: get_conn().execute(
        "SELECT v.telefono, u.unidad FROM vecinos v JOIN unidades u USING (unidad_id) "
        "WHERE REPLACE(UPPER(u.unidad), '°', '') = ? LIMIT 1", (pedida,)).fetchone())
    if not fila:
        await update.message.reply_text("Decime una unidad del consorcio de demo, por ejemplo: /demo 4°B")
        return
    await responder(update, context, _base(update, telefono_compartido=fila["telefono"]))


async def loop_outbox(app: Application) -> None:
    loop = asyncio.get_running_loop()

    def enviar(chat_id: str, m: MensajeSaliente) -> None:
        futuro = asyncio.run_coroutine_threadsafe(
            app.bot.send_message(int(chat_id), texto_saliente(m), reply_markup=teclado(m)), loop)
        futuro.result(timeout=15)

    while True:
        try:
            if n := await en_hilo(ejecucion.enviar_pendientes, enviar):
                log.info("Outbox: %d mensajes enviados", n)
        except Exception:  # noqa: BLE001 — el loop no se cae por un error de envío
            log.exception("Error vaciando la outbox")
        await asyncio.sleep(CADA_OUTBOX_S)


async def loop_seguimiento(app: Application) -> None:
    while True:
        try:
            r = await en_hilo(seguimiento.revisar)
            if any(r.values()):
                log.info("Seguimiento: %s", r)
        except Exception:  # noqa: BLE001
            log.exception("Error en el seguimiento de reclamos")
        await asyncio.sleep(CADA_SEGUIMIENTO_S)


async def al_iniciar(app: Application) -> None:
    app.create_task(loop_outbox(app))
    app.create_task(loop_seguimiento(app))
    yo = await app.bot.get_me()
    log.info("Bot @%s listo", yo.username)


def construir_app(token: str) -> Application:
    app = Application.builder().token(token).post_init(al_iniciar).build()
    app.add_handler(CommandHandler("start", on_start))
    app.add_handler(CommandHandler("chatid", on_chatid))
    app.add_handler(CommandHandler("demo", on_demo))
    app.add_handler(MessageHandler(filters.CONTACT, on_contacto))
    app.add_handler(MessageHandler(filters.PHOTO, on_foto))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, on_audio))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_texto))
    return app


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    construir_app(env("TELEGRAM_BOT_TOKEN")).run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
