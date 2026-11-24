"""Evaluación de recuperación de precedentes y calibración de PRECEDENTES_UMBRAL_RERANK (design D11, tarea 5.2).

    python evaluation/mediador/precedentes_eval.py               # local (necesita Pinecone con los precedentes ingeridos)
    python evaluation/mediador/precedentes_eval.py --langsmith   # además, dataset y experimento en LangSmith

Repite la búsqueda de `precedentes._desde_pinecone` (filtro por consorcio y tipo, rerank, umbral,
misma columna primero, hasta 3) pero guarda el score del reranker de cada candidato, para poder
barrer el umbral sin volver a llamar a Pinecone.

Métricas por consulta (sobre los precedentes devueltos):
  precision   devueltos relevantes / devueltos (1 si no devuelve nada y no había nada relevante)
  recall      relevantes devueltos / relevantes (1 si no había relevantes)
  primero     el primero devuelto es el esperado (o no devuelve nada cuando no se espera ninguno)
"""
import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from eliseo import config  # noqa: E402
from eliseo.agentes.mediador import precedentes  # noqa: E402
from eliseo.plataforma import lectura  # noqa: E402
from eliseo.plataforma.db import get_conn  # noqa: E402

CONSULTAS = [json.loads(l) for l in (Path(__file__).parent / "consultas_precedentes.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]


def candidatos(q: dict) -> list[tuple[dict, float]]:
    """Los candidatos de Pinecone con su score de rerank, antes del umbral (mismo camino que producción)."""
    from eliseo.agentes.documental.retriever import rerank_pinecone
    from eliseo.vectores import NS_PRECEDENTES, filtro_consorcio, get_index

    filtro = filtro_consorcio(q["consorcio_id"], **({"tipo": {"$eq": q["tipo"]}} if q["tipo"] else {}))
    r = get_index().search(namespace=NS_PRECEDENTES, fields=["prec_id", "consorcio_id"],
                           query={"inputs": {"text": q["descripcion"]}, "top_k": precedentes.TOP_CANDIDATOS, "filter": filtro})
    base = {p["prec_id"]: p for p in lectura.precedentes(get_conn(), q["consorcio_id"], q["tipo"])}
    cands = [base[h.fields["prec_id"]] for h in r.result.hits
             if h.fields.get("consorcio_id") == q["consorcio_id"] and h.fields.get("prec_id") in base]
    if not cands:
        return []
    orden = rerank_pinecone(q["descripcion"], [precedentes._texto(p) for p in cands], len(cands))
    return [(cands[i], score) for i, score in orden]


def devueltos(q: dict, cands: list[tuple[dict, float]], umbral: float) -> list[str]:
    pasan = [p for p, score in cands if score >= umbral]
    return [p["prec_id"] for p in precedentes._misma_columna_primero(pasan, q["unidad_id"])[:precedentes.MAX_PRECEDENTES]]


def metricas(q: dict, ids: list[str]) -> dict:
    rel = set(q["relevantes"])
    return {
        "precision": (len(rel & set(ids)) / len(ids)) if ids else float(not rel),
        "recall": (len(rel & set(ids)) / len(rel)) if rel else 1.0,
        "primero": (ids[0] == q["primero"]) if ids else q["primero"] is None,
    }


def resumen(filas: list[dict]) -> dict:
    n = len(filas)
    return {k: round(sum(float(f[k]) for f in filas) / n, 3) for k in ("precision", "recall", "primero")}


def evaluar(cands_por_q: dict, umbral: float) -> tuple[list[dict], dict]:
    filas = []
    for q in CONSULTAS:
        ids = devueltos(q, cands_por_q[q["id"]], umbral)
        filas.append({"id": q["id"], "devueltos": ids, **metricas(q, ids)})
    return filas, resumen(filas)


def calibrar(cands_por_q: dict) -> list[dict]:
    """Barre el umbral en los scores observados (y 0): cada fila es lo que daría ese umbral."""
    scores = sorted({0.0, *(round(s, 4) for c in cands_por_q.values() for _, s in c)})
    return [{"umbral": u, **evaluar(cands_por_q, u)[1]} for u in scores]


def subir_a_langsmith(umbral: float) -> str:
    from langsmith import Client, evaluate

    client, nombre = Client(), "eliseo-precedentes"
    if not client.has_dataset(dataset_name=nombre):
        ds = client.create_dataset(nombre, description="Consultas rotuladas para la tool de precedentes (design D11)")
        client.create_examples(
            dataset_id=ds.id,
            inputs=[{k: q[k] for k in ("id", "consorcio_id", "unidad_id", "tipo", "descripcion")} for q in CONSULTAS],
            outputs=[{"relevantes": q["relevantes"], "primero": q["primero"]} for q in CONSULTAS])
    por_id = {q["id"]: q for q in CONSULTAS}

    def objetivo(inputs: dict) -> dict:
        q = por_id[inputs["id"]]
        cands = candidatos(q)
        return {"devueltos": devueltos(q, cands, umbral), "scores": {p["prec_id"]: s for p, s in cands}}

    def metrica(clave: str):
        def ev(run, example):
            return {"key": clave, "score": float(metricas(por_id[example.inputs["id"]], run.outputs["devueltos"])[clave])}
        return ev

    res = evaluate(objetivo, data=nombre, evaluators=[metrica(k) for k in ("precision", "recall", "primero")],
                   experiment_prefix=f"precedentes-umbral-{umbral}", metadata={"umbral": umbral}, max_concurrency=1)
    return res.experiment_name


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--umbral", type=float, help="umbral a evaluar (por defecto, PRECEDENTES_UMBRAL_RERANK)")
    ap.add_argument("--langsmith", action="store_true")
    args = ap.parse_args()
    config._cargar()
    umbral = precedentes.umbral() if args.umbral is None else args.umbral

    cands_por_q = {q["id"]: candidatos(q) for q in CONSULTAS}
    print("Scores del reranker por consulta:")
    for q in CONSULTAS:
        print(f"  {q['id']} {q['unidad_id']:9} {q['descripcion'][:55]:55} "
              + (", ".join(f"{p['prec_id']}={s:.3f}" for p, s in cands_por_q[q["id"]]) or "(sin candidatos)"))

    filas, res = evaluar(cands_por_q, umbral)
    print(f"\nCon umbral {umbral}:")
    for f in filas:
        ok = f["precision"] == 1 and f["recall"] == 1 and f["primero"]
        print(f"  {'✓' if ok else '✗'} {f['id']}  devueltos={f['devueltos']}  P={f['precision']:.2f} R={f['recall']:.2f} primero={f['primero']}")
    print("  promedio:", res)

    print("\nBarrido del umbral:")
    for c in calibrar(cands_por_q):
        print(f"  {c['umbral']:<7} P={c['precision']:.3f} R={c['recall']:.3f} primero={c['primero']:.3f}")

    if args.langsmith:
        print("experimento:", subir_a_langsmith(umbral))
