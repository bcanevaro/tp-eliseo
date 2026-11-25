"""Panel del administrador (spec panel-admin). Correr con:

    streamlit run eliseo/panel/app.py

Solo dibuja: la lógica está en `servicio.py`. Incluye un simulador de vecino para probar y
mostrar el flujo completo sin Telegram (usa el mismo runtime que el bot).

Exige iniciar sesión (spec cuentas-admin): sin sesión solo se ve el formulario de ingreso, y
todo lo que se muestra sale de `servicio` filtrado por la administración de la cuenta.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from eliseo import cuentas  # noqa: E402
from eliseo.panel import servicio  # noqa: E402
from eliseo.schemas import AccionAdmin, EstadoCaso  # noqa: E402

st.set_page_config(page_title="Eliseo · Panel de la administración", page_icon="🏢", layout="wide")

st.markdown("""
<style>
.ia-label {display:inline-block; background:#ede7fb; color:#4a2a9c; border-radius:6px;
           padding:2px 8px; font-size:0.8rem; font-weight:600; margin-bottom:6px}
.cita-ok {color:#1b7a3d; font-weight:600}
.cita-mal {color:#b42318; font-weight:600}
.mensaje {border-left:4px solid #8a6cd8; padding:8px 12px; background:rgba(138,108,216,0.07);
          border-radius:4px; white-space:pre-wrap}
</style>
""", unsafe_allow_html=True)

ESTADOS = {
    EstadoCaso.PENDIENTE_APROBACION: "🟡 Pendiente de aprobación",
    EstadoCaso.APROBADO: "🟢 Aprobado",
    EstadoCaso.RECHAZADO: "🔴 Rechazado",
    EstadoCaso.EN_ANALISIS: "🔵 En análisis",
    EstadoCaso.INCOMPLETO: "⚪ Incompleto",
    EstadoCaso.REGISTRADO: "⚪ Registrado",
    EstadoCaso.CERRADO: "⚫ Cerrado",
}
ACCIONES = {"Aprobar": AccionAdmin.APROBAR, "Modificar": AccionAdmin.MODIFICAR, "Rechazar": AccionAdmin.RECHAZAR}


def ia(texto: str = "Escrito por la IA · revisalo antes de aprobar") -> None:
    st.markdown(f'<span class="ia-label">🤖 {texto}</span>', unsafe_allow_html=True)


def seleccionar(tipo: str, id_: int) -> None:
    st.session_state.sel = (tipo, id_)
    st.session_state.pop("pendiente", None)


# ---------------------------------------------------------------- sesión

def pantalla_ingreso() -> None:
    _, centro, _ = st.columns([1, 1.2, 1])
    with centro:
        st.title("🏢 Eliseo")
        st.caption("Panel de la administración")
        with st.form("ingreso"):
            email = st.text_input("Email", key="login-email")
            password = st.text_input("Contraseña", type="password", key="login-password")
            entrar = st.form_submit_button("Ingresar", type="primary", use_container_width=True)
        if entrar:
            sesion = cuentas.autenticar(email, password)
            if sesion is None:
                st.error(cuentas.ERROR_LOGIN)
            else:
                st.session_state.clear()
                st.session_state.admin_id = sesion.admin_id
                st.rerun()


def cerrar_sesion() -> None:
    st.session_state.clear()


# La sesión se relee de la base en cada interacción: si la cuenta se borra, deja de valer.
sesion = cuentas.sesion_de(st.session_state["admin_id"]) if st.session_state.get("admin_id") else None
if sesion is None:
    st.session_state.pop("admin_id", None)
    pantalla_ingreso()
    st.stop()


# ---------------------------------------------------------------- barra lateral

with st.sidebar:
    st.title("🏢 Eliseo")
    st.caption(f"{sesion.administracion} · {sesion.nombre}")
    vista = st.radio("Vista", ["Panel de la administración", "Simulador de vecino"], label_visibility="collapsed")
    consorcios = servicio.consorcios(sesion)
    if not consorcios:
        st.info("Tu administración todavía no tiene edificios.")
        st.button("Cerrar sesión", on_click=cerrar_sesion, use_container_width=True, key="logout")
        st.stop()
    nombres = {c["consorcio_id"]: c["nombre"] for c in consorcios}
    consorcio_id = st.selectbox("Consorcio", list(nombres), format_func=nombres.get)
    st.button("🔄 Actualizar", use_container_width=True)
    st.button("Cerrar sesión", on_click=cerrar_sesion, use_container_width=True, key="logout")


# ---------------------------------------------------------------- detalle de un caso

def mostrar_hipotesis(det: servicio.DetalleCaso) -> None:
    fallas = {f["cita"]: f["motivo"] for f in (det.verificacion or {}).get("fallas", [])}
    for h in det.dictamen.hipotesis:
        with st.container(border=True):
            quien = "la unidad" if h.responsable == "unidad" else "el consorcio"
            st.markdown(f"**Hipótesis {h.id}** · responsable: **{quien}**")
            st.write(h.descripcion)
            for ref in h.citas:
                fuente = det.fuentes.get(ref, "")
                marca = f"✗ {ref} · {fallas[ref]}" if ref in fallas else f"✓ {ref} · {fuente.split('. ')[0][:70]}"
                with st.expander(marca, expanded=False):
                    st.caption("Texto de la fuente")
                    st.write(fuente)
            c1, c2 = st.columns(2)
            c1.markdown("**A favor**\n" + ("\n".join(f"- {x}" for x in h.a_favor) or "\n_—_"))
            c2.markdown("**En contra**\n" + ("\n".join(f"- {x}" for x in h.en_contra) or "\n_—_"))
            st.markdown(f"**Lo confirmaría:** {h.confirmaria}")


def mostrar_confirmacion(det: servicio.DetalleCaso) -> None:
    caso_id, decision = st.session_state.pendiente
    prev = servicio.vista_previa(det, decision)
    with st.container(border=True):
        st.subheader("Confirmá antes de ejecutar")
        if prev.mensaje:
            st.markdown(f"Se le va a enviar a **{prev.destinatario}**"
                        + (" _(como respuesta de la administración)_" if prev.de_la_administracion else "") + ":")
            st.markdown(f'<div class="mensaje">{prev.mensaje}</div>', unsafe_allow_html=True)
            if not prev.canal_vinculado:
                st.warning("Este vecino no tiene Telegram vinculado: el mensaje queda en cola hasta que escriba al bot.")
        else:
            st.markdown("No se le envía ningún mensaje al vecino.")
        if prev.pedido:
            st.markdown(f"Se crea el pedido de **{prev.pedido}**.")
        if decision.accion is AccionAdmin.RECHAZAR:
            st.markdown(f"Motivo del rechazo (queda registrado): _{decision.motivo}_")
        c1, c2 = st.columns(2)
        if c1.button("✅ Confirmar", type="primary", use_container_width=True, key=f"conf-{caso_id}"):
            try:
                caso = servicio.decidir(sesion, caso_id, decision)
                st.session_state.pop("pendiente", None)
                st.session_state.aviso = f"Caso #{caso_id}: {ESTADOS[caso.estado]}"
            except ValueError:
                st.session_state.pop("pendiente", None)
                st.session_state.aviso = f"El caso #{caso_id} ya tenía una decisión: no se ejecutó nada de nuevo."
            st.rerun()
        if c2.button("Cancelar", use_container_width=True, key=f"canc-{caso_id}"):
            st.session_state.pop("pendiente", None)
            st.rerun()


def mostrar_acciones(det: servicio.DetalleCaso) -> None:
    caso_id = det.caso.caso_id
    if st.session_state.get("pendiente", (None,))[0] == caso_id:
        mostrar_confirmacion(det)
        return
    st.subheader("Decisión")
    eleccion = st.radio("Acción", list(ACCIONES), horizontal=True, key=f"accion-{caso_id}",
                        label_visibility="collapsed")
    accion = ACCIONES[eleccion]
    mensaje, motivo = None, None
    if accion is AccionAdmin.APROBAR:
        st.caption("Se envía el mensaje propuesto por la IA y se crea el pedido de la recomendación.")
    elif accion is AccionAdmin.MODIFICAR:
        mensaje = st.text_area("Mensaje al vecino", value=det.dictamen.mensaje_vecino, key=f"msg-{caso_id}",
                               height=140)
    else:
        motivo = st.text_area("Motivo del rechazo (obligatorio)", key=f"motivo-{caso_id}")
        mensaje = st.text_area("Tu respuesta al vecino (opcional, sale como de la administración)",
                               key=f"rech-{caso_id}")
    falta_motivo = accion is AccionAdmin.RECHAZAR and not (motivo or "").strip()
    if falta_motivo:
        st.caption("Cargá el motivo para poder seguir.")
    if st.button("Revisar y confirmar →", type="primary", disabled=falta_motivo, key=f"rev-{caso_id}"):
        try:
            st.session_state.pendiente = (caso_id, servicio.armar_decision(accion, sesion, mensaje, motivo))
            st.rerun()
        except ValidationError as e:
            st.error(e.errors()[0]["msg"].removeprefix("Value error, "))


def mostrar_caso(caso_id: int) -> None:
    try:
        det = servicio.detalle_caso(sesion, caso_id)
    except servicio.NoEncontrado:
        st.warning("Ese caso no existe.")
        return
    caso, r = det.caso, det.caso.reclamo
    st.header(f"Caso #{caso.caso_id} · {det.vecino['unidad']}")
    st.markdown(f"{ESTADOS[caso.estado]} · {det.vecino['nombre']} · {det.vecino['telefono']}")

    with st.container(border=True):
        st.markdown("**Reclamo del vecino**")
        st.write(r.descripcion)
        st.markdown(f"**Ambiente:** {r.ambiente or '—'} · **Desde:** {r.desde_cuando or '—'} · "
                    f"**¿Gotea?:** {({True: 'sí', False: 'no', None: '—'})[r.gotea]} · **Fotos:** {len(r.fotos)}")
        for foto in r.fotos:
            if foto.ruta_local and Path(foto.ruta_local).exists():
                st.image(foto.ruta_local, width=280)

    if det.dictamen is None:
        st.info("Todavía no hay dictamen para este caso.")
        return

    d = det.dictamen
    with st.container(border=True):
        ia()
        st.markdown(f"**Dictamen** (versión {det.version})")
        if d.hechos:
            st.markdown("**Hechos**\n" + "\n".join(f"- {x}" for x in d.hechos))
        if d.afirmaciones_sin_evidencia:
            st.warning("**Afirmaciones sin evidencia** (no se usan para decidir)\n"
                       + "\n".join(f"- {x}" for x in d.afirmaciones_sin_evidencia))
        if d.hipotesis:
            mostrar_hipotesis(det)
        else:
            st.info("Sin hipótesis con fuente: la IA no asigna responsabilidad.")
        rec = d.recomendacion
        titulo = "🔍 Inspección" if rec.tipo == "inspeccion" else f"✅ Asignar según la hipótesis {rec.hipotesis}"
        st.markdown(f"**Recomendación:** {titulo}  \n{rec.accion}")
        st.markdown("**Mensaje propuesto al vecino**")
        st.markdown(f'<div class="mensaje">{d.mensaje_vecino}</div>', unsafe_allow_html=True)
        v = det.verificacion
        if v is None or v.get("ok"):
            st.success("Verificador de citas: todas las citas existen y están vigentes.")
        else:
            st.error("Verificador de citas: " + "; ".join(f"{f['cita']} ({f['motivo']})" for f in v["fallas"]))

    if det.esperando_decision and caso.estado is EstadoCaso.PENDIENTE_APROBACION:
        mostrar_acciones(det)
    else:
        for dec in det.decisiones:
            st.markdown(f"**Decisión:** {dec['accion']} por {dec['admin_id']} ({dec['creado']})"
                        + (f" · motivo: _{dec['motivo']}_" if dec["motivo"] else ""))
            if dec["mensaje_final"]:
                st.markdown(f'<div class="mensaje">{dec["mensaje_final"]}</div>', unsafe_allow_html=True)
        for p in det.pedidos:
            st.markdown(f"**Pedido de {p['tipo']}:** {p['descripcion']}")
        if det.precedente:
            st.caption(f"Guardado como precedente {det.precedente['prec_id']} para casos futuros.")


def mostrar_derivacion(der_id: int) -> None:
    try:
        d = servicio.derivacion(sesion, der_id)
    except servicio.NoEncontrado:
        st.warning("Esa consulta no existe.")
        return
    v = d["vecino"]
    titulos = {"urgencia": "🚨 Urgencia", "sin_fuente": "❓ Consulta sin fuente",
               "hablar_con_admin": "🙋 Pide hablar con una persona", "no_entendido": "🙋 El bot no entendió"}
    st.header(titulos.get(d["tipo"], d["tipo"]))
    st.markdown(f"{v['nombre']} · {v['unidad']} · {v['telefono']} · {d['creado']}")
    st.markdown(f'<div class="mensaje">{d["texto"]}</div>', unsafe_allow_html=True)
    if d["tipo"] == "sin_fuente":
        st.caption("El bot no encontró una fuente que responda esto y no contestó.")
    if d["estado"] != "pendiente":
        st.info(f"Estado: {d['estado']}")
        return
    texto = st.text_area("Respuesta al vecino (sale por Telegram como respuesta de la administración)",
                         key=f"resp-{der_id}")
    c1, c2 = st.columns(2)
    if c1.button("Enviar respuesta", type="primary", disabled=not texto.strip(), key=f"env-{der_id}"):
        servicio.responder_derivacion(sesion, der_id, texto)
        st.session_state.aviso = "Respuesta encolada para el vecino."
        st.rerun()
    if c2.button("Marcar como resuelta sin responder", key=f"desc-{der_id}"):
        servicio.descartar_derivacion(sesion, der_id)
        st.rerun()


# ---------------------------------------------------------------- vistas

def vista_panel() -> None:
    if aviso := st.session_state.pop("aviso", None):
        st.toast(aviso)
    izq, der = st.columns([1, 2], gap="large")
    with izq:
        st.subheader("Bandeja")
        grupos = servicio.bandeja(sesion, consorcio_id)
        for clave, titulo in servicio.GRUPOS:
            items = grupos[clave]
            st.markdown(f"**{titulo}** ({len(items)})")
            if not items:
                st.caption("Nada pendiente.")
            for it in items:
                etiqueta = f"{it.titulo} — {it.detalle[:70]}"
                st.button(etiqueta, key=f"{it.tipo}-{it.id}", use_container_width=True,
                          type="primary" if clave == "urgencias" else "secondary",
                          on_click=seleccionar, args=(it.tipo, it.id))
        with st.expander("Historial de casos"):
            for c in servicio.historial(sesion, consorcio_id):
                st.button(f"#{c['caso_id']} · {ESTADOS[EstadoCaso(c['estado'])]}", key=f"hist-{c['caso_id']}",
                          use_container_width=True, on_click=seleccionar, args=("caso", c["caso_id"]))
    with der:
        sel = st.session_state.get("sel")
        if not sel:
            st.info("Elegí un elemento de la bandeja.")
        elif sel[0] == "caso":
            mostrar_caso(sel[1])
        else:
            mostrar_derivacion(sel[1])


def vista_simulador() -> None:
    from eliseo.grafo import runtime
    from eliseo.plataforma.db import get_conn
    from eliseo.schemas import Adjunto, MensajeEntrante

    st.subheader("Simulador de vecino")
    st.caption("Para probar sin Telegram: usa el mismo runtime que el bot. Los mensajes que la administración "
               "aprueba en el panel aparecen acá.")
    conn = get_conn()
    vecinos = servicio.vecinos(sesion, consorcio_id)
    if not vecinos:
        st.info("Este edificio todavía no tiene vecinos cargados.")
        return
    tel = st.selectbox("Vecino", [v["telefono"] for v in vecinos],
                       format_func=lambda t: next(f"{v['unidad']} · {v['nombre']}" for v in vecinos if v["telefono"] == t),
                       index=next((i for i, v in enumerate(vecinos) if v["unidad"] == "4°B"), 0))
    usuario = f"sim-{tel}"
    historial = st.session_state.setdefault("chats", {}).setdefault(tel, [])

    def enviar(texto: str = "", **kw) -> None:
        msg = MensajeEntrante(chat_id=usuario, usuario_canal_id=usuario, texto=texto, **kw)
        for s in runtime.procesar_mensaje(msg):
            historial.append(("assistant", s.texto, s.botones))

    if not historial:
        enviar(telefono_compartido=tel)  # vincula el "Telegram" simulado con el teléfono del vecino

    for rol, texto, _ in historial:
        with st.chat_message(rol):
            st.markdown(texto.replace("\n", "  \n"))
    for _, _destino, m in _outbox(conn, tel):
        with st.chat_message("assistant", avatar="🏢"):
            st.markdown(("**De la administración:** " if m.de_la_administracion else "") + m.texto.replace("\n", "  \n"))

    botones = historial[-1][2] if historial else []
    if botones:
        cols = st.columns(len(botones))
        for col, b in zip(cols, botones):
            if col.button(b, key=f"btn-{tel}-{len(historial)}-{b}"):
                historial.append(("user", b, []))
                enviar(b)
                st.rerun()
    c1, c2 = st.columns([4, 1])
    if c2.button("📷 Mandar foto", use_container_width=True):
        historial.append(("user", "📷 (foto)", []))
        enviar(adjuntos=[Adjunto(tipo="foto", file_id=f"sim-{len(historial)}")])
        st.rerun()
    if texto := st.chat_input("Escribí como el vecino…"):
        historial.append(("user", texto, []))
        enviar(texto)
        st.rerun()


def _outbox(conn, telefono: str):
    filas = conn.execute("SELECT id, destino, mensaje_json FROM outbox WHERE destino = ? ORDER BY id",
                         (f"vecino:{telefono}",)).fetchall()
    from eliseo.schemas import MensajeSaliente
    return [(f["id"], f["destino"], MensajeSaliente.model_validate_json(f["mensaje_json"])) for f in filas]


if vista == "Simulador de vecino":
    vista_simulador()
else:
    vista_panel()
