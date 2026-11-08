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
        self.assertEqual(dataset.problems(dataset.load_all()), [])

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


class Retrieval(unittest.TestCase):
    def test_answers_and_windows_match_the_journals(self):
        from datetime import datetime
        from ml import retrieval_eval as r
        now = datetime.now()
        journals = {n: {e["id"]: e for e in r.load_journal(n, now)} for n in ("a", "b", "c")}
        queries = r.load_queries(("a", "b", "c"))
        self.assertEqual(len({q["id"] for q in queries}), len(queries))
        for q in queries:
            with self.subTest(q=q["id"]):
                entries = journals[q["journal"]]
                self.assertTrue(set(q["relevant"]) <= set(entries))
                self.assertIn(2, q["relevant"].values())
                if q.get("window"):
                    lo, hi = q["window"]
                    best = [i for i, g in q["relevant"].items() if g == 2]
                    self.assertTrue(all(lo <= entries[i]["days_ago"] <= hi for i in best))

    def test_scores(self):
        from ml import retrieval_eval as r
        q = {"id": "q", "relevant": {"x": 2, "y": 1}, "window": [0, 5]}
        row = r.score_query(q, ["z", "x", "w", "v", "u"], {"x": 3, "y": 9, "z": 1, "w": 20, "v": 30, "u": 40})
        self.assertEqual((row["recall"], row["answer_found"], row["mrr"]), (0.5, True, 0.5))
        self.assertEqual(row["in_window"], 0.4)
        self.assertTrue(0 < row["ndcg"] < 1)
        self.assertEqual(r.main(["--split", "test"]), 2)


class Evidence(unittest.TestCase):
    def test_claims_are_well_formed_and_pairs_share_a_half(self):
        from ml import evidence_eval as ev
        items = ev.load()
        self.assertEqual(len({i["id"] for i in items}), len(items))
        halves = {}
        for i in items:
            with self.subTest(i=i["id"]):
                self.assertIn(i["label"], ev.LABELS)
                self.assertTrue(i["evidence"])
            halves.setdefault(ev.group_of(i), set()).add(ev.split_of(i))
        self.assertTrue(all(len(s) == 1 for s in halves.values()))

    def test_reply_parsing_and_scores(self):
        from ml import evidence_eval as ev
        self.assertEqual(ev.parse_label("SUPPORTED - clearly"), "supported")
        self.assertEqual(ev.parse_label("**Contradicted**"), "contradicted")
        self.assertIsNone(ev.parse_label("Maybe?"))
        rows = [{"label": "supported", "pred": "supported", "traits": []},
                {"label": "contradicted", "pred": "supported", "traits": []},
                {"label": "insufficient", "pred": "insufficient", "traits": []}]
        m = ev.score(rows)
        self.assertEqual(m["unsupported_claims_accepted"], 0.5)
        self.assertEqual(m["valid_claims_rejected"], 0.0)
        self.assertEqual(ev.main(["--split", "test"]), 2)


class TrainingTargets(unittest.TestCase):
    def test_labels_replace_fields_and_base_keeps_the_rest(self):
        from ml import targets
        e = dataset._normalise(entry(text="Lunch with Sam and my sister.", emotion="calm", intensity=3,
                                     people=["Sam"], people_optional=["my sister"]))
        base = reply("happy", 8, ["Sam", "my sister", "Priya"])
        t = json.loads(targets.target_reply(e, base))
        self.assertEqual(list(t), ["emotion", "intensity", "summary", "tags", "themes", "people"])
        self.assertEqual((t["emotion"], t["intensity"]), ("calm", 3))
        self.assertEqual((t["summary"], t["tags"], t["themes"]), ("x", ["a"], ["b"]))
        self.assertEqual(t["people"], ["Sam", "my sister"])  # invented Priya dropped, optional kept
        self.assertEqual(analysis.parse(json.dumps(t))["analysis_status"], "ok")

    def test_failed_base_reply_still_gives_labelled_target(self):
        from ml import targets
        e = dataset._normalise(entry(people=["Sam"]))
        t = json.loads(targets.target_reply(e, "[LLM error: down]"))
        self.assertEqual((t["emotion"], t["summary"], t["people"]), ("happy", "", ["Sam"]))

    def test_every_train_entry_needs_a_reply(self):
        from ml import targets
        with self.assertRaises(ValueError):
            targets.build([dataset._normalise(entry())], {})

    def test_prompt_is_the_production_prompt(self):
        from ml import targets
        rec = targets.chat_record(dataset._normalise(entry()), reply())
        self.assertEqual(rec["messages"][0]["content"], analysis.build_prompt("Lunch with Sam on Monday."))


class Training(unittest.TestCase):
    def test_only_the_reply_is_learned(self):
        from ml import train_emotion as te

        class FakeTok:
            def apply_chat_template(self, messages, tokenize, add_generation_prompt):
                return "<user>" + messages[0]["content"] + "<assistant>"

            def __call__(self, text, add_special_tokens):
                return {"input_ids": [ord(c) for c in text]}

        rec = {"messages": [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "ok"}]}
        enc = te.encode(FakeTok(), rec, 1024)
        prompt_len = len("<user>hi<assistant>")
        self.assertEqual(enc["labels"][:prompt_len], [-100] * prompt_len)
        self.assertEqual(enc["labels"][prompt_len:], [ord(c) for c in "ok<|im_end|>"])
        self.assertEqual(len(enc["input_ids"]), len(enc["labels"]))

    def test_keep_only_when_better_without_regressions(self):
        from ml import train_emotion as te

        def m(f1, mae, failed=0.0, people=0.9, invented=0):
            return {"emotion": {"macro_f1": f1, "lenient_accuracy": f1}, "intensity": {"mae": mae},
                    "structure": {"failed_rate": failed}, "people": {"f1": people, "invented": invented}}
        base = m(0.70, 1.2)
        self.assertTrue(te.compare(base, m(0.75, 1.0), base)["keep"])
        self.assertFalse(te.compare(base, m(0.75, 1.3), base)["keep"])
        self.assertFalse(te.compare(base, m(0.75, 1.0, people=0.8), base)["keep"])
        self.assertFalse(te.compare(base, m(0.75, 1.0, invented=2), base)["keep"])

    def test_notebook_runs_every_stage_in_order(self):
        nb = json.loads((ROOT / "notebooks" / "02_emotion_training.ipynb").read_text())
        code = "\n".join("".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code")
        positions = [code.find(f"--stage {s}") for s in ("check", "replies", "smoke", "train", "evaluate")]
        self.assertTrue(all(p >= 0 for p in positions))
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn("--split test", code)


class ThreeWayComparison(unittest.TestCase):
    def test_eval_hf_strips_thinking_and_guards_test(self):
        from ml import eval_hf
        self.assertEqual(eval_hf.strip_thinking("<think>hmm</think>\n{\"emotion\":\"sad\"}"), '{"emotion":"sad"}')
        self.assertEqual(eval_hf.strip_thinking('{"emotion":"sad"}'), '{"emotion":"sad"}')
        self.assertEqual(eval_hf.main(["--model", "x", "--split", "test"]), 2)

    def test_compare_marks_the_best(self):
        from ml import compare
        def m(f1, mae):
            return {"scored": 402, "emotion": {"macro_f1": f1, "accuracy": f1, "lenient_accuracy": f1},
                    "intensity": {"mae": mae}, "structure": {"failed_rate": 0, "schema_complete_rate": 1},
                    "people": {"f1": 0.9, "invented": 0}, "by_trait": {}, "seconds": {"p50": 1.0}}
        t = compare.table([("7b", m(0.636, 1.23)), ("0.8b", m(0.70, 1.1))])
        self.assertIn("**0.7**", t)
        self.assertIn("**1.1**", t)
        self.assertNotIn("Warning", t)

    def test_notebook_keeps_validation_and_test_away_from_editing(self):
        brief = (ROOT / "ml" / "weight_editing" / "BRIEF.md").read_text()
        self.assertIn("must not use", brief)
        nb = json.loads((ROOT / "notebooks" / "03_qwen3.5_weight_editing.ipynb").read_text())
        code = "\n".join("".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code")
        self.assertNotIn("--split test", code)
        self.assertIn("Qwen/Qwen3.5-0.8B", code)


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
