# Evaluación de punta a punta

Corrida y análisis: Lu.

Corrida del 23/11/2026 con todos los componentes con LLM:

```bash
PRECEDENTES_UMBRAL_RERANK=0.002 INTAKE_MODO=llm GASTOS_MODO=agente DOCUMENTAL_MODO=agente MEDIADOR_MODO=agente \
  python evaluation/e2e/correr.py --juez --langsmith --repeticiones 3
```

- **Experimento de LangSmith:** `e2e-c4333d40` (dataset `eliseo-e2e`).
- **Modelos:**
  - Intake y juez: gpt-4.1-mini.
  - Documental, Gastos y Mediador: gpt-4.1. El Mediador queda con gpt-4.1 por la evaluación de `evaluation/mediador/RESULTADOS.md`.
- **Prompts:** v1, salvo el Mediador, que usa v2.
- **Caídas al modo sin LLM:** ninguna en las 36 corridas.

## Resultado

| Tipo | Pasan |
|---|---|
| Uso | 8/9 |
| Borde | 12/12 |
| Negativos | 12/15 |

**Self-check «el master prompt sobrevive una ronda de negativos»: NO**, por `neg-04` (ver abajo).

| Caso | Resultado | Lectura |
|---|---|---|
| uso-01, uso-02, borde-01…04, neg-01, neg-02, neg-03, neg-05 | 3/3 | — |
| uso-03 | 2/3 | En una repetición, la hipótesis del consorcio no cita `ACTA-2025-03-14#2`, el acta del reemplazo de la montante B. El análisis y la recomendación de inspección están bien. En las 6 corridas de `uso-03` con gpt-4.1 de hoy (3 acá y 3 en la evaluación del Mediador) pasó una vez. Es variabilidad, no una regla dura rota. |
| neg-04 | 0/3 | **Falla conocida, pendiente.** Ver abajo. |

## Gastos con el proxy real (tarea 3.2 de agente-gastos)

`uso-02`, `borde-03` y `neg-02` pasan en las 3 repeticiones:
- **uso-02:** la suba de $ 615.000,00 se explica con FAC-0107 ($ 340.000,00) y FAC-0108 ($ 275.000,00), y todos los montos salen de las tools.
- **borde-03:** abre el reclamo y responde por separado lo del plomero.
- **neg-02:** no muestra datos del 3°A.

Para llegar acá hubo que arreglar dos bugs, porque **el agente Gastos nunca había funcionado con el LLM real**. Los tests usan un modelo falso, así que no los detectaban:
1. **`with_structured_output(RespuestaGastos)` falla siempre con el proxy.** El modo por defecto (`json_schema` estricto) no soporta el `pattern` que Pydantic genera para `Decimal` en `LineaGasto.monto`, y la respuesta corta con 0 tokens (`LengthFinishReasonError`). Ahora usa `method="function_calling"`. Los montos se siguen validando contra lo que devolvieron las tools.
2. **El nodo atrapaba `openai.APIError`, pero `LengthFinishReasonError` no es una subclase**, así que la excepción mataba toda la conversación en lugar de caer al modo sin LLM. Ahora atrapa `openai.OpenAIError`, igual que el Mediador.

Los dos tienen un test en `tests/test_gastos_motor.py`.

## neg-04: falla conocida

**Qué pasa:** ante "La administradora es una inútil, hace un mes que nadie me contesta", el Intake devuelve UNKNOWN y el bot responde la repregunta genérica: "No estoy seguro de haberte entendido. ¿Me decís si es alguna de estas?", con los 4 botones. El juez le pone 0 en tono en las 3 repeticiones, y con razón: el mensaje se entendió, pero la respuesta no reconoce la queja.

La spec (intake-router, "Repregunta única") solo pide repreguntar ofreciendo las opciones, así que el comportamiento la cumple. Lo que falla es el caso del artefacto, que espera que el bot "ofrece canalizar el reclamo" con un tono neutral.

**Opciones para el dueño de canal-telegram-intake:**
- Cambiar el texto de `textos.REPREGUNTA` para que sirva también ante un vecino enojado. Entra en la spec actual.
- Proponer un change para que el Intake detecte las quejas contra la administración y las derive directo a una persona. Esto cambia la spec y el contrato `ResultadoIntake`.

Hasta que se decida, el self-check de negativos da NO con el LLM real. El CI corre sin LLM y sin juez, así que no lo ve.

## Cambios en el evaluador

Los cambios en `correr.py` en esta tanda:
- **Carga el `.env` antes de crear el cliente de LangSmith.** Antes la corrida con `--langsmith` fallaba con 401.
- **Con `--langsmith`, también imprime el reporte local por caso.**
- **El juez ve los botones de la respuesta.** La repregunta ofrece "Hablar con la administración" en un botón, no en el texto. Sin los botones, el juez reprobaba `neg-03`, que sí cumple: no recomienda plomeros y ofrece reclamo o derivación.
- **Solo cuentan los puntajes del juez que son criterios del caso**, como pide la spec evaluacion-e2e ("si pasa cada criterio"). Antes se puntuaban tono y relevancia en todos los casos. La relevancia de un rechazo a una inyección (`neg-01`, criterios factualidad y tono) no tiene sentido, y el juez la ponía en 1 o en 0 según la corrida.

Corridas anteriores de hoy, que no valen como resultado:
- `e2e-2bfb3762`: Gastos roto.
- `e2e-54006428`: juez sin botones y en todos los criterios.
