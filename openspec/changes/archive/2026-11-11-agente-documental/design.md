## Context

El bootstrap dejó el corpus del consorcio de demo con ids canónicos (`eliseo/corpus.py`), los contratos `Cita`, `RespuestaDocumental` y `RespuestaVecino`, y stubs para los nodos `documental`, `verificar_consulta`, `responder_reglamento` y `documental_caso`. El stub de búsqueda es léxico y muy básico, y el del verificador no maneja vigencia por fecha ni fragmentos recortados.

Restricción importante: al 10/11/2026 el proxy del ITBA está **sin crédito** en OpenAI y en Anthropic, tanto para chat como para embeddings. Pinecone funciona, incluidos sus modelos hospedados de embeddings (`multilingual-e5-large`) y de rerank (`bge-reranker-v2-m3`). El diseño tiene que dejar avanzar todo lo que no es redacción sin depender del proxy.

## Goals / Non-Goals

**Goals:**
- Que la recuperación (ingesta, híbrido y rerank) y el verificador funcionen y se puedan evaluar sin el proxy.
- Que la rama de reglamento responda con citas verificadas o se abstenga, también con el proxy caído (modo retriever).
- Darle a `flujo-reclamo-mediador` el paquete de citas del caso y un verificador de dictámenes reales.

**Non-Goals:**
- OCR de PDFs: el corpus del MVP es texto (decisión del bootstrap).
- Búsqueda de precedentes: es del change `flujo-reclamo-mediador`, aunque usa el mismo índice.
- Reemplazar el intake: la `pregunta_reescrita` sigue viniendo del Intake + Router.

## Decisions

### D1. Índice de Pinecone con embedding integrado
`eliseo/vectores.py` crea el índice con `create_index_for_model` (modelo `multilingual-e5-large`, 1024 dimensiones, `field_map = {"text": "texto"}`). Con eso Pinecone vectoriza el texto del lado del servidor: la ingesta hace `upsert_records` con texto y metadata, y la búsqueda hace `search` con el texto de la consulta.

Alternativas:
- **Embeddings del proxy** (`text-embedding-3-small`, la decisión D5 del bootstrap): hoy no hay crédito, y además obliga a vectorizar en dos lados (ingesta y consulta) con el mismo modelo.
- **`langchain-pinecone` (`PineconeVectorStore`)**: no soporta índices integrados de forma directa y agrega una capa que no necesitamos.

El modelo e5 es multilingüe, rinde bien en español y los artículos entran holgados en su límite de 507 tokens. El índice nuevo se llama `eliseo` (sigue siendo `PINECONE_INDEX_NAME`). Si alguien ya creó uno de 1536 dimensiones con ese nombre, hay que borrarlo: el script de ingesta lo detecta y avisa.

### D2. Un chunk por artículo o punto de acta
La unidad es la que ya define `eliseo/corpus.py`: `REG-<n>` o `ACTA-<fecha>#<punto>`. Los artículos del consorcio son cortos, así que no hace falta subdividirlos. Si algún día un artículo pasa los 400 tokens, se parte en varios chunks con el mismo `ref` y el sufijo `~k` en el id del vector.

Cada record lleva:
- `_id = "<consorcio_id>:<ref>"`;
- `texto = "<título>. <texto>"`, que es el campo que se vectoriza;
- la metadata `consorcio_id`, `doc_tipo`, `ref`, `titulo`, `fecha`, `vigente`, `modifica`, `efecto`, `modificado_por` y `reemplazado_por`.

Alternativa descartada: chunking por tamaño fijo, porque parte artículos al medio y la cita deja de corresponder a una unidad que el vecino pueda buscar.

### D3. Retriever híbrido: dense + BM25, fusión RRF y rerank
`buscar(consorcio_id, consulta, k=3)`:
1. **Dense:** `index.search` en el namespace `documentos`, con top 10 y el filtro `consorcio_id`.
2. **Léxico:** BM25 (`rank_bm25`) sobre los chunks del mismo consorcio, armado en memoria a partir de `eliseo/corpus.py`. Tokeniza en minúsculas, sin tildes, sin stopwords y con stemming en español (`snowballstemmer`). Se queda con el top 10.
3. **Fusión:** Reciprocal Rank Fusion con k = 60, que no necesita calibrar escalas entre las dos listas.
4. **Rerank:** `pc.inference.rerank` con `bge-reranker-v2-m3` (multilingüe) sobre los 10 primeros de la fusión, y se devuelven los top-k.
5. **Resolución de vigencia**, en código y no como filtro de la búsqueda. Un artículo reemplazado se sustituye por el acta que lo reemplaza. A un artículo complementado se le agregan las actas que lo complementan.

El paso 5 no es un filtro `vigente = true` en la búsqueda porque la pregunta del vecino suele parecerse más al artículo original que al acta (por ejemplo, "horario de obras" se parece más a REG-14 que a ACTA-2025-08-20#3). Si se filtrara antes, se perdería el camino al acta.

Cada paso es una función aparte, para evaluarlo por separado. Si Pinecone no responde, el retriever sigue solo con BM25 y lo loguea: degrada, no se cae.

Alternativas:
- **Índice sparse-dense de Pinecone:** necesita un encoder sparse propio, y el sparse hospedado (`pinecone-sparse-english-v0`) está pensado para inglés.
- **Solo dense:** pierde coincidencias exactas de términos del reglamento, como "montante", "coeficiente" o "toldos".

### D4. El agente: un loop explícito con tools y tope de búsquedas
`eliseo/agentes/documental/agente.py` es un loop corto escrito a mano. Con `LLM_MODEL` y `bind_tools`, el modelo puede llamar a dos tools:
- `search_reglamento(consulta)`;
- `get_acta(acta_id)`, que devuelve el acta completa o un punto.

El `consorcio_id` **no es un argumento de las tools**: se fija con un closure al construirlas a partir de la `Identidad` del estado, así el LLM no puede pedir documentos de otro consorcio.

Un contador corta a las 3 búsquedas. A partir de ahí la tool devuelve "límite de búsquedas alcanzado" y se pide la respuesta final con `with_structured_output(RespuestaDocumental)`. La reescritura de la consulta del vecino al lenguaje jurídico la hace el propio agente al elegir el argumento de `search_reglamento`; la primera búsqueda parte de la `pregunta_reescrita` del intake.

Alternativas:
- **`create_react_agent` o `langchain.agents.create_agent`:** sirven, pero esconden el tope de búsquedas y la salida estructurada detrás de parámetros que cambian seguido entre versiones. Además el segundo obliga a instalar `langchain`. Un loop de unas 40 líneas se testea con un modelo falso.
- **Retriever fijo sin agente:** no puede decidir volver a buscar cuando un acta modifica un artículo, que es justamente por qué esta caja es un agente.

### D5. Dos modos: `agente` y `retriever`
`DOCUMENTAL_MODO` (por defecto `agente`):
- **`agente`:** el de D4, con LLM.
- **`retriever`:** sin LLM. Devuelve las citas de `buscar(k=1)`, ya con la vigencia resuelta, y arma la respuesta con una plantilla ("Según el REG-18: …").

El modo `retriever` existe por la falta de crédito del proxy y para los tests, y la abstención funciona igual en los dos modos. Si en modo `agente` el LLM devuelve un error de crédito o de conexión, se cae al modo `retriever` y queda logueado.

### D6. Verificador en `eliseo/verificador/`
Es código sin LLM y reemplaza a `stubs.verificar_citas`.

`verificar_citas(consorcio_id, citas, fecha=None)` devuelve `{"ok": bool, "fallas": [{"cita", "motivo", "vigente": <ref o None>}]}`, la misma forma de dict que ya usa el grafo de caso. Las comprobaciones son:
- **Existencia:** contra el corpus (REG y ACTA) o contra la base (FAC, LIQ y PREC).
- **Vigencia a una fecha:** un artículo reemplazado por un acta con fecha ≤ `fecha` no está vigente, y la falla sugiere el acta. Sin `fecha`, se toma la de hoy.
- **Fragmento literal:** se comparan los textos en minúsculas, sin tildes, con espacios simples y sin puntuación. Si el fragmento tiene "...", cada tramo tiene que aparecer en orden.

`verificar_dictamen(consorcio_id, dictamen, fecha)` aplica lo mismo a los ids de cada hipótesis (que no traen fragmento) y devuelve las fallas con la hipótesis a la que pertenecen. El nodo `verificar_dictamen` del grafo de caso sigue siendo de `flujo-reclamo-mediador`, pero llama a esta función.

### D7. Abstención y redacción
- **`verificar_consulta`:** si hay citas que fallan, se descartan. Si las que quedan alcanzan (la respuesta tenía `suficiente = true` y queda al menos una cita válida), la redacción se hace solo con esas. Si no queda ninguna, se deriva.
- **`responder_reglamento`:** en modo `agente`, redacta con el master prompt `vecino` y `with_structured_output(RespuestaVecino)`, pasando las citas válidas como `<fuentes>`. Si el LLM devuelve `derivar = true` o una cita que no estaba en las fuentes, se deriva. En modo `retriever` usa la plantilla.
- **El texto del vecino y el de los documentos** van siempre dentro de etiquetas, como dato.

### D8. Paquete de citas para el reclamo
`documental_caso` usa el mismo retriever, sin LLM, con tres consultas: el reclamo (ambiente y descripción), las instalaciones de uso exclusivo a cargo de la unidad y las cañerías generales a cargo del consorcio. Son tres porque el Mediador tiene que poder plantear hipótesis de los dos lados, y una sola consulta tiende a traer solo uno (en las pruebas traía REG-16 y no REG-15). Además trae las actas que mencionan la misma columna o instalación. Devuelve `RespuestaDocumental` con las citas, sin redactar respuesta.

### D9. Evaluación
- **Recuperación, sin LLM:** `evaluation/documental/preguntas.jsonl`, con unas 25 preguntas en lenguaje vecinal y sus `refs_esperadas`. Las métricas son recall@3 y MRR, por paso: dense solo, BM25 solo, RRF, y RRF con rerank, para justificar el híbrido con números. Se corre local y se sube como experimento a LangSmith.
- **Agente, con LLM, cuando el proxy tenga crédito:** los casos `uso-01`, `borde-02`, `neg-01` y `neg-04` de `evaluation/casos.jsonl`, más inyecciones dentro de documentos. Los evaluadores son determinísticos: schema válido, verificador ok y refs esperadas presentes.

## Risks / Trade-offs

- [Consistencia eventual de Pinecone: lo recién upserteado tarda unos segundos en aparecer] → la ingesta espera a que `describe_index_stats` muestre la cantidad esperada de records antes de terminar.
- [El plan gratis de Pinecone tiene límites de lectura y de unidades de rerank] → el corpus es chico. Los tests unitarios no llaman a Pinecone (hay un retriever dense falso) y los de integración se marcan con `@pytest.mark.pinecone` y se saltean sin `PINECONE_API_KEY`.
- [Cambiar la dimensión del índice rompe un índice `eliseo` creado antes] → nadie lo creó todavía. La ingesta valida la dimensión y avisa en lugar de fallar en silencio.
- [Un BM25 en memoria por consorcio no escala a miles de consorcios] → para el MVP alcanza: se cachea por consorcio y se reconstruye al reingestar.
- [En modo `retriever` las respuestas son textuales y poco amigables] → solo se usa sin crédito del proxy. La abstención y las citas son las mismas.

## Open Questions

- ¿Vuelve el crédito del proxy antes de la entrega? Si no, la redacción y el loop del agente quedan probados solo con un modelo falso.
- ¿`multilingual-e5-large` o `llama-text-embed-v2` (también hospedado y multilingüe)? Se decide con la evaluación de recuperación de D9; el código no cambia, solo el nombre del modelo en la config.
