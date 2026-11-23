## ADDED Requirements

### Requirement: Tool de precedentes, no agente
La consulta de precedentes SHALL ser una tool `get_precedentes(consorcio_id, unidad_id, tipo, descripcion)` sin LLM, que combina filtros estructurados (consorcio y tipo de reclamo) con similitud semántica sobre la descripción del reclamo y un rerank, prioriza los de la misma columna o ubicación, y devuelve los precedentes con su id `PREC-<n>`, descripción, resolución y fecha. El consorcio SHALL fijarlo el código desde el estado del grafo, nunca el LLM. Sin acceso a Pinecone SHALL responder desde la base con los mismos filtros.

#### Scenario: Filtración en la misma columna
- **WHEN** se consultan precedentes para una filtración en el 4°B
- **THEN** el resultado incluye `PREC-2201` (filtración en el 3°B por la montante B, a cargo del consorcio) antes que los de otras columnas

#### Scenario: Otro consorcio
- **WHEN** otro consorcio tiene un precedente casi idéntico
- **THEN** no aparece en el resultado

#### Scenario: Sin Pinecone
- **WHEN** no hay API key de Pinecone y se consultan precedentes para una filtración en el 4°B
- **THEN** el resultado sale de la base e incluye `PREC-2201` primero

### Requirement: Escritura solo con aprobación
Un precedente SHALL escribirse únicamente cuando el administrador aprueba (o modifica y aprueba) un dictamen, y SHALL guardar su procedencia: caso_id, dictamen, decisión, admin y fecha. La base SHALL ser la fuente de verdad; el precedente SHALL indexarse además en Pinecone, y si la indexación falla la aprobación no SHALL bloquearse y la ingesta SHALL poder reconstruir el índice desde la base. Los dictámenes rechazados no SHALL convertirse en precedentes.

#### Scenario: Dictamen rechazado
- **WHEN** el administrador rechaza un dictamen
- **THEN** no se crea ningún precedente y el motivo del rechazo queda registrado en la decisión

#### Scenario: Dictamen aprobado
- **WHEN** el administrador aprueba el dictamen del caso 17
- **THEN** se crea un precedente con procedencia del caso 17, que aparece en consultas futuras del mismo consorcio

#### Scenario: Falla la indexación
- **WHEN** el administrador aprueba un dictamen y Pinecone no responde
- **THEN** la aprobación se completa, el precedente queda en la base y la próxima ingesta lo indexa

### Requirement: Retención
Los precedentes no SHALL vencer ni perder peso por antigüedad: borrarlos es decisión de la administración. Cada precedente SHALL llegar al Mediador con su fecha y como antecedente, no como norma: si el artículo en que se apoyó cambió, manda el artículo vigente.

#### Scenario: Precedente con un artículo modificado
- **WHEN** un precedente se resolvió con un artículo que un acta posterior modificó
- **THEN** el precedente sigue apareciendo con su fecha, y el dictamen cita el artículo vigente para la regla
