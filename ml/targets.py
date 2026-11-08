"""Training targets for the emotion model: the reply we want for each entry.

The labels cover emotion, intensity and people, but the production schema
also asks for a summary, tags and themes. A model trained without those would
stop writing them. So each target starts from the base model's own reply for
that entry (its summary, tags and themes) and replaces the labelled fields
with the labels. The base replies come from `ml.benchmark` (on this Mac) or
`ml.train_emotion --stage replies` (on Colab), in the same predictions format.

    python -m ml.targets --split train --replies reports/runs/<run>/predictions.jsonl
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from innerbloom_core import analysis  # noqa: E402
from ml import metrics  # noqa: E402

OUT_DIR = ROOT / "ml" / "datasets" / "targets"


def target_reply(entry: dict, base_raw: str) -> str:
    """The reply to train on, as compact JSON in the production field order."""
    base = analysis.parse(base_raw) if base_raw else None
    usable = base is not None and base["analysis_status"] == "ok"
    people = list(entry["people"])
    if usable:
        # Keep optional mentions ("my sister") only when the base model chose them.
        for name in base["people"]:
            if any(metrics.same_person(name, o) for o in entry["people_optional"]) \
                    and not any(metrics.same_person(name, p) for p in people):
                people.append(name)
    target = {
        "emotion": entry["emotion"],
        "intensity": entry["intensity"],
        "summary": base["summary"] if usable else "",
        "tags": base["tags"] if usable else [],
        "themes": base["themes"] if usable else [],
        "people": people[:6],
    }
    return json.dumps(target, ensure_ascii=False, separators=(", ", ": "))


def chat_record(entry: dict, base_raw: str) -> dict:
    """One training example in chat form: the production prompt as the user
    turn (Ollama sends it that way) and the target as the assistant turn."""
    return {"id": entry["id"], "messages": [
        {"role": "user", "content": analysis.build_prompt(entry["text"])},
        {"role": "assistant", "content": target_reply(entry, base_raw)},
    ]}


def build(entries: list, replies: dict) -> list:
    missing = [e["id"] for e in entries if e["id"] not in replies]
    if missing:
        raise ValueError(f"{len(missing)} entries have no base reply, first: {missing[:3]}")
    return [chat_record(e, replies[e["id"]]) for e in entries]


def read_replies(path: Path) -> dict:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            out[row["id"]] = row["raw"]
    return out


def main(argv=None) -> int:
    from ml import benchmark
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", choices=("train", "validation"), required=True)
    ap.add_argument("--replies", type=Path, required=True)
    args = ap.parse_args(argv)
    records = build(benchmark.load_split(args.split), read_replies(args.replies))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{args.split}.jsonl"
    out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n", encoding="utf-8")
    print(f"wrote {len(records)} examples to {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
