"""Benchmark tooling: dataset checks, splits, scoring and resumable runs.

No model is needed: replies are scripted.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from innerbloom_core import analysis  # noqa: E402
from ml import benchmark, dataset, metrics, spec, split  # noqa: E402


def entry(**kw):
    base = {"id": "e9999", "group": "e9999", "text": "Lunch with Sam on Monday.", "emotion": "happy",
            "intensity": 5, "also": [], "people": [], "people_optional": [], "not_people": [], "traits": []}
    return {**base, **kw}


def reply(emotion="happy", intensity=5, people=()):
    return json.dumps({"emotion": emotion, "intensity": intensity, "summary": "x", "tags": ["a"],
                       "themes": ["b"], "people": list(people)})


class Data(unittest.TestCase):
    def test_committed_entries_are_valid(self):
        self.assertEqual(dataset.problems(dataset.load()), [])

    def test_checker_catches_bad_labels(self):
        bad = dataset._normalise(entry(emotion="joyful", intensity=11, people=["Priya"]))
        bad["_source"] = "test"
        found = "\n".join(dataset.problems([bad]))
        self.assertIn("not a production emotion", found)
        self.assertIn("intensity", found)
        self.assertIn("'Priya' does not appear", found)

    def test_spec_matches_code(self):
        self.assertEqual(json.loads(spec.SPEC_FILE.read_text())["prompt_sha256"], spec.build()["prompt_sha256"])

    def test_splits_are_current_and_disjoint(self):
        self.assertEqual(split.main(["--check"]), 0)
        groups = {name: {json.loads(l)["group"] for l in (split.SPLIT_DIR / f"{name}.jsonl").read_text().splitlines() if l}
                  for name in ("train", "validation", "test")}
        self.assertFalse(groups["train"] & groups["test"])
        self.assertFalse(groups["validation"] & groups["test"])
        self.assertFalse(groups["train"] & groups["validation"])

    def test_every_emotion_reaches_the_test_split(self):
        rows = [json.loads(l) for l in (split.SPLIT_DIR / "test.jsonl").read_text().splitlines() if l]
        self.assertEqual({r["emotion"] for r in rows}, set(analysis.EMOTIONS))


class People(unittest.TestCase):
    def test_title_and_partial_names_match(self):
        self.assertTrue(metrics.same_person("Mr. Haddad", "Haddad"))
        self.assertTrue(metrics.same_person("uncle raj", "Uncle Raj"))
        self.assertFalse(metrics.same_person("Lucy", "Lucía"))

    def test_counts(self):
        e = entry(text="Lunch with Sam and my sister on Monday.", people=["Sam"],
                  people_optional=["my sister"], not_people=["Monday"])
        c = metrics.people_counts(e, ["Sam", "my sister", "Monday", "Priya"])
        self.assertEqual((c["tp"], c["fp"], c["fn"]), (1, 2, 0))
        self.assertEqual((c["not_people"], c["invented"]), (1, 1))


class Scoring(unittest.TestCase):
    def test_perfect_and_failed_readings(self):
        es = [entry(id="e0001", emotion="happy", intensity=5),
              entry(id="e0002", emotion="sad", intensity=7, also=["lonely"]),
              entry(id="e0003", emotion="calm", intensity=3)]
        raws = {"e0001": reply("happy", 5), "e0002": reply("lonely", 6), "e0003": "[LLM error: down]"}
        preds = {i: {"raw": r, "parsed": analysis.parse(r), "seconds": 1.0} for i, r in raws.items()}
        m = metrics.score(es, preds)
        self.assertEqual(m["emotion"]["accuracy"], round(1 / 3, 3))
        self.assertEqual(m["emotion"]["lenient_accuracy"], round(2 / 3, 3))
        self.assertEqual(m["emotion"]["confusion"]["calm"], {"<failed>": 1})
        self.assertEqual(m["intensity"]["mae"], 0.5)  # failed reading not scored for intensity
        self.assertEqual(m["structure"]["failed_rate"], round(1 / 3, 3))


class BlindSafetySet(unittest.TestCase):
    def test_only_totals_leave_the_blind_set(self):
        from ml import safety_eval
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "crisis.txt").write_text("a secret test sentence\nanother one\n")
            with patch.object(safety_eval, "BLIND_DIR", Path(tmp)):
                totals = safety_eval.blind_totals(safety_eval.run(safety_eval.load_blind()))
        dumped = json.dumps(totals)
        self.assertNotIn("secret", dumped)
        self.assertNotIn("crisis.txt", dumped)
        self.assertEqual(totals["counts"]["crisis"], 2)


class Runs(unittest.TestCase):
    def test_smoke_run_resumes_and_refuses_locked_test(self):
        self.assertEqual(benchmark.main(["--split", "test"]), 2)
        with tempfile.TemporaryDirectory() as tmp, patch.object(benchmark, "RUNS_DIR", Path(tmp)):
            calls = []

            def fake(url, model, prompt, seed, timeout):
                calls.append(prompt)
                if len(calls) == 3:
                    raise benchmark.requests.ConnectionError("ollama stopped")
                return {"raw": reply(), "seconds": 0.1, "eval_count": 10, "prompt_eval_count": 50}

            with patch.object(benchmark, "ollama_generate", side_effect=fake):
                benchmark.main(["--split", "validation", "--limit", "4", "--run", "smoke"])
                done = (Path(tmp) / "smoke" / "predictions.jsonl").read_text().splitlines()
                self.assertEqual(len(done), 2)  # stopped cleanly at the third
                benchmark.main(["--split", "validation", "--limit", "4", "--run", "smoke"])
            rows = (Path(tmp) / "smoke" / "predictions.jsonl").read_text().splitlines()
            self.assertEqual(len(rows), 4)
            self.assertEqual(len({json.loads(r)["id"] for r in rows}), 4)
            report = json.loads((Path(tmp) / "smoke" / "report.json").read_text())
            self.assertEqual(report["metrics"]["scored"], 4)
            self.assertEqual(report["prompt_sha256"], report["spec_prompt_sha256"])


if __name__ == "__main__":
    unittest.main()
