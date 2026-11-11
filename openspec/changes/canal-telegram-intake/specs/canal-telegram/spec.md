## ADDED Requirements

### Requirement: Vinculación del teléfono
La primera vez que un usuario de Telegram escribe, el bot SHALL pedirle que comparta su número con el botón de contacto de Telegram y SHALL aceptar solo el contacto del propio usuario (no uno reenviado de otra persona). El vínculo `usuario_canal_id → telefono` SHALL guardarse en la base y reutilizarse en los mensajes siguientes.

#### Scenario: Primer contacto
- **WHEN** un usuario nuevo escribe "hola"
- **THEN** el bot explica que necesita su número para identificar la unidad y muestra el botón de compartir contacto

#### Scenario: Contacto de otra persona
- **WHEN** el usuario comparte un contacto cuyo id de usuario no es el suyo
- **THEN** el bot rechaza el vínculo y vuelve a pedir su propio número

### Requirement: Presentación como asistente
El bot SHALL presentarse como asistente de la administración y nunca como el administrador. Tras identificar la unidad, SHALL saludar con el nombre y la unidad que salen de la plataforma, y ofrecer los botones "Hacer un reclamo", "Consultar el reglamento" y "Mis expensas", además de aceptar texto libre.

#### Scenario: Saludo identificado
- **WHEN** el vecino del 4°B, ya vinculado, escribe "hola"
- **THEN** el bot saluda con su nombre y "4°B", se presenta como asistente y muestra los tres botones

### Requirement: Salida a una persona siempre disponible
El bot SHALL ofrecer en todo momento la opción "Hablar con la administración". Al elegirla, la conversación SHALL aparecer en el panel como pendiente y el vecino SHALL recibir aviso de que lo contacta una persona.

#### Scenario: El vecino pide hablar con alguien en medio de un reclamo
- **WHEN** el vecino toca "Hablar con la administración" mientras el bot le pide datos de un reclamo
- **THEN** el reclamo queda guardado como está, la conversación cae en el panel y el bot deja de repreguntar

### Requirement: Estado visible
Mientras el grafo procesa un mensaje, el bot SHALL mostrar un indicador de estado acorde al paso ("Buscando en el reglamento…", "Revisando tu cuenta…", "Registrando tu reclamo…"). Al registrar un caso SHALL informar su número.

#### Scenario: Consulta de reglamento
- **WHEN** el vecino pregunta por el reglamento
- **THEN** ve "Buscando en el reglamento…" antes de recibir la respuesta con cita

### Requirement: Fotos como evidencia
El canal SHALL aceptar fotos, guardarlas asociadas al hilo y pasarlas como `Adjunto` al intake. Los mensajes de audio SHALL responderse pidiendo el texto, salvo que se implemente la transcripción.

#### Scenario: Foto de la humedad
- **WHEN** el vecino manda una foto mientras completa un reclamo
- **THEN** la foto queda adjunta al `ReclamoBorrador` y el campo "foto" deja de figurar como faltante
