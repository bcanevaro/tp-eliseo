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
        if not env("TELEGRAM_CHAT_ADMIN_ID", default=""):
            linea(AVISO, "TELEGRAM_CHAT_ADMIN_ID", "sin configurar: escribile al bot y abrí "
                  f"https://api.telegram.org/bot<token>/getUpdates para ver tu chat id")
    except Exception as e:  # noqa: BLE001
        linea(MAL, "Telegram", f"{type(e).__name__}: {str(e)[:200]}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # la consola de Windows no es UTF-8 por defecto
    for chequeo in (proxy, estructurado, pinecone, langsmith, telegram):
        chequeo()
