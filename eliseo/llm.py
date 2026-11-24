"""Clientes del proxy LiteLLM del ITBA, uno por rol (design D6).

- get_fast_model: intake y redacción de respuestas (LLM_MODEL_FAST, si falta usa LLM_MODEL).
- get_model: agentes Documental y Gastos (LLM_MODEL).
- get_reasoning_model: Mediador (LLM_MODEL_REASONING, con LLM_REASONING_EFFORT). No recibe
  temperature porque los modelos de razonamiento la rechazan; si cae a LLM_MODEL (gpt-4.1) tampoco
  recibe reasoning_effort, que ese modelo rechaza (design D2 de flujo-reclamo-mediador).
"""
from langchain_openai import ChatOpenAI

from eliseo.config import env


def _proxy() -> dict:
    # Se aceptan los nombres del enunciado (LITELLM_*) y los del proxy de la materia (LLM_*).
    return dict(
        base_url=env("LITELLM_BASE_URL", "LLM_SERVICE_URL"),
        api_key=env("LITELLM_API_KEY", "LLM_API_KEY"),
    )


def get_fast_model(temperature: float = 0) -> ChatOpenAI:
    modelo = env("LLM_MODEL_FAST", "LLM_MODEL")
    return ChatOpenAI(model=modelo, temperature=temperature, **_proxy())


def get_model(temperature: float = 0) -> ChatOpenAI:
    return ChatOpenAI(model=env("LLM_MODEL"), temperature=temperature, **_proxy())


def es_razonamiento(modelo: str) -> bool:
    """Los gpt-3.x / gpt-4.x (gpt-4.1, gpt-4o…) no aceptan reasoning_effort. El proxy también
    nombra los modelos con el proveedor adelante (`openai/gpt-4.1`): se compara sin el prefijo."""
    return not modelo.lower().rsplit("/", 1)[-1].startswith(("gpt-3", "gpt-4"))


def get_reasoning_model() -> ChatOpenAI:
    modelo = env("LLM_MODEL_REASONING", default="")
    if modelo and es_razonamiento(modelo):
        esfuerzo = env("LLM_REASONING_EFFORT", default="medium")
        return ChatOpenAI(model=modelo, reasoning_effort=esfuerzo, **_proxy())
    return ChatOpenAI(model=modelo or env("LLM_MODEL"), **_proxy())
