## Why

Responder el reglamento con la fuente citada es el valor más directo para el vecino y la base del dictamen: el Mediador no busca, recibe lo que encuentra Documental. Es un agente (y no un retriever fijo) porque decide cuántas búsquedas hacer: si un acta modifica un artículo, vuelve a buscar. El verificador de citas va en este mismo change porque es lo que permite que la respuesta salga sin aprobación: sin cita verificada, el sistema se abstiene (riesgo 1 del Discovery).

## What Changes

- Ingesta del reglamento y las actas: chunking por artículo o punto de acta, metadata (consorcio, id canónico, fecha, vigente, modifica) y carga en el namespace `documentos` de Pinecone.
- Retriever híbrido: query rewriting de lenguaje vecinal a jurídico, dense con Pinecone, BM25, filtros de consorcio y vigencia, y rerank.
- Agente Documental con las tools de solo lectura `search_reglamento` y `get_acta`, que devuelve `RespuestaDocumental`.
- Verificador de citas determinístico, que comprueba existencia, vigencia y fragmento literal. Lo usan tanto la rama de consulta como el Mediador.
- Redacción de la respuesta al vecino con el master prompt "Respuestas al vecino" v1.
- Reemplaza los stubs `documental`, `verificador` y `responder` (rama reglamento) del bootstrap.

## Capabilities

### New Capabilities

- `ingesta-documental`: del texto del reglamento y las actas a chunks indexados con metadata.
- `agente-documental`: el agente de consulta de reglamento y actas, con su contrato y su retriever híbrido.
- `verificador-citas`: validación determinística de las citas de cualquier componente.

### Modified Capabilities

(ninguna)

## Impact

- **Dueño:** Bruno.
- **Depende de:** `bootstrap-proyecto` (contratos `Cita` y `RespuestaDocumental`, corpus, `eliseo/vectores.py`). **Lo usa:** `flujo-reclamo-mediador`.
- **Origen:** cajas "Documental" y "Verificador de citas" del artefacto; prompt "Respuestas al vecino" v1; casos de test de mascotas, artículo modificado por acta, pileta y las inyecciones.
- **Dependencias nuevas:** `rank_bm25` y `snowballstemmer` (BM25 con stemming en español); de Pinecone, el índice con embedding integrado (`multilingual-e5-large`) y el reranker hospedado (`bge-reranker-v2-m3`). Ver design D1 y D3.
- **Cambia código del bootstrap:** `eliseo/vectores.py` pasa a crear un índice con embedding integrado (1024 dimensiones en lugar de 1536). Afecta también al namespace `precedentes` de `flujo-reclamo-mediador`, que gana la vectorización del lado de Pinecone.
