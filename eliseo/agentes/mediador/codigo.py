"""Modo sin LLM del Mediador (design D6): arma el dictamen por reglas con las citas y los precedentes recibidos.

Se usa con `MEDIADOR_MODO=codigo` (tests), si el proxy falla y tras dos salidas con formato inválido.
Siempre recomienda inspección: el código no decide a quién le corresponde.
"""
from eliseo.schemas import Caso, Dictamen, Hipotesis, Recomendacion, RespuestaDocumental

ACCION_INSPECCION = "Inspección de un plomero matriculado en la unidad, la superior y la montante"


def mensaje_inspeccion(caso: Caso) -> str:
    """Aviso neutral al vecino: no asigna culpa ni nombra a nadie."""
    return (f"Revisamos tu reclamo #{caso.caso_id}. Para saber a quién le corresponde la reparación hace "
            "falta una inspección: te contactamos para coordinarla.")


def dictamen_codigo(caso: Caso, documental: RespuestaDocumental | None, precedentes: list[dict]) -> Dictamen:
    refs = [c.referencia for c in documental.citas] if documental else []
    # Solo los precedentes resueltos contra el consorcio respaldan la hipótesis de la montante.
    precs = [p["prec_id"] for p in precedentes or [] if p.get("responsable") == "consorcio"]
    hipotesis = []
    if "REG-15" in refs:
        hipotesis.append(Hipotesis(
            id="A", responsable="unidad", descripcion="Pérdida en una instalación de uso exclusivo de la unidad superior",
            citas=["REG-15"], a_favor=["La mancha está debajo de otra unidad"], en_contra=[],
            confirmaria="Prueba de la instalación de la unidad superior con la montante cerrada"))
    a_consorcio = [r for r in refs if r == "REG-16" or r.startswith("ACTA-")] + precs
    if a_consorcio:
        hipotesis.append(Hipotesis(
            id="B" if hipotesis else "A", responsable="consorcio", descripcion="Pérdida en la montante general de la columna",
            citas=a_consorcio, a_favor=["Hay antecedentes o una obra aprobada sobre la misma columna"] if len(a_consorcio) > 1 else [],
            en_contra=[], confirmaria="Inspección de la montante a la altura de la unidad"))
    return Dictamen(
        hechos=[f"{caso.reclamo.descripcion} ({caso.reclamo.ambiente or 'ambiente sin indicar'})"],
        hipotesis=hipotesis,
        recomendacion=Recomendacion(tipo="inspeccion", accion=ACCION_INSPECCION),
        mensaje_vecino=mensaje_inspeccion(caso),
    )
