"""Fit one logit offset per emotion that corrects the model's bias, from training readings only.

    .venv-ml/bin/python -m ml.weight_editing.fit

Coordinate ascent on macro-F1 over the 16 first-token logits saved by probe.py.
Offsets are checked with 5-fold cross-validation inside the training split, so
the reported gain is on training entries the offsets were not fitted to.
Writes reports/weight_editing/offsets.json.
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from innerbloom_core.analysis import EMOTIONS  # noqa: E402

GRID = np.round(np.arange(-3.0, 3.01, 0.25), 2)


def macro_f1(pred, y):
    scores = []
    for k in range(len(EMOTIONS)):
        tp = np.sum((pred == k) & (y == k))
        fp = np.sum((pred == k) & (y != k))
        fn = np.sum((pred != k) & (y == k))
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        scores.append(2 * p * r / (p + r) if p + r else 0.0)
    return float(np.mean(scores))


def fit(L, y, rounds=4):
    b = np.zeros(L.shape[1])
    for _ in range(rounds):
        for k in range(L.shape[1]):
            best, best_v = macro_f1((L + b).argmax(1), y), b[k]
            for v in GRID:
                b[k] = v
                s = macro_f1((L + b).argmax(1), y)
                if s > best + 1e-9:
                    best, best_v = s, v
            b[k] = best_v
    return b


def main() -> int:
    d = np.load(ROOT / "reports" / "weight_editing" / "probe_train.npz")
    ids, L = d["ids"], d["logits"].astype(np.float64)
    lab = {json.loads(l)["id"]: json.loads(l) for l in (ROOT / "ml/datasets/splits/train.jsonl").read_text().splitlines() if l}
    y = np.array([EMOTIONS.index(lab[i]["emotion"]) for i in ids])

    folds = np.arange(len(y)) % 5
    np.random.default_rng(7).shuffle(folds)
    before, after = [], []
    for f in range(5):
        tr, te = folds != f, folds == f
        b = fit(L[tr], y[tr])
        before.append(macro_f1(L[te].argmax(1), y[te]))
        after.append(macro_f1((L[te] + b).argmax(1), y[te]))
    b = fit(L, y)
    result = {"entries": int(len(y)),
              "cv_macro_f1_before": round(float(np.mean(before)), 3),
              "cv_macro_f1_after": round(float(np.mean(after)), 3),
              "offsets": {e: float(v) for e, v in zip(EMOTIONS, b)},
              "picks_before": {e: int(((L.argmax(1)) == k).sum()) for k, e in enumerate(EMOTIONS)},
              "picks_after": {e: int(((L + b).argmax(1) == k).sum()) for k, e in enumerate(EMOTIONS)}}
    out = ROOT / "reports" / "weight_editing" / "offsets.json"
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
