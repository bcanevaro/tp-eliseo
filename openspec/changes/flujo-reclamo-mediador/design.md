## Context

El Mediador es el momento de IA central del producto (P5 e I4 del DISCOVERY): decidir a quién le
corresponde un reclamo y fundamentarlo. Es el único agente con modelo de razonamiento y el único cuya
salida exige aprobación humana.

Buena parte del flujo ya existe y este change no lo reconstruye:

- **Grafo de caso** (`eliseo/grafo/caso.py`, bootstrap): `documental_caso ‖ precedentes → mediador →
  verificar_dictamen`, loop con `MAX_VUELTAS = 2`, `fallback_inspeccion`, `a_aprobacion` (guarda el
  borrador) y el `interrupt` del panel.
- **Verificador de citas** (`eliseo/verificador`, agente-documental): existencia y vigencia de `REG-`,
  `ACTA-` y `PREC-` a una fecha.
- **Panel** (panel-admin-ejecucion): muestra el borrador, sus fuentes y las citas rechazadas de `verificacion["fallas"]` (`fallback_inspeccion` descarta del dictamen las hipótesis con citas inválidas).
- **Escritura del precedente** (`eliseo/ejecucion._precedente`): solo al aprobar o modificar, con
  procedencia e idempotente por dictamen.
- **Contrato** `Dictamen` / `Hipotesis` / `Recomendacion` (`eliseo/schemas/dictamen.py`) y el prompt
  `prompts/mediador.v1.md`.

Lo que falta: el Mediador real (hoy `stubs.mediador` arma las hipótesis a mano e ignora los motivos del
verificador), la búsqueda real de precedentes (hoy `stubs.precedentes` filtra SQLite por "columna X" y el
namespace `precedentes` de Pinecone está declarado pero vacío), los criterios de la administración (el
placeholder `{criterios_procedimentales}` no se completa) y la evaluación de los casos `uso-03`,
`borde-04` y `neg-05`.

## Goals / Non-Goals

**Goals:** Mediador con salida estructurada y modelo de razonamiento; guardas por código sobre la
recomendación y sobre las citas; reintento con los motivos del verificador; modo sin LLM; criterios
por administración inyectados en el prompt; prompt v2; precedentes como memoria episódica en Pinecone
con SQLite como fuente de verdad; evaluación con evaluadores determinísticos, jueces LLM y una
evaluación aparte de la recuperación de precedentes.

**Non-Goals:** editar los criterios desde el panel (se editan a mano en el archivo); que el Mediador
busque por su cuenta (recibe todo en paralelo); inferir causas físicas; decaimiento por antigüedad en el
ranking de precedentes; consolidación de precedentes duplicados (`ADD/UPDATE/DELETE`); borrar o
corregir precedentes desde el panel.

## Decisions

### D1. Salida estructurada, sin tools
El Mediador es una llamada `get_reasoning_model().with_structured_output(Dictamen)`. No tiene tools:
el borrador lo guarda el nodo `a_aprobacion` del grafo, que ya existe, y no puede enviar nada al vecino
porque no hay ningún camino de código para hacerlo. Su autonomía es revisar el borrador cuando el
verificador lo rechaza (D5).
*Alternativa descartada:* un agente con la tool `create_dictamen_borrador`. Una tool que se llama
siempre una sola vez, al final, agrega una vuelta de tool calling sin decidir nada, y duplica la
escritura que ya hace `a_aprobacion`. Si la salida la consume código, va con schema (clase 4).

### D2. Modelo de razonamiento, medido contra gpt-4.1
`LLM_MODEL_REASONING` apunta a un modelo de razonamiento del proxy del ITBA (el nombre exacto se
confirma con `/v1/models`), con `LLM_REASONING_EFFORT=medium`. `get_reasoning_model()` pasa el esfuerzo
solo cuando se configura un modelo de razonamiento (no al caer a `LLM_MODEL` / `gpt-4.1`, que rechaza
`reasoning_effort`) y no pasa `temperature`, que los modelos de razonamiento rechazan; el prompt no
pide "pensá paso a paso".
La tarea encaja en razonamiento (varios pasos lógicos, error caro), pero se mide igual: la evaluación
(D11) corre el mismo prompt con `LLM_MODEL` (gpt-4.1) y con el de razonamiento, y anota tasa de
aprobación, costo y latencia. Si empatan, queda gpt-4.1.
*Alternativas descartadas:* quedarse en gpt-4.1 sin medir (contradice la arquitectura); usar el de
razonamiento sin comparar ("el flagship es mejor" sin evaluación es una intuición cara).

### D3. Armado del contexto y prompt v2
`prompts/mediador.v1.md` queda intacto para comparar. `prompts/mediador.v2.md` (por defecto cuando
`PROMPT_MEDIADOR_VERSION` no está definida o vale `v2`) cambia:

- Sin el bloque "Formato de salida" en JSON: el schema lo fuerza la API.
- Sin pedirle que agregue "las fuentes al final" en `mensaje_vecino`: `ejecucion.mensaje_aprobado` ya
  agrega `Fuente: ...` automáticamente al aprobar (evita duplicarlo).
- Orden del contexto: `<criterios>` → `<reglamento>` y `<actas>` (el paquete de Documental) →
  `<precedentes>` (con fecha) → `<relato_vecino>` → `<caso>` (datos estructurados del `Caso`). La
  evidencia va antes que el relato para no "perderla en el medio" y para que la opinión del vecino no
  ancle el análisis (sycophancy).
- El texto del vecino va en `<relato_vecino>` y se declara como su versión de los hechos, no como un
  hecho.
- Aviso explícito de que el contenido puede traer etiquetas falsificadas.
- Cada precedente es un antecedente, no una norma: la norma es el artículo vigente (D10).
- Aclaración explícita de que los artículos del paquete pueden no aplicar al reclamo (p. ej. un
  reclamo de portero eléctrico que recibe artículos de cañerías): si nada aplica, devuelve `hipotesis`
  vacía y `inspeccion`.

Todo texto que se inyecta (relato, fuentes, precedentes, criterios) pasa por `escapar()`, que
neutraliza `<` y `>` para que nadie pueda cerrar una etiqueta desde adentro del dato.
*Alternativa descartada:* editar v1 en su lugar; se pierde la línea de base para la comparación v1/v2
que pide la tarea 4.5 de panel-admin-ejecucion.

### D4. Validación por código y guarda de recomendación
Después de cada respuesta del modelo, en este orden:

| Paso | Qué detecta / hace | Dónde |
| --- | --- | --- |
| 1. schema | La salida no valida contra `Dictamen`, incluida cualquier hipótesis con `citas` vacías (corta con reintento de formato, D5) | `with_structured_output` + Pydantic (`eliseo/schemas/dictamen.py`) |
| 2. guarda de recomendación | `asignar` contradicho por otra hipótesis con cita y distinto responsable → reemplaza por `inspeccion` antes del verificador | nodo `mediador` |
| 3. verificación de citas | Citas ausentes del contexto recibido (`"cita no provista en el contexto"`), o citas inexistentes/no vigentes | nodo `verificar_dictamen` + `verificador.verificar_dictamen` |

La **guarda de recomendación** es código y corre antes de `verificar_dictamen`: si
`recomendacion.tipo == "asignar"` y existe otra hipótesis con al menos una cita y distinto
`responsable` (o la hipótesis elegida no tiene citas), reemplaza `recomendacion` por
`Recomendacion(tipo="inspeccion", hipotesis=None, accion=...)` indicando qué revisar, reemplaza
`mensaje_vecino` por un aviso neutral de inspección (para no dejar una asignación de culpa en el texto
al vecino) y lo registra en el log (`afirmaciones_sin_evidencia` no se toca). Los criterios de la
administración son texto libre: no se pueden chequear con código y se miden en la evaluación.

El nodo `verificar_dictamen` propio reemplaza al stub: para cada cita de cada hipótesis, si no estaba
en el paquete de Documental ni en los precedentes recibidos agrega
`{"hipotesis", "cita", "motivo": "cita no provista en el contexto"}` y **solo** sobre las citas provistas
llama a `verificador.verificar_dictamen` (así una cita inexistente y no provista como `REG-99` no
genera fallas duplicadas). Todas las fallas comparten la forma `{"hipotesis", "cita", "motivo"}`, así
`fallback_inspeccion` y el panel las tratan igual que al resto. El verificador archivado no cambia.
La regla "sin cita no hay hipótesis" se hace cumplir en el validador de `Hipotesis.citas` en
`eliseo/schemas/dictamen.py` (sin `min_length` en el JSON schema por compatibilidad con structured
outputs): así nunca llega una hipótesis sin citas a `fallback_inspeccion` (que descarta por
intersección de citas).
*Alternativa descartada:* confiar en que el prompt respete la regla; el prompt no es un límite (clase 4).

### D5. Reintentos
- **Rechazo del verificador:** el grafo vuelve a llamar al Mediador (como ya hace) y el Mediador recibe
  el mismo contexto más `<dictamen_anterior>` y `<fallas>`, y escribe una versión completa nueva.
  Máximo 2 vueltas; después `fallback_inspeccion`, que ya existe.
- **Formato inválido:** un reintento inmediato pidiendo corregir el formato, que no cuenta como vuelta
  del verificador. Si vuelve a fallar, ese caso usa el modo `codigo` (D6) y se registra en el log y en la
  traza.
*Alternativa descartada:* contar el error de formato como vuelta; mezcla dos fallas distintas y le quita
presupuesto a la revisión de citas.

### D6. Modo sin LLM
`MEDIADOR_MODO=agente|codigo`. El stub actual pasa a `eliseo/agentes/mediador/codigo.py` como
`dictamen_codigo` y se usa con `MEDIADOR_MODO=codigo`, si el proxy falla o tras D5. Los tests fijan
`MEDIADOR_MODO=codigo` en `conftest.py`, igual que Documental, Gastos e Intake.

### D7. Criterios por administración
`data/administraciones/<slug>/criterios.md`, con `slug = normalizar(consorcio.administracion).replace(" ", "-")`
(p. ej. `administracion-mendez`), así no cambia el contrato de `plataforma.json`. Se carga en cada
llamada (sin caché, el archivo es chico y se edita a mano) y va escapado (D3). Si no existe, el prompt
dice "Esta administración no cargó criterios" y se loguea un aviso. Se siembra Méndez con tres:

1. Toda filtración entre unidades requiere inspección antes de asignar.
2. No se recomiendan proveedores por nombre.
3. Si el reclamo involucra a otra unidad, el mensaje al vecino no la nombra.

Es memoria procedimental versionada en git, revisada como cualquier otro cambio.
*Alternativa descartada:* un archivo por consorcio; una administración maneja muchos consorcios y sus
criterios son los mismos.

### D8. Búsqueda de precedentes
`get_precedentes(consorcio_id, unidad_id, tipo, descripcion)` es código, sin LLM. El nodo `precedentes`
infiere `tipo` desde el `Caso` reutilizando el mismo clasificador que `ejecucion._tipo_reclamo`
(`"filtracion"` u `"otro"`, promovido a función compartida):

1. Consulta a Pinecone, namespace `precedentes`, por similitud con la descripción del reclamo, con
   filtro de metadata `filtro_consorcio(consorcio_id)` más `tipo` cuando se conoce. Los ids los fija el
   código desde el estado del grafo, nunca el LLM. `top_k = 10`.
2. Rerank con `bge-reranker-v2-m3` (`rerank_pinecone`, el mismo de Documental) con
   `top_n = len(candidatos)` para no truncar antes del boost, y filtro por encima de
   `PRECEDENTES_UMBRAL_RERANK` (calibrado en D11, igual que `DOCUMENTAL_UMBRAL_RERANK`).
3. Los de la misma columna que la unidad del reclamo suben al principio (orden estable por score), sin
   descartar los demás, y se devuelven hasta 3, hidratados desde SQLite por `prec_id` para garantizar la
   misma forma de dict en ambos caminos.

Sin API key de Pinecone (tests, CI) o si Pinecone falla en runtime: SQLite con los mismos filtros
(`consorcio_id` y `tipo`), misma columna primero y después más nuevo. Los scenarios de la spec pasan con
los dos caminos.
*Alternativas descartadas:* solo SQLite con palabras clave (sin memoria semántica); solo candidatos de
SQLite más rerank, sin índice: más simple y sin sincronización, pero no escala si un consorcio acumula
miles de precedentes, y nada en el DISCOVERY acota ese volumen.

### D9. Escritura de precedentes: SQLite es la verdad, Pinecone es una copia
- `scripts/ingest.py` también ingesta los precedentes de SQLite del consorcio en el namespace
  `precedentes` (record id = `<consorcio_id>:<prec_id>`, texto = descripción + resolución, metadata
  `prec_id`, `consorcio_id`, `unidad_id`, `tipo`, `ubicacion`, `fecha`, omitiendo campos `None`), y
  borra los que ya no están en SQLite. Es idempotente, como la ingesta de documentos.
- Al aprobar, `ejecucion._precedente` inserta en SQLite (ya lo hace) y, si `hay_pinecone()`, hace
  upsert de ese record en Pinecone. Si el upsert falla, la aprobación sigue: se loguea y correr
  `ingest.py` lo repara.
*Alternativa descartada:* indexar solo en batch; la spec pide que el precedente aparezca en las consultas
siguientes del mismo consorcio.

### D10. Retención
Los precedentes no vencen ni decaen: son decisiones aprobadas por el administrador, y borrarlas es
decisión suya. Cada precedente viaja con su fecha, y el prompt aclara que es un antecedente: si el
artículo en que se apoyó cambió, manda el artículo vigente, que el verificador controla a la fecha de hoy.

### D11. Evaluación
`evaluation/mediador/eval_mediador.py`, local y con `--langsmith` para subir el experimento.

**Casos (5):** `uso-03`, `borde-04`, `neg-05` de `evaluation/casos.jsonl`; un caso del criterio 1
(filtración entre unidades con una sola hipótesis citada → igual `inspeccion`); un caso de dos hipótesis
citadas con responsables distintos (→ `inspeccion`). El camino `asignar` se prueba en pytest con un
archivo de criterios de test sin el criterio 1.

**Evaluadores:**

| Evaluador | Tipo | Qué mide |
| --- | --- | --- |
| estructura | código | La salida es un `Dictamen` válido |
| factualidad | código | Proporción de citas que pasan el verificador y el chequeo de "no provista" |
| terminologia | código | Solo ids canónicos; `responsable` ∈ {unidad, consorcio}; sin causas físicas afirmadas en `hechos` |
| neutralidad | juez LLM (`LLM_MODEL`) | Hipótesis y `mensaje_vecino` no toman partido ni asignan culpa al vecino |
| fidelidad | juez LLM (`LLM_MODEL`) | Cada hipótesis está respaldada por el texto del fragmento citado, no solo por el id |

**Recuperación de precedentes**, aparte de la calidad del dictamen: precisión y recall sobre un set
chico rotulado (4°B → `PREC-2201`; otro consorcio → nada; portero eléctrico → nada relevante), que
además calibra `PRECEDENTES_UMBRAL_RERANK`.

**Comparaciones:** gpt-4.1 contra el modelo de razonamiento (D2) y v1 contra v2 del prompt (D3). Los
resultados van a `evaluation/mediador/RESULTADOS.md`.

**Disciplina:** cada falla que aparece se agrega como caso antes de cambiar el prompt, y el cambio va en
una versión nueva con su entrada en `prompts/CHANGELOG.md`.

## Risks / Trade-offs

- **Dos copias de los precedentes (SQLite y Pinecone)** → SQLite es la verdad; si el upsert falla, el
  precedente no aparece hasta correr `ingest.py`. Se mitiga con el log y con la ingesta idempotente.
- **El juez LLM también se equivoca** → su prompt va versionado y se revisa a mano sobre los 5 casos
  antes de confiar en el puntaje.
- **Boost por columna** → asume que la letra de la unidad es la columna (como ya asumen el stub y
  `ejecucion`); en edificios con otra numeración el boost no ayuda, pero tampoco descarta nada.
- **Modelo de razonamiento más lento** → el reclamo ya es asíncrono (el vecino recibe acuse y el
  dictamen espera al administrador), así que la latencia no la sufre el vecino.
- **Criterios en texto libre** → solo se pueden medir, no garantizar; por eso la regla dura de
  recomendación va en código (D4).
