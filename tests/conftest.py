import pytest

from eliseo.plataforma.db import conectar


@pytest.fixture(autouse=True)
def sin_red(request, monkeypatch):
    """Por defecto los tests no usan red ni LLM: Documental en modo retriever y solo BM25, Gastos, Intake y Mediador sin LLM.
    Los tests marcados `pinecone` usan la configuración real."""
    # Los tests no mandan trazas a LangSmith aunque el .env tenga LANGSMITH_TRACING=true.
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    if request.node.get_closest_marker("pinecone"):
        yield
        return
    from eliseo import config
    from eliseo.agentes.documental import retriever

    # Sin Pinecone aunque el .env tenga la key: se carga el .env antes de borrarla, así
    # load_dotenv (que corre una sola vez) no la vuelve a poner durante el test.
    config._cargar()
    monkeypatch.delenv("PINECONE_API_KEY", raising=False)
    monkeypatch.setenv("DOCUMENTAL_MODO", "retriever")
    monkeypatch.setenv("GASTOS_MODO", "codigo")
    monkeypatch.setenv("INTAKE_MODO", "reglas")
    monkeypatch.setenv("MEDIADOR_MODO", "codigo")
    monkeypatch.setattr(retriever, "_config", {"dense": None, "reranker": None})
    yield


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    """Base y checkpoints en un directorio temporal, recién sembrados."""
    path = tmp_path / "eliseo.db"
    monkeypatch.setenv("ELISEO_DB_PATH", str(path))
    monkeypatch.setenv("ELISEO_CHECKPOINT_DB", str(tmp_path / "grafos.db"))
    from scripts.seed_db import seed

    seed(path)
    return path


@pytest.fixture
def conn(db_path):
    c = conectar(db_path)
    yield c
    c.close()
