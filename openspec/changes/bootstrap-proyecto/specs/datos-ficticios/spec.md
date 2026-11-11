## ADDED Requirements

### Requirement: Consorcio de demo
El repo SHALL incluir un consorcio ficticio completo, "Consorcio Rivadavia 4520", administrado por una administración ficticia, en `data/consorcios/rivadavia-4520/`. Ningún dato SHALL corresponder a personas, edificios o administraciones reales.

#### Scenario: Revisión de datos personales
- **WHEN** alguien revisa los datos de demo
- **THEN** todos los nombres, teléfonos y montos son inventados, y los teléfonos usan un rango que no pertenece a líneas reales

### Requirement: Corpus documental con ids canónicos
El corpus SHALL tener un reglamento de copropiedad con al menos 25 artículos, cada uno con id `REG-<n>`, y al menos 4 actas de asamblea con fecha y puntos numerados (id `ACTA-<fecha>#<punto>`). Cada documento SHALL guardar como metadata el consorcio, la fecha y la vigencia, y SHALL indicar si un acta modifica un artículo y cuál.

#### Scenario: Artículo modificado por un acta
- **WHEN** se carga el corpus
- **THEN** existe al menos un artículo (por ejemplo, el de toldos o fachada) modificado por un acta posterior, y la metadata del acta apunta al `REG-<n>` que modifica

#### Scenario: Temas que cubren los casos de test
- **WHEN** se buscan en el corpus los temas de los casos de test del artefacto
- **THEN** hay artículos sobre mascotas, fachada y toldos, cañerías de uso exclusivo y espacios comunes, y no hay ninguno sobre piletas (para el caso "sin fuente")

### Requirement: Base de la plataforma simulada
El sistema SHALL simular la plataforma de gestión con un SQLite que se crea desde cero con `scripts/seed_db.py`. La base SHALL tener tablas de consorcios, unidades (con coeficiente de prorrateo), vecinos con teléfono registrado, cuentas corrientes, liquidaciones con sus líneas, facturas, casos, dictámenes, decisiones y precedentes.

#### Scenario: Reseed idempotente
- **WHEN** se corre `scripts/seed_db.py` dos veces seguidas
- **THEN** la base queda en el mismo estado que después de la primera corrida

#### Scenario: Coeficientes consistentes
- **WHEN** se suman los coeficientes de todas las unidades del consorcio
- **THEN** la suma es 1 (o 100 %) con tolerancia de redondeo

### Requirement: Datos que ejercitan las ramas
Los datos de demo SHALL incluir, como mínimo:
- una liquidación de octubre 2026 que sube respecto de septiembre por gastos identificables con factura;
- un teléfono que no está registrado en la plataforma;
- un precedente aprobado de filtración por la montante de la columna B;
- un acta que aprueba el reemplazo de la montante B, todavía no ejecutado;
- una unidad con deuda.

#### Scenario: Suba de expensas explicable
- **WHEN** se comparan las liquidaciones de septiembre y octubre 2026
- **THEN** la diferencia se explica completa por líneas de la liquidación, cada una con su número de factura
