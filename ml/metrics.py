"""Scores for entry analysis: emotion, intensity, structure, people, speed.

Pure functions over (entry, prediction) pairs so they can be tested without a
model. A prediction is {"raw": model reply, "parsed": analysis.parse(raw),
"seconds": float}.
"""
import json
import re
import statistics
from collections import Counter, defaultdict
from typing import Dict, List, Optional

from innerbloom_core.analysis import EMOTIONS, extract_json

FIELDS = ("emotion", "intensity", "summary", "tags", "themes", "people")


def _words(name: str) -> List[str]:
    return re.findall(r"[a-zà-ÿ0-9']+", name.lower())


def same_person(a: str, b: str) -> bool:
    """'Mr. Haddad' ~ 'Haddad', 'Uncle Raj' ~ 'Raj', case-insensitive."""
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return False
    return wa == wb or set(wa) <= set(wb) or set(wb) <= set(wa)


def _in_text(name: str, text: str) -> bool:
    words = _words(text)
    return all(w in words for w in _words(name))


def people_counts(entry: dict, predicted: List[str]) -> Dict[str, int]:
    gold, optional, not_people = entry["people"], entry["people_optional"], entry["not_people"]
    matched_gold = set()
    tp = fp = invented = wrong_kind = 0
    for p in predicted:
        hit = next((i for i, g in enumerate(gold) if i not in matched_gold and same_person(p, g)), None)
        if hit is not None:
            matched_gold.add(hit)
            tp += 1
        elif any(same_person(p, o) for o in optional):
            continue  # fine either way
        else:
            fp += 1
            if any(same_person(p, n) for n in not_people):
                wrong_kind += 1
            elif not _in_text(p, entry["text"]):
                invented += 1
    return {"tp": tp, "fp": fp, "fn": len(gold) - len(matched_gold),
            "invented": invented, "not_people": wrong_kind, "predicted": len(predicted)}


def _f1(p: float, r: float) -> float:
    return 2 * p * r / (p + r) if p + r else 0.0


def _structure(raw: str) -> Dict[str, bool]:
    try:
        direct = json.loads(raw)
        direct_ok = isinstance(direct, dict)
    except Exception:
        direct_ok = False
    data = extract_json(raw)
    complete = isinstance(data, dict) and all(k in data for k in FIELDS)
    in_list = isinstance(data, dict) and str(data.get("emotion", "")).lower().strip() in EMOTIONS
    return {"direct_json": direct_ok, "schema_complete": complete, "emotion_in_list": in_list}


def score(entries: List[dict], predictions: Dict[str, dict]) -> dict:
    pairs = [(e, predictions[e["id"]]) for e in entries if e["id"] in predictions]
    n = len(pairs)
    if not n:
        return {"scored": 0}

    # Emotion (failed readings count as wrong: they are what users would see)
    gold = [e["emotion"] for e, _ in pairs]
    pred = [p["parsed"]["emotion"] if p["parsed"]["analysis_status"] == "ok" else "<failed>"
            for _, p in pairs]
    confusion: Dict[str, Counter] = defaultdict(Counter)
    for g, p in zip(gold, pred):
        confusion[g][p] += 1
    per_class = {}
    for label in EMOTIONS:
        tp = confusion[label][label]
        fp = sum(confusion[g][label] for g in confusion if g != label)
        fn = sum(confusion[label].values()) - tp
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        per_class[label] = {"precision": round(prec, 3), "recall": round(rec, 3),
                            "f1": round(_f1(prec, rec), 3), "support": tp + fn}
    present = [l for l in EMOTIONS if per_class[l]["support"]]
    lenient = [p == e["emotion"] or p in e["also"] for (e, _), p in zip(pairs, pred)]

    # Intensity, on readings that did not fail
    errors = [abs(p["parsed"]["intensity"] - e["intensity"]) for e, p in pairs
              if p["parsed"]["analysis_status"] == "ok"]

    # Structure
    structure = [_structure(p["raw"]) for _, p in pairs]

    # People
    pc = Counter()
    for e, p in pairs:
        pc.update(people_counts(e, p["parsed"]["people"]))
    prec = pc["tp"] / (pc["tp"] + pc["fp"]) if pc["tp"] + pc["fp"] else 0.0
    rec = pc["tp"] / (pc["tp"] + pc["fn"]) if pc["tp"] + pc["fn"] else 0.0

    # By trait (lenient emotion accuracy)
    traits: Dict[str, List[bool]] = defaultdict(list)
    for (e, _), ok in zip(pairs, lenient):
        for t in e["traits"] or ["plain"]:
            traits[t].append(ok)

    seconds = sorted(p["seconds"] for _, p in pairs if p.get("seconds") is not None)

    def pct(q: float) -> Optional[float]:
        return round(seconds[min(len(seconds) - 1, int(q * len(seconds)))], 2) if seconds else None

    return {
        "scored": n,
        "emotion": {
            "accuracy": round(sum(g == p for g, p in zip(gold, pred)) / n, 3),
            "macro_f1": round(sum(per_class[l]["f1"] for l in present) / len(present), 3),
            "lenient_accuracy": round(sum(lenient) / n, 3),
            "per_class": per_class,
            "confusion": {g: dict(c) for g, c in sorted(confusion.items())},
        },
        "intensity": {
            "mae": round(statistics.mean(errors), 3) if errors else None,
            "within_1": round(sum(1 for x in errors if x <= 1) / len(errors), 3) if errors else None,
        },
        "structure": {
            "failed_rate": round(sum(1 for _, p in pairs if p["parsed"]["analysis_status"] == "failed") / n, 3),
            "direct_json_rate": round(sum(s["direct_json"] for s in structure) / n, 3),
            "schema_complete_rate": round(sum(s["schema_complete"] for s in structure) / n, 3),
            "emotion_in_list_rate": round(sum(s["emotion_in_list"] for s in structure) / n, 3),
        },
        "people": {
            "precision": round(prec, 3), "recall": round(rec, 3), "f1": round(_f1(prec, rec), 3),
            "invented": pc["invented"], "not_people_extracted": pc["not_people"],
            "predicted": pc["predicted"],
        },
        "by_trait": {t: {"lenient_accuracy": round(sum(v) / len(v), 3), "n": len(v)}
                     for t, v in sorted(traits.items())},
        "seconds": {"mean": round(statistics.mean(seconds), 2) if seconds else None,
                    "p50": pct(0.5), "p95": pct(0.95)},
    }
