---
license: apache-2.0
base_model: Qwen/Qwen2.5-1.5B-Instruct
base_model_relation: finetune
language:
  - en
pipeline_tag: text-generation
library_name: gguf
tags:
  - gguf
  - ollama
  - journaling
  - emotion-classification
  - qwen2.5
---

# Innerbloom reader 1.5B

A small model that reads one journal entry and returns its main emotion, how strong it is, a one-line summary, tags, themes and the people named. It runs locally through Ollama in about 2.6 seconds per entry on an 8 GB M1 Mac, in 1.9 GB.

It is the entry reader for [Innerbloom](https://github.com/GhanshyamPaunikar/innerbloom), a local-first AI journal. Innerbloom uses it automatically when Ollama has it, and keeps a larger model for chat.

## Install

```bash
ollama pull hf.co/{REPO}:Q8_0
ollama cp hf.co/{REPO}:Q8_0 innerbloom-reader:1.5b-q8-edited
```

The second line gives it the name Innerbloom looks for. Or, from an Innerbloom checkout: `python scripts/get_reader.py`.

## Results

On Innerbloom's locked test split: 400 fictional entries, scored once, never used for any choice. All three models ran through Ollama on the same Mac, with the same prompt, temperature 0.3 and seed 7.

| | qwen2.5:7b | This model before the edit | **This model** |
|---|---|---|---|
| Emotion macro-F1 (16 classes) | 0.652 | 0.702 | **0.746** |
| Emotion accuracy, defensible alternatives | 0.795 | 0.825 | **0.853** |
| Intensity error, 1-10 (MAE) | 1.155 | **0.777** | 0.795 |
| Failed readings | 0 | 0 | 0 |
| People F1 | 0.823 | 0.916 | **0.923** |
| Invented names | 9 | 3 | **2** |
| Median seconds per entry | 13.3 | 3.4 | **2.6** |
| Size | 4.7 GB | 1.6 GB | 1.9 GB |

On the 402-entry validation split the same model scored 0.752, so the score held on unseen entries. A second person labelled 100 validation entries blind: Cohen's kappa 0.84 with the original labels, and 99% agreement allowing defensible alternatives.

## How it was made

1. **Fine-tuning.** QLoRA (rank 16, alpha 32, learning rate 2e-4, early stopping on validation loss) of Qwen2.5-1.5B-Instruct on 1,199 fictional entries. Targets: the labelled emotion, intensity and names, plus a summary, tags and themes written by qwen2.5:7b. About 6.5 Colab A100 compute units.
2. **Quantisation.** Merged, converted to GGUF with llama.cpp and quantised to Q8_0. Q4_K_M lost too much (0.672 on validation).
3. **Weight edit.** The model over-picked some emotions and avoided others. A per-emotion bias was fitted on training entries only, by coordinate ascent on macro-F1 checked with 5-fold cross-validation, and written into the model: Qwen2.5-1.5B shares one table for reading and writing tokens, so the edit adds a separate output table and moves the rows for 11 emotions' first tokens along the mean final hidden state. Reading is untouched. Validation macro-F1 went from 0.711 to 0.752, and test from 0.702 to 0.746.

Code and reports: `ml/train_emotion.py`, `ml/weight_editing/`, `reports/final-test.md` in the Innerbloom repository.

## Prompt

The model was trained and scored on Innerbloom's own prompt, `build_prompt` in `innerbloom_core/analysis.py`, which asks for compact JSON:

```json
{"emotion": "...", "intensity": 1, "summary": "...", "tags": ["..."], "themes": ["..."], "people": ["..."]}
```

The 16 emotions are happy, sad, anxious, calm, grateful, frustrated, excited, reflective, hopeful, tired, angry, content, lonely, proud, overwhelmed and neutral. Other prompts or tasks are untested.

## Limits

- **Fictional, English entries only.** Every training and test entry was invented; none came from a real journal. Real writing may differ.
- **Sarcasm is the weak spot:** about 4 of 9 sarcastic test entries read correctly, the same as the 7B.
- **Not a safety or medical tool.** It does not detect crisis risk. Innerbloom checks for that separately, and nothing here should be used to judge anyone's mental health.
- One writer wrote the entries and labels; one second reader checked a sample.

## Licence

Apache 2.0, the same as the base model Qwen2.5-1.5B-Instruct. The training data was written for Innerbloom; no public dataset was used in this model.
