"""Entry-reading parser: names, tags and People keys in any script."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from innerbloom_core import analysis  # noqa: E402


def parsed(**fields):
    return analysis.parse(json.dumps({"emotion": "happy", **fields}))


class Names(unittest.TestCase):
    def test_accents_and_other_scripts_survive(self):
        people = parsed(people=["Tomás", "Lucía", "Zoë", "राहुल", "美咲", "Seo-yeon"])["people"]
        self.assertEqual(people, ["Tomás", "Lucía", "Zoë", "राहुल", "美咲", "Seo-yeon"])

    def test_titles_and_apostrophes_kept_symbols_dropped(self):
        self.assertEqual(parsed(people=["Dr. Lee", "O'Brien", "Sam!!", "@kai"])["people"],
                         ["Dr. Lee", "O'Brien", "Sam", "kai"])

    def test_decomposed_accents_are_joined(self):
        self.assertEqual(parsed(people=["José"])["people"], ["José"])


class Tags(unittest.TestCase):
    def test_letters_in_any_script(self):
        self.assertEqual(parsed(tags=["Café", "#work!", "योग", "self-care"])["tags"],
                         ["café", "work", "योग", "self-care"])


class PersonKeys(unittest.TestCase):
    def test_same_person_same_key(self):
        key = analysis.person_key
        self.assertEqual(key("José"), key("jose"))
        self.assertEqual(key("Mom"), key("MOM"))
        self.assertNotEqual(key("Lucía"), key("Lucy"))
        self.assertEqual(key("राहुल"), "राहुल")
        self.assertTrue(key("美咲"))

    def test_plain_names_keep_their_old_keys(self):
        # Keys already stored in people.json must not change.
        for name, old in (("Sam", "sam"), ("Dr. Lee", "drlee"), ("O'Brien", "obrien"), ("Mary-Jo", "maryjo")):
            with self.subTest(name=name):
                self.assertEqual(analysis.person_key(name), old)


if __name__ == "__main__":
    unittest.main()
