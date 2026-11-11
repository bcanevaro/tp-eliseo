"""Evaluación de recuperación del agente Documental, por etapa (design D9). No usa LLM.

    python evaluation/documental/eval_recuperacion.py              # local
    python evaluation/documental/eval_recuperacion.py --langsmith  # además, experimento en LangSmith

Métricas por etapa (dense, bm25, rrf, rrf+rerank), siempre después de resolver la vigencia:
- acierto@3: alguna ref esperada en las 3 primeras
- recall@3:  fracción de las refs esperadas que están en las 3 primeras
- MRR:       1 / posición de la primera ref esperada
Y la calibración del umbral de abstención con las preguntas sin fuente.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from eliseo.agentes.documental import retriever  # noqa: E402

CID = "R4520"
PREGUNTAS = [json.loads(l) for l in (Path(__file__).parent / "preguntas.jsonl").read_text().splitlines() if l.strip()]
ETAPAS = ["dense", "bm25", "rrf", "rerank"]


def _resueltas(refs: list[str], k: int = 3) -> list[str]:
    return [d.ref for d in retriever.resolver_vigencia(CID, refs[:k])]


def metricas(obtenidas: list[str], esperadas: list[str]) -> dict:
    top = obtenidas[:3]
    rr = next((1 / (i + 1) for i, r in enumerate(obtenidas) if r in esperadas), 0.0)
    return {"acierto@3": float(any(r in top for r in esperadas)),
            "recall@3": sum(r in top for r in esperadas) / len(esperadas), "mrr": rr}


def correr() -> tuple[list[dict], dict]:
    filas = []
    for p in PREGUNTAS:
        r = retriever.buscar(CID, p["pregunta"], k=3)
        etapas = {e: _resueltas(r.etapas[e]) for e in ETAPAS if e in r.etapas}
        filas.append({**p, "etapas": etapas, "score": r.score})

    con_fuente = [f for f in filas if f["refs_esperadas"]]
    resumen = {}
    for e in ETAPAS:
        ms = [metricas(f["etapas"][e], f["refs_esperadas"]) for f in con_fuente if e in f["etapas"]]
        if ms:
            resumen[e] = {m: round(sum(x[m] for x in ms) / len(ms), 3) for m in ms[0]}
    return filas, resumen


def calibrar(filas: list[dict], umbral: float | None = None) -> dict:
    """Costo asimétrico: contestar sin fuente (riesgo 1 del Discovery) es mucho peor que derivar
    de más. Se reporta el umbral configurado y el mínimo que no deja pasar ninguna sin fuente."""
    if all(f["score"] is None for f in filas):
        return {}
    umbral = retriever.umbral_suficiente() if umbral is None else umbral
    sin_fuente = [f["score"] or 0 for f in filas if not f["refs_esperadas"]]
    con_fuente = [f for f in filas if f["refs_esperadas"]]
    return {
        "umbral": umbral,
        "mayor_score_sin_fuente": round(max(sin_fuente), 3),
        "sin_fuente_contestadas": [f["id"] for f in filas if not f["refs_esperadas"] and (f["score"] or 0) >= umbral],
        "con_fuente_contestadas": f"{sum((f['score'] or 0) >= umbral for f in con_fuente)}/{len(con_fuente)}",
        "con_fuente_derivadas": [f["id"] for f in con_fuente if (f["score"] or 0) < umbral],
    }


def subir_a_langsmith() -> str:
    from langsmith import Client, evaluate

    client, nombre = Client(), "eliseo-documental-recuperacion"
    if not client.has_dataset(dataset_name=nombre):
        ds = client.create_dataset(nombre, description="Preguntas vecinales → refs del reglamento y actas (Consorcio Rivadavia 4520)")
        client.create_examples(dataset_id=ds.id, inputs=[{"pregunta": p["pregunta"]} for p in PREGUNTAS],
                               outputs=[{"refs_esperadas": p["refs_esperadas"]} for p in PREGUNTAS],
                               metadata=[{"id": p["id"]} for p in PREGUNTAS])

    def objetivo(inputs: dict) -> dict:
        r = retriever.buscar(CID, inputs["pregunta"], k=3)
        return {"refs": r.refs, "score": r.score, **{e: _resueltas(r.etapas[e]) for e in ETAPAS if e in r.etapas}}

    def evaluador(etapa: str, metrica: str):
        def ev(run, example):
            esperadas = example.outputs["refs_esperadas"]
            if not esperadas:
                return {"key": f"{etapa}_{metrica}", "score": None}
            return {"key": f"{etapa}_{metrica}", "score": metricas(run.outputs.get(etapa, []), esperadas)[metrica]}
        return ev

    def abstencion(run, example):
        sin_fuente = not example.outputs["refs_esperadas"]
        se_abstiene = (run.outputs["score"] or 0) < retriever.umbral_suficiente()
        return {"key": "abstencion_correcta", "score": float(se_abstiene == sin_fuente)}

    evaluadores = [evaluador(e, m) for e in ETAPAS for m in ("acierto@3", "mrr")] + [abstencion]
    res = evaluate(objetivo, data=nombre, evaluators=evaluadores, experiment_prefix="hibrido-e5-bge",
                   metadata={"embedding": "multilingual-e5-large", "rerank": "bge-reranker-v2-m3", "rrf_k": retriever.RRF_K})
    return res.experiment_name


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--langsmith", action="store_true")
    ap.add_argument("--detalle", action="store_true")
    args = ap.parse_args()

    filas, resumen = correr()
    print(f"{'etapa':8} {'acierto@3':>10} {'recall@3':>9} {'MRR':>6}")
    for e, m in resumen.items():
        print(f"{e:8} {m['acierto@3']:>10} {m['recall@3']:>9} {m['mrr']:>6}")
    print("calibración:", calibrar(filas))
    if args.detalle:
        for f in filas:
            final = f["etapas"].get("rerank") or f["etapas"]["rrf"]
            ok = "✓" if not f["refs_esperadas"] or any(r in final for r in f["refs_esperadas"]) else "✗"
            print(f"{ok} {f['id']} {f['score'] and round(f['score'], 3)!s:>6} {final} ← {f['refs_esperadas']} | {f['pregunta']}")
    if args.langsmith:
        print("experimento:", subir_a_langsmith())
