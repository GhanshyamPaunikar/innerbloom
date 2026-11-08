"""Extra training examples from Meta's EmpatheticDialogues (CC BY-NC 4.0).

    python -m ml.public_data --out DIR     # downloads, maps and writes DIR/public_train.jsonl

Rashkin et al., 2019, "Towards Empathetic Open-domain Conversation Models: a
New Benchmark and Dataset", https://github.com/facebookresearch/EmpatheticDialogues.
Licensed CC BY-NC 4.0: a model trained with these examples may only be used
non-commercially. The data is downloaded at training time and never committed.

Each conversation opens with a short first-person situation labelled with one
of 32 emotions. Those that fit Innerbloom's 16 are mapped; the rest are left
out. Situations carry no intensity, summary or names, so they teach only the
emotion: the training target is the opening of the reply, {"emotion": "..."},
and the rest of the reply is learned from Innerbloom's own entries.
"""
import argparse
import hashlib
import io
import json
import sys
import tarfile
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from innerbloom_core import analysis  # noqa: E402

URL = "https://dl.fbaipublicfiles.com/parlai/empatheticdialogues/empatheticdialogues.tar.gz"
PER_EMOTION = 250
MAP = {
    "joyful": "happy", "excited": "excited", "anticipating": "excited", "proud": "proud",
    "grateful": "grateful", "content": "content", "hopeful": "hopeful",
    "sad": "sad", "devastated": "sad", "disappointed": "sad", "lonely": "lonely",
    "anxious": "anxious", "afraid": "anxious", "terrified": "anxious", "apprehensive": "anxious",
    "angry": "angry", "furious": "angry", "annoyed": "frustrated",
    "nostalgic": "reflective", "sentimental": "reflective",
}


def situations(tar_bytes: bytes) -> dict:
    """conv_id -> (label, situation text), one per conversation, all three files."""
    out = {}
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:gz") as tar:
        for name in ("train.csv", "valid.csv", "test.csv"):
            member = next(m for m in tar.getmembers() if m.name.endswith(name))
            lines = tar.extractfile(member).read().decode("utf-8").splitlines()[1:]
            for line in lines:
                parts = line.split(",")
                if len(parts) >= 4 and parts[0] not in out:
                    out[parts[0]] = (parts[2], parts[3].replace("_comma_", ",").strip())
    return out


def select(rows: dict, per_emotion: int = PER_EMOTION) -> list:
    """Map labels, drop the unmapped, and take a fixed, seeded sample per emotion."""
    by_target = defaultdict(list)
    for conv_id, (label, text) in rows.items():
        target = MAP.get(label)
        if target and len(text.split()) >= 4:
            by_target[target].append((conv_id, label, text))
    chosen = []
    for target, items in sorted(by_target.items()):
        items.sort(key=lambda r: hashlib.sha256(f"ed-v1:{r[0]}".encode()).hexdigest())
        chosen += [(target, *r) for r in items[:per_emotion]]
    return chosen


def record(target: str, conv_id: str, label: str, text: str) -> dict:
    return {"id": f"ed:{conv_id}", "source": "EmpatheticDialogues", "label": label, "partial": True,
            "messages": [{"role": "user", "content": analysis.build_prompt(text)},
                         {"role": "assistant", "content": json.dumps({"emotion": target})[:-1]}]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--per-emotion", type=int, default=PER_EMOTION)
    args = ap.parse_args(argv)
    raw = args.out / "empatheticdialogues.tar.gz"
    if not raw.exists():
        args.out.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(URL, raw)
    chosen = select(situations(raw.read_bytes()), args.per_emotion)
    path = args.out / "public_train.jsonl"
    path.write_text("\n".join(json.dumps(record(*c), ensure_ascii=False) for c in chosen) + "\n", encoding="utf-8")
    counts = defaultdict(int)
    for c in chosen:
        counts[c[0]] += 1
    print(f"wrote {len(chosen)} examples to {path}: {dict(sorted(counts.items()))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
