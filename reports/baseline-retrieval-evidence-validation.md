# Baseline: memory search and evidence checking

Measured on 2026-11-05 on the validation halves, before any change. Fictional data only.

## Memory search

Data: `ml/datasets/retrieval/`. Three fictional journals of 36 entries over five to six months, with recurring people and threads, and 54 questions whose answering entries are marked (2 = answers it, 1 = related). Dates are stored as days before today. Journals a and b (36 questions) are for development; journal c (18 questions) is the locked test.

Run with `python -m ml.retrieval_eval`. Entries carry their text only, without the model's summary and tags.

### Keyword search (`retrieve_relevant`)

| Metric | Result |
|---|---|
| An answering entry in the top 5 | 80.6% |
| Recall of all marked entries in the top 5 | 65.5% |
| Mean reciprocal rank | 0.578 |
| nDCG@5 | 0.532 |
| Top-5 results inside the asked time window | 27% |

| Question type | Questions | Answer in top 5 | Recall@5 |
|---|---|---|---|
| Direct lookups | 7 | 100% | 100% |
| Different wording from the entry | 13 | 84.6% | 69.9% |
| About a person | 17 | 76.5% | 58.7% |
| About a time period | 7 | 71.4% | 66.7% |
| Needing several entries | 11 | 72.7% | 32.4% |

Keyword search finds direct lookups well but misses most entries for questions that need several, and it ignores time beyond a small boost for the last month.

### Meaning search (`retrieve_similar`) and the agent's search tool

Not measured yet: they need the embedding model `mxbai-embed-large` (about 670 MB), which is not installed in Ollama on this Mac. Innerbloom's chat memory uses it too, so it is needed to run the app as designed.

## Evidence checking

Data: `ml/datasets/evidence/claims.jsonl`. 120 fictional claims of the kind the insight engines write (patterns, causes, trends, values, people, intentions), each with dated journal snippets and a label: supported (66), contradicted (31) or insufficient (23: too thin, unrelated, or an overreach such as a diagnosis). Claims sharing evidence stay in one half; 67 are for development, 53 locked.

Run with `python -m ml.evidence_eval`: `qwen2.5:7b` as a plain judge, given only the three label definitions.

| Metric | Result |
|---|---|
| Accuracy | 73.1% |
| Macro-F1 | 0.588 |
| Claims not supported by the entries, accepted as supported | 39.3% (11 of 28) |
| Valid claims rejected | 0% (0 of 39) |

| Correct label | Judged supported | Judged contradicted | Judged insufficient |
|---|---|---|---|
| supported (39) | 39 | 0 | 0 |
| contradicted (14) | 3 | 4 | 7 |
| insufficient (14) | 8 | 0 | 6 |

The judge leans towards agreeing. Its main failure is accepting claims built on too little: 8 of 14 such claims, and 3 of 4 sweeping "always / every" claims, were waved through. It handled hedged claims, values and intentions well.

## What this means

- **Phase 4 (memory):** the clearest gaps are questions that need several entries, and time. Meaning search must be measured before deciding whether a reranker is worth training.
- **Phase 5 (verifier):** the target is clear. A verifier must cut the 39% of unsupported claims accepted, especially overreach from thin evidence, without starting to reject valid ones.

## Caveats

- Small sets: 36 and 67 items, one writer, not yet checked by a second reader.
- The evidence labels involve judgement, particularly between contradicted and insufficient.
