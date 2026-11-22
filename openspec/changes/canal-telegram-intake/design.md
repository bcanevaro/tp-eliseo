## Context

El bootstrap deja el grafo de conversación completo: identificar por teléfono vinculado, saludo con
botones, ruteo por intent, repregunta única y `outbox` para lo que sale fuera de turno. Faltan el
canal real (Telegram) y el intake con LLM. El panel ya deja en la outbox las resoluciones, los
avisos de urgencia y las respuestas manuales, y `ejecucion.enviar_pendientes(enviar)` las resuelve
a un chat.

## Goals / Non-Goals

**Goals:** bot de Telegram con vinculación del propio contacto, botones, "Hablar con la
administración" siempre visible, estado visible, fotos como evidencia y envío de la outbox; intake
con structured output, reintento y caída a reglas; recordatorio único a las 24 h y caso INCOMPLETO;
dataset del intake con métricas por intent y recall de urgencias.

**Non-Goals:** transcripción de audios (se pide el texto); WhatsApp (fase de piloto); grupos de
Telegram (el bot atiende chats individuales).

## Decisions

### D1. Lógica del canal separada del SDK de Telegram
`eliseo/canal/telegram.py` tiene lo testeable (normalizar teléfono, contacto propio, teclado, estado
visible) sin importar `python-telegram-bot`. `bot.py` solo conecta handlers. Los handlers también se
prueban con objetos falsos (sin red).

### D2. Un único hilo para el grafo
El bot es asíncrono, pero el grafo, SQLite y el checkpointer son sincrónicos y comparten conexión.
Todo el trabajo del grafo (mensajes, análisis de casos, outbox, seguimiento) corre en un
`ThreadPoolExecutor` de un solo hilo. *Alternativa descartada:* una conexión por hilo con
`AsyncSqliteSaver`; más cambios en el bootstrap para un volumen de demo.

### D3. El análisis del reclamo corre después de contestar
`runtime.procesar_mensaje` acepta `lanzar_caso`: el bot primero le manda al vecino "Registré tu
reclamo #N" y después corre el grafo de caso (Mediador incluido) en segundo plano.

### D4. Estado visible con el stream del grafo
`procesar_mensaje(al_avanzar=...)` usa `stream(stream_mode="updates")`; cuando termina el nodo
`intake`, el bot manda "Buscando en el reglamento…", "Revisando tu cuenta…" o "Registrando tu
reclamo…" según el intent principal.

### D5. Urgencia = LLM **o** palabras clave
El recall de urgencias tiene que ser 1, así que el resultado del LLM se combina con la lista de
palabras del bootstrap (gas, encerrado, humo, inundación, cables…). Además, ante una urgencia el
grafo ya no pide los datos del reclamo (ambiente, foto…) en el mismo turno: la administración ya
está avisada.

### D6. Intake: structured output, un reintento, después UNKNOWN; si el proxy cae, reglas
`with_structured_output(ResultadoIntake)` con el master prompt `prompts/intake.v1.md`. Si la salida
no valida, un reintento; si vuelve a fallar, UNKNOWN (spec). Si el proxy no responde, se usan las
reglas por palabras clave del bootstrap, así el bot sigue funcionando. `INTAKE_MODO=reglas` fija el
modo sin LLM (lo usan los tests).

### D7. Recordatorio y caso INCOMPLETO sin tabla nueva
`seguimiento.revisar()` recorre los vecinos vinculados, lee `reclamo_en_curso` y `ultimo_mensaje` del
checkpoint de su hilo y encola un único recordatorio (clave de idempotencia con la hora del último
mensaje) a las 24 h. A las 48 h registra el caso como INCOMPLETO (aparece en el panel) y lo saca del
hilo.

### D8. Modo demo
Los teléfonos de la base de demo son ficticios. Con `ELISEO_DEMO=1`, `/demo 4°B` vincula el Telegram
de quien lo escribe con el vecino ficticio de esa unidad. Apagado por defecto en producción.

## Risks / Trade-offs

- **Un solo hilo** → si el Mediador tarda, los mensajes de otros vecinos esperan. Aceptable en la demo.
- **Long polling** → el bot tiene que estar corriendo para recibir; en producción, webhook.
