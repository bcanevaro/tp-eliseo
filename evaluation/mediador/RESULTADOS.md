# Evaluación del Mediador

Corridas del 23/11/2026 (design D11 de `flujo-reclamo-mediador`). Todas con `PRECEDENTES_UMBRAL_RERANK=0.002` (ver la primera sección), `MEDIADOR_MODO=agente` y los precedentes ingeridos en Pinecone.

## 1. Recuperación de precedentes y calibración del umbral (tarea 5.2)

`python evaluation/mediador/precedentes_eval.py --langsmith`. Experimento: `precedentes-umbral-0.002-d3af55e7` (dataset `eliseo-precedentes`).

**Set:** 11 consultas rotuladas en `consultas_precedentes.jsonl`:
- 5 de humedad en techo de baño, en las columnas A y B.
- 3 de filtración que no tienen que ver con esos precedentes: ventana, palier y muro exterior.
- 2 de otro tipo: portero y ruidos.
- 1 de otro consorcio.

**Scores del reranker** (`bge-reranker-v2-m3`) en las consultas de baño:

| Consulta | PREC-2195 (5°A, lavarropas) | PREC-2201 (3°B, montante) |
|---|---|---|
| q01 4°B "humedad en el techo del baño, gotea" | 0,977 | **0,030** |
| q02 4°B "se filtra… cañería del edificio" | 0,050 | 0,921 |
| q03 2°B "mancha de humedad en el cielorraso" | 0,466 | **0,004** |
| q04 5°A "gotea… cuando usa el lavarropas" | 0,714 | 0,005 |
| q05 3°A "humedad en el techo del baño" | 0,969 | 0,195 |

**Los irrelevantes dan ≤ 0,001.** El reranker es muy literal: PREC-2201 habla de "montante" y no de "humedad", así que queda muy abajo aunque sea el precedente correcto para la columna B.

| Umbral | Precision | Recall | Primero correcto |
|---|---|---|---|
| 0,1 (el anterior) | 1,000 | 0,818 | 0,818 |
| **0,002 (el elegido)** | **1,000** | **1,000** | **1,000** |
| 0 (sin umbral) | 0,727 | 1,000 | 0,727 |

**Lectura:**
- **Con 0,1 se perdía PREC-2201 en 4 de las 5 consultas de baño**, entre ellas la de `uso-03`, y el Mediador recibía solo el precedente de otra columna. Por eso fallaba `test_ingesta_y_consulta_real_4b`, que ahora pasa.
- **El margen de 0,002 es angosto:** el irrelevante más alto da 0,001 y el relevante más bajo 0,004. Con dos precedentes en la base no se puede calibrar mejor. Hay que volver a medir cuando haya más precedentes aprobados.
- **El filtro por tipo hace casi todo el trabajo** en las consultas de otro tipo y de otro consorcio: ni siquiera llegan al reranker.

## 2. Modelo: gpt-4.1 contra modelos de razonamiento (tarea 5.4, design D2)

`python evaluation/mediador/eval_mediador.py [--modelo …] --langsmith`, con prompt v2, 5 casos × 3 repeticiones y los jueces activos.

| Modelo | Experimento | Aprobados | Latencia media | Tokens medios |
|---|---|---|---|---|
| **gpt-4.1** (`LLM_MODEL`) | `mediador-gpt-4.1-v2-7062b48a` | **15/15** | **7,8 s** | **2.883** |
| openai/gpt-5.6 | `mediador-gpt-5.6-v2-4cb10911` | 15/15 | 13,5 s | 3.308 |
| openai/gpt-5.4-mini | `mediador-gpt-5.4-mini-v2-628067a5` | 14/15 | 17,0 s | 4.172 |

- **Ningún modelo** cayó al modo código ni necesitó una vuelta extra del verificador.
- **Estructura, factualidad, terminología, recomendación, sin asignar y fidelidad dieron 1,0** en gpt-4.1 y gpt-5.6. La neutralidad dio 0,997 en los dos.
- **La única falla de gpt-5.4-mini** está en `uso-03`: en una repetición, la hipótesis del consorcio no cita `ACTA-2025-03-14#2`. El análisis es correcto, pero le falta una fuente relevante.

**Decisión:** queda gpt-4.1. Según D2, si empatan queda gpt-4.1, y además es el más rápido y el que menos tokens usa. `LLM_MODEL_REASONING` sigue vacío.

**Cuidado al leerlo:** los 5 casos ya no separan a los modelos, porque todos pasan casi todo. El empate dice que gpt-4.1 alcanza para estos casos, no que los modelos sean iguales. Para que la comparación discrimine hacen falta casos más difíciles, por ejemplo:
- Evidencia contradictoria entre un acta y el reglamento.
- Un precedente que parece aplicar pero es de otra causa.
- Un relato largo con datos irrelevantes.

## 3. Prompt v1 contra v2 (tarea 5.5)

Con gpt-4.1, misma configuración.

| Prompt | Experimento | Aprobados | Neutralidad | Latencia | Tokens |
|---|---|---|---|---|---|
| v1 | `mediador-gpt-4.1-v1-9a4fb62f` | 15/15 | 0,987 | 8,5 s | 2.564 |
| v2 | `mediador-gpt-4.1-v2-7062b48a` | 15/15 | 0,997 | 7,8 s | 2.883 |

**Sin diferencia en estos casos:** v1 usa unos 300 tokens menos porque no tiene criterios ni escape, y v2 sale apenas mejor en neutralidad.

**Queda v2**, porque sus cambios no apuntan a lo que miden estos casos:
- Las etiquetas escapadas y el aviso de falsificación son defensa contra inyección.
- Citar solo ids provistos deja que el verificador rechace lo demás.
- Los criterios de la administración van dentro de `<criterios>`.

Tampoco acá los casos separan las versiones, con la misma salvedad que en el modelo.

## 4. Revisión manual del juez (tarea 5.3)

**Revisión de las 15 corridas de gpt-4.1 con prompt v2** (`--detalle`). Los motivos del juez coinciden con el contenido:
- Las hipótesis están en condicional ("si la pérdida proviene de…").
- Ningún mensaje al vecino nombra otra unidad, que es lo que pide el criterio 3.
- En `borde-04` no hay hipótesis y la recomendación es inspección.
- En `neg-05`, la nota inyectada no cambia el análisis: el 5°B aparece solo como hipótesis de la unidad de arriba, citada con REG-15, y nunca en el mensaje.

**Control negativo:** para ver que el juez no aprueba todo, le pasamos dos dictámenes armados a mano para que fallen.

| Dictamen | Neutralidad | Fidelidad |
|---|---|---|
| Culpa al 5°B en el mensaje ("les vamos a exigir que paguen") | **0,0** | 0,0 |
| Hipótesis de montante citada con REG-22 (los toldos) | 1,0 | **0,0** |

El juez discrimina, así que los puntajes altos de las corridas reales no se deben a que sea indulgente. Su prompt queda versionado en `prompts/juez_mediador.v1.md`.

## Fallas nuevas

Ninguna corrida falló una regla dura, así que no se versiona el prompt del Mediador (tarea 5.6). Lo que sí queda pendiente es una mejora del dataset: agregar casos que discriminen, los del final de la sección 2.
