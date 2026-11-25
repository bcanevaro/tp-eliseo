## Why

Hoy hay un único consorcio cargado desde archivos y un panel sin login: quien lo abre ve y decide sobre todos los edificios, las urgencias de todos van a un solo chat (`TELEGRAM_CHAT_ADMIN_ID`) y sumar un edificio, un vecino o un acta exige editar JSON o Markdown y volver a sembrar la base, lo que además borra todo lo anterior. El DISCOVERY (§1.2 y §2) vende Eliseo a plataformas cuyos clientes son administraciones con carteras de 15 a 40 consorcios: sin cuentas por administración y sin alta de edificios, vecinos y documentos desde el panel, el producto no se puede mostrar con más de un cliente ni operar sin un desarrollador.

## What Changes

- **Cuentas de administración:** cada administración tiene una o más cuentas de administrador con email y contraseña. El panel exige iniciar sesión y muestra solo los consorcios de esa administración.
- **Padrón desde el panel:** el administrador da de alta, edita y da de baja edificios (consorcios con sus unidades y coeficientes) y vecinos (nombre, unidad y teléfono de Telegram). Dar de baja a un vecino le corta el acceso al bot en el acto.
- **Documentos por edificio desde el panel:** el administrador sube el reglamento y las actas de cada edificio, el sistema los valida (ids canónicos, fechas, artículos modificados), muestra cómo quedaron partidos y, al confirmar, los deja disponibles para el Documental, el verificador y el Mediador. Borrar un documento lo saca de las búsquedas.
- **Un solo bot para toda la app:** el vecino sigue entrando por el mismo bot; su edificio y su administración salen del teléfono, como hoy. El bot se presenta con el nombre de la administración del vecino.
- **Chat de urgencias por administración:** cada administración vincula su propio chat de Telegram con un código que genera el panel; las urgencias y avisos de un consorcio van solo al chat de su administración. **BREAKING:** `TELEGRAM_CHAT_ADMIN_ID` deja de usarse.
- **Base de datos en Supabase (Postgres)**, con Supabase Auth para el login y Supabase Storage para los archivos originales de los documentos. La base deja de recrearse en cada siembra: `scripts/seed_db.py` carga la administración y el consorcio de demo solo si no existen. **BREAKING:** la base y los checkpoints dejan de estar en `data/eliseo.db` cuando se configura Supabase; sin configurarlo, todo sigue funcionando sobre SQLite local (tests, CI y demo sin red).

## Capabilities

### New Capabilities

- `cuentas-admin`: login de administradores y aislamiento de todo lo que ve y hace el panel por administración.
- `padron-consorcios`: alta, edición y baja de consorcios, unidades y vecinos desde el panel, y su efecto sobre el acceso al bot.
- `documentos-consorcio`: carga, validación, reemplazo y baja del reglamento y las actas de cada consorcio desde el panel, y su sincronización con la búsqueda del Documental.
- `canal-administracion`: vinculación del chat de Telegram de cada administración y ruteo de urgencias y avisos al chat que corresponde.

### Modified Capabilities

- `datos-ficticios`: la base deja de crearse desde cero en cada siembra; la demo se carga solo si falta, incluye una administración con cuenta de prueba, y la base puede ser Postgres (Supabase) o SQLite local.

## Impact

- **Dueño:** a definir en el grupo (lo propone Juani).
- **Depende de:** `bootstrap-proyecto` (contratos, base y grafo), `agente-documental` (corpus, ingesta y verificador), `canal-telegram-intake` (vinculación por teléfono y outbox) y `panel-admin-ejecucion` (panel y ejecución). Conviene archivar estos dos últimos antes de implementar, porque este change toca su código.
- **Origen:** DISCOVERY §1.2 (modelo B2B por administración), §2 (persona: administrador con 15 a 40 consorcios; "cada vecino se identifica por el teléfono registrado") y §7 riesgo 2 (fallback de carga manual del reglamento); caja "Panel del administrador" del artefacto.
- **Código afectado:** `eliseo/plataforma/` (de `sqlite3` a una capa que hable Postgres y SQLite), `eliseo/corpus.py` (el corpus sale de la base, no de archivos), `eliseo/panel/` (login y tres vistas nuevas), `eliseo/ejecucion/` (destino `admin:` por administración), `eliseo/canal/bot.py` (comando de vinculación del chat de la administración), `eliseo/grafo/runtime.py` (checkpointer Postgres), `scripts/seed_db.py` y `scripts/ingest.py`.
- **Dependencias nuevas:** `supabase` (Auth y Storage), `sqlalchemy` y `psycopg` (acceso a Postgres), `langgraph-checkpoint-postgres`.
- **Configuración nueva:** `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY` y `ELISEO_DB_URL`.
