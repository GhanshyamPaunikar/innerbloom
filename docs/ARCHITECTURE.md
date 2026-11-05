# How Innerbloom works

A plain HTML, CSS and JavaScript page (`index.html` and `assets/`) talks to `app.py` (FastAPI), which talks to a model running in Ollama on the same computer. Everything is stored as JSON in `./data/`. There is no build step and no `node_modules`. Pieces that do not need the web app live in `innerbloom_core/`: the entry-reading prompt, schema and parser (`analysis.py`), used by the app and by benchmarks alike, and crisis detection (`safety.py`).

## Reading an entry

Every saved entry is read once by the model and returned in a strict JSON shape: `emotion`, `intensity` (1 to 10), `summary`, `tags`, `themes` and `people`. Emotion comes from a fixed list of 16 (happy, sad, anxious, calm, grateful, frustrated, excited, reflective, hopeful, tired, angry, content, lonely, proud, overwhelmed, neutral) so stats stay consistent over months.

If the model cannot be reached or its reply cannot be read, the entry is still saved but marked `analysis_status: "failed"` with the error. It shows as "not read yet", stays out of feelings, intensity charts and insights, and can be read again later from Entries (`POST /journal/reanalyze`).

## Memory that understands meaning

- Entries are embedded with `mxbai-embed-large`.
- Long entries are split into paragraph-sized chunks, each embedded on its own. Search takes the best chunk, so a long entry does not dilute itself.
- Search is hybrid: keywords plus similarity of meaning.
- Every embedding is stamped with the model that made it. Switch embedding models and Innerbloom re-embeds as it goes.

## The agent

Chat (`/chat/agent`) is a real agent, streamed as JSONL so you watch each step:

1. **Classify.** Small talk, a follow-up, or a real question?
2. **Plan.** The model chooses tools, or asks you to clarify.
3. **Tools.** `search_entries`, `get_entry`, `list_themes`, `period_summary`, `emotion_extremes`.
4. **Draft.** The model writes the answer and streams it, citing entries as `[cite:id]`, which become clickable sources.

Three voices change the system prompt: **Companion** (a warm friend who has read it all), **Observer** (quiet and evidence-first) and **Challenger** (kind, but names the gap between what you say and what you do).

## Insight engines

Four engines, cached in `data/insights.json`, refreshed on request or in the background every few new entries:

- **Contradictions.** Real intention sentences ("I'll stop checking email at night") are found in your text first; the model only matches them to later entries, and anything not grounded in your words is dropped.
- **Emotional triggers.** Which tags and people reliably lift or drain your mood, scored statistically, explained in plain language.
- **Wellbeing radar.** Burnout (a 14-day trend) and a low spiral (a 7-day trajectory), each rated ok, watch, elevated or high, or "not enough to read yet" with fewer than four entries. Levels come from the numbers; the model only writes the one-line read for a flagged signal, and entries that could not be read never count.
- **Your story.** Identity, values in action, the tensions you hold, and who you are becoming.

## Memory map

The map is computed in the browser from `/journal`. Entries are linked when they share at least two themes or tags; groups form by weighted label propagation and are named from their two most common terms. `/graph` also builds a server-side graph with IDF-weighted similarity and model-named clusters.

## People

Two layers, merged when read:

- **From your entries:** mentions, first and last seen, dominant emotion, average intensity, themes, recent entries.
- **What you add** (`data/people.json`): relationship, birthday, check-in cadence, dated notes, pinned or hidden.

Anyone you name is added when you save. Each person also gets simple signals (days since last mentioned, overdue for a check-in, birthday soon) that drive the reminders.

## Care

Helplines (iCall, AASRA, 988, Samaritans, Find a Helpline) are attached when writing suggests self-harm or suicidal thoughts, in chat, while writing and on save. The reply itself is never withheld. It is a support prompt, not a diagnosis.

- **Clear phrases** ("thinking about ending my life", "wish I was dead") show the full list straight away, without the model.
- **Ambiguous or negated phrases** ("cut myself cooking", "end things with Sam", "I'm not suicidal") and heavy feelings ("hopeless", "numb") go to a small classifier first.
- **If the classifier cannot answer**, the gentle version of the list is shown. An unreachable model is never read as "safe".
- The writing page checks clear phrases as you pause (`POST /safety/check`, no model call); saving runs the full check.

## Storage and privacy

- Each data file has its own lock. Every load-change-save holds it, and model calls happen outside it, so a slow reading never blocks other saves.
- Writes go to a uniquely named temporary file that then replaces the original, so a crash never leaves a half-written journal.
- Background embedding passes write back only their vectors, matched by entry id, so entries saved meanwhile are kept.
- Deleting an entry also removes it from cached insights, including any insight that quoted it.
- The API has no login, so it answers only requests addressed to this computer (`127.0.0.1`, `localhost`, `::1`) and coming from its own page or another page on this computer. This blocks other websites and DNS rebinding. `INNERBLOOM_ALLOWED_HOSTS` adds names for a custom setup.
- Background insight jobs report `queued`, `running`, `idle` or `failed`, with the last error and its time, at `/insights/status`.

## The page

The interface is a warm, quiet room: cream architecture, frosted navigation, near-opaque ivory pages for reading and writing, charcoal controls and one orange accent. Fonts, images, styles and scripts are bundled, with no CDN or analytics. Settings can switch to a plain background or fully opaque panels. Design notes and accessibility work are in [UI-DESIGN.md](UI-DESIGN.md).
