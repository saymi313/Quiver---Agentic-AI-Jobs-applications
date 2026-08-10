"""
The ten role categories the agent searches, and how a job title maps to one.

Scope rule: a job that maps to nothing is not tracked at all. The search is
defined by these categories, so an SRE or data-analyst posting that happens to
surface from a board is dropped rather than stored with a vague label.

Order is the whole design. The rules are checked most specific first, because
the category names overlap by construction:

    "AI Software Engineer"  -> ai_software_engineer, not ai_engineer
    "AI Engineer"           -> ai_engineer,          not software_engineer
    "UI/UX Designer"        -> ui_ux,                not ui_design or ux_design
    "Senior Product Designer" -> product_design,     not ui_ux

Titles are matched, not descriptions: a backend posting that mentions React in
its stack list is still a backend role. `describe()` exists so the UI and the
logs can show the human label without importing the table.
"""

from __future__ import annotations

import re
from typing import Any

# slug -> human label, in the order the spec lists them.
CATEGORIES: dict[str, str] = {
    "backend": "Backend",
    "frontend": "Frontend",
    "fullstack": "Full stack",
    "software_engineer": "Software engineer",
    "ai_engineer": "AI engineer",
    "ai_software_engineer": "AI software engineer",
    "product_design": "Product design",
    "ui_ux": "UI UX designer",
    "ui_design": "UI designer",
    "ux_design": "UX designer",
}

ALL = tuple(CATEGORIES)

# Anything here is not one of the ten no matter what else the title says.
# Checked before the category rules so "Data Engineer" never lands in backend.
OUT_OF_SCOPE = re.compile(
    r"\b(data (?:engineer|analyst|scientist)|analytics engineer|sre|site reliability|"
    r"devops|platform engineer|infrastructure engineer|security engineer|qa|"
    r"test engineer|automation engineer|support engineer|solutions? (?:architect|engineer)|"
    r"sales engineer|technical writer|scrum master|project manager|product manager|"
    r"business analyst|graphic designer|motion designer|3d artist|illustrator|"
    r"marketing|recruiter|accountant|hr\b)",
    re.I,
)

# (slug, pattern) checked in order. First hit wins.
RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    # --- AI, most specific first -----------------------------------------
    ("ai_software_engineer", re.compile(
        r"\b(ai|ml|machine learning|genai|llm)\b[\w /]*\b(software|application|product)\b"
        r"[\w /]*\bengineer|"
        r"\bsoftware engineer\b[\w /,()-]*\b(ai|ml|machine learning|llm|genai)\b|"
        r"\b(ai|ml)\s*/\s*(software|swe)\b", re.I)),
    ("ai_engineer", re.compile(
        r"\b(ai|ml|machine learning|deep learning|llm|genai|generative ai|nlp|"
        r"computer vision|mlops|applied scientist|research engineer)\b"
        r"[\w /-]*\b(engineer|scientist|developer|specialist)\b|"
        r"\b(ai|ml)\s*engineer\b", re.I)),

    # --- design, most specific first --------------------------------------
    ("ui_ux", re.compile(
        r"\bui\s*[/&+·-]?\s*ux\b|\bux\s*[/&+·-]?\s*ui\b|"
        r"\buser interface\b[\w /]*\buser experience\b", re.I)),
    ("product_design", re.compile(
        r"\bproduct design(?:er)?\b|\bdesign(?:er)? ?[,-]? product\b|"
        r"\bsenior designer\b|\bdigital product design", re.I)),
    ("ux_design", re.compile(
        r"\bux\b|\buser experience\b|\bexperience design(?:er)?\b|"
        r"\binteraction design(?:er)?\b|\bux research(?:er)?\b|\buser research(?:er)?\b", re.I)),
    ("ui_design", re.compile(
        r"\bui\b|\buser interface\b|\bvisual design(?:er)?\b|\binterface design(?:er)?\b",
        re.I)),

    # --- engineering ------------------------------------------------------
    ("fullstack", re.compile(
        r"\bfull[\s-]?stack\b|\bfullstack\b|\bmern\b|\bmean stack\b|"
        r"\bfront ?end and back ?end\b", re.I)),
    ("frontend", re.compile(
        r"\bfront[\s-]?end\b|\bfrontend\b|\breact(?:\.js)?\s*(developer|engineer)\b|"
        r"\b(vue|angular|next\.?js|svelte)\s*(developer|engineer)\b|"
        r"\bweb developer\b|\bui engineer\b|\bclient[\s-]?side\b", re.I)),
    ("backend", re.compile(
        r"\bback[\s-]?end\b|\bbackend\b|\bserver[\s-]?side\b|\bapi engineer\b|"
        # The `(?:\.?js)?` matters: "Node.js Developer" is the common spelling,
        # and a bare \bnode\b would stop at the dot and never reach "Developer".
        r"\b(node(?:\.?js)?|nest(?:\.?js)?|express(?:\.?js)?|python|java|golang|go|ruby|"
        r"php|\.net|c#|rails|django|laravel|spring|fastapi)\s*(developer|engineer)\b|"
        r"\bmicroservices? engineer\b", re.I)),
    # Deliberately last: the widest net, and it must not steal from the rest.
    ("software_engineer", re.compile(
        r"\bsoftware (?:development )?engineer\b|\bsoftware developer\b|\bsde\b|\bswe\b|"
        # "Product Engineer" is a standard startup title for a generalist
        # software engineer. The design rules run first, so "Product Designer"
        # is already claimed by product_design and cannot be stolen here.
        r"\bproduct engineer\b|"
        r"\bapplication developer\b|\bprogrammer\b|\bcomputer engineer\b|"
        r"\bsoftware craftsperson\b|^\s*(?:senior |junior |mid[\s-]?level )?"
        r"(?:developer|engineer)\s*(?:i{1,3}|[123])?\s*$", re.I)),
)

CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": [*ALL, "none"]},
        "why": {"type": "string"},
    },
    "required": ["category"],
}

CLASSIFY_SYSTEM = (
    "You place a job title into exactly one category, or 'none'.\n\n"
    + "\n".join(f"- {slug}: {label}" for slug, label in CATEGORIES.items())
    + "\n\nReturn 'none' unless the role genuinely belongs to one of these. Data, DevOps, "
      "SRE, QA, security, product management and graphic design are all 'none'. "
      "Judge the role itself, not the technologies listed."
)


def describe(slug: str | None) -> str:
    """Human label for a slug, for logs and the UI."""
    return CATEGORIES.get(slug or "", "Uncategorised")


def _rule_match(title: str) -> str | None:
    if not title or OUT_OF_SCOPE.search(title):
        return None
    for slug, pattern in RULES:
        if pattern.search(title):
            return slug
    return None


def classify(title: str, description: str = "", *, use_llm: bool = False,
             log=None) -> str | None:
    """
    Map a job title to one of the ten categories, or None to drop it.

    Rules answer the overwhelming majority. `use_llm` is opt-in and only ever
    consulted for a title no rule matched, so a discovery run does not spend a
    model call on every posting.
    """
    title = (title or "").strip()
    slug = _rule_match(title)
    if slug or not use_llm or not title:
        return slug

    # An unmatched title is usually genuinely out of scope. Only ask the model
    # when the title alone looks like it could be engineering or design work.
    if not re.search(r"\b(engineer|developer|design|architect|scientist|dev)\b", title, re.I):
        return None
    if OUT_OF_SCOPE.search(title):
        return None

    try:
        from . import llm

        ok, _ = llm.available()
        if not ok:
            return None
        prompt = f"Job title: {title}\n\n{(description or '')[:600]}"
        data = llm.complete_json(prompt, CLASSIFY_SCHEMA, system=CLASSIFY_SYSTEM,
                                 default={"category": "none"})
        guess = (data.get("category") or "none").strip()
        if guess in CATEGORIES:
            if log:
                log(f"[category] LLM mapped '{title[:48]}' -> {guess}")
            return guess
    except Exception:
        pass
    return None


def enabled_slugs(targeting: dict[str, Any] | None) -> set[str]:
    """Categories switched on in settings, defaulting to all ten."""
    wanted = (targeting or {}).get("categories")
    if not wanted:
        return set(ALL)
    return {s for s in wanted if s in CATEGORIES} or set(ALL)
