"""Public demo mode: private sandboxes, moved dates, Spotify off, AI limits.

Runs the backend in a child process so its sandbox settings never leak into
the other tests. Gemini and embeddings are mocked; nothing leaves the machine.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CHILD = r'''
import json, os, sys
sys.path.insert(0, os.environ["ROOT"])
from unittest.mock import patch
import app
from fastapi.testclient import TestClient

out = {}
a, b = TestClient(app.app), TestClient(app.app)
first = a.get("/journal")
out["cookie"] = "innerbloom_sandbox=" in first.headers.get("set-cookie", "")
entry = first.json()["entries"][0]
out["timestamp"], out["text"] = entry["timestamp"][:10], entry["text"]
fake = {"emotion": "happy", "intensity": 5, "summary": "x", "tags": [], "themes": [], "people": []}
with patch.object(app, "analyze_entry", return_value=fake), patch.object(app, "embed", return_value=None):
    a.post("/save", json={"text": "Only visitor A should see this."})
out["a_count"] = len(a.get("/journal").json()["entries"])
out["b_count"] = len(b.get("/journal").json()["entries"])
out["spotify_status"] = b.get("/spotify/status").json()
out["spotify_config"] = b.post("/spotify/config", json={}).status_code
out["docs"] = a.get("/docs").status_code
far = TestClient(app.app, headers={"X-Timezone": "Pacific/Kiritimati"})  # UTC+14
far_entry = far.get("/journal").json()["entries"][0]
out["far_seed_day"], out["far_seed_time"] = far_entry["timestamp"][:10], far_entry["timestamp"]
with patch.object(app, "analyze_entry", return_value=fake), patch.object(app, "embed", return_value=None):
    out["far_saved_day"] = far.post("/save", json={"text": "Written far ahead."}).json()["entry"]["timestamp"][:10]

class Reply:
    status_code = 200
    def json(self):
        return {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}
sent = []
with patch.object(app.requests, "post", side_effect=lambda *x, **k: sent.append(k.get("headers")) or Reply()):
    app._CLIENT.set(("f" * 32, "203.0.113.9"))
    out["replies"] = [app.call_llama("hi") for _ in range(3)]
out["sent"] = len(sent)
out["key_header"] = bool(sent and sent[0].get("x-goog-api-key") == "test-key")
print(json.dumps(out))
'''


class PublicDemoTests(unittest.TestCase):
    def test_sandboxes(self):
        with tempfile.TemporaryDirectory() as tmp:
            seed = Path(tmp, "seed")
            seed.mkdir()
            (seed / "meta.json").write_text(json.dumps({"anchor": "2026-01-10"}))
            (seed / "journal.json").write_text(json.dumps([{
                "id": "demo01", "timestamp": "2026-01-10T09:00:00", "title": "Seed",
                "text": "Lunch with John Doe on 2026-01-09.", "emotion": "calm", "intensity": 4,
                "tags": [], "themes": [], "people": ["John Doe"], "summary": "s", "word_count": 6}]))
            env = dict(os.environ, ROOT=str(ROOT), INNERBLOOM_SANDBOX="1", INNERBLOOM_PROVIDER="gemini",
                       GEMINI_API_KEY="test-key", INNERBLOOM_DATA_DIR=str(Path(tmp, "data")),
                       INNERBLOOM_SEED_DIR=str(seed), INNERBLOOM_AI_PER_VISITOR="2")
            run = subprocess.run([sys.executable, "-c", CHILD], env=env, capture_output=True, text=True, timeout=120)
            self.assertEqual(run.returncode, 0, run.stderr[-2000:])
            out = json.loads(run.stdout.strip().splitlines()[-1])

        from datetime import date, timedelta
        today = date.today()
        self.assertTrue(out["cookie"])
        self.assertEqual(out["timestamp"], today.isoformat())  # the sample ends today
        self.assertIn((today - timedelta(days=1)).isoformat(), out["text"])
        self.assertEqual((out["a_count"], out["b_count"]), (2, 1))  # visitors never see each other
        self.assertTrue(out["spotify_status"]["demo"])
        self.assertEqual(out["spotify_config"], 403)
        self.assertEqual(out["docs"], 404)
        from datetime import datetime
        from zoneinfo import ZoneInfo
        far_today = datetime.now(ZoneInfo("Pacific/Kiritimati")).date().isoformat()
        self.assertEqual(out["far_seed_day"], far_today)  # the sample ends on the visitor's today
        self.assertEqual(out["far_saved_day"], far_today)  # and new entries carry their date
        self.assertLessEqual(out["far_seed_time"], datetime.now(ZoneInfo("Pacific/Kiritimati")).replace(tzinfo=None).isoformat())
        self.assertEqual(out["replies"][:2], ["ok", "ok"])
        self.assertIn("AI limit", out["replies"][2])
        self.assertEqual(out["sent"], 2)  # the limited call never reaches Gemini
        self.assertTrue(out["key_header"])


if __name__ == "__main__":
    unittest.main()
