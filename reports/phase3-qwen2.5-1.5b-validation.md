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
