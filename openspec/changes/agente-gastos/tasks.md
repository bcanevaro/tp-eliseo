## 1. Motor de reglas

- [x] 1.1 `eliseo/motor`: `prorratear` por mayor resto con suma exacta y validaciones
- [x] 1.2 `evaluar_mayoria` con doble cómputo (unidades y coeficientes) y mayorías especiales
- [x] 1.3 Tests unitarios sin red (scenarios de `motor-reglas`)

## 2. Agente Gastos

- [x] 2.1 Tools de solo lectura atadas a la `Identidad` (`get_periodos`, `get_liquidacion`, `comparar_con_anterior`, `get_factura`, `get_cuenta_corriente`)
- [x] 2.2 `Registro` de montos y comprobantes y validación de salida (`MontoNoRespaldado`)
- [x] 2.3 Loop del agente con salida estructurada `RespuestaGastos` y master prompt `prompts/gastos.v1.md`
- [x] 2.4 Modo sin LLM (`respuesta_codigo`) como respaldo; `GASTOS_MODO`
- [x] 2.5 Corte por código de pedidos sobre otra unidad o todas
- [x] 2.6 Período ambiguo y comprobante faltante (derivación al panel)
- [x] 2.7 Reemplazar los stubs `gastos` y `responder_gastos` en `nodos.py`

## 3. Tests y evaluación

- [x] 3.1 `tests/test_gastos_motor.py`: un test por scenario, más el agente con un modelo falso que inventa un monto
- [ ] 3.2 Correr con el proxy real (`GASTOS_MODO=agente`) los casos `uso-02`, `borde-03` y `neg-02` de `evaluation/e2e/correr.py --juez` y anotar el resultado
