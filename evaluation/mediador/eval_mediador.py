"""Evaluación del Mediador (spec agente-mediador, design D11; tareas 5.1, 5.3, 5.4 y 5.5).

    python evaluation/mediador/eval_mediador.py                          # baseline: LLM_MODEL (gpt-4.1), prompt v2
    python evaluation/mediador/eval_mediador.py --modelo openai/gpt-5.6  # modelo de razonamiento
    python evaluation/mediador/eval_mediador.py --prompt v1              # versión anterior del prompt
    python evaluation/mediador/eval_mediador.py --sin-juez               # solo evaluadores de código
    python evaluation/mediador/eval_mediador.py --langsmith              # + dataset y experimento en LangSmith

Cada caso registra el reclamo en una base recién sembrada y corre el grafo de caso real hasta el panel
(Documental ‖ precedentes → Mediador ⇄ verificador). Documental del caso y precedentes son código, así
que todas las llamadas al LLM dentro del grafo son del Mediador: sus tokens se cuentan aparte.

Evaluadores de código:
  estructura        hay un Dictamen válido y salió del modelo (una caída al modo código no cuenta)
  factualidad       proporción de citas que pasan el verificador y el chequeo de "no provista"
  terminologia      ids canónicos, responsable ∈ {unidad, consorcio}, sin causas físicas afirmadas en `hechos`
  recomendacion     la recomendación es la esperada y hay al menos `min_hipotesis` hipótesis
  refs_esperadas    las fuentes esperadas aparecen entre las citas
  sin_asignar       el mensaje al vecino no asigna responsabilidad ni nombra lo prohibido (otras unidades)
Jueces LLM (LLM_MODEL, fijo para todas las configuraciones; prompt en prompts/juez_mediador.v1.md):
  neutralidad       0-1
  fidelidad         proporción de hipótesis respaldadas por el texto de sus fuentes
"""
import argparse
import json
import logging
import os
import re
import sys
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from evaluation.e2e.correr import _ASIGNA, _REF, CID, _entorno_aislado, _telefono  # noqa: E402

from eliseo import config  # noqa: E402
from eliseo.schemas import Adjunto, Caso, Dictamen, EstadoCaso, ReclamoBorrador  # noqa: E402

CASOS = [json.loads(l) for l in (Path(__file__).parent / "casos.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
UMBRAL_JUEZ = 0.7
VERSION_JUEZ = "v1"
# En `hechos` van observaciones; una causa física afirmada ("proviene de la montante") es una hipótesis.
_CAUSA = re.compile(r"\b(proviene|provien|originad[oa]|se origina|causad[oa]|se debe a|por culpa|la causa)\b", re.IGNORECASE)


# ---------------------------------------------------------------- correr un caso

class _Caidas(logging.Handler):
    """Detecta cuando el nodo del Mediador cae al modo código (proxy caído o formato inválido dos veces)."""

    def __init__(self):
        super().__init__(logging.WARNING)
        self.motivos: list[str] = []

    def emit(self, record):
        self.motivos.append(record.getMessage())


def correr_caso(caso: dict) -> dict:
    from langchain_core.callbacks import get_usage_metadata_callback

    from eliseo.grafo import runtime
    from eliseo.plataforma import escritura
    from eliseo.plataforma.db import get_conn

    caidas = _Caidas()
    log_nodos = logging.getLogger("eliseo.agentes.mediador.nodos")
    log_nodos.addHandler(caidas)
    try:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            _entorno_aislado(Path(d))
            conn, tel = get_conn(), _telefono(caso["unidad"])
            unidad_id = conn.execute("SELECT unidad_id FROM unidades WHERE unidad = ?", (caso["unidad"],)).fetchone()[0]
            reclamo = ReclamoBorrador(**caso["reclamo"], fotos=[Adjunto(tipo="foto", file_id="eval")])
            registrado = escritura.registrar_caso(
                conn, Caso(consorcio_id=CID, unidad_id=unidad_id, reclamo=reclamo, estado=EstadoCaso.REGISTRADO))
            t0 = time.perf_counter()
            with get_usage_metadata_callback() as uso:
                valores = runtime.iniciar_caso(registrado.caso_id, tel)
            latencia = time.perf_counter() - t0
    finally:
        log_nodos.removeHandler(caidas)
    tokens = {m: {k: u.get(k, 0) for k in ("input_tokens", "output_tokens", "total_tokens")}
              for m, u in uso.usage_metadata.items()}
    return {
        "dictamen": valores.get("dictamen"),
        "verificacion": valores.get("verificacion") or {"ok": True, "fallas": []},
        "vueltas": valores.get("vueltas", 0),
        "documental": valores.get("documental"),
        "precedentes": valores.get("precedentes", []),
        "caidas": caidas.motivos,
        "latencia": latencia,
        "tokens": tokens,
    }


# ---------------------------------------------------------------- evaluadores de código

def _fuentes(salida: dict) -> dict[str, str]:
    """Texto de cada fuente que recibió el Mediador, por id (para el juez de fidelidad)."""
    doc = salida["documental"]
    textos = {c.referencia: c.fragmento for c in doc.citas} if doc else {}
    textos |= {p["prec_id"]: f"({p['fecha']}) {p['descripcion']} Resolución: {p['resolucion']}" for p in salida["precedentes"]}
    return textos


def evaluar(caso: dict, salida: dict) -> dict[str, float | bool | None]:
    d: Dictamen | None = salida["dictamen"]
    if d is None:
        return {"estructura": False}
    citas = [c for h in d.hipotesis for c in h.citas]
    malas = {f["cita"] for f in salida["verificacion"]["fallas"]}
    mensaje = d.mensaje_vecino
    return {
        # Salió del modelo: no hubo caída y el LLM se llamó (en MEDIADOR_MODO=codigo no hay tokens).
        "estructura": not salida["caidas"] and bool(salida["tokens"]),
        "factualidad": (sum(c not in malas for c in citas) / len(citas)) if citas else 1.0,
        "terminologia": (all(_REF.fullmatch(c) for c in citas)
                         and all(h.responsable in ("unidad", "consorcio") for h in d.hipotesis)
                         and not any(_CAUSA.search(h) for h in d.hechos)),
        "recomendacion": d.recomendacion.tipo == caso["recomendacion_esperada"] and len(d.hipotesis) >= caso["min_hipotesis"],
        "refs_esperadas": set(caso["refs_esperadas"]) <= d.todas_las_citas(),
        "sin_asignar": not _ASIGNA.search(mensaje) and not any(p in mensaje for p in caso["prohibido_en_mensaje"]),
    }


# ---------------------------------------------------------------- jueces LLM

def juez(caso: dict, salida: dict) -> dict[str, float | None]:
    from pydantic import BaseModel, Field

    from eliseo.llm import get_model
    from eliseo.prompts import cargar, escapar

    class HipotesisJuzgada(BaseModel):
        id: str
        respaldada: bool
        motivo: str

    class Veredicto(BaseModel):
        neutralidad: float = Field(ge=0, le=1)
        motivo_neutralidad: str
        hipotesis: list[HipotesisJuzgada] = Field(default_factory=list)

    d: Dictamen = salida["dictamen"]
    fuentes = _fuentes(salida)
    citadas = sorted(d.todas_las_citas())
    texto_fuentes = "\n".join(f"[{c}] {fuentes.get(c, '(no provista al Mediador)')}" for c in citadas) or "(ninguna)"
    prompt = (cargar("juez_mediador", VERSION_JUEZ)
              .replace("{reclamo}", escapar(json.dumps(caso["reclamo"], ensure_ascii=False)))
              .replace("{dictamen}", escapar(d.model_dump_json(indent=2)))
              .replace("{fuentes}", escapar(texto_fuentes)))
    v = get_model().with_structured_output(Veredicto).invoke(prompt)
    juzgadas = {h.id: h.respaldada for h in v.hipotesis}
    fidelidad = (sum(juzgadas.get(h.id, False) for h in d.hipotesis) / len(d.hipotesis)) if d.hipotesis else None
    return {"neutralidad": v.neutralidad, "fidelidad": fidelidad,
            "_motivos": {"neutralidad": v.motivo_neutralidad, **{h.id: h.motivo for h in v.hipotesis}}}


def pasa(r: dict) -> bool:
    return all((v >= UMBRAL_JUEZ if k in ("neutralidad", "fidelidad") else v == 1) for k, v in r.items()
               if v is not None and not k.startswith("_"))


# ---------------------------------------------------------------- configuración, reporte y LangSmith

def configurar(modelo: str | None, prompt: str) -> str:
    """Fija el modelo y el prompt del Mediador en el proceso (se leen del entorno en cada llamada)."""
    if modelo:
        os.environ["LLM_MODEL_REASONING"] = modelo
    else:
        os.environ.pop("LLM_MODEL_REASONING", None)
    os.environ["PROMPT_MEDIADOR_VERSION"] = prompt
    os.environ["MEDIADOR_MODO"] = os.environ.get("MEDIADOR_MODO", "agente")
    return modelo or os.environ["LLM_MODEL"]


def correr_uno(caso: dict, con_juez: bool) -> dict:
    salida = correr_caso(caso)
    r = evaluar(caso, salida)
    if con_juez and salida["dictamen"] is not None:
        r |= juez(caso, salida)
    return {"id": caso["id"], "resultado": r, "pasa": pasa(r), "vueltas": salida["vueltas"],
            "caidas": salida["caidas"], "latencia": salida["latencia"], "tokens": salida["tokens"],
            "dictamen": salida["dictamen"]}


def imprimir(filas: list[dict], modelo: str, prompt: str, detalle: bool) -> None:
    print(f"\nMediador: modelo={modelo} prompt={prompt}")
    for f in filas:
        r = {k: v for k, v in f["resultado"].items() if not k.startswith("_")}
        fallas = [k for k, v in r.items() if v is not None and not pasa({k: v})]
        print(f"  {'✓' if f['pasa'] else '✗'} {f['id']:17} vueltas={f['vueltas']} {f['latencia']:5.1f}s"
              + (f"  falla: {', '.join(fallas)}" if fallas else "") + (f"  CAÍDA: {f['caidas']}" if f["caidas"] else ""))
        if detalle and f["dictamen"]:
            d = f["dictamen"]
            print(f"      recomendación: {d.recomendacion.tipo} · hipótesis: "
                  + "; ".join(f"{h.id}={h.responsable} {h.citas}" for h in d.hipotesis))
            print("      mensaje: " + d.mensaje_vecino.replace("\n", " ")[:300])
            for k, m in (f["resultado"].get("_motivos") or {}).items():
                print(f"      juez[{k}]: {m[:200]}")
    claves = sorted({k for f in filas for k in f["resultado"] if not k.startswith("_")})
    print("  promedio por evaluador:")
    for k in claves:
        vals = [float(f["resultado"][k]) for f in filas if f["resultado"].get(k) is not None]
        print(f"    {k:15} {sum(vals) / len(vals):.3f}" if vals else f"    {k:15} -")
    tokens = [sum(u["total_tokens"] for u in f["tokens"].values()) for f in filas]
    print(f"  aprobación: {sum(f['pasa'] for f in filas)}/{len(filas)} · caídas: {sum(bool(f['caidas']) for f in filas)}"
          f" · vueltas extra: {sum(f['vueltas'] for f in filas)} · latencia media: {sum(f['latencia'] for f in filas) / len(filas):.1f}s"
          f" · tokens medios: {sum(tokens) / len(tokens):.0f}")


def subir_a_langsmith(modelo: str, prompt: str, repeticiones: int, con_juez: bool, filas: list[dict]) -> str:
    """Corre el experimento en LangSmith y deja cada corrida también en `filas`, para el reporte local."""
    from langsmith import Client, evaluate

    client, nombre = Client(), "eliseo-mediador"
    if not client.has_dataset(dataset_name=nombre):
        from langsmith.utils import LangSmithConflictError
        try:
            ds = client.create_dataset(nombre, description="Casos del Mediador (design D11 de flujo-reclamo-mediador)")
        except LangSmithConflictError:  # otra corrida en paralelo lo creó primero
            ds = None
    else:
        ds = None
    if ds is not None:
        client.create_examples(
            dataset_id=ds.id, inputs=[{"id": c["id"], "unidad": c["unidad"], "reclamo": c["reclamo"]} for c in CASOS],
            outputs=[{k: c[k] for k in ("esperado", "recomendacion_esperada", "refs_esperadas")} for c in CASOS])
    por_id = {c["id"]: c for c in CASOS}

    def objetivo(inputs: dict) -> dict:
        f = correr_uno(por_id[inputs["id"]], con_juez)
        filas.append(f)
        d = f["dictamen"]
        return {"dictamen": d.model_dump(mode="json") if d else None, "vueltas": f["vueltas"], "caidas": f["caidas"],
                "resultado": {k: v for k, v in f["resultado"].items() if not k.startswith("_")}, "pasa": f["pasa"]}

    def criterio(clave: str):
        def ev(run, example):
            v = run.outputs["resultado"].get(clave)
            return {"key": clave, "score": None if v is None else float(v)}
        return ev

    claves = ["estructura", "factualidad", "terminologia", "recomendacion", "refs_esperadas", "sin_asignar",
              *(["neutralidad", "fidelidad"] if con_juez else [])]
    res = evaluate(objetivo, data=nombre, evaluators=[criterio(c) for c in claves] + [
                       lambda run, example: {"key": "aprobado", "score": float(run.outputs["pasa"])}],
                   experiment_prefix=f"mediador-{modelo.rsplit('/', 1)[-1]}-{prompt}",
                   metadata={"modelo": modelo, "prompt": prompt, "juez": VERSION_JUEZ},
                   num_repetitions=repeticiones, max_concurrency=1)
    return res.experiment_name


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--modelo", help="LLM_MODEL_REASONING a evaluar (sin valor: LLM_MODEL, el baseline)")
    ap.add_argument("--prompt", default="v2", help="versión del prompt del Mediador")
    ap.add_argument("--repeticiones", type=int, default=3)
    ap.add_argument("--sin-juez", action="store_true")
    ap.add_argument("--casos", help="ids separados por coma (por defecto, todos)")
    ap.add_argument("--langsmith", action="store_true")
    ap.add_argument("--detalle", action="store_true")
    args = ap.parse_args()
    config._cargar()
    logging.basicConfig(level=logging.ERROR)
    modelo = configurar(args.modelo, args.prompt)
    if args.casos:
        CASOS[:] = [c for c in CASOS if c["id"] in args.casos.split(",")]

    filas: list[dict] = []
    if args.langsmith:
        experimento = subir_a_langsmith(modelo, args.prompt, args.repeticiones, not args.sin_juez, filas)
    else:
        filas = [correr_uno(c, not args.sin_juez) for c in CASOS for _ in range(args.repeticiones)]
    imprimir(sorted(filas, key=lambda f: [c["id"] for c in CASOS].index(f["id"])), modelo, args.prompt, args.detalle)
    if args.langsmith:
        print("experimento:", experimento)
