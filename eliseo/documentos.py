"""Reglamento y actas de cada consorcio guardados en la base (spec documentos-consorcio, design D6-D8).

- `revisar`: valida un documento en el formato del corpus y lo parte como lo va a usar el sistema,
  con cada error y su línea. No guarda nada.
- `confirmar`: vuelve a validar, guarda (el reglamento nuevo reemplaza al anterior), guarda el
  original e indexa en Pinecone. Si la indexación falla, el documento queda guardado y marcado
  como pendiente; el Documental lo encuentra igual por BM25, que se arma desde la base.
- `dar_de_baja`, `indexar`, `texto_historico` (para las citas de casos viejos).

Sin sesión: lo usan el panel (`eliseo.panel.documentos`, que agrega el control de la
administración), la siembra de la demo y `scripts/ingest.py`.
"""
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from eliseo import archivos
from eliseo.corpus import Corpus, Documento, _parse_meta, _secciones, armar_corpus, cargar_corpus, documentos_de, invalidar

log = logging.getLogger(__name__)

TIPOS = ("Reglamento", "Acta")
_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ENCABEZADO = re.compile(r"^## (.+?) · (.+)$")
_ID = {"Reglamento": re.compile(r"^REG-\d+$"), "Acta": re.compile(r"^ACTA-(\d{4}-\d{2}-\d{2})#\d+$")}
EFECTOS = ("complementa", "reemplaza")

PLANTILLA = {
    "Reglamento": """# Reglamento de Copropiedad — Consorcio <nombre>

<!-- fecha: 1998-06-15 -->

## REG-1 · Objeto
Texto del artículo 1.

## REG-2 · Partes comunes
Texto del artículo 2.
""",
    "Acta": """# Acta de Asamblea Ordinaria — 18/04/2023

<!-- fecha: 2023-04-18 -->

## ACTA-2023-04-18#1 · Designación de firmantes
Texto del punto 1.

## ACTA-2023-04-18#2 · Horario de obras
<!-- modifica: REG-14 · efecto: reemplaza -->
Texto del punto 2. Si modifica un artículo, indicalo en la primera línea como arriba
(efecto: complementa o reemplaza).
""",
}


@dataclass
class Error:
    linea: int | None
    mensaje: str

    def __str__(self) -> str:
        return f"Línea {self.linea}: {self.mensaje}" if self.linea else self.mensaje


@dataclass
class Revision:
    tipo: str
    ref: str | None
    fecha: str | None
    secciones: list[Documento] = field(default_factory=list)
    errores: list[Error] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errores


def _ahora() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")


def _activos(conn, consorcio_id: str) -> list[dict]:
    return [dict(f) for f in conn.execute(
        "SELECT doc_id, tipo, ref, fecha, contenido_md FROM documentos WHERE consorcio_id = ? AND estado = 'activo'",
        (consorcio_id,)).fetchall()]


def revisar(conn, consorcio_id: str, tipo: str, contenido: str) -> Revision:
    """Valida y parte el documento contra lo que el consorcio tiene activo hoy."""
    if tipo not in TIPOS:
        return Revision(tipo, None, None, errores=[Error(None, f"Tipo de documento desconocido: {tipo}")])
    contenido = (contenido or "").replace("\r\n", "\n")
    errores: list[Error] = []
    meta = _parse_meta(contenido)
    fecha = meta.get("fecha")
    if not fecha or not _FECHA.match(fecha):
        errores.append(Error(_linea_de(contenido, "<!--") or 1,
                             "Falta la fecha del documento: agregá `<!-- fecha: AAAA-MM-DD -->` debajo del título."))
        fecha = None
    if meta.get("consorcio_id") and meta["consorcio_id"] != consorcio_id:
        errores.append(Error(_linea_de(contenido, "consorcio_id"),
                             f"El documento dice ser del consorcio {meta['consorcio_id']}, no de este."))

    lineas_de: dict[str, int] = {}
    for n, linea in enumerate(contenido.split("\n"), 1):
        if not linea.startswith("## "):
            continue
        m = _ENCABEZADO.match(linea.strip())
        if not m:
            errores.append(Error(n, "El encabezado tiene que ser `## <ID> · <título>` (con el punto medio ·)."))
            continue
        ref = m.group(1)
        id_ok = _ID[tipo].match(ref)
        if not id_ok:
            esperado = "REG-<número>" if tipo == "Reglamento" else "ACTA-<AAAA-MM-DD>#<punto>"
            errores.append(Error(n, f"«{ref}» no es un id válido: tiene que ser {esperado}."))
        elif tipo == "Acta" and fecha and id_ok.group(1) != fecha:
            errores.append(Error(n, f"«{ref}» no tiene la fecha del acta ({fecha})."))
        if ref in lineas_de:
            errores.append(Error(n, f"El id {ref} está repetido (ya aparece en la línea {lineas_de[ref]})."))
        else:
            lineas_de[ref] = n

    secciones = documentos_de(tipo, contenido, consorcio_id)  # type: ignore[arg-type]
    if not secciones and not any(e.mensaje.startswith("El encabezado") for e in errores):
        errores.append(Error(None, "No encontré ningún " + ("artículo" if tipo == "Reglamento" else "punto")
                             + " con el formato `## <ID> · <título>`. Descargá la plantilla para ver el formato."))

    activos = _activos(conn, consorcio_id)
    reglamento_activo = next((d for d in activos if d["tipo"] == "Reglamento"), None)
    articulos = {d.ref for d in documentos_de("Reglamento", reglamento_activo["contenido_md"], consorcio_id)} \
        if reglamento_activo else set()
    for (ref, _, texto, m) in _secciones(contenido):
        if not texto:
            errores.append(Error(lineas_de.get(ref), f"{ref} no tiene texto."))
        if tipo == "Acta" and m.get("modifica"):
            # El comentario `<!-- modifica: … -->` va en la línea siguiente al encabezado.
            linea = lineas_de[ref] + 1 if ref in lineas_de else None
            if m["modifica"] not in articulos:
                errores.append(Error(linea, f"{ref} dice modificar el {m['modifica']}, que no existe "
                                            "en el reglamento vigente."))
            if m.get("efecto") not in EFECTOS:
                errores.append(Error(linea, f"{ref}: el efecto tiene que ser «complementa» o «reemplaza»."))

    ref_doc = "REGLAMENTO" if tipo == "Reglamento" else (f"ACTA-{fecha}" if fecha else None)
    if tipo == "Acta" and ref_doc and any(d["ref"] == ref_doc for d in activos):
        errores.append(Error(None, f"Ya hay un acta del {fecha}. Si querés cambiarla, dala de baja primero."))
    if tipo == "Reglamento":
        nuevos = {d.ref for d in secciones}
        for acta in (d for d in activos if d["tipo"] == "Acta"):
            for punto in documentos_de("Acta", acta["contenido_md"], consorcio_id):
                if punto.modifica and punto.modifica not in nuevos:
                    errores.append(Error(None, f"{punto.ref} modifica el {punto.modifica}, que no está en el "
                                               "reglamento nuevo. Dá de baja esa acta o agregá el artículo."))
    return Revision(tipo, ref_doc, fecha, secciones, errores)


def _linea_de(contenido: str, texto: str) -> int | None:
    for n, linea in enumerate(contenido.split("\n"), 1):
        if texto in linea:
            return n
    return None


class DocumentoInvalido(ValueError):
    def __init__(self, revision: Revision):
        self.revision = revision
        super().__init__("; ".join(str(e) for e in revision.errores))


def confirmar(conn, consorcio_id: str, tipo: str, contenido: str, *, nombre_archivo: str | None = None,
              original: bytes | None = None, subido_por: str | None = None, indexar_ahora: bool = True,
              index=None) -> int:
    """Guarda el documento (validándolo de nuevo) y lo deja disponible para los agentes. Devuelve su id."""
    contenido = (contenido or "").replace("\r\n", "\n")
    revision = revisar(conn, consorcio_id, tipo, contenido)
    if not revision.ok:
        raise DocumentoInvalido(revision)
    ahora = _ahora()
    if tipo == "Reglamento":
        conn.execute("UPDATE documentos SET estado = 'reemplazado', actualizado = ? "
                     "WHERE consorcio_id = ? AND tipo = 'Reglamento' AND estado = 'activo'", (ahora, consorcio_id))
    doc_id = conn.execute(
        """INSERT INTO documentos (consorcio_id, tipo, ref, fecha, contenido_md, nombre_archivo, subido_por,
                                   creado, actualizado)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING doc_id""",
        (consorcio_id, tipo, revision.ref, revision.fecha, contenido, nombre_archivo, subido_por, ahora, ahora),
    ).fetchone()["doc_id"]
    if original is not None:
        try:
            ruta = archivos.guardar(consorcio_id, doc_id, nombre_archivo or f"{revision.ref}.md", original)
            conn.execute("UPDATE documentos SET archivo_path = ? WHERE doc_id = ?", (ruta, doc_id))
        except Exception:  # el documento vale igual; sin original solo se descarga el Markdown validado
            log.exception("no se pudo guardar el original del documento %s", doc_id)
    invalidar(consorcio_id)
    if indexar_ahora:
        indexar(conn, consorcio_id, index)
    return doc_id


def dar_de_baja(conn, consorcio_id: str, doc_id: int, index=None) -> None:
    """Saca un acta de las búsquedas y de las citas nuevas. El reglamento no se da de baja: se reemplaza."""
    fila = conn.execute("SELECT tipo FROM documentos WHERE doc_id = ? AND consorcio_id = ? AND estado = 'activo'",
                        (doc_id, consorcio_id)).fetchone()
    if fila is None:
        raise KeyError(f"No existe el documento {doc_id}")
    if fila["tipo"] == "Reglamento":
        raise ValueError("El reglamento no se da de baja: subí uno nuevo para reemplazarlo.")
    conn.execute("UPDATE documentos SET estado = 'baja', actualizado = ? WHERE doc_id = ?", (_ahora(), doc_id))
    invalidar(consorcio_id)
    indexar(conn, consorcio_id, index)


def indexar(conn, consorcio_id: str, index=None) -> bool:
    """Deja Pinecone igual a los documentos activos del consorcio (agrega lo nuevo y borra lo que ya
    no está). Marca `indexado` según el resultado. Sin Pinecone configurado devuelve False."""
    from eliseo.agentes.documental.ingesta import records, sincronizar
    from eliseo.vectores import NS_DOCUMENTOS, get_index, hay_pinecone

    ok = False
    try:
        if index is None and hay_pinecone():
            index = get_index(crear=True)
        if index is not None:
            sincronizar(index, NS_DOCUMENTOS, consorcio_id, records(cargar_corpus(consorcio_id)))
            ok = True
    except Exception:
        log.exception("no se pudo indexar el consorcio %s en Pinecone", consorcio_id)
    conn.execute("UPDATE documentos SET indexado = ? WHERE consorcio_id = ? AND estado = 'activo'",
                 (1 if ok else 0, consorcio_id))
    return ok


def texto_historico(conn, consorcio_id: str, ref: str) -> Documento | None:
    """Un artículo o punto que ya no está vigente (reemplazado o dado de baja), para seguir mostrando
    lo que se citó en casos viejos. El más reciente si hubo varios."""
    filas = conn.execute("SELECT tipo, contenido_md FROM documentos WHERE consorcio_id = ? AND estado != 'activo' "
                         "ORDER BY actualizado DESC, doc_id DESC", (consorcio_id,)).fetchall()
    for f in filas:
        doc = Corpus(documentos_de(f["tipo"], f["contenido_md"], consorcio_id)).get(ref)
        if doc:
            return doc
    return None


def cargar_desde_directorio(conn, consorcio_id: str, directorio) -> int:
    """Siembra de la demo: carga el reglamento y las actas de una carpeta como si se subieran por el
    panel, solo si el consorcio todavía no tiene documentos en la base. Devuelve cuántos cargó."""
    from eliseo.corpus import fuentes_de_directorio

    if conn.execute("SELECT 1 FROM documentos WHERE consorcio_id = ?", (consorcio_id,)).fetchone():
        return 0
    fuentes = fuentes_de_directorio(directorio)
    nombres = ["reglamento.md"] + [a.name for a in sorted((directorio / "actas").glob("*.md"))]
    for (tipo, contenido), nombre in zip(fuentes, nombres):
        confirmar(conn, consorcio_id, tipo, contenido, nombre_archivo=nombre, subido_por="demo", indexar_ahora=False)
    return len(fuentes)


__all__ = ["Error", "Revision", "DocumentoInvalido", "PLANTILLA", "revisar", "confirmar", "dar_de_baja",
           "indexar", "texto_historico", "cargar_desde_directorio", "armar_corpus"]
