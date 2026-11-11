## ADDED Requirements

### Requirement: Tool de precedentes, no agente
La consulta de precedentes SHALL ser una tool `get_precedentes(consorcio_id, unidad_id, tipo)` sin LLM, que combina filtros estructurados (consorcio, tipo de reclamo, columna o ubicación) con similitud semántica sobre la descripción del reclamo, y devuelve los precedentes con su id `PREC-<n>`, resumen, resolución y fecha.

#### Scenario: Filtración en la misma columna
- **WHEN** se consultan precedentes para una filtración en el 4°B
- **THEN** el resultado incluye `PREC-2201` (filtración en el 3°B por la montante B, a cargo del consorcio)

#### Scenario: Otro consorcio
- **WHEN** otro consorcio tiene un precedente casi idéntico
- **THEN** no aparece en el resultado

### Requirement: Escritura solo con aprobación
Un precedente SHALL escribirse únicamente cuando el administrador aprueba (o modifica y aprueba) un dictamen, y SHALL guardar su procedencia: caso_id, dictamen, decisión, admin y fecha. Los dictámenes rechazados no SHALL convertirse en precedentes.

#### Scenario: Dictamen rechazado
- **WHEN** el administrador rechaza un dictamen
- **THEN** no se crea ningún precedente y el motivo del rechazo queda registrado en la decisión

#### Scenario: Dictamen aprobado
- **WHEN** el administrador aprueba el dictamen del caso 17
- **THEN** se crea un precedente con procedencia del caso 17, que aparece en consultas futuras del mismo consorcio
