# Phase 3 result: trained Qwen2.5-1.5B on the 402-entry validation split

Run on 2026-11-08 on a Colab A100 (40 GB) with `notebooks/02_emotion_training.ipynb` at commit `a8af2d6`. The adapter and full outputs are in Google Drive at `MyDrive/innerbloom/phase3/qwen2.5-1.5b/`.

| | Untrained 1.5B (4-bit) | **Trained 1.5B (4-bit)** | 7B production (Ollama) |
|---|---|---|---|
| Emotion macro-F1 | 0.066 | **0.746** | 0.636 |
| Accuracy, defensible alternatives | 16.2% | **86.1%** | 78.9% |
| Intensity error (MAE) | 2.261 | **0.881** | 1.229 |
| Failed readings | 0 | 0 | 0 |
| People F1 | 0.148 | **0.964** | 0.890 |
| Invented names | 1 | 1 | 1 |
| Median seconds per entry | 0.51 (A100) | 0.90 (A100) | 8.64 (M1 Mac) |

Verdict from `compare` in `ml/train_emotion.py`: **keep = True** (beats its untrained self on emotion and intensity, no regressions) and **can_replace_7b_for_reading = True**.

## Training

- QLoRA, rank 16, 18.5M trainable parameters (1.18% of 1.56B)
- 1,199 training entries; targets: labelled emotion, intensity and names, with the 7B's summary, tags and themes
- Early stopping on validation loss: stopped at step 160 of 225, best eval loss 0.500
- Cost: about 6.5 compute units for everything (answers, smoke test, training, evaluation); 154 of 159 units left after training

## Caveats

- Labels and entries are one writer's. Part of the gain may be the model learning that writer's labelling style, which the 7B never saw. A second reader's check and the locked test split will show how much holds.
- Speed is not comparable across rows: the 7B ran on an 8 GB M1 through Ollama, the others on an A100. Laptop speed is measured in Phase 6.
- The locked test split (400 entries) has not been run. It is run once, on the final choice.

## On the Mac (2026-11-08)

The trained model exported to GGUF (`ml.train_emotion --stage export`), loaded into Ollama as `innerbloom-reader:1.5b` with the 7B's chat template, quantised to q4_K_M (986 MB), and run with `ml.benchmark` exactly like the 7B: same prompt, temperature, seed and 8 GB M1. Run: `reports/runs/reader-1.5b-ollama-validation/`.

| | 7B (Ollama, q4) | Trained 1.5B (Ollama, q4_K_M) |
|---|---|---|
| Emotion macro-F1 | 0.636 | **0.672** |
| Accuracy, exact / allowing alternatives | 64.2% / 78.9% | **67.2% / 79.6%** |
| Intensity error | 1.229 | **0.806** |
| People F1 | 0.890 | **0.955** |
| Failed readings / invented names | 0 / 1 | 0 / 1 |
| Sarcasm (10 entries) | **5 of 10** | 3 of 10 |
| Seconds per entry, median / 95th percentile | 8.6 / 20.3 | **2.2 / 3.3** |
| Size | 4.7 GB | **0.99 GB** |

The 1.5B keeps its lead on everything except sarcasm, at a quarter of the time and a fifth of the size. Its emotion score drops from 0.746 (4-bit transformers on Colab) to 0.672 here, most likely from q4_K_M quantisation and Ollama's sampling; a q8_0 build (about 1.6 GB) is the next thing to try to recover it.
