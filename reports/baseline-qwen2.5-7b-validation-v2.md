# Baseline v2: qwen2.5:7b on the 402-entry validation split

The production model and prompt on the grown dataset, before any training. Run on 2026-11-05/06 on an Apple M1 with 8 GB of RAM through local Ollama, temperature 0.3, seed 7.

- Split: `ml/datasets/splits/validation.jsonl` (seed v2), 402 fictional entries, 24-26 per emotion, fingerprint `63e45a2a7635`
- Raw replies and full metrics: `reports/runs/baseline-qwen2.5-7b-validation-v2/`
- Cost: no compute units; about 70 minutes on the Mac

This is the number Phase 3 has to beat. It is lower than the first baseline (0.705) because the new entries were aimed at what the model found hard: the two runs are on different sets and should not be compared.

## Results

| Task | Metric | Result |
|---|---|---|
| Emotion | Macro-F1 (16 classes) | 0.636 |
| | Accuracy, exact label | 64.2% |
| | Accuracy, allowing a defensible alternative | 78.9% |
| Intensity | Mean absolute error (1-10) | 1.23 |
| | Within one point | 67.4% |
| Structured output | Failed readings / valid JSON / every field | 0 / 100% / 100% |
| People | Precision / recall | 0.96 / 0.83 |
| | Names not in the entry | 1 ("Mom", added to an entry about a teenager) |
| Speed | Seconds per entry, median / 95th percentile | 8.6 / 20.3 |

## Where it goes wrong

| Emotion | F1 |
|---|---|
| overwhelmed | 0.33 |
| proud | 0.49 |
| happy | 0.49 |
| excited | 0.56 |
| anxious | 0.57 |
| frustrated | 0.59 |
| ... | |
| hopeful | 0.79 |
| tired | 0.88 |

| Written as | Read as | Times (of about 25) |
|---|---|---|
| overwhelmed | anxious | 12 |
| lonely | sad | 10 |
| proud | excited | 8 |
| happy | excited | 7 |
| angry | frustrated | 6 |

It answered `anxious` 49 times and `excited` 40 times for about 25 of each, and `overwhelmed` only 5 times and `proud` 8 times. Sarcasm: 5 of 10 read acceptably; "So nice of Gavin to reply-all with my mistake to the entire company" came back `grateful`. Implied feelings: 13 of 23. Mixed feelings: 9 of 16.

It handles negation (5 of 5), factual entries (20 of 22), long entries (8 of 9) and time references well.

## What Phase 3 has to show

On this split, a trained light model is worth keeping if it beats its own untrained version on macro-F1 and intensity error with no loss on structure or names, and can replace the 7B for reading entries if it reaches about 0.62 macro-F1 and 1.28 intensity error or better while staying fast. The bias above (too many `anxious` and `excited`, too few `overwhelmed`, `proud`, `lonely`) is what the labels are best placed to correct.

## Caveats

- One writer's labels, not yet checked by a second reader.
- Intensity is a judgement; an error of 1 is often a reasonable disagreement.
- The locked test split (400 entries) has not been run.
