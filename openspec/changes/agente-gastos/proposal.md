## Why

"¿Por qué subió la expensa?" es una de las consultas más frecuentes del Discovery y hoy se contesta a mano por WhatsApp. El agente de Gastos es una frontera de seguridad: es el único componente que lee deudas y cuentas corrientes, así que va aislado, en solo lectura y con la unidad fijada por el teléfono. El motor de reglas va en este change porque comparte la regla dura: los montos, las mayorías y los prorrateos salen de la base o de código, nunca del LLM.

## What Changes

- Agente Gastos con las tools de solo lectura `get_cuenta_corriente`, `get_liquidacion` y `get_factura`, que devuelve `RespuestaGastos` con las líneas y el comprobante de cada monto.
- Permisos impuestos en el repo de la plataforma: la unidad y el consorcio salen de la `Identidad`, no de los argumentos del LLM.
- Comparación entre períodos para explicar subas, hecha por código.
- Motor de reglas determinístico: prorrateo por coeficiente y mayorías del art. 2060 del Código Civil y Comercial, que usan este agente y la ejecución.
- Reemplaza los stubs `gastos` y `responder` (rama gastos) del bootstrap.

## Capabilities

### New Capabilities

- `agente-gastos`: consulta de la cuenta corriente, las liquidaciones y las facturas con mínimo privilegio y montos copiados de la base.
- `motor-reglas`: cálculo determinístico de prorrateos y mayorías.

### Modified Capabilities

(ninguna)

## Impact

- **Dueño:** Integrante C.
- **Depende de:** `bootstrap-proyecto` (contratos `RespuestaGastos` y `LineaGasto`, base de la plataforma y liquidaciones de demo). **Lo usa:** `panel-admin-ejecucion` (motor).
- **Origen:** caja "Gastos" y celda "Montos de gastos, mayorías, prorrateo" del cuadrante del artefacto; casos de test de la suba de octubre y "¿Cuánto debe el 3°A?".
- **Dependencias nuevas:** ninguna.
