## 1. Canal de Telegram

- [x] 1.1 `eliseo/canal/telegram.py`: teléfono, contacto propio, teclado con "Hablar con la administración", estado visible
- [x] 1.2 `eliseo/canal/bot.py`: /start, contacto, texto, fotos (se descargan a `data/fotos`), audios, /chatid, /demo
- [x] 1.3 Un único hilo para el grafo; análisis del caso después de contestar (`lanzar_caso`)
- [x] 1.4 Vaciar la outbox cada 3 s con `ejecucion.enviar_pendientes`
- [x] 1.5 `python-telegram-bot` en `requirements.txt` y servicio `bot` en `docker-compose.yml`

## 2. Intake + Router

- [x] 2.1 Master prompt `prompts/intake.v1.md` y entrada con el mensaje y el reclamo en curso como dato
- [x] 2.2 Structured output, un reintento y UNKNOWN; caída a reglas si el proxy falla; `INTAKE_MODO`
- [x] 2.3 Urgencia por LLM o palabras clave; el grafo no pide datos del reclamo ante una urgencia
- [x] 2.4 Reemplazar el stub `intake` en `nodos.py` (`completar_datos` queda como código puro)

## 3. Seguimiento

- [x] 3.1 `eliseo/canal/seguimiento.py`: recordatorio único a las 24 h y caso INCOMPLETO a las 48 h

## 4. Tests y evaluación

- [x] 4.1 `tests/test_canal_intake.py`: scenarios de `canal-telegram` e `intake-router`, handlers con Telegram falso e intake con LLM falso
- [x] 4.2 Dataset `evaluation/intake/mensajes.jsonl` (44 mensajes: multi-intent, urgencias, fuera de dominio, inyecciones)
- [x] 4.3 `evaluation/intake/eval_intake.py`: precision y recall por intent, recall de urgencias, `--langsmith`
- [ ] 4.4 Correr con el proxy real y anotar los resultados (el recall de urgencias tiene que dar 1)
- [ ] 4.5 Probar el bot de punta a punta en Telegram (vincular, consulta, reclamo con foto, aprobación en el panel)
