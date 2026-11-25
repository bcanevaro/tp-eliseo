"""Evaluación del Intake + Router como clasificador (spec intake-router, "Evaluación como clasificador").

    python evaluation/intake/eval_intake.py               # con el LLM del proxy (INTAKE_MODO=llm)
    INTAKE_MODO=reglas python evaluation/intake/eval_intake.py   # línea de base sin LLM
    python evaluation/intake/eval_intake.py --langsmith   # + dataset y experimento en LangSmith

Métricas: precision y recall por intent (contando el intent principal y los `multi`), acierto del
intent principal y recall de urgencias, que tiene que ser 1.
"""
import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from eliseo.schemas import Intent, MensajeEntrante  # noqa: E402

MENSAJES = [json.loads(l) for l in (Path(__file__).parent / "mensajes.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
TEL = "+5491100000402"
INTENTS = [i.value for i in Intent]


def clasificar(texto: str) -> dict:
    from eliseo.intake import intake
    from eliseo.plataforma import lectura
    from eliseo.plataforma.db import get_conn

    ident = lectura.identidad_por_telefono(get_conn(), TEL)
    r = intake({"mensaje": MensajeEntrante(chat_id="eval", usuario_canal_id="eval", texto=texto), "identidad": ident})["intake"]
    return {"intent": r.intent.value, "multi": [m.value for m in r.multi], "urgencia": r.urgencia}


def metricas(filas: list[dict]) -> dict:
    res = {}
    for intent in INTENTS:
        tp = sum(intent in f["pred_todos"] and intent in f["esp_todos"] for f in filas)
        fp = sum(intent in f["pred_todos"] and intent not in f["esp_todos"] for f in filas)
        fn = sum(intent not in f["pred_todos"] and intent in f["esp_todos"] for f in filas)
        res[intent] = {"precision": round(tp / (tp + fp), 3) if tp + fp else None,
                       "recall": round(tp / (tp + fn), 3) if tp + fn else None}
    urg = [f for f in filas if f["esp_urgencia"]]
    res["acierto_intent_principal"] = round(sum(f["pred"]["intent"] == f["intent"] for f in filas) / len(filas), 3)
    res["recall_urgencias"] = round(sum(f["pred"]["urgencia"] for f in urg) / len(urg), 3)
    res["falsas_urgencias"] = sum(f["pred"]["urgencia"] and not f["esp_urgencia"] for f in filas)
    return res


def correr() -> tuple[list[dict], dict]:
    import os
    import tempfile

    from eliseo.grafo import runtime
    from scripts.seed_db import seed

    tmp = Path(tempfile.mkdtemp())
    os.environ["ELISEO_DB_URL"] = ""  # nunca la base de Supabase del .env
    os.environ.setdefault("ELISEO_DB_PATH", str(tmp / "eliseo.db"))
    if not Path(os.environ["ELISEO_DB_PATH"]).exists():
        seed(Path(os.environ["ELISEO_DB_PATH"]))
    runtime._grafos.cache_clear()
    filas = []
    for m in MENSAJES:
        pred = clasificar(m["texto"])
        filas.append({**m, "pred": pred, "pred_todos": {pred["intent"], *pred["multi"]},
                      "esp_todos": {m["intent"], *m["multi"]}, "esp_urgencia": m["urgencia"]})
    return filas, metricas(filas)


def subir_a_langsmith() -> str:
    from langsmith import Client, evaluate

    client, nombre = Client(), "eliseo-intake"
    if not client.has_dataset(dataset_name=nombre):
        ds = client.create_dataset(nombre, description="Mensajes de vecinos etiquetados: intent, multi y urgencia")
        client.create_examples(dataset_id=ds.id, inputs=[{"texto": m["texto"]} for m in MENSAJES],
                               outputs=[{"intent": m["intent"], "multi": m["multi"], "urgencia": m["urgencia"]} for m in MENSAJES],
                               metadata=[{"id": m["id"]} for m in MENSAJES])

    def intent_principal(run, example):
        return {"key": "intent_principal", "score": float(run.outputs["intent"] == example.outputs["intent"])}

    def todos_los_intents(run, example):
        pred = {run.outputs["intent"], *run.outputs["multi"]}
        esp = {example.outputs["intent"], *example.outputs["multi"]}
        return {"key": "todos_los_intents", "score": float(pred == esp)}

    def urgencia(run, example):
        if not example.outputs["urgencia"]:
            return {"key": "recall_urgencia", "score": None}
        return {"key": "recall_urgencia", "score": float(run.outputs["urgencia"])}

    def resumen(runs, examples):
        filas = [{"intent": e.outputs["intent"], "pred": r.outputs, "esp_urgencia": e.outputs["urgencia"],
                  "pred_todos": {r.outputs["intent"], *r.outputs["multi"]}, "esp_todos": {e.outputs["intent"], *e.outputs["multi"]}}
                 for r, e in zip(runs, examples)]
        m = metricas(filas)
        # LangSmith pide {"results": [...]} para varias métricas de resumen; una lista suelta la rechaza.
        return {"results": [{"key": f"{i}_{k}", "score": m[i][k]} for i in INTENTS for k in ("precision", "recall")
                            if m[i][k] is not None]}

    res = evaluate(lambda inputs: clasificar(inputs["texto"]), data=nombre,
                   evaluators=[intent_principal, todos_los_intents, urgencia], summary_evaluators=[resumen],
                   experiment_prefix="intake")
    return res.experiment_name


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # la consola de Windows no es UTF-8 por defecto
    ap = argparse.ArgumentParser()
    ap.add_argument("--langsmith", action="store_true")
    ap.add_argument("--detalle", action="store_true")
    args = ap.parse_args()
    filas, m = correr()
    print(f"{'intent':11} {'precision':>9} {'recall':>7}")
    for i in INTENTS:
        print(f"{i:11} {m[i]['precision']!s:>9} {m[i]['recall']!s:>7}")
    print(f"acierto del intent principal: {m['acierto_intent_principal']}")
    print(f"recall de urgencias: {m['recall_urgencias']} (tiene que ser 1) · falsas urgencias: {m['falsas_urgencias']}")
    if args.detalle:
        for f in filas:
            ok = f["pred_todos"] == f["esp_todos"] and f["pred"]["urgencia"] == f["urgencia"]
            print(f"{'✓' if ok else '✗'} {f['id']} {f['pred']} ← {f['intent']}{f['multi']} urg={f['urgencia']} | {f['texto']}")
    if args.langsmith:
        print("experimento:", subir_a_langsmith())
