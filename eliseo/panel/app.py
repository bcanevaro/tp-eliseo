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
from eliseo.panel import documentos, padron, servicio  # noqa: E402
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
    vista = st.radio("Vista", ["Panel de la administración", "Edificios", "Vecinos", "Documentos",
                               "Simulador de vecino"], label_visibility="collapsed")
    consorcios = servicio.consorcios(sesion)
    consorcio_id = None
    if consorcios:
        nombres = {c["consorcio_id"]: c["nombre"] for c in consorcios}
        consorcio_id = st.selectbox("Consorcio", list(nombres), format_func=nombres.get)
    else:
        st.info("Tu administración todavía no tiene edificios. Dalos de alta en **Edificios**.")
    st.button("🔄 Actualizar", use_container_width=True)
    chat_vinculado = bool(cuentas.chat_avisos(sesion.administracion_id))
    with st.expander("📣 Chat de avisos" + ("" if chat_vinculado else " · sin vincular"), expanded=not chat_vinculado):
        st.caption("Las urgencias de tus edificios llegan a este chat de Telegram." if chat_vinculado
                   else "Todavía no vinculaste un chat: las urgencias quedan solo en la bandeja.")
        if st.button("Vincular chat de avisos" if not chat_vinculado else "Cambiar de chat", key="codigo-avisos"):
            st.session_state.codigo_avisos = cuentas.generar_codigo_avisos(sesion)
        if codigo := st.session_state.get("codigo_avisos"):
            st.markdown(f"Desde el chat donde querés recibirlos, mandale al bot:\n\n`/admin {codigo}`")
            st.caption("El código sirve una sola vez y vence a los 15 minutos.")
    st.button("Cerrar sesión", on_click=cerrar_sesion, use_container_width=True, key="logout")

if consorcio_id is None and vista != "Edificios":
    st.subheader("Bienvenida")
    st.write("Para empezar, andá a **Edificios** en la barra lateral y cargá tu primer edificio.")
    st.stop()


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
        if grupos["urgencias"] and not chat_vinculado:
            st.warning("Hay urgencias y tu administración no tiene un chat de avisos vinculado: "
                       "vinculalo desde la barra lateral para recibirlas por Telegram.")
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


# ---------------------------------------------------------------- padrón (spec padron-consorcios)

def _tabla_unidades(filas: list[dict], key: str):
    """Editor de unidades: piso (0 = PB), depto y coeficiente. Devuelve la tabla editada."""
    import pandas as pd

    df = pd.DataFrame(filas or [{"piso": 1, "depto": "A", "coeficiente": "1.0000", "unidad_id": None}],
                      columns=["piso", "depto", "coeficiente", "unidad_id"])
    df["coeficiente"] = df["coeficiente"].astype(str)
    editada = st.data_editor(
        df, key=key, num_rows="dynamic", hide_index=True, use_container_width=True,
        column_config={"piso": st.column_config.NumberColumn("Piso (0 = PB)", min_value=0, step=1, required=True),
                       "depto": st.column_config.TextColumn("Depto", required=True),
                       "coeficiente": st.column_config.TextColumn("Coeficiente", required=True,
                                                                  help="Proporción de 0 a 1; todas suman 1"),
                       "unidad_id": None})
    return editada


def _a_unidades(df) -> list[padron.UnidadNueva]:
    import pandas as pd

    unidades = []
    for f in df.to_dict("records"):
        if pd.isna(f.get("piso")) and not f.get("depto"):
            continue  # fila vacía que agregó el editor
        uid = f.get("unidad_id")
        unidades.append(padron.UnidadNueva(piso=int(f["piso"]), depto=str(f["depto"] or ""),
                                           coeficiente=str(f["coeficiente"]),
                                           unidad_id=None if uid is None or pd.isna(uid) else str(uid)))
    return unidades


def _intentar(accion, exito: str) -> None:
    try:
        accion()
    except padron.DatoInvalido as e:
        st.error(str(e))
    except servicio.NoEncontrado:
        st.error("Eso ya no existe. Actualizá la página.")
    else:
        st.session_state.aviso = exito
        st.rerun()


def vista_edificios() -> None:
    if aviso := st.session_state.pop("aviso", None):
        st.toast(aviso)
    if consorcio_id:
        c = padron.consorcio(sesion, consorcio_id)
        st.subheader(c["nombre"])
        with st.form(f"datos-{consorcio_id}"):
            nombre = st.text_input("Nombre", value=c["nombre"])
            direccion = st.text_input("Dirección", value=c["direccion"])
            tel = st.text_input("Teléfono de emergencias", value=c["telefono_emergencias"])
            if st.form_submit_button("Guardar datos"):
                _intentar(lambda: padron.editar_consorcio(sesion, consorcio_id, nombre, direccion, tel),
                          "Datos del edificio guardados.")

        st.markdown("**Unidades**")
        actuales = padron.unidades(sesion, consorcio_id)
        st.caption("Una unidad con vecinos o casos no se puede quitar. Los coeficientes tienen que sumar 1.")
        editada = _tabla_unidades([{**u, "coeficiente": f"{u['coeficiente']:.4f}"} for u in actuales],
                                  key=f"unidades-{consorcio_id}")
        if st.button("Guardar unidades", key=f"guardar-unidades-{consorcio_id}"):
            _intentar(lambda: padron.guardar_unidades(sesion, consorcio_id, _a_unidades(editada)),
                      "Unidades guardadas.")

        with st.expander("Dar de baja este edificio"):
            st.warning("Sus vecinos dejan de poder usar el bot y sus documentos salen de las búsquedas. "
                       "El historial de casos se conserva.")
            if st.session_state.get("baja-consorcio") == consorcio_id:
                c1, c2 = st.columns(2)
                if c1.button("Sí, dar de baja", type="primary", key="baja-confirmar"):
                    st.session_state.pop("baja-consorcio", None)
                    _intentar(lambda: padron.baja_consorcio(sesion, consorcio_id), f"{c['nombre']} dado de baja.")
                if c2.button("Cancelar", key="baja-cancelar"):
                    st.session_state.pop("baja-consorcio", None)
                    st.rerun()
            elif st.button("Dar de baja", key="baja-pedir"):
                st.session_state["baja-consorcio"] = consorcio_id
                st.rerun()
        st.divider()

    st.subheader("Nuevo edificio")
    with st.form("nuevo-edificio"):
        nombre = st.text_input("Nombre", placeholder="Consorcio Corrientes 1200")
        direccion = st.text_input("Dirección", placeholder="Corrientes 1200, CABA")
        tel = st.text_input("Teléfono de emergencias", placeholder="911 · guardia de la administración")
        st.caption("Unidades: agregá una fila por unidad.")
        nuevas = _tabla_unidades([], key="unidades-nuevo")
        if st.form_submit_button("Crear edificio", type="primary"):
            _intentar(lambda: padron.alta_consorcio(sesion, nombre, direccion, tel, _a_unidades(nuevas)),
                      f"{nombre} creado.")


def vista_vecinos() -> None:
    if aviso := st.session_state.pop("aviso", None):
        st.toast(aviso)
    st.subheader("Vecinos")
    lista = servicio.vecinos(sesion, consorcio_id)
    if lista:
        st.dataframe([{"Unidad": v["unidad"], "Nombre": v["nombre"], "Teléfono": v["telefono"]} for v in lista],
                     hide_index=True, use_container_width=True)
    else:
        st.info("Este edificio todavía no tiene vecinos.")
    unidades = padron.unidades(sesion, consorcio_id)
    etiquetas = {u["unidad_id"]: u["unidad"] for u in unidades}

    with st.expander("Agregar vecino", expanded=not lista):
        with st.form("alta-vecino", clear_on_submit=True):
            nombre = st.text_input("Nombre y apellido")
            unidad_id = st.selectbox("Unidad", list(etiquetas), format_func=etiquetas.get)
            tel = st.text_input("Celular (el que usa en Telegram)", placeholder="11 5555-1234")
            if st.form_submit_button("Agregar", type="primary"):
                _intentar(lambda: padron.alta_vecino(sesion, unidad_id, nombre, tel), f"{nombre} agregado.")

    if not lista:
        return
    with st.expander("Editar o dar de baja"):
        por_tel = {v["telefono"]: v for v in lista}
        tel_actual = st.selectbox("Vecino", list(por_tel),
                                  format_func=lambda t: f"{por_tel[t]['unidad']} · {por_tel[t]['nombre']}")
        v = por_tel[tel_actual]
        with st.form(f"editar-{tel_actual}"):
            nombre = st.text_input("Nombre y apellido", value=v["nombre"])
            ids = list(etiquetas)
            unidad_id = st.selectbox("Unidad", ids, index=ids.index(v["unidad_id"]), format_func=etiquetas.get)
            tel = st.text_input("Celular", value=v["telefono"],
                                help="Si lo cambiás, tiene que volver a compartir su contacto en el bot.")
            if st.form_submit_button("Guardar cambios"):
                _intentar(lambda: padron.editar_vecino(sesion, tel_actual, nombre, unidad_id, tel), "Vecino actualizado.")
        if st.session_state.get("baja-vecino") == tel_actual:
            st.warning(f"¿Dar de baja a {v['nombre']} ({v['unidad']})? Deja de poder usar el bot desde su próximo mensaje.")
            c1, c2 = st.columns(2)
            if c1.button("Sí, dar de baja", type="primary", key="baja-vecino-confirmar"):
                st.session_state.pop("baja-vecino", None)
                _intentar(lambda: padron.baja_vecino(sesion, tel_actual), f"{v['nombre']} dado de baja.")
            if c2.button("Cancelar", key="baja-vecino-cancelar"):
                st.session_state.pop("baja-vecino", None)
                st.rerun()
        elif st.button("Dar de baja", key="baja-vecino-pedir"):
            st.session_state["baja-vecino"] = tel_actual
            st.rerun()


# ---------------------------------------------------------------- documentos (spec documentos-consorcio)

ESTADOS_DOC = {"activo": "vigente", "reemplazado": "reemplazado", "baja": "dado de baja"}


def vista_documentos() -> None:
    from eliseo import documentos as docs

    if aviso := st.session_state.pop("aviso", None):
        st.toast(aviso)
    st.subheader("Documentos")
    lista = documentos.listar(sesion, consorcio_id)
    activos = [d for d in lista if d["estado"] == "activo"]
    if not any(d["tipo"] == "Reglamento" for d in activos):
        st.warning("Este edificio no tiene reglamento: el bot no puede responder consultas de reglamento.")
    if any(not d["indexado"] for d in activos):
        c1, c2 = st.columns([3, 1])
        c1.info("Hay documentos pendientes de indexar: el bot los encuentra igual, pero la búsqueda es menos precisa.")
        if c2.button("Reintentar indexación", key="reindexar"):
            ok = documentos.reintentar_indexacion(sesion, consorcio_id)
            st.session_state.aviso = "Documentos indexados." if ok else "No se pudo indexar: probá más tarde."
            st.rerun()

    for d in lista:
        with st.container(border=True):
            c1, c2, c3 = st.columns([4, 1, 1])
            indexado = "✓ indexado" if d["indexado"] else "⏳ pendiente de indexar"
            c1.markdown(f"**{d['tipo']}** · {d['ref']} · {d['fecha']} · _{ESTADOS_DOC[d['estado']]}_"
                        + (f" · {indexado}" if d["estado"] == "activo" else ""))
            c1.caption(f"Subido por {d['subido_por'] or '—'} el {d['creado'][:16]}")
            nombre, contenido = documentos.original(sesion, d["doc_id"])
            c2.download_button("Original", contenido, file_name=nombre, key=f"desc-{d['doc_id']}")
            if d["estado"] == "activo" and d["tipo"] == "Acta":
                if st.session_state.get("baja-doc") == d["doc_id"]:
                    if c3.button("Confirmar baja", type="primary", key=f"baja-conf-{d['doc_id']}"):
                        st.session_state.pop("baja-doc", None)
                        documentos.dar_de_baja(sesion, consorcio_id, d["doc_id"])
                        st.session_state.aviso = f"{d['ref']} dado de baja."
                        st.rerun()
                elif c3.button("Dar de baja", key=f"baja-{d['doc_id']}"):
                    st.session_state["baja-doc"] = d["doc_id"]
                    st.rerun()

    st.divider()
    st.subheader("Subir un documento")
    tipo = st.radio("Tipo", ["Reglamento", "Acta"], horizontal=True, key="doc-tipo",
                    help="Un reglamento nuevo reemplaza al vigente.")
    st.download_button(f"Descargar plantilla de {tipo.lower()}", docs.PLANTILLA[tipo].encode("utf-8"),
                       file_name=f"plantilla-{tipo.lower()}.md", key=f"plantilla-{tipo}")
    # La key cambia después de confirmar o cancelar, así el uploader vuelve a quedar vacío.
    archivo = st.file_uploader("Archivo Markdown (.md)", key=f"subida-{tipo}-{st.session_state.get('subidas', 0)}")
    if archivo is None:
        return
    contenido = archivo.getvalue()
    rev = documentos.revisar(sesion, consorcio_id, tipo, contenido)
    if not rev.ok:
        st.error("No se puede guardar. Corregí esto y volvé a subirlo:\n\n" + "\n".join(f"- {e}" for e in rev.errores))
        return
    st.markdown(f"**Vista previa** · {rev.ref} · {rev.fecha} · {len(rev.secciones)} "
                + ("artículos" if tipo == "Reglamento" else "puntos"))
    st.dataframe([{"Id": s.ref, "Título": s.titulo, "Modifica": f"{s.modifica} ({s.efecto})" if s.modifica else "",
                   "Texto": s.texto[:120]} for s in rev.secciones], hide_index=True, use_container_width=True)
    if tipo == "Reglamento" and any(d["tipo"] == "Reglamento" for d in activos):
        st.warning("Este reglamento va a reemplazar al vigente.")
    c1, c2 = st.columns(2)
    if c1.button("Confirmar", type="primary", key="doc-confirmar"):
        try:
            documentos.confirmar(sesion, consorcio_id, tipo, contenido, archivo.name)
        except docs.DocumentoInvalido as e:
            st.error(str(e))
            return
        st.session_state.subidas = st.session_state.get("subidas", 0) + 1
        st.session_state.aviso = f"{rev.ref} guardado: el bot ya lo usa."
        st.rerun()
    if c2.button("Cancelar", key="doc-cancelar"):
        st.session_state.subidas = st.session_state.get("subidas", 0) + 1
        st.rerun()


if vista == "Simulador de vecino":
    vista_simulador()
elif vista == "Documentos":
    vista_documentos()
elif vista == "Edificios":
    vista_edificios()
elif vista == "Vecinos":
    vista_vecinos()
else:
    vista_panel()
