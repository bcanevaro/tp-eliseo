## Context

Gastos es el único componente que lee la cuenta corriente de una unidad, así que es una frontera de
seguridad: mínimo privilegio y montos que nunca salen del LLM. El bootstrap ya trae la plataforma
simulada (`lectura.cuenta_corriente`, `liquidacion`, `factura`) con montos `Decimal` y un stub que
explica la suba de octubre sin LLM.

## Goals / Non-Goals

**Goals:** agente con tools de solo lectura atadas a la `Identidad`; validación de salida que descarta
cualquier monto o comprobante que no devolvió una tool; comparación entre períodos y prorrateo
hechos por código; motor de reglas (prorrateo y mayorías del art. 2060) puro y testeado.

**Non-Goals:** mostrar datos de otra unidad aunque lo pida un administrador (eso es el panel);
extraer del reglamento qué mayoría especial aplica (lo puede hacer Documental; el motor recibe el tipo).

## Decisions

### D1. Las tools se construyen con la Identidad y no tienen argumentos de unidad ni consorcio
`crear_tools(ident, registro)` cierra sobre la `Identidad` del estado. `get_cuenta_corriente()` no
recibe parámetros. Un test verifica que ninguna tool expone `unidad` o `consorcio` en su schema.
*Alternativa descartada:* validar el argumento dentro de la tool; deja la puerta abierta a un bug.

### D2. Registro de lo que devolvieron las tools + validación de salida
Cada tool anota en un `Registro` los montos y comprobantes que mostró. `validar()` extrae todo `$ …`
del texto y todos los montos y `FAC-…` de las líneas, y falla si alguno no está en el registro. Si
falla, la respuesta del LLM se descarta (`MontoNoRespaldado`) y se usa el modo sin LLM: la respuesta
no se envía.

### D3. Diferencias y prorrateo como tool (`comparar_con_anterior`)
La suba entre períodos y la parte de la unidad (vía `motor.prorratear`) las calcula código y se le
entregan al LLM como datos ya resueltos; así el LLM nunca tiene que restar.

### D4. Modo sin LLM como respaldo y para los tests
`respuesta_codigo` cubre los casos frecuentes (suba, gasto puntual por concepto y mes, cuenta
corriente, otra unidad). Se usa con `GASTOS_MODO=codigo`, si el proxy falla o si la validación
descarta la respuesta. Los tests fijan `GASTOS_MODO=codigo` en `conftest.py`, igual que Documental.

### D5. Otra unidad se corta por código antes del LLM
`otra_unidad()` detecta "3°A", "3A" o "todas las unidades" y responde con un texto fijo. Es más barato
y no depende de que el modelo resista la inyección.

### D6. Período ambiguo: responde con el último liquidado y pregunta una vez
La spec pide preguntar el mes una sola vez sugiriendo el último liquidado. Como el estado de la
conversación no guarda preguntas pendientes de Gastos (y agregarlo cambia el contrato compartido),
el bot responde con el último mes liquidado y en el mismo mensaje ofrece ver otro mes. No hay loop
de repreguntas posible.

### D7. Prorrateo por mayor resto
`prorratear` trunca cada parte al centavo y reparte los centavos faltantes a los mayores restos,
desempatando por id de unidad. La suma da exacta y el resultado no depende del orden de entrada.
*Alternativa descartada:* dar la diferencia a la última unidad (lo que hace `seed_db.py`): depende
del orden y concentra el error en una unidad.

### D8. Mayorías: umbral sobre el total de unidades, doble cómputo
`evaluar_mayoria` computa sobre el total de unidades del consorcio (los ausentes no suman), por
número de unidades y por coeficientes; tienen que cumplirse los dos e informa cuál falló. La mayoría
absoluta es estricta (más de la mitad); las especiales (dos tercios, unanimidad) son "al menos".

## Risks / Trade-offs

- **Detección de "otra unidad" por regex** → puede dar falsos positivos raros ("3B" en otro contexto);
  el costo es una respuesta prudente de más, no una filtración.
- **Comprobantes faltantes** → se deriva al panel con el concepto; los rubros sin factura por naturaleza
  (sueldo del encargado, fondo de reserva) no se derivan.
