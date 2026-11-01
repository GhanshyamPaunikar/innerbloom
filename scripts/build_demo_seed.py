"""Build the sample journal used by the public website demo.

Writes demo_seed/ (journal, insights, people, meta). Each visitor's sandbox
starts from a copy of it, with dates moved so the last day is today. The
entries are written by hand in scripts/demo_entries.json; Gemini computes
their embeddings and runs the four insight engines over them, exactly as it
would for a real journal.

Run once, then review and commit demo_seed/:
    GEMINI_API_KEY=... python scripts/build_demo_seed.py
"""
import json
import os
import random
import shutil
import sys
import tempfile
import time
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "demo_seed"
WORK = Path(tempfile.mkdtemp(prefix="innerbloom-seed-"))
os.environ.update(INNERBLOOM_PROVIDER="gemini", INNERBLOOM_DATA_DIR=str(WORK))
sys.path.insert(0, str(ROOT))
import app  # noqa: E402

CRM = {  # what a visitor might have filled in on the People page
    "johndoe": {"relationship": "friend", "cadence_days": 14, "birthday": "06-14",
                "notes": ["Loves the Saturday market. Ask about his new job."]},
    "janesmith": {"relationship": "family", "cadence_days": 7, "birthday": "03-02",
                  "notes": ["Engagement party went beautifully. Help with wedding playlist."]},
    "mom": {"relationship": "family", "cadence_days": 7, "birthday": None, "notes": []},
    "alexjohnson": {"relationship": "colleague", "cadence_days": None, "birthday": None, "notes": []},
    "mariagarcia": {"relationship": "mentor", "cadence_days": 14, "birthday": None, "notes": []},
    "samlee": {"relationship": "friend", "cadence_days": 7, "birthday": "09-21", "notes": []},
}

def paced(fn, pause):
    """Space out model calls to stay inside free-tier rate limits."""
    def wrapper(*args, **kwargs):
        time.sleep(pause)
        return fn(*args, **kwargs)
    return wrapper


def main():
    if not app.GEMINI_API_KEY:
        sys.exit("Set GEMINI_API_KEY first.")
    app.call_llama = paced(app.call_llama, 4.5)
    app.embed = paced(app.embed, 0.7)
    random.seed(40)
    anchor = date.today()
    written = json.loads((ROOT / "scripts" / "demo_entries.json").read_text())
    entries = []
    for i, item in enumerate(written):
        day = anchor - timedelta(days=len(written) - 1 - i)
        hour, minute = random.choice([(7, 40), (8, 15), (12, 30), (18, 50), (21, 10), (22, 35)])
        entry = {
            "id": f"demo{i + 1:02d}",
            **{k: item[k] for k in ("title", "text", "emotion", "intensity", "tags", "themes", "people")},
            "summary": item["text"].split(". ")[0].rstrip(".") + ".",
            "user_mood": None,
            "word_count": len(item["text"].split()),
            "timestamp": datetime.combine(day, datetime.min.time()).replace(hour=hour, minute=minute).isoformat(),
        }
        entry["embedding"] = app.embed(app._entry_embed_text(entry))
        entry["embedding_version"] = app.EMBED_VERSION
        app._embed_entry_chunks(entry)
        if not entry["embedding"]:
            sys.exit(f"Day {i + 1}: Gemini embedding failed.")
        entries.append(entry)
        app._upsert_people_from_entry(entry)
        print(f"{day} {entry['emotion']:>11} {entry['title']}", flush=True)
    app.save_file(app.JOURNAL_FILE, entries)

    store = app._load_people_store()
    for key, extra in CRM.items():
        if key in store:
            notes = [{"id": f"note-{key}-{n}", "text": t,
                      "created_at": (datetime.now() - timedelta(days=3 + n)).isoformat()}
                     for n, t in enumerate(extra["notes"])]
            store[key].update({k: v for k, v in extra.items() if k != "notes"}, notes=notes)
    app._save_people_store(store)

    for name, run in (("contradictions", lambda: app.compute_contradictions(window_days=60)),
                      ("triggers", lambda: app.compute_triggers(window_days=90)),
                      ("wellbeing", lambda: app.compute_wellbeing(window_days=14)),
                      ("narrative", lambda: app.compute_narrative(window_days=120))):
        run()
        print("insight:", name, flush=True)

    shutil.rmtree(OUT, ignore_errors=True)
    OUT.mkdir()
    for name in ("journal.json", "insights.json", "people.json"):
        if (WORK / name).exists():
            shutil.copy(WORK / name, OUT / name)
    (OUT / "meta.json").write_text(json.dumps({"anchor": anchor.isoformat(), "model": app.MODEL}, indent=2))
    shutil.rmtree(WORK, ignore_errors=True)
    print("Wrote", OUT)


if __name__ == "__main__":
    main()
