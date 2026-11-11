## Why

El panel es el único approval boundary del sistema: nada que asigne responsabilidad sale sin la firma del administrador. Es también la segunda superficie del producto (la administradora "decide rápido y con respaldo") y el destino de toda abstención. La ejecución es la parte irreversible (enviar al vecino, pedir inspección), así que va junta con el panel que la dispara. La evaluación de punta a punta va en este change porque es quien integra todo al final.

## What Changes

- Panel en Streamlit: bandeja de casos y consultas derivadas por estado, detalle del dictamen con lo escrito por la IA marcado, hipótesis con sus fuentes, y acciones Aprobar, Modificar o Rechazar.
- Retomar el grafo de caso con la `DecisionAdmin` (`Command(resume=...)`) sobre el checkpointer compartido.
- Bandeja de urgencias y de conversaciones que pidieron hablar con una persona, con respuesta manual al vecino.
- Ejecución: confirmación explícita, envío del mensaje al vecino por Telegram, creación del pedido de inspección o de trabajo en la base, idempotencia por id de dictamen y cierre del caso.
- Evaluación de punta a punta en LangSmith con los 12 casos del artefacto, y registro de motivos de rechazo para versionar prompts.
- Reemplaza los stubs `panel`, `derivar`, `urgencia` (aviso) y `ejecucion` del bootstrap.

## Capabilities

### New Capabilities

- `panel-admin`: la superficie del administrador y sus puntos de control.
- `ejecucion`: las acciones irreversibles que siguen a una aprobación.
- `evaluacion-e2e`: el dataset de casos del artefacto corrido contra el sistema completo.

### Modified Capabilities

(ninguna)

## Impact

- **Dueño:** Integrante E.
- **Depende de:** `bootstrap-proyecto` (grafo de caso con `interrupt`, contratos `Dictamen` y `DecisionAdmin`), `canal-telegram-intake` (envío al vecino) y `agente-gastos` (motor, si la ejecución prorratea un trabajo). Se desarrolla contra dictámenes de fixture.
- **Origen:** caja "Panel del administrador" y "Ejecución" del artefacto; pasos 13 a 19 del Target State Workflow; wireframes del panel; tabla de casos de test y self-check.
- **Dependencias nuevas:** `streamlit`.
