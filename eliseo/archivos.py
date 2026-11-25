"""Archivos originales de los documentos que suben las administraciones (design D6).

Con Supabase configurado (SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY) van al bucket privado
`documentos` de Supabase Storage; si no, a `data/archivos/`. La ruta guardada en la base empieza
con `storage:` o `local:` para saber de dónde leerla aunque cambie la configuración.
"""
import re
from pathlib import Path

from eliseo.config import DATA_DIR, env, supabase_url

BUCKET = "documentos"


def _con_storage() -> bool:
    return bool(supabase_url() and env("SUPABASE_SERVICE_ROLE_KEY", default=""))


def _storage():
    from supabase import create_client

    cliente = create_client(supabase_url(), env("SUPABASE_SERVICE_ROLE_KEY"))
    if not any(b.name == BUCKET for b in cliente.storage.list_buckets()):
        cliente.storage.create_bucket(BUCKET, options={"public": False})
    return cliente.storage.from_(BUCKET)


def _seguro(nombre: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", nombre or "documento.md")[:80]


def guardar(consorcio_id: str, doc_id: int, nombre: str, contenido: bytes) -> str:
    """Guarda el original y devuelve la ruta para la base."""
    relativa = f"{consorcio_id}/{doc_id}-{_seguro(nombre)}"
    if _con_storage():
        _storage().upload(relativa, contenido, {"content-type": "text/markdown", "upsert": "true"})
        return f"storage:{relativa}"
    destino = dir_local() / relativa
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(contenido)
    return f"local:{relativa}"


def leer(ruta: str) -> bytes:
    origen, _, relativa = ruta.partition(":")
    if origen == "storage":
        return _storage().download(relativa)
    if origen == "local":
        return (dir_local() / relativa).read_bytes()
    raise ValueError(f"Ruta de archivo desconocida: {ruta}")


def dir_local() -> Path:
    """ELISEO_ARCHIVOS_DIR la cambian los tests (un directorio temporal)."""
    return Path(env("ELISEO_ARCHIVOS_DIR", default=str(DATA_DIR / "archivos")))
