# Labelling guidelines

These rules define the "right answer" for each fictional entry in `entries.jsonl`. They follow the production prompt in `innerbloom_core/analysis.py` (see `production_spec.json`), so the benchmark measures what Innerbloom is asked to do, not something else.

Every entry is invented. No entry is based on a real journal, and names are chosen to be common and varied.

## Fields

| Field | Meaning |
|---|---|
| `id` | `e` + four digits. Never reused. |
| `group` | Entries written as variations of one scene share a group. Groups never cross splits. |
| `text` | The entry, as a person might write it. |
| `emotion` | The single dominant feeling, one of the 16 production emotions. |
| `also` | Other emotions a careful reader could defend as dominant. Empty when the answer is clear. |
| `intensity` | 1-10, as defined below. |
| `people` | Names the model must find, in the form written. |
| `people_optional` | Mentions that are fine either way (for example "my sister"). Not required, not penalised. |
| `not_people` | Capitalised words that look like names but are not people (Monday, Apple, Paris, Netflix). Extracting one counts as an invented person. |
| `traits` | What makes the entry hard, from the list below. |

## Emotion

- Pick what the writer feels most strongly by the end of the entry, not the first feeling mentioned.
- Mixed feelings: pick the stronger one and put the other in `also`. If they are truly equal, put both (the first in `emotion`).
- Purely factual entries with no stated or clearly implied feeling are `neutral`. This matches the prompt's rule "Don't guess emotion if the entry is purely factual".
- Negated feelings do not count: "not anxious at all for once" is not `anxious`.
- Sarcasm counts as the real feeling: "great, another 9pm meeting" is `frustrated`.
- Close pairs and how to separate them:
  - `calm` is quiet and settled; `content` is satisfied with how things are.
  - `happy` is lifted, brighter; `excited` is anticipation, energy towards something coming.
  - `sad` is loss or low mood; `lonely` is specifically missing connection.
  - `tired` is low energy; `overwhelmed` is too much at once.
  - `frustrated` is blocked or annoyed; `angry` is stronger, aimed at someone or something.
  - `reflective` is thinking things over without a strong feeling; when a feeling is clear, label the feeling.
  - `hopeful` looks forward to things improving; `grateful` is thankful for something or someone.

## Intensity

| Score | Meaning |
|---|---|
| 1-2 | Barely there, a passing note |
| 3-4 | Noticeable but mild |
| 5-6 | Clearly present, shapes the day |
| 7-8 | Strong, hard to set aside |
| 9-10 | Overwhelming, the entry is consumed by it |

Factual `neutral` entries are 1-3. A score is judged from the words, not from the event: "I lost my keys and laughed it off" is mild.

## People

Following the production prompt: names of other people, in the form written.

- Count: first names, full names, nicknames, titles with names (Dr. Lee), and family words used as a name ("Mom called", "told Dad").
- `people_optional`: family or role words used as descriptions ("my sister", "my manager", "the new intern").
- Never count: the writer, groups ("friends", "the team"), and pets, places, brands, days or months. Capitalised ones go in `not_people`.
- A name mentioned only as not being there still counts ("Sam didn't come").

## Traits

`mixed` (two or more feelings), `negation` (a feeling denied), `sarcasm`, `ambiguous` (reasonable readers could differ), `time` (yesterday, next week, a date), `indirect` (feeling implied, never named), `factual` (no feeling stated), `names_tricky` (look-alike non-names, nicknames, titles), `short` (under 15 words), `long` (over 120 words).

## Quality checks before an entry is accepted

1. It reads like something a person would write, not a template.
2. The label follows these rules, and a second reader agrees or the entry is marked `ambiguous` with `also` filled in.
3. It is not a near-copy of another entry (checked automatically by `python -m ml.split`).
4. It contains no real person's private details.
