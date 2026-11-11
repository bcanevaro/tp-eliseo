## ADDED Requirements

### Requirement: Prorrateo por coeficiente
El motor SHALL calcular la parte de cada unidad en un gasto común como monto × coeficiente de la unidad, con redondeo a centavos, de modo que la suma de las partes sea exactamente el monto total (la diferencia de redondeo se asigna de forma determinística y documentada).

#### Scenario: Gasto de 100.000 pesos
- **WHEN** se prorratea un gasto de 100.000,00 entre las unidades del consorcio de demo
- **THEN** cada unidad recibe monto × coeficiente y la suma de las partes es exactamente 100.000,00

### Requirement: Mayorías del art. 2060
El motor SHALL determinar si una decisión de asamblea alcanza la mayoría requerida según el art. 2060 del Código Civil y Comercial (mayoría absoluta de propietarios, computada por unidades y por coeficientes) y según la mayoría especial que fije el reglamento para ese tipo de decisión, si la hay.

#### Scenario: Mayoría por unidades pero no por coeficientes
- **WHEN** votan a favor más de la mitad de las unidades pero suman menos de la mitad de los coeficientes
- **THEN** el motor devuelve que la mayoría no se alcanza e indica cuál de los dos cómputos falló

### Requirement: Sin LLM
El motor SHALL ser código puro, sin llamadas a modelos, con tests unitarios para cada regla.

#### Scenario: Ejecución sin red
- **WHEN** se corren los tests del motor sin acceso a la red
- **THEN** todos pasan
