import pytest

from eliseo.plataforma.db import conectar


@pytest.fixture(autouse=True)
def sin_red(request, monkeypatch):
    """Por defecto los tests no usan red ni LLM: Documental en modo retriever y solo BM25.
    Los tests marcados `pinecone` usan la configuración real."""
    if request.node.get_closest_marker("pinecone"):
        yield
        return
    from eliseo.agentes.documental import retriever

    monkeypatch.setenv("DOCUMENTAL_MODO", "retriever")
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
