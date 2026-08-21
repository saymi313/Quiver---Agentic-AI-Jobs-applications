"""
Turn a posting's prose into fields.

Tsenta's job panel is a parsed document: a salary range, a seniority, a work
arrangement, an extracted list of skills, and a deadline — not just a link and a
score. This module is the parser behind the same panel in Quiver. It is
deliberately deterministic and free: no LLM call, because it runs over every
scored job and the day's model budget is small. Regex and a dictionary get the
large majority right, and a wrong salary is worse than a missing one — so every
extractor here would rather return nothing than guess.

Everything is a pure function of the job dict. `enrich(job)` is the one callers
use; the rest are exposed for the tests, which pin each format that has ever
mattered.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

# --------------------------------------------------------------------------
# Salary
# --------------------------------------------------------------------------

_CURRENCY_SYMBOL = {"$": "USD", "£": "GBP", "€": "EUR", "¥": "JPY", "₹": "INR"}
_CURRENCY_CODES = ("USD", "GBP", "EUR", "CAD", "AUD", "CHF", "JPY", "INR", "PKR", "SGD")

# A salary is only read from a segment that says it is one. Compensation numbers
# and "posted 3 days ago" look identical to a regex; the context word is what
# tells them apart, so one is required before any number is trusted.
_SALARY_CONTEXT = re.compile(
    r"(salary|compensation|pay|package|base|/\s*(yr|year|annum)|per\s+(year|annum|hour)"
    r"|k/yr|\bOTE\b|remuneration|wage)", re.I)

# A money amount: optional currency, digits with thousands separators or a k
# suffix. "43k", "120,000", "150K", "70000".
_AMOUNT = re.compile(
    r"(?P<sym>[$£€¥₹])?\s*"
    r"(?P<num>\d{1,3}(?:[,\s]\d{3})+|\d+(?:\.\d+)?)\s*"
    r"(?P<k>k\b)?",
    re.I)


def _amount_value(num: str, k: str | None) -> float | None:
    n = float(num.replace(",", "").replace(" ", ""))
    if k:
        n *= 1000
    # A salary is not a single-digit number and not a headcount. Below 1,000
    # without a k suffix is almost never pay.
    if n < 1000:
        return None
    return n


def parse_salary(text: str) -> tuple[float | None, float | None, str | None]:
    """(min, max, currency) or (None, None, None). Never guesses out of context."""
    if not text:
        return (None, None, None)

    # Look only inside a window around a salary context word — the whole
    # description contains many numbers, almost none of them pay.
    best: tuple[float | None, float | None, str | None] = (None, None, None)
    for ctx in _SALARY_CONTEXT.finditer(text):
        window = text[max(0, ctx.start() - 60): ctx.end() + 60]
        currency = None
        for code in _CURRENCY_CODES:
            if re.search(rf"\b{code}\b", window):
                currency = code
                break
        amounts: list[float] = []
        for m in _AMOUNT.finditer(window):
            value = _amount_value(m.group("num"), m.group("k"))
            if value is None:
                continue
            if currency is None and m.group("sym"):
                currency = _CURRENCY_SYMBOL.get(m.group("sym"))
            amounts.append(value)
        if not amounts:
            continue
        amounts = amounts[:2]
        lo = min(amounts)
        hi = max(amounts)
        # A context that yields a real pair wins over one that yields a lone
        # number, so "40k-60k salary" beats an earlier stray "$5 credit".
        if best == (None, None, None) or (best[0] == best[1] and lo != hi):
            best = (lo, hi if hi != lo else None, currency)
        if lo != hi:
            break
    return best


# --------------------------------------------------------------------------
# Seniority
# --------------------------------------------------------------------------

# Ordered most-senior first so "Senior Staff" reads as staff, and the title is
# tried before the body — a title is the employer's own label for the level.
_SENIORITY = [
    ("principal", re.compile(r"\bprincipal\b", re.I)),
    ("staff", re.compile(r"\bstaff\b", re.I)),
    ("lead", re.compile(r"\b(lead|le&nbsp;|team lead|tech lead)\b", re.I)),
    ("senior", re.compile(r"\b(senior|sr\.?|snr)\b", re.I)),
    ("mid", re.compile(r"\b(mid[- ]?level|intermediate)\b", re.I)),
    ("junior", re.compile(r"\b(junior|jr\.?)\b", re.I)),
    ("entry", re.compile(r"\b(entry[- ]?level|graduate|new grad|early career)\b", re.I)),
    ("intern", re.compile(r"\b(intern|internship|placement|co[- ]?op)\b", re.I)),
]


def detect_seniority(title: str, text: str = "") -> str | None:
    for level, pattern in _SENIORITY:
        if pattern.search(title or ""):
            return level
    for level, pattern in _SENIORITY:
        if pattern.search(text or ""):
            return level
    return None


# --------------------------------------------------------------------------
# Work arrangement
# --------------------------------------------------------------------------

_HYBRID = re.compile(r"\bhybrid\b", re.I)
_REMOTE = re.compile(r"\b(fully|100%\s+)?remote\b|work from home|\bwfh\b|distributed team", re.I)
_ONSITE = re.compile(r"\b(on[- ]?site|in[- ]?office|in[- ]?person)\b", re.I)


def detect_arrangement(location: str, text: str = "") -> str | None:
    blob = f"{location or ''} {text or ''}"
    # Hybrid first: a hybrid posting nearly always also says "remote" somewhere,
    # so checking remote first would mislabel it.
    if _HYBRID.search(blob):
        return "hybrid"
    if _REMOTE.search(blob):
        return "remote"
    if _ONSITE.search(blob):
        return "onsite"
    return None


# --------------------------------------------------------------------------
# Employment type
# --------------------------------------------------------------------------

_EMPLOYMENT = [
    ("Internship", re.compile(r"\b(internship|intern)\b", re.I)),
    ("Contract", re.compile(r"\b(contract|contractor|freelance|fixed[- ]term)\b", re.I)),
    ("Part Time", re.compile(r"\bpart[- ]?time\b", re.I)),
    ("Full Time", re.compile(r"\bfull[- ]?time\b", re.I)),
]


def detect_employment_type(text: str) -> str | None:
    for label, pattern in _EMPLOYMENT:
        if pattern.search(text or ""):
            return label
    return None


# --------------------------------------------------------------------------
# Skills
# --------------------------------------------------------------------------
#
# A dictionary rather than an LLM, for the same budget reason as the rest. The
# canonical name on the left is what shows on the chip; the alternates are what
# a posting might call it. Ordered roughly by how a resume is aimed — languages
# and frameworks first, methods and soft skills after — because the extracted
# list is truncated and the technical terms are the ones a keyword match needs.

_SKILL_DICT: list[tuple[str, tuple[str, ...]]] = [
    ("JavaScript", ("javascript", "js", "es6", "ecmascript")),
    ("TypeScript", ("typescript", "ts")),
    ("Python", ("python",)),
    ("Java", ("java",)),
    ("C++", ("c\\+\\+", "cpp")),
    ("C#", ("c#", "c sharp", "\\.net", "dotnet")),
    ("Go", ("golang", "\\bgo\\b")),
    ("Rust", ("rust",)),
    ("Ruby", ("ruby", "rails")),
    ("PHP", ("php", "laravel")),
    ("Swift", ("swift",)),
    ("Kotlin", ("kotlin",)),
    ("SQL", ("sql", "postgres", "postgresql", "mysql")),
    ("React", ("react", "react.js", "reactjs")),
    ("Next.js", ("next.js", "nextjs")),
    ("Vue", ("vue", "vue.js", "vuejs")),
    ("Angular", ("angular",)),
    ("Node.js", ("node.js", "nodejs", "node")),
    ("Express", ("express", "express.js")),
    ("Django", ("django",)),
    ("Flask", ("flask",)),
    ("FastAPI", ("fastapi",)),
    ("Spring", ("spring boot", "spring")),
    ("GraphQL", ("graphql",)),
    ("REST APIs", ("rest", "restful", "rest api", "apis")),
    ("MongoDB", ("mongodb", "mongo")),
    ("Redis", ("redis",)),
    ("Elasticsearch", ("elasticsearch", "elastic search")),
    ("AWS", ("aws", "amazon web services")),
    ("Azure", ("azure",)),
    ("Google Cloud", ("gcp", "google cloud")),
    ("Docker", ("docker",)),
    ("Kubernetes", ("kubernetes", "k8s")),
    ("Terraform", ("terraform",)),
    ("Infrastructure as Code", ("infrastructure as code", "iac")),
    ("CI/CD", ("ci/cd", "ci / cd", "continuous integration", "continuous delivery")),
    ("Git", ("\\bgit\\b", "github", "gitlab")),
    ("Linux", ("linux", "unix")),
    ("Machine Learning", ("machine learning", "\\bml\\b", "deep learning")),
    ("AI", ("artificial intelligence", "\\bai\\b", "llm", "genai")),
    ("Data Science", ("data science", "data scientist")),
    ("TensorFlow", ("tensorflow",)),
    ("PyTorch", ("pytorch",)),
    ("Figma", ("figma",)),
    ("Agile", ("agile",)),
    ("Scrum", ("scrum",)),
    ("Kanban", ("kanban",)),
    ("Microservices", ("microservices", "micro-services")),
    ("Problem Solving", ("problem solving", "problem-solving")),
    ("Communication", ("communication",)),
    ("Collaboration", ("collaboration", "teamwork")),
    ("Leadership", ("leadership",)),
    ("Analytical Thinking", ("analytical",)),
]

# The boundary excludes only letters and digits, not punctuation: a skill at
# the end of a sentence ("AWS.", "Node.js.") must still match, and internal
# dots and pluses are part of the token ("node.js", "c++"). A class that
# included "." blocked exactly the end-of-sentence case, which is common.
_SKILL_PATTERNS = [
    (name, re.compile("|".join(rf"(?<![A-Za-z0-9]){alt}(?![A-Za-z0-9])" for alt in alts), re.I))
    for name, alts in _SKILL_DICT
]

MAX_SKILLS = 24


def extract_skills(text: str) -> list[str]:
    """Canonical skills present in the text, in dictionary order, capped."""
    if not text:
        return []
    found = [name for name, pattern in _SKILL_PATTERNS if pattern.search(text)]
    return found[:MAX_SKILLS]


# --------------------------------------------------------------------------
# Deadline
# --------------------------------------------------------------------------

_DEADLINE_CONTEXT = re.compile(
    r"(appl(y|ications?)\s+(by|before|close|deadline)|closing date|deadline"
    r"|end date|closes on|apply by|last date)", re.I)

_MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], start=1)}

_DATE_DMY = re.compile(r"\b(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\b")          # 30 August 2026
_DATE_MDY = re.compile(r"\b([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})\b")        # August 30, 2026
_DATE_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")                    # 2026-08-30
_DATE_NUM = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")                # 30/08/2026


def _iso(y: int, m: int, d: int) -> str | None:
    try:
        return datetime(y, m, d).strftime("%Y-%m-%d")
    except ValueError:
        return None


def parse_deadline(text: str) -> str | None:
    """An application deadline as YYYY-MM-DD, read only near a deadline word."""
    if not text:
        return None
    for ctx in _DEADLINE_CONTEXT.finditer(text):
        window = text[ctx.start(): ctx.end() + 40]
        m = _DATE_ISO.search(window)
        if m:
            got = _iso(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if got:
                return got
        m = _DATE_DMY.search(window)
        if m and m.group(2).lower() in _MONTHS:
            got = _iso(int(m.group(3)), _MONTHS[m.group(2).lower()], int(m.group(1)))
            if got:
                return got
        m = _DATE_MDY.search(window)
        if m and m.group(1).lower() in _MONTHS:
            got = _iso(int(m.group(3)), _MONTHS[m.group(1).lower()], int(m.group(2)))
            if got:
                return got
        m = _DATE_NUM.search(window)
        if m:
            got = _iso(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            if got:
                return got
    return None


# --------------------------------------------------------------------------
# The one entry point
# --------------------------------------------------------------------------

def enrich(job: dict[str, Any]) -> dict[str, Any]:
    """
    Parse a job into the fields the panel and the filters use.

    Returns only what was actually found — a caller stores the result over the
    row, so a key that is absent leaves whatever was there before rather than
    blanking it. `employment_type` is only offered when the row does not already
    carry one from its source, which is more reliable than prose.
    """
    title = job.get("title") or ""
    description = job.get("description") or ""
    location = job.get("location") or ""
    blob = f"{title}\n{description}"

    out: dict[str, Any] = {}

    lo, hi, currency = parse_salary(blob)
    if lo is not None:
        out["salary_min"] = lo
        out["salary_max"] = hi
        out["salary_currency"] = currency

    seniority = detect_seniority(title, description)
    if seniority:
        out["seniority"] = seniority

    arrangement = detect_arrangement(location, description)
    if arrangement:
        out["work_arrangement"] = arrangement

    if not (job.get("employment_type") or "").strip():
        etype = detect_employment_type(blob)
        if etype:
            out["employment_type"] = etype

    skills = extract_skills(blob)
    if skills:
        out["skills"] = skills

    deadline = parse_deadline(description)
    if deadline:
        out["deadline"] = deadline

    return out
