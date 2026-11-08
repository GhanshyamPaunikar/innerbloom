# Final locked test: 400 entries, run once (2026-11-08)

The test split (400 entries, sha `d52235779188`) was locked from the start and had never been scored
by any model or used for any decision. Each model read it once on the Mac (Apple Silicon, Ollama),
through the production prompt, at temperature 0.3 and seed 7: `python -m ml.benchmark --split test --final`.

| | qwen2.5:7b | 1.5B q8 | 1.5B q8 edited |
|---|---|---|---|
| Emotion macro-F1 | 0.652 | 0.702 | **0.746** |
| Emotion accuracy | 0.66 | 0.70 | **0.745** |
| Accuracy, defensible alternatives | 0.795 | 0.825 | **0.853** |
| Intensity error (MAE) | 1.155 | **0.777** | 0.795 |
| Failed readings | 0 | 0 | 0 |
| People F1 | 0.823 | 0.916 | **0.923** |
| Invented names | 9 | 3 | **2** |
| Sarcasm (lenient) | **0.444** | 0.333 | **0.444** |
| Seconds per entry (median) | 13.33 | 3.37 | **2.61** |
| Size on disk | 4.7 GB | 1.6 GB | 1.9 GB |

## Validation versus test

| Model | Validation macro-F1 | Test macro-F1 |
|---|---|---|
| qwen2.5:7b | 0.636 | 0.652 |
| 1.5B q8 | 0.711 | 0.702 |
| 1.5B q8 edited | 0.752 | 0.746 |

The scores held up on unseen entries, so the choices made on validation (training round 1, q8, and the
bias edit) were not tuned to luck. The edit's gain over the plain q8 is +0.044 on test (+0.041 on validation).

## Verdict

**The edited 1.5B q8 (`innerbloom-reader:1.5b-q8-edited`) becomes Innerbloom's entry reader.**
Compared with the 7B it reads emotions better (+0.094 macro-F1), judges intensity better
(0.80 against 1.16 error), finds people better and invents fewer names. It is about five times
faster and under half the size. Chat and insights keep the 7B.

Notes:
- The 7B's speed here (13.3 s) is slower than on validation (8.6 s), because the three runs shared the Mac
  one after another; the small models' speeds are comparable to validation.
- All entries are fictional. A second reader has not yet checked the labels, and the blind safety set is still to come.
- The test split is now spent: it must not be used to choose between further variants.

Raw outputs: `reports/runs/final-test-qwen2.5-7b/`, `reports/runs/final-test-1.5b-q8/`, `reports/runs/final-test-1.5b-q8-edited/`.
