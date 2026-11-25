## Context

Ver `proposal.md` (Why). Estado actual que condiciona el diseño:

- `eliseo/plataforma/` habla `sqlite3` directo, con SQL propio de SQLite (`?`, `datetime('now')`, `AUTOINCREMENT`). La misma base guarda los checkpoints de LangGraph (`SqliteSaver`).
- El corpus se lee de archivos: `corpus.cargar_corpus(consorcio_id)` busca la carpeta cuyo `plataforma.json` tiene ese id, parsea `reglamento.md` y `actas/*.md`, y lo cachea con `lru_cache`. Lo usan el Documental (BM25 y vigencia), el verificador, el Mediador y el panel (`_texto_fuente`).
- La ingesta a Pinecone (`ingesta.sincronizar`) ya es idempotente por consorcio y borra los records sobrantes.
- La identidad del vecino ya sale del teléfono (`lectura.identidad_por_telefono`) y el aislamiento entre consorcios del lado de los agentes ya está resuelto. Lo que no existe es la capa de administración: el consorcio tiene un texto `administracion`, no hay cuentas y la outbox resuelve `admin:<consorcio>` a una única variable de entorno.
- El panel (Streamlit) tiene la lógica en `panel/servicio.py` y Streamlit solo dibuja (design D1 de `panel-admin-ejecucion`); se mantiene esa separación.
- Regla del proyecto: `pytest` pasa sin red ni LLM.

## Goals / Non-Goals

**Goals:**
- Login por cuenta y aislamiento por administración aplicado en el servidor.
- Alta, edición y baja de consorcios, unidades, vecinos y documentos desde el panel, con efecto inmediato en el bot.
- Base hosteada en Supabase sin romper el modo local: tests, CI y demo siguen corriendo sobre SQLite sin red.
- Un solo bot y un chat de avisos por administración.

**Non-Goals:**
- Alta de administraciones y cuentas desde el panel (lo hace un script de operación).
- Roles dentro de una administración (titular y auxiliares ven y hacen lo mismo).
- Carga de PDF o documentos escaneados con OCR (idea I8 del DISCOVERY, descartada para el MVP).
- Un vecino con unidades en dos consorcios (el teléfono sigue siendo único).
- Editar desde el panel los criterios de la administración que usa el Mediador.
- Carga de liquidaciones, facturas y cuentas corrientes desde el panel: siguen viniendo de la plataforma simulada (seed).
- WhatsApp.

## Decisions

### D1. Un solo bot para toda la app
La administración del vecino ya se deduce de su teléfono (teléfono → unidad → consorcio → administración), así que un bot por administración no agrega aislamiento: lo da el padrón. Un solo bot es un token, un proceso y un lugar donde mirar logs; el bot se presenta con el nombre de la administración del vecino.
*Alternativa descartada:* un bot por administración. Cada cliente necesitaría crear su bot en BotFather y cargar el token, el sistema tendría que levantar un proceso o un webhook por token y elegir el bot correcto en la outbox. La única ganancia es el nombre y la foto del bot por cliente, que no justifica la operación en un MVP. Si un cliente lo pide, se puede agregar después con una tabla `bots(administracion_id, token)` sin cambiar el modelo de datos.

### D2. Supabase como base, con SQLite como modo local
Supabase da en un solo servicio Postgres (el esquema actual es relacional y migra casi sin cambios), Auth con email y contraseña (D4) y Storage para los archivos originales de los documentos (D6). El plan gratuito alcanza para el TP.
*Alternativas descartadas:*
- **Seguir solo con SQLite:** no sirve si el panel y el bot corren en máquinas distintas o si el grupo comparte datos, y el login y el guardado de archivos habría que escribirlos a mano.
- **Postgres solo (Neon, Railway):** resuelve la base pero no el login ni los archivos, que habría que sumar como dos servicios más.
- **Firebase:** es documental (NoSQL), lo que obliga a reescribir todas las consultas relacionales de `plataforma/` y del Gastos.

### D3. Acceso a datos con SQLAlchemy Core sobre una URL
`ELISEO_DB_URL` define la base: `postgresql+psycopg://...` (Supabase) o, si falta, `sqlite:///data/eliseo.db`. `plataforma/` pasa de `sqlite3` a SQLAlchemy Core (tablas declaradas en un solo módulo, consultas con `text()` o el constructor de Core y parámetros con nombre), que genera el SQL de cada motor. No se usa el ORM: las funciones de `lectura` y `escritura` siguen devolviendo dicts y contratos Pydantic como hoy.
*Alternativas descartadas:*
- **Cliente REST de Supabase (PostgREST) para todo:** no hay transacciones entre varias escrituras (la ejecución y la decisión del panel las necesitan) y los tests necesitarían red.
- **`psycopg` directo:** obliga a mantener dos dialectos de SQL a mano, o a correr Postgres en todos los tests.
- **Alembic para migraciones:** el esquema se crea con `metadata.create_all`, que es idempotente. Alembic se agrega cuando haya datos reales que migrar.

El CI corre los tests dos veces: con SQLite y contra un Postgres de servicio de GitHub Actions, para que los dos modos no se separen.

### D4. Login con Supabase Auth y fallback local
Con Supabase configurado, el panel valida email y contraseña con Supabase Auth desde el servidor y guarda la sesión en `st.session_state`. La tabla `administradores(auth_user_id, administracion_id, email, nombre)` asocia la cuenta a su administración. Sin Supabase (tests y demo local), el panel valida contra la misma tabla con un hash `bcrypt` guardado en la base. Las dos variantes implementan una interfaz `autenticar(email, password) -> Sesion | None`, y los tests usan la local.
*Alternativas descartadas:*
- **`streamlit-authenticator` con un YAML:** las cuentas viven en un archivo del repo y no se pueden administrar por cliente.
- **`st.login` con OIDC (Google):** obliga a que cada administración tenga una cuenta de un proveedor y a registrar la app en ese proveedor.

### D5. Aislamiento en `servicio.py`, no en la interfaz
Toda función de `panel/servicio.py` recibe la `Sesion` y filtra por `consorcios.administracion_id = sesion.administracion_id` dentro de la consulta. Un id de caso o de consorcio que no es de la sesión se trata como inexistente (no se distingue "no existe" de "no es tuyo"). El backend se conecta con la clave de servicio, que no aplica Row Level Security, así que RLS no protege al panel. Igual se activa RLS sin políticas para el rol `anon`, para que la clave pública de Supabase no pueda leer ninguna tabla aunque se filtre.
*Alternativa descartada:* RLS como mecanismo principal, con el panel conectado con el token del usuario. Obliga a pasar el token a cada consulta y a duplicar las reglas en SQL, y el bot y los agentes igual necesitan la clave de servicio.

### D6. Documentos en la base; Storage solo para el original
Tabla `documentos(id, consorcio_id, tipo, contenido_md, archivo_path, estado, indexado, subido_por, creado, dado_de_baja)`, con `estado` en `activo`, `reemplazado` o `baja`. El Markdown validado se guarda en la base y el archivo original va a Supabase Storage (o a `data/archivos/` en modo local). `corpus.cargar_corpus` arma el corpus parseando el `contenido_md` de los documentos activos con el parser que ya existe (`_secciones` y `_parse_meta`), así que el Documental, el verificador y el Mediador no cambian. El caché pasa a tener como clave `(consorcio_id, versión)`, donde la versión es la fecha de la última modificación de los documentos del consorcio, para que un cambio valga en el próximo mensaje.
Para que las citas viejas sigan mostrando su texto, `_texto_fuente` busca primero en el corpus vigente y, si no está, en los documentos dados de baja o reemplazados del consorcio.
*Alternativas descartadas:*
- **Seguir con archivos en disco:** el panel y el bot pueden correr en máquinas distintas.
- **Leer el corpus de Storage en cada consulta:** agrega red y latencia a cada respuesta.

### D7. Formato de carga: el Markdown canónico del corpus
Se carga el mismo formato que hoy usa `data/consorcios/*/` (encabezados `## REG-<n> · Título` y `## ACTA-<fecha>#<punto> · Título`, con metadata en el comentario). El consorcio lo fija la sesión: si el comentario trae un `consorcio_id` distinto, se rechaza. Se publica una plantilla descargable desde el panel.
*Alternativa descartada:* subir un PDF y partirlo con un LLM. El parseo produce ids y vigencias que el verificador asume ciertos; un error ahí rompe la regla "sin cita verificada no hay respuesta". Queda para la idea I8.

### D8. Indexación al confirmar, con reintento
Al confirmar se guarda el documento y se llama a `ingesta.sincronizar` del consorcio (y a la de precedentes si hiciera falta), que agrega lo nuevo y borra lo que ya no está activo. Si Pinecone falla, el documento queda con `indexado = false` y el panel ofrece reintentar. Mientras tanto, el Documental lo encuentra por BM25, que se arma desde la base. Una baja de consorcio borra sus records de los dos namespaces.

### D9. Chat de avisos por administración con código de un solo uso
`administraciones.chat_avisos_id` reemplaza a `TELEGRAM_CHAT_ADMIN_ID`. El panel genera un código aleatorio de 8 caracteres; en la base se guarda solo su hash, con vencimiento a 15 minutos y marca de usado. El bot agrega el comando `/admin <código>`. `ejecucion.chat_de_destino("admin:<consorcio>")` resuelve consorcio → administración → `chat_avisos_id`, y si falta, el mensaje queda pendiente.
*Alternativa descartada:* que el administrador pegue su chat id en el panel (como hoy con `/chatid`). Cualquiera podría poner el chat de otra persona y redirigir avisos que contienen datos de vecinos.

### D10. Checkpoints en la misma base
Con Postgres se usa `PostgresSaver` (`langgraph-checkpoint-postgres`) sobre la misma URL; con SQLite, el `SqliteSaver` actual. Así el panel y el bot pueden correr en máquinas distintas y seguir retomando el mismo caso.

### D11. Bajas
- **Consorcio:** baja lógica (`consorcios.activo = false`). `identidad_por_telefono` ignora a los vecinos de consorcios inactivos, sus documentos salen de Pinecone y el historial queda.
- **Vecino:** borrado físico de la fila y de sus `vinculos_canal`. Los casos referencian la unidad, no al vecino, así que el historial queda.
- **Hilo de conversación de un vecino dado de baja:** queda en el checkpointer pero es inalcanzable, porque `identificar` corta antes. El seguimiento de reclamos incompletos lo saltea si el teléfono ya no está en el padrón.

### D12. Seed no destructivo
`scripts/seed_db.py` crea las tablas si faltan y carga la administración de demo, su cuenta de prueba y el Consorcio Rivadavia 4520 solo si no existen (por id). Los documentos de demo se cargan desde `data/consorcios/rivadavia-4520/` como si se subieran por el panel. `--reset` borra y recrea todo, y pide confirmación si la URL es de Postgres. La evaluación e2e sigue usando una base SQLite temporal recién sembrada por corrida.

## Risks / Trade-offs

- [El plan gratuito de Supabase pausa el proyecto tras una semana sin uso] → Probar la conexión con `check_servicios.py` antes de una demo, y si falla, usar el modo SQLite local, que sigue completo.
- [Los modos SQLite y Postgres se separan con el tiempo] → El CI corre la suite contra los dos (D3).
- [La clave de servicio de Supabase da acceso total a la base] → Vive solo en el `.env` del servidor y en los secretos del CI. El panel nunca la expone al navegador, porque Streamlit corre del lado del servidor. Se agrega a `check_servicios.py` una verificación de que el `.env` no esté versionado.
- [Un documento válido en formato pero con contenido equivocado] → La vista previa obliga a revisar la partición antes de confirmar, y el reemplazo o la baja se revierten subiendo de nuevo el archivo original, que queda guardado.
- [Una administración nueva no tiene criterios para el Mediador] → El Mediador ya funciona sin criterios: `criterios.bloque_criterios` pone "Esta administración no cargó criterios." en lugar del archivo. Como los criterios se buscan por el nombre de la administración, renombrar una administración los desconecta; se agrega un test con una administración sin archivo.
- [El teléfono único impide que una persona sea vecina en dos consorcios] → Es un non-goal explícito. El mensaje de error no revela en qué consorcio está registrado.
- [Cambiar `plataforma/` toca el código de casi todos los changes] → Se hace primero y en un paso aparte, con la suite actual en verde antes y después y sin cambios de comportamiento (grupo 1 de tasks).

## Migration Plan

1. Archivar `canal-telegram-intake` y `panel-admin-ejecucion`, para que este change modifique specs archivadas.
2. Grupo 1 de tasks: pasar `plataforma/` a SQLAlchemy sin cambiar el comportamiento, con la suite en verde sobre SQLite.
3. Crear el proyecto de Supabase, cargar `ELISEO_DB_URL` y las claves en el `.env` y en los secretos del CI, y correr `seed_db.py` e `ingest.py R4520`.
4. Vuelta atrás: sacar `ELISEO_DB_URL` del `.env`. El sistema vuelve a SQLite local con los datos de demo. No se migran datos de Supabase a SQLite.

## Open Questions

- Quién es el dueño del change. No cambia el diseño, pero lo exige la regla de proposals.
- Si Supabase manda el mail de invitación a la cuenta nueva o el script imprime un enlace para fijar la contraseña. Depende de la configuración de correo del proyecto de Supabase y se decide al crearlo.
