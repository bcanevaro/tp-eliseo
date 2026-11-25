## Purpose

Que el administrador mantenga desde el panel sus edificios, las unidades de cada uno y los vecinos con su teléfono de Telegram, y que esos cambios definan quién puede usar el bot y qué ve.

## ADDED Requirements

### Requirement: Alta de consorcio
El administrador SHALL poder dar de alta un consorcio con nombre, dirección y teléfono de emergencias, y sus unidades (piso, departamento y coeficiente). El consorcio SHALL quedar asociado a la administración de la sesión.

#### Scenario: Edificio nuevo
- **WHEN** la administradora da de alta "Consorcio Corrientes 1200" con 8 unidades cuyos coeficientes suman 1
- **THEN** el consorcio aparece en su selector, con sus 8 unidades, y no aparece en el de ninguna otra administración

### Requirement: Coeficientes consistentes
Al guardar las unidades de un consorcio, el sistema SHALL rechazar el guardado si los coeficientes no suman 1 con tolerancia de 0,0001, e indicar la suma actual.

#### Scenario: Coeficientes que no cierran
- **WHEN** la administradora guarda unidades cuyos coeficientes suman 0,97
- **THEN** el sistema no guarda nada y muestra que la suma es 0,97 y debe ser 1

### Requirement: Edición de consorcio y unidades
El administrador SHALL poder editar los datos de un consorcio y agregar, editar o quitar unidades. No SHALL poder quitar una unidad que tiene vecinos o casos.

#### Scenario: Unidad con vecino
- **WHEN** la administradora intenta quitar el 4°B, que tiene un vecino registrado
- **THEN** el sistema lo impide e indica que primero hay que dar de baja al vecino

### Requirement: Baja de consorcio
El administrador SHALL poder dar de baja un consorcio con confirmación explícita. La baja SHALL ser lógica: el historial de casos y decisiones se conserva, sus vecinos dejan de poder usar el bot y sus documentos dejan de estar en la búsqueda.

#### Scenario: Baja confirmada
- **WHEN** la administradora da de baja un consorcio y confirma
- **THEN** el consorcio desaparece del selector, un vecino de ese consorcio que escribe al bot recibe el mensaje de teléfono no registrado, y una búsqueda del Documental para ese consorcio no devuelve documentos

#### Scenario: Baja cancelada
- **WHEN** la administradora toca "Dar de baja" y después cancela
- **THEN** nada cambia

### Requirement: Alta de vecino
El administrador SHALL poder dar de alta un vecino con nombre, unidad de uno de sus consorcios y teléfono. El teléfono SHALL guardarse normalizado en formato internacional y SHALL ser único en todo el sistema.

#### Scenario: Vecino nuevo
- **WHEN** la administradora da de alta a "Ana Pérez" en el 2°A con el teléfono "11 5555-1234"
- **THEN** el vecino queda con el teléfono "+5491155551234" y, cuando Ana comparte su contacto en el bot, la saluda por su nombre y "2°A"

#### Scenario: Teléfono ya registrado
- **WHEN** la administradora da de alta un teléfono que ya pertenece a un vecino de cualquier consorcio
- **THEN** el sistema no lo guarda e indica que el teléfono ya está registrado, sin decir en qué consorcio ni a nombre de quién

#### Scenario: Teléfono inválido
- **WHEN** el teléfono no se puede normalizar a un número argentino válido
- **THEN** el sistema no lo guarda y lo indica

### Requirement: Edición de vecino
El administrador SHALL poder cambiar el nombre, la unidad o el teléfono de un vecino. Si cambia el teléfono, el vínculo de Telegram anterior SHALL borrarse y el vecino SHALL volver a compartir su contacto.

#### Scenario: Cambio de teléfono
- **WHEN** la administradora cambia el teléfono de un vecino ya vinculado
- **THEN** el próximo mensaje desde la cuenta de Telegram vieja recibe el pedido de compartir contacto

### Requirement: Baja de vecino
El administrador SHALL poder dar de baja un vecino con confirmación. La baja SHALL borrar su vínculo de Telegram y cortarle el acceso al bot desde su próximo mensaje. Sus casos SHALL conservarse en el historial del consorcio.

#### Scenario: Vecino dado de baja
- **WHEN** la administradora da de baja al vecino del 3°A y él escribe "hola" al bot
- **THEN** el bot le pide compartir su contacto y, si lo comparte, responde que su número no está registrado; sus casos anteriores siguen en el historial del panel

#### Scenario: Conversación en curso
- **WHEN** se da de baja a un vecino que tenía un reclamo a medio completar
- **THEN** el bot no le repregunta más y el reclamo incompleto queda en el panel

### Requirement: Padrón y mínimo privilegio del bot
Lo que el bot y los agentes pueden ver de un vecino SHALL depender solo del padrón vigente: su unidad, su consorcio y los documentos y gastos de ese consorcio. Un cambio en el padrón SHALL valer desde el próximo mensaje, sin reiniciar el bot.

#### Scenario: Mudanza a otro edificio de la misma administración
- **WHEN** la administradora cambia a un vecino del Consorcio Rivadavia 4520 a una unidad del Consorcio Corrientes 1200
- **THEN** su próxima consulta de reglamento responde con el reglamento de Corrientes 1200 y su consulta de expensas muestra los gastos de Corrientes 1200
