# Writing the blind safety set

These sentences test whether Innerbloom notices when someone may be in danger. They only work as a test if the rules have never been shaped around them, so they must be written by someone who has **not** read `innerbloom_core/safety.py`, `ml/datasets/safety_cases.jsonl` or `tests/test_safety.py`.

The scoring script only ever prints totals for this folder, never the sentences, so the rules can be measured without anyone tuning them to these exact words.

## What to write

Make three plain text files in this folder, **one sentence per line**, written the way a person might write in a private journal. Typos, slang, lowercase and very short lines are all welcome. Everything must be invented.

| File | What goes in it | How many |
|---|---|---|
| `crisis.txt` | The writer may be thinking about dying or hurting themselves, now or soon, said directly or only hinted at. | 40 or more |
| `distress.txt` | The writer is struggling badly (hopeless, numb, can't cope) but there is no sign of wanting to die or self-harm. | 20 or more |
| `harmless.txt` | Sentences that *sound* alarming but are not: figures of speech, injuries, risk that is clearly over, a film, a book, a course, someone else's story. | 40 or more |

Try to vary the wording as much as you can. Think about how different people, ages and moods would put it.

If writing these is upsetting, stop. It is fine to do it over several days, or to ask someone else.

## Then

Run:

```bash
.venv/bin/python -m ml.safety_eval
```

The report shows how many sentences in each file got help and how many did not, without showing which ones.
