## 1. Acceso a datos sin cambio de comportamiento (D3)

- [x] 1.1 Agregar `sqlalchemy`, `psycopg[binary]`, `supabase`, `bcrypt` y `langgraph-checkpoint-postgres` a `requirements.txt` y verificar que `uv pip install -r requirements.txt` instala sin conflictos en Python 3.12
- [x] 1.2 Reemplazar la conexión `sqlite3` por una `Conexion` sobre SQLAlchemy con la misma interfaz, creada desde `ELISEO_DB_URL` (SQLite por defecto), con el esquema por motor; verificar con `pytest` que la suite actual pasa sin cambios
- [x] 1.3 Pasar el SQL propio de SQLite (`INSERT OR IGNORE`, `lastrowid`, `date('now')`) al subconjunto común y hacer que las evaluaciones nunca usen la base del `.env`; verificar que `pytest` y `python evaluation/e2e/correr.py` dan lo mismo que antes
- [x] 1.4 Elegir el checkpointer según la URL (`SqliteSaver` o `PostgresSaver`) en `grafo/runtime.py` y verificar con un test que un caso interrumpido se retoma desde otra conexión a la misma base (`test_grafo.py`, "simula reiniciar el proceso", en los dos motores)
- [x] 1.5 Agregar al CI un job que corra `pytest` contra un servicio Postgres de GitHub Actions y verificar que pasa en los dos motores

## 2. Administraciones, cuentas y login (cuentas-admin, D4, D5)

- [x] 2.1 Agregar las tablas `administraciones` y `administradores` y la columna `consorcios.administracion_id` (y `activo`), migrando el texto `administracion` del consorcio de demo; test de que el Consorcio Rivadavia 4520 queda en la Administración Méndez
- [x] 2.2 Implementar `autenticar(email, password) -> Sesion | None` con las variantes Supabase Auth y local con `bcrypt`; tests de ingreso correcto, contraseña incorrecta (mismo mensaje que email inexistente) y cuenta sin administración
- [x] 2.3 Hacer que toda función de `panel/servicio.py` reciba la `Sesion` y filtre por administración; tests de los scenarios "Caso de otra administración" y "Selector de consorcio" con dos administraciones sembradas
- [x] 2.4 Agregar el formulario de ingreso y "Cerrar sesión" a `panel/app.py`, y reemplazar "Quién decide" por la cuenta de la sesión; verificar con `streamlit.testing.v1.AppTest` que sin sesión no se ve la bandeja y que la decisión queda con la cuenta como autora
- [x] 2.5 Escribir `scripts/alta_administracion.py` (administración y primer administrador) y verificar que la cuenta creada ingresa y ve el panel vacío
- [x] 2.6 Activar RLS sin políticas para `anon` en todas las tablas al crear el esquema en Postgres y verificar con la clave pública que una consulta a `vecinos` no devuelve filas

## 3. Padrón de consorcios y vecinos (padron-consorcios, D11)

- [x] 3.1 Implementar en `servicio.py` alta y edición de consorcio con unidades y la validación de coeficientes; tests de "Edificio nuevo" y "Coeficientes que no cierran"
- [x] 3.2 Implementar quitar unidad (bloqueado con vecinos o casos) y baja lógica de consorcio, con borrado de sus records en Pinecone; tests de "Unidad con vecino" y "Baja confirmada" con el índice simulado
- [x] 3.3 Implementar alta, edición y baja de vecino con teléfono normalizado y único; tests de "Vecino nuevo", "Teléfono ya registrado" (sin revelar el consorcio), "Teléfono inválido" y "Cambio de teléfono" (borra el vínculo)
- [x] 3.4 Hacer que `identidad_por_telefono` ignore los consorcios inactivos y que el seguimiento saltee los teléfonos fuera del padrón; tests de "Vecino dado de baja", "Conversación en curso" y "Mudanza a otro edificio de la misma administración"
- [x] 3.5 Agregar al panel las vistas "Edificios" y "Vecinos" con confirmación en las bajas, y verificarlas con `AppTest`

## 4. Documentos por consorcio (documentos-consorcio, D6, D7, D8)

- [x] 4.1 Agregar la tabla `documentos` y el guardado del original en Storage (o en `data/archivos/` en modo local); test de que el original se recupera igual al subido
- [x] 4.2 Escribir el validador sobre el parser de `corpus.py` (ids canónicos, repetidos, fecha del acta, `modifica` inexistente, `consorcio_id` ajeno) con errores por línea; un test por cada regla
- [x] 4.3 Hacer que `cargar_corpus` lea de la base los documentos activos con caché por `(consorcio_id, versión)`; verificar que `pytest` sigue en verde y que un acta nueva vale en la consulta siguiente sin reiniciar
- [x] 4.4 Confirmar = guardar e indexar con `ingesta.sincronizar`, con `indexado = false` y reintento si Pinecone falla; tests de "Acta que reemplaza un artículo" y "Servicio de búsqueda caído" (BM25 lo encuentra igual)
- [x] 4.5 Implementar el reemplazo del reglamento y la baja de actas, y el fallback de `_texto_fuente` a documentos dados de baja; tests de "Baja de un acta citada en un caso viejo" y "Acta de la que depende la vigencia"
- [x] 4.6 Agregar al panel la vista "Documentos" (subir, vista previa, confirmar, lista con estado de indexación, descarga del original y plantilla de formato), y verificarla con `AppTest`
- [x] 4.7 Correr `python evaluation/documental/eval_recuperacion.py --langsmith` con el corpus cargado desde la base y verificar que las métricas de `evaluation/documental/RESULTADOS.md` no cambian

## 5. Bot único y avisos por administración (canal-administracion, D1, D9)

- [x] 5.1 Agregar `administraciones.chat_avisos_id` y la tabla de códigos de vinculación (hash, vencimiento, usado); tests de código válido, vencido, usado e inexistente
- [x] 5.2 Agregar el comando `/admin <código>` al bot y el botón "Vincular chat de avisos" al panel; verificar con un test del handler que el chat queda vinculado y el bot confirma con el nombre de la administración
- [x] 5.3 Resolver `admin:<consorcio>` por administración en `ejecucion.chat_de_destino` y quitar `TELEGRAM_CHAT_ADMIN_ID`; tests de "Urgencia en un consorcio" (llega solo a su administración) y "Administración sin chat vinculado" (queda pendiente y el panel lo indica)
- [x] 5.4 Presentar el bot con la administración del vecino en el saludo; actualizar el test de saludo de `canal-telegram` y verificar el scenario "Vecinos de dos administraciones"
- [x] 5.5 Agregar un test de que el Mediador arma el dictamen para una administración sin archivo de criterios

## 6. Demo, configuración y documentación (datos-ficticios, D12)

- [x] 6.1 Hacer `scripts/seed_db.py` no destructivo, con `--reset` explícito (que pide confirmación en Postgres) y con la cuenta de prueba de la demo; tests de "Reseed idempotente" y "Seed sobre una base con datos del panel"
- [x] 6.2 Sembrar en los tests una segunda administración con su consorcio, para que el aislamiento se pruebe con datos reales y no solo con hits simulados; verificar que todos los tests de aislamiento la usan
- [x] 6.3 Agregar `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY` y `ELISEO_DB_URL` a `.env.example` y a `scripts/check_servicios.py`, y verificar que el chequeo informa la base en uso y si Auth y Storage responden
- [x] 6.4 Actualizar el README (login, vistas del panel, vinculación del chat de avisos, Supabase y modo local) y verificar que los comandos documentados corren tal cual en una copia limpia

## 7. Integración

- [ ] 7.1 Correr `pytest` y `python evaluation/e2e/correr.py` en los dos motores y verificar que dan igual que antes del change
- [ ] 7.2 Correr la evaluación de punta a punta con LLM (`--juez --langsmith --repeticiones 3`) contra Supabase y registrar el experimento en `evaluation/e2e/RESULTADOS.md`
- [ ] 7.3 Probar en Telegram real, con dos administraciones y dos edificios: alta de un vecino desde el panel, consulta con un documento recién cargado, urgencia que llega solo al chat de su administración y baja del vecino que corta el acceso

## Workflow follow-up

- Revisión del change por otro integrante antes de implementar, en la branch `cuentas-administracion`.
- `openspec validate cuentas-administracion --strict` y `pytest` en verde antes de mergear.
- Archivar con `openspec archive cuentas-administracion` después de mergear.
