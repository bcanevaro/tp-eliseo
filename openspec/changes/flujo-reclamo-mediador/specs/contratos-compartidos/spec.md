## MODIFIED Requirements

### Requirement: Dictamen y decisión del administrador
El sistema SHALL modelar el borrador del Mediador como `Dictamen` según el master prompt del Mediador v1 (hechos, afirmaciones_sin_evidencia, hipotesis con id, responsable, descripcion, citas, a_favor, en_contra y confirmaria, recomendacion con tipo `asignar` o `inspeccion`, y mensaje_vecino). Cada hipótesis SHALL tener al menos una cita: una `Hipotesis` con `citas` vacías no valida. La respuesta del panel SHALL modelarse como `DecisionAdmin` (accion APROBAR, MODIFICAR o RECHAZAR, mensaje_final, motivo, admin_id).

#### Scenario: Recomendación de asignar sin hipótesis
- **WHEN** un `Dictamen` trae `recomendacion.tipo = "asignar"` y `recomendacion.hipotesis = null`
- **THEN** la validación del modelo falla

#### Scenario: Hipótesis sin citas
- **WHEN** un `Dictamen` trae una hipótesis con `citas = []`
- **THEN** la validación del modelo falla

#### Scenario: Rechazo sin motivo
- **WHEN** el panel envía una `DecisionAdmin` con `accion = RECHAZAR` y sin `motivo`
- **THEN** la validación falla, porque el motivo de rechazo se guarda para refinar el prompt
