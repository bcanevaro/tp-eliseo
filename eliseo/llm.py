"""Clientes del proxy LiteLLM del ITBA, uno por rol (design D6).

- get_fast_model: intake y redacción de respuestas (LLM_MODEL_FAST, si falta usa LLM_MODEL).
- get_model: agentes Documental y Gastos (LLM_MODEL).
- get_reasoning_model: Mediador (LLM_MODEL_REASONING). No recibe temperature porque los
  modelos de razonamiento la rechazan.
"""
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

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


def get_reasoning_model() -> ChatOpenAI:
    return ChatOpenAI(model=env("LLM_MODEL_REASONING", "LLM_MODEL"), **_proxy())


def get_embeddings() -> OpenAIEmbeddings:
    # check_embedding_ctx_length=False: evita que LangChain tokenice con tiktoken un modelo
    # que está detrás del proxy.
    return OpenAIEmbeddings(
        model=env("EMBEDDING_MODEL", default="text-embedding-3-small"),
        check_embedding_ctx_length=False,
        **_proxy(),
    )
