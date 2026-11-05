# Baseline: qwen2.5:7b on the validation split

> **Superseded.** Measured on the first split (1,220 entries, 183 for validation). The dataset grew to 2,001 entries and was re-split 60/20/20; see `reports/baseline-qwen2.5-7b-validation-v2.md`. Kept for the record; do not compare its numbers with later runs.

The production model and prompt, measured before any training. Run on 2026-11-05 on an Apple M1 with 8 GB of RAM through local Ollama, at the production temperature (0.3) with a fixed seed (7).

- Split: `ml/datasets/splits/validation.jsonl`, 183 fictional entries, fingerprint `b0dcab49af32`
- Prompt: `innerbloom_core/analysis.py`, matches `production_spec.json`
- Raw replies and full metrics: `reports/runs/baseline-qwen2.5-7b-validation/`
- Cost: no compute units; about 50 minutes on the Mac

## Results

| Task | Metric | Result |
|---|---|---|
| Emotion | Macro-F1 (16 classes) | 0.705 |
| | Accuracy, exact label | 71.6% |
| | Accuracy, allowing a defensible alternative | 82.5% |
| Intensity | Mean absolute error (1-10 scale) | 1.19 |
| | Within one point | 65.6% |
| Structured output | Failed readings | 0 of 183 |
| | Replies that were valid JSON as sent | 100% |
| | Replies with every field | 100% |
| People | Precision / recall | 0.95 / 0.87 |
| | Names not in the entry | 1 (a parser bug, below) |
| | Non-people extracted (days, places, brands, pets) | 0 |
| Speed | Seconds per entry, median / 95th percentile | 15.3 / 23.8 |

## Where it goes wrong

**Close emotions.** The weakest classes are `proud` (F1 0.31), `overwhelmed` (0.53), `happy` (0.54) and `content` (0.58). The most common mistakes:

| Written as | Read as | Times |
|---|---|---|
| lonely | sad | 6 |
| proud | excited | 4 |
| overwhelmed | anxious | 4 |
| calm | content | 3 |
| proud | happy | 2 |

The model rarely answers `proud` (2 times for 11 proud entries) or `lonely` (5 for 11), and over-uses `content` and `excited` (20 each for 11 each).

**Sarcasm.** 1 of 3 sarcastic entries was read correctly. "Absolutely thrilled to be spending my birthday at the tax office" came back as `excited`.

**Feelings that are implied, not named.** 3 of 6 indirect entries were read acceptably. A long entry describing a flat, grey week came back `neutral`.

**What it handles well.** Negation (4 of 4), time references (15 of 16), look-alike names (3 of 3), mixed feelings (9 of 11 acceptable), and plain entries (85%).

## A bug found along the way

The parser in `innerbloom_core/analysis.py` removed accented letters from names, so "Tomás" was stored as "Toms". This was not the model inventing a name; it affected every accented name in the People view, and names in other scripts (Hindi, Japanese) were dropped entirely.

Fixed the same day: names, tags and People keys now keep letters in any script. The same replies, rescored (`reports/runs/baseline-qwen2.5-7b-validation-namefix/`): people precision 0.964, recall 0.885, no invented names. Emotion and intensity are unchanged. Names already saved in a journal keep their old spelling until the entry is edited.

## Caveats

- Each emotion has 11-13 validation entries, so per-class scores move a lot with one or two answers.
- All labels are one writer's and have not yet been checked by a second reader.
- Intensity labels are a judgement on a 1-10 scale; an error of 1 is often a reasonable disagreement.
- The locked test split has not been run and should only be run once, on the finished model.

## Safety classifier, same day

`python -m ml.safety_eval --model qwen2.5:7b`, on the 110 seen safety cases, with the model answering:

| | Result |
|---|---|
| Crisis statements with full help lines | 39 of 40 |
| Crisis statements with any help | 40 of 40 |
| Distress statements with any help | 20 of 20 |
| Harmless sentences raising a full alert | 2 of 40 |
| Harmless sentences with gentle help | 11 of 40 |
| Everyday sentences with any help | 0 of 10 |
| Seconds per check | about 2 |

These cases were used to design the fix, so they show it works as intended, not how it generalises. The blind set (`ml/datasets/blind/`) is still needed for that.

## What this means for Phase 3

The case for fine-tuning is real but narrow: structure and names are already strong, so the gain to look for is in close emotions (proud, lonely, overwhelmed, content), sarcasm and implied feelings, plus intensity calibration. A fine-tuned model is only worth keeping if it beats 0.705 macro-F1 and 1.19 intensity MAE on validation, and then on the locked test, without getting slower or worse on names.
