## 1. Ejecución

- [x] 1.1 `eliseo/ejecucion`: nodos `ejecucion`, `rechazo`, `avisar_urgencia`, `derivar_sin_fuente` y `hablar_con_admin` (reemplazan los stubs en `nodos.py`)
- [x] 1.2 Mensaje al vecino con número de caso y fuentes; pedido de inspección o trabajo; caso a APROBADO
- [x] 1.3 Idempotencia por id de dictamen (outbox, pedidos y precedente) y cambio de estado condicionado
- [x] 1.4 Precedente con procedencia al aprobar; ninguno al rechazar (`escritura.crear_precedente`)
- [x] 1.5 Aviso de urgencia al chat de la administración con clave de idempotencia
- [x] 1.6 `enviar_pendientes(enviar)` para que el bot vacíe la outbox (reintento si falla)

## 2. Panel

- [x] 2.1 `eliseo/panel/servicio.py`: bandeja por estado (urgencias primero), detalle, vista previa, decidir, respuesta manual
- [x] 2.2 `eliseo/panel/app.py` (Streamlit): bandeja, detalle con lo escrito por la IA marcado, citas con fuente y verificador
- [x] 2.3 Aprobar / Modificar / Rechazar con confirmación explícita; rechazo bloqueado sin motivo
- [x] 2.4 Respuesta manual a consultas derivadas y pedidos de hablar con una persona
- [x] 2.5 Simulador de vecino para probar sin Telegram
- [x] 2.6 `streamlit` en `requirements.txt`

## 3. Tests

- [x] 3.1 `tests/test_panel_ejecucion.py`: un test por scenario de `panel-admin` y `ejecucion` (y el rechazo sin precedente de `precedentes`)
- [x] 3.2 Tests de la interfaz con `streamlit.testing.v1.AppTest`

## 4. Evaluación de punta a punta

- [x] 4.1 `evaluation/e2e/correr.py`: los 12 casos contra el grafo real, con evaluadores determinísticos
- [x] 4.2 Juez LLM de tono y relevancia (`--juez`)
- [x] 4.3 Dataset `eliseo-e2e` y experimento en LangSmith con repeticiones (`--langsmith`)
- [x] 4.4 Correr `--juez --langsmith` con las claves reales una vez enchufados intake, gastos y mediador, y anotar los resultados en `evaluation/e2e/RESULTADOS.md` — `e2e-c4333d40`; neg-04 queda como falla conocida
- [ ] 4.5 Versionar prompts según las fallas (CHANGELOG + comparación v1/v2 en LangSmith). Mediador v1/v2 ya comparado (`evaluation/mediador/RESULTADOS.md`); pendiente neg-04 (repregunta ante una queja), a decidir por el dueño de canal-telegram-intake
