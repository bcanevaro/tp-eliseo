## Why

Es la puerta de entrada: sin canal no hay demo, y sin un intake confiable el workflow rutea mal todo lo que viene después. El Discovery elige el chat que el vecino ya usa (sin app nueva) y para el MVP de la materia usamos Telegram. El intake fusiona el Triage y el Orquestador del Discovery en un solo LLM step que clasifica y extrae, pero no decide.

## What Changes

- Bot de Telegram que recibe texto y fotos, pide una vez el número de teléfono (botón de compartir contacto) y resuelve la unidad por código.
- Botones rápidos del primer mensaje (reclamo, reglamento, mis expensas) y "Hablar con la administración" siempre disponible.
- Indicador de estado visible ("Buscando en el reglamento…") mientras corre el grafo.
- Intake + Router: LLM step con structured output que produce `ResultadoIntake` (intent, multi, campos faltantes, urgencia y pregunta reescrita).
- Checklist de datos faltantes del reclamo (ambiente, foto, desde cuándo, si gotea), con recordatorio a las 24 horas y caso INCOMPLETO si no contesta.
- Reemplaza los stubs `identificar`, `intake` y `completar_datos` del bootstrap.

## Capabilities

### New Capabilities

- `canal-telegram`: recepción y envío de mensajes por Telegram, vinculación de teléfono, botones, indicador de estado y escape hacia la administración.
- `intake-router`: clasificación de intención, extracción del reclamo al schema, detección de urgencias y multi-intent, y repregunta.

### Modified Capabilities

(ninguna)

## Impact

- **Dueño:** Integrante A.
- **Depende de:** `bootstrap-proyecto` (contratos, grafo de conversación y base).
- **Origen:** cajas "Canal" e "Intake + Router" del artefacto; pasos 01 a 04 y 09 a 11 del Target State Workflow; wireframes del chat.
- **Dependencias nuevas:** `python-telegram-bot`. Variable `TELEGRAM_BOT_TOKEN` (bot creado con BotFather).
- **Evaluación:** el intake se evalúa como clasificador (precision y recall por intent) con un dataset propio en LangSmith.
