## Why

El repo solo tiene el Discovery y somos cinco personas que van a implementar en paralelo cinco piezas de la arquitectura. Si cada una define sus propios tipos, sus propios datos de prueba y su propia forma de enchufarse al grafo, la integración va a fallar al final. Este change fija lo que todos comparten (stack, contratos de datos, datos ficticios y esqueleto del grafo) antes de que arranque el trabajo en paralelo.

## What Changes

- Estructura del repo como paquete Python (`eliseo/`), con entorno uv en Python 3.12, `.env.example` y `requirements.txt`.
- Clientes compartidos: LLM vía proxy LiteLLM (modelo rápido, principal y de razonamiento), embeddings y Pinecone.
- Contratos de datos en Pydantic para todo lo que cruza una frontera entre componentes: mensaje entrante, identidad del vecino, resultado del intake, cita, respuestas de Documental y Gastos, caso, dictamen y decisión del administrador.
- Datos ficticios del Consorcio Rivadavia 4520: reglamento, actas, unidades, teléfonos, cuentas corrientes, liquidaciones, facturas y precedentes, cargados en un SQLite que simula la plataforma de gestión.
- Esqueleto de los dos grafos de LangGraph (conversación y caso), con todos los nodos como stubs que respetan los contratos, para que cada integrante reemplace el suyo sin tocar el de los demás.
- Los master prompts v1 del artefacto (respuestas al vecino y Mediador) versionados en `prompts/`.
- Los 12 casos de test del artefacto como dataset en `evaluation/`.

## Capabilities

### New Capabilities

- `contratos-compartidos`: los schemas Pydantic que cruzan las fronteras entre componentes y las reglas de validación que todos respetan.
- `datos-ficticios`: el corpus y la base del consorcio de demo, con los casos que necesitan los tests (artículo modificado por un acta, teléfono no registrado, suba de expensas explicable, precedente en la misma columna).
- `grafo-orquestacion`: el ruteo por intent, los dos grafos (conversación por vecino y caso por reclamo), el `thread_id`, la persistencia y las ramas de abstención, urgencia y repregunta.

### Modified Capabilities

(ninguna: es el primer change del repo)

## Impact

- **Dueño:** Bruno.
- **Depende de:** nada. **Bloquea a:** `canal-telegram-intake`, `agente-documental`, `agente-gastos`, `flujo-reclamo-mediador` y `panel-admin-ejecucion`, que arrancan cuando este change se mergea.
- **Origen:** pestaña Arquitectura del artefacto (cajas y contratos), Target State Workflow y Master prompt y tests; DISCOVERY §5 y §6.
- **Dependencias nuevas:** langgraph, langgraph-checkpoint-sqlite, langchain-openai, langchain-pinecone, pinecone, pydantic, python-dotenv, langsmith, pytest. Las del canal y el panel las suma cada change.
- **Cuentas:** cada integrante necesita la clave del proxy del ITBA, una API key de Pinecone (o la compartida del grupo) y LangSmith. El token del bot de Telegram lo agrega `canal-telegram-intake`.
