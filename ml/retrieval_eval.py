"""Score Innerbloom's memory search on fictional journals with known answers.

    python -m ml.retrieval_eval                    # keyword search, validation journals (a, b)
    python -m ml.retrieval_eval --system all       # also meaning search (needs mxbai-embed-large in Ollama)
    python -m ml.retrieval_eval --split test --final --system all   # journal c, once per finished system

Each question lists the entries that answer it (2 = answers it, 1 = related).
Dates are stored as days before today, so "the last two weeks" always means
the same entries. Searches run through the app's own functions:
retrieve_relevant (keyword), retrieve_similar (meaning, with recency and
diversity) and the chat agent's search tool (meaning, then keyword).
"""
import argparse
import json
import math
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "ml" / "datasets" / "retrieval"
sys.path.insert(0, str(ROOT))

SPLITS = {"validation": ("a", "b"), "test": ("c",)}
K = 5


def load_journal(name: str, now: datetime) -> list:
    rows = [json.loads(l) for l in (DATA / f"journal_{name}.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    for r in rows:
        ts = (now - timedelta(days=r["days_ago"])).replace(hour=12, minute=0, second=0, microsecond=0)
        r["timestamp"] = ts.isoformat()
    return rows


def load_queries(journals) -> list:
    rows = [json.loads(l) for l in (DATA / "queries.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    return [q for q in rows if q["journal"] in journals]


def score_query(q: dict, ranked: list, days_ago: dict) -> dict:
    top = ranked[:K]
    rel = q["relevant"]
    found = [i for i in top if i in rel]
    first = next((n for n, i in enumerate(top, 1) if i in rel), None)
    dcg = sum((2 ** rel.get(i, 0) - 1) / math.log2(n + 1) for n, i in enumerate(top, 1))
    ideal = sorted(rel.values(), reverse=True)[:K]
    idcg = sum((2 ** g - 1) / math.log2(n + 1) for n, g in enumerate(ideal, 1))
    out = {"id": q["id"], "top": top,
           "recall": len(found) / len(rel),
           "answer_found": any(rel[i] == 2 for i in found),
           "mrr": 1 / first if first else 0.0,
           "ndcg": dcg / idcg if idcg else 0.0}
    if q.get("window") and top:
        lo, hi = q["window"]
        out["in_window"] = sum(1 for i in top if lo <= days_ago[i] <= hi) / len(top)
    return out


def summarise(rows: list) -> dict:
    def mean(key, items=rows):
        vals = [r[key] for r in items if key in r]
        return round(sum(vals) / len(vals), 3) if vals else None
    return {"questions": len(rows), f"recall@{K}": mean("recall"),
            f"answer_in_top{K}": mean("answer_found"), "mrr": mean("mrr"), f"ndcg@{K}": mean("ndcg"),
            "temporal_in_window": mean("in_window")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", choices=SPLITS, default="validation")
    ap.add_argument("--final", action="store_true")
    ap.add_argument("--system", choices=("keyword", "all"), default="keyword")
    args = ap.parse_args(argv)
    if args.split == "test" and not args.final:
        print("Journal c is locked. Tune on validation; add --final for the one scored test run.")
        return 2

    os.environ.setdefault("INNERBLOOM_DATA_DIR", tempfile.mkdtemp(prefix="innerbloom_retrieval_"))
    import app  # noqa: E402

    now = datetime.now()
    systems = {"keyword": lambda q, es: app.retrieve_relevant(es, q, k=K)}
    if args.system == "all":
        probe = app.embed("test")
        if not probe:
            print(f"Meaning search needs the embedding model: ollama pull {app.EMBED_MODEL}")
            return 2
        systems["meaning"] = lambda q, es: app.retrieve_similar(q, es, k=K)
        systems["agent_search"] = lambda q, es: app.retrieve_similar(q, es, k=K) or app.retrieve_relevant(es, q, k=K)

    results, per_query = {}, {}
    journals = {name: load_journal(name, now) for name in SPLITS[args.split]}
    if args.system == "all":
        for entries in journals.values():
            for e in entries:
                e["embedding"] = app.embed(app._entry_embed_text(e))
                e["embedding_version"] = app.EMBED_VERSION
                app._embed_entry_chunks(e)
    queries = load_queries(SPLITS[args.split])
    for name, search in systems.items():
        rows = []
        for q in queries:
            entries = journals[q["journal"]]
            days_ago = {e["id"]: e["days_ago"] for e in entries}
            ranked = [e["id"] for e in search(q["query"], entries)]
            row = score_query(q, ranked, days_ago)
            row["traits"] = q["traits"]
            rows.append(row)
        by_trait = {}
        for t in sorted({t for r in rows for t in r["traits"]}):
            by_trait[t] = summarise([r for r in rows if t in r["traits"]])
        results[name] = {"overall": summarise(rows), "by_trait": by_trait}
        per_query[name] = rows

    report = {"date": now.date().isoformat(), "split": args.split, "k": K,
              "embed_model": app.EMBED_MODEL if args.system == "all" else None,
              "note": "entries carry text only (no summary/tags), as if analysis were unavailable",
              "results": results, "per_query": per_query}
    out = ROOT / "reports" / f"retrieval-{args.split}-{now.date().isoformat()}.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for name, r in results.items():
        print(name, r["overall"])
    print(f"wrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
