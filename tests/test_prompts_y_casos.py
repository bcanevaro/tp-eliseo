"""Los prompts y el dataset de evaluación son consistentes con el corpus y los contratos."""
import json
import re

import pytest

from eliseo.config import RAIZ
from eliseo.corpus import cargar_corpus
from eliseo.formato import normalizar
from eliseo.prompts import cargar
from eliseo.schemas import Dictamen, RespuestaVecino, tipo_de_referencia

CASOS = [json.loads(l) for l in (RAIZ / "evaluation" / "casos.jsonl").read_text().splitlines() if l.strip()]


def _salidas_de_ejemplo(prompt: str) -> list[dict]:
    return [json.loads(m) for m in re.findall(r"^Salida:\n(\{.*\})$", prompt, re.MULTILINE)]


def test_ejemplos_del_prompt_vecino_cumplen_el_contrato_y_citan_texto_literal():
    corpus = cargar_corpus("R4520")
    ejemplos = _salidas_de_ejemplo(cargar("vecino"))
    assert len(ejemplos) == 2
    for ej in ejemplos:
        r = RespuestaVecino.model_validate(ej)
        for c in r.citas:
            assert normalizar(c.fragmento).rstrip(".") in normalizar(corpus.get(c.referencia).texto)


def test_ejemplo_del_prompt_mediador_es_un_dictamen_valido():
    (ej,) = _salidas_de_ejemplo(cargar("mediador"))
    d = Dictamen.model_validate(ej)
    assert d.recomendacion.tipo == "inspeccion" and len(d.hipotesis) == 2


def test_dataset_tiene_los_12_casos_del_artefacto():
    tipos = [c["tipo"] for c in CASOS]
    assert (tipos.count("uso"), tipos.count("borde"), tipos.count("neg")) == (3, 4, 5)
    assert len({c["id"] for c in CASOS}) == 12


@pytest.mark.parametrize("caso", CASOS, ids=lambda c: c["id"])
def test_refs_esperadas_son_ids_canonicos(caso):
    assert all(tipo_de_referencia(r) for r in caso["refs_esperadas"])
