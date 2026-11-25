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

| Change | Capabilities | Dueño | Colaboran | Depende de |
|---|---|---|---|---|
| `bootstrap-proyecto` ✓ | contratos-compartidos, datos-ficticios, grafo-orquestacion | Bruno | — | — |
| `canal-telegram-intake` (implementado) | canal-telegram, intake-router | Bautista | Lu (evaluación) | bootstrap |
| `agente-documental` ✓ | ingesta-documental, agente-documental, verificador-citas | Bruno | — | bootstrap |
| `agente-gastos` (implementado) | agente-gastos, motor-reglas | Bautista | Lu (evaluación y arreglos) | bootstrap |
| `flujo-reclamo-mediador` (implementado) | agente-mediador, precedentes | Federico | Lu (evaluación y arreglos) | bootstrap, documental (se arranca con stubs) |
| `panel-admin-ejecucion` (implementado) | panel-admin, ejecucion, evaluacion-e2e | Bautista | Lu (evaluación) | bootstrap, canal (se arranca con fixtures) |
| `cuentas-administracion` (en implementación) | cuentas-admin, padron-consorcios, documentos-consorcio, canal-administracion | a definir | Juani | bootstrap, documental, canal, panel |

El bootstrap deja el grafo entero corriendo con stubs, así cada uno reemplaza su nodo sin esperar a los demás. "Implementado" quiere decir que las tasks están hechas y falta archivar; ✓, que ya está archivado. Las tasks pendientes de `canal-telegram-intake` y `panel-admin-ejecucion` están en su `tasks.md`.

## Stack del MVP

Python 3.12 (uv) · LangGraph · proxy LiteLLM del ITBA (modelos GPT) · Pinecone · Supabase (Postgres, Auth y Storage) o SQLite local (plataforma simulada) · Telegram · Streamlit (panel) · LangSmith · pytest.

## Levantar el entorno

Necesitás [uv](https://docs.astral.sh/uv/) y Python 3.12. No uses Python 3.14: `langchain-pinecone` todavía no es compatible.

```bash
uv venv --python 3.12 .venv
source .venv/bin/activate
uv pip install -r requirements.txt
cp .env.example .env          # completar las claves: proxy del ITBA, Pinecone, LangSmith (y Supabase, ver abajo)
python scripts/seed_db.py     # carga la demo (administración, cuenta de prueba, consorcio y documentos) sin borrar nada
python scripts/ingest.py R4520      # indexa el reglamento, las actas y los precedentes en Pinecone
pytest                        # tiene que dar todo en verde, sin red ni LLM
python scripts/check_servicios.py   # verifica el .env y la conexión a la base, Supabase, el proxy, Pinecone, LangSmith y Telegram
```

### Base de datos: Supabase o SQLite

- **Con Supabase** (`ELISEO_DB_URL` en el `.env`): la base y los checkpoints de los grafos van a Postgres, el login del panel puede usar Supabase Auth y los originales de los documentos van a Supabase Storage. En el proyecto de Supabase:
  1. **Connect → Connection String → Session pooler**: copiá la URI y reemplazá `[YOUR-PASSWORD]` (con los corchetes) por la contraseña de la base. Va en `ELISEO_DB_URL`.
  2. **Project Settings → API Keys**: la clave pública (`anon` o `publishable`) va en `SUPABASE_ANON_KEY` y la secreta (`service_role` o `secret`) en `SUPABASE_SERVICE_ROLE_KEY`.
  3. `SUPABASE_URL` es `https://<proyecto>.supabase.co`, sin ruta.
- **Sin Supabase** (`ELISEO_DB_URL` vacía): todo queda en `data/eliseo.db` (SQLite) y los originales en `data/archivos/`. Es lo que usan los tests y el CI, que nunca tocan la base del `.env`.

`scripts/seed_db.py` no borra nada: crea las tablas que falten y agrega la demo si no está. `python scripts/seed_db.py --reset` borra **toda** la base y la recrea; con Postgres pide escribir el host para confirmar.

### Cuentas de administración

Cada administración tiene sus cuentas, y cada cuenta ve solo los edificios de su administración. La siembra crea la cuenta de prueba de la Administración Méndez (`admin@demo.eliseo.test` / `eliseo-demo`, configurable en el `.env`). Para dar de alta otra administración:

```bash
python scripts/alta_administracion.py "Administración Pérez" pedro@ejemplo.com "Pedro Pérez" --password <contraseña>
```

Con Supabase configurado la cuenta se crea en Supabase Auth (sin `--password`, Supabase le manda una invitación por mail); sin Supabase, la contraseña se guarda con bcrypt.

## Panel del administrador y simulador de vecino

```bash
streamlit run eliseo/panel/app.py
```

Abre en http://localhost:8501 y pide iniciar sesión. Tiene cinco vistas, todas limitadas a los edificios de tu administración:
- **Panel de la administración:** bandeja (urgencias primero), detalle del dictamen con lo escrito por la IA marcado y cada cita con su fuente, y Aprobar / Modificar / Rechazar con confirmación. La decisión queda firmada con tu cuenta.
- **Edificios:** alta, edición y baja de edificios y sus unidades (los coeficientes tienen que sumar 1).
- **Vecinos:** alta, edición y baja de vecinos con su celular. Dar de baja a un vecino le corta el bot desde su próximo mensaje.
- **Documentos:** subir el reglamento y las actas de cada edificio en el formato del corpus (hay una plantilla para descargar). El panel los valida, muestra cómo quedaron partidos y, al confirmar, el bot los usa en el próximo mensaje.
- **Simulador de vecino:** un chat que usa el mismo runtime que el bot, para probar el flujo completo sin Telegram. Los mensajes que se aprueban en el panel aparecen ahí.

En la barra lateral, **Chat de avisos** genera el código para vincular el chat de Telegram donde tu administración recibe las urgencias.

## Bot de Telegram

```bash
python -m eliseo.canal.bot
```

Necesita `TELEGRAM_BOT_TOKEN` en el `.env`. Hay un solo bot para todas las administraciones: el edificio y la administración de cada vecino salen de su teléfono, cargado en el padrón. En Telegram:
- `/admin <código>` vincula ese chat como chat de avisos de tu administración (el código lo genera el panel, sirve una vez y vence a los 15 minutos).
- `/demo 4°B` (con `ELISEO_DEMO=1`) vincula tu Telegram con el vecino ficticio de esa unidad, porque tu número real no está en la base de demo. En un despliegue real tiene que estar apagado.
- `/chatid` te devuelve el id del chat.

El bot y el panel comparten la base: lo que se aprueba en el panel le llega al vecino por Telegram en unos segundos.

## Evaluación

Cada evaluación tiene su `RESULTADOS.md` con la última corrida y el experimento de LangSmith.

```bash
# De punta a punta: los 12 casos del artefacto con evaluadores determinísticos
python evaluation/e2e/correr.py
# Con todos los componentes con LLM, juez de tono y relevancia (según los criterios de cada caso) y LangSmith
INTAKE_MODO=llm GASTOS_MODO=agente DOCUMENTAL_MODO=agente MEDIADOR_MODO=agente \
  python evaluation/e2e/correr.py --juez --langsmith --repeticiones 3

# Por componente
python evaluation/intake/eval_intake.py --langsmith               # precision/recall por intent y recall de urgencias
python evaluation/documental/eval_recuperacion.py --langsmith     # recuperación del Documental por etapa
python evaluation/mediador/precedentes_eval.py --langsmith        # recuperación de precedentes y barrido de PRECEDENTES_UMBRAL_RERANK
python evaluation/mediador/eval_mediador.py --langsmith           # dictamen: estructura, factualidad, terminología, neutralidad, fidelidad
python evaluation/mediador/eval_mediador.py --modelo openai/gpt-5.6 --langsmith   # comparar modelos
python evaluation/mediador/eval_mediador.py --prompt v1 --langsmith               # comparar versiones del prompt
```

## Docker y CI

```bash
docker compose up --build                 # carga la demo si falta (sin borrar nada) y levanta el panel en :8501
docker compose --profile bot up --build   # además el bot de Telegram
```

El CI (`.github/workflows/ci.yml`) corre `pytest`, la evaluación de punta a punta sin LLM y el build de la imagen en cada push.

## Cómo está armado el código

```
eliseo/
  schemas/        contratos compartidos (Pydantic): lo que cruza entre componentes
  plataforma/     la base que simula la plataforma de gestión: Postgres (Supabase) o SQLite (lectura con mínimo privilegio)
  corpus.py       reglamento y actas con ids canónicos (REG-<n>, ACTA-<fecha>#<punto>; los precedentes son PREC-<n>), leídos de la base
  documentos.py   validación, guardado, baja e indexación del reglamento y las actas de cada consorcio
  cuentas.py      administraciones, cuentas, login y chat de avisos
  panel/          app.py (Streamlit) y la lógica por sesión: servicio.py, padron.py, documentos.py
  agentes/        documental/, gastos/ y mediador/: la implementación de cada agente
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
evaluation/<componente>/          evaluaciones por componente, cada una con su RESULTADOS.md
```

**Para empezar tu componente:**
1. Leé tu change en `openspec/changes/<tu-change>/` y escribí `design.md` y `tasks.md`.
2. Mirá en `eliseo/grafo/stubs.py` qué recibe y qué devuelve tu nodo.
3. Implementalo en tu carpeta, por ejemplo `eliseo/agentes/documental/`.
4. Cambiá tu línea en `eliseo/grafo/nodos.py`.

El test de humo (`tests/test_grafo.py`) tiene que seguir pasando: si cambia un comportamiento que está en la spec, el test cambia junto con la spec.

Los mensajes que salen fuera de turno, como la resolución de un caso o un aviso de urgencia, no se mandan directo: van a la tabla `outbox` y los envía el proceso del bot.
