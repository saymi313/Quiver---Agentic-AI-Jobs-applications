"""
BeHuman: strip the tells of machine-written prose.

Adapted from the `behuman` skill in Backend/.skills/behuman, which in turn
follows Wikipedia's "Signs of AI writing" field guide. Every prompt in this
project that produces prose a human will read — resume bullets, summaries,
cover letters, cold emails — imports `RULES` and appends it to its system
prompt.

`lint()` is the check after the fact: models comply unevenly, and a résumé
bullet that opens "Spearheaded a transformative, cutting-edge solution" fails
in front of a recruiter, not in a test. `scrub()` fixes only what can be fixed
without touching meaning.
"""

from __future__ import annotations

import re

# Appended to the system prompt of every generation call.
RULES = """
WRITING RULES (these override any habit to sound impressive):

Banned words unless literally accurate or quoted: delve, tapestry, vibrant, crucial,
pivotal, seamless, robust, dynamic, intricate, nuanced, multifaceted, holistic,
comprehensive, innovative, cutting-edge, state-of-the-art, game-changer, transformative,
revolutionize, elevate, empower, unlock, unleash, harness, leverage, foster, garner,
showcase, underscore, boast, testament, realm, landscape, journey, navigate, myriad,
plethora, ever-evolving, fast-paced, at the forefront, spearhead, embark, dive into.
Replace each with the specific fact it was hiding: not "a robust system" but "handles
2,000 concurrent users".

Banned constructions:
- Negative parallelism: "not just X, but Y". State the point plainly.
- Significance tails: a comma then a participle assigning meaning — ", ensuring
  scalability", ", highlighting the impact", ", demonstrating expertise". Delete them.
  The fact carries itself.
- Rule-of-three padding: three adjectives or three clauses stacked for rhythm. Use the
  number of items that are actually true.
- Puffery: "stands as a testament", "plays a vital role", "proven track record".
- Filler transitions: moreover, furthermore, additionally, it's worth noting.
- Formula openers: "In today's...", "When it comes to...", "As a passionate...".

Formatting:
- No em dashes. Use commas or a full stop.
- No emoji. No bold scattered on key terms.
- Straight quotes and apostrophes only.

Never leave chatbot residue: "Certainly!", "Here's...", "I hope this helps", "[insert X]".

Write the way a competent engineer describes their own work to a colleague: concrete,
specific, and finished.
""".strip()

# High-confidence single words. Context-legitimate technical uses are excluded
# in `lint` (e.g. "dynamic" in "dynamic programming", "robust" in statistics).
BANNED_WORDS = [
    "delve", "tapestry", "vibrant", "crucial", "pivotal", "seamless", "intricate",
    "nuanced", "multifaceted", "holistic", "cutting-edge", "state-of-the-art",
    "game-changer", "transformative", "revolutionize", "revolutionise", "elevate",
    "empower", "unleash", "harness", "foster", "garner", "showcase", "underscore",
    "boast", "testament", "myriad", "plethora", "ever-evolving", "fast-paced",
    "spearhead", "spearheaded", "embark", "realm",
]

# Words that are fine in a technical sentence but not as decoration.
CONTEXTUAL_WORDS = {
    "robust": r"robust\s+(?!statistic|regression|standard error)",
    "dynamic": r"dynamic\s+(?!programming|import|typing|route|allocation)",
    "leverage": r"\bleverag(?:e|ed|ing)\b(?!\s+ratio)",
    "comprehensive": r"\bcomprehensive\b",
    "innovative": r"\binnovative\b",
    "landscape": r"\blandscape\b(?!\s+(?:orientation|mode))",
}

# Consumes the whole trailing clause, not just the participle, so removing it
# leaves a clean sentence rather than an orphaned fragment.
SIGNIFICANCE_TAIL = re.compile(
    r",\s+(?:ensuring|highlighting|underscoring|reflecting|showcasing|emphasizing|"
    r"emphasising|demonstrating|solidifying|cementing|illustrating|"
    r"fostering)\s+[^.;!?\n]*",
    re.I,
)
NEGATIVE_PARALLEL = re.compile(r"\bnot (just|only|merely)\b[^.!?]{0,80}?\b(but|it'?s)\b", re.I)
PUFFERY = re.compile(
    r"\b(stands? as a testament|plays? a (vital|key|crucial) role|proven track record|"
    r"passionate about|results[- ]driven|detail[- ]oriented|team player|"
    r"go[- ]getter|think outside the box|hit the ground running)\b", re.I)
FILLER = re.compile(r"\b(moreover|furthermore|additionally|it'?s worth noting|"
                    r"it is important to note|in conclusion|in summary|overall,)\b", re.I)
RESIDUE = re.compile(r"(certainly!|here'?s (the|a|your)|i hope this helps|"
                     r"as an ai|\[insert [^\]]+\]|would you like me to)", re.I)
FORMULA_OPENER = re.compile(r"^\s*(in today'?s|when it comes to|in the world of|"
                            r"as a passionate|whether you'?re)", re.I)


def lint(text: str) -> list[dict[str, str]]:
    """Return every tell found, so the caller can report or retry."""
    if not text:
        return []
    hits: list[dict[str, str]] = []
    low = text.lower()

    for word in BANNED_WORDS:
        if re.search(rf"\b{re.escape(word)}\b", low):
            hits.append({"kind": "word", "match": word,
                         "fix": "replace with the specific fact it stands in for"})
    for word, pattern in CONTEXTUAL_WORDS.items():
        if re.search(pattern, low):
            hits.append({"kind": "word", "match": word,
                         "fix": "decorative use — name the concrete property instead"})

    for label, pattern, fix in (
        ("significance tail", SIGNIFICANCE_TAIL, "delete the trailing participle clause"),
        ("negative parallelism", NEGATIVE_PARALLEL, "state the point directly"),
        ("puffery", PUFFERY, "replace with evidence"),
        ("filler transition", FILLER, "start the sentence without the joint"),
        ("chatbot residue", RESIDUE, "remove entirely"),
        ("formula opener", FORMULA_OPENER, "open with the actual subject"),
    ):
        for m in pattern.finditer(text):
            hits.append({"kind": label, "match": m.group(0).strip()[:70], "fix": fix})

    dashes = text.count("—") + text.count("–")
    if dashes >= 2:
        hits.append({"kind": "em dashes", "match": f"{dashes} occurrences",
                     "fix": "use commas or full stops"})

    if re.search(r"[\U0001F300-\U0001FAFF✀-➿]", text):
        hits.append({"kind": "emoji", "match": "emoji present", "fix": "remove"})

    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    for h in hits:
        key = f"{h['kind']}:{h['match'].lower()}"
        if key not in seen:
            seen.add(key)
            unique.append(h)
    return unique


def scrub(text: str) -> str:
    """
    Deterministic cleanup for the tells that can be fixed without judgement.

    Deliberately narrow: rewriting "leveraged" into something truthful needs to
    know what actually happened, so that stays a `lint` finding for the model or
    the user to resolve. This only removes what is safe to remove.
    """
    if not text:
        return text

    def drop_tail(m: re.Match) -> str:
        # A tail carrying a number is usually a real result ("...for 500+ users"),
        # not decoration. Keep anything measurable; only cut the empty flourish.
        return m.group(0) if re.search(r"\d", m.group(0)) else ""

    out = RESIDUE.sub("", text)
    out = SIGNIFICANCE_TAIL.sub(drop_tail, out)
    out = FILLER.sub("", out)
    # A removed opener leaves ", this isn't..." — restore the sentence start.
    out = re.sub(r"(^|[.!?]\s+)\s*,\s*", r"\1", out)
    out = re.sub(r"(^|[.!?]\s+)([a-z])",
                 lambda m: m.group(1) + m.group(2).upper(), out)

    # Em dash as a pause becomes a comma; a spaced dash becomes a full stop.
    out = re.sub(r"\s+[—–]\s+", ", ", out)
    out = out.replace("—", ", ").replace("–", "-")

    out = (out.replace("’", "'").replace("‘", "'")
              .replace("“", '"').replace("”", '"'))
    out = re.sub(r"[\U0001F300-\U0001FAFF✀-➿]", "", out)

    out = re.sub(r"\s+,", ",", out)
    out = re.sub(r",\s*,+", ",", out)
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    out = re.sub(r"\s+([.,;:!?])", r"\1", out)
    return out.strip()


def report(text: str) -> str:
    """One-line human summary of what lint found, for logs."""
    hits = lint(text)
    if not hits:
        return "clean"
    kinds: dict[str, int] = {}
    for h in hits:
        kinds[h["kind"]] = kinds.get(h["kind"], 0) + 1
    return ", ".join(f"{n}x {k}" for k, n in sorted(kinds.items(), key=lambda kv: -kv[1]))
