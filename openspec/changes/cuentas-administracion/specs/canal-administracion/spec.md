## Purpose

Que un único bot de Telegram atienda a los vecinos de todas las administraciones y entregue las urgencias y avisos de cada consorcio solo en el chat de la administración que corresponde.

## ADDED Requirements

### Requirement: Un bot para todas las administraciones
El sistema SHALL usar un único bot de Telegram para todos los consorcios. La administración y el consorcio de un vecino SHALL salir de su teléfono registrado, nunca del texto ni de qué bot usó.

#### Scenario: Vecinos de dos administraciones
- **WHEN** un vecino de la Administración Méndez y uno de otra administración escriben al mismo bot
- **THEN** cada uno recibe respuestas solo con los documentos y gastos de su consorcio

### Requirement: Presentación con la administración del vecino
Al saludar a un vecino identificado, el bot SHALL presentarse como asistente de la administración de ese vecino, con el nombre que figura en la base.

#### Scenario: Saludo
- **WHEN** el vecino del 4°B del Consorcio Rivadavia 4520 escribe "hola"
- **THEN** el bot se presenta como asistente de la Administración Méndez

### Requirement: Vinculación del chat de la administración
El panel SHALL generar, para la administración de la sesión, un código de un solo uso que vence a los 15 minutos. Enviar ese código al bot desde un chat SHALL dejar ese chat como chat de avisos de la administración, reemplazando al anterior. Un código vencido, usado o inexistente SHALL rechazarse sin dar detalles.

#### Scenario: Vincular el chat
- **WHEN** la administradora genera un código en el panel y lo envía al bot con `/admin <código>` desde su Telegram
- **THEN** el bot confirma la vinculación con el nombre de la administración y el panel muestra el chat como vinculado

#### Scenario: Código vencido
- **WHEN** alguien envía al bot un código generado hace más de 15 minutos
- **THEN** el bot responde que el código no es válido y no cambia ningún vínculo

### Requirement: Avisos al chat de su administración
Las urgencias, derivaciones con aviso inmediato y demás mensajes dirigidos a la administración SHALL enviarse solo al chat vinculado de la administración del consorcio. Si la administración no tiene chat vinculado, el aviso SHALL quedar pendiente y el panel SHALL mostrar que falta vincularlo.

#### Scenario: Urgencia en un consorcio
- **WHEN** un vecino del Consorcio Rivadavia 4520 avisa de olor a gas
- **THEN** el aviso llega al chat de la Administración Méndez y a ningún otro

#### Scenario: Administración sin chat vinculado
- **WHEN** hay una urgencia en un consorcio cuya administración no vinculó su chat
- **THEN** el aviso queda pendiente, la urgencia aparece primera en la bandeja del panel y el panel indica que el chat de avisos no está vinculado

### Requirement: Chats separados de vecino y administración
Un chat vinculado como chat de avisos de una administración SHALL seguir pudiendo usarse como vecino solo si el teléfono de esa cuenta de Telegram está en el padrón. Un chat de avisos SHALL no dar acceso a datos de ningún consorcio por sí mismo.

#### Scenario: Administradora que escribe consultas
- **WHEN** la administradora, cuyo teléfono no está en el padrón, escribe "¿cuánto debo?" en el chat de avisos
- **THEN** el bot le pide compartir su contacto y responde que su número no está registrado como vecino
