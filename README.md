# Eliseo

Asistente multiagente para consorcios de propiedad horizontal. TP grupal de Sistemas Multiagentes I (72.79, ITBA).

- Qué es y por qué: [DISCOVERY.md](DISCOVERY.md).
- Cómo está dividido: el artefacto de arquitectura (Design) y las specs en [`openspec/`](openspec/).

## Trabajamos con specs (OpenSpec)

Nada se implementa sin un change aprobado. Cada change vive en `openspec/changes/<nombre>/` y tiene:

| Archivo | Qué dice | Quién lo escribe |
|---|---|---|
| `proposal.md` | Por qué y qué cambia | Quien propone |
| `specs/<capability>/spec.md` | Requisitos con escenarios WHEN/THEN, testeables | Quien propone |
| `design.md` | Cómo, con las decisiones y sus alternativas | El dueño del change |
| `tasks.md` | Checklist de implementación | El dueño del change |

El contexto y las reglas del proyecto, que leen todos los asistentes de IA, están en [`openspec/config.yaml`](openspec/config.yaml).

### Ciclo de un change

1. **Proponer:** `openspec new change <nombre>` (o `/opsx:propose` en Claude Code o Cursor) en una branch con el mismo nombre.
2. **Revisar antes de codear:** se abre el PR solo con los artefactos; otro integrante revisa proposal, specs y design.
3. **Implementar:** `/opsx:apply`, marcando las tasks a medida que se completan.
4. **Validar:** `openspec validate <nombre> --strict` y `pytest`.
5. **Archivar al mergear:** `openspec archive <nombre>` mueve las specs a `openspec/specs/`, que pasa a ser la fuente de verdad.

Comandos útiles: `openspec list`, `openspec view`, `openspec show <nombre>`, `openspec status --change <nombre>`.

### Changes y dueños

| Change | Capabilities | Dueño | Depende de |
|---|---|---|---|
| `bootstrap-proyecto` | contratos-compartidos, datos-ficticios, grafo-orquestacion | Bruno | — |
| `canal-telegram-intake` | canal-telegram, intake-router | A | bootstrap |
| `agente-documental` | ingesta-documental, agente-documental, verificador-citas | B | bootstrap |
| `agente-gastos` | agente-gastos, motor-reglas | C | bootstrap |
| `flujo-reclamo-mediador` | agente-mediador, precedentes | D | bootstrap, documental (se arranca con stubs) |
| `panel-admin-ejecucion` | panel-admin, ejecucion, evaluacion-e2e | E | bootstrap, canal (se arranca con fixtures) |

El bootstrap deja el grafo entero corriendo con stubs, así cada uno reemplaza su nodo sin esperar a los demás. Los cinco changes de componentes ya tienen proposal y specs; cada dueño escribe su `design.md` y `tasks.md` como primer paso.

## Stack del MVP

Python 3.12 (uv) · LangGraph · proxy LiteLLM del ITBA (modelos GPT) · Pinecone · SQLite (plataforma simulada) · Telegram · Streamlit (panel) · LangSmith · pytest.

La guía para levantar el entorno se completa en el change `bootstrap-proyecto`.
