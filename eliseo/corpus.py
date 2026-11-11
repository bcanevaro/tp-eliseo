"""Lectura del corpus documental (reglamento y actas) de un consorcio.

Formato de los archivos (ver data/consorcios/*/):
- Una línea `<!-- clave: valor · clave: valor -->` después del título con la metadata del documento.
- Una sección `## <ID> · <título>` por artículo o punto de acta, con un comentario opcional
  `<!-- modifica: REG-<n> · efecto: complementa|reemplaza -->` en la primera línea.

Lo usan la ingesta (agente-documental), el verificador de citas y los stubs.
"""
import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
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
        if json.loads(plataforma.read_text())["consorcio"]["consorcio_id"] == consorcio_id:
            return plataforma.parent
    raise KeyError(f"No hay datos para el consorcio {consorcio_id}")


def leer_corpus(directorio: Path) -> Corpus:
    docs: list[Documento] = []
    reglamento = (directorio / "reglamento.md").read_text()
    meta = _parse_meta(reglamento)
    for ref, titulo, texto, _ in _secciones(reglamento):
        docs.append(Documento(ref, "Reglamento", meta["consorcio_id"], titulo, texto, meta["fecha"]))

    for archivo in sorted((directorio / "actas").glob("*.md")):
        contenido = archivo.read_text()
        meta = _parse_meta(contenido)
        for ref, titulo, texto, m in _secciones(contenido):
            docs.append(Documento(ref, "Acta", meta["consorcio_id"], titulo, texto, meta["fecha"],
                                  modifica=m.get("modifica"), efecto=m.get("efecto")))  # type: ignore[arg-type]

    corpus = Corpus(docs)
    for acta in corpus.actas():
        if acta.modifica:
            articulo = corpus.docs[acta.modifica]
            articulo.modificado_por.append(acta.ref)
            if acta.efecto == "reemplaza":
                articulo.reemplazado_por = acta.ref
    return corpus


@lru_cache(maxsize=None)
def cargar_corpus(consorcio_id: str) -> Corpus:
    return leer_corpus(directorio_consorcio(consorcio_id))
