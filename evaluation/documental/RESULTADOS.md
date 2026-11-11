# Evaluación de recuperación del agente Documental

Corrida del 11/11/2026 con `python evaluation/documental/eval_recuperacion.py --langsmith`. Experimento de LangSmith: `hibrido-e5-bge-9f8a7448` (dataset `eliseo-documental-recuperacion`).

- **Corpus:** Consorcio Rivadavia 4520, con 43 chunks (28 artículos y 15 puntos de acta).
- **Preguntas:** 31 en lenguaje de vecino, sin reescritura del intake (es el peor caso). 26 tienen fuente en el corpus y 5 no.
- **Métricas:** se miden después de resolver la vigencia, así que la respuesta correcta a "horario de obras" es el acta que reemplazó al REG-14.

## Recuperación por etapa (26 preguntas con fuente)

| Etapa | Acierto@3 | Recall@3 | MRR |
|---|---|---|---|
| Dense (Pinecone, `multilingual-e5-large`) | 1,000 | 0,981 | 0,936 |
| BM25 (stemming en español) | 0,731 | 0,712 | 0,622 |
| RRF (dense + BM25) | 0,962 | 0,923 | 0,885 |
| **RRF + rerank (`bge-reranker-v2-m3`)**, la configuración final | **0,962** | **0,962** | **0,962** |
| Dense + rerank, sin BM25 (comparación aparte) | 0,962 | 0,962 | 0,962 |

**Lectura:**
- **El rerank es lo que más aporta:** sube el MRR de 0,89 a 0,96. La respuesta correcta queda primera en 25 de 26 preguntas.
- **En este corpus, sumar BM25 no mejora al dense**, y la fusión pierde un caso (p18, "dejar entrar al plomero" → REG-17). Lo mantenemos por dos razones:
  - Es lo que queda cuando Pinecone no responde: el retriever degrada a BM25 en lugar de caerse.
  - Con un corpus más grande, con términos exactos como "montante" o "coeficiente", la evidencia general a favor del híbrido sigue en pie.
  
  Hay que volver a medirlo cuando haya más consorcios.

## Abstención en modo `retriever` (sin LLM)

El score del reranker **no separa bien** lo que tiene fuente de lo que no:
- Preguntas bien respondidas sacan scores bajísimos: p20 ("música fuerte") da 0,006 y p16 ("se rompe un caño adentro de mi casa") da 0,012.
- La pileta, que no tiene fuente, saca 0,213 por el artículo de la terraza.

Como contestar sin fuente es el riesgo 1 del Discovery y derivar de más es solo menos cómodo, el umbral queda en **0,25**, por encima del mayor score sin fuente:

| Umbral | Sin fuente contestadas | Con fuente contestadas | Con fuente derivadas |
|---|---|---|---|
| 0,25 | 0 de 5 | 17 de 26 | 9 (p02, p06, p08, p10, p15, p16, p18, p19, p20) |
| 0,001 (máxima exactitud simétrica) | 3 de 5 (s01, s04, s05) | 26 de 26 | 0 |

**Conclusión:** el modo `retriever` es un respaldo seguro pero conservador. Decidir si la evidencia alcanza es trabajo del agente con LLM, y es una de las razones por las que Documental es un agente y no un retriever fijo.

## Pendiente

- **Evaluación del agente con LLM** (task 6.3): necesita crédito en el proxy. Se corre sobre `uso-01`, `borde-02`, `neg-01` y `neg-04` de `evaluation/casos.jsonl`.
- **Repetir la evaluación con la `pregunta_reescrita` del intake real.** La reescritura sube mucho el score: "perro" da 0,32 y "animales domésticos", 0,99.
