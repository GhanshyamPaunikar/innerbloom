"""Crisis detection: false negatives, false positives and an unreachable model.

All text is fictional. "down" is the reply call_llama gives when Ollama is
off; "none" is a classifier that sees nothing concerning.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from innerbloom_core import safety  # noqa: E402


def down(prompt):
    return "[LLM error: connection refused]"


def none(prompt):
    return "NONE"


def reply(word):
    return lambda prompt: word


def level(text, classify):
    result = safety.assess(text, classify)
    return result["level"] if result else None


# Must show the full help lines from the words alone, even with the model off.
CLEAR = [
    "I want to kill myself.",
    "I've been thinking about ending my life.",
    "Sometimes I wish I was dead.",
    "Everyone would be better off without me.",
    "I don't want to be alive anymore.",
    "I don’t want to live like this",  # curly apostrophe
    "I keep having suicidal thoughts at night.",
    "I just want to end it all.",
    "I hope I never wake up.",
    "I've been thinking about suicide a lot.",
    "honestly kms",
    "I started self-harming again.",
    "I'm not sure I want to live anymore.",
    "There's no reason to live.",
    "I'm tired of living.",
]

# Harmless when the classifier says so, never an alarm from the words alone.
AMBIGUOUS_HARMLESS = [
    "I cut myself while chopping onions.",
    "I hurt myself at the gym, nothing serious.",
    "We decided to end things after five years.",
    "I'm going to end it here for today.",
    "I can't go on like this at work, I need a new job.",
    "I'm not suicidal, just very tired.",
    "I don't want to die without seeing Japan.",
    "Watched a documentary about suicide prevention.",
    "Cutting myself some slack this week.",
]

# No check needed at all.
EVERYDAY = [
    "Had a lovely dinner with Sam.",
    "This deadline is killing me.",
    "My phone died on the train.",
    "I could die of embarrassment, the slides froze.",
    "Dead tired but happy after the hike.",
]


class ClearLanguage(unittest.TestCase):
    def test_full_help_lines_without_the_model(self):
        for text in CLEAR:
            with self.subTest(text=text):
                self.assertEqual(level(text, down), "high")


class AmbiguousLanguage(unittest.TestCase):
    def test_no_alarm_when_classifier_sees_nothing(self):
        for text in AMBIGUOUS_HARMLESS:
            with self.subTest(text=text):
                self.assertIsNone(level(text, none))

    def test_classifier_can_still_raise_it(self):
        self.assertEqual(level("I just want to disappear forever.", reply("CRISIS")), "high")

    def test_gentle_lines_when_model_is_off(self):
        for text in AMBIGUOUS_HARMLESS:
            with self.subTest(text=text):
                self.assertEqual(level(text, down), "soft")


class SoftSignals(unittest.TestCase):
    def test_heavy_feelings(self):
        text = "I feel hopeless and numb, I just want it all to stop."
        self.assertEqual(level(text, reply("CRISIS")), "high")
        self.assertEqual(level(text, reply("DISTRESS")), "soft")
        self.assertIsNone(level(text, none))

    def test_unreachable_model_is_not_read_as_safe(self):
        self.assertEqual(level("Everything feels pointless lately.", down), "soft")

    def test_classifier_that_raises(self):
        def broken(prompt):
            raise TimeoutError
        self.assertEqual(level("I feel worthless.", broken), "soft")

    def test_verdict_read_from_first_word_only(self):
        # "NONE — no crisis here" once matched CRISIS by substring.
        self.assertIsNone(level("I'm exhausted.", reply("NONE — no crisis here")))


class WhileTyping(unittest.TestCase):
    """classify=None: the instant check the writing page runs on each pause."""

    def test_clear_phrases_only(self):
        for text in CLEAR:
            with self.subTest(text=text):
                self.assertEqual(level(text, None), "high")
        for text in AMBIGUOUS_HARMLESS + EVERYDAY + ["Everything feels pointless lately."]:
            with self.subTest(text=text):
                self.assertIsNone(level(text, None))


class Everyday(unittest.TestCase):
    def test_no_check_and_no_alarm(self):
        calls = []

        def spy(prompt):
            calls.append(prompt)
            return "CRISIS"
        for text in EVERYDAY:
            with self.subTest(text=text):
                self.assertIsNone(level(text, spy))
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
