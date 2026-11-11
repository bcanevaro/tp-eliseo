## ADDED Requirements

### Requirement: Confirmación antes de lo irreversible
Antes de enviar un mensaje al vecino o crear un pedido de inspección o de trabajo, el panel SHALL pedir una confirmación explícita que muestre exactamente qué se va a enviar y a quién.

#### Scenario: Cancelar en la confirmación
- **WHEN** el administrador aprueba pero cancela en la confirmación
- **THEN** no se envía nada y el caso sigue en PENDIENTE_APROBACION

### Requirement: Idempotencia por dictamen
Cada acción de ejecución SHALL llevar el id del dictamen como clave de idempotencia. Reintentar la misma decisión no SHALL duplicar el mensaje ni el pedido.

#### Scenario: Doble click en Aprobar
- **WHEN** se procesa dos veces la misma `DecisionAdmin` de APROBAR
- **THEN** el vecino recibe un solo mensaje y hay un solo pedido de inspección

### Requirement: Envío y cierre
Tras la aprobación, la ejecución SHALL enviar al vecino el mensaje final con las fuentes al final, crear el pedido que corresponda a la recomendación, actualizar el estado del caso y, al cerrarlo, disparar la escritura del precedente.

#### Scenario: Aprobación de inspección
- **WHEN** se aprueba un dictamen con recomendación de inspección
- **THEN** el vecino recibe el mensaje con el número de caso y las fuentes, se crea un pedido de inspección en la base y el caso pasa a APROBADO

### Requirement: Aviso de urgencias
Ante una urgencia, la ejecución SHALL avisar al administrador por un canal inmediato (mensaje de Telegram al chat de la administración configurado) además de la bandeja.

#### Scenario: Olor a gas
- **WHEN** entra una urgencia de gas
- **THEN** el chat de la administración recibe un aviso con la unidad y el texto del vecino en segundos
