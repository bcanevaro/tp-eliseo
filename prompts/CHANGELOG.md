# Historial de los master prompts

Cada versión nueva va en `prompts/<nombre>.v<N>.md` y se elige con `PROMPT_<NOMBRE>_VERSION` en `.env`. Cada cambio lleva el caso de evaluación o el motivo de rechazo del panel que lo motivó, y un experimento de LangSmith que lo compara con la versión anterior (spec evaluacion-e2e).

| Prompt | Versión | Fecha | Cambio | Por qué |
|---|---|---|---|---|
| vecino | v1 | 21/10/2026 | Primera versión, del artefacto de Design | Sale del Discovery: abstención sin fuente y aprobación humana obligatoria (riesgo 1). |
| mediador | v1 | 21/10/2026 | Primera versión, del artefacto de Design | Ídem. |
| vecino, mediador | v1 | 10/11/2026 | Al pasarlos al repo: ids canónicos en los ejemplos (REG-22, ACTA-2024-11-10#3, PREC-2201) en lugar de "Art. 22" y "#2201"; canal Telegram | El verificador de citas resuelve solo ids canónicos (spec contratos-compartidos). No cambia el comportamiento. |
