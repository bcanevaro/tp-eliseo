## Why

Es el momento de IA central del producto y la parte cara que nadie automatiza: decidir a quién le corresponde un reclamo y fundamentarlo. El Mediador es el único agente con modelo de razonamiento y el único cuya salida exige aprobación humana. Los precedentes van en este change porque solo los consume el Mediador y porque su memoria episódica se escribe con las decisiones aprobadas.

## What Changes

- Agente Mediador con el master prompt v1 y un modelo de razonamiento: produce un `Dictamen` con hechos, hipótesis citadas, evidencia a favor y en contra, recomendación y mensaje al vecino.
- Criterios procedimentales de la administración como memoria editable (archivo por administración) que se inyecta en el prompt.
- Tool `get_precedentes(consorcio, unidad, tipo)` sobre la memoria episódica (Pinecone namespace `precedentes` más la tabla de la base), con filtros estructurados y similitud.
- Escritura de precedentes solo desde decisiones aprobadas, con procedencia.
- Implementación del loop Mediador ⇄ verificador (máximo 2 vueltas) y del fallback a inspección en el grafo de caso.
- Reemplaza los stubs `precedentes` y `mediador` del bootstrap.

## Capabilities

### New Capabilities

- `agente-mediador`: redacción del borrador de dictamen de responsabilidad con su contrato y su loop de verificación.
- `precedentes`: memoria episódica de reclamos resueltos y su tool de consulta.

### Modified Capabilities

(ninguna)

## Impact

- **Dueño:** Integrante D.
- **Depende de:** `bootstrap-proyecto` (contratos `Dictamen` y `Caso`, grafo de caso) y `agente-documental` (paquete de citas y verificador). Mientras tanto se desarrolla contra los stubs.
- **Origen:** cajas "Mediador" y "Precedentes" del artefacto; prompt "Mediador" v1; casos de test de humedad en el 4°B, caso sin artículo aplicable e instrucción oculta en un documento.
- **Decisión pendiente:** qué modelo de razonamiento del proxy del ITBA usar (`LLM_MODEL_REASONING`).
