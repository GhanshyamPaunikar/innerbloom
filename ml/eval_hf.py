"""Score any Hugging Face model (or a local folder of weights) on the benchmark.

    python -m ml.eval_hf --model Qwen/Qwen3.5-0.8B --split validation --out DIR
    python -m ml.eval_hf --model DIR/edited --split train --limit 64 --out DIR   # quick check while editing

Same production prompt and parser as ml.benchmark, sampled at the production
temperature with a fixed seed, so results line up with the Ollama runs. Writes
DIR/<name>-<split>/predictions.jsonl (resumable) and report.json. The locked
test split needs --final.
"""
import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from innerbloom_core import analysis  # noqa: E402
from ml import benchmark, metrics  # noqa: E402

SEED = 7


def load(model_id: str):
    """Text-only loading; Qwen3.5 checkpoints also carry a vision encoder."""
    import torch
    import transformers
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(model_id)
    tok.padding_side = "left"
    kwargs = {"torch_dtype": torch.bfloat16, "device_map": "auto"}
    for name in ("AutoModelForCausalLM", "AutoModelForImageTextToText", "AutoModelForMultimodalLM"):
        cls = getattr(transformers, name, None)
        if cls is None:
            continue
        try:
            return cls.from_pretrained(model_id, **kwargs).eval(), tok
        except (ValueError, KeyError):
            continue
    raise SystemExit(f"transformers {transformers.__version__} cannot load {model_id}; install the latest.")


def prompt_text(tok, entry_text: str) -> str:
    messages = [{"role": "user", "content": analysis.build_prompt(entry_text)}]
    try:  # Qwen3-style templates: keep the model out of thinking mode
        return tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)
    except TypeError:
        return tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)


def strip_thinking(raw: str) -> str:
    return raw.split("</think>", 1)[1].strip() if "</think>" in raw else raw.strip()


def run(model_id: str, split: str, out_dir: Path, limit: int = None, batch: int = 8) -> dict:
    import torch
    from transformers import set_seed
    entries = benchmark.load_split(split)[:limit] if limit else benchmark.load_split(split)
    out_dir.mkdir(parents=True, exist_ok=True)
    pred_path = out_dir / "predictions.jsonl"
    done = {json.loads(l)["id"] for l in pred_path.read_text().splitlines() if l.strip()} if pred_path.exists() else set()
    todo = [e for e in entries if e["id"] not in done]
    if todo:
        model, tok = load(model_id)
        set_seed(SEED)
        with pred_path.open("a", encoding="utf-8") as f:
            for i in range(0, len(todo), batch):
                part = todo[i:i + batch]
                enc = tok([prompt_text(tok, e["text"]) for e in part], return_tensors="pt", padding=True).to(model.device)
                started = time.perf_counter()
                with torch.no_grad():
                    out = model.generate(**enc, max_new_tokens=256, do_sample=True,
                                         temperature=analysis.TEMPERATURE,
                                         pad_token_id=tok.pad_token_id or tok.eos_token_id)
                secs = (time.perf_counter() - started) / len(part)
                for e, ids in zip(part, out):
                    raw = strip_thinking(tok.decode(ids[enc["input_ids"].shape[1]:], skip_special_tokens=True))
                    f.write(json.dumps({"id": e["id"], "raw": raw, "seconds": round(secs, 3)}, ensure_ascii=False) + "\n")
                f.flush()
                print(f"  {len(done) + i + len(part)}/{len(entries)}")
    rows = [json.loads(l) for l in pred_path.read_text().splitlines() if l.strip()]
    preds = {r["id"]: {"raw": r["raw"], "parsed": analysis.parse(r["raw"]), "seconds": r["seconds"]} for r in rows}
    report = {"model": model_id, "runtime": "transformers bf16", "split": split, "limit": limit,
              "temperature": analysis.TEMPERATURE, "seed": SEED,
              "scored_at": datetime.now().isoformat(timespec="seconds"),
              "metrics": metrics.score(entries, preds)}
    (out_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True, help="Hugging Face id or local folder")
    ap.add_argument("--split", choices=("train", "validation", "test"), default="validation")
    ap.add_argument("--final", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--name", help="folder name for the results (default from --model)")
    ap.add_argument("--out", type=Path, default=ROOT / "reports" / "runs")
    args = ap.parse_args(argv)
    if args.split == "test" and not args.final:
        print("The test split is locked. Add --final for the one scored test run.")
        return 2
    name = args.name or Path(args.model.rstrip("/")).name
    report = run(args.model, args.split, args.out / f"{name}-{args.split}" , args.limit)
    print("\n".join(benchmark.summary_lines(report)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
