"""Documentos de los consorcios desde el panel (spec documentos-consorcio).

Como `servicio.py`: sin Streamlit, con la `Sesion` primero, y todo limitado a los consorcios de
la administración de la sesión. La validación, el guardado y la indexación están en
`eliseo.documentos`.
"""
from eliseo import archivos
from eliseo import documentos as docs
from eliseo.cuentas import Sesion
from eliseo.panel.servicio import NoEncontrado, _consorcio_de, _conn

FORMATO = ("El documento tiene que ser un archivo de texto en Markdown (.md) con el formato del corpus: "
           "la fecha en `<!-- fecha: AAAA-MM-DD -->` y una sección `## <ID> · <título>` por artículo "
           "(`REG-<número>`) o por punto del acta (`ACTA-<fecha>#<punto>`). Descargá la plantilla para ver un ejemplo.")


def _texto(contenido: bytes) -> str:
    if contenido[:5] == b"%PDF-":
        raise docs.DocumentoInvalido(docs.Revision("?", None, None, errores=[docs.Error(None, FORMATO)]))
    try:
        return contenido.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise docs.DocumentoInvalido(docs.Revision("?", None, None, errores=[docs.Error(None, FORMATO)])) from None


def listar(sesion: Sesion, consorcio_id: str, conn=None) -> list[dict]:
    """Los documentos del consorcio, activos primero, con su estado de indexación."""
    conn = _conn(conn)
    _consorcio_de(conn, sesion, consorcio_id)
    return [dict(f) for f in conn.execute(
        """SELECT doc_id, tipo, ref, fecha, estado, indexado, nombre_archivo, subido_por, creado
           FROM documentos WHERE consorcio_id = ?
           ORDER BY CASE estado WHEN 'activo' THEN 0 ELSE 1 END, tipo DESC, fecha""", (consorcio_id,)).fetchall()]


def revisar(sesion: Sesion, consorcio_id: str, tipo: str, contenido: bytes, conn=None) -> docs.Revision:
    """La vista previa: el documento partido como lo va a usar el sistema, o los errores. No guarda nada."""
    conn = _conn(conn)
    _consorcio_de(conn, sesion, consorcio_id)
    try:
        texto = _texto(contenido)
    except docs.DocumentoInvalido as e:
        return e.revision
    return docs.revisar(conn, consorcio_id, tipo, texto)


def confirmar(sesion: Sesion, consorcio_id: str, tipo: str, contenido: bytes, nombre_archivo: str,
              conn=None, index=None) -> int:
    conn = _conn(conn)
    _consorcio_de(conn, sesion, consorcio_id)
    return docs.confirmar(conn, consorcio_id, tipo, _texto(contenido), nombre_archivo=nombre_archivo,
                          original=contenido, subido_por=sesion.email, index=index)


def dar_de_baja(sesion: Sesion, consorcio_id: str, doc_id: int, conn=None, index=None) -> None:
    conn = _conn(conn)
    _consorcio_de(conn, sesion, consorcio_id)
    try:
        docs.dar_de_baja(conn, consorcio_id, doc_id, index)
    except KeyError:
        raise NoEncontrado(f"No existe el documento {doc_id}") from None


def reintentar_indexacion(sesion: Sesion, consorcio_id: str, conn=None, index=None) -> bool:
    conn = _conn(conn)
    _consorcio_de(conn, sesion, consorcio_id)
    return docs.indexar(conn, consorcio_id, index)


def original(sesion: Sesion, doc_id: int, conn=None) -> tuple[str, bytes]:
    """(nombre, contenido) del archivo que se subió; si no se guardó, el Markdown validado."""
    conn = _conn(conn)
    f = conn.execute("SELECT consorcio_id, ref, nombre_archivo, archivo_path, contenido_md FROM documentos "
                     "WHERE doc_id = ?", (doc_id,)).fetchone()
    try:
        _consorcio_de(conn, sesion, f["consorcio_id"] if f else None)
    except NoEncontrado:
        raise NoEncontrado(f"No existe el documento {doc_id}") from None
    nombre = f["nombre_archivo"] or f"{f['ref']}.md"
    if f["archivo_path"]:
        try:
            return nombre, archivos.leer(f["archivo_path"])
        except Exception:  # Storage caído: el Markdown validado es el mismo contenido
            pass
    return nombre, f["contenido_md"].encode("utf-8")
