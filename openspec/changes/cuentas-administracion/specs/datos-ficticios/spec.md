## MODIFIED Requirements

### Requirement: Consorcio de demo
El repo SHALL incluir un consorcio ficticio completo, "Consorcio Rivadavia 4520", administrado por una administración ficticia, en `data/consorcios/rivadavia-4520/`. Ningún dato SHALL corresponder a personas, edificios o administraciones reales. La administración ficticia SHALL tener una cuenta de administrador de prueba, cuyo email y contraseña se documentan en el `.env.example` y nunca son credenciales de una persona real.

#### Scenario: Revisión de datos personales
- **WHEN** alguien revisa los datos de demo
- **THEN** todos los nombres, teléfonos y montos son inventados, y los teléfonos usan un rango que no pertenece a líneas reales

#### Scenario: Ingreso con la cuenta de prueba
- **WHEN** se siembra la demo y se ingresa al panel con la cuenta de prueba
- **THEN** el panel muestra el Consorcio Rivadavia 4520 y ningún otro

### Requirement: Base de la plataforma simulada
El sistema SHALL simular la plataforma de gestión con una base relacional: Postgres (Supabase) si está configurada, o un SQLite local si no. La base SHALL tener tablas de administraciones, cuentas de administrador, consorcios, unidades (con coeficiente de prorrateo), vecinos con teléfono registrado, documentos, cuentas corrientes, liquidaciones con sus líneas, facturas, casos, dictámenes, decisiones y precedentes.

#### Scenario: Reseed idempotente
- **WHEN** se corre `scripts/seed_db.py` dos veces seguidas
- **THEN** la base queda en el mismo estado que después de la primera corrida

#### Scenario: Sin Supabase configurado
- **WHEN** se corre `pytest` sin variables de Supabase y sin red
- **THEN** los tests usan una base SQLite local y pasan

#### Scenario: Coeficientes consistentes
- **WHEN** se suman los coeficientes de todas las unidades del consorcio
- **THEN** la suma es 1 (o 100 %) con tolerancia de redondeo

## ADDED Requirements

### Requirement: Siembra no destructiva
`scripts/seed_db.py` SHALL cargar la administración, la cuenta de prueba y el consorcio de demo solo si no existen, sin borrar ni modificar lo cargado desde el panel. Recrear la base desde cero SHALL requerir una opción explícita y, sobre Postgres, una confirmación.

#### Scenario: Seed sobre una base con datos del panel
- **WHEN** se dio de alta un edificio desde el panel y se vuelve a correr `scripts/seed_db.py`
- **THEN** el edificio sigue igual y la demo no se duplica

#### Scenario: Recrear la base
- **WHEN** se corre `scripts/seed_db.py --reset` sobre Postgres
- **THEN** el script pide confirmación antes de borrar y, si no se confirma, no cambia nada
