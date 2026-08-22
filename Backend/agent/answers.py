"""
Saved answers — the questions a profile cannot hold.

Some forms ask things no structured profile will ever carry: "Are you open to
co-living?", "What's your favourite side project?", "How did this role find you?"
The agent will not invent an answer to these, so without help it stops and waits.
This is the help: a small bank of question → answer pairs the user fills once,
consulted on every later form so a question answered by hand never has to be
answered again.

Two deliberate choices:

  * **Matching is forgiving but honest.** A saved pattern matches a field when
    the field's label contains it, or when most of the pattern's meaningful
    words appear in the label — so "open to co-living" still answers "Are you
    open to co-living arrangements?". It is the user's own words being reused,
    not a guess, so a loose match is safe in a way an invented answer never is.

  * **It never overrides the truthful rules.** These answers fill in where the
    profile and its rules had nothing to say; a work-authorisation or salary
    question is still answered from the profile. The bank is for the long tail,
    not for rewriting the known fields.
"""

from __future__ import annotations

import re

from . import store

# Words too common to carry meaning when scoring an overlap match.
_STOP = {
    "the", "a", "an", "to", "of", "and", "or", "you", "your", "are", "is", "do",
    "would", "be", "for", "in", "on", "with", "this", "that", "have", "has", "will",
    "any", "at", "as", "please", "what", "which", "how", "we", "our", "us", "if",
}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _keywords(s: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", _norm(s)) if w not in _STOP and len(w) > 1]


def load() -> list[dict[str, str]]:
    """Every saved answer with both halves present, in the order the user set."""
    raw = store.get_setting("custom_answers", []) or []
    out = []
    for a in raw:
        if isinstance(a, dict) and (a.get("match") or "").strip() and (a.get("answer") or "").strip():
            out.append({"match": a["match"].strip(), "answer": a["answer"].strip()})
    return out


def match(label: str, *, saved: list[dict[str, str]] | None = None) -> str | None:
    """
    The saved answer for a field label, or None.

    A direct substring is taken at once; otherwise the best word-overlap match at
    or above 70% of the pattern's keywords wins, so small wording differences
    between the saved question and the form's do not lose it.
    """
    lab = _norm(label)
    if not lab:
        return None
    entries = saved if saved is not None else load()

    best_answer: str | None = None
    best_score = 0.0
    for a in entries:
        m = _norm(a["match"])
        if not m:
            continue
        if m in lab or lab in m:
            return a["answer"]
        words = _keywords(m)
        if not words:
            continue
        score = sum(1 for w in words if w in lab) / len(words)
        if score >= 0.7 and score > best_score:
            best_score, best_answer = score, a["answer"]
    return best_answer


def as_yes_no(value: str | None) -> str | None:
    """A saved answer coerced to Yes/No for a button group, or None if it is not one."""
    v = (value or "").strip().lower()
    if v in ("yes", "y", "true", "1", "agree", "accept"):
        return "Yes"
    if v in ("no", "n", "false", "0", "decline"):
        return "No"
    return None
