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
import unicodedata
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
    r"\bkill(?:ing)? myself\b", r"\bunalive (?:myself|me)\b", r"\bhang(?:ing)? myself\b",
    r"(?<!\d)(?<!\d )(?<!few )(?<!many )(?<!of )(?<!the )\bkms\b",  # not "ran 5 kms"
    r"\bend(?:ing)? (?:it all|my (?:own )?life)\b",
    r"\btak(?:e|ing) my (?:own )?life\b",
    r"\b(?:want(?:ed|ing|s)?|wanna|ready) to die\b",
    r"\b(?:want(?:ed|s)? to|wanna) be dead\b",
    r"\b(?:slit|slitting|slash|slashing)(?:ed)? my wrists?\b", r"\bcut(?:ting)? (?:my|both) wrists\b",
    r"\b(?:want(?:ed)? to|wanna|going to|gonna|plan(?:ning)? to|thinking about|thought about|"
    r"feel(?:ing)? like|felt like) (?:just )?(?:take an |taking an )?overdos(?:e|ing)\b(?! on\b)",
    r"\b(?:want(?:ed)? to|wanna|going to|gonna|plan(?:ning)? to|thinking about|thought about|"
    r"feel(?:ing)? like|felt like) (?:just )?(?:jump(?:ing)? (?:off|from) (?:a|the|this) "
    r"(?:bridge|building|roof|balcony|tower)|(?:jump(?:ing)?|throw(?:ing)? myself|step(?:ping)?) "
    r"in front of (?:a|the) (?:train|bus|truck|car))\b",
    r"\bwish (?:i (?:was|were) (?:dead|never born)|i could (?:just )?die)\b",
    r"\b(?:don'?t|do not) want to (?:be here|be alive|live|exist|wake up)\b",
    r"\b(?:want(?:ing)? to|wanna) (?:stop existing|not exist|not be alive|not be here)\b",
    r"\bnot sure (?:i )?want to (?:live|be alive|be here|go on)\b",
    # A wish not to wake up; "I did not wake up until noon" is not one.
    r"\b(?:hope|hoping|wish|wishing|want|wanting|wanna|pray|praying|like|rather|easier|better)\b"
    r"[^.!?\n]{0,30}(?:\bnever|\bnot|n't) (?:ever )?wake up\b"
    r"(?! (?:the|my|him|her|them|you|us|everyone|anyone|early|late|in time|on time|at|before|until)\b)",
    r"\b(?:better off|happier|easier) (?:dead|without me|(?:if|when|with) (?:i'?m|i am|i was|i were|me) "
    r"(?:gone|dead|not around|not here))\b",
    r"\b(?:no ?one|nobody) would (?:even )?(?:notice|care|miss me) if i (?:was|were|died|disappeared)\b",
    r"\bno (?:reason|will) to live\b", r"\bnot worth living\b", r"\blife (?:isn'?t|is not) worth it\b",
    r"\bgive up on life\b", r"\btired of (?:living|being alive)\b", r"\bdone with (?:life|living)\b",
    r"\bhate being alive\b",
    r"\bself[- ]?harm(?:ing|ed)?\b",
    r"\bhurt myself to\b",
    r"\b(?:burn(?:ed|t|ing)?|cut(?:ting)?|scratch(?:ed|ing)?|hit(?:ting)?) "
    r"(?:myself|my (?:arm|arms|wrist|wrists|skin|legs?)) (?:\w+ )?(?:on purpose|deliberately|until it bl[e]?ed)",
    r"\bstockpil\w* (?:my |the )?(?:pills|tablets|meds|medication)",
    r"\bhow many (?:of )?(?:my |these |the )?(?:pills|tablets)\b.{0,30}\b(?:take|kill|enough)\b",
    r"\bsuicide (?:note|letter)s?\b",
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
    # Usually a figure of speech or a sudden fright, so the classifier decides.
    r"\bgoing to die\b", r"\bno future for me\b", r"\bgoodbye (?:note|letter)s?\b",
    r"\brather be dead\b", r"\boverdos(?:e|ed|ing)\b", r"\bcut(?:ting)? my wrist\b",
    r"\b(?:never|not) wake up\b(?! (?:until|before|at|in time|on time|early|late|rested|refreshed|feeling|"
    r"the|my|him|her|them|you|us|everyone|anyone)\b)",
    r"\bjump(?:ing)? (?:off|from) (?:a|the|this) (?:bridge|building|roof|balcony|tower)\b",
)]

# Heavy feelings or warning signs without self-harm words.
SOFT_SIGNALS = ("hopeless", "pointless", "no point", "worthless", "a burden",
                "can't do this", "cant do this", "exhausted", "numb", "empty",
                "nothing matters", "want it to stop", "tired of", "drowning",
                "hate myself", "the bridge", "rope", "pills", "tablets", "letters to",
                "no future", "don't see myself", "dont see myself")

# A negation governing the phrase: at most three words before it, in the same clause
# ("I don't want to die", "I never really wanted to kill myself"). "Can't stop",
# "can't help" and the like say the opposite, so they don't count.
_NEGATED = re.compile(r"(?:\b(?:not|never|no longer|stopped)|n't)\s+"
                      r"(?!(?:stop|stopping|help|wait|resist|shake|get)\b)(?:[\w']+\s+){0,3}$")
# A statement told at a distance: the past or a topic...
_DISTANCE = re.compile(r"\b(?:used to|years ago|months ago|documentary|book|novel|film|movie|"
                       r"article|lecture|podcast|prevention|charity|awareness)\b|"
                       r"\bin the past\b(?!\s+(?:few|couple|several|last|\d+|day|days|week|weeks|month|months|"
                       r"year|night|nights|hour|hours|while)\b)")
# ...or someone else, unless the writer is the one speaking ("my friend found me after I...").
_OTHER_PERSON = re.compile(r"\b(?:my friend|friend's)\b")
_SPEAKER = re.compile(r"\bi(?:'m|'ve|'d|'ll)?\b")
_CLAUSE_END = re.compile(r"[.!?;\n]|,? but\b")
_APOSTROPHES = str.maketrans({c: "'" for c in "’‘´`ʼʹ′＇"})

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
    """Lower case, one kind of apostrophe, and every run of spaces as one space
    (a line break where the run had one), so 'want to  die', a no-break space
    or 'don´t' match the lists. 'my self' is read as 'myself'."""
    low = unicodedata.normalize("NFKC", text.translate(_APOSTROPHES)).lower()
    low = re.sub(r"\s+", lambda m: "\n" if "\n" in m.group() else " ", low)
    return re.sub(r"\bmy self\b", "myself", low)


def _distanced(low: str, match: re.Match) -> bool:
    """Negated just before the phrase, or told about the past, a topic or
    someone else earlier in the same clause."""
    clause = _CLAUSE_END.split(low[:match.start()])[-1]
    if _NEGATED.search(clause) or _DISTANCE.search(clause):
        return True
    other = None
    for other in _OTHER_PERSON.finditer(clause):
        pass
    return bool(other and not _SPEAKER.search(clause[other.end():]))


def _verdict(reply: str) -> Optional[str]:
    """NONE, DISTRESS or CRISIS: the first of them on the classifier's first line."""
    first_line = (reply or "").strip().split("\n", 1)[0].upper()
    m = re.search(r"\b(NONE|DISTRESS|CRISIS)\b", first_line)
    return m.group(1) if m else None


_WINDOW, _OVERLAP, _MAX_WINDOWS = 1500, 200, 4


def _windows(text: str, has_sign: Callable[[str], bool]) -> list:
    """The parts of a long text the classifier reads, 1,500 characters each, so
    words near the end are read too. A text longer than four parts gives its
    start, its end and the parts in between that hold a warning sign."""
    if len(text) <= _WINDOW:
        return [text]
    step = _WINDOW - _OVERLAP
    parts = [text[i:i + _WINDOW] for i in range(0, len(text) - _OVERLAP, step)]
    if len(parts) <= _MAX_WINDOWS:
        return parts
    middle = [p for p in parts[1:-1] if has_sign(p)]
    return [parts[0], *middle[:_MAX_WINDOWS - 2], parts[-1]]


def assess(text: str, classify: Optional[Callable[[str], str]]) -> Optional[dict]:
    """A safety block for the reply, or None when nothing calls for one.
    `classify(prompt)` asks the model and returns its raw reply. With
    classify=None only the clear phrases count (instant, for live typing)."""
    if not text:
        return None
    low = _normalise(text)
    flat = low.replace("\n", " ")  # same positions as `low`; phrases may run across a line break

    clear = [m for p in CLEAR for m in p.finditer(flat)]
    if any(not _distanced(low, m) for m in clear):
        return {"level": "high", "reason": "explicit self-harm or suicidal language",
                "resources": RESOURCES, "message": _HIGH_FROM_WORDS}
    if classify is None:
        return None

    def has_sign(part: str) -> bool:
        part = _normalise(part).replace("\n", " ")
        return bool(any(p.search(part) for p in CLEAR) or any(p.search(part) for p in AMBIGUOUS)
                    or any(s in part for s in SOFT_SIGNALS))

    warning_sign = has_sign(text)
    verdicts = []
    for part in _windows(text, has_sign):
        try:
            verdicts.append(_verdict(classify(_CLASSIFIER_PROMPT.format(text=part))))
        except Exception:
            verdicts.append(None)
        if verdicts[-1] == "CRISIS":
            break
    if "CRISIS" in verdicts:
        return {"level": "high", "reason": "model flagged crisis-level distress",
                "resources": RESOURCES, "message": _HIGH_FROM_MODEL}
    if "DISTRESS" in verdicts:
        return {"level": "soft", "reason": "elevated distress",
                "resources": GENTLE_RESOURCES, "message": _SOFT}
    if None in verdicts and warning_sign:
        return {"level": "soft", "reason": "could not check; showing support lines to be safe",
                "resources": GENTLE_RESOURCES, "message": _SOFT}
    return None
