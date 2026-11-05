"""Score innerbloom_core/safety.py on the locked safety cases.

    python -m ml.safety_eval              # prints the table, writes reports/safety-<date>.json

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


def main():
    rows = run(load())
    blind_rows = run(load_blind())
    result = {"date": date.today().isoformat(), "rules": "innerbloom_core/safety.py",
              "cases": str(CASES.relative_to(ROOT)), "seen": True, "metrics": score(rows),
              "blind": blind_totals(blind_rows) if blind_rows else "not written yet: see ml/datasets/blind/HOW_TO_WRITE.md",
              "rows": rows}
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
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
