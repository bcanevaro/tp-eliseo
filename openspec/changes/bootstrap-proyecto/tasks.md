## 1. Entorno y estructura

- [x] 1.1 Crear el paquete `eliseo/` con el layout del design (D1) y `__init__.py` en cada módulo
- [x] 1.2 `.venv` con uv en Python 3.12, `requirements.txt` con las dependencias del proposal y `pytest.ini`
- [x] 1.3 `.env.example` con LLM_SERVICE_URL, LLM_API_KEY, LLM_MODEL_FAST, LLM_MODEL, LLM_MODEL_REASONING, EMBEDDING_MODEL, PINECONE_API_KEY, PINECONE_INDEX_NAME, LANGSMITH_*, ELISEO_DB_PATH y TELEGRAM_BOT_TOKEN; `.gitignore` con `.env`, `.venv/` y `data/*.db`
- [x] 1.4 `eliseo/config.py` y `eliseo/llm.py` (los tres modelos y los embeddings, D6)
- [x] 1.5 `eliseo/vectores.py`: crear el índice si no existe y exponer los namespaces `documentos` y `precedentes` (D5)

## 2. Contratos compartidos

- [x] 2.1 `MensajeEntrante`, `Identidad` y `Adjunto`
- [x] 2.2 `Intent`, `ReclamoBorrador` y `ResultadoIntake`
- [x] 2.3 `Cita` (con los formatos de id canónico), `RespuestaDocumental`, `LineaGasto`, `RespuestaGastos` y `RespuestaVecino` (máximo 600 caracteres)
- [x] 2.4 `Caso`, `EstadoCaso` y la tabla de transiciones válidas
- [x] 2.5 `Dictamen`, `Hipotesis`, `Recomendacion` (validador: `asignar` exige hipótesis) y `DecisionAdmin` (validador: `RECHAZAR` exige motivo)
- [x] 2.6 Tests de contratos: un test por cada scenario de `contratos-compartidos`

## 3. Datos ficticios

- [x] 3.1 `reglamento.md` del Consorcio Rivadavia 4520, con 25 artículos o más e ids `REG-<n>`
- [x] 3.2 Cuatro actas o más, con puntos numerados y metadata de qué artículo modifican (incluye toldos y montante B)
- [x] 3.3 `plataforma.json`: unidades con coeficientes, vecinos y teléfonos, cuentas corrientes, liquidaciones de septiembre y octubre 2026 con líneas, facturas y el precedente PREC-2201
- [x] 3.4 `eliseo/plataforma/`: esquema SQLite (WAL), repos de solo lectura y repos de escritura para casos, dictámenes y decisiones
- [x] 3.5 `scripts/seed_db.py` idempotente
- [x] 3.6 Tests de datos: coeficientes que suman 1, suba de octubre explicada por líneas con factura, teléfono no registrado presente

## 4. Grafos

- [x] 4.1 `EstadoConversacion` y `EstadoCaso` (TypedDict) a partir de los contratos
- [x] 4.2 `eliseo/grafo/stubs.py`: un stub determinístico por nodo (identificar, intake, documental, verificador, gastos, responder, derivar, urgencia, completar_datos, registrar_caso, precedentes, mediador, panel, ejecucion)
- [x] 4.3 `eliseo/grafo/conversacion.py`: ruteo por intent, fan-out de `multi`, repregunta única, urgencia y TTL
- [x] 4.4 `eliseo/grafo/caso.py`: Documental ‖ Precedentes → Mediador ⇄ verificador (máximo 2) → `interrupt` → ejecución
- [x] 4.5 Checkpointer `SqliteSaver` compartido (D3) y helper `retomar_caso(caso_id, decision)`
- [x] 4.6 Test de humo de punta a punta con stubs: consulta con cita, sin fuente, gastos, urgencia y reclamo hasta ejecución

## 5. Prompts, evaluación y documentación

- [x] 5.1 `prompts/vecino.v1.md` y `prompts/mediador.v1.md` copiados del artefacto, y `prompts/CHANGELOG.md` con la v1
- [x] 5.2 `evaluation/casos.jsonl` con los 12 casos del artefacto (tipo, prompt, input, esperado, criterios)
- [x] 5.3 README: cómo levantar el entorno, cómo correr los tests y el flujo de trabajo con OpenSpec
- [x] 5.4 `openspec validate bootstrap-proyecto --strict` sin errores
- [ ] 5.5 Mergear a `main` y correr `openspec archive bootstrap-proyecto`
