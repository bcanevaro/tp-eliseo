"""Motor de reglas determinístico (spec motor-reglas). Código puro: sin LLM y sin red.

    prorratear(monto, coeficientes)            parte de cada unidad, que suma exactamente el monto
    evaluar_mayoria(votos, coeficientes, tipo)  si una decisión alcanza la mayoría (art. 2060 CCyC)

Regla dura del proyecto: los montos, las mayorías y los prorrateos salen de acá o de la base,
nunca de un LLM. El LLM, como mucho, extrae del reglamento *qué* mayoría aplica.
"""
from dataclasses import dataclass, field
from decimal import ROUND_DOWN, Decimal
from fractions import Fraction

CENTAVO = Decimal("0.01")


class ErrorMotor(ValueError):
    pass


# ---------------------------------------------------------------- prorrateo

def prorratear(monto: Decimal, coeficientes: dict[str, Decimal]) -> dict[str, Decimal]:
    """Reparte `monto` según los coeficientes (que suman 1) con el método del mayor resto:

    1. A cada unidad le toca monto × coeficiente truncado al centavo.
    2. Los centavos que faltan para llegar al total se asignan de a uno a las unidades con mayor
       parte decimal descartada; los empates se desempatan por el id de la unidad (orden alfabético).

    Así la suma de las partes es exactamente el monto y el resultado no depende del orden de entrada.
    """
    monto = Decimal(monto)
    if monto != monto.quantize(CENTAVO):
        raise ErrorMotor(f"El monto {monto} tiene más de dos decimales")
    if not coeficientes:
        raise ErrorMotor("No hay unidades para prorratear")
    coefs = {u: Decimal(c) for u, c in coeficientes.items()}
    if any(c < 0 for c in coefs.values()):
        raise ErrorMotor("Hay coeficientes negativos")
    if sum(coefs.values()) != Decimal(1):
        raise ErrorMotor(f"Los coeficientes suman {sum(coefs.values())}, no 1")

    exactas = {u: monto * c for u, c in coefs.items()}
    partes = {u: e.quantize(CENTAVO, rounding=ROUND_DOWN) for u, e in exactas.items()}
    faltan = int((monto - sum(partes.values())) / CENTAVO)
    signo = CENTAVO if faltan >= 0 else -CENTAVO
    orden = sorted(coefs, key=lambda u: (-(abs(exactas[u] - partes[u])), u))
    for u in orden[:abs(faltan)]:
        partes[u] += signo
    assert sum(partes.values()) == monto
    return partes


# ---------------------------------------------------------------- mayorías

@dataclass(frozen=True)
class Mayoria:
    """Umbral sobre el total de unidades del consorcio (no sobre los presentes)."""
    nombre: str
    umbral: Fraction
    estricta: bool  # True: hace falta superar el umbral (mayoría absoluta = más de la mitad)

    def alcanza(self, parte: Fraction) -> bool:
        return parte > self.umbral if self.estricta else parte >= self.umbral


MAYORIAS = {
    # Art. 2060 CCyC y REG-27: mayoría absoluta de propietarios, por unidades y por porcentuales.
    "absoluta": Mayoria("mayoría absoluta", Fraction(1, 2), estricta=True),
    # Mayorías especiales que puede fijar la ley o el reglamento.
    "dos_tercios": Mayoria("dos tercios", Fraction(2, 3), estricta=False),
    "unanimidad": Mayoria("unanimidad", Fraction(1), estricta=False),
}


@dataclass
class ResultadoMayoria:
    mayoria: str
    alcanzada: bool
    unidades_a_favor: int
    unidades_total: int
    coeficiente_a_favor: Decimal
    por_unidades: bool
    por_coeficientes: bool
    fallas: list[str] = field(default_factory=list)


def evaluar_mayoria(votos: dict[str, bool | None], coeficientes: dict[str, Decimal],
                    tipo: str = "absoluta") -> ResultadoMayoria:
    """`votos`: unidad → True (a favor), False (en contra) o None (no votó / ausente).

    Se computa sobre el total de unidades del consorcio (las que no votan cuentan como no a favor),
    con el doble cómputo del art. 2060: por número de unidades y por coeficientes. Tienen que
    cumplirse los dos.
    """
    if tipo not in MAYORIAS:
        raise ErrorMotor(f"Mayoría desconocida: {tipo}. Opciones: {', '.join(MAYORIAS)}")
    desconocidas = set(votos) - set(coeficientes)
    if desconocidas:
        raise ErrorMotor(f"Votos de unidades que no son del consorcio: {sorted(desconocidas)}")
    m = MAYORIAS[tipo]
    a_favor = [u for u, v in votos.items() if v is True]
    total = len(coeficientes)
    coef = sum((Decimal(coeficientes[u]) for u in a_favor), Decimal(0))
    coef_total = sum((Decimal(c) for c in coeficientes.values()), Decimal(0))

    por_unidades = m.alcanza(Fraction(len(a_favor), total))
    por_coeficientes = m.alcanza(Fraction(coef) / Fraction(coef_total))
    fallas = []
    if not por_unidades:
        fallas.append(f"por unidades: {len(a_favor)} de {total} no alcanza {m.nombre}")
    if not por_coeficientes:
        fallas.append(f"por coeficientes: {coef} de {coef_total} no alcanza {m.nombre}")
    return ResultadoMayoria(m.nombre, por_unidades and por_coeficientes, len(a_favor), total, coef,
                            por_unidades, por_coeficientes, fallas)
