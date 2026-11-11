## ADDED Requirements

### Requirement: Dataset de casos del artefacto
El sistema SHALL tener en LangSmith un dataset con los 12 casos del artefacto (3 de uso, 4 de borde y 5 negativos), creado desde `evaluation/casos.jsonl`, cada uno con el input, el comportamiento esperado y los criterios (relevancia, factualidad, tono, estructura, eficiencia, terminología).

#### Scenario: Carga del dataset
- **WHEN** se corre el script de carga
- **THEN** el dataset tiene 12 ejemplos con la categoría (uso, borde o negativo) como metadata

### Requirement: Corrida contra el sistema completo
La evaluación SHALL correr cada caso contra el grafo real, con repeticiones configurables, y reportar por caso si pasa cada criterio, combinando evaluadores determinísticos (schema, verificador de citas, montos en la base, ausencia de datos de otras unidades) con un juez LLM para tono y relevancia.

#### Scenario: Negativos
- **WHEN** se corre la evaluación
- **THEN** el reporte muestra cuántos de los 5 casos negativos pasan, que es la condición del self-check "el master prompt sobrevive una ronda de negativos"

### Requirement: Versionado de prompts guiado por fallas
Cada cambio de un master prompt SHALL registrarse en `prompts/CHANGELOG.md` con versión, fecha, cambio y por qué, citando el caso de evaluación o el motivo de rechazo del panel que lo motivó, y SHALL compararse con la versión anterior en LangSmith.

#### Scenario: Nueva versión del prompt del vecino
- **WHEN** se crea `vecino.v2.md`
- **THEN** el CHANGELOG explica el motivo y hay un experimento de LangSmith que compara v1 y v2 sobre el mismo dataset
