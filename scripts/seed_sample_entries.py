"""Add clearly marked fictional entries to the local journal for UI exploration.

Run explicitly: python scripts/seed_sample_entries.py
Existing entries are preserved. Stable IDs make repeated runs idempotent.
"""
import json
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = [
    (0, "A song for the walk home", "calm", 3, ["music", "walking", "rest"], ["making space", "everyday rituals"], "I put on a familiar playlist and took the longer route home. The day had been full of small demands, but walking gave each thought a little room. I arrived feeling less rushed. Tomorrow I want to leave ten minutes between finishing work and starting the evening."),
    (1, "Closing the laptop on time", "hopeful", 5, ["work", "boundaries", "rest"], ["making space", "sustainable work"], "I stopped working at the time I had planned, even though the task was not perfect. There was a moment of guilt before the relief arrived. Cooking dinner without checking notifications felt like a small promise kept. I want to remember that leaving something for tomorrow can be a deliberate choice."),
    (2, "The playlist I keep returning to", "reflective", 4, ["music", "attention", "routine"], ["everyday rituals", "self awareness"], "The same songs have been keeping me company all week. I noticed that I choose familiar music when I need to concentrate and quieter tracks when I need to unwind. I am curious about the memories attached to those choices. This evening I listened without doing anything else."),
    (3, "Too many open tabs", "anxious", 7, ["work", "focus", "boundaries"], ["sustainable work", "attention"], "I agreed to another small task before looking at the rest of my day. By the afternoon every unfinished thing felt equally urgent. Writing down three priorities helped. Next time I want to pause before saying yes and ask what would have to move to make room."),
    (5, "Coffee without a deadline", "grateful", 4, ["friends", "connection", "rest"], ["making space", "relationships"], "I met a friend for coffee and left my phone in my bag. We talked about ordinary things, and that was enough. I have been treating catching up like another task to schedule efficiently. Today reminded me that unhurried time together is part of the point."),
    (6, "A quiet morning outside", "calm", 2, ["walking", "nature", "attention"], ["everyday rituals", "making space"], "The park was almost empty when I arrived. I walked slowly and noticed the light on the trees instead of counting steps. There was no dramatic change in my mood, just a softer start. I would like to make this a regular morning practice rather than waiting for a free day."),
    (8, "When everything felt urgent", "frustrated", 7, ["work", "boundaries", "focus"], ["sustainable work", "attention"], "Notifications kept pulling me away from the one task I wanted to finish. I felt irritated with other people, then realised I had never made my availability clear. Tomorrow I will block an hour for focused work and tell the team when I will be back online."),
    (10, "One thing finished", "proud", 6, ["work", "focus", "progress"], ["sustainable work", "personal growth"], "I finished a piece of work that had been hanging over me. Breaking it into a smaller first step made the rest less intimidating. I am pleased with the result, but even more pleased that I did not wait to feel completely ready. Progress felt quiet today, and still counted."),
    (12, "Making room for people", "hopeful", 5, ["friends", "connection", "boundaries"], ["relationships", "making space"], "I reached out to someone I had meant to message for weeks. The conversation was easy once it began. I often say that relationships matter, then give them whatever time is left after work. I want to plan one evening around a person instead of another unfinished task."),
    (14, "An evening without scrolling", "calm", 3, ["rest", "attention", "routine"], ["everyday rituals", "making space"], "I put my phone away after dinner and read a few pages. At first I kept reaching for it without thinking. The urge passed, and the evening felt longer. I do not need every night to look like this, but I like knowing that a quieter ending is available."),
    (16, "Music and a fresh page", "excited", 6, ["music", "creativity", "focus"], ["personal growth", "attention"], "A new album made me want to sketch again. I spent half an hour trying ideas without deciding whether any of them were good. It felt different from making something for a deadline. I want to protect a little time for work that has no audience and no score."),
    (19, "The plan that needed breathing room", "tired", 6, ["work", "rest", "boundaries"], ["sustainable work", "making space"], "I filled every gap in the calendar and then wondered why the day felt heavy. Nothing terrible happened; there was simply no space to reset. I moved one optional task to next week and took a walk. A workable plan needs room for being a person, not just completing a list."),
    (22, "Dinner and an honest conversation", "grateful", 5, ["friends", "connection", "attention"], ["relationships", "self awareness"], "Over dinner I admitted that I had been distracted lately. My friend listened without trying to solve the whole situation. Saying it aloud helped me see which parts were practical problems and which parts were pressure I had added myself. I left feeling understood rather than fixed."),
    (25, "Choosing the slower route", "reflective", 4, ["walking", "nature", "rest"], ["making space", "everyday rituals"], "I nearly skipped the walk because I wanted to get home quickly. Taking the slower route turned out to be the best part of the afternoon. It gave me a clear boundary between the working day and the evening. I want to notice small transitions like this more often."),
    (29, "Saying yes too quickly", "anxious", 7, ["work", "boundaries", "connection"], ["sustainable work", "self awareness"], "I said yes to helping before checking what I already had to do. I like being dependable, but I do not want dependability to mean being available all the time. I wrote a message setting a realistic deadline. It felt uncomfortable and also more honest."),
    (34, "A small creative habit", "hopeful", 5, ["creativity", "routine", "progress"], ["personal growth", "everyday rituals"], "Ten minutes of sketching felt easier than the ambitious plan I kept postponing. I am trying to make the habit small enough to fit an ordinary day. The page was uneven and unfinished. I enjoyed making it anyway, and that seems like a useful place to begin."),
    (40, "What I want my weeks to feel like", "reflective", 4, ["rest", "friends", "work"], ["making space", "relationships", "sustainable work"], "I want my weeks to contain focused work, unhurried conversations, and time outside. Looking at the calendar, work currently gets the clearest place. I am experimenting with planning rest and connection first on one day each week. This is an intention to return to, not a rule to get perfect."),
    (46, "A different kind of productive", "content", 3, ["nature", "rest", "creativity"], ["making space", "personal growth"], "I spent the afternoon outside and came home with a few ideas for a drawing. Nothing was checked off the work list. The day still felt worthwhile. I want to leave room for experiences that feed my attention without needing to turn them into an achievement."),
]

GENERATED_TEMPLATES = [
    ("A softer start", "calm", 3, ["routine", "rest"], ["everyday rituals", "making space"], "I gave the morning a little more room than usual. The quieter pace made it easier to notice what I actually needed before the day gathered speed."),
    ("A useful pause", "reflective", 4, ["attention", "boundaries"], ["self awareness", "making space"], "I paused before answering the next request and noticed the difference between urgency and importance. The pause did not solve everything, but it made my choice feel like mine."),
    ("Outside for a while", "hopeful", 5, ["walking", "nature"], ["everyday rituals", "personal growth"], "A little time outside changed the texture of the afternoon. I came back with fewer looping thoughts and one small idea I want to carry forward."),
    ("A song that stayed", "grateful", 4, ["music", "attention"], ["everyday rituals", "self awareness"], "One song kept returning today. I let it play without multitasking and remembered that attention can be a form of care."),
    ("The honest version", "anxious", 6, ["work", "boundaries"], ["sustainable work", "self awareness"], "I wrote down what was actually difficult instead of describing the day as simply busy. Naming the friction made the next step feel more manageable."),
    ("Making something small", "excited", 6, ["creativity", "progress"], ["personal growth", "attention"], "I chose a small creative task and finished it before judging it. The result was imperfect, but the act of beginning felt energising."),
    ("Room to recover", "tired", 5, ["rest", "boundaries"], ["sustainable work", "making space"], "I noticed I was trying to earn rest instead of treating it as part of the plan. I made one thing optional and felt my shoulders drop."),
    ("A good conversation", "content", 4, ["friends", "connection"], ["relationships", "self awareness"], "A simple conversation gave the day a sense of shape. I listened more carefully than usual and left feeling connected rather than hurried."),
    ("One clear priority", "proud", 6, ["focus", "work"], ["sustainable work", "personal growth"], "Choosing one clear priority made the rest of the list less loud. I did not finish everything, but I finished the thing that mattered most."),
    ("A quieter ending", "calm", 2, ["rest", "routine"], ["making space", "everyday rituals"], "The evening did not need to be productive. I put a little distance between myself and the day, and that was enough."),
]


def seed():
    data_dir = Path(os.environ.get("INNERBLOOM_DATA_DIR", ROOT / "data"))
    path = data_dir / "journal.json"
    data_dir.mkdir(parents=True, exist_ok=True)
    original = path.read_bytes() if path.exists() else None
    entries = json.loads(original) if original is not None else []
    if not isinstance(entries, list):
        raise ValueError("Journal must contain an entry list; no changes made.")
    existing = {e["id"] for e in entries}
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    added = []
    for days, title, emotion, intensity, tags, themes, body in SAMPLES:
        entry_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "reflect-ui-samples-v1/" + title))
        if entry_id in existing:
            continue
        text = "Fictional sample entry for exploring Innerbloom’s features.\n\n" + body
        added.append({"id": entry_id, "title": "[Sample] " + title, "text": text,
                      "summary": body.split(". ")[0] + ".", "emotion": emotion,
                      "intensity": intensity, "tags": tags, "themes": themes,
                      "user_mood": None, "word_count": len(text.split()),
                      "timestamp": (now - timedelta(days=days)).replace(hour=14, minute=30, second=0, microsecond=0, tzinfo=None).isoformat(),
                      "embedding": None, "sample_batch": "reflect-ui-samples-v1",
                      "analysis_source": "hand-authored fictional test data"})

    # Complete a 150-day fictional fixture without creating duplicate days.
    occupied_days = set()
    for entry in entries + added:
        if not str(entry.get("sample_batch", "")).startswith("reflect-ui-samples"):
            continue
        if isinstance(entry.get("sample_day"), int):
            occupied_days.add(entry["sample_day"])
            continue
        try:
            stamp = datetime.fromisoformat(entry["timestamp"]).date()
            occupied_days.add((now.date() - stamp).days)
        except (KeyError, TypeError, ValueError):
            continue

    for days in range(150):
        if days in occupied_days:
            continue
        title, emotion, intensity, tags, themes, body = GENERATED_TEMPLATES[days % len(GENERATED_TEMPLATES)]
        entry_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"reflect-ui-samples-v2/day-{days}"))
        if entry_id in existing or any(item["id"] == entry_id for item in added):
            occupied_days.add(days)
            continue
        text = "Fictional sample entry for exploring Innerbloom’s features.\n\n" + body
        added.append({"id": entry_id, "title": "[Sample] " + title,
                      "text": text, "summary": body.split(". ")[0] + ".",
                      "emotion": emotion, "intensity": intensity, "tags": tags,
                      "themes": themes, "user_mood": None, "word_count": len(text.split()),
                      "timestamp": (now - timedelta(days=days)).replace(hour=14, minute=30, second=0, microsecond=0, tzinfo=None).isoformat(),
                      "embedding": None, "sample_batch": "reflect-ui-samples-v2",
                      "sample_day": days, "analysis_source": "generated fictional UI fixture"})
        occupied_days.add(days)
    if added:
        if (path.read_bytes() if path.exists() else None) != original:
            raise RuntimeError("Journal changed while preparing samples; rerun safely.")
        if original is not None:
            backup = data_dir / "journal.before-ui-samples.json"
            if not backup.exists():
                backup.write_bytes(original)
        temp = data_dir / "journal.samples.tmp"
        temp.write_text(json.dumps(entries + added, indent=2, ensure_ascii=False))
        temp.replace(path)
    print(f"Added {len(added)} fictional sample entries; preserved {len(entries)} existing entries.")

if __name__ == "__main__":
    seed()
