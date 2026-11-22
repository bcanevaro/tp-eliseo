## Context

El panel es el único approval boundary del sistema y la ejecución es la única parte irreversible.
El grafo de caso ya se detiene con `interrupt` en el nodo `panel` y se retoma con
`runtime.retomar_caso(caso_id, DecisionAdmin)` sobre el checkpointer SQLite compartido (bootstrap).
El bot y el panel son procesos distintos: todo lo que sale hacia una persona fuera del turno
pasa por la tabla `outbox`.

## Goals / Non-Goals

**Goals:** bandeja por estado con urgencias primero; detalle del dictamen con lo escrito por la IA
marcado y cada cita con su fuente y el resultado del verificador; Aprobar / Modificar / Rechazar con
confirmación explícita; ejecución idempotente; aviso inmediato de urgencias; evaluación de punta a
punta con los 12 casos.

**Non-Goals:** autenticación de administradores (el MVP usa un campo "Quién decide"); reclasificar un
caso rechazado y volver a analizarlo (la máquina de estados lo permite, queda para una fase 2);
envío real por Telegram (lo hace el proceso del bot con `ejecucion.enviar_pendientes`).

## Decisions

### D1. Lógica en `eliseo/panel/servicio.py`, Streamlit solo dibuja
Todo lo que importa (qué ve el administrador, qué se envía y a quién) es una función pura sobre la
base y el runtime, testeada con pytest. `app.py` solo llama a esas funciones. La interfaz se prueba
con `streamlit.testing.v1.AppTest` (aprobar con confirmación, rechazo bloqueado sin motivo).
*Alternativa descartada:* lógica en los callbacks de Streamlit: no se puede testear sin navegador.

### D2. Confirmación = vista previa sin efectos
`servicio.vista_previa(detalle, decision)` arma exactamente el texto y el pedido que va a generar la
ejecución, usando las mismas funciones (`ejecucion.mensaje_aprobado`, `tipo_pedido`). Cancelar es no
llamar a `decidir`: no hay estado intermedio que deshacer.

### D3. Idempotencia en dos capas
1. `retomar_caso` falla si el caso ya no espera en `panel` (doble click → el segundo no ejecuta nada).
2. Cada acción usa el id del dictamen como clave: `outbox.clave = dictamen:<id>:vecino`,
   `pedidos UNIQUE(dictamen_id, tipo)` y precedente único por `dictamen_id`. Reejecutar el nodo
   (p. ej. tras una caída a mitad de camino) no duplica nada, y el cambio de estado solo se aplica si
   el caso sigue en PENDIENTE_APROBACION.

### D4. El precedente se escribe en la ejecución
La spec `ejecucion` dice que al aprobar se dispara la escritura del precedente, y la spec
`precedentes` que solo se escribe desde una aprobación. `escritura.crear_precedente` guarda la
procedencia (caso, dictamen, si fue modificado y quién aprobó). La indexación en el namespace
`precedentes` de Pinecone queda para `flujo-reclamo-mediador`, que es quien la consulta.

### D5. Envío de la outbox desacoplado del canal
`ejecucion.enviar_pendientes(enviar)` resuelve el destino (`vecino:<tel>` → chat vinculado,
`admin:<consorcio>` → `TELEGRAM_CHAT_ADMIN_ID`) y recibe la función que envía. El bot de
`canal-telegram-intake` la llama cada pocos segundos con su `send_message`. Lo que no se puede enviar
(vecino sin vincular, Telegram caído) queda pendiente y se reintenta.

### D6. Simulador de vecino dentro del panel
Una segunda vista llama a `runtime.procesar_mensaje` como si fuera el bot. Sirve para probar y
mostrar el flujo completo (consulta → reclamo → panel → respuesta) sin depender del token de Telegram,
y se usa en la demo como respaldo.

### D7. Evaluación de punta a punta con evaluadores determinísticos primero
`evaluation/e2e/correr.py` corre cada caso en una base recién sembrada y aislada. Los criterios que se
pueden chequear con código (refs esperadas, verificador, montos en la base, otras unidades, nada
asignado sin aprobación, un chequeo específico por caso) no usan LLM; tono y relevancia los puntúa un
juez LLM opcional (`--juez`). Con `--langsmith` crea el dataset `eliseo-e2e` con la categoría como
metadata y corre el experimento con repeticiones.

## Risks / Trade-offs

- **SQLite compartido entre dos procesos** → WAL activado en `conectar` (bootstrap); con un solo
  administrador por consorcio alcanza para el MVP.
- **El panel ejecuta el grafo en su proceso** → la ejecución es código sin LLM y tarda milisegundos.
- **Sin autenticación** → aceptable en la demo; en un piloto, el login lo pone la plataforma socia.
