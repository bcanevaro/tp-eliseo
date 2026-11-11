"""Specs ingesta-documental y agente-documental (requirement "Retriever híbrido")."""
from types import SimpleNamespace

import pytest

from eliseo.agentes.documental import retriever
from eliseo.agentes.documental.ingesta import a_record, records
from eliseo.corpus import cargar_corpus

CID = "R4520"


# ------------------------------------------------------------------ ingesta

def test_un_record_por_articulo_y_punto_de_acta():
    corpus = cargar_corpus(CID)
    recs = records(corpus)
    assert len(recs) == len(corpus) == 43
    assert len({r["_id"] for r in recs}) == len(recs)
    assert all(r["_id"] == f"{CID}:{r['ref']}" for r in recs)


def test_metadata_obligatoria_y_sin_nulos():
    for r in records(cargar_corpus(CID)):
        assert {"consorcio_id", "doc_tipo", "ref", "fecha", "vigente", "texto"} <= r.keys()
        assert None not in r.values()


# Scenario: Acta que modifica un artículo
def test_metadata_de_modificacion():
    corpus = cargar_corpus(CID)
    acta = a_record(corpus.get("ACTA-2025-08-20#3"))
    articulo = a_record(corpus.get("REG-14"))
    assert acta["modifica"] == "REG-14" and acta["efecto"] == "reemplaza"
    assert articulo["vigente"] is False and articulo["reemplazado_por"] == "ACTA-2025-08-20#3"
    assert a_record(corpus.get("REG-22"))["modificado_por"] == ["ACTA-2024-11-10#3"]


# ------------------------------------------------------------------ retriever (sin red)

def test_tokenizador_en_espanol():
    assert set(retriever.tokenizar("¿Puedo tener PERROS en el departamento?")) == set(retriever.tokenizar("perro departamentos tener"))


def test_rrf_premia_lo_que_aparece_en_las_dos_listas():
    assert retriever.rrf([["A", "B", "C"], ["C", "D"]])[0] == "C"


def test_bm25_solo_encuentra_toldos():
    r = retriever.buscar(CID, "toldos en el balcón")
    assert "REG-22" in r.refs and "ACTA-2024-11-10#3" in r.refs
    assert r.score is None  # sin reranker


def test_vigencia_reemplaza_el_articulo_derogado():
    r = retriever.buscar(CID, "horario de obras en las unidades")
    assert "ACTA-2025-08-20#3" in r.refs and "REG-14" not in r.refs
    assert "REG-14" in r.etapas["bm25"]  # lo encontró, pero se reemplazó por el acta vigente


def test_vigencia_suma_las_actas_que_complementan():
    docs = retriever.resolver_vigencia(CID, ["REG-22"])
    assert [d.ref for d in docs] == ["REG-22", "ACTA-2024-11-10#3"]


def test_usa_dense_y_rerank_cuando_estan(monkeypatch):
    llamados = {}

    def dense(cid, consulta, k):
        llamados["dense"] = cid
        return ["REG-18", "REG-12"]

    def reranker(consulta, textos, n):
        return [(0, 0.9), (1, 0.1)][:n]

    monkeypatch.setattr(retriever, "_config", {"dense": dense, "reranker": reranker})
    r = retriever.buscar(CID, "¿Puedo tener un perro?", k=1)
    assert llamados["dense"] == CID and r.refs == ["REG-18"] and r.score == 0.9


def test_degrada_a_bm25_si_pinecone_falla(monkeypatch):
    def dense_caido(*a):
        raise ConnectionError("sin red")

    def rerank_caido(*a):
        raise ConnectionError("sin red")

    monkeypatch.setattr(retriever, "_config", {"dense": dense_caido, "reranker": rerank_caido})
    r = retriever.buscar(CID, "animales domésticos")
    assert r.refs[0] == "REG-18" and "dense" not in r.etapas


# Scenario: Documento de otro consorcio
def test_dense_descarta_hits_de_otro_consorcio(monkeypatch):
    hits = [SimpleNamespace(fields={"ref": "REG-1", "consorcio_id": "OTRO"}),
            SimpleNamespace(fields={"ref": "REG-18", "consorcio_id": CID})]
    indice = SimpleNamespace(search=lambda **kw: SimpleNamespace(result=SimpleNamespace(hits=hits)))
    monkeypatch.setattr("eliseo.vectores.get_index", lambda: indice)
    assert retriever.dense_pinecone(CID, "x", 5) == ["REG-18"]


def test_bm25_solo_ve_el_corpus_del_consorcio():
    with pytest.raises(KeyError):
        retriever.buscar("OTRO", "animales")


# ------------------------------------------------------------------ integración con Pinecone

@pytest.mark.pinecone
def test_reingesta_sin_duplicados():
    from eliseo.agentes.documental.ingesta import _ids_existentes, ingerir
    from eliseo.vectores import get_index

    ingerir(CID)
    antes = _ids_existentes(get_index(), CID)
    ingerir(CID)
    assert _ids_existentes(get_index(), CID) == antes and len(antes) == 43


# Scenario: Palabra coloquial
@pytest.mark.pinecone
def test_toldito_con_pinecone():
    r = retriever.buscar(CID, "el toldito del balcón")
    assert {"REG-22", "ACTA-2024-11-10#3"} <= set(r.refs)


@pytest.mark.pinecone
def test_horario_de_obras_con_pinecone():
    assert "ACTA-2025-08-20#3" in retriever.buscar(CID, "a qué hora puedo hacer ruido con una obra").refs
