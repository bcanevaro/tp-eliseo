## 1. Precedentes

- [x] 1.1 `eliseo/agentes/mediador/precedentes.py`: `get_precedentes(consorcio_id, unidad_id, tipo, descripcion)` con Pinecone (filtro de metadata `consorcio_id` + `tipo`, `top_k=10`), rerank (`top_n=len(candidatos)`), umbral `PRECEDENTES_UMBRAL_RERANK`, boost por columna, top 3 e hidratación desde SQLite; si Pinecone falla en runtime, degrada a SQLite (D8)
- [x] 1.2 Camino sin Pinecone: SQLite con los mismos filtros (`consorcio_id` y `tipo` inferido desde el `Caso`, compartiendo el clasificador con `ejecucion`), misma columna primero y después más nuevo (D8)
- [x] 1.3 Ingesta de precedentes en el namespace `precedentes` desde SQLite (metadata con `prec_id`, omitiendo valores `None`), idempotente y borrando sobrantes; `scripts/ingest.py` la corre junto con la de documentos (D9)
- [x] 1.4 Upsert del precedente en Pinecone desde `ejecucion._precedente` después del insert en SQLite (solo si `hay_pinecone()`); si falla, loguea y la aprobación sigue (D9)
- [x] 1.5 Reemplazar el stub `precedentes` en `nodos.py`

## 2. Criterios y prompt

- [x] 2.1 `data/administraciones/administracion-mendez/criterios.md` con los tres criterios de D7
- [x] 2.2 Carga de criterios por `normalizar(consorcio.administracion).replace(" ", "-")`, con aviso si falta el archivo (D7)
- [x] 2.3 `prompts/mediador.v2.md` con los cambios de D3; v1 queda intacto; entrada en `prompts/CHANGELOG.md`
- [x] 2.4 `escapar()` para todo texto inyectado (relato, fuentes, precedentes, criterios) (D3)
- [x] 2.5 `.env.example`: `LLM_MODEL_REASONING`, `LLM_REASONING_EFFORT=medium`, `MEDIADOR_MODO=agente`, `PROMPT_MEDIADOR_VERSION=v2`, `PRECEDENTES_UMBRAL_RERANK`

## 3. Agente Mediador

- [ ] 3.1 `get_reasoning_model()` pasa `reasoning_effort` solo para modelos de razonamiento (no con `gpt-4.1`) y no pasa `temperature` (D2)
- [ ] 3.2 `eliseo/agentes/mediador/agente.py`: armado del contexto (orden de D3), `PROMPT_MEDIADOR_VERSION` con default `v2` y llamada con `with_structured_output(Dictamen)` (D1)
- [ ] 3.3 Reintento por formato inválido: una reparación inmediata que no cuenta como vuelta, después modo `codigo` (D5)
- [ ] 3.4 Reintento por rechazo del verificador: mismo contexto más `<dictamen_anterior>` y `<fallas>` (D5)
- [ ] 3.5 Guarda de recomendación por código (antes del verificador): `asignar` sobre hipótesis sin citas o contradicha por otra hipótesis citada de distinto responsable → `inspeccion` con `hipotesis=None` y `mensaje_vecino` neutral de inspección (D4)
- [ ] 3.6 Modo sin LLM: mover el stub a `eliseo/agentes/mediador/codigo.py` (`dictamen_codigo`); `MEDIADOR_MODO`; caída al modo `codigo` si el proxy falla (D6)
- [ ] 3.7 Nodo `verificar_dictamen` propio: rechaza citas no provistas en el contexto y corre `verificador.verificar_dictamen` solo sobre las provistas (sin duplicar fallas) con la misma forma de dict; en `eliseo/schemas/dictamen.py`, el validador de `Hipotesis.citas` rechaza listas vacías (D4)
- [ ] 3.8 Reemplazar los stubs `mediador` y `verificar_dictamen` en `nodos.py`

## 4. Tests (pytest, sin red)

- [ ] 4.1 `tests/conftest.py`: fijar `MEDIADOR_MODO=codigo`
- [ ] 4.2 `tests/test_precedentes.py`: 4°B → `PREC-2201`; otro consorcio no aparece; un precedente aprobado aparece en la consulta siguiente; el upsert recibe la metadata correcta (índice falso); si el upsert falla, la ejecución termina igual; un dictamen rechazado no crea precedente
- [ ] 4.3 `tests/test_mediador.py` con un modelo falso: humedad en el 4°B (dos hipótesis, `inspeccion`, mensaje sin culpa); caso sin artículo aplicable; instrucción oculta en el relato; dos hipótesis con cita → `inspeccion`; la guarda corrige un `asignar` contradicho o sin citas (y deja `mensaje_vecino` neutral); criterio de inspección previa en el prompt; cita no provista rechazada (y sin duplicar con cita inexistente); hipótesis sin citas rechazada; formato inválido → reparación → modo `codigo`; el reintento recibe las fallas
- [ ] 4.4 `tests/test_grafo.py`: dos rechazos seguidos → no hay tercera llamada al Mediador, la recomendación es `inspeccion`, el dictamen guardado descarta las hipótesis inválidas y `verificacion["fallas"]` registra las citas rechazadas
- [ ] 4.5 `escapar()`: un relato con `</relato_vecino>` no cierra la etiqueta
- [ ] 4.6 Test marcado `pinecone` (corre solo con API key): ingesta de precedentes y consulta real de 4°B

## 5. Evaluación (LangSmith)

- [ ] 5.1 `evaluation/mediador/eval_mediador.py` con los 5 casos y los evaluadores estructura, factualidad, terminologia, neutralidad y fidelidad; `--langsmith` sube el experimento (D11)
- [ ] 5.2 Evaluación de recuperación de precedentes (precisión y recall) y calibración de `PRECEDENTES_UMBRAL_RERANK`
- [ ] 5.3 Revisar a mano los puntajes de los jueces sobre los 5 casos antes de usarlos
- [ ] 5.4 Correr con el proxy real: gpt-4.1 contra el modelo de razonamiento (D2) y elegir `LLM_MODEL_REASONING`
- [ ] 5.5 Correr v1 contra v2 del prompt y comparar en LangSmith (insumo de la tarea 4.5 de panel-admin-ejecucion)
- [ ] 5.6 Anotar los resultados en `evaluation/mediador/RESULTADOS.md`; cada falla nueva se agrega como caso antes de tocar el prompt
- [ ] 5.7 Correr `evaluation/e2e/correr.py` y confirmar que `uso-03`, `borde-04` y `neg-05` pasan con el Mediador real (ya los cubre)
