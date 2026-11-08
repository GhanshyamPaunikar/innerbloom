"""Read the model's emotion decision on training entries, without generating.

    .venv-ml/bin/python -m ml.weight_editing.probe --gguf ~/Downloads/innerbloom-reader-1.5b-f16.gguf --split train

For each entry, runs the production prompt followed by the opening of the
reply, {"emotion": ", and saves (a) the 16 emotions' first-token logits and
(b) the final normalised hidden state at that position. One forward pass per
entry; resumable. Train split only, so validation stays unseen.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from innerbloom_core.analysis import EMOTIONS, build_prompt  # noqa: E402
from ml import benchmark  # noqa: E402

PREFIX = '{"emotion": "'
SYSTEM = "You are Qwen, created by Alibaba Cloud. You are a helpful assistant."  # the Ollama template's default


def first_tokens(tok) -> list:
    base = tok(PREFIX, add_special_tokens=False)["input_ids"]
    out = []
    for e in EMOTIONS:
        ids = tok(PREFIX + e, add_special_tokens=False)["input_ids"]
        assert ids[:len(base)] == base, e
        out.append(ids[len(base)])
    assert len(set(out)) == len(out)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gguf", type=Path, required=True)
    ap.add_argument("--split", default="train", choices=("train", "validation"))
    ap.add_argument("--out", type=Path, default=ROOT / "reports" / "weight_editing")
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    dest = args.out / f"probe_{args.split}.npz"

    tok = AutoTokenizer.from_pretrained(str(args.gguf.parent), gguf_file=args.gguf.name)
    model = AutoModelForCausalLM.from_pretrained(str(args.gguf.parent), gguf_file=args.gguf.name,
                                                 dtype=torch.float16).to("mps").eval()
    ids16 = first_tokens(tok)
    entries = benchmark.load_split(args.split)
    done = dict(np.load(dest, allow_pickle=True)) if dest.exists() else {}
    keys, logits, states = (list(done["ids"]), list(done["logits"]), list(done["states"])) if done else ([], [], [])
    todo = [e for e in entries if e["id"] not in set(keys)]
    for n, e in enumerate(todo, 1):
        text = tok.apply_chat_template([{"role": "system", "content": SYSTEM},
                                        {"role": "user", "content": build_prompt(e["text"])}],
                                       tokenize=False, add_generation_prompt=True) + PREFIX
        enc = tok(text, return_tensors="pt", add_special_tokens=False).to("mps")
        with torch.no_grad():
            out = model(**enc, output_hidden_states=True)
        h = out.hidden_states[-1][0, -1]  # transformers applies the final norm to the last hidden state
        keys.append(e["id"])
        logits.append(out.logits[0, -1, ids16].float().cpu().numpy())
        states.append(h.float().cpu().numpy())
        if n % 50 == 0 or n == len(todo):
            np.savez(dest, ids=np.array(keys), logits=np.array(logits), states=np.array(states))
            print(f"  {len(keys)}/{len(entries)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
