"""Split the entries 60/20/20 into train, validation and a locked test set.

    python -m ml.split            # write ml/datasets/splits/*.jsonl and the manifest
    python -m ml.split --check    # confirm the splits match the entries and the manifest

Groups (variations of one scene) never cross splits, and every emotion is
spread across all three. The split is deterministic: the same entries always
give the same split. Near-duplicates across splits are refused.

The test split is locked: train and tune only on train and validation, and run
the benchmark on test once per finished model (python -m ml.benchmark --split test).
"""
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
SPLIT_DIR = ROOT / "ml" / "datasets" / "splits"
MANIFEST = SPLIT_DIR / "manifest.json"
sys.path.insert(0, str(ROOT))

from ml import dataset  # noqa: E402

# 60/20/20 so validation and test each hold about 25 entries per emotion: enough
# to tell a real improvement from noise. v2: re-split at 2,001 entries, before
# the test split was ever scored.
SHARES = (("train", 0.60), ("validation", 0.20), ("test", 0.20))
NEAR_DUPLICATE = 0.6  # Jaccard similarity of word trigrams


def _rank(group: str) -> str:
    return hashlib.sha256(f"innerbloom-split-v2:{group}".encode()).hexdigest()


def assign(entries: List[dict]) -> Dict[str, str]:
    """group -> split, stratified by each group's main emotion."""
    groups: Dict[str, List[dict]] = defaultdict(list)
    for e in entries:
        groups[e["group"]].append(e)
    by_emotion: Dict[str, List[str]] = defaultdict(list)
    for g, members in groups.items():
        by_emotion[members[0]["emotion"]].append(g)

    out = {}
    for emotion, gs in by_emotion.items():
        gs.sort(key=_rank)
        sizes = [len(groups[g]) for g in gs]
        total, filled = sum(sizes), 0
        bounds = [total * SHARES[0][1], total * (SHARES[0][1] + SHARES[1][1])]
        for g, size in zip(gs, sizes):
            mid = filled + size / 2
            out[g] = "train" if mid <= bounds[0] else "validation" if mid <= bounds[1] else "test"
            filled += size
    return out


def _shingles(text: str) -> set:
    words = re.findall(r"[a-z0-9']+", text.lower())
    return {" ".join(words[i:i + 3]) for i in range(max(1, len(words) - 2))}


def near_duplicates(splits: Dict[str, List[dict]]) -> List[str]:
    found = []
    names = list(splits)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            for x in splits[a]:
                sx = _shingles(x["text"])
                for y in splits[b]:
                    sy = _shingles(y["text"])
                    if len(sx) > 2 and len(sy) > 2:
                        j = len(sx & sy) / len(sx | sy)
                        if j >= NEAR_DUPLICATE:
                            found.append(f"{x['id']} ({a}) and {y['id']} ({b}) are {j:.0%} alike")
    return found


def build():
    entries = dataset.load()
    bad = dataset.problems(entries)
    if bad:
        raise SystemExit("fix the entries first:\n" + "\n".join(bad))
    where = assign(entries)
    splits = {name: [] for name, _ in SHARES}
    for e in sorted(entries, key=lambda e: e["id"]):
        clean = {k: v for k, v in e.items() if k != "_source"}
        splits[where[e["group"]]].append(clean)
    dupes = near_duplicates(splits)
    if dupes:
        raise SystemExit("near-duplicates across splits:\n" + "\n".join(dupes))
    files = {name: "\n".join(json.dumps(e, ensure_ascii=False) for e in rows) + "\n"
             for name, rows in splits.items()}
    manifest = {
        "seed": "innerbloom-split-v2",
        "shares": dict(SHARES),
        "entries": len(entries),
        "splits": {name: {"entries": len(splits[name]),
                          "groups": len({e["group"] for e in splits[name]}),
                          "sha256": hashlib.sha256(files[name].encode()).hexdigest()}
                   for name in files},
        "locked": "test",
    }
    return files, manifest


def main(argv) -> int:
    files, manifest = build()
    text = json.dumps(manifest, indent=2) + "\n"
    if "--check" in argv:
        current = MANIFEST.read_text(encoding="utf-8") if MANIFEST.exists() else ""
        on_disk = all((SPLIT_DIR / f"{n}.jsonl").exists()
                      and (SPLIT_DIR / f"{n}.jsonl").read_text(encoding="utf-8") == body
                      for n, body in files.items())
        if current != text or not on_disk:
            print("splits are out of date with the entries: run python -m ml.split")
            return 1
        print("splits match the entries and the manifest")
        return 0
    SPLIT_DIR.mkdir(parents=True, exist_ok=True)
    for name, body in files.items():
        (SPLIT_DIR / f"{name}.jsonl").write_text(body, encoding="utf-8")
    MANIFEST.write_text(text, encoding="utf-8")
    for name, info in manifest["splits"].items():
        print(f"{name:11} {info['entries']:5} entries  {info['groups']:5} groups  {info['sha256'][:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
