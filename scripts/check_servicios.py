"""Verifica el .env y la conexión con cada servicio externo antes de correr la demo o la evaluación.

    python scripts/check_servicios.py

Para cada servicio dice ✓ o ✗ con qué hacer. No escribe nada en ningún servicio.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eliseo.config import env  # noqa: E402

OK, MAL, AVISO = "✓", "✗", "!"


def linea(estado: str, que: str, detalle: str = "") -> None:
    print(f"{estado} {que}" + (f": {detalle}" if detalle else ""))


def proxy() -> None:
    try:
        from openai import OpenAI

        client = OpenAI(base_url=env("LITELLM_BASE_URL", "LLM_SERVICE_URL"), api_key=env("LITELLM_API_KEY", "LLM_API_KEY"))
    except KeyError as e:
        return linea(MAL, "Proxy LiteLLM", str(e))
    try:
        modelos = sorted(m.id for m in client.models.list().data)
        linea(OK, "Proxy LiteLLM", f"{len(modelos)} modelos disponibles")
        print("    " + ", ".join(modelos[:40]))
    except Exception as e:  # noqa: BLE001
        return linea(MAL, "Proxy LiteLLM", f"{type(e).__name__}: {e}")
    for var, nombre in [("LLM_MODEL", "principal"), ("LLM_MODEL_FAST", "rápido"), ("LLM_MODEL_REASONING", "razonamiento")]:
        modelo = env(var, default="")
        if not modelo:
            linea(AVISO, f"Modelo {nombre} ({var})", "no configurado: se usa LLM_MODEL")
            continue
        try:
            r = client.chat.completions.create(model=modelo, messages=[{"role": "user", "content": "Decí OK"}], max_tokens=5)
            linea(OK, f"Modelo {nombre} ({modelo})", repr(r.choices[0].message.content))
        except Exception as e:  # noqa: BLE001
            linea(MAL, f"Modelo {nombre} ({modelo})", f"{type(e).__name__}: {str(e)[:200]}")


def estructurado() -> None:
    try:
        from pydantic import BaseModel

        from eliseo.llm import get_fast_model

        class Prueba(BaseModel):
            ok: bool

        r = get_fast_model().with_structured_output(Prueba).invoke("Respondé ok=true")
        linea(OK, "Salida estructurada (with_structured_output)", str(r))
    except Exception as e:  # noqa: BLE001
        linea(MAL, "Salida estructurada", f"{type(e).__name__}: {str(e)[:200]}")


def pinecone() -> None:
    try:
        from eliseo import vectores

        pc = vectores.get_client()
        nombre = vectores.nombre_indice()
        if not pc.has_index(nombre):
            return linea(AVISO, f"Pinecone (índice '{nombre}')", "no existe: corré python scripts/ingest.py R4520")
        stats = vectores.get_index().describe_index_stats()
        linea(OK, f"Pinecone (índice '{nombre}')", f"namespaces: {dict((k, v.vector_count) for k, v in stats.namespaces.items())}")
    except KeyError as e:
        linea(MAL, "Pinecone", str(e))
    except Exception as e:  # noqa: BLE001
        linea(MAL, "Pinecone", f"{type(e).__name__}: {str(e)[:200]}")


def langsmith() -> None:
    try:
        env("LANGSMITH_API_KEY")
        from langsmith import Client

        list(Client().list_projects(limit=1))
        linea(OK, "LangSmith", f"proyecto '{env('LANGSMITH_PROJECT', default='default')}'")
    except KeyError as e:
        linea(MAL, "LangSmith", str(e))
    except Exception as e:  # noqa: BLE001
        linea(MAL, "LangSmith", f"{type(e).__name__}: {str(e)[:200]}")


def telegram() -> None:
    try:
        token = env("TELEGRAM_BOT_TOKEN")
    except KeyError:
        return linea(AVISO, "Telegram", "falta TELEGRAM_BOT_TOKEN (creá el bot con @BotFather → /newbot)")
    try:
        import requests

        r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10).json()
        if not r.get("ok"):
            return linea(MAL, "Telegram", r.get("description", "token inválido"))
        linea(OK, "Telegram", f"bot @{r['result']['username']}")
    except Exception as e:  # noqa: BLE001
        linea(MAL, "Telegram", f"{type(e).__name__}: {str(e)[:200]}")


def base() -> None:
    """La base en uso (Supabase o SQLite), sin mostrar la contraseña, y qué tiene cargado."""
    import re

    from eliseo.config import db_url

    url = db_url()
    nombre = "Postgres (Supabase)" if url.startswith("postgresql") else "SQLite local"
    try:
        from eliseo.plataforma.db import get_conn

        conn = get_conn()
        cuenta = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                  for t in ("administraciones", "administradores", "consorcios", "vecinos", "documentos")}
        linea(OK, f"Base: {nombre}", re.sub(r"://([^:/@]+):[^@]+@", r"://\1:***@", url))
        print("    " + ", ".join(f"{k}: {v}" for k, v in cuenta.items()))
        if not cuenta["administradores"]:
            linea(AVISO, "Cuentas", "no hay ninguna: corré python scripts/seed_db.py (demo) o scripts/alta_administracion.py")
        sin_chat = [f[0] for f in conn.execute("SELECT nombre FROM administraciones WHERE chat_avisos_id IS NULL").fetchall()]
        if sin_chat:
            linea(AVISO, "Chat de avisos", "sin vincular en " + ", ".join(sin_chat)
                  + " (panel → Chat de avisos → /admin <código> en Telegram)")
        pendientes = conn.execute("SELECT COUNT(*) FROM documentos WHERE estado = 'activo' AND indexado = 0").fetchone()[0]
        if pendientes:
            linea(AVISO, "Documentos", f"{pendientes} sin indexar en Pinecone (panel → Documentos → Reintentar, "
                                       "o python scripts/ingest.py <consorcio>)")
    except Exception as e:  # noqa: BLE001
        linea(MAL, f"Base: {nombre}", f"{type(e).__name__}: {str(e)[:200]}")


def supabase() -> None:
    from eliseo.config import supabase_url

    url = supabase_url()
    if env("SUPABASE_URL", default="").rstrip("/") != url:
        linea(AVISO, "SUPABASE_URL", f"tiene una ruta de más; se usa {url} (copiá solo eso en el .env)")
    if not url:
        return linea(AVISO, "Supabase Auth y Storage", "sin SUPABASE_URL: login local y originales en data/archivos/")
    try:
        import requests

        anon = env("SUPABASE_ANON_KEY")
        r = requests.get(f"{url}/auth/v1/health", headers={"apikey": anon}, timeout=10)
        linea(OK if r.ok else MAL, "Supabase Auth", f"HTTP {r.status_code}")
    except KeyError as e:
        linea(MAL, "Supabase Auth", str(e))
    except Exception as e:  # noqa: BLE001
        linea(MAL, "Supabase Auth", f"{type(e).__name__}: {str(e)[:200]}")
    try:
        from supabase import create_client

        buckets = [b.name for b in create_client(url, env("SUPABASE_SERVICE_ROLE_KEY")).storage.list_buckets()]
        linea(OK, "Supabase Storage", f"buckets: {buckets or 'ninguno (se crea «documentos» al subir el primero)'}")
    except KeyError as e:
        linea(MAL, "Supabase Storage", str(e))
    except Exception as e:  # noqa: BLE001
        linea(MAL, "Supabase Storage", f"{type(e).__name__}: {str(e)[:200]}")


def env_versionado() -> None:
    """El .env tiene la clave de servicio de Supabase: nunca tiene que estar en git."""
    import subprocess

    raiz = Path(__file__).resolve().parent.parent
    r = subprocess.run(["git", "ls-files", "--error-unmatch", ".env"], cwd=raiz, capture_output=True)
    if r.returncode == 0:
        linea(MAL, ".env", "está versionado en git: sacalo (git rm --cached .env) y rotá las claves")
    else:
        linea(OK, ".env", "no está versionado")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # la consola de Windows no es UTF-8 por defecto
    for chequeo in (env_versionado, base, supabase, proxy, estructurado, pinecone, langsmith, telegram):
        chequeo()
