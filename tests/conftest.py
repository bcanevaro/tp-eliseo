import pytest

from eliseo.plataforma.db import conectar


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
