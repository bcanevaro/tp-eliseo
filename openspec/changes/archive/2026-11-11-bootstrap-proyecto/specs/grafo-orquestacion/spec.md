## ADDED Requirements

### Requirement: Grafo de conversación por vecino
El sistema SHALL procesar cada mensaje entrante con un grafo de conversación de LangGraph cuyo `thread_id` es `<telefono>:<consorcio_id>`. El estado SHALL persistir en un checkpointer SQLite, de modo que un reclamo a medio completar sobreviva al reinicio del proceso. El historial del hilo SHALL expirar tras un TTL configurable (por defecto 7 días).

#### Scenario: Reclamo en varios mensajes
- **WHEN** el vecino escribe "hay humedad", el bot pide el ambiente y el vecino contesta "en el baño" en un mensaje posterior
- **THEN** el segundo mensaje se procesa en el mismo hilo y completa el mismo reclamo

### Requirement: Identificación antes que todo
El primer nodo del grafo de conversación SHALL resolver la `Identidad` por teléfono. Si el teléfono no está registrado, el grafo SHALL responder que la administración tiene que validarlo y SHALL terminar sin invocar ningún LLM ni mostrar datos.

#### Scenario: Teléfono no registrado
- **WHEN** escribe un teléfono que no está en la plataforma
- **THEN** el bot pide la validación de la administración y no se ejecuta el intake

### Requirement: Ruteo por intent decidido por el workflow
Después del intake, el siguiente paso SHALL decidirlo el workflow según `ResultadoIntake`, no un LLM:
- REGLAMENTO → Documental → verificador de citas → respuesta con cita, o derivación al panel si no hay cita válida;
- GASTOS → Gastos → respuesta con montos de la base;
- RECLAMO → completar datos faltantes → registrar caso → lanzar el grafo de caso;
- UNKNOWN → repreguntar una vez; si sigue sin entenderse, derivar al panel.
Si `multi` trae más intents, el grafo SHALL procesar cada uno por su rama (fan-out) y responder por separado.

#### Scenario: Consulta de reglamento sin fuente
- **WHEN** el vecino pregunta "¿Puedo poner una pileta en la terraza?" y Documental no encuentra cita válida
- **THEN** el vecino recibe el aviso de que lo responde la administración y la consulta aparece en el panel

#### Scenario: No se entiende dos veces
- **WHEN** el intake devuelve UNKNOWN en dos mensajes seguidos del mismo hilo
- **THEN** el grafo deriva al panel en lugar de repreguntar por tercera vez

### Requirement: Urgencias sin espera
Si `ResultadoIntake.urgencia` es verdadero (por ejemplo, olor a gas o una persona atrapada en el ascensor), el grafo SHALL avisar de inmediato al administrador y responder al vecino con el teléfono de emergencias, antes y con independencia de cualquier otro paso.

#### Scenario: Olor a gas
- **WHEN** el vecino escribe "hay mucho olor a gas en el palier"
- **THEN** el administrador recibe un aviso urgente y el vecino recibe el número de emergencias en la misma respuesta, sin esperar un dictamen

### Requirement: Grafo de caso con aprobación humana
Cada reclamo registrado SHALL correr en su propio grafo de caso, con `thread_id = caso:<caso_id>`, que sigue la secuencia fija intake → [Documental ‖ Precedentes] → Mediador ⇄ verificador (máximo 2 vueltas) → panel → ejecución. El paso de panel SHALL usar `interrupt` de LangGraph y el grafo SHALL retomarse solo con una `DecisionAdmin`.

#### Scenario: El vecino escribe mientras el caso espera aprobación
- **WHEN** el caso 17 está detenido en el panel y el vecino manda otro mensaje
- **THEN** el mensaje se procesa en el grafo de conversación del vecino, sin destrabar ni modificar el grafo del caso 17

#### Scenario: Nada sale sin decisión
- **WHEN** el Mediador produjo un dictamen que pasó el verificador
- **THEN** el grafo de caso queda en PENDIENTE_APROBACION y no se envía ningún mensaje al vecino hasta recibir la `DecisionAdmin`

### Requirement: Mensajes fuera de turno por outbox
Los mensajes que no son respuesta inmediata a un mensaje del vecino (resolución de un caso, aviso de urgencia al administrador, respuesta manual del panel) SHALL encolarse en la outbox de la base con una clave de idempotencia, y el proceso del canal SHALL enviarlos. Encolar dos veces con la misma clave no SHALL duplicar el envío.

#### Scenario: Aprobación desde el panel
- **WHEN** el panel aprueba el dictamen del caso 17
- **THEN** el mensaje al vecino queda en la outbox con la clave del dictamen, y el bot lo envía aunque el panel corra en otro proceso

### Requirement: Nodos reemplazables
Cada caja de la arquitectura SHALL ser un nodo con una función de entrada y salida tipadas con los contratos compartidos. El bootstrap SHALL entregar un stub determinístico por nodo, de modo que el grafo completo corra de punta a punta sin LLM y cada integrante pueda reemplazar su nodo sin tocar los demás.

#### Scenario: Corrida de punta a punta con stubs
- **WHEN** se corre el test de humo con los stubs y un mensaje de reclamo
- **THEN** el grafo de conversación registra un caso, el grafo de caso se detiene en el panel, y al enviarle una `DecisionAdmin` de APROBAR llega a ejecución
