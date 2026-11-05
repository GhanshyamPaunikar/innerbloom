"""Crisis detection for what a person writes.

When the model is available, every message is checked by a small classifier:
a list of phrases can never cover the ways people describe wanting to die.
The phrase lists are the backup for when the model is off, rate-limited or
too slow, and they decide on their own only while typing.

- Clear statements of wanting to die or to harm oneself show the full help
  lines straight away, without waiting for the model.
- The same statements told at a distance (negated, in the past, about a book
  or someone else) are left to the classifier.
- When the classifier cannot answer, the gentle help lines are shown if
  anything in the message is a warning sign. Silence is never read as safe.

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

# The gentle version: lines open around the clock, wherever the writer is.
GENTLE_RESOURCES = [RESOURCES[1], RESOURCES[4]]

# Unambiguous wishes to die or to hurt oneself, in the writer's own voice.
CLEAR = [re.compile(p) for p in (
    r"\bsuicidal\b",
    r"\b(?:commit|committing|attempt(?:ed|ing)?|thinking about|thought about|"
    r"considering|planning) (?:to )?suicide\b",
    r"\bkill(?:ing)? myself\b", r"\bkms\b",
    r"\bend(?:ing)? (?:it all|my (?:own )?life)\b",
    r"\btak(?:e|ing) my (?:own )?life\b",
    r"\b(?:want(?:ed|ing|s)?|wanna|ready|going) to die\b",
    r"\bwish (?:i (?:was|were) (?:dead|never born)|i could (?:just )?die)\b",
    r"\b(?:don'?t|do not) want to (?:be here|be alive|live|exist|wake up)\b",
    r"\b(?:want(?:ing)? to|wanna) (?:stop existing|not exist|not be alive|not be here)\b",
    r"\bnot sure (?:i )?want to (?:live|be alive|be here|go on)\b",
    r"\b(?:never|not) wake up\b",
    r"\b(?:better off|happier|easier) (?:dead|without me|(?:if|when|with) (?:i'?m|i am|i was|i were|me) "
    r"(?:gone|dead|not around|not here))\b",
    r"\b(?:no ?one|nobody) would (?:even )?(?:notice|care|miss me) if i (?:was|were|died|disappeared)\b",
    r"\bno (?:reason|will) to live\b", r"\bnot worth living\b", r"\blife (?:isn'?t|is not) worth it\b",
    r"\bgive up on life\b", r"\btired of (?:living|being alive)\b", r"\bdone with (?:life|living)\b",
    r"\bhate being alive\b", r"\bno future for me\b",
    r"\bself[- ]?harm(?:ing|ed)?\b",
    r"\bhurt myself to\b",
    r"\b(?:burn(?:ed|t)?|cut|scratch(?:ed)?|hit) (?:myself|my (?:arm|arms|wrist|wrists|skin|legs?)) "
    r"(?:\w+ )?(?:on purpose|deliberately|until it bl[e]?ed)",
    r"\bstockpil\w* (?:my |the )?(?:pills|tablets|meds|medication)",
    r"\bhow many (?:of )?(?:my |these |the )?(?:pills|tablets)\b.{0,30}\b(?:take|kill|enough)\b",
    r"\b(?:suicide|goodbye) (?:note|letter)s?\b",
)]

# Often harmless, sometimes not: the classifier decides.
AMBIGUOUS = [re.compile(p) for p in (
    r"\bsuicide\b",
    r"\bend (?:it|things)\b",
    r"\bcan(?:'?t|not) go on\b", r"\bcan(?:'?t|not) keep going\b",
    r"\bhurt(?:ing)? myself\b",
    r"\bcut(?:ting)? (?:myself|again)\b",
    r"\b(?:want to|could just|wanna) disappear\b", r"\bdisappear(?:ing)? (?:forever|permanently)\b",
    r"\bkill me\b", r"\bi want out\b",
    r"\b(?:gave|giving|give) away my\b", r"\bwon'?t need (?:it|them)\b",
    r"\b(?:have|got|made) a plan\b", r"\bsaying goodbye\b", r"\blooks like an accident\b",
)]

# Heavy feelings or warning signs without self-harm words.
SOFT_SIGNALS = ("hopeless", "pointless", "no point", "worthless", "a burden",
                "can't do this", "cant do this", "exhausted", "numb", "empty",
                "nothing matters", "want it to stop", "tired of", "drowning",
                "hate myself", "the bridge", "rope", "pills", "tablets", "letters to",
                "no future", "don't see myself", "dont see myself")

_NEGATION = re.compile(r"\b(?:not|never|no|stopped|no longer)\b|n't\b")
# A statement told at a distance: the past, a topic, or someone else.
_DISTANCE = re.compile(r"\b(?:used to|years ago|months ago|in the past|documentary|book|novel|film|movie|"
                       r"article|course|lecture|podcast|prevention|charity|awareness|my friend|friend's)\b")

_CLASSIFIER_PROMPT = (
    "You check one message from a private journal for suicide or self-harm risk. "
    "Reply with ONE word:\n"
    "  CRISIS   — the writer may be thinking about dying, suicide or hurting themselves, now or soon, "
    "even if it is only implied: wishing not to exist or not to wake up, feeling everyone would be "
    "better off without them, saying goodbye, giving possessions away, gathering means or making a plan, "
    "or harming themselves on purpose\n"
    "  DISTRESS — strong distress (hopeless, numb, worthless, can't cope) without those signs\n"
    "  NONE     — none of the above: everyday feelings, figures of speech ('this deadline is killing me'), "
    "accidents and injuries, risk that is clearly in the past, or the topic discussed in a book, a film, "
    "study or someone else's story\n"
    "When unsure between CRISIS and DISTRESS, choose CRISIS.\n\n"
    "Message: \"\"\"{text}\"\"\"\n\nAnswer:"
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


def _distanced(low: str, match: re.Match) -> bool:
    """Negated just before the phrase ('not', "n't", 'stopped'), or told about
    the past, a topic or someone else earlier in the same sentence."""
    before = low[max(0, match.start() - 25):match.start()]
    sentence = re.split(r"[.!?\n]", low[:match.start()])[-1]
    return bool(_NEGATION.search(before) or _DISTANCE.search(sentence))


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
    if any(not _distanced(low, m) for m in clear):
        return {"level": "high", "reason": "explicit self-harm or suicidal language",
                "resources": RESOURCES, "message": _HIGH_FROM_WORDS}
    if classify is None:
        return None

    warning_sign = bool(clear or any(p.search(low) for p in AMBIGUOUS)
                        or any(s in low for s in SOFT_SIGNALS))
    try:
        verdict = _verdict(classify(_CLASSIFIER_PROMPT.format(text=text[:1500])))
    except Exception:
        verdict = None
    if verdict == "CRISIS":
        return {"level": "high", "reason": "model flagged crisis-level distress",
                "resources": RESOURCES, "message": _HIGH_FROM_MODEL}
    if verdict == "DISTRESS":
        return {"level": "soft", "reason": "elevated distress",
                "resources": GENTLE_RESOURCES, "message": _SOFT}
    if verdict is None and warning_sign:
        return {"level": "soft", "reason": "could not check; showing support lines to be safe",
                "resources": GENTLE_RESOURCES, "message": _SOFT}
    return None
