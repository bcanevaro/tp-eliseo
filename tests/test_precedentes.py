"""Spec precedentes: búsqueda (Pinecone + rerank o SQLite), escritura solo al aprobar e indexación. Sin red."""
from types import SimpleNamespace

import pytest

from eliseo import vectores
from eliseo.agentes.mediador import nodos, precedentes
from eliseo.grafo import runtime
from eliseo.panel import servicio
from tests.cuentas_demo import app_logueada, sesion_demo
from eliseo.plataforma.db import get_conn
from eliseo.schemas import Adjunto, Caso, EstadoCaso, MensajeEntrante, ReclamoBorrador

CID = "R4520"
TEL_4B = "+5491100000402"
HUMEDAD = "Hay humedad en el techo del baño, gotea"


def _ids(precs):
    return [p["prec_id"] for p in precs]


def _caso(unidad_id="R4520-4B", descripcion=HUMEDAD, ambiente="baño", gotea=True) -> Caso:
    return Caso(caso_id=1, consorcio_id=CID, unidad_id=unidad_id,
                reclamo=ReclamoBorrador(descripcion=descripcion, ambiente=ambiente, gotea=gotea))


class IndiceFalso:
    """Índice de Pinecone en memoria: guarda lo que se le sube y responde `search` con hits fijos."""

    def __init__(self, hits=(), falla=False):
        self.hits, self.falla = list(hits), falla
        self.subidos, self.borrados, self.busquedas, self.extras = [], [], [], []

    def search(self, namespace, query, fields):
        self.busquedas.append({"namespace": namespace, **query})
        if self.falla:
            raise ConnectionError("Pinecone caído")
        hits = [SimpleNamespace(_id=f"{c}:{p}", fields={"prec_id": p, "consorcio_id": c}) for c, p in self.hits]
        return SimpleNamespace(result=SimpleNamespace(hits=hits))

    def upsert_records(self, namespace, records):
        if self.falla:
            raise ConnectionError("Pinecone caído")
        self.subidos += [(namespace, r) for r in records]

    def list(self, prefix, namespace):
        yield [r["_id"] for ns, r in self.subidos if ns == namespace and r["_id"].startswith(prefix)] + \
              [i for i in self.extras if i.startswith(prefix)]

    def delete(self, ids, namespace):
        self.borrados += ids
        self.extras = [i for i in self.extras if i not in ids]


@pytest.fixture
def otro_consorcio(conn):
    """Otro consorcio con un precedente casi idéntico al PREC-2201 (misma columna, mismo tipo)."""
    conn.execute("INSERT INTO consorcios (consorcio_id, nombre, direccion, administracion, administradora, "
                 "telefono_emergencias) VALUES ('OTRO', 'Otro', 'Calle 1', 'Adm X', 'X', '911')")
    conn.execute("INSERT INTO unidades VALUES ('OTRO-3B', 'OTRO', '3°B', 3, 'B', '0.05')")
    conn.execute(
        """INSERT INTO precedentes (prec_id, consorcio_id, unidad_id, tipo, ubicacion, descripcion, resolucion,
                                    responsable, fecha, procedencia)
           VALUES ('PREC-9001', 'OTRO', 'OTRO-3B', 'filtracion', 'columna B, baño',
                   'Filtración en el techo del baño del 3°B por la montante de la columna B.',
                   'A cargo del consorcio (REG-16).', 'consorcio', '2025-01-10', 'test')""")
    conn.commit()


def test_los_tests_no_ven_pinecone():
    assert not vectores.hay_pinecone()


def test_clasificador_de_tipo_compartido():
    assert precedentes.tipo_reclamo(_caso()) == "filtracion"
    assert precedentes.tipo_reclamo(_caso(descripcion="No anda el portero eléctrico", ambiente="palier",
                                          gotea=False)) == "otro"


# ---------------------------------------------------------------- búsqueda sin Pinecone (SQLite)

# Scenario: Sin Pinecone / Filtración en la misma columna
def test_4b_filtracion_prec_2201_primero(db_path):
    r = precedentes.get_precedentes(CID, "R4520-4B", "filtracion", HUMEDAD)
    assert _ids(r)[0] == "PREC-2201" and "PREC-2195" in _ids(r)  # la otra columna no se descarta
    assert {"prec_id", "descripcion", "resolucion", "fecha"} <= r[0].keys()


# Scenario: Otro consorcio
def test_otro_consorcio_no_aparece(otro_consorcio):
    assert "PREC-9001" not in _ids(precedentes.get_precedentes(CID, "R4520-4B", "filtracion", HUMEDAD))
    assert _ids(precedentes.get_precedentes("OTRO", "OTRO-3B", "filtracion", HUMEDAD)) == ["PREC-9001"]


def test_filtra_por_tipo(db_path):
    assert precedentes.get_precedentes(CID, "R4520-4B", "otro", "No anda el portero eléctrico") == []


def test_nodo_toma_los_ids_del_caso(db_path):
    salida = nodos.precedentes({"caso": _caso()})
    assert _ids(salida["precedentes"])[0] == "PREC-2201"


# ---------------------------------------------------------------- búsqueda con Pinecone (índice falso)

@pytest.fixture
def con_pinecone(monkeypatch, db_path, otro_consorcio):
    def armar(hits, scores=None, falla=False, umbral="0.3"):
        indice = IndiceFalso(hits, falla=falla)
        llamadas = []

        def rerank(consulta, textos, top_n):
            llamadas.append(top_n)
            orden = [(i, scores[i]) for i in range(len(textos))]
            return sorted(orden, key=lambda x: -x[1])[:top_n]

        monkeypatch.setattr(precedentes, "hay_pinecone", lambda: True)
        monkeypatch.setattr(precedentes, "get_index", lambda **kw: indice)
        monkeypatch.setattr(precedentes, "rerank_pinecone", rerank)
        monkeypatch.setenv("PRECEDENTES_UMBRAL_RERANK", umbral)
        return indice, llamadas
    return armar


def test_pinecone_filtra_por_consorcio_y_tipo_y_sube_la_misma_columna(con_pinecone):
    # El reranker prefiere PREC-2195 (columna A), pero el boost pone primero la columna B.
    indice, llamadas = con_pinecone([(CID, "PREC-2195"), ("OTRO", "PREC-9001"), (CID, "PREC-2201")],
                                    scores=[0.9, 0.5])
    r = precedentes.get_precedentes(CID, "R4520-4B", "filtracion", HUMEDAD)
    assert _ids(r) == ["PREC-2201", "PREC-2195"]
    (b,) = indice.busquedas
    assert b["namespace"] == "precedentes" and b["top_k"] == 10 and b["inputs"]["text"] == HUMEDAD
    assert b["filter"] == {"consorcio_id": {"$eq": CID}, "tipo": {"$eq": "filtracion"}}
    assert llamadas == [2]  # rerank sin truncar antes del boost; el hit de otro consorcio no llega


def test_pinecone_descarta_bajo_el_umbral(con_pinecone):
    con_pinecone([(CID, "PREC-2195"), (CID, "PREC-2201")], scores=[0.9, 0.1])
    assert _ids(precedentes.get_precedentes(CID, "R4520-4B", "filtracion", HUMEDAD)) == ["PREC-2195"]


def test_pinecone_caido_degrada_a_sqlite(con_pinecone):
    con_pinecone([], falla=True)
    assert _ids(precedentes.get_precedentes(CID, "R4520-4B", "filtracion", HUMEDAD))[0] == "PREC-2201"


def test_rerank_caido_degrada_a_sqlite(con_pinecone, monkeypatch):
    con_pinecone([(CID, "PREC-2195")], scores=[0.9])

    def caido(*a):
        raise ConnectionError("sin red")

    monkeypatch.setattr(precedentes, "rerank_pinecone", caido)
    assert _ids(precedentes.get_precedentes(CID, "R4520-4B", "filtracion", HUMEDAD))[0] == "PREC-2201"


# ---------------------------------------------------------------- ingesta

def test_record_con_metadata_y_sin_nulos(conn):
    fila = dict(conn.execute("SELECT * FROM precedentes WHERE prec_id = 'PREC-2201'").fetchone())
    fila["ubicacion"] = None
    r = precedentes.a_record(fila)
    assert r["_id"] == f"{CID}:PREC-2201" and r["prec_id"] == "PREC-2201"
    assert {"consorcio_id": CID, "unidad_id": "R4520-3B", "tipo": "filtracion", "fecha": "2024-07-22"}.items() <= r.items()
    assert "montante" in r["texto"] and "REG-16" in r["texto"]
    assert "ubicacion" not in r and None not in r.values()


def test_ingesta_idempotente_y_borra_sobrantes(db_path, monkeypatch):
    indice = IndiceFalso()
    indice.extras = [f"{CID}:PREC-1"]  # quedó en Pinecone pero ya no está en la base
    primera = precedentes.ingerir(CID, index=indice)
    precedentes.ingerir(CID, index=indice)
    assert primera == {"consorcio_id": CID, "records": 2, "borrados": 1}
    assert indice.borrados == [f"{CID}:PREC-1"]
    assert {ns for ns, _ in indice.subidos} == {"precedentes"}
    assert {r["_id"] for _, r in indice.subidos} == {f"{CID}:PREC-2195", f"{CID}:PREC-2201"}


# ---------------------------------------------------------------- escritura al aprobar

@pytest.fixture
def bot(db_path):
    runtime._grafos.cache_clear()
    runtime._checkpointer.cache_clear()

    def enviar(texto="", usuario="u-4b", **kw):
        msg = MensajeEntrante(chat_id=f"chat-{usuario}", usuario_canal_id=usuario, texto=texto, **kw)
        return [s.texto for s in runtime.procesar_mensaje(msg)]

    enviar(telefono_compartido=TEL_4B)
    return enviar


def _reclamo(bot) -> int:
    bot("Hay humedad en el techo del baño")
    bot("gotea desde hace una semana")
    bot(adjuntos=[Adjunto(tipo="foto", file_id="f1")])
    (caso_id,) = get_conn().execute("SELECT MAX(caso_id) FROM casos").fetchone()
    return caso_id


def _prec_de(caso_id):
    return get_conn().execute("SELECT * FROM precedentes WHERE caso_id = ?", (caso_id,)).fetchone()


# Scenario: Dictamen aprobado
def test_aprobado_aparece_en_la_consulta_siguiente(bot):
    caso_id = _reclamo(bot)
    servicio.decidir(sesion_demo(), caso_id, servicio.armar_decision("APROBAR", sesion_demo()))
    prec = _prec_de(caso_id)
    assert prec["prec_id"] in _ids(precedentes.get_precedentes(CID, "R4520-4B", "filtracion", HUMEDAD))


def test_aprobado_se_indexa_con_su_metadata(bot, monkeypatch):
    indice = IndiceFalso()
    monkeypatch.setattr(precedentes, "hay_pinecone", lambda: True)
    monkeypatch.setattr(precedentes, "get_index", lambda **kw: indice)
    caso_id = _reclamo(bot)
    servicio.decidir(sesion_demo(), caso_id, servicio.armar_decision("APROBAR", sesion_demo()))
    prec = _prec_de(caso_id)
    ((ns, record),) = indice.subidos
    assert ns == "precedentes" and record["_id"] == f"{CID}:{prec['prec_id']}"
    assert {"prec_id": prec["prec_id"], "consorcio_id": CID, "unidad_id": "R4520-4B", "tipo": "filtracion"}.items() \
        <= record.items()
    assert "ubicacion" in record and "fecha" in record and None not in record.values()


def test_sin_pinecone_no_se_indexa(bot, monkeypatch):
    def no_llamar(**kw):
        raise AssertionError("no debería tocar Pinecone")

    monkeypatch.setattr(precedentes, "get_index", no_llamar)
    caso_id = _reclamo(bot)
    assert servicio.decidir(sesion_demo(), caso_id, servicio.armar_decision("APROBAR", sesion_demo())).estado is EstadoCaso.APROBADO


# Scenario: Falla la indexación
def test_falla_el_upsert_y_la_aprobacion_sigue(bot, monkeypatch):
    monkeypatch.setattr(precedentes, "hay_pinecone", lambda: True)
    monkeypatch.setattr(precedentes, "get_index", lambda **kw: IndiceFalso(falla=True))
    caso_id = _reclamo(bot)
    caso = servicio.decidir(sesion_demo(), caso_id, servicio.armar_decision("APROBAR", sesion_demo()))
    assert caso.estado is EstadoCaso.APROBADO and _prec_de(caso_id) is not None


# Scenario: Dictamen rechazado
def test_rechazado_no_crea_ni_indexa_precedente(bot, monkeypatch):
    indice = IndiceFalso()
    monkeypatch.setattr(precedentes, "hay_pinecone", lambda: True)
    monkeypatch.setattr(precedentes, "get_index", lambda **kw: indice)
    caso_id = _reclamo(bot)
    servicio.decidir(sesion_demo(), caso_id, servicio.armar_decision("RECHAZAR", sesion_demo(), motivo="falta inspección"))
    assert _prec_de(caso_id) is None and indice.subidos == []
    (decision,) = servicio.detalle_caso(sesion_demo(), caso_id).decisiones
    assert decision["motivo"] == "falta inspección"


# ---------------------------------------------------------------- integración con Pinecone

@pytest.mark.pinecone
def test_ingesta_y_consulta_real_4b(db_path):
    precedentes.ingerir(CID)
    assert _ids(precedentes.get_precedentes(CID, "R4520-4B", "filtracion", HUMEDAD))[0] == "PREC-2201"
