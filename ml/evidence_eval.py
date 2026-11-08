"""Score a judge that says whether journal entries support a claim.

    python -m ml.evidence_eval                          # qwen2.5:7b as a plain judge, validation half
    python -m ml.evidence_eval --split test --final     # the locked half, once per finished verifier

ml/datasets/evidence/claims.jsonl holds 120 fictional claims of the kind the
insight engines write, each with dated journal snippets and a label:
supported, contradicted, or insufficient (too thin, unrelated, or an
overreach such as a diagnosis). Claims that share their evidence stay in the
same half. The baseline is the production model with only the label
definitions, no tuned rules: the number a Phase 5 verifier has to beat.
"""
import argparse
import hashlib
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
CLAIMS = ROOT / "ml" / "datasets" / "evidence" / "claims.jsonl"
LABELS = ("supported", "contradicted", "insufficient")

PROMPT = """Decide whether these private journal entries support a statement written about their author.

Statement: "{claim}"

Entries:
{evidence}

Reply with ONE word:
SUPPORTED     - the entries back the statement as written
CONTRADICTED  - the entries show the statement is wrong
INSUFFICIENT  - the entries are too few, unrelated, or cannot justify the statement

Answer:"""


def load() -> list:
    return [json.loads(l) for l in CLAIMS.read_text(encoding="utf-8").splitlines() if l.strip()]


def group_of(item: dict) -> str:
    return hashlib.sha256(json.dumps(item["evidence"], sort_keys=True).encode()).hexdigest()


def split_of(item: dict) -> str:
    return "validation" if int(group_of(item)[:8], 16) % 2 == 0 else "test"


def render(item: dict) -> str:
    return PROMPT.format(claim=item["claim"], evidence="\n".join(
        f"- {e['days_ago']} days ago: {e['text']}" for e in item["evidence"]))


def parse_label(reply: str):
    word = (reply or "").strip().split()
    word = word[0].strip(".:*").lower() if word else ""
    return word if word in LABELS else None


def score(rows: list) -> dict:
    n = len(rows)
    acc = sum(r["pred"] == r["label"] for r in rows) / n
    per = {}
    for lab in LABELS:
        tp = sum(1 for r in rows if r["pred"] == lab and r["label"] == lab)
        fp = sum(1 for r in rows if r["pred"] == lab and r["label"] != lab)
        fn = sum(1 for r in rows if r["pred"] != lab and r["label"] == lab)
        p = tp / (tp + fp) if tp + fp else 0.0
        rc = tp / (tp + fn) if tp + fn else 0.0
        per[lab] = {"precision": round(p, 3), "recall": round(rc, 3),
                    "f1": round(2 * p * rc / (p + rc), 3) if p + rc else 0.0,
                    "support": tp + fn}
    not_supported = [r for r in rows if r["label"] != "supported"]
    supported = [r for r in rows if r["label"] == "supported"]
    traits = defaultdict(list)
    for r in rows:
        for t in r["traits"]:
            traits[t].append(r["pred"] == r["label"])
    return {
        "claims": n, "accuracy": round(acc, 3),
        "macro_f1": round(sum(v["f1"] for v in per.values()) / len(per), 3),
        "per_label": per,
        "unsupported_claims_accepted": round(sum(r["pred"] == "supported" for r in not_supported) / len(not_supported), 3),
        "valid_claims_rejected": round(sum(r["pred"] != "supported" for r in supported) / len(supported), 3),
        "unreadable_replies": sum(1 for r in rows if r["pred"] is None),
        "confusion": {g: dict(Counter(str(r["pred"]) for r in rows if r["label"] == g)) for g in LABELS},
        "by_trait": {t: {"accuracy": round(sum(v) / len(v), 3), "n": len(v)} for t, v in sorted(traits.items())},
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", choices=("validation", "test"), default="validation")
    ap.add_argument("--final", action="store_true")
    ap.add_argument("--model", default="qwen2.5:7b")
    ap.add_argument("--url", default="http://localhost:11434/api/generate")
    args = ap.parse_args(argv)
    if args.split == "test" and not args.final:
        print("The test half is locked. Tune on validation; add --final for the one scored test run.")
        return 2

    items = [i for i in load() if split_of(i) == args.split]
    rows = []
    for item in items:
        started = time.perf_counter()
        r = requests.post(args.url, json={"model": args.model, "prompt": render(item), "stream": False,
                                          "options": {"temperature": 0.0, "seed": 7}}, timeout=180)
        r.raise_for_status()
        reply = r.json().get("response", "")
        rows.append({"id": item["id"], "label": item["label"], "traits": item["traits"],
                     "reply": reply.strip()[:80], "pred": parse_label(reply),
                     "seconds": round(time.perf_counter() - started, 2)})
    result = {"date": date.today().isoformat(), "model": args.model, "split": args.split,
              "judge": "plain prompt with label definitions only", "metrics": score(rows), "rows": rows}
    out = ROOT / "reports" / f"evidence-{args.model.replace(':', '-')}-{args.split}-{result['date']}.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    m = result["metrics"]
    print(f"{args.model} on {m['claims']} {args.split} claims: accuracy {m['accuracy']}, macro-F1 {m['macro_f1']}")
    print(f"unsupported claims accepted {m['unsupported_claims_accepted']}, valid claims rejected {m['valid_claims_rejected']}")
    print("per label:", {k: v["recall"] for k, v in m["per_label"].items()}, "(recall)")
    print(f"wrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
