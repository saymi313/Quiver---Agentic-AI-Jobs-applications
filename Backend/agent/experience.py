"""
Experience-level gate.

Keeps the queue to roles a candidate with 1-3 years can realistically win, using
three signals in descending order of trust:

  1. An explicit level from the board itself (The Muse and Jobicy publish one).
  2. The job title — "Senior", "Staff", "Principal" are unambiguous.
  3. A years requirement parsed out of the description ("3+ years", "2-4 years").

A role passes when nothing rules it out. Silence is not disqualifying: plenty of
good postings never state a number, and rejecting those would throw away most of
the market.
"""

from __future__ import annotations

import re
from typing import Any

WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 10, "ten": 10,
}

# "2-4 years", "2 to 4 years"
RANGE_RE = re.compile(
    r"\b(\d{1,2})\s*(?:-|–|—|to|\+?\s*-\s*)\s*(\d{1,2})\s*\+?\s*(?:years?|yrs?)\b", re.I)
# "3+ years", "at least 3 years", "minimum of 3 years", "3 years of experience"
MIN_RE = re.compile(
    r"\b(?:at\s+least\s+|minimum\s+(?:of\s+)?|min\.?\s*|over\s+|more\s+than\s+)?"
    r"(\d{1,2})\s*\+?\s*(?:years?|yrs?)\b(?![^.]{0,20}\bago\b)", re.I)
WORD_RE = re.compile(
    r"\b(?:at\s+least\s+|minimum\s+(?:of\s+)?)?"
    r"(one|two|three|four|five|six|seven|eight|nine|ten)\s+(?:\+\s*)?(?:years?|yrs?)\b", re.I)

SENIOR_TITLE = re.compile(
    r"\b(senior|sr\.?|staff|principal|lead|leader|head\s+of|director|vp|vice\s+president|"
    r"chief|architect|manager|distinguished|fellow|expert|specialist\s+iv|iii|iv|v)\b", re.I)
JUNIOR_TITLE = re.compile(
    r"\b(intern|internship|apprentice|trainee|graduate|working\s+student|placement|"
    r"co-?op|entry[\s-]level|junior|jr\.?)\b", re.I)

SENIOR_LEVEL = re.compile(r"senior|lead|principal|staff|director|executive|management", re.I)
JUNIOR_LEVEL = re.compile(r"intern|entry|graduate|student", re.I)


def required_years(text: str) -> tuple[int | None, int | None]:
    """
    Lowest and highest years-of-experience the posting asks for.

    Returns (None, None) when the posting never says. Only the first ~4000
    characters are read: requirements live near the top, and benefits sections
    further down mention years for unrelated reasons.
    """
    if not text:
        return None, None
    head = text[:4000]

    m = RANGE_RE.search(head)
    if m:
        low, high = int(m.group(1)), int(m.group(2))
        if 0 <= low <= high <= 30:
            return low, high

    mins: list[int] = []
    for m in MIN_RE.finditer(head):
        n = int(m.group(1))
        if 0 <= n <= 30:
            mins.append(n)
    for m in WORD_RE.finditer(head):
        mins.append(WORD_NUMBERS[m.group(1).lower()])

    if not mins:
        return None, None
    # Several numbers usually means "3 years of X, 5 years of Y" — the smallest
    # is the entry bar; demanding all maxima would reject nearly everything.
    return min(mins), None


def seniority(title: str, level: str = "") -> str:
    """
    intern | junior | mid | senior.

    The title is read first and trusted most: "Senior Software Engineer" is
    senior no matter how a board files it. This ordering matters because LinkedIn
    stamps a huge share of postings — senior ones included — with the single
    coarse bucket "Mid-Senior level", and reading that bucket before the title
    once let those senior roles slip the gate. So an unambiguous title word wins,
    and only a neutral title falls back to the board's own level.
    """
    t = title or ""
    if JUNIOR_TITLE.search(t):
        return "intern" if re.search(r"intern|apprentice|placement|co-?op", t, re.I) else "junior"
    if SENIOR_TITLE.search(t):
        return "senior"

    if level:
        # "Mid-Senior level" is LinkedIn's catch-all for the whole middle of the
        # market; with a neutral title it is treated as mid, so genuine mid roles
        # are not thrown out along with the senior ones the title would catch.
        if re.search(r"mid[\s-]?senior|mid[\s-]?level|associate|^\s*mid\b", level, re.I):
            return "mid"
        if JUNIOR_LEVEL.search(level):
            return "junior"
        if SENIOR_LEVEL.search(level):
            return "senior"
    return "mid"


def verdict(job: dict[str, Any], *, min_years: int = 1, max_years: int = 3,
            allow_internships: bool = False) -> tuple[bool, str]:
    """
    Should this role stay in the queue?

    `max_years` is the ceiling on what the posting may *demand*, not the
    candidate's own experience: a job asking for 8 years is out of range for
    someone with 2, regardless of how well the keywords match.
    """
    title = job.get("title") or ""
    level = job.get("level") or ""
    kind = seniority(title, level)

    if kind == "intern" and not allow_internships:
        return False, "internship or placement"
    if kind == "senior":
        return False, f"senior-level title ({title[:40]})"

    lo, hi = required_years(job.get("description") or "")
    if lo is not None and lo > max_years:
        return False, f"asks for {lo}+ years, above your {max_years}-year ceiling"
    if hi is not None and hi < min_years:
        return False, f"caps at {hi} years, below your {min_years}-year floor"

    if lo is not None:
        return True, f"asks for {lo}{'-' + str(hi) if hi else '+'} years"
    if level:
        return True, f"board level: {level}"
    return True, f"{kind}-level, no explicit years requirement"


def describe(job: dict[str, Any]) -> str:
    """One-line summary for logs."""
    lo, hi = required_years(job.get("description") or "")
    years = f"{lo}-{hi}y" if lo is not None and hi else (f"{lo}+y" if lo is not None else "no years stated")
    return f"{seniority(job.get('title', ''), job.get('level', ''))}, {years}"
