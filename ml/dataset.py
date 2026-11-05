"""Load and validate the fictional benchmark entries.

    python -m ml.dataset          # validate every batch in ml/datasets/entries/

Each line of a batch file is one entry (see ml/datasets/GUIDELINES.md).
Empty fields may be left out; they are filled in here.
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
ENTRIES_DIR = ROOT / "ml" / "datasets" / "entries"
sys.path.insert(0, str(ROOT))

from innerbloom_core.analysis import EMOTIONS  # noqa: E402

TRAITS = {"mixed", "negation", "sarcasm", "ambiguous", "time", "indirect",
          "factual", "names_tricky", "short", "long"}
LIST_FIELDS = ("also", "people", "people_optional", "not_people", "traits")
KNOWN = {"id", "group", "text", "emotion", "intensity", *LIST_FIELDS}


def _normalise(entry: dict) -> dict:
    out = dict(entry)
    out.setdefault("group", out.get("id"))
    for field in LIST_FIELDS:
        out.setdefault(field, [])
    return out


def load(directory: Path = ENTRIES_DIR) -> List[dict]:
    entries = []
    for path in sorted(directory.glob("*.jsonl")):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"{path.name}:{n}: not valid JSON ({e})")
            entry["_source"] = f"{path.name}:{n}"
            entries.append(_normalise(entry))
    return entries


def _mentions(text: str, name: str) -> bool:
    return re.search(r"(?<![\w])" + re.escape(name.lower()) + r"(?![\w])", text.lower()) is not None


def problems(entries: List[dict]) -> List[str]:
    found = []
    ids = Counter(e.get("id") for e in entries)
    for e in entries:
        where = f"{e['_source']} {e.get('id')}"
        unknown = set(e) - KNOWN - {"_source"}
        if unknown:
            found.append(f"{where}: unknown fields {sorted(unknown)}")
        if not re.fullmatch(r"e\d{4}", str(e.get("id", ""))):
            found.append(f"{where}: id must be e + four digits")
        if ids[e.get("id")] > 1:
            found.append(f"{where}: duplicate id")
        text = e.get("text", "")
        if not isinstance(text, str) or not text.strip():
            found.append(f"{where}: text missing")
        if e.get("emotion") not in EMOTIONS:
            found.append(f"{where}: emotion {e.get('emotion')!r} is not a production emotion")
        for alt in e["also"]:
            if alt not in EMOTIONS or alt == e.get("emotion"):
                found.append(f"{where}: bad 'also' emotion {alt!r}")
        if not isinstance(e.get("intensity"), int) or not 1 <= e["intensity"] <= 10:
            found.append(f"{where}: intensity must be an integer 1-10")
        for field in ("people", "people_optional", "not_people"):
            for name in e[field]:
                if not _mentions(text, name):
                    found.append(f"{where}: {field} {name!r} does not appear in the text")
        overlap = {n.lower() for n in e["people"]} & {n.lower() for n in e["not_people"]}
        if overlap:
            found.append(f"{where}: {sorted(overlap)} is both a person and not a person")
        for trait in e["traits"]:
            if trait not in TRAITS:
                found.append(f"{where}: unknown trait {trait!r}")
        words = len(text.split())
        if "short" in e["traits"] and words >= 15:
            found.append(f"{where}: marked short but has {words} words")
        if "long" in e["traits"] and words <= 120:
            found.append(f"{where}: marked long but has {words} words")
        if e.get("emotion") == "neutral" and e.get("intensity", 0) > 3 and "factual" in e["traits"]:
            found.append(f"{where}: factual neutral entries are intensity 1-3")
    return found


def summary(entries: List[dict]) -> Dict[str, object]:
    return {
        "entries": len(entries),
        "groups": len({e["group"] for e in entries}),
        "emotions": dict(Counter(e["emotion"] for e in entries).most_common()),
        "traits": dict(Counter(t for e in entries for t in e["traits"]).most_common()),
        "with_people": sum(1 for e in entries if e["people"]),
    }


def main() -> int:
    entries = load()
    found = problems(entries)
    for p in found:
        print(p)
    print(json.dumps(summary(entries), indent=2))
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
