"""Reading one journal entry: the production prompt, schema and parser.

Kept apart from the web app so benchmarks and training notebooks use exactly
what Innerbloom ships. `parse` never raises: a reply it cannot use comes back
as a placeholder reading marked analysis_status "failed".
"""
import json
import re
from typing import Any, Dict, List, Optional

EMOTIONS = [
    "happy", "sad", "anxious", "calm", "grateful", "frustrated",
    "excited", "reflective", "hopeful", "tired", "angry", "content",
    "lonely", "proud", "overwhelmed", "neutral",
]

TEMPERATURE = 0.3


def extract_json(text: str) -> Optional[dict]:
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    blob = match.group(0)
    try:
        return json.loads(blob)
    except Exception:
        cleaned = re.sub(r",\s*([}\]])", r"\1", blob)
        cleaned = cleaned.replace("'", '"')
        try:
            return json.loads(cleaned)
        except Exception:
            return None


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
    # No usable reading (model down, rate-limited or unparsable): keep the
    # placeholders below for the UI, but mark the entry so it is not counted
    # as a genuine neutral feeling and can be read again later.
    failed = not isinstance(data, dict) or "emotion" not in data
    if not isinstance(data, dict):
        data = {}

    emotion = str(data.get("emotion", "neutral")).lower().strip()
    if emotion not in EMOTIONS:
        emotion = "neutral"
    try:
        intensity = int(data.get("intensity", 5))
        intensity = max(1, min(10, intensity))
    except Exception:
        intensity = 5
    summary = str(data.get("summary", "")).strip()[:280]
    tags = data.get("tags") or []
    themes = data.get("themes") or []
    people = data.get("people") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",")]
    if isinstance(themes, str):
        themes = [t.strip() for t in themes.split(",")]
    if isinstance(people, str):
        people = [p.strip() for p in people.split(",")]
    tags = [re.sub(r"[^a-z0-9\-]", "", str(t).lower())[:24] for t in tags if t][:5]
    tags = [t for t in tags if t]
    themes = [str(t).strip()[:40] for t in themes if t][:3]
    # People are case-preserved (Title Case), de-duplicated, max 6
    seen_people = set()
    cleaned_people: List[str] = []
    for p in people:
        if not p: continue
        name = re.sub(r"[^A-Za-z\- '’.]", "", str(p)).strip()
        if not name or len(name) > 40:
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
