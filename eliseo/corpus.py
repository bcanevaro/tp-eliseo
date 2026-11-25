"""Lectura del corpus documental (reglamento y actas) de un consorcio.

Formato de los archivos (ver data/consorcios/*/):
- Una línea `<!-- clave: valor · clave: valor -->` después del título con la metadata del documento.
- Una sección `## <ID> · <título>` por artículo o punto de acta, con un comentario opcional
  `<!-- modifica: REG-<n> · efecto: complementa|reemplaza -->` en la primera línea.

Lo usan la ingesta (agente-documental), el verificador de citas y los stubs.
"""
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from eliseo.config import CONSORCIOS_DIR

_META = re.compile(r"<!--\s*(.*?)\s*-->")
_SECCION = re.compile(r"^## (\S+) · (.+)$", re.MULTILINE)


@dataclass
class Documento:
    ref: str
    tipo: Literal["Reglamento", "Acta"]
    consorcio_id: str
    titulo: str
    texto: str
    fecha: str
    modifica: str | None = None
    efecto: Literal["complementa", "reemplaza"] | None = None
    modificado_por: list[str] = field(default_factory=list)
    reemplazado_por: str | None = None

    @property
    def vigente(self) -> bool:
        return self.reemplazado_por is None


def _parse_meta(texto: str) -> dict[str, str]:
    m = _META.search(texto)
    if not m:
        return {}
    pares = (p.split(":", 1) for p in m.group(1).split("·"))
    return {k.strip(): v.strip() for k, v in pares}


def _secciones(contenido: str):
    matches = list(_SECCION.finditer(contenido))
    for i, m in enumerate(matches):
        fin = matches[i + 1].start() if i + 1 < len(matches) else len(contenido)
        cuerpo = contenido[m.end():fin].strip()
        meta = {}
        if cuerpo.startswith("<!--"):
            meta = _parse_meta(cuerpo)
            cuerpo = _META.sub("", cuerpo, count=1).strip()
        yield m.group(1), m.group(2).strip(), cuerpo, meta


class Corpus:
    """Todos los documentos de un consorcio, indexados por id canónico."""

    def __init__(self, documentos: list[Documento]):
        self.docs: dict[str, Documento] = {d.ref: d for d in documentos}

    def get(self, ref: str) -> Documento | None:
        """Un artículo, un punto de acta o un acta completa (ACTA-<fecha> sin punto)."""
        if ref in self.docs:
            return self.docs[ref]
        puntos = [d for r, d in self.docs.items() if r.startswith(ref + "#")]
        if not puntos:
            return None
        base = puntos[0]
        return Documento(ref=ref, tipo="Acta", consorcio_id=base.consorcio_id, titulo=f"Acta {base.fecha}",
                         texto="\n\n".join(p.texto for p in puntos), fecha=base.fecha)

    def articulos(self) -> list[Documento]:
        return [d for d in self.docs.values() if d.tipo == "Reglamento"]

    def actas(self) -> list[Documento]:
        return [d for d in self.docs.values() if d.tipo == "Acta"]

    def __iter__(self):
        return iter(self.docs.values())

    def __len__(self) -> int:
        return len(self.docs)


def directorio_consorcio(consorcio_id: str, raiz: Path = CONSORCIOS_DIR) -> Path:
    for plataforma in raiz.glob("*/plataforma.json"):
        if json.loads(plataforma.read_text(encoding="utf-8"))["consorcio"]["consorcio_id"] == consorcio_id:
            return plataforma.parent
    raise KeyError(f"No hay datos para el consorcio {consorcio_id}")


def documentos_de(tipo: Literal["Reglamento", "Acta"], contenido: str, consorcio_id: str) -> list[Documento]:
    """Los artículos o puntos de acta de un documento en el formato del corpus. El consorcio lo fija
    quien llama (la sesión del panel o la carpeta de la demo), no el comentario del archivo."""
    meta = _parse_meta(contenido)
    docs = []
    for ref, titulo, texto, m in _secciones(contenido):
        if tipo == "Reglamento":
            docs.append(Documento(ref, "Reglamento", consorcio_id, titulo, texto, meta.get("fecha", "")))
        else:
            docs.append(Documento(ref, "Acta", consorcio_id, titulo, texto, meta.get("fecha", ""),
                                  modifica=m.get("modifica"), efecto=m.get("efecto")))  # type: ignore[arg-type]
    return docs


def armar_corpus(fuentes: list[tuple[str, str]], consorcio_id: str) -> Corpus:
    """`fuentes`: (tipo, contenido Markdown) del reglamento y las actas activos. Resuelve la vigencia."""
    docs: list[Documento] = []
    for tipo, contenido in sorted(fuentes, key=lambda f: f[0] != "Reglamento"):
        docs += documentos_de(tipo, contenido, consorcio_id)  # type: ignore[arg-type]
    corpus = Corpus(docs)
    for acta in corpus.actas():
        articulo = corpus.docs.get(acta.modifica) if acta.modifica else None
        if articulo:
            articulo.modificado_por.append(acta.ref)
            if acta.efecto == "reemplaza":
                articulo.reemplazado_por = acta.ref
    return corpus


def fuentes_de_directorio(directorio: Path) -> list[tuple[str, str]]:
    fuentes = [("Reglamento", (directorio / "reglamento.md").read_text(encoding="utf-8"))]
    fuentes += [("Acta", a.read_text(encoding="utf-8")) for a in sorted((directorio / "actas").glob("*.md"))]
    return fuentes


def leer_corpus(directorio: Path) -> Corpus:
    consorcio_id = _parse_meta((directorio / "reglamento.md").read_text(encoding="utf-8"))["consorcio_id"]
    return armar_corpus(fuentes_de_directorio(directorio), consorcio_id)


# ---------------------------------------------------------------- corpus desde la base

# El corpus sale de la tabla `documentos` (spec documentos-consorcio, design D6). Se cachea por
# (base, consorcio) y se revalida contra la versión de la base cada TTL_VERSION segundos: un
# documento confirmado en el panel vale en el próximo mensaje del bot, aunque corran en procesos
# distintos. `invalidar` lo fuerza en el mismo proceso.
TTL_VERSION = 3.0
_cache: dict[tuple[str, str], tuple[float, tuple, Corpus]] = {}


def _version(conn, consorcio_id: str) -> tuple:
    f = conn.execute(
        """SELECT COUNT(*) AS total, SUM(CASE WHEN estado = 'activo' THEN 1 ELSE 0 END) AS activos,
                  MAX(actualizado) AS ultimo, MAX(doc_id) AS ultimo_id
           FROM documentos WHERE consorcio_id = ?""", (consorcio_id,)).fetchone()
    return (f["total"], f["activos"] or 0, f["ultimo"], f["ultimo_id"])


def _leer_de_la_base(conn, consorcio_id: str, version: tuple) -> Corpus:
    if version[0] == 0:
        # Nunca se cargaron documentos en la base: los archivos de la demo, si los hay.
        try:
            return leer_corpus(directorio_consorcio(consorcio_id))
        except KeyError:
            return Corpus([])
    filas = conn.execute("SELECT tipo, contenido_md FROM documentos WHERE consorcio_id = ? AND estado = 'activo' "
                         "ORDER BY fecha, doc_id", (consorcio_id,)).fetchall()
    return armar_corpus([(f["tipo"], f["contenido_md"]) for f in filas], consorcio_id)


def cargar_corpus(consorcio_id: str) -> Corpus:
    from eliseo.config import db_url
    from eliseo.plataforma.db import get_conn

    clave, ahora = (db_url(), consorcio_id), time.monotonic()
    previo = _cache.get(clave)
    if previo and ahora - previo[0] < TTL_VERSION:
        return previo[2]
    conn = get_conn()
    version = _version(conn, consorcio_id)
    corpus = previo[2] if previo and previo[1] == version else _leer_de_la_base(conn, consorcio_id, version)
    _cache[clave] = (ahora, version, corpus)
    return corpus


def invalidar(consorcio_id: str | None = None) -> None:
    for clave in [k for k in _cache if consorcio_id is None or k[1] == consorcio_id]:
        del _cache[clave]
