"""Phase 3: fine-tune a small Qwen2.5 model with QLoRA to read journal entries.

Innerbloom's entry reading is one fixed job (one JSON format, 16 emotions),
so the aim is a light model that matches the 7B production model on it while
running fast on an ordinary laptop. --base picks the size; 1.5B is the main
candidate, 3B and 0.5B are for comparison.

Run on a Colab GPU, one stage at a time, from notebooks/02_emotion_training.ipynb:

    python -m ml.train_emotion --stage check      # GPU, libraries, data (seconds)
    python -m ml.train_emotion --stage replies    # the 7B writes summaries/tags/themes for the targets
    python -m ml.train_emotion --stage smoke --base 1.5b   # 10 steps, save, reload, read 3 entries
    python -m ml.train_emotion --stage train --base 1.5b   # the real run, validation-checked, resumable
    python -m ml.train_emotion --stage evaluate --base 1.5b  # untrained vs trained, same 4-bit setup

Everything a stage produces goes to --out (Google Drive on Colab), so a
disconnected runtime loses nothing: every stage continues where it stopped.
The locked test split is never touched here.
"""
import argparse
import json
import random
import os
import re
import sys
from collections import Counter
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from innerbloom_core import analysis  # noqa: E402
from ml import benchmark, metrics, targets  # noqa: E402

BASES = {  # Hugging Face model and the matching Ollama tag
    "0.5b": ("Qwen/Qwen2.5-0.5B-Instruct", "qwen2.5:0.5b"),
    "1.5b": ("Qwen/Qwen2.5-1.5B-Instruct", "qwen2.5:1.5b"),
    "3b": ("Qwen/Qwen2.5-3B-Instruct", "qwen2.5:3b"),  # Qwen research licence: check before shipping
    "7b": ("Qwen/Qwen2.5-7B-Instruct", "qwen2.5:7b"),   # what production uses
}
TEACHER = "7b"  # writes the summaries, tags and themes the small models learn from
BASE_MODEL = BASES[TEACHER][0]
SEED = 7
UNITS_PER_HOUR = 8.88  # last observed A100 rate; check Colab's resource panel

CONFIG = {
    "lora_r": 16, "lora_alpha": 32, "lora_dropout": 0.05,
    "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    "max_length": 1024, "learning_rate": 2e-4, "per_device_batch": 4, "grad_accum": 4,  # effective 16
    "max_epochs": 3, "warmup_ratio": 0.05, "eval_every_steps": 20, "early_stop_patience": 4,
    # The feeling and its strength are about 2 of the ~55 reply tokens; the rest
    # copies the 7B's summary, tags and themes. These weights make them count,
    # and the feeling's weight is balanced by how common it is in training, so
    # a common feeling (happy, 9% of train) doesn't become the default answer.
    "emotion_weight": 5.0, "intensity_weight": 3.0, "class_weight_range": (0.5, 2.0),
    # The best checkpoint is the one that reads feelings best on validation
    # (macro-F1 from a short greedy generation), not the lowest overall loss.
    "select_by": "eval_macro_f1", "f1_max_new_tokens": 10, "f1_batch": 32,
    "smoke_steps": 10, "smoke_examples": 64,
    "gen_max_new_tokens": 256, "gen_batch": 8, "temperature": analysis.TEMPERATURE,
}


# ---------------------------------------------------------------- helpers

def log(out: Path, stage: str, **fields):
    row = {"at": datetime.now().isoformat(timespec="seconds"), "stage": stage, **fields}
    with (out / "log.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    print(json.dumps(row))


def read_jsonl(path: Path) -> list:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


_EMOTION_VALUE = re.compile(r'"emotion"\s*:\s*"([^"]*)"')
_INTENSITY_VALUE = re.compile(r'"intensity"\s*:\s*"?(\d+)')


def class_weights(records: list) -> dict:
    """emotion -> weight, so every feeling counts about equally in the loss
    however often it appears in training. Clipped to class_weight_range."""
    counts = Counter(m.group(1) for r in records
                     for m in [_EMOTION_VALUE.search(r["messages"][1]["content"])] if m)
    if not counts:
        return {}
    mean = sum(counts.values()) / len(counts)
    lo, hi = CONFIG["class_weight_range"]
    return {e: round(min(hi, max(lo, mean / n)), 3) for e, n in counts.items()}


def token_weights(answer: str, offsets: list, weights_by_emotion: dict = None) -> list:
    """One loss weight per reply token: 1, or more for the tokens that spell
    the feeling and the intensity (found by character position)."""
    spans = []
    m = _EMOTION_VALUE.search(answer)
    if m:
        w = CONFIG["emotion_weight"] * (weights_by_emotion or {}).get(m.group(1), 1.0)
        spans.append((m.start(1), m.end(1), w))
    m = _INTENSITY_VALUE.search(answer)
    if m:
        spans.append((m.start(1), m.end(1), CONFIG["intensity_weight"]))
    out = []
    for start, end in offsets:
        w = 1.0
        for s0, s1, sw in spans:
            if start < s1 and end > s0:  # the token overlaps the value
                w = max(w, sw)
        out.append(w)
    return out


def encode(tokenizer, record: dict, max_length: int, weights_by_emotion: dict = None) -> dict:
    """Token ids for one example; only the assistant reply is learned, with the
    feeling and intensity weighted (see token_weights)."""
    prompt = tokenizer.apply_chat_template(record["messages"][:1], tokenize=False, add_generation_prompt=True)
    # Public examples teach only the opening {"emotion": "..."}: no end token,
    # so the model never learns to stop there.
    answer = record["messages"][1]["content"] + ("" if record.get("partial") else "<|im_end|>")
    p_ids = tokenizer(prompt, add_special_tokens=False)["input_ids"]
    a = tokenizer(answer, add_special_tokens=False, return_offsets_mapping=True)
    a_ids = a["input_ids"]
    a_w = token_weights(answer, a["offset_mapping"], weights_by_emotion)
    ids = (p_ids + a_ids)[:max_length]
    labels = ([-100] * len(p_ids) + a_ids)[:max_length]
    loss_weights = ([0.0] * len(p_ids) + a_w)[:max_length]
    return {"input_ids": ids, "attention_mask": [1] * len(ids), "labels": labels,
            "loss_weights": loss_weights}


def pad_batch(features: list, pad_id: int) -> dict:
    """Right-pad a batch: ids with pad_id, labels with -100, weights with 0."""
    import torch
    n = max(len(f["input_ids"]) for f in features)

    def col(key, fill, dtype):
        return torch.tensor([f[key] + [fill] * (n - len(f[key])) for f in features], dtype=dtype)
    return {"input_ids": col("input_ids", pad_id, torch.long),
            "attention_mask": col("attention_mask", 0, torch.long),
            "labels": col("labels", -100, torch.long),
            "loss_weights": col("loss_weights", 0.0, torch.float32)}


def weighted_loss(logits, labels, weights):
    """Next-token cross-entropy, as a weighted mean over the learned tokens."""
    import torch.nn.functional as F
    logits, labels, weights = logits[:, :-1, :].float(), labels[:, 1:], weights[:, 1:]
    ce = F.cross_entropy(logits.reshape(-1, logits.size(-1)), labels.reshape(-1),
                         ignore_index=-100, reduction="none").view(labels.shape)
    w = weights * (labels != -100).float()
    return (ce * w).sum() / w.sum().clamp(min=1e-6)


def macro_f1(gold: list, pred: list) -> float:
    """Macro-F1 over the feelings present in gold, like ml.metrics.score."""
    labels = sorted(set(gold))
    scores = []
    for label in labels:
        tp = sum(1 for g, p in zip(gold, pred) if g == label and p == label)
        fp = sum(1 for g, p in zip(gold, pred) if g != label and p == label)
        fn = sum(1 for g, p in zip(gold, pred) if g == label and p != label)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        scores.append(2 * prec * rec / (prec + rec) if prec + rec else 0.0)
    return round(sum(scores) / len(scores), 4) if scores else 0.0


def first_emotion(raw: str) -> str:
    m = _EMOTION_VALUE.search(raw or "") or re.search(r'"emotion"\s*:\s*"([a-z]+)', raw or "")
    return m.group(1).strip().lower() if m else "<failed>"


def validation_macro_f1(model, tok, entries: list) -> float:
    """Greedy, a few tokens each: enough to read the feeling the model chose."""
    import torch
    was_training, side = model.training, tok.padding_side
    model.eval()
    tok.padding_side = "left"
    preds = []
    try:
        for i in range(0, len(entries), CONFIG["f1_batch"]):
            batch = entries[i:i + CONFIG["f1_batch"]]
            prompts = [tok.apply_chat_template([{"role": "user", "content": analysis.build_prompt(e["text"])}],
                                               tokenize=False, add_generation_prompt=True) for e in batch]
            enc = tok(prompts, return_tensors="pt", padding=True).to(model.device)
            with torch.no_grad():
                out = model.generate(**enc, max_new_tokens=CONFIG["f1_max_new_tokens"], do_sample=False,
                                     use_cache=True, pad_token_id=tok.pad_token_id or tok.eos_token_id)
            preds += [first_emotion(tok.decode(ids[enc["input_ids"].shape[1]:], skip_special_tokens=True))
                      for ids in out]
    finally:
        tok.padding_side = side
        model.train(was_training)
    return macro_f1([e["emotion"] for e in entries], preds)


def load_model(adapter: Path = None, train: bool = False, base: str = TEACHER):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    model_id = BASES[base][0]
    tok = AutoTokenizer.from_pretrained(model_id)
    tok.padding_side = "left"
    quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                               bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True)
    model = AutoModelForCausalLM.from_pretrained(model_id, quantization_config=quant,
                                                 torch_dtype=torch.bfloat16, device_map="auto")
    if train:
        from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
        model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
        model = get_peft_model(model, LoraConfig(
            r=CONFIG["lora_r"], lora_alpha=CONFIG["lora_alpha"], lora_dropout=CONFIG["lora_dropout"],
            target_modules=CONFIG["target_modules"], task_type="CAUSAL_LM"))
        model.print_trainable_parameters()
    elif adapter:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, str(adapter))
    model.eval() if not train else model.train()
    return model, tok


def generate(model, tok, entries: list, out_path: Path, sample: bool):
    """Read entries in batches, appending {"id", "raw", "seconds"} rows; resumes."""
    import torch
    from transformers import set_seed
    done = {r["id"] for r in read_jsonl(out_path)}
    todo = [e for e in entries if e["id"] not in done]
    set_seed(SEED)
    with out_path.open("a", encoding="utf-8") as f:
        for i in range(0, len(todo), CONFIG["gen_batch"]):
            batch = todo[i:i + CONFIG["gen_batch"]]
            prompts = [tok.apply_chat_template([{"role": "user", "content": analysis.build_prompt(e["text"])}],
                                               tokenize=False, add_generation_prompt=True) for e in batch]
            enc = tok(prompts, return_tensors="pt", padding=True).to(model.device)
            started = time.perf_counter()
            options = {"do_sample": True, "temperature": CONFIG["temperature"]} if sample else {"do_sample": False}
            with torch.no_grad():
                out = model.generate(**enc, max_new_tokens=CONFIG["gen_max_new_tokens"],
                                     pad_token_id=tok.pad_token_id or tok.eos_token_id, **options)
            seconds = (time.perf_counter() - started) / len(batch)
            for e, ids in zip(batch, out):
                raw = tok.decode(ids[enc["input_ids"].shape[1]:], skip_special_tokens=True).strip()
                f.write(json.dumps({"id": e["id"], "raw": raw, "seconds": round(seconds, 3)}, ensure_ascii=False) + "\n")
            f.flush()
            print(f"  {len(done) + i + len(batch)}/{len(entries)}")


# ---------------------------------------------------------------- stages

def stage_check(out: Path, base: str):
    import torch
    import transformers, peft, bitsandbytes, accelerate  # noqa: E401
    from ml import dataset, spec, split
    if not torch.cuda.is_available():
        raise SystemExit("No GPU. Runtime > Change runtime type > A100 GPU, then run again.")
    name = torch.cuda.get_device_name(0)
    vram = torch.cuda.get_device_properties(0).total_memory / 2 ** 30
    problems = dataset.problems(dataset.load_all())
    if problems:
        raise SystemExit("Dataset problems:\n" + "\n".join(problems[:10]))
    if split.main(["--check"]) != 0 or spec.main(["--check"]) != 0:
        raise SystemExit("Splits or production spec are out of date in this checkout.")
    log(out, "check", gpu=name, vram_gb=round(vram, 1), torch=torch.__version__,
        transformers=transformers.__version__, peft=peft.__version__,
        bitsandbytes=bitsandbytes.__version__, accelerate=accelerate.__version__,
        train=len(benchmark.load_split("train")), validation=len(benchmark.load_split("validation")))
    if vram < 39:
        print(f"Warning: {name} has {vram:.0f} GB. The settings assume an A100 (40 or 80 GB).")
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(BASE_MODEL)
    longest = max(len(tok.apply_chat_template([{"role": "user", "content": analysis.build_prompt(e["text"])}],
                                              tokenize=True, add_generation_prompt=True))
                  for e in benchmark.load_split("train") + benchmark.load_split("validation"))
    room = CONFIG["max_length"] - longest
    log(out, "check_lengths", longest_prompt_tokens=longest, room_for_reply=room)
    if room < 200:
        raise SystemExit(f"The longest prompt leaves only {room} tokens for the reply: raise max_length.")


def stage_replies(out: Path, base: str):
    """The 7B's replies for train and validation, then targets for both.
    Shared by every size, so it runs once."""
    model, tok = load_model(base=TEACHER)
    for split in ("train", "validation"):
        entries = benchmark.load_split(split)
        path = out / f"base_replies_{split}.jsonl"
        started = time.time()
        generate(model, tok, entries, path, sample=False)
        records = targets.build(entries, {r["id"]: r["raw"] for r in read_jsonl(path)})
        failed = sum(1 for r in read_jsonl(path) if analysis.parse(r["raw"])["analysis_status"] == "failed")
        tpath = out / f"targets_{split}.jsonl"
        tpath.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n", encoding="utf-8")
        log(out, "replies", split=split, examples=len(records), base_failed=failed,
            minutes=round((time.time() - started) / 60, 1))


WITH_PUBLIC = False  # set by --with-public: add ml.public_data examples to training
TAG = ""  # set by --tag: keeps a later round's model apart from earlier ones


def _base_dir(out: Path, base: str) -> Path:
    path = out / (f"qwen2.5-{base}-{TAG}" if TAG else f"qwen2.5-{base}")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _datasets(out: Path, tok, limit: int = None):
    """Encoded train and validation examples, and the per-feeling weights."""
    train = read_jsonl(out / "targets_train.jsonl")
    val = read_jsonl(out / "targets_validation.jsonl")
    if not train or not val:
        raise SystemExit("Run --stage replies first.")
    if WITH_PUBLIC:
        public = read_jsonl(out / "public_train.jsonl")
        if not public:
            raise SystemExit("Run --stage public first.")
        train = train + public
        random.Random(SEED).shuffle(train)
    if limit:
        train, val = train[:limit], val[:16]
    weights = class_weights(train)
    return ([encode(tok, r, CONFIG["max_length"], weights) for r in train],
            [encode(tok, r, CONFIG["max_length"], weights) for r in val], weights)


def _trainer(model, tok, train_ds, val_ds, out_dir: Path, max_steps: int = -1, f1_entries: list = None):
    from transformers import EarlyStoppingCallback, Trainer, TrainerCallback, TrainingArguments, set_seed
    set_seed(SEED)

    class WeightedTrainer(Trainer):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            # compute_loss averages each micro-batch itself, so Trainer must still
            # divide by gradient_accumulation_steps. It skips that when it thinks
            # the model's own loss takes num_items_in_batch (Qwen2 does), which
            # made the logged loss and the gradients 4 times too big.
            self.model_accepts_loss_kwargs = False

        def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
            labels, weights = inputs.pop("labels"), inputs.pop("loss_weights")
            outputs = model(**inputs)
            loss = weighted_loss(outputs.logits, labels, weights)
            return (loss, outputs) if return_outputs else loss

    class ValidationF1(TrainerCallback):
        """Adds eval_macro_f1 to every evaluation, before early stopping and
        best-checkpoint tracking read the metrics."""
        def on_evaluate(self, args, state, control, metrics=None, model=None, **kwargs):
            if metrics is not None and model is not None and f1_entries:
                metrics["eval_macro_f1"] = validation_macro_f1(model, tok, f1_entries)
                print(f"  step {state.global_step}: validation macro-F1 {metrics['eval_macro_f1']}")

    args = TrainingArguments(
        output_dir=str(out_dir), seed=SEED, bf16=True,
        per_device_train_batch_size=CONFIG["per_device_batch"], per_device_eval_batch_size=CONFIG["per_device_batch"],
        gradient_accumulation_steps=CONFIG["grad_accum"], learning_rate=CONFIG["learning_rate"],
        num_train_epochs=CONFIG["max_epochs"], max_steps=max_steps, warmup_ratio=CONFIG["warmup_ratio"],
        lr_scheduler_type="cosine", logging_steps=5,
        eval_strategy="steps", eval_steps=CONFIG["eval_every_steps"],
        save_strategy="steps", save_steps=CONFIG["eval_every_steps"], save_total_limit=3,
        load_best_model_at_end=max_steps < 0 and bool(f1_entries),
        metric_for_best_model=CONFIG["select_by"] if f1_entries else "eval_loss",
        greater_is_better=bool(f1_entries),
        gradient_checkpointing=True, gradient_checkpointing_kwargs={"use_reentrant": False},
        report_to=[], optim="paged_adamw_8bit",
        restore_callback_states_from_checkpoint=True,  # a resumed run keeps its early-stopping count
        remove_unused_columns=False)  # keep loss_weights for compute_loss
    tok.padding_side = "right"
    callbacks = [ValidationF1()]  # first, so the metric exists for what follows
    if max_steps < 0:
        callbacks.append(EarlyStoppingCallback(CONFIG["early_stop_patience"]))
    pad_id = tok.pad_token_id if tok.pad_token_id is not None else tok.eos_token_id
    return WeightedTrainer(model=model, args=args, train_dataset=train_ds, eval_dataset=val_ds,
                           data_collator=lambda feats: pad_batch(feats, pad_id), callbacks=callbacks)


def stage_smoke(out: Path, base: str):
    from transformers import set_seed
    started = time.time()
    set_seed(SEED)  # before the adapter is made, so --seed decides its starting weights
    model, tok = load_model(train=True, base=base)
    out = _base_dir(out, base)
    train_ds, val_ds, weights = _datasets(out.parent, tok, limit=CONFIG["smoke_examples"])
    f1_entries = benchmark.load_split("validation")[:16]
    trainer = _trainer(model, tok, train_ds, val_ds, out / "smoke", max_steps=CONFIG["smoke_steps"],
                       f1_entries=f1_entries)
    result = trainer.train()
    smoke_f1 = trainer.evaluate().get("eval_macro_f1")  # proves the weighted loss and F1 check run
    adapter = out / "smoke" / "adapter"
    model.save_pretrained(str(adapter))
    del model, trainer
    import gc, torch  # noqa: E401
    gc.collect(); torch.cuda.empty_cache()
    model, tok = load_model(adapter=adapter, base=base)
    entries = benchmark.load_split("validation")[:3]
    path = out / "smoke" / "replies.jsonl"
    path.unlink(missing_ok=True)
    generate(model, tok, entries, path, sample=False)
    parsed = [analysis.parse(r["raw"]) for r in read_jsonl(path)]
    ok = all(p["analysis_status"] == "ok" for p in parsed)
    log(out, "smoke", train_loss=round(result.training_loss, 4), steps=CONFIG["smoke_steps"],
        validation_macro_f1_16=smoke_f1, class_weights=weights,
        reload_and_read_ok=ok, emotions=[p["emotion"] for p in parsed],
        minutes=round((time.time() - started) / 60, 1))
    if not ok:
        raise SystemExit("Smoke test: the reloaded adapter did not produce readable replies.")
    print("SMOKE TEST PASSED: training, saving to Drive, reloading and reading all work.")


def stage_train(out: Path, base: str):
    from transformers import set_seed
    finished = _base_dir(out, base) / "adapter" / "training.json"
    if finished.exists():
        # Running the cell again after a disconnect must not train a finished run
        # further; unfinished runs still resume from their last checkpoint.
        print(f"Already trained, skipping: {finished.parent} (delete that folder to train this tag again).")
        return
    started = time.time()
    set_seed(SEED)  # before the adapter is made, so --seed decides its starting weights
    model, tok = load_model(train=True, base=base)
    train_ds, val_ds, weights = _datasets(out, tok)
    out = _base_dir(out, base)
    run_dir = out / "train"
    trainer = _trainer(model, tok, train_ds, val_ds, run_dir, f1_entries=benchmark.load_split("validation"))
    resume = any(p.name.startswith("checkpoint-") for p in run_dir.glob("checkpoint-*"))
    result = trainer.train(resume_from_checkpoint=resume or None)
    adapter = out / "adapter"
    trainer.model.save_pretrained(str(adapter))
    tok.save_pretrained(str(adapter))
    # Replies an earlier adapter of this tag wrote must not be scored as this one's.
    (out / "eval_tuned_validation.jsonl").unlink(missing_ok=True)
    (adapter / "training.json").write_text(json.dumps({
        "base_model": BASES[base][0], "teacher": BASES[TEACHER][0], "config": CONFIG, "seed": SEED,
        "train_examples": len(train_ds), "validation_examples": len(val_ds),
        "class_weights": weights, "selected_by": CONFIG["select_by"],
        "best_checkpoint": trainer.state.best_model_checkpoint, "best_metric": trainer.state.best_metric,
        "training_loss": result.training_loss, "steps": trainer.state.global_step,
        "split_manifest": json.loads((ROOT / "ml" / "datasets" / "splits" / "manifest.json").read_text()),
    }, indent=2) + "\n")
    hours = (time.time() - started) / 3600
    log(out, "train", steps=trainer.state.global_step, best_validation_macro_f1=trainer.state.best_metric,
        resumed=resume, hours=round(hours, 2), approx_units=round(hours * UNITS_PER_HOUR, 1))


def stage_evaluate(out: Path, base: str):
    """Untrained and trained, both 4-bit through transformers, sampled at the
    production temperature, against the 7B production numbers from Ollama."""
    entries = benchmark.load_split("validation")
    out = _base_dir(out, base)
    adapter = out / "adapter"
    if not adapter.exists():
        raise SystemExit("Run --stage train first.")
    results = {}
    for name, path in (("base", None), ("tuned", adapter)):
        model, tok = load_model(adapter=path, base=base)
        replies = out / f"eval_{name}_validation.jsonl"
        generate(model, tok, entries, replies, sample=True)
        preds = {r["id"]: {"raw": r["raw"], "parsed": analysis.parse(r["raw"]), "seconds": r["seconds"]}
                 for r in read_jsonl(replies)}
        results[name] = metrics.score(entries, preds)
        del model
        import gc, torch  # noqa: E401
        gc.collect(); torch.cuda.empty_cache()
    ollama = json.loads((ROOT / "reports" / "runs" / "baseline-qwen2.5-7b-validation-v2" / "report.json").read_text())
    comparison = {"base_model": BASES[base][0], **compare(results["base"], results["tuned"], ollama["metrics"])}
    (out / "comparison.json").write_text(json.dumps({"results": results, "comparison": comparison}, indent=2) + "\n")
    log(out, "evaluate", **comparison)
    print("\n".join(f"{k:34} {v}" for k, v in comparison.items()))


def compare(base: dict, tuned: dict, ollama: dict) -> dict:
    """The go/no-go numbers. Keep the tuned model only if it beats the base on
    emotion and intensity without losing on structure or people."""
    def pick(m):
        seconds = (m.get("seconds") or {}).get("p50")
        return {"macro_f1": m["emotion"]["macro_f1"], "lenient": m["emotion"]["lenient_accuracy"],
                "intensity_mae": m["intensity"]["mae"], "failed": m["structure"]["failed_rate"],
                "people_f1": m["people"]["f1"], "invented": m["people"]["invented"], "seconds_p50": seconds}
    b, t, o = pick(base), pick(tuned), pick(ollama)
    better = (t["macro_f1"] > b["macro_f1"] and t["intensity_mae"] is not None
              and b["intensity_mae"] is not None and t["intensity_mae"] < b["intensity_mae"])
    no_regression = (t["failed"] <= b["failed"] and t["people_f1"] >= b["people_f1"] - 0.02
                     and t["invented"] <= b["invented"])
    # Can the light model replace the 7B for reading entries? Small tolerance on
    # emotion because the sets are small; none on structure.
    matches_7b = (t["macro_f1"] >= o["macro_f1"] - 0.02 and t["intensity_mae"] is not None
                  and o["intensity_mae"] is not None and t["intensity_mae"] <= o["intensity_mae"] + 0.05
                  and t["failed"] <= o["failed"] and t["people_f1"] >= o["people_f1"] - 0.03)
    return {"untrained_4bit": b, "trained_4bit": t, "production_7b_ollama": o,
            "keep": bool(better and no_regression),
            "reason": "beats the untrained model on emotion and intensity, no regressions" if better and no_regression
            else "does not clear the bar: " + ("no gain on emotion and intensity" if not better else "a regression"),
            "can_replace_7b_for_reading": bool(better and no_regression and matches_7b)}


def stage_export(out: Path, base: str):
    """Merge the adapter into the full model and write one GGUF file for Ollama.
    Unquantised (f16); Ollama quantises it to q4_K_M on the Mac, like the 7B."""
    import subprocess
    # Colab ships an old torchao that current peft refuses to load beside; we don't use it.
    subprocess.run([sys.executable, "-m", "pip", "uninstall", "-y", "-q", "torchao"], check=False)
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer
    out = _base_dir(out, base)
    adapter, merged = out / "adapter", Path("/content/merged") if Path("/content").exists() else out / "merged"
    if not adapter.exists():
        raise SystemExit("Run --stage train first.")
    model = AutoModelForCausalLM.from_pretrained(BASES[base][0], torch_dtype=torch.float16)
    model = PeftModel.from_pretrained(model, str(adapter)).merge_and_unload()
    model.save_pretrained(str(merged))
    AutoTokenizer.from_pretrained(BASES[base][0]).save_pretrained(str(merged))
    llama = Path("/content/llama.cpp") if Path("/content").exists() else out / "llama.cpp"
    if not llama.exists():
        subprocess.run(["git", "clone", "-q", "--depth", "1", "https://github.com/ggml-org/llama.cpp", str(llama)], check=True)
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "gguf", "sentencepiece"], check=True)
    gguf = out / f"innerbloom-reader-{base}{'-' + TAG if TAG else ''}-f16.gguf"
    subprocess.run([sys.executable, str(llama / "convert_hf_to_gguf.py"), str(merged),
                    "--outtype", "f16", "--outfile", str(gguf)], check=True)
    log(out, "export", gguf=str(gguf), size_gb=round(gguf.stat().st_size / 2 ** 30, 2))
    print(f"Download this one file to your Mac: {gguf}")


def stage_public(out: Path, base: str):
    from ml import public_data
    public_data.main(["--out", str(out)])


STAGES = {"public": stage_public, "check": stage_check, "replies": stage_replies, "smoke": stage_smoke,
          "train": stage_train, "evaluate": stage_evaluate, "export": stage_export}


def main(argv=None) -> int:
    global TAG, WITH_PUBLIC, SEED
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", choices=STAGES, required=True)
    ap.add_argument("--out", type=Path, default=Path(os.environ.get("INNERBLOOM_TRAIN_OUT", ROOT / "reports" / "phase3")))
    ap.add_argument("--base", choices=BASES, default="1.5b", help="model size to train (default 1.5b)")
    ap.add_argument("--tag", default="", help="name for this round, e.g. r2; results go to qwen2.5-<base>-<tag>")
    ap.add_argument("--lora-r", type=int, help="LoRA rank (alpha is set to twice the rank)")
    ap.add_argument("--lr", type=float, help="learning rate")
    ap.add_argument("--with-public", action="store_true", help="add EmpatheticDialogues examples (non-commercial licence)")
    ap.add_argument("--seed", type=int, default=SEED,
                    help="training seed; train three (7, 8, 9) and keep the best on validation")
    args = ap.parse_args(argv)
    TAG, WITH_PUBLIC, SEED = args.tag, args.with_public, args.seed
    if SEED != 7:  # the first seed keeps the old folder names
        TAG = f"{TAG}-s{SEED}" if TAG else f"s{SEED}"
    if args.lora_r:
        CONFIG["lora_r"], CONFIG["lora_alpha"] = args.lora_r, 2 * args.lora_r
    if args.lr:
        CONFIG["learning_rate"] = args.lr
    args.out.mkdir(parents=True, exist_ok=True)
    started = time.time()
    STAGES[args.stage](args.out, args.base)
    hours = (time.time() - started) / 3600
    print(f"stage {args.stage} took {hours * 60:.1f} min, about {hours * UNITS_PER_HOUR:.1f} compute units")
    return 0


if __name__ == "__main__":
    sys.exit(main())
