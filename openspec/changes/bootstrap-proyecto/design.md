## Context

El Discovery y el artefacto de Design definen qué es Eliseo y cómo se divide: tres agentes (Documental, Gastos, Mediador), un LLM step (Intake + Router), un workflow fijo para el reclamo, un approval boundary (panel) y el resto código. El repo está vacío de código y cinco personas van a trabajar en paralelo. El MVP de la materia usa Telegram como canal y Pinecone como base vectorial, igual que en los TPs individuales. No hay una plataforma de gestión real a la que conectarse, así que la simulamos.

## Goals / Non-Goals

**Goals:**
- Que cada integrante pueda implementar y testear su caja sin esperar a los demás.
- Que la integración sea reemplazar stubs, no reescribir interfaces.
- Que el grafo completo corra de punta a punta desde el día uno (con stubs y sin LLM).

**Non-Goals:**
- Implementar la lógica de ningún agente (es de los changes de cada integrante).
- WhatsApp, OCR de PDFs escaneados y transcripción de audio (fuera del MVP; ver Open Questions).
- Integración con una plataforma real (AdminProp, ConsorcioAbierto).

## Decisions

### D1. Layout del repo

```
eliseo/
  config.py          # lee .env, un solo lugar
  llm.py             # get_fast_model / get_model / get_reasoning_model / get_embeddings
  vectores.py        # cliente Pinecone + namespaces
  schemas/           # contratos compartidos (Pydantic)
  plataforma/        # SQLite que simula la plataforma: db.py, repos por entidad
  grafo/
    conversacion.py  # grafo por vecino
    caso.py          # grafo por reclamo, con interrupt
    stubs.py         # un stub determinístico por nodo
  canal/             # change canal-telegram-intake
  intake/            # change canal-telegram-intake
  agentes/documental|gastos|mediador/
  verificador/       # change agente-documental
  precedentes/       # change flujo-reclamo-mediador
  motor/             # change agente-gastos
  ejecucion/         # change panel-admin-ejecucion
panel/app.py         # Streamlit, change panel-admin-ejecucion
prompts/             # master prompts versionados + CHANGELOG.md
data/consorcios/rivadavia-4520/
evaluation/          # dataset de casos y scripts de LangSmith
scripts/             # seed_db.py, ingest.py
tests/
```
Cada integrante toca su carpeta y, si necesita cambiar un contrato, `eliseo/schemas/` en su change. Alternativa descartada: un repo por agente, porque es demasiada ceremonia para un TP y complica el grafo.

### D2. Dos grafos en lugar de uno
El grafo de conversación vive por vecino (`thread_id = telefono:consorcio_id`) y el de caso vive por reclamo (`thread_id = caso:<id>`). Si el reclamo corriera dentro del hilo del vecino, el `interrupt` del panel dejaría ese hilo bloqueado y el vecino no podría hacer otra consulta mientras espera. Alternativa descartada: un solo grafo con un subgrafo, que tiene el mismo problema de bloqueo.

### D3. Checkpointer SQLite compartido
El bot de Telegram y el panel de Streamlit son procesos distintos. Los dos usan `SqliteSaver` sobre el mismo archivo de checkpoints (`data/grafos.db`, separado de la base de la plataforma para que el esquema de LangGraph no se mezcle con el nuestro), así el panel puede retomar con `Command(resume=DecisionAdmin)` el grafo de caso que dejó el bot. `scripts/seed_db.py` borra los dos archivos juntos, porque los checkpoints quedarían apuntando a casos que ya no existen. Los contratos que viajan en el estado se registran explícitamente en el serializador (`allowed_msgpack_modules`), porque LangGraph va a bloquear los tipos no registrados. Alternativa descartada: `MemorySaver`, que no sobrevive entre procesos. Postgres sería lo correcto en producción, pero es infraestructura de más para el MVP.

### D4. Plataforma simulada en SQLite
Una sola base `data/eliseo.db` (gitignoreada, se regenera con `scripts/seed_db.py` desde `data/consorcios/*/plataforma.json`). El acceso pasa por repos en `eliseo/plataforma/`, que exponen solo consultas parametrizadas; ningún agente escribe SQL. Así el permiso "solo lectura, solo su unidad" de Gastos se impone en el repo y no en el prompt.

### D5. Pinecone: un índice, namespaces por tipo
Un índice `eliseo` (dense, 1536, cosine) con namespaces `documentos` y `precedentes`; el consorcio va como filtro de metadata `consorcio_id`. Para el retriever híbrido que pide el artefacto, el bootstrap recomienda (y `agente-documental` decide en su design):
- **Dense** en Pinecone.
- **BM25** local con `rank_bm25` sobre los chunks del consorcio (el corpus es chico: decenas de artículos), fusionado con RRF.
- **Rerank** con el reranker hospedado de Pinecone (`bge-reranker-v2-m3`, multilingüe), con la misma API key.
Alternativas: el índice sparse-dense de Pinecone necesita un encoder sparse propio y el modelo sparse hospedado de Pinecone está pensado para inglés.

### D6. Modelos por rol, por configuración
`LLM_MODEL_FAST` (intake y redacción, p. ej. `gpt-4.1-mini`), `LLM_MODEL` (Documental y Gastos, `gpt-4.1`) y `LLM_MODEL_REASONING` (Mediador). Los modelos de razonamiento rechazan `temperature`, así que `get_reasoning_model()` no la pasa. Todo con `with_structured_output` sobre los contratos.

### D7. Identidad en Telegram
Telegram no entrega el teléfono del usuario salvo que lo comparta. El canal (change `canal-telegram-intake`) pide una vez el contacto con el botón de "compartir número", guarda `usuario_canal_id → telefono` en la base, y desde ahí la `Identidad` se resuelve por código. El bootstrap solo deja la tabla y el repo.

### D8. Prompts como archivos versionados
`prompts/<nombre>.v<N>.md` y `prompts/CHANGELOG.md` con versión, fecha, cambio y por qué, como pide el artefacto. El código carga la versión que indica la config. Los motivos de rechazo del panel alimentan las versiones siguientes.

### D9. Outbox para los mensajes fuera de turno
Las respuestas del turno las devuelve `procesar_mensaje()` y el bot las manda en el acto. Lo que sale fuera de turno (la resolución de un caso que aprueba el panel, el aviso de urgencia al administrador, una respuesta manual) va a la tabla `outbox` con una clave de idempotencia, y el proceso del bot la vacía. Así el panel no necesita hablar con Telegram y aprobar dos veces no manda dos mensajes. Alternativa descartada: que el panel llame a la API de Telegram directamente, porque duplica la configuración del canal en dos procesos.

### D10. Registro de nodos reemplazables
La estructura de los grafos (qué sigue a qué) vive en `eliseo/grafo/conversacion.py` y `caso.py`, y la implementación de cada caja en `eliseo/grafo/nodos.py`, un diccionario `nombre → función` que arranca apuntando a los stubs de `stubs.py`. Cada integrante reemplaza solo sus líneas, así los merges no chocan. Los nodos de código propios del workflow (identificar, despachar, registrar caso, aprobación) no están en el registro.

## Risks / Trade-offs

- [Los contratos cambian a mitad de camino] → todo cambio a `eliseo/schemas/` va en un change revisado por el dueño del consumidor; los tests de contratos corren en cada PR.
- [Pinecone free tier: límite de índices] → un solo índice con namespaces.
- [El reranker hospedado de Pinecone no está disponible en el plan] → fallback a rerank con LLM rápido sobre los top-k.
- [SQLite con dos procesos escribiendo] → WAL mode activado; la carga es mínima.
- [El proxy del ITBA sin crédito] → el 10/11/2026 las cuentas de OpenAI y Anthropic del proxy devolvían "no credits remaining" (chat y embeddings). Pinecone sí respondía, incluidos sus modelos hospedados `multilingual-e5-large` (embeddings de 1024 dimensiones) y `bge-reranker-v2-m3`. Si el proxy sigue sin crédito, `agente-documental` puede usar los embeddings de Pinecone (con un índice de 1024 dimensiones); el resto de los agentes necesita el proxy.
- [Los stubs esconden problemas de integración] → test de humo de punta a punta en CI desde el día uno y reemplazo de stubs de a uno.

## Open Questions

- ¿Qué modelo de razonamiento está disponible en el proxy del ITBA para el Mediador? Definirlo en `flujo-reclamo-mediador`.
- ¿Entra audio en el MVP? Si sí, transcripción con Whisper vía el proxy, en `canal-telegram-intake`.
- ¿Documentos en PDF con OCR o directamente en texto? El bootstrap entrega texto (markdown por artículo); OCR queda fuera del MVP salvo que sobre tiempo.
