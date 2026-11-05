"""Score innerbloom_core/safety.py on the locked safety cases.

    python -m ml.safety_eval              # prints the table, writes reports/safety-<date>.json
    python -m ml.safety_eval --model qwen2.5:7b   # also asks the real classifier through Ollama

The cases in ml/datasets/safety_cases.jsonl were written separately from the
rules, then used once to find the gaps fixed on 2026-11-05: they are now a
seen set and only show regressions. ml/datasets/blind/*.txt, written by
someone who has not read the rules, is the real test. Only its totals are
ever printed or saved, so nobody can tune the rules to its sentences.

Runs with the model off (the worst case the rules must still handle) and with
a classifier that answers NONE (no help beyond what the words alone show).
"""
import json
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "ml" / "datasets" / "safety_cases.jsonl"
sys.path.insert(0, str(ROOT))

from innerbloom_core import safety  # noqa: E402


def _off(prompt):
    return "[LLM error: connection refused]"


def _none(prompt):
    return "NONE"


def load():
    return [json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines() if line.strip()]


def ollama_classifier(model: str, url: str = "http://localhost:11434/api/generate"):
    """The production classifier call (app.crisis_check: temperature 0), with a fixed seed."""
    import requests

    def classify(prompt):
        r = requests.post(url, json={"model": model, "prompt": prompt, "stream": False,
                                     "options": {"temperature": 0.0, "seed": 7}}, timeout=120)
        r.raise_for_status()
        return r.json().get("response", "")
    return classify


def run_model(cases, classify):
    rows = []
    for c in cases:
        started = time.perf_counter()
        out = safety.assess(c["text"], classify)
        rows.append({"id": c["id"], "expect": c["expect"], "model_on": out["level"] if out else None,
                     "seconds": round(time.perf_counter() - started, 2)})
    return rows


def score_model(rows):
    by = defaultdict(list)
    for r in rows:
        by[r["expect"]].append(r)

    def share(items, pred):
        return round(sum(1 for r in items if pred(r)) / len(items), 3) if items else None
    return {
        "crisis_full_help": share(by["crisis"], lambda r: r["model_on"] == "high"),
        "crisis_any_help": share(by["crisis"], lambda r: r["model_on"] is not None),
        "distress_any_help": share(by["distress"], lambda r: r["model_on"] is not None),
        "harmless_full_alarm": share(by["harmless"], lambda r: r["model_on"] == "high"),
        "harmless_any_help": share(by["harmless"], lambda r: r["model_on"] is not None),
        "everyday_any_help": share(by["everyday"], lambda r: r["model_on"] is not None),
        "seconds_mean": round(sum(r["seconds"] for r in rows) / len(rows), 2) if rows else None,
    }


def run(cases):
    rows = []
    for c in cases:
        off = safety.assess(c["text"], _off)
        calls = []
        none = safety.assess(c["text"], lambda p: calls.append(p) or "NONE")
        rows.append({"id": c["id"], "expect": c["expect"], "text": c["text"],
                     "model_off": off["level"] if off else None,
                     "classifier_none": none["level"] if none else None,
                     "asked_classifier": bool(calls)})
    return rows


def score(rows):
    by = defaultdict(list)
    for r in rows:
        by[r["expect"]].append(r)

    def share(items, pred):
        return round(sum(1 for r in items if pred(r)) / len(items), 3) if items else None

    crisis, distress, harmless, everyday = by["crisis"], by["distress"], by["harmless"], by["everyday"]
    return {
        "counts": {k: len(v) for k, v in by.items()},
        "crisis_full_help_from_words": share(crisis, lambda r: r["model_off"] == "high"),
        "crisis_any_help_model_off": share(crisis, lambda r: r["model_off"] is not None),
        "crisis_sent_to_classifier": share(crisis, lambda r: r["model_off"] == "high" or r["asked_classifier"]),
        "distress_any_help_model_off": share(distress, lambda r: r["model_off"] is not None),
        "harmless_false_full_alarm": share(harmless, lambda r: r["classifier_none"] == "high"),
        "harmless_help_shown_model_off": share(harmless, lambda r: r["model_off"] is not None),
        "everyday_help_shown_model_off": share(everyday, lambda r: r["model_off"] is not None),
        "crisis_missed_entirely_model_off": [r["id"] for r in crisis if r["model_off"] is None],
        "harmless_false_full_alarm_ids": [r["id"] for r in harmless if r["classifier_none"] == "high"],
    }


BLIND_DIR = ROOT / "ml" / "datasets" / "blind"
BLIND_FILES = {"crisis": "crisis.txt", "distress": "distress.txt", "harmless": "harmless.txt"}


def load_blind():
    cases = []
    for expect, name in BLIND_FILES.items():
        path = BLIND_DIR / name
        if path.exists():
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if line.strip():
                    cases.append({"id": f"{name}:{n}", "expect": expect, "text": line.strip()})
    return cases


def blind_totals(rows):
    """Totals only: no sentence and no line number leaves this function."""
    metrics = score(rows)
    return {k: v for k, v in metrics.items() if not k.endswith("_ids") and k != "crisis_missed_entirely_model_off"}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    model = argv[argv.index("--model") + 1] if "--model" in argv else None
    rows = run(load())
    blind_rows = run(load_blind())
    result = {"date": date.today().isoformat(), "rules": "innerbloom_core/safety.py",
              "cases": str(CASES.relative_to(ROOT)), "seen": True, "metrics": score(rows),
              "blind": blind_totals(blind_rows) if blind_rows else "not written yet: see ml/datasets/blind/HOW_TO_WRITE.md",
              "rows": rows}
    if model:
        classify = ollama_classifier(model)
        seen_model = run_model(load(), classify)
        for row, m in zip(rows, seen_model):
            row["model_on"] = m["model_on"]
        result["model"] = model
        result["metrics_model_on"] = score_model(seen_model)
        if blind_rows:
            result["blind_model_on"] = score_model(run_model(load_blind(), classify))
    out = ROOT / "reports" / f"safety-{result['date']}.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("seen set (regressions only)")
    for k, v in result["metrics"].items():
        print(f"  {k:38} {v}")
    print("blind set")
    if isinstance(result["blind"], str):
        print(f"  {result['blind']}")
    else:
        for k, v in result["blind"].items():
            print(f"  {k:38} {v}")
    if model:
        print(f"seen set with {model} answering")
        for k, v in result["metrics_model_on"].items():
            print(f"  {k:38} {v}")
        if "blind_model_on" in result:
            print(f"blind set with {model} answering")
            for k, v in result["blind_model_on"].items():
                print(f"  {k:38} {v}")
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
