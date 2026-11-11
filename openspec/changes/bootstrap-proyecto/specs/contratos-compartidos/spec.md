## ADDED Requirements

### Requirement: Un único módulo de contratos
El sistema SHALL definir en `eliseo/schemas/` todos los modelos Pydantic que cruzan una frontera entre componentes (canal, intake, agentes, verificador, panel y ejecución). Ningún componente SHALL definir su propia versión de un tipo que ya está ahí; si necesita un campo nuevo, lo agrega en este módulo mediante un change.

#### Scenario: Un componente necesita un campo nuevo
- **WHEN** un integrante necesita que el resultado del intake lleve un dato más
- **THEN** agrega el campo en `eliseo/schemas/` en su change y los tests de contratos siguen pasando para todos los consumidores

### Requirement: Mensaje entrante e identidad
El sistema SHALL representar cada mensaje del canal como `MensajeEntrante` (canal, chat_id, usuario_canal_id, texto, adjuntos, timestamp) y la identidad resuelta del vecino como `Identidad` (telefono, unidad_id, consorcio_id, nombre). La `Identidad` SHALL resolverse por código a partir del teléfono registrado en la plataforma, nunca a partir de lo que escribe el vecino.

#### Scenario: El vecino dice ser de otra unidad
- **WHEN** un vecino registrado como 4°B escribe "soy el del 3°A"
- **THEN** la `Identidad` del hilo sigue siendo 4°B, porque sale del teléfono y no del texto

### Requirement: Resultado del intake
El sistema SHALL modelar la salida del Intake + Router como `ResultadoIntake` con: `intent` (REGLAMENTO, GASTOS, RECLAMO o UNKNOWN), `multi` (lista de intents adicionales del mismo mensaje), `campos_faltantes`, `urgencia` (bool), `pregunta_reescrita` y, si el intent es RECLAMO, un `ReclamoBorrador` (ambiente, descripcion, desde_cuando, gotea, fotos).

#### Scenario: Mensaje con dos temas
- **WHEN** el vecino escribe "Se me llueve el baño y quiero saber cuánto se pagó el plomero"
- **THEN** el `ResultadoIntake` válido tiene `intent = RECLAMO` y `multi = [GASTOS]`

### Requirement: Cita verificable
El sistema SHALL representar toda fuente como `Cita` con `documento` (Reglamento, Acta, Liquidacion, Factura o Precedente), `referencia` (el id canónico del corpus, por ejemplo `REG-22`, `ACTA-2024-11-10#3`, `LIQ-2026-10`, `FAC-0042`, `PREC-2201`) y `fragmento` (texto literal de la fuente). Los ids canónicos SHALL ser los mismos en el corpus, en Pinecone y en la base, para que el verificador pueda resolverlos.

#### Scenario: Cita con referencia inexistente
- **WHEN** un agente devuelve una `Cita` con `referencia = "REG-99"` y el reglamento no tiene artículo 99
- **THEN** el modelo se construye igual, pero el verificador de citas la marca como inválida al no encontrar el id en el corpus

### Requirement: Respuestas de los agentes de consulta
El sistema SHALL modelar la salida de Documental como `RespuestaDocumental` (respuesta, citas, suficiente) y la de Gastos como `RespuestaGastos` (respuesta, lineas con concepto, monto y comprobante). El mensaje final al vecino SHALL seguir el formato del master prompt de respuestas: `RespuestaVecino` con respuesta de hasta 600 caracteres, citas, derivar y motivo_derivacion.

#### Scenario: Respuesta demasiado larga
- **WHEN** el LLM devuelve una `respuesta` de 800 caracteres
- **THEN** la validación de `RespuestaVecino` falla y el nodo reintenta o deriva, sin mandar el texto al vecino

### Requirement: Caso y estados
El sistema SHALL modelar cada reclamo como `Caso` (caso_id, consorcio_id, unidad_id, reclamo, estado, timestamps) con `estado` en: INCOMPLETO, REGISTRADO, EN_ANALISIS, PENDIENTE_APROBACION, APROBADO, RECHAZADO, CERRADO. Las transiciones válidas SHALL estar definidas en un solo lugar y una transición inválida SHALL lanzar un error.

#### Scenario: Transición inválida
- **WHEN** el código intenta pasar un caso de REGISTRADO a APROBADO sin dictamen
- **THEN** se lanza un error de transición y el caso no cambia de estado

### Requirement: Dictamen y decisión del administrador
El sistema SHALL modelar el borrador del Mediador como `Dictamen` según el master prompt del Mediador v1 (hechos, afirmaciones_sin_evidencia, hipotesis con id, responsable, descripcion, citas, a_favor, en_contra y confirmaria, recomendacion con tipo `asignar` o `inspeccion`, y mensaje_vecino). La respuesta del panel SHALL modelarse como `DecisionAdmin` (accion APROBAR, MODIFICAR o RECHAZAR, mensaje_final, motivo, admin_id).

#### Scenario: Recomendación de asignar sin hipótesis
- **WHEN** un `Dictamen` trae `recomendacion.tipo = "asignar"` y `recomendacion.hipotesis = null`
- **THEN** la validación del modelo falla

#### Scenario: Rechazo sin motivo
- **WHEN** el panel envía una `DecisionAdmin` con `accion = RECHAZAR` y sin `motivo`
- **THEN** la validación falla, porque el motivo de rechazo se guarda para refinar el prompt
