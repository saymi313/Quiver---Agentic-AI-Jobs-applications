"""
The fact gate: a rewritten bullet may not assert anything the profile does not.

This is deliberately mechanical rather than a line in a prompt. "Never invent a
metric" has been in the rewrite instructions from the start, and models mostly
obey it — but "mostly" is the wrong standard for a document that goes to a real
employer with the candidate's name on it. A prompt is a request; this is a
check, and a rewrite that fails it is discarded in favour of the original.

Three kinds of claim are checked, because they are the three a model actually
invents:

  * **Numbers.** "serving 4M users", "cut latency 38%". A number absent from
    the profile is a fabrication, full stop. This is the important one.
  * **Proper nouns.** Employers, products and technologies — Kubernetes, Stripe,
    BangoPure. Capitalised or camel-cased tokens the profile never mentions.
  * **Credentials.** Degrees and certifications the profile does not claim.

Everything else — verbs, connective prose, ordinary adjectives — is free to
change, because rewording is the entire point of tailoring.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

# Words that look like proper nouns but are not claims: sentence-initial
# capitals, and the handful of capitalised words that appear in ordinary prose.
COMMON_CAPS = {
    "A", "An", "And", "As", "At", "Built", "By", "Delivered", "Designed",
    "Developed", "Drove", "For", "From", "Implemented", "In", "Increased",
    "Led", "Maintained", "Of", "On", "Optimized", "Owned", "Reduced",
    "Shipped", "The", "To", "With", "Wrote", "Created", "Improved", "Managed",
    "Migrated", "Launched", "Architected", "Automated", "Integrated", "Ran",
    "Collaborated", "Contributed", "Partnered", "Scaled", "Standardised",
    "Standardized", "Streamlined", "Refactored", "Rebuilt", "Established",
}

# Numbers that carry no claim about the candidate's work.
HARMLESS_NUMBERS = {"1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "0"}

_NUMBER = re.compile(r"\d+(?:[.,]\d+)*\s*(?:%|k|m|b|x|\+)?", re.I)
_PROPER = re.compile(r"\b[A-Z][A-Za-z0-9.+#/-]{1,}\b")
_CAMEL = re.compile(r"\b[a-z]+[A-Z][A-Za-z]*\b")


def _norm_number(token: str) -> str:
    """4,000 / 4000 / 4 000 all mean the same claim."""
    return re.sub(r"[,\s]", "", token.strip().lower()).rstrip("+")


def profile_vocabulary(*sources: Any) -> dict[str, set[str]]:
    """
    The set of claims the profile actually supports.

    Pass anything stringable — the raw profile dict, the original bullets, the
    summary. Everything is flattened, because a fact stated anywhere in the
    candidate's own material is a fact they may restate in a bullet.
    """
    blob = " ".join(_flatten(sources))
    numbers = {_norm_number(n) for n in _NUMBER.findall(blob)}
    numbers.discard("")
    proper = {t.lower() for t in _PROPER.findall(blob)}
    proper |= {t.lower() for t in _CAMEL.findall(blob)}
    # Bare words too: "kubernetes" written lowercase in the profile still
    # supports "Kubernetes" in a bullet.
    proper |= {w.lower() for w in re.findall(r"\b[A-Za-z][A-Za-z0-9.+#/-]{1,}\b", blob)}
    return {"numbers": numbers, "proper": proper}


def _flatten(value: Any) -> Iterable[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        out: list[str] = []
        for key, item in value.items():
            out.append(str(key))
            out.extend(_flatten(item))
        return out
    if isinstance(value, (list, tuple, set)):
        out = []
        for item in value:
            out.extend(_flatten(item))
        return out
    return [str(value)]


# A word is supported if the profile carries it or a close morphological
# relative: "European clients" in the profile supports "clients across Europe"
# in a rewrite. Rewording is the entire point of tailoring, so a gate that
# rejects a legitimate inflection is a gate nobody will leave switched on.
_STEM_MIN = 4


def _supported(token: str, known: set[str]) -> bool:
    low = token.lower()
    if low in known:
        return True
    if len(low) < _STEM_MIN:
        return False
    return any(
        (word.startswith(low) or low.startswith(word))
        for word in known
        if len(word) >= _STEM_MIN and abs(len(word) - len(low)) <= 4
    )


def unsupported_claims(text: str, vocabulary: dict[str, set[str]]) -> list[str]:
    """
    What this text asserts that the profile does not support.

    Empty list means the rewrite is safe to accept.
    """
    problems: list[str] = []

    # Numbers are matched exactly, and deliberately so. "4M users" and "4.2M
    # users" are different claims, and a fabricated figure is the failure this
    # whole module exists to prevent.
    for raw in _NUMBER.findall(text or ""):
        token = _norm_number(raw)
        if not token or token in HARMLESS_NUMBERS:
            continue
        if token not in vocabulary["numbers"]:
            problems.append(f"invented number {raw.strip()!r}")

    # The house style opens every bullet with an action verb, so a capital in
    # the first position usually means "start of sentence", not "name". But
    # only skip it when the word is actually verb-shaped: waving through
    # whatever happens to be first would let "Stripe payments were integrated"
    # smuggle an employer past the gate in the one position nobody checks.
    body = (text or "").strip()
    first_word = body.split(" ", 1)[0].strip(".,;:") if body else ""
    skip_first = bool(first_word) and (
        first_word in COMMON_CAPS or first_word.lower().endswith("ed"))

    for index, token in enumerate(_PROPER.findall(body)):
        if token in COMMON_CAPS or len(token) < 3:
            continue
        if index == 0 and skip_first and token == first_word:
            continue
        if not _supported(token, vocabulary["proper"]):
            problems.append(f"unsupported proper noun {token!r}")

    for token in _CAMEL.findall(text or ""):
        if not _supported(token, vocabulary["proper"]):
            problems.append(f"unsupported technology {token!r}")

    # Report each distinct problem once; a bullet repeating "Kubernetes" twice
    # has one problem, not two.
    seen: set[str] = set()
    return [p for p in problems if not (p in seen or seen.add(p))]


def check_rewrite(original: str, revised: str,
                  vocabulary: dict[str, set[str]]) -> list[str]:
    """
    Claims the revision adds that neither the original nor the profile carries.

    The original is folded into the vocabulary for this comparison: a bullet is
    always allowed to keep what it already said, even in a rewritten shape.
    """
    local = {
        "numbers": vocabulary["numbers"] | {
            _norm_number(n) for n in _NUMBER.findall(original or "")},
        "proper": vocabulary["proper"] | {
            t.lower() for t in _PROPER.findall(original or "")}
        | {t.lower() for t in _CAMEL.findall(original or "")},
    }
    return unsupported_claims(revised, local)
