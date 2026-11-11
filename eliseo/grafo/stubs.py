"""Stubs determinísticos de los nodos reemplazables (spec grafo-orquestacion, "Nodos reemplazables").

Ninguno usa un LLM: sirven para que el grafo corra de punta a punta desde el día uno y como
ejemplo del contrato de cada nodo. Cada integrante reemplaza los suyos en `nodos.py`:

    canal-telegram-intake   → intake, completar_datos
    agente-documental       → documental, verificar_consulta, responder_reglamento, documental_caso
    agente-gastos           → gastos, responder_gastos
    flujo-reclamo-mediador  → precedentes, mediador, verificar_dictamen
    panel-admin-ejecucion   → avisar_urgencia, derivar_sin_fuente, hablar_con_admin, ejecucion, rechazo

Contrato de todos los nodos: reciben el estado (EstadoConversacion o EstadoGrafoCaso) y devuelven
un dict con las claves que actualizan. Los mensajes al vecino del turno van en "salidas".
"""
import re

from eliseo import textos, verificador
from eliseo.corpus import cargar_corpus
from eliseo.formato import nombre_periodo, normalizar, pesos
from eliseo.plataforma import escritura, lectura
from eliseo.plataforma.db import get_conn
from eliseo.schemas import (
    Cita,
    Dictamen,
    EstadoCaso,
    Hipotesis,
    Intent,
    LineaGasto,
    MensajeSaliente,
    ReclamoBorrador,
    Recomendacion,
    RespuestaDocumental,
    RespuestaGastos,
    RespuestaVecino,
    ResultadoIntake,
)

# ---------------------------------------------------------------- intake (canal-telegram-intake)

_URGENCIA = ["gas", "encerrad", "atrapad", "incendio", "fuego", "humo", "chispa", "electrocut", "inund"]
_RECLAMO = ["humedad", "filtra", "gotea", "goteo", "llueve", "perdida", "mancha", "rot", "no anda", "no funciona"]
_GASTOS = ["expensa", "pague", "pagar", "pago", "debo", "deuda", "gasto", "factura", "cuenta", "saldo",
           "cuanto se", "liquidacion", "subio"]
_REGLAMENTO = ["puedo", "se puede", "reglamento", "permit", "prohib", "toldo", "perro", "gato", "mascota",
               "obra", "horario", "pileta", "bicicleta", "ruido"]
# Reescritura de lenguaje vecinal a lenguaje de reglamento (el intake real la hace con el LLM).
_SINONIMOS = {"perro": "animales domesticos", "gato": "animales domesticos", "mascota": "animales domesticos",
              "toldo": "toldos fachada", "obra": "obras horario", "ruido": "ruidos molestos convivencia",
              "bicicleta": "bicicletas partes comunes"}
_AMBIENTES = ["baño", "cocina", "living", "comedor", "dormitorio", "habitacion", "balcon", "lavadero", "pasillo"]


def _tiene(texto: str, claves: list[str]) -> bool:
    return any(c in texto for c in claves)


def _extraer_reclamo(texto_original: str) -> ReclamoBorrador:
    t = normalizar(texto_original)
    ambiente = next((a for a in _AMBIENTES if normalizar(a) in t), None)
    gotea = True if re.search(r"\b(gotea|goteo|llueve|si)\b", t) else False if re.search(r"\b(mancha|no gotea|no)\b", t) else None
    desde = re.search(r"\b(desde|hace|ayer|anoche|semana|mes|dias)\b.*", t)
    return ReclamoBorrador(ambiente=ambiente, descripcion=texto_original.strip(),
                           desde_cuando=desde.group(0) if desde else None, gotea=gotea)


def intake(state: dict) -> dict:
    texto = state["mensaje"].texto
    t = normalizar(texto)
    intents: list[Intent] = []
    if t == normalizar(textos.BOTON_RECLAMO) or _tiene(t, _RECLAMO) or (state.get("reclamo_en_curso") and t):
        intents.append(Intent.RECLAMO)
    if t == normalizar(textos.BOTON_EXPENSAS) or _tiene(t, _GASTOS):
        intents.append(Intent.GASTOS)
    if _tiene(t, _REGLAMENTO) and Intent.RECLAMO not in intents:
        intents.append(Intent.REGLAMENTO)
    if not intents and state["mensaje"].adjuntos and state.get("reclamo_en_curso"):
        intents.append(Intent.RECLAMO)
    if not intents:
        intents.append(Intent.UNKNOWN)

    reescrita = " ".join(_SINONIMOS.get(p, p) for p in t.replace("?", " ").replace("¿", " ").split())
    resultado = ResultadoIntake(
        intent=intents[0],
        multi=intents[1:],
        urgencia=_tiene(t, _URGENCIA),
        pregunta_reescrita=reescrita,
        reclamo=_extraer_reclamo(texto) if Intent.RECLAMO in intents else None,
    )
    if resultado.reclamo:
        resultado.campos_faltantes = resultado.reclamo.faltantes()
    return {"intake": resultado}


def completar_datos(state: dict) -> dict:
    """Junta lo extraído con lo que ya había y pide el primer dato que falta."""
    borrador = (state.get("reclamo_en_curso") or ReclamoBorrador()).completar(state["intake"].reclamo)
    fotos = [a for a in state["mensaje"].adjuntos if a.tipo == "foto"]
    if fotos:
        borrador = borrador.completar(ReclamoBorrador(fotos=fotos))
    faltan = borrador.faltantes()
    if not faltan:
        return {"reclamo_en_curso": borrador}
    pregunta = textos.PREGUNTAS_RECLAMO[faltan[0].value]
    aviso = "me falta 1 dato" if len(faltan) == 1 else f"me faltan {len(faltan)} datos"
    return {"reclamo_en_curso": borrador,
            "salidas": [MensajeSaliente(texto=f"Para registrar el reclamo {aviso}. {pregunta}")]}


# ---------------------------------------------------------------- documental (agente-documental)

_STOP = set("de la el los las un una y o a en que por para con del al se mi me es lo le su sus como "
            "puedo puede tener poner hay quiero saber".split())


def _buscar(consorcio_id: str, consulta: str, k: int = 3) -> list:
    """Búsqueda léxica mínima sobre el corpus vigente (el real es híbrido con Pinecone)."""
    palabras = {p[:6] for p in normalizar(consulta).split() if len(p) > 3 and p not in _STOP}
    puntaje = []
    for doc in cargar_corpus(consorcio_id):
        texto = {p[:6] for p in normalizar(doc.titulo + " " + doc.texto).split()}
        score = len(palabras & texto)
        if score >= 2:
            puntaje.append((score, doc))
    return [d for _, d in sorted(puntaje, key=lambda x: -x[0])[:k]]


def _primera_oracion(texto: str) -> str:
    return texto.split(". ")[0].rstrip(".") + "."


def _citas_de(docs: list, consorcio_id: str) -> list[Cita]:
    corpus = cargar_corpus(consorcio_id)
    citas, vistos = [], set()
    for doc in docs:
        # Si un acta modifica el artículo, se cita también (o en su lugar, si lo reemplaza).
        refs = [] if doc.reemplazado_por else [doc.ref]
        refs += doc.modificado_por
        for ref in refs:
            if ref in vistos:
                continue
            vistos.add(ref)
            d = corpus.get(ref)
            citas.append(Cita(documento=d.tipo, referencia=ref, fragmento=_primera_oracion(d.texto)))
    return citas


def documental(state: dict) -> dict:
    ident = state["identidad"]
    consulta = state["intake"].pregunta_reescrita or state["mensaje"].texto
    docs = _buscar(ident.consorcio_id, consulta, k=1)
    citas = _citas_de(docs, ident.consorcio_id)
    respuesta = " ".join(f"{c.referencia}: {c.fragmento}" for c in citas)
    return {"documental": RespuestaDocumental(respuesta=respuesta[:600], citas=citas, suficiente=bool(citas))}


def verificar_consulta(state: dict) -> dict:
    doc = state["documental"]
    if not doc.suficiente or not doc.citas:
        return {"verificacion_consulta": {"ok": False, "fallas": [], "motivo": "sin evidencia"}}
    return {"verificacion_consulta": verificador.verificar_citas(state["identidad"].consorcio_id, doc.citas)}


def _con_fuentes(texto: str, refs: list[str]) -> str:
    return f"{texto}\n\nFuente: {', '.join(refs)}" if refs else texto


def responder_reglamento(state: dict) -> dict:
    doc = state["documental"]
    r = RespuestaVecino(respuesta=doc.respuesta, citas=doc.citas)
    return {"salidas": [MensajeSaliente(texto=_con_fuentes(r.respuesta, [c.referencia for c in r.citas]))]}


def documental_caso(state: dict) -> dict:
    caso = state["caso"]
    consulta = f"cañerías montantes uso exclusivo agua {caso.reclamo.descripcion}"
    docs = _buscar(caso.consorcio_id, consulta, k=3)
    # Actas posteriores que mencionan la misma instalación (p. ej. la montante de la columna).
    columna = caso.unidad_id[-1]
    docs += [a for a in cargar_corpus(caso.consorcio_id).actas() if f"columna {columna.lower()}" in normalizar(a.texto)]
    citas = _citas_de(docs, caso.consorcio_id)
    return {"documental": RespuestaDocumental(respuesta="", citas=citas, suficiente=bool(citas))}


# ---------------------------------------------------------------- gastos (agente-gastos)

def gastos(state: dict) -> dict:
    ident, conn = state["identidad"], get_conn()
    t = normalizar(state["mensaje"].texto)
    if _tiene(t, ["debo", "deuda", "saldo", "cuenta"]):
        cc = lectura.cuenta_corriente(conn, ident)
        ultimo = cc["movimientos"][-1]
        texto = f"El saldo de tu cuenta ({ident.unidad}) es {pesos(cc['saldo_deudor'])}."
        return {"gastos": RespuestaGastos(respuesta=texto, lineas=[
            LineaGasto(concepto=ultimo["concepto"], monto=ultimo["debe"] or ultimo["haber"], comprobante=ultimo["comprobante"])])}

    periodos = lectura.periodos_liquidados(conn, ident.consorcio_id)
    actual = lectura.liquidacion(conn, ident.consorcio_id, periodos[-1])
    if len(periodos) < 2:
        return {"gastos": RespuestaGastos(respuesta=f"Total de {nombre_periodo(periodos[-1])}: {pesos(actual['total'])}.",
                                          lineas=actual["lineas"])}
    previa = lectura.liquidacion(conn, ident.consorcio_id, periodos[-2])
    ya = {(l.concepto, l.monto) for l in previa["lineas"]}
    nuevas = [l for l in actual["lineas"] if (l.concepto, l.monto) not in ya]
    diferencia = actual["total"] - previa["total"]  # lo calcula código, no el LLM
    texto = (f"La expensa de {nombre_periodo(periodos[-1])} fue {pesos(actual['total'])}, "
             f"{pesos(diferencia)} más que {nombre_periodo(periodos[-2])}, por estos gastos:")
    return {"gastos": RespuestaGastos(respuesta=texto, lineas=nuevas)}


def responder_gastos(state: dict) -> dict:
    g = state["gastos"]
    lineas = [f"• {l.concepto}: {pesos(l.monto)}" + (f" ({l.comprobante})" if l.comprobante else " (sin comprobante cargado)")
              for l in g.lineas]
    return {"salidas": [MensajeSaliente(texto="\n".join([g.respuesta, *lineas]))]}


# ---------------------------------------------------------------- reclamo (flujo-reclamo-mediador)

def precedentes(state: dict) -> dict:
    caso = state["caso"]
    columna = f"columna {caso.unidad_id[-1]}"
    encontrados = [p for p in lectura.precedentes(get_conn(), caso.consorcio_id, tipo="filtracion")
                   if columna.lower() in (p["ubicacion"] or "").lower()]
    return {"precedentes": encontrados}


def mediador(state: dict) -> dict:
    caso, doc = state["caso"], state["documental"]
    refs = [c.referencia for c in doc.citas] if doc else []
    precs = [p["prec_id"] for p in state.get("precedentes", [])]
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
    dictamen = Dictamen(
        hechos=[f"{caso.reclamo.descripcion} ({caso.reclamo.ambiente or 'ambiente sin indicar'})"],
        hipotesis=hipotesis,
        recomendacion=Recomendacion(tipo="inspeccion", accion="Inspección de un plomero matriculado en la unidad, la superior y la montante"),
        mensaje_vecino=(f"Revisamos tu reclamo #{caso.caso_id}. Para saber a quién le corresponde la reparación hace "
                        "falta una inspección: te contactamos para coordinarla."),
    )
    return {"dictamen": dictamen}


def verificar_dictamen(state: dict) -> dict:
    v = verificador.verificar_dictamen(state["caso"].consorcio_id, state["dictamen"])
    return {"verificacion": v, "vueltas": state.get("vueltas", 0) + (0 if v["ok"] else 1)}


# ---------------------------------------------------------------- panel y ejecución (panel-admin-ejecucion)

def avisar_urgencia(state: dict) -> dict:
    ident, conn = state["identidad"], get_conn()
    texto = state["mensaje"].texto
    escritura.crear_derivacion(conn, "urgencia", texto, consorcio_id=ident.consorcio_id,
                               unidad_id=ident.unidad_id, telefono=ident.telefono)
    escritura.encolar_mensaje(conn, f"admin:{ident.consorcio_id}",
                              MensajeSaliente(texto=f"URGENCIA {ident.unidad} ({ident.nombre}): {texto}"))
    tel = lectura.consorcio(conn, ident.consorcio_id)["telefono_emergencias"]
    return {"salidas": [MensajeSaliente(texto=textos.URGENCIA.format(telefono_emergencias=tel))]}


def derivar_sin_fuente(state: dict) -> dict:
    ident = state["identidad"]
    escritura.crear_derivacion(get_conn(), "sin_fuente", state["mensaje"].texto, consorcio_id=ident.consorcio_id,
                               unidad_id=ident.unidad_id, telefono=ident.telefono,
                               detalle={"verificacion": state.get("verificacion_consulta")})
    return {"salidas": [MensajeSaliente(texto=textos.DERIVADO_SIN_FUENTE)]}


def hablar_con_admin(state: dict) -> dict:
    ident = state["identidad"]
    escritura.crear_derivacion(get_conn(), "hablar_con_admin", state["mensaje"].texto, consorcio_id=ident.consorcio_id,
                               unidad_id=ident.unidad_id, telefono=ident.telefono)
    return {"salidas": [MensajeSaliente(texto=textos.DERIVADO_HABLAR)]}


def ejecucion(state: dict) -> dict:
    conn, caso, decision = get_conn(), state["caso"], state["decision"]
    dictamen_id = state["dictamen_id"]
    texto = decision.mensaje_final or state["dictamen"].mensaje_vecino
    refs = sorted(state["dictamen"].todas_las_citas())
    escritura.encolar_mensaje(conn, f"vecino:{state['telefono']}", MensajeSaliente(texto=_con_fuentes(texto, refs)),
                              clave=f"dictamen:{dictamen_id}:vecino")
    rec = state["dictamen"].recomendacion
    escritura.crear_pedido(conn, caso.caso_id, dictamen_id, "inspeccion" if rec.tipo == "inspeccion" else "trabajo", rec.accion)
    return {"caso": escritura.cambiar_estado(conn, caso.caso_id, EstadoCaso.APROBADO)}


def rechazo(state: dict) -> dict:
    conn, caso, decision = get_conn(), state["caso"], state["decision"]
    if decision.mensaje_final:
        escritura.encolar_mensaje(conn, f"vecino:{state['telefono']}",
                                  MensajeSaliente(texto=decision.mensaje_final, de_la_administracion=True),
                                  clave=f"dictamen:{state['dictamen_id']}:rechazo")
    return {"caso": escritura.cambiar_estado(conn, caso.caso_id, EstadoCaso.RECHAZADO)}
