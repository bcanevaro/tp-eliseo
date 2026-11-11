## ADDED Requirements

### Requirement: Verificación determinística
El verificador SHALL ser código sin LLM. Para cada `Cita` SHALL comprobar que (1) la `referencia` existe en el corpus o en la base del consorcio, (2) está vigente a la fecha del caso y (3) el `fragmento` aparece literalmente en el texto de esa referencia (normalizando espacios, mayúsculas y puntuación). Devuelve el resultado por cita y un veredicto global.

#### Scenario: Cita válida
- **WHEN** una cita apunta a `REG-15` con un fragmento copiado del artículo 15
- **THEN** el verificador la marca válida

#### Scenario: Fragmento inventado
- **WHEN** la referencia existe pero el fragmento no aparece en su texto
- **THEN** la cita es inválida con motivo "fragmento no encontrado"

#### Scenario: Fragmento recortado
- **WHEN** el fragmento es "Ningún propietario podrá modificar la fachada..." (un recorte con puntos suspensivos)
- **THEN** la cita es válida si cada tramo entre los puntos suspensivos aparece literal y en orden en el texto de la referencia

#### Scenario: Artículo derogado
- **WHEN** la cita apunta a un artículo cuyo texto fue reemplazado por un acta anterior a la fecha del caso
- **THEN** la cita es inválida con motivo "no vigente" e indica el acta vigente

### Requirement: Abstención en la rama de consulta
En la rama reglamento, si alguna afirmación queda sin cita válida, el sistema SHALL abstenerse: el vecino recibe el aviso de derivación y la consulta cae en el panel con las citas rechazadas y sus motivos.

#### Scenario: Una de dos citas inválida
- **WHEN** la respuesta tiene dos citas y una no pasa el verificador
- **THEN** la respuesta no se envía tal cual: se reintenta sin la afirmación no sostenida o se deriva

### Requirement: Uso en el loop del Mediador
El verificador SHALL exponer una función que reciba un `Dictamen` y devuelva qué citas de qué hipótesis fallan, para que el grafo de caso reintente (máximo 2 vueltas) o pase a la hipótesis de inspección.

#### Scenario: Dictamen con una hipótesis sin respaldo
- **WHEN** la hipótesis A cita `REG-99`, que no existe
- **THEN** el verificador devuelve que la hipótesis A falla con motivo "referencia inexistente"
