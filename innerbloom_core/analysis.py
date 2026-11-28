"""Reading one journal entry: the production prompt, schema and parser.

Kept apart from the web app so benchmarks and training notebooks use exactly
what Innerbloom ships. `parse` never raises: a reply it cannot use comes back
as a placeholder reading marked analysis_status "failed".
"""
import json
import re
import unicodedata
from typing import Any, Dict, List

EMOTIONS = [
    "happy", "sad", "anxious", "calm", "grateful", "frustrated",
    "excited", "reflective", "hopeful", "tired", "angry", "content",
    "lonely", "proud", "overwhelmed", "neutral",
]

TEMPERATURE = 0.3


def _loads(blob: str) -> Any:
    try:
        return json.loads(blob)
    except Exception:
        return None


def extract_json(text: str) -> Any:
    """The JSON in a model reply: the whole reply, else the {...} inside it, then
    the same without trailing commas, and with ' swapped for " only as a last
    resort (it breaks any apostrophe, as in "Mom's call"). Callers must check
    the type: a reply can be any JSON value."""
    if not text:
        return None
    whole = _loads(text)
    if whole is not None:
        return whole
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    blob = match.group(0)
    no_trailing = re.sub(r",\s*([}\]])", r"\1", blob)
    for candidate in (blob, no_trailing, no_trailing.replace("'", '"')):
        value = _loads(candidate)
        if value is not None:
            return value
    return None


def _items(value) -> list:
    """A list field from the reply: "a, b" is split; anything else that isn't a
    list (true, 3, an object) counts as empty."""
    if isinstance(value, str):
        return [v.strip() for v in value.split(",")]
    return value if isinstance(value, list) else []


# Placeholders a model writes when nobody is named.
_NOBODY = {"none", "n/a", "na", "nobody", "no one", "null", "unknown", "nil"}


def _tag(value) -> str:
    """Lowercase letters (any script), digits and '-'; 'Café' stays 'café'."""
    text = unicodedata.normalize("NFC", str(value)).lower()
    return "".join(ch for ch in text if ch.isalnum() or ch == "-"
                   or unicodedata.category(ch) in ("Mn", "Mc"))[:24]


def _name(value) -> str:
    """Letters in any script plus space, '-', apostrophes and '.'; 'Tomás' stays 'Tomás'."""
    text = unicodedata.normalize("NFC", str(value))
    return "".join(ch for ch in text if ch.isalpha() or ch in " -'’."
                   or unicodedata.category(ch) in ("Mn", "Mc")).strip()


def person_key(name: str) -> str:
    """One key per person: case and Latin accents folded ('José' ~ 'Jose'),
    other scripts kept whole, everything else dropped."""
    out = []
    for ch in unicodedata.normalize("NFD", (name or "").lower()):
        if unicodedata.category(ch) == "Mn" and out and out[-1].isascii():
            continue  # an accent on a Latin letter
        if ch.isalpha() or unicodedata.category(ch) in ("Mn", "Mc"):
            out.append(ch)
    return unicodedata.normalize("NFC", "".join(out))


def build_prompt(text: str) -> str:
    return f"""You classify one journal entry. Return ONLY a compact JSON object. No prose. No fences.

Schema (every field required, even if empty):
{{
  "emotion":   "the dominant feeling — exactly one of: {', '.join(EMOTIONS)}",
  "intensity": "integer 1-10. 1 = barely felt, 5 = clearly present, 10 = overwhelming",
  "summary":   "one concrete sentence, <= 20 words. Say what HAPPENED or what the writer felt — never start with 'The writer' or 'They'",
  "tags":      "2-4 lowercase single-word nouns naming what the entry is about (work, sleep, partner, anxiety, running). No verbs. No adjectives. No '#'",
  "themes":    "1-3 short phrases (1-4 words each) for the deeper pattern (e.g. 'work boundaries', 'fear of being seen', 'rebuilding routine'). Not just rewordings of tags",
  "people":    "names of OTHER people the writer mentioned, in the form they wrote (Mom, Sam, dad, Dr. Lee). Skip the writer themselves and skip generic words like 'people' / 'friends'. Omit if nobody named. Never invent."
}}

Rules:
- Don't guess emotion if the entry is purely factual — use 'neutral'.
- Tags must actually appear (literally or by clear paraphrase) in the entry.
- Don't include 'journal', 'entry', 'writing' as tags — those describe the act, not the content.

Entry:
\"\"\"{text}\"\"\"

JSON:"""


def error_text(raw: str) -> str:
    raw = (raw or "").strip()
    if raw.startswith("[") and raw.endswith("]"):
        return raw.strip("[]")[:200]
    return "The model's reply could not be read as an analysis." if raw else "The model returned nothing."


def parse(raw: str) -> Dict[str, Any]:
    data = extract_json(raw)
    if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict):
        data = data[0]  # a reading wrapped in a list
    # No usable reading (model down, rate-limited or unparsable): keep the
    # placeholders below for the UI, but mark the entry so it is not counted
    # as a genuine neutral feeling and can be read again later.
    failed = not isinstance(data, dict) or "emotion" not in data
    if not isinstance(data, dict):
        data = {}

    emotion = re.sub(r"[^a-z]", "", str(data.get("emotion") or "").lower())  # "Anxious." -> anxious
    if emotion not in EMOTIONS:
        failed = True  # "stressed" is not a reading the app can count
        emotion = "neutral"
    number = re.match(r"\s*(\d+(?:\.\d+)?)", str(data.get("intensity", "")))
    intensity = max(1, min(10, round(float(number.group(1))))) if number else 5
    summary = str(data.get("summary") or "").strip()[:280]
    tags = _items(data.get("tags"))
    themes = _items(data.get("themes"))
    people = _items(data.get("people"))
    tags = [_tag(t) for t in tags if t and not isinstance(t, (dict, list))][:5]
    tags = [t for t in tags if t]
    themes = [str(t).strip()[:40] for t in themes if t and not isinstance(t, (dict, list))][:3]
    # People are case-preserved (Title Case), de-duplicated, max 6
    seen_people = set()
    cleaned_people: List[str] = []
    for p in people:
        if isinstance(p, dict):
            p = p.get("name") or ""
        if not p or isinstance(p, list): continue
        name = _name(p)
        if not name or len(name) > 40 or name.lower() in _NOBODY:
            continue
        # Title case but keep all-caps initials etc.
        key = name.lower()
        if key in seen_people:
            continue
        seen_people.add(key)
        cleaned_people.append(name)
        if len(cleaned_people) >= 6:
            break

    return {
        "emotion": emotion,
        "intensity": intensity,
        "summary": summary,
        "tags": tags,
        "themes": themes,
        "people": cleaned_people,
        "analysis_status": "failed" if failed else "ok",
        "analysis_error": error_text(raw) if failed else None,
    }
