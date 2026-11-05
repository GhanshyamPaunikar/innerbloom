# Innerbloom AI v2: progress

Working branch: `feature/innerbloom-ai-v2`. `main` stays stable until a phase is reviewed and merged.

| Phase | Scope | GPU budget | Status |
|---|---|---|---|
| 0 | Audit, backup, branch | 0 | Done (2026-11-05) |
| 1 | Data and security stability | 0 | Next |
| 2 | Fictional benchmark and baseline | 15 units | Not started |
| 3 | Emotion model QLoRA | 45 units | Not started |
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

### Next human action

Review the issues above and approve Phase 1. No GPU is needed until Phase 2.
