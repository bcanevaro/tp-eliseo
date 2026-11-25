## Purpose

Que el administrador cargue y mantenga desde el panel el reglamento y las actas de cada consorcio, con la validación necesaria para que el Documental, el verificador de citas y el Mediador los puedan citar.

## ADDED Requirements

### Requirement: Carga de documentos
El administrador SHALL poder subir, para un consorcio suyo, un reglamento o un acta en el formato Markdown del corpus (secciones `REG-<n>` o `ACTA-<fecha>#<punto>` con título). Cada consorcio SHALL tener como máximo un reglamento vigente y cualquier cantidad de actas.

#### Scenario: Primer reglamento de un edificio nuevo
- **WHEN** la administradora sube el reglamento del Consorcio Corrientes 1200 con 30 artículos y confirma
- **THEN** una consulta de un vecino de ese consorcio sobre un tema del reglamento responde citando el `REG-<n>` correspondiente

### Requirement: Validación antes de guardar
Antes de guardar, el sistema SHALL validar el documento y, si falla, no guardar nada y listar cada error con su línea. SHALL rechazar: secciones sin id canónico, ids repetidos, un acta sin fecha o con una fecha distinta de la de sus ids, y un acta que dice modificar un `REG-<n>` que no existe en el reglamento vigente.

#### Scenario: Acta que modifica un artículo inexistente
- **WHEN** la administradora sube un acta cuyo punto 2 dice modificar el `REG-40` y el reglamento tiene 30 artículos
- **THEN** el sistema no la guarda y muestra que el `REG-40` no existe

#### Scenario: Archivo que no es del formato
- **WHEN** la administradora sube un PDF o un Markdown sin secciones con id
- **THEN** el sistema no lo guarda y explica el formato esperado con un ejemplo

### Requirement: Vista previa de la partición
Un documento válido SHALL mostrarse partido como lo va a usar el sistema (un bloque por artículo o por punto del acta, con su id, su título y, en las actas, el artículo que modifican) antes de que el administrador confirme. Cancelar SHALL no dejar ningún rastro.

#### Scenario: Confirmar después de revisar
- **WHEN** la administradora sube un acta válida
- **THEN** ve sus puntos con ids y el artículo que modifica cada uno, y el acta solo queda disponible para los agentes después de tocar "Confirmar"

### Requirement: Disponible para los agentes al confirmar
Al confirmar, el documento SHALL quedar disponible para el Documental, el verificador de citas y el Mediador del consorcio, incluida la vigencia que resulta de las actas que modifican artículos. Si la indexación para la búsqueda falla, el documento SHALL quedar guardado y marcado como pendiente de indexar, el panel SHALL indicarlo y SHALL permitir reintentar.

#### Scenario: Acta que reemplaza un artículo
- **WHEN** se confirma un acta que reemplaza el `REG-14` (horario de obras)
- **THEN** la consulta "¿hasta qué hora se puede hacer obra?" de un vecino de ese consorcio cita el acta y no el `REG-14`

#### Scenario: Servicio de búsqueda caído
- **WHEN** se confirma un documento mientras el servicio de vectores no responde
- **THEN** el documento queda guardado, el panel lo muestra como "pendiente de indexar" con un botón para reintentar, y el Documental lo encuentra igual por búsqueda léxica

### Requirement: Reemplazo y baja de documentos
El administrador SHALL poder reemplazar el reglamento (subir una versión nueva) y dar de baja un acta, con confirmación. Lo reemplazado o dado de baja SHALL dejar de aparecer en las búsquedas y en las citas nuevas. Las citas de casos ya decididos SHALL seguir mostrando el texto que se citó en su momento.

#### Scenario: Baja de un acta citada en un caso viejo
- **WHEN** la administradora da de baja un acta que fue citada en un dictamen ya aprobado
- **THEN** las consultas nuevas no la citan y el detalle del caso viejo sigue mostrando el texto citado

#### Scenario: Acta de la que depende la vigencia
- **WHEN** la administradora da de baja el acta que reemplazaba el `REG-14`
- **THEN** el `REG-14` vuelve a estar vigente para las consultas nuevas

### Requirement: Documentos aislados por consorcio
Un documento SHALL pertenecer a un solo consorcio y SHALL ser visible solo para los vecinos de ese consorcio y para las cuentas de su administración. Dos consorcios SHALL poder tener ids iguales (por ejemplo, ambos un `REG-14`) sin pisarse.

#### Scenario: Mismo id en dos edificios
- **WHEN** dos consorcios de administraciones distintas tienen cada uno su `REG-14`
- **THEN** cada vecino recibe solo el `REG-14` de su consorcio y ninguna cuenta ve el documento del otro

### Requirement: Archivo original conservado
El sistema SHALL guardar el archivo original subido, asociado al consorcio y a la cuenta que lo subió, y el panel SHALL permitir descargarlo desde la lista de documentos del consorcio.

#### Scenario: Descarga del original
- **WHEN** la administradora abre la lista de documentos de un consorcio
- **THEN** ve cada documento con su fecha de carga, quién lo subió, su estado de indexación y un enlace al archivo original
