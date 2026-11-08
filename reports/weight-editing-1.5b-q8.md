# Weight editing: correcting the 1.5B's emotion bias without training

2026-11-08, on the Mac. Round-1 Qwen2.5-1.5B, q8_0 in Ollama. The method follows the idea of editing weights directly from reading the model, with no gradient training; the edit was derived from the training split only.

## Method

1. `ml/weight_editing/probe.py`: one forward pass per training entry (1,359) with the production prompt and the reply opening `{"emotion": "`, saving the 16 emotions' first-token logits and the final hidden state.
2. `ml/weight_editing/fit.py`: one logit offset per emotion, by coordinate ascent on macro-F1, checked with 5-fold cross-validation inside the training split: 0.797 → 0.837.
3. `ml/weight_editing/apply.py`: the model ties its input and output tables, so the edit adds a separate output table (a copy) and changes only 11 rows: `row_k += offset_k * hbar / |hbar|^2`, where `hbar` is the mean final state at the decision (its projection varies by about 2% across entries). 16,896 numbers changed, about 0.001% of the model; reading is untouched.
4. Rebuilt as q8_0 (`innerbloom-reader:1.5b-q8-edited`, 1.9 GB), checked on 80 training entries (100% valid JSON, normal summaries), then scored once on validation.

Offsets: tired +3.0, proud +2.0, anxious +0.5, content +0.5, excited +0.25; sad −2.0, hopeful −0.75, happy −0.5, calm −0.5, grateful −0.5, overwhelmed −0.25.

## Validation (402 entries, Mac, Ollama)

| | 7B | 1.5B q8 | **1.5B q8 edited** |
|---|---|---|---|
| Emotion macro-F1 | 0.636 | 0.711 | **0.752** |
| Accuracy, defensible alternatives | 78.9% | 82.6% | **84.1%** |
| Intensity error | 1.229 | 0.799 | **0.776** |
| People F1 | 0.890 | **0.954** | 0.950 |
| Failed readings | 0 | 0 | 0 |
| Invented names | 1 | 1 | 2 |
| Sarcasm (10) | **5** | 4 | 3 |
| Median seconds per entry | 8.64 | **2.64** | 3.34 |
| Size | 4.7 GB | **1.6 GB** | 1.9 GB |

Per emotion: proud F1 0.47 → **0.78**, tired 0.60 → **0.82**, sad 0.58 → **0.70**, happy 0.53 → 0.56. Picks per about 25 labelled: proud 9 → 21, tired 11 → 23, sad 37 → 18, happy 42 → 31.

The validation gain (+0.041) matches the cross-validated training gain (+0.040), so the correction generalises rather than fitting noise.

## Costs and caveats

- One more invented name (2 against 1) and one fewer sarcastic entry read acceptably (3 against 4, out of 10): small numbers, worth watching on the locked test.
- 0.7 s slower and 0.3 GB larger, because of the separate output table.
- Validation was used to choose between models; the locked test split (400 entries) is the final check.
