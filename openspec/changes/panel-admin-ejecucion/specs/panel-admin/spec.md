## ADDED Requirements

### Requirement: Bandeja por estado
El panel SHALL listar, por consorcio, los casos y consultas que requieren al administrador, agrupados en: urgencias, pendientes de aprobación, consultas derivadas (sin fuente), pedidos de hablar con una persona e incompletos. Las urgencias SHALL mostrarse primero.

#### Scenario: Llega una urgencia
- **WHEN** el intake marca una urgencia de gas en el consorcio de demo
- **THEN** aparece arriba de todo en la bandeja, marcada como urgente

### Requirement: Lo escrito por la IA, marcado
En el detalle de un caso, el panel SHALL marcar visualmente todo contenido generado por IA y mostrar, por hipótesis, su responsable, sus citas con el fragmento, la evidencia a favor y en contra, qué la confirmaría y el resultado del verificador.

#### Scenario: Revisión de un dictamen
- **WHEN** el administrador abre el caso del 4°B
- **THEN** ve las dos hipótesis con sus fuentes, la recomendación de inspección y el mensaje al vecino, marcados como escritos por la IA

### Requirement: Aprobar, Modificar o Rechazar
El panel SHALL ofrecer tres acciones que retoman el grafo de caso con una `DecisionAdmin`: Aprobar (envía el mensaje propuesto), Modificar (abre el mensaje al vecino editable y luego aprueba) y Rechazar (exige un motivo y deja al administrador redactar su decisión o reclasificar el caso).

#### Scenario: Rechazo
- **WHEN** el administrador rechaza el dictamen sin escribir un motivo
- **THEN** el panel no permite confirmar hasta que cargue el motivo

#### Scenario: Modificar
- **WHEN** el administrador edita el mensaje al vecino y confirma
- **THEN** el vecino recibe el texto editado, no el original de la IA, y la decisión registra los dos

### Requirement: Respuesta manual a derivaciones
Para las consultas derivadas y los pedidos de hablar con una persona, el panel SHALL permitir responder manualmente al vecino por el mismo canal, y la respuesta SHALL identificarse como de la administración.

#### Scenario: Consulta sin fuente
- **WHEN** el administrador responde la consulta de la pileta desde el panel
- **THEN** el vecino la recibe en Telegram identificada como respuesta de la administración
