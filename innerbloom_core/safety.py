"""Crisis detection for what a person writes.

Two tiers of phrases. Clear statements of wanting to die or to harm oneself
show the help lines straight away. Phrases that are often harmless ("I cut
myself cooking", "we decided to end things") or that are negated ("I'm not
suicidal") go to a small classifier first.

When the classifier cannot answer (the model is off, rate-limited or replies
with something else), the gentle version of the help lines is shown. Silence
is never treated as evidence that someone is safe.

This is a support prompt, not a diagnosis, and the reply is never withheld.
"""
import re
from typing import Callable, Optional

RESOURCES = [
    {"name": "iCall (India)", "detail": "+91 9152987821 · Mon–Sat 8am–10pm"},
    {"name": "AASRA (India)", "detail": "+91 9820466726 · 24/7"},
    {"name": "988 Suicide & Crisis Lifeline (US)", "detail": "Call or text 988 · 24/7"},
    {"name": "Samaritans (UK & ROI)", "detail": "116 123 · 24/7"},
    {"name": "Find a Helpline (worldwide)", "detail": "https://findahelpline.com"},
]

# Unambiguous wishes to die or to hurt oneself.
CLEAR = [re.compile(p) for p in (
    r"\bsuicidal\b",
    r"\b(?:commit|committing|attempt(?:ed|ing)?|thinking about|thought about|"
    r"considering|planning) (?:to )?suicide\b",
    r"\bkill(?:ing)? myself\b", r"\bkms\b",
    r"\bend(?:ing)? (?:it all|my (?:own )?life)\b",
    r"\btak(?:e|ing) my (?:own )?life\b",
    r"\b(?:want(?:ed)?|ready|going) to die\b",
    r"\bwish (?:i (?:was|were) (?:dead|never born)|i could die|i could just die)\b",
    r"\bdon'?t want to (?:be here|be alive|live|exist|wake up)\b",
    r"\bnot sure (?:i )?want to (?:live|be alive|be here|go on)\b",
    r"\bnever wake up\b",
    r"\bbetter off (?:dead|without me|if i (?:was|were) gone)\b",
    r"\bno (?:reason|will) to live\b", r"\bnot worth living\b",
    r"\bgive up on life\b", r"\btired of (?:living|being alive)\b",
    r"\bhate being alive\b",
    r"\bself[- ]?harm(?:ing|ed)?\b",
)]

# Often harmless, sometimes not: the classifier decides.
AMBIGUOUS = [re.compile(p) for p in (
    r"\bsuicide\b",
    r"\bend (?:it|things)\b",
    r"\bcan(?:'?t|not) go on\b",
    r"\bhurt(?:ing)? myself\b",
    r"\bcut(?:ting)? myself\b",
    r"\b(?:want to|could just) disappear\b", r"\bdisappear forever\b",
)]

# Heavy feelings without self-harm words: worth a check, not an alarm.
SOFT_SIGNALS = ("hopeless", "pointless", "no point", "worthless",
                "can't do this", "cant do this", "exhausted", "numb",
                "nothing matters", "want it to stop", "tired of", "a burden")

_NEGATION = re.compile(r"\b(?:not|never|no)\b|n't\b")

_CLASSIFIER_PROMPT = (
    "Classify the following message for crisis risk. Reply with ONE of:\n"
    "  NONE       — no concerning content\n"
    "  DISTRESS   — significant distress but no self-harm/suicidal ideation\n"
    "  CRISIS     — possible self-harm or suicidal ideation, even if implicit\n"
    "Reply with only the single word.\n\n"
    "Message: \"\"\"{text}\"\"\""
)

_HIGH_FROM_WORDS = (
    "What you're carrying sounds heavy, and I'm glad you wrote it down. "
    "You don't have to figure this out alone — please reach out to one of the lines below. "
    "They're free, confidential, and trained for exactly this."
)
_HIGH_FROM_MODEL = (
    "I want to check in — what you wrote sounds really heavy. "
    "If any part of you is thinking about not being here, please reach out to one of the lines below. "
    "You don't have to be sure it's 'serious enough' to call."
)
_SOFT = (
    "Sounds like a hard moment. If it gets heavier, these lines are there — "
    "no need to be in 'crisis' to use them."
)


def _normalise(text: str) -> str:
    return text.lower().replace("’", "'").replace("‘", "'")


def _negated(low: str, match: re.Match) -> bool:
    """A 'not', 'never', 'no' or "n't" just before the phrase."""
    return bool(_NEGATION.search(low[max(0, match.start() - 25):match.start()]))


def _verdict(reply: str) -> Optional[str]:
    """NONE, DISTRESS or CRISIS from the classifier's first word, else None."""
    m = re.match(r"\W*(NONE|DISTRESS|CRISIS)\b", (reply or "").strip().upper())
    return m.group(1) if m else None


def assess(text: str, classify: Optional[Callable[[str], str]]) -> Optional[dict]:
    """A safety block for the reply, or None when nothing calls for one.
    `classify(prompt)` asks the model and returns its raw reply. With
    classify=None only the clear phrases count (instant, for live typing)."""
    if not text:
        return None
    low = _normalise(text)

    clear = [m for p in CLEAR for m in p.finditer(low)]
    if any(not _negated(low, m) for m in clear):
        return {"level": "high", "reason": "explicit self-harm or suicidal language",
                "resources": RESOURCES, "message": _HIGH_FROM_WORDS}

    if classify is None:
        return None
    worth_checking = (clear or any(p.search(low) for p in AMBIGUOUS)
                      or any(s in low for s in SOFT_SIGNALS))
    if not worth_checking:
        return None

    try:
        verdict = _verdict(classify(_CLASSIFIER_PROMPT.format(text=text[:500])))
    except Exception:
        verdict = None
    if verdict == "CRISIS":
        return {"level": "high", "reason": "model flagged crisis-level distress",
                "resources": RESOURCES, "message": _HIGH_FROM_MODEL}
    if verdict == "DISTRESS":
        return {"level": "soft", "reason": "elevated distress",
                "resources": RESOURCES[:2], "message": _SOFT}
    if verdict is None:
        return {"level": "soft", "reason": "could not check; showing support lines to be safe",
                "resources": RESOURCES[:2], "message": _SOFT}
    return None
