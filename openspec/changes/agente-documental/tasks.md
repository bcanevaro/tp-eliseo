## 1. Verificador de citas (sin red)

- [ ] 1.1 `eliseo/verificador/`: `verificar_citas(consorcio_id, citas, fecha)` con existencia (corpus y base), vigencia a la fecha y fragmento literal normalizado, con soporte de recortes con "..." (D6)
- [ ] 1.2 `verificar_dictamen(consorcio_id, dictamen, fecha)` que devuelve las fallas por hipótesis
- [ ] 1.3 Reemplazar `stubs.verificar_citas` por el verificador nuevo (lo usan `verificar_consulta` y `verificar_dictamen`)
- [ ] 1.4 Tests: un test por scenario de `verificador-citas` (válida, fragmento inventado, recortado, derogado, una de dos inválida, dictamen con REG-99)

## 2. Ingesta

- [ ] 2.1 `eliseo/vectores.py`: crear el índice con embedding integrado `multilingual-e5-large` (D1) y validar la dimensión si ya existe
- [ ] 2.2 `eliseo/agentes/documental/ingesta.py`: records por artículo y punto de acta con la metadata de D2, id `<consorcio_id>:<ref>`
- [ ] 2.3 `scripts/ingest.py <consorcio_id>`: upsert idempotente y espera de consistencia con `describe_index_stats`
- [ ] 2.4 Tests sin red de la construcción de records (metadata, ids, acta que modifica); test de integración `@pytest.mark.pinecone` de reingesta sin duplicados
- [ ] 2.5 Correr la ingesta del Consorcio Rivadavia 4520 en el índice del grupo

## 3. Retriever híbrido

- [ ] 3.1 Tokenizador en español (minúsculas, sin tildes, stopwords y `snowballstemmer`) y BM25 por consorcio, cacheado (D3)
- [ ] 3.2 Búsqueda densa en Pinecone con el filtro `consorcio_id`, detrás de una interfaz que se pueda reemplazar por un falso en los tests
- [ ] 3.3 Fusión RRF (k = 60) y rerank con `bge-reranker-v2-m3`, con fallback a BM25 si Pinecone falla
- [ ] 3.4 Resolución de vigencia: reemplazados → acta vigente; complementados → más sus actas
- [ ] 3.5 Tests: aislamiento por consorcio (con un segundo consorcio de prueba), "toldito" → REG-22 y ACTA-2024-11-10#3 en el top 3, "horario de obras" → ACTA-2025-08-20#3, fallback sin Pinecone

## 4. Agente Documental

- [ ] 4.1 Tools `search_reglamento` y `get_acta` con el `consorcio_id` fijado por closure, más el contador de 3 búsquedas (D4)
- [ ] 4.2 Loop del agente con `bind_tools` y salida final `with_structured_output(RespuestaDocumental)`
- [ ] 4.3 Modo `retriever` sin LLM y fallback automático ante errores del proxy (D5); variable `DOCUMENTAL_MODO` en `.env.example`
- [ ] 4.4 Nodos `documental` y `documental_caso` (D8); reemplazar sus líneas en `eliseo/grafo/nodos.py`
- [ ] 4.5 Tests con un modelo falso: tope de búsquedas, el consorcio no se puede cambiar desde los argumentos, cita del acta posterior, instrucción escondida en un chunk que no cambia la respuesta

## 5. Abstención y respuesta al vecino

- [ ] 5.1 `verificar_consulta`: descarta las citas inválidas y deriva si no queda ninguna (D7)
- [ ] 5.2 `responder_reglamento` con el master prompt `vecino` y `RespuestaVecino`, con las fuentes entre etiquetas y derivación si el LLM cita algo que no estaba en las fuentes
- [ ] 5.3 Reemplazar `verificar_consulta` y `responder_reglamento` en `nodos.py`
- [ ] 5.4 El test de humo `tests/test_grafo.py` sigue pasando en modo `retriever`

## 6. Evaluación

- [ ] 6.1 `evaluation/documental/preguntas.jsonl`: unas 25 preguntas vecinales con sus `refs_esperadas` (incluye coloquiales, artículos modificados y sin fuente)
- [ ] 6.2 Script de evaluación de recuperación: recall@3 y MRR para dense, BM25, RRF y RRF con rerank; resultados en LangSmith y en el README del change
- [ ] 6.3 Con crédito en el proxy: experimento del agente en LangSmith sobre `uso-01`, `borde-02`, `neg-01` y `neg-04` con evaluadores determinísticos
- [ ] 6.4 `openspec validate agente-documental --strict`, mergear a `main` y `openspec archive agente-documental`
