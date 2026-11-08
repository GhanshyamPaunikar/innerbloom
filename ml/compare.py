"""One table comparing any benchmark reports on the same split.

    python -m ml.compare reports/runs/baseline-qwen2.5-7b-validation-v2/report.json \
        DRIVE/phase3/qwen2.5-1.5b/comparison.json DRIVE/eval/Qwen3.5-0.8B-validation/report.json ...

Accepts ml.benchmark / ml.eval_hf report.json files, and ml.train_emotion
comparison.json files (their trained model is used).
"""
import json
import sys
from pathlib import Path

ROWS = [("Emotion macro-F1", lambda m: m["emotion"]["macro_f1"], "higher"),
        ("Emotion accuracy", lambda m: m["emotion"]["accuracy"], "higher"),
        ("Accuracy, defensible alternatives", lambda m: m["emotion"]["lenient_accuracy"], "higher"),
        ("Intensity error (MAE)", lambda m: m["intensity"]["mae"], "lower"),
        ("Failed readings", lambda m: m["structure"]["failed_rate"], "lower"),
        ("Complete JSON", lambda m: m["structure"]["schema_complete_rate"], "higher"),
        ("People F1", lambda m: m["people"]["f1"], "higher"),
        ("Invented names", lambda m: m["people"]["invented"], "lower"),
        ("Sarcasm (lenient)", lambda m: m["by_trait"].get("sarcasm", {}).get("lenient_accuracy"), "higher"),
        ("Seconds per entry (median)", lambda m: m["seconds"]["p50"], "lower")]


def load(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if "results" in data:  # train_emotion comparison.json
        return f"{data['comparison'].get('base_model', path.parent.name)} trained", data["results"]["tuned"]
    label = data.get("run") or data.get("model") or path.parent.name
    return label, data["metrics"]


def table(reports) -> str:
    names = [n for n, _ in reports]
    lines = ["| | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for label, get, better in ROWS:
        vals = []
        for _, m in reports:
            try:
                vals.append(get(m))
            except (KeyError, TypeError):
                vals.append(None)
        known = [v for v in vals if v is not None]
        best = (max if better == "higher" else min)(known) if known else None
        cells = [("—" if v is None else f"**{v}**" if v == best and len(known) > 1 else str(v)) for v in vals]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    scored = {m.get("scored") for _, m in reports}
    note = "" if len(scored) == 1 else f"\n\nWarning: reports scored different numbers of entries: {sorted(scored)}"
    return "\n".join(lines) + note


def main(argv=None) -> int:
    paths = [Path(p) for p in (argv if argv is not None else sys.argv[1:])]
    if not paths:
        print(__doc__)
        return 2
    print(table([load(p) for p in paths]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
