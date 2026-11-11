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
2. **Revisar antes de codear:** pusheás la branch solo con los artefactos y avisás en el grupo; otro integrante revisa proposal, specs y design en la branch.
3. **Implementar:** `/opsx:apply`, marcando las tasks a medida que se completan.
4. **Validar:** `openspec validate <nombre> --strict` y `pytest`, con todo en verde.
5. **Mergear y archivar:** traés lo último de `main`, mergeás tu branch y corrés `openspec archive <nombre>`, que mueve las specs a `openspec/specs/` (la fuente de verdad). No usamos pull requests.

Comandos útiles: `openspec list`, `openspec view`, `openspec show <nombre>`, `openspec status --change <nombre>`.

### Changes y dueños

| Change | Capabilities | Dueño | Depende de |
|---|---|---|---|
| `bootstrap-proyecto` ✓ | contratos-compartidos, datos-ficticios, grafo-orquestacion | Bruno | — |
| `canal-telegram-intake` | canal-telegram, intake-router | A | bootstrap |
| `agente-documental` ✓ | ingesta-documental, agente-documental, verificador-citas | Bruno | bootstrap |
| `agente-gastos` | agente-gastos, motor-reglas | C | bootstrap |
| `flujo-reclamo-mediador` | agente-mediador, precedentes | D | bootstrap, documental (se arranca con stubs) |
| `panel-admin-ejecucion` | panel-admin, ejecucion, evaluacion-e2e | E | bootstrap, canal (se arranca con fixtures) |

El bootstrap deja el grafo entero corriendo con stubs, así cada uno reemplaza su nodo sin esperar a los demás. Los cinco changes de componentes ya tienen proposal y specs; cada dueño escribe su `design.md` y `tasks.md` como primer paso.

## Stack del MVP

Python 3.12 (uv) · LangGraph · proxy LiteLLM del ITBA (modelos GPT) · Pinecone · SQLite (plataforma simulada) · Telegram · Streamlit (panel) · LangSmith · pytest.

## Levantar el entorno

Necesitás [uv](https://docs.astral.sh/uv/) y Python 3.12. No uses Python 3.14: `langchain-pinecone` todavía no es compatible.

```bash
uv venv --python 3.12 .venv
source .venv/bin/activate
uv pip install -r requirements.txt
cp .env.example .env          # completar las claves: proxy del ITBA, Pinecone, LangSmith
python scripts/seed_db.py     # crea data/eliseo.db con el consorcio de demo
pytest                        # tiene que dar todo en verde, sin red ni LLM
```

## Cómo está armado el código

```
eliseo/
  schemas/        contratos compartidos (Pydantic): lo que cruza entre componentes
  plataforma/     SQLite que simula la plataforma de gestión (lectura con mínimo privilegio)
  corpus.py       reglamento y actas con ids canónicos (REG-<n>, ACTA-<fecha>#<punto>)
  grafo/
    conversacion.py   grafo por vecino: identificar → intake → ramas por intent
    caso.py           grafo por reclamo: Documental ‖ Precedentes → Mediador ⇄ verificador → panel → ejecución
    nodos.py          ← acá enchufás tu implementación (reemplazás el stub)
    stubs.py          implementación de referencia sin LLM de cada nodo
    runtime.py        procesar_mensaje(), retomar_caso(), estado_caso()
  llm.py, vectores.py, prompts.py, config.py
data/consorcios/rivadavia-4520/   reglamento, actas y plataforma.json (todo ficticio)
prompts/                          master prompts versionados + CHANGELOG
evaluation/casos.jsonl            los 12 casos del artefacto
```

**Para empezar tu componente:**
1. Leé tu change en `openspec/changes/<tu-change>/` y escribí `design.md` y `tasks.md`.
2. Mirá en `eliseo/grafo/stubs.py` qué recibe y qué devuelve tu nodo.
3. Implementalo en tu carpeta, por ejemplo `eliseo/agentes/documental/`.
4. Cambiá tu línea en `eliseo/grafo/nodos.py`.

El test de humo (`tests/test_grafo.py`) tiene que seguir pasando: si cambia un comportamiento que está en la spec, el test cambia junto con la spec.

Los mensajes que salen fuera de turno, como la resolución de un caso o un aviso de urgencia, no se mandan directo: van a la tabla `outbox` y los envía el proceso del bot.
