"""Run a model on the benchmark entries and write a versioned report.

    python -m ml.benchmark --split validation                 # production model via local Ollama
    python -m ml.benchmark --split validation --limit 5       # smoke test
    python -m ml.benchmark --split test --final               # the locked test, once per finished model
    python -m ml.benchmark --rescore reports/runs/<run>       # recompute metrics from saved replies

Each reply is saved as it arrives in reports/runs/<run>/predictions.jsonl, so
an interrupted run continues where it stopped (same --run name). The request
matches app.call_llama for Ollama, with a fixed seed added so runs repeat.
"""
import argparse
import hashlib
import json
import platform
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from innerbloom_core import analysis  # noqa: E402
from ml import metrics  # noqa: E402

SPLIT_DIR = ROOT / "ml" / "datasets" / "splits"
RUNS_DIR = ROOT / "reports" / "runs"
SPEC = json.loads((ROOT / "ml" / "datasets" / "production_spec.json").read_text(encoding="utf-8"))


def load_split(name: str) -> list:
    path = SPLIT_DIR / f"{name}.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def ollama_generate(url: str, model: str, prompt: str, seed: int, timeout: int) -> dict:
    payload = {"model": model, "prompt": prompt, "stream": False,
               "options": {"temperature": analysis.TEMPERATURE, "seed": seed}}
    started = time.perf_counter()
    r = requests.post(url, json=payload, timeout=timeout)
    seconds = time.perf_counter() - started
    r.raise_for_status()
    body = r.json()
    return {"raw": body.get("response", "").strip(), "seconds": round(seconds, 3),
            "eval_count": body.get("eval_count"), "prompt_eval_count": body.get("prompt_eval_count")}


def _read_predictions(path: Path) -> dict:
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            out[row["id"]] = row
    return out


def _report(run_dir: Path, meta: dict, entries: list) -> dict:
    rows = _read_predictions(run_dir / "predictions.jsonl")
    preds = {i: {"raw": r["raw"], "parsed": analysis.parse(r["raw"]), "seconds": r.get("seconds")}
             for i, r in rows.items()}
    report = {**meta, "scored_at": datetime.now().isoformat(timespec="seconds"),
              "metrics": metrics.score(entries, preds)}
    (run_dir / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def summary_lines(report: dict) -> list:
    m = report["metrics"]
    if not m.get("scored"):
        return ["nothing scored yet"]
    e, s, p, t = m["emotion"], m["structure"], m["people"], m["seconds"]
    return [
        f"{report['model']} on {report['split']}: {m['scored']} entries",
        f"emotion   macro-F1 {e['macro_f1']}  accuracy {e['accuracy']}  lenient {e['lenient_accuracy']}",
        f"intensity MAE {m['intensity']['mae']}  within 1: {m['intensity']['within_1']}",
        f"structure failed {s['failed_rate']}  direct JSON {s['direct_json_rate']}  complete {s['schema_complete_rate']}",
        f"people    precision {p['precision']}  recall {p['recall']}  invented {p['invented']}  non-people {p['not_people_extracted']}",
        f"speed     mean {t['mean']}s  p50 {t['p50']}s  p95 {t['p95']}s per entry",
    ]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", choices=("train", "validation", "test"), default="validation")
    ap.add_argument("--final", action="store_true", help="required to run on the locked test split")
    ap.add_argument("--model", default=SPEC["model"])
    ap.add_argument("--ollama-url", default="http://localhost:11434/api/generate")
    ap.add_argument("--limit", type=int, help="first N entries only (smoke test)")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--run", help="run name; reuse it to resume")
    ap.add_argument("--rescore", type=Path, help="recompute report.json for an existing run folder")
    args = ap.parse_args(argv)

    if args.rescore:
        meta = json.loads((args.rescore / "meta.json").read_text(encoding="utf-8"))
        entries = load_split(meta["split"])
        if meta.get("limit"):
            entries = entries[:meta["limit"]]
        print("\n".join(summary_lines(_report(args.rescore, meta, entries))))
        return 0

    if args.split == "test" and not args.final:
        print("The test split is locked. Tune on validation; add --final for the one scored test run.")
        return 2

    entries = load_split(args.split)
    if args.limit:
        entries = entries[:args.limit]
    safe_model = args.model.replace(":", "-").replace("/", "-")
    run = args.run or f"{datetime.now():%Y%m%d-%H%M}-{safe_model}-{args.split}" + (f"-n{args.limit}" if args.limit else "")
    run_dir = RUNS_DIR / run
    run_dir.mkdir(parents=True, exist_ok=True)
    split_text = (SPLIT_DIR / f"{args.split}.jsonl").read_text(encoding="utf-8")
    meta = {
        "run": run, "model": args.model, "provider": "ollama", "split": args.split, "limit": args.limit,
        "seed": args.seed, "temperature": analysis.TEMPERATURE,
        "prompt_sha256": hashlib.sha256(analysis.build_prompt("<<ENTRY>>").encode()).hexdigest(),
        "spec_prompt_sha256": SPEC["prompt_sha256"],
        "split_sha256": hashlib.sha256(split_text.encode()).hexdigest(),
        "machine": f"{platform.system()} {platform.machine()} {platform.processor()}".strip(),
        "started": datetime.now().isoformat(timespec="seconds"),
    }
    if meta["prompt_sha256"] != meta["spec_prompt_sha256"]:
        print("The prompt differs from ml/datasets/production_spec.json: run python -m ml.spec first.")
        return 2
    meta_path = run_dir / "meta.json"
    if meta_path.exists():
        old = json.loads(meta_path.read_text(encoding="utf-8"))
        for key in ("model", "split", "seed", "prompt_sha256", "split_sha256"):
            if old.get(key) != meta[key]:
                print(f"Run {run} was started with a different {key}; use a new --run name.")
                return 2
        meta["started"] = old["started"]
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    pred_path = run_dir / "predictions.jsonl"
    done = _read_predictions(pred_path)
    todo = [e for e in entries if e["id"] not in done]
    print(f"run {run}: {len(done)} done, {len(todo)} to go")
    with pred_path.open("a", encoding="utf-8") as out:
        for i, e in enumerate(todo, 1):
            try:
                reply = ollama_generate(args.ollama_url, args.model, analysis.build_prompt(e["text"]),
                                        args.seed, args.timeout)
            except requests.RequestException as err:
                print(f"stopped at {e['id']}: {err}\nIs Ollama running with {args.model} pulled? "
                      f"Re-run with --run {run} to continue.")
                break
            out.write(json.dumps({"id": e["id"], **reply}, ensure_ascii=False) + "\n")
            out.flush()
            if i % 10 == 0 or i == len(todo):
                print(f"  {len(done) + i}/{len(entries)}  last {reply['seconds']}s")

    report = _report(run_dir, meta, entries)
    print("\n".join(summary_lines(report)))
    path = run_dir / "report.json"
    print(f"report: {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
