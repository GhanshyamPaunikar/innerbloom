# Weight-editing brief: Qwen3.5-0.8B for Innerbloom entry reading

Give this whole file to the editing model, together with a Python sandbox that has this repository checked out, a GPU, and the latest `transformers`.

## The job

Innerbloom reads a private journal entry and returns one JSON object:

```
{"emotion": ..., "intensity": 1-10, "summary": ..., "tags": [...], "themes": [...], "people": [...]}
```

The exact prompt is `innerbloom_core.analysis.build_prompt(text)`; replies are parsed by `innerbloom_core.analysis.parse(raw)`. `emotion` must be one of the 16 in `innerbloom_core.analysis.EMOTIONS`. The labelling rules are in `ml/datasets/GUIDELINES.md`.

Edit the weights of `Qwen/Qwen3.5-0.8B` (text model only; leave the vision encoder untouched) so it does this job better. **No gradient-based training.** Only direct edits to weight values, reasoned from reading the weights, activations and outputs.

## What you may use

- `ml/datasets/splits/train.jsonl` (1,199 labelled entries) freely, as practice.
- Evaluations: `python -m ml.eval_hf --model <folder> --split train --limit <n> --name <tag> --out /content/edit_runs`. Each scored entry counts as one forward pass. **Budget: 3,000 scored training entries in total.** Keep a log of every evaluation and its result.
- Activations, attention patterns and any analysis of the weights you like.

## What you must not use

- `ml/datasets/splits/validation.jsonl` or `test.jsonl`, or anything in `reports/` derived from them. They decide whether your edit is kept, so they must stay unseen.
- Any other model's outputs as training targets.

## Known weaknesses to aim at

Measured on the 7B production model; the 0.8B has not been measured yet, so check first.

- `overwhelmed` read as `anxious`, `lonely` as `sad`, `proud` as `excited`, `angry` as `frustrated`
- Too many `anxious` and `excited` answers; too few `overwhelmed`, `proud`, `lonely`
- Sarcasm read literally ("So nice of Gavin to reply-all with my mistake" read as grateful)
- Inventing people who are not in the entry
- Any reply that is not one complete JSON object, or that loops or runs on

## What to hand back

1. The edited model saved with `save_pretrained` to a folder (with the tokenizer).
2. `EDIT_LOG.md`: what you changed and why, which weights (layer, matrix, rows or columns), the share of weights changed, and every evaluation with its score.
3. Your own training-split score before and after.

## How it is judged

Scored once on the 402 validation entries with `python -m ml.eval_hf --split validation`, next to the untrained 0.8B, the trained 1.5B and the 7B. The edit is kept only if it beats the untrained 0.8B on emotion macro-F1 and intensity error, with no more failed readings or invented names.
