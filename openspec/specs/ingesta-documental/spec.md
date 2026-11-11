# ingesta-documental Specification

## Purpose
TBD - created by archiving change agente-documental. Update Purpose after archive.
## Requirements
### Requirement: Chunking por unidad jurídica
La ingesta SHALL partir el reglamento en un chunk por artículo y cada acta en un chunk por punto del orden del día. Ningún chunk SHALL mezclar dos artículos o dos puntos.

#### Scenario: Artículo largo
- **WHEN** un artículo tiene varios incisos
- **THEN** queda en un solo chunk con su id `REG-<n>`, o en varios chunks que comparten el mismo id y se citan como ese artículo

### Requirement: Metadata obligatoria
Cada chunk SHALL guardar `consorcio_id`, `doc_tipo` (reglamento o acta), `ref` (id canónico), `fecha`, `vigente` (bool) y, si es un acta que modifica un artículo, `modifica` con el `REG-<n>`. Un artículo modificado por un acta posterior SHALL seguir indexado con `vigente = false` para el texto reemplazado.

#### Scenario: Acta que modifica un artículo
- **WHEN** se ingiere un acta cuyo punto 3 modifica el artículo 22
- **THEN** el chunk del acta tiene `modifica = "REG-22"` y el chunk de `REG-22` queda marcado con la modificación

### Requirement: Ingesta idempotente
`scripts/ingest.py` SHALL poder correrse varias veces sobre el mismo consorcio sin duplicar vectores, usando como id del vector `<consorcio_id>:<ref>` (el id canónico prefijado por el consorcio, para que dos consorcios con un `REG-14` no se pisen).

#### Scenario: Reingesta
- **WHEN** se corre la ingesta dos veces sobre el Consorcio Rivadavia 4520
- **THEN** la cantidad de vectores en el namespace `documentos` con ese `consorcio_id` no cambia

