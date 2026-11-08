# Innerbloom AI v2: progress

Working branch: `feature/innerbloom-ai-v2`. `main` stays stable until a phase is reviewed and merged.

| Phase | Scope | GPU budget | Status |
|---|---|---|---|
| 0 | Audit, backup, branch | 0 | Done (2026-11-05) |
| 1 | Data and security stability | 0 | Done (2026-11-05), awaiting review |
| 2 | Fictional benchmark and baseline | 15 units | Baseline done on the Mac (0 units); second-reader check and retrieval/evidence sets still to do |
| 3 | Light emotion model (QLoRA) | 45 units | 1.5B trained: beats the 7B on validation (about 6.5 units) |
| 4 | Memory reranker | 25 units | Not started |
| 5 | Evidence verifier | 20 units | Not started |
| 6 | Ollama export and integration | 0 | Not started |
| 7 | Final comparisons and release | 20 units | Not started |

Reserve: 34 units. No GPU run starts without an agreed objective, cost ceiling and pass/fail criteria.

## Phase 0: audit (2026-11-05)

### Baseline

- `main` at `187350c` (CI workflow added).
- `python tests/test_app.py`: 89 checks pass, 0 fail.
- `python -m unittest discover -s tests -t .`: 5 tests pass (workspace serving, public demo).

### Current AI pipeline

| Step | Where | Model / method |
|---|---|---|
| Entry analysis | `analyze_entry` | `qwen2.5:7b` via Ollama (`INNERBLOOM_MODEL`), temperature 0.3, prompt asks for JSON |
| JSON parsing | `extract_json` | `json.loads`, then regex `{...}`, then trailing-comma and quote repair |
| Output schema | `analyze_entry` | `emotion` (one of 16 in `EMOTIONS`), `intensity` 1-10, `summary` ≤280 chars, `tags` ≤5, `themes` ≤3, `people` ≤6 |
| Embeddings | `embed`, `_embed_entry_chunks` | `mxbai-embed-large`; entries over 400 chars split into ~280-char chunks; stamped with model name |
| Retrieval | `retrieve_similar`, `retrieve_memory` | cosine similarity × recency (30-day half-life, floor 0.85), MMR (λ 0.7), plus keyword scoring |
| Chat agent | `/chat/agent` | classify → plan tools → run tools → draft with `[cite:id]` citations |
| Insights | `compute_contradictions`, `compute_triggers`, `compute_wellbeing`, `compute_narrative` | statistics first, model writes explanations; cached in `data/insights.json` |
| Safety | `crisis_check` | keyword list plus model classifier; attaches helplines |

Alternate provider: `INNERBLOOM_PROVIDER=gemini` (public demo only).

Storage: JSON files in `data/` (`journal.json`, `chat.json`, `insights.json`, `people.json`, `spotify.json`, `cluster_names.json`), written by `save_file` via a temp file and `os.replace`.

### Sensitive data check

- Private data files in `data/` are ignored and have never been committed.
- No API keys, tokens or private keys found in tracked files or in history.
- `docs/Spotify.png` exists in history only (removed from the tree); it should be checked for a visible client ID.
- Developer-tool files are excluded locally through `.git/info/exclude`, not the tracked `.gitignore`.
- `main` has no tool attribution in files or commit messages. The local-only branch `backup-before-clean` (never pushed) still holds the pre-cleanup history.

### Issues found for Phase 1

1. **Failed analysis looks like a real reading.** If the model is down or returns unparsable text, `analyze_entry` returns `neutral`, intensity 5 and no error. Stats, triggers and wellbeing then count these as genuine neutral entries.
2. **Any website can read the local API.** CORS allows every origin, and there is no Origin or Host check. A page open in the same browser could fetch `http://127.0.0.1:5000/journal`. Some browsers now prompt before a public page reaches localhost, but this cannot be relied on. DNS rebinding is also unguarded. To be confirmed with adversarial tests.
3. **Concurrent writes can lose data.** Routes run in a thread pool. Read-modify-write on `journal.json`, `people.json` and `chat.json` has no lock (only insights do), and all writers to a file share one `.tmp` path.
4. **CI cannot fail on backend checks.** The workflow runs `pytest`, but `tests/test_app.py` records failures in a counter instead of asserting, so its 89 checks always pass under pytest. They only fail when the file is run directly.
5. **`app.py` is about 6,000 lines.** Extract modules incrementally, behind the existing tests, without changing API contracts.

Still to review in Phase 1: derived-data refresh on edit/delete (embeddings, people, insights) and background job status (queued, running, failed, with errors and timestamps).

## Phase 1: stabilise data and security (2026-11-05)

Tests: `python -m pytest -q` passes 29 tests with 68 sub-cases; `python tests/test_app.py` passes 129 checks (89 before Phase 1). Browser check against a throwaway data folder with Ollama stopped: saving shows "not read yet", Entries offers "Read again", no console errors.

| Area | Change | Evidence |
|---|---|---|
| CI | `tests/conftest.py` fails a pytest test when any of its `check()` calls fail | A planted failing check made pytest fail; removed again |
| Structured analysis | A failed reading is saved with `analysis_status: "failed"` and the error. It is excluded from stats, triggers, wellbeing, chat tools and listening comparisons. `POST /journal/reanalyze` reads it again; the UI labels it and offers a retry | Failed-analysis tests |
| JSON writes | One lock per data file around every load-change-save, unique temp files, embedding write-back merged by id, chat turns appended under the lock | 12 parallel saves × 5 runs: old code lost 43 of 60 entries, new code lost none |
| Derived data | Deleting an entry removes it from cached insights, dropping any insight that quoted it. Edits already re-embed; people stats are computed live from entries | Derived-data tests |
| Background jobs | Jobs end as `idle` or `failed`; `/insights/status` returns the last error and its time | Job status tests |
| Local API security | CORS limited to pages on this computer. A guard refuses other Hosts (DNS rebinding) and other sites' Origins, including `null`. The public demo keeps a same-site rule behind its rewrite | Local-only tests, demo test |
| Wellbeing and safety | Crisis detection rewritten in two tiers (clear phrases; ambiguous or negated phrases checked by the classifier). An unreachable classifier shows gentle help lines instead of nothing. The classifier's verdict is read from its first word only. Writing, saving and chat now share one set of rules. Wellbeing reports "not enough to read yet" instead of "ok" with fewer than 4 entries, and a quiet signal can't take on the model's words | `tests/test_safety.py`, wellbeing level checks; see the table below |
| Maintainability | `innerbloom_core/analysis.py` (entry prompt, schema, parser) and `innerbloom_core/safety.py` extracted. The prompt is byte-identical and the parser gives identical output on sample replies. A JSON-list reply no longer crashes a save. The demo export copies the package; the name avoids the website's `innerbloom.py` entry file | Comparison script; demo export imported in a scratch copy |

Crisis detection on the same fictional cases (`tests/test_safety.py`):

| | Before | After |
|---|---|---|
| Clear statements missed (model off) | 8 of 15 | 0 of 15 |
| Harmless sentences raising a full alert | 9 of 14 | 0 of 14 |
| Ambiguous or heavy sentences with no help lines when the model is off | 1 of 10 | 0 of 10 |

These cases were written alongside the new rules, so they show the rules do what they intend, not how well they generalise. Phase 2 needs an independently written, locked set of safety cases.

Notes:
- Spotify tokens stay in `data/spotify.json` on this computer, ignored by Git. With cross-site requests refused, no other site can read them through the API.
- The old `docs/Spotify.png` in history still needs a look for a visible client ID.

### Next human action

Review Phase 1, then approve Phase 2 (benchmark and baseline, ceiling 15 compute units). Phase 2 starts on this computer: reading the production schema from `innerbloom_core/analysis.py` and writing fictional benchmark data, with no GPU. Colab is needed only for the baseline runs.

Further `app.py` extraction (storage, retrieval, insights) continues alongside later phases.

## Phase 2: benchmark (started 2026-11-05)

### Done

| Piece | Where | Notes |
|---|---|---|
| Production spec | `ml/datasets/production_spec.json` (`python -m ml.spec`) | Read from the code: `qwen2.5:7b` via Ollama, temperature 0.3, 16 emotions, field limits, prompt fingerprint. The benchmark refuses to run if the prompt has changed since |
| Labelling rules | `ml/datasets/GUIDELINES.md` | Follow the production prompt, including what counts as a person |
| Entries | `ml/datasets/entries/` (`python -m ml.dataset`) | 1,220 fictional entries, 70-93 per emotion. Hard cases: 63 mixed, 34 negation, 18 sarcasm, 46 indirect, 55 look-alike names, 62 factual, 148 short, 11 long. 382 name at least one person |
| Splits | `ml/datasets/splits/` (`python -m ml.split`) | 855 train, 183 validation, 182 test. Stratified by emotion, groups kept together, near-duplicates refused, fingerprints in `manifest.json`. Test is locked: the benchmark needs `--final` |
| Benchmark | `python -m ml.benchmark` | Emotion macro-F1, accuracy and lenient accuracy (allowing defensible alternatives), confusion matrix, intensity MAE, JSON and schema rates, people precision/recall and invented names, speed. Saves every reply and resumes after an interruption |
| Safety cases | `ml/datasets/safety_cases.jsonl` (`python -m ml.safety_eval`) | 110 cases written in different wording from the rules: 40 crisis, 20 distress, 40 harmless, 10 everyday. Locked: do not tune the rules against them |

Tests: `python -m pytest -q` passes 38 tests with 68 sub-cases.

### Not yet reviewed by a person

All labels so far are one writer's. Before the baseline is trusted, a second reader should check a sample of about 100 validation entries against the guidelines and mark disagreements.

### Finding: crisis detection misses most independent wording

`reports/safety-2026-11-05.json`, current rules, model off unless stated:

| | Result |
|---|---|
| Crisis statements with full help lines from the words alone | 9 of 40 (22.5%) |
| Crisis statements with no help at all | 27 of 40 |
| Crisis statements ever passed to the classifier | 13 of 40 |
| Distress statements with any help | 8 of 20 |
| Harmless sentences raising a full alert (classifier says none) | 3 of 40 (past or educational mentions) |
| Everyday sentences with any help | 0 of 10 |

The Phase 1 table (0 of 15 missed) was measured on cases written alongside the rules. This set shows the rules did not generalise: indirect signs (giving things away, writing letters, stockpiling pills, "I want out") were not recognised, and the classifier was only asked when a listed phrase appeared.

### Fix (2026-11-05)

- The classifier now checks every chat message and saved entry when the model is available, with a prompt that names indirect signs and clear non-risks.
- The backup phrase lists cover more indirect signs, and statements told at a distance (past, topic, a friend) go to the classifier instead of alerting.
- Gentle help now shows on the writing page after saving, with lines open around the clock (AASRA, Find a Helpline).

The same set after the fix. It was used to find the gaps, so these numbers only show the direction of change:

| | Before | After |
|---|---|---|
| Crisis statements checked by the classifier | 13 of 40 | 40 of 40 |
| Crisis statements with any help, model off | 13 of 40 | 31 of 40 |
| Crisis statements with full help from the words alone | 9 of 40 | 17 of 40 |
| Distress statements with any help, model off | 8 of 20 | 11 of 20 |
| Harmless sentences raising a full alert | 3 of 40 | 0 of 40 |
| Harmless sentences with gentle help, model off | 13 of 40 | 17 of 40 |
| Everyday sentences with any help | 0 of 10 | 0 of 10 |

How well the classifier itself catches crisis statements has not been measured yet: that needs the model (Phase 2 baseline). The real test is a blind set written by someone who has not read the rules: `ml/datasets/blind/HOW_TO_WRITE.md`. Only its totals are ever printed.

### Baseline (2026-11-05)

Full write-up: `reports/baseline-qwen2.5-7b-validation.md`. On 183 validation entries, run locally with no compute units:

- Emotion macro-F1 0.705, accuracy 71.6% (82.5% allowing a defensible alternative)
- Intensity MAE 1.19
- 100% valid, complete JSON; 0 failed readings
- People precision 0.95, recall 0.87
- 15 seconds per entry on this Mac
- Weak spots: proud, lonely, overwhelmed, content; sarcasm; implied feelings
- The safety classifier with the model on: 39 of 40 crisis statements get full help, 2 of 40 harmless ones alert (seen set)
- Bug found and fixed: the parser stripped accented letters from names ("Tomás" became "Toms") and dropped names in other scripts. Rescored: people precision 0.964, recall 0.885, no invented names

### Memory search and evidence checking (2026-11-05)

Full write-up: `reports/baseline-retrieval-evidence-validation.md`.

- `ml/datasets/retrieval/`: three fictional journals (108 entries) and 54 questions with marked answers; journal c locked.
- `ml/datasets/evidence/claims.jsonl`: 120 claims with dated evidence, labelled supported, contradicted or insufficient; half locked.
- Keyword search: the answer is in the top 5 for 80.6% of questions; meaning search (what the chat agent uses): 91.7%, recall 82.3%. Both ignore time (27-28% of results inside the asked window), and meaning search finds about 62% of entries for questions needing several.
- `qwen2.5:7b` as a plain evidence judge: accepts 39% of claims the entries do not support (mostly overreach from thin evidence), rejects no valid claims.

### Dataset v2 (2026-11-05)

Grown from 1,220 to 2,001 entries, aimed at the baseline's weak spots and written in more voices: teenagers and students, elderly writers, second-language English, parents and carers, shift workers, one-line notes, long entries, chronic illness, LGBTQ+ writers, artists, rural life, faith, neurodivergent writers and Indian English.

- 122-129 entries per emotion. Sarcasm 18 → 51, long entries 11 → 50, implied feelings 46 → 106, mixed 63 → 93, intensity 1-2 and 9-10 much better covered.
- Re-split 60/20/20 (seed v2): 1,199 train, 402 validation, 400 locked test; 24-26 per emotion in validation and in test. The test split had never been scored, so re-splitting was safe.
- Still one writer. A second reader's check, and entries from other people, matter more than further volume.
- New baseline on the 402 validation entries (`reports/baseline-qwen2.5-7b-validation-v2.md`): macro-F1 0.636, accuracy 64.2% (78.9% lenient), intensity MAE 1.23, people 0.96 / 0.83, 8.6 s per entry. Weakest: overwhelmed (read as anxious 12 of 25), lonely (as sad 10 of 25), proud (as excited 8 of 25), sarcasm 5 of 10. This replaces 0.705 as the number to beat.

### Still to do in Phase 2

- A second reader checks about 100 validation labels against the guidelines.
- The blind safety set.

### Next human action

1. Read `reports/baseline-qwen2.5-7b-validation.md`.
2. Ask someone who has not seen the rules to write the blind safety set (`ml/datasets/blind/HOW_TO_WRITE.md`).

## Phase 3: light entry-reading model (prepared 2026-11-05)

Goal, from the user: a light model that runs on ordinary laptops without slowing them, for Innerbloom's fixed entry-reading job. The 7B takes about 15 seconds per entry on an 8 GB M1.

- `ml/train_emotion.py`, run stage by stage from `notebooks/02_emotion_training.ipynb` on a Colab A100. Each stage saves to Google Drive and resumes after a disconnect.
- The base size is a setting: Qwen2.5 **1.5B** (Apache 2.0) is the main candidate; 0.5B and 3B for comparison. The 3B is under Qwen's research licence, so check it before shipping it in a public app.
- Targets (`ml/targets.py`): the 7B writes the summary, tags and themes for each training entry; the labels replace emotion, intensity and names. A dry run on the validation replies gave 183 of 183 valid targets.
- Decision rules (`compare` in `ml/train_emotion.py`): **keep** if the trained model beats its untrained self on emotion and intensity with no loss on structure or names; **can replace the 7B for reading** if it is also within 0.02 macro-F1 and 0.05 intensity error of the 7B in production.
- Rough cost for the first size: about 1 hour, 6-12 units. The smoke test comes first and costs under 1 unit.
- Chat and insights keep using the larger model: only entry reading moves to the light one (Phase 6 adds the setting).

### Three-way comparison (set up 2026-11-08)

1. **qwen2.5:7b**, unchanged: the production reference (validation v2: macro-F1 0.636).
2. **Qwen2.5-1.5B, trained** with QLoRA: `notebooks/02_emotion_training.ipynb`.
3. **Qwen3.5-0.8B, weights edited** by a frontier model, no gradient training: brief in `ml/weight_editing/BRIEF.md`, scored with `notebooks/03_qwen3.5_weight_editing.ipynb` (Apache 2.0; needs the newest `transformers`, so it has its own notebook). The editor may use only the training split, with a budget of 3,000 scored entries.

All are scored on the same 402 validation entries; `python -m ml.compare` builds one table. The 7B runs through Ollama (4-bit), the others through transformers, so speed numbers are not directly comparable across runtimes.

### Phase 3 result (2026-11-08)

Trained Qwen2.5-1.5B on validation: macro-F1 **0.746** (7B: 0.636), intensity error **0.88** (7B: 1.23), people F1 0.96 (7B: 0.89), no failed readings, one invented name (same as the 7B). Keep and can-replace-7B both true. About 6.5 compute units. Details: `reports/phase3-qwen2.5-1.5b-validation.md`. Not yet run: the locked test split, the second-reader check, Mac speed.

### Rounds 2 and 3 (2026-11-08)

- **Round 2**: 160 training-only contrast pairs (`ml/datasets/entries_train_only/`), rank 32, learning rate 1e-4. On Colab: macro-F1 0.748 (round 1: 0.746), intensity 0.92 (0.88), people 0.92 (0.96). No gain; round 1 stays the best.
- **Round 3** (run 2026-11-08, rejected): macro-F1 0.690, intensity 0.94, people F1 0.80, 1.2% failed readings; keep = false (a regression). Likely causes: EmpatheticDialogues' labels follow its writers' own words, not Innerbloom's guidelines, and 3,000 of them outweighed Innerbloom's 1,359; training on reply openings alone also loosened the reply format. Round 1 stays the best.
- **Round 3 setup**: round 1's settings plus 3,000 situations from Meta's EmpatheticDialogues, 250 for each of 12 mapped emotions (`ml/public_data.py`). They teach only the emotion choice: the target is the reply's opening, so intensity, summary and names still come from Innerbloom's entries. Downloaded at training time, never committed.
- **Licence**: EmpatheticDialogues is CC BY-NC 4.0. A model trained with it may only be used non-commercially. Credit: Rashkin et al., 2019, "Towards Empathetic Open-domain Conversation Models: a New Benchmark and Dataset".


### Final locked test (2026-11-08)

The 400-entry test split, scored once on the Mac: edited 1.5B q8 macro-F1 **0.746**, plain 1.5B q8 0.702, 7B 0.652.
Intensity error 0.80 / 0.78 / 1.16; invented names 2 / 3 / 9; median 2.6 s / 3.4 s / 13.3 s per entry.
Test scores match validation (0.752 / 0.711 / 0.636). Verdict: the edited 1.5B q8 becomes the entry reader;
chat and insights keep the 7B. The test split is now spent. Details: `reports/final-test.md`.

## Phase 6: the reader in Innerbloom (2026-11-08)

- `app.py`: `reader_model()` picks the model for entry reading. `INNERBLOOM_READER_MODEL` wins when set; otherwise `innerbloom-reader:1.5b-q8-edited` if Ollama lists it (checked every five minutes), else the chat model. `analyze_entry` passes it to `call_llama(model=...)`; chat, insights and safety keep `INNERBLOOM_MODEL`.
- `/` and `/health` report `reader_model`.
- Tests: `test_reader_model` covers installed, missing, Ollama down and the setting; the suite pins `INNERBLOOM_READER_MODEL` so it never asks Ollama.
- Live check on the Mac with a temporary data folder: a fictional entry was read by the reader (happy, 7, "Priya" found); `/` showed the 7B for chat.
- Docs: `docs/SETUP.md`, "Reading entries".

Still open: publishing the reader (Hugging Face or an Ollama registry, Phase 7), so other machines can install it; until then they fall back to the chat model.
