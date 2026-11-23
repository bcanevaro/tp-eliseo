## Why

Es el momento de IA central del producto y la parte cara que nadie automatiza: decidir a quién le corresponde un reclamo y fundamentarlo. El Mediador es el único agente con modelo de razonamiento y el único cuya salida exige aprobación humana. Los precedentes van en este change porque solo los consume el Mediador y porque su memoria episódica se escribe con las decisiones aprobadas.

## What Changes

- Agente Mediador con el master prompt v2 y un modelo de razonamiento: produce, como salida estructurada, un `Dictamen` con hechos, hipótesis citadas, evidencia a favor y en contra, recomendación y mensaje al vecino.
- Guardas por código sobre la salida: la regla de recomendación y el rechazo de citas que no estaban en el contexto recibido.
- Modo sin LLM (`MEDIADOR_MODO=codigo`) para tests, CI y caídas del proxy.
- Criterios procedimentales de la administración como memoria editable (archivo por administración) que se inyecta en el prompt.
- Tool `get_precedentes(consorcio_id, unidad_id, tipo, descripcion)` sobre la memoria episódica (Pinecone namespace `precedentes` más la tabla de la base como fuente de verdad), con filtros estructurados, similitud y rerank.
- Escritura de precedentes solo desde decisiones aprobadas, con procedencia, en la base y en el índice.
- Reintento del Mediador con los motivos del verificador. El loop (máximo 2 vueltas) y el fallback a inspección ya están en el grafo de caso.
- Reemplaza los stubs `precedentes`, `mediador` y `verificar_dictamen` del bootstrap.

## Capabilities

### New Capabilities

- `agente-mediador`: redacción del borrador de dictamen de responsabilidad con su contrato y su loop de verificación.
- `precedentes`: memoria episódica de reclamos resueltos y su tool de consulta.

### Modified Capabilities

- `contratos-compartidos`: cada hipótesis del `Dictamen` exige al menos una cita (validador de `Hipotesis.citas`).

## Impact

- **Dueño:** Federico Viera (Integrante D).
- **Depende de:** `bootstrap-proyecto` (contratos `Dictamen` y `Caso`, grafo de caso) y `agente-documental` (paquete de citas, verificador y reranker).
- **Toca código de otros changes:** `eliseo/ejecucion` (panel-admin-ejecucion), para indexar el precedente al aprobar, y `scripts/ingest.py` (agente-documental), para ingestar los precedentes. Además `eliseo/schemas/dictamen.py` (bootstrap-proyecto, contrato compartido), para rechazar hipótesis sin citas; los dictámenes guardados que el panel relee con `Dictamen.model_validate_json` nunca tienen hipótesis sin citas, porque el stub y el fallback no las generan.
- **Origen:** cajas "Mediador" y "Precedentes" del artefacto; prompt "Mediador" v1; casos de test de humedad en el 4°B, caso sin artículo aplicable e instrucción oculta en un documento.
- **Modelo:** uno de razonamiento del proxy del ITBA (`LLM_MODEL_REASONING`), comparado contra gpt-4.1 en la evaluación antes de fijarlo (design D2).
