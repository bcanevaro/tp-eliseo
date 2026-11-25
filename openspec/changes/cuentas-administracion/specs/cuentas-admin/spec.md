## Purpose

Que cada administración entre al panel con su propia cuenta y vea, decida y modifique solo lo de sus consorcios, sin acceso a los de otra administración.

## ADDED Requirements

### Requirement: Login obligatorio en el panel
El panel SHALL exigir iniciar sesión con email y contraseña antes de mostrar cualquier dato. Una cuenta pertenece a una sola administración. Sin sesión válida, el panel SHALL mostrar solo el formulario de ingreso.

#### Scenario: Ingreso correcto
- **WHEN** la administradora de la Administración Méndez ingresa su email y contraseña correctos
- **THEN** el panel abre con la bandeja y el selector muestra solo los consorcios de la Administración Méndez

#### Scenario: Contraseña incorrecta
- **WHEN** alguien ingresa un email registrado con una contraseña equivocada
- **THEN** el panel muestra "Email o contraseña incorrectos", sin decir cuál de los dos falló, y no muestra ningún dato

#### Scenario: Sin sesión
- **WHEN** alguien abre la URL del panel sin haber iniciado sesión
- **THEN** ve solo el formulario de ingreso

### Requirement: Cierre de sesión
El panel SHALL ofrecer "Cerrar sesión" en todas las vistas. Al cerrarla, ninguna vista SHALL volver a mostrar datos hasta un nuevo ingreso.

#### Scenario: Cerrar sesión
- **WHEN** la administradora toca "Cerrar sesión"
- **THEN** el panel vuelve al formulario de ingreso y recargar la página no muestra la bandeja

### Requirement: Aislamiento por administración
Toda lectura y escritura del panel (bandeja, detalle, decisiones, historial, padrón, documentos y simulador de vecino) SHALL limitarse a los consorcios de la administración de la sesión. El filtro SHALL aplicarlo el servidor a partir de la sesión, nunca a partir de un valor que elija la interfaz.

#### Scenario: Caso de otra administración
- **WHEN** una cuenta de la Administración Méndez pide el detalle o intenta decidir sobre un caso de un consorcio de otra administración, aunque conozca su número
- **THEN** el sistema responde como si el caso no existiera y no registra ninguna decisión

#### Scenario: Selector de consorcio
- **WHEN** una administración con dos consorcios inicia sesión y existen otros consorcios en la base
- **THEN** el selector ofrece exactamente sus dos consorcios

### Requirement: Decisión firmada por la cuenta
Toda decisión sobre un dictamen (aprobar, modificar o rechazar) y toda respuesta manual SHALL registrar como autor la cuenta que tenía la sesión, en lugar de un nombre escrito a mano.

#### Scenario: Autor de una aprobación
- **WHEN** la administradora aprueba un dictamen
- **THEN** la decisión queda registrada con su cuenta como autora y el panel no pide "Quién decide"

### Requirement: Alta de cuentas
Las administraciones y sus cuentas SHALL crearse con un script de operación o desde la consola de la base, no desde el panel. Una cuenta nueva SHALL quedar asociada a exactamente una administración.

#### Scenario: Alta de una administración nueva
- **WHEN** se corre el script de alta con el nombre de la administración y el email de su primer administrador
- **THEN** la administración queda creada sin consorcios, el administrador recibe una forma de fijar su contraseña y, al ingresar, ve el panel vacío con la opción de dar de alta su primer edificio
