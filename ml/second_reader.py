"""A second person labels 100 validation entries without seeing the answers.

    python -m ml.second_reader make                    # writes the blank sheet
    python -m ml.second_reader score FILLED.csv        # compares, writes the report

`make` picks 100 entries (six of each emotion plus four more, fixed by a seed)
and writes ml/datasets/second_reader/sheet.csv with the original labels left
out. The sheet opens in Excel, Numbers or Google Sheets. HOW_TO_CHECK.md, next
to it, is the note for the person filling it in.

`score` reads the filled sheet back (CSV, in any of those apps' CSV exports)
and writes reports/second-reader-check.md: how often the two readers agree on
the feeling, how far apart their strengths are, which names differ, and every
disagreement side by side so the labels can be fixed where the second reader
is right.
"""
import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from innerbloom_core.analysis import EMOTIONS  # noqa: E402
from ml.metrics import same_person  # noqa: E402

KIT = ROOT / "ml" / "datasets" / "second_reader"
SHEET = KIT / "sheet.csv"
REPORT = ROOT / "reports" / "second-reader-check.md"
SEED = "second-reader-v1"
PER_EMOTION = 6
TOTAL = 100
COLUMNS = ["No.", "Entry", "Main feeling", "Also fits (optional)", "How strong (1-10)",
           "Names of people", "Notes (optional)", "Code (leave as is)"]


def load_validation() -> list:
    path = ROOT / "ml" / "datasets" / "splits" / "validation.jsonl"
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _key(entry: dict) -> str:
    return hashlib.sha256(f"{SEED}:{entry['id']}".encode()).hexdigest()


def pick(entries: list) -> list:
    """Six of each emotion, then the next four by the same seeded order; shuffled."""
    by_emotion = defaultdict(list)
    for e in sorted(entries, key=_key):
        by_emotion[e["emotion"]].append(e)
    chosen = [e for emo in EMOTIONS for e in by_emotion[emo][:PER_EMOTION]]
    taken = {e["id"] for e in chosen}
    chosen += [e for e in sorted(entries, key=_key) if e["id"] not in taken][:TOTAL - len(chosen)]
    return sorted(chosen, key=lambda e: _key({"id": "order:" + e["id"]}))


def make(out: Path = SHEET) -> int:
    chosen = pick(load_validation())
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as f:  # the BOM lets Excel show accents
        w = csv.writer(f)
        w.writerow(COLUMNS)
        for n, e in enumerate(chosen, 1):
            w.writerow([n, e["text"], "", "", "", "", "", e["id"]])
    print(f"wrote {len(chosen)} entries to {out}")
    return 0


def _emotion(value: str):
    v = (value or "").strip().lower()
    return v if v in EMOTIONS else None


def _emotions(value: str) -> list:
    parts = [p.strip().lower() for p in (value or "").replace(";", ",").replace("/", ",").split(",")]
    return [p for p in parts if p in EMOTIONS]


def _names(value: str) -> list:
    v = (value or "").strip()
    if v.lower() in ("", "-", "none", "no one", "nobody", "n/a"):
        return []
    return [p.strip() for p in v.replace(";", ",").split(",") if p.strip()]


def _intensity(value: str):
    try:
        n = round(float(str(value).strip()))
    except ValueError:
        return None
    return n if 1 <= n <= 10 else None


def read_sheet(path: Path) -> list:
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    col = {c.split(" (")[0].strip().lower(): c for c in (rows[0].keys() if rows else [])}
    get = lambda r, name: r.get(col.get(name, ""), "") or ""
    out = []
    for r in rows:
        out.append({"id": get(r, "code").strip(), "main_raw": get(r, "main feeling").strip(),
                    "main": _emotion(get(r, "main feeling")), "also": _emotions(get(r, "also fits")),
                    "intensity": _intensity(get(r, "how strong")), "names": _names(get(r, "names of people")),
                    "notes": get(r, "notes").strip()})
    return out


def kappa(pairs: list) -> float:
    n = len(pairs)
    if not n:
        return 0.0
    observed = sum(a == b for a, b in pairs) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    expected = sum(ca[k] * cb[k] for k in EMOTIONS) / (n * n)
    return round((observed - expected) / (1 - expected), 3) if expected < 1 else 1.0


def compare(entries: dict, answers: list) -> dict:
    rows, skipped, unknown = [], [], []
    for a in answers:
        e = entries.get(a["id"])
        if e is None:
            continue
        if not a["main_raw"]:
            skipped.append(a["id"])
            continue
        if a["main"] is None:
            unknown.append((a["id"], a["main_raw"]))
            continue
        ours = {e["emotion"], *e.get("also", [])}
        theirs = {a["main"], *a["also"]}
        missed = [p for p in e["people"] if not any(same_person(p, n) for n in a["names"])]
        allowed = e["people"] + e.get("people_optional", [])
        extra = [n for n in a["names"] if not any(same_person(n, p) for p in allowed)]
        rows.append({"id": e["id"], "text": e["text"], "ours": e["emotion"], "ours_also": e.get("also", []),
                     "theirs": a["main"], "theirs_also": a["also"], "exact": a["main"] == e["emotion"],
                     "close": bool(ours & theirs), "our_intensity": e["intensity"],
                     "their_intensity": a["intensity"], "missed": missed, "extra": extra, "notes": a["notes"]})
    gaps = [abs(r["our_intensity"] - r["their_intensity"]) for r in rows if r["their_intensity"] is not None]
    n = len(rows)
    return {
        "checked": n, "skipped": skipped, "unknown": unknown, "rows": rows,
        "exact": round(sum(r["exact"] for r in rows) / n, 3) if n else 0.0,
        "close": round(sum(r["close"] for r in rows) / n, 3) if n else 0.0,
        "kappa": kappa([(r["ours"], r["theirs"]) for r in rows]),
        "intensity_gap": round(sum(gaps) / len(gaps), 2) if gaps else None,
        "intensity_within_2": round(sum(g <= 2 for g in gaps) / len(gaps), 3) if gaps else None,
        "names_same": round(sum(not r["missed"] and not r["extra"] for r in rows) / n, 3) if n else 0.0,
    }


def verdict(k: float) -> str:
    if k >= 0.8:
        return "very strong agreement: the labels can be trusted as they are"
    if k >= 0.6:
        return "good agreement: fix the clear mistakes below and the labels hold"
    if k >= 0.4:
        return "only moderate agreement: the guidelines leave too much room; tighten them and relabel the disputed kinds"
    return "weak agreement: the labels reflect one person's reading more than a shared one"


def report(result: dict) -> str:
    r = result
    lines = ["# Second-reader check", "",
             f"A second person labelled {r['checked']} validation entries from `ml/datasets/second_reader/sheet.csv` "
             "without seeing the original labels (`python -m ml.second_reader score`).", "",
             "| | Result |", "|---|---|",
             f"| Same main feeling | {r['exact']:.0%} |",
             f"| Same, or the other's answer is listed as also fitting | {r['close']:.0%} |",
             f"| Agreement beyond chance (Cohen's kappa) | {r['kappa']} |",
             f"| Average gap in strength (1-10) | {r['intensity_gap']} |",
             f"| Strength within 2 points | {r['intensity_within_2'] if r['intensity_within_2'] is None else format(r['intensity_within_2'], '.0%')} |",
             f"| Same names | {r['names_same']:.0%} |", "",
             f"**Verdict:** {verdict(r['kappa'])}.", ""]
    if r["skipped"] or r["unknown"]:
        lines += [f"Left blank: {len(r['skipped'])}. Not one of the 16 feelings: "
                  + (", ".join(f"{i} ({v})" for i, v in r["unknown"]) or "none") + ".", ""]
    pairs = Counter((x["ours"], x["theirs"]) for x in r["rows"] if not x["exact"])
    if pairs:
        lines += ["## Where the readers differ most", "", "| Original | Second reader | Times |", "|---|---|---|"]
        lines += [f"| {a} | {b} | {c} |" for (a, b), c in pairs.most_common(10)] + [""]
    differ = [x for x in r["rows"] if not x["close"] or x["missed"] or x["extra"]
              or (x["their_intensity"] is not None and abs(x["our_intensity"] - x["their_intensity"]) > 2)]
    if differ:
        lines += ["## Entries to look at again", "",
                  "For each, decide who is right by the guidelines. If the second reader is, fix the label in "
                  "`ml/datasets/entries/`; if it is genuinely both, add their feeling to `also` and the `ambiguous` trait.", ""]
        for x in differ:
            lines.append(f"**{x['id']}**: {x['text']}")
            lines.append(f"- Feeling: original **{x['ours']}**" + (f" (also {', '.join(x['ours_also'])})" if x["ours_also"] else "")
                         + f", second reader **{x['theirs']}**" + (f" (also {', '.join(x['theirs_also'])})" if x["theirs_also"] else ""))
            lines.append(f"- Strength: original {x['our_intensity']}, second reader {x['their_intensity']}")
            if x["missed"] or x["extra"]:
                lines.append(f"- Names: second reader missed {x['missed'] or 'none'}, added {x['extra'] or 'none'}")
            if x["notes"]:
                lines.append(f"- Their note: {x['notes']}")
            lines.append("")
    return "\n".join(lines)


def score(path: Path, out: Path = REPORT) -> int:
    if not path.exists():
        print(f"No file at {path}.\nThis step is for the sheet your friend sends back. "
              f"The blank one to send them is {SHEET}")
        return 1
    entries = {e["id"]: e for e in load_validation()}
    result = compare(entries, read_sheet(path))
    if not result["checked"]:
        print("no filled-in rows found; is the 'Main feeling' column empty?")
        return 1
    out.write_text(report(result) + "\n", encoding="utf-8")
    print(f"checked {result['checked']}: same feeling {result['exact']:.0%}, close {result['close']:.0%}, "
          f"kappa {result['kappa']}, strength gap {result['intensity_gap']}\nreport: {out}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("make")
    s = sub.add_parser("score")
    s.add_argument("sheet", type=Path)
    args = ap.parse_args(argv)
    return make() if args.cmd == "make" else score(args.sheet)


if __name__ == "__main__":
    sys.exit(main())
