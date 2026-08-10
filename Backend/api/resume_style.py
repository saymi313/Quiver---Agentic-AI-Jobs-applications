"""
House style for generated resumes.

The rules here are formatting constraints that apply to every resume this
project produces, whatever the target job. They are separate from `behuman.py`,
which judges *voice*; this module judges *typography and mechanics*.

Two of them need explaining because they look arbitrary:

  * No hyphen characters. Some ATS tokenisers split on `-`, so "full-stack"
    can index as "full" and "stack", and a line-broken "settle-ment" indexes as
    two non-words. Writing the compound open ("full stack") is read correctly by
    every parser. Date ranges use the word "to" for the same reason.

  * No first person. "I built" wastes the strongest position in the line, which
    belongs to the verb.

`enforce()` is the entry point: it rewrites what can be rewritten mechanically.
`lint()` reports what cannot, so a human fixes it rather than a regex guessing.
"""

from __future__ import annotations

import re
from typing import Any

# --------------------------------------------------------------------------
# Hyphens and dashes
# --------------------------------------------------------------------------

DASHES = "‐‑‒–—―"  # ‐ ‑ ‒ – — ―

MONTHS = {
    "jan": "January", "feb": "February", "mar": "March", "apr": "April",
    "may": "May", "jun": "June", "jul": "July", "aug": "August",
    "sep": "September", "sept": "September", "oct": "October",
    "nov": "November", "dec": "December",
}

# Compounds that must not simply lose their hyphen: "e-commerce" -> "ecommerce",
# not "e commerce". Everything not listed becomes two words, which is correct
# for the overwhelming majority ("real-time", "end-to-end", "job-search").
CLOSED = {
    "e-commerce": "ecommerce", "e-mail": "email", "e-learning": "elearning",
    "re-usable": "reusable", "co-founder": "cofounder", "multi-tenant": "multitenant",
    "front-end": "frontend", "back-end": "backend", "full-stack": "full stack",
    "pre-processing": "preprocessing", "post-processing": "postprocessing",
    "on-boarding": "onboarding", "de-duplication": "deduplication",
}

_RANGE = re.compile(
    r"\b([A-Z][a-z]{2,8}\.?\s+\d{4}|\d{1,2}/\d{4}|\d{4})\s*"
    rf"(?:[{DASHES}\-]+|\bto\b)\s*"
    r"([A-Z][a-z]{2,8}\.?\s+\d{4}|\d{1,2}/\d{4}|\d{4}|Present|Current|Now|Ongoing)\b"
)

_MONTH_WORD = re.compile(r"\b([A-Z][a-z]{2})[a-z]*\.?\s+(\d{4})\b")


def _full_month(text: str) -> str:
    """Mar 2026 -> March 2026. Leaves already-full names alone."""
    def repl(m: re.Match) -> str:
        full = MONTHS.get(m.group(1).lower())
        return f"{full} {m.group(2)}" if full else m.group(0)
    return _MONTH_WORD.sub(repl, text)


def date_range(text: str) -> str:
    """Rewrite any date range to `August 2023 to Present`."""
    def repl(m: re.Match) -> str:
        return f"{_full_month(m.group(1))} to {_full_month(m.group(2))}"
    return _RANGE.sub(repl, _full_month(text))


def dehyphenate(text: str) -> str:
    """
    Remove every hyphen and dash used as punctuation or as a compound joiner.

    URLs and email addresses are left alone by `enforce()`, which never routes
    them here — a hyphen inside `linkedin.com/in/usairam-saeed-148044285` is
    part of the address, and removing it breaks the link.
    """
    if not text:
        return ""
    out = text
    for src, dst in CLOSED.items():
        out = re.sub(re.escape(src), dst, out, flags=re.I)
        out = re.sub(re.escape(src.replace("-", "‑")), dst, out, flags=re.I)

    # A dash with space either side was standing in for a comma or colon.
    out = re.sub(rf"\s+(?:[{DASHES}]|--+)\s+", ", ", out)
    # A dash joining two word characters was a compound: open it up.
    out = re.sub(rf"(?<=\w)(?:[{DASHES}]|-)(?=\w)", " ", out)
    # Anything left (leading, trailing, doubled) is decoration.
    out = re.sub(rf"[{DASHES}-]+", " ", out)
    return re.sub(r"\s{2,}", " ", out).strip()


# --------------------------------------------------------------------------
# Other mechanical rules
# --------------------------------------------------------------------------

EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
    "\U00002190-\U000021FF\U00002B00-\U00002BFF️❤]"
)

FIRST_PERSON = re.compile(
    r"\b(I|I'm|I've|I'll|me|my|mine|myself|we|our|ours|us)\b", re.I)

WEAK_OPENERS = re.compile(
    r"^\s*(responsible for|worked on|helped (?:to )?|assisted (?:with|in)|"
    r"tasked with|involved in|participated in|duties included)", re.I)

# Soft claims that carry no evidence. Flagged, never auto-removed: the fix is a
# rewrite with a fact in it, which a regex cannot invent.
SOFT_CLAIMS = re.compile(
    r"\b(strong communicator|team player|hard.?working|self.?starter|detail.?oriented|"
    r"go.?getter|passionate about|excellent communication|proven track record|"
    r"think outside the box|results.?driven|highly motivated)\b", re.I)


def phone(text: str) -> str:
    """+92-301-8165385 -> +92 301 8165385, keeping the leading plus."""
    if not text:
        return ""
    body = text.strip()
    lead = "+" if body.startswith("+") else ""
    body = body.lstrip("+")
    return lead + re.sub(r"\s{2,}", " ", re.sub(rf"[{DASHES}\-.()]", " ", body)).strip()


# A URL or email inside prose. Hyphens in these are part of the address, so
# they are shielded from `dehyphenate` and restored untouched.
_ADDRESS = re.compile(
    r"\S*(?:https?://|www\.)\S+|[\w.+-]+@[\w-]+\.[\w.-]+|"
    r"\b[\w-]+(?:\.[\w-]+)*\.(?:com|io|dev|app|net|org|pk|co|ai)(?:/\S*)?", re.I)


def enforce(text: str) -> str:
    """Apply every rule that can be applied without judgement.

    URLs and email addresses pass through byte-identical: a hyphen inside
    `usairam-saeed.vercel.app` is part of the address, not punctuation."""
    if not text:
        return ""
    shielded: list[str] = []

    def shield(m: re.Match) -> str:
        shielded.append(m.group(0))
        return f"\x02{len(shielded) - 1}\x03"

    out = _ADDRESS.sub(shield, str(text))
    out = EMOJI.sub("", out)
    out = date_range(out)
    out = dehyphenate(out)
    out = re.sub(r"\s{2,}", " ", out).strip()
    for i, original in enumerate(shielded):
        out = out.replace(f"\x02{i}\x03", original)
    return out


def lint(text: str, *, where: str = "") -> list[str]:
    """Report what `enforce()` deliberately will not rewrite for you."""
    problems: list[str] = []
    tag = f"{where}: " if where else ""

    for label, pattern in (("first person", FIRST_PERSON),
                           ("weak opener", WEAK_OPENERS),
                           ("unevidenced soft claim", SOFT_CLAIMS)):
        hit = pattern.search(text or "")
        if hit:
            problems.append(f"{tag}{label} — {hit.group(0).strip()!r}")

    if re.search(rf"[{DASHES}-]", _ADDRESS.sub(" ", text or "")):
        problems.append(f"{tag}hyphen or dash survived enforcement")
    if EMOJI.search(text or ""):
        problems.append(f"{tag}emoji")
    if text and not re.match(r"^[A-Z]", text.strip()):
        problems.append(f"{tag}does not start with a capital")
    return problems


def file_stem(name: str, company: str = "", role: str = "") -> str:
    """
    House naming for every generated resume file: Name_Company_Role.

    "Usairam Saeed" + "SpaceX" + "Full Stack Engineer" becomes
    `Usairam_Saeed_SpaceX_Full_Stack_Engineer`. A role like
    "Frontend Engineer at SpaceX" is split on " at " so the company is not
    duplicated. Empty parts are simply skipped, never guessed.
    """
    if role and not company:
        head, _, tail = role.partition(" at ")
        if tail.strip():
            role, company = head.strip(), tail.strip()

    def words(text: str, limit: int) -> str:
        parts = re.findall(r"[A-Za-z0-9]+", text or "")
        return "_".join(parts)[:limit].rstrip("_")

    bits = [words(name or "Resume", 40), words(company, 30), words(role, 40)]
    return "_".join(b for b in bits if b)


def skill_rows(lines: list[str]) -> list[dict[str, str]]:
    """
    Split `Languages: JavaScript, C++` into a bold category and its list.

    Shared by the LaTeX and DOCX renderers so the two cannot drift — they used
    to carry byte-identical private copies of this. A line with no colon still
    becomes a row under a generic label rather than being silently dropped.
    """
    rows: list[dict[str, str]] = []
    for line in lines or []:
        if not line or not line.strip():
            continue
        label, sep, items = line.partition(":")
        if sep and len(label) <= 40:
            rows.append({"label": enforce(label), "value": enforce(items)})
        else:
            rows.append({"label": "Also", "value": enforce(line)})
    return rows


def contact_parts(content: Any) -> list[str]:
    """
    Contact line in the reference order: location, phone, email, spelled-out
    URLs. Returns plain-text parts; each renderer joins and escapes its own
    way. URLs are never style-enforced — their hyphens are part of the address.
    """
    parts: list[str] = []
    if getattr(content, "location", ""):
        parts.append(enforce(content.location))
    if getattr(content, "phone", ""):
        parts.append(phone(content.phone))
    if getattr(content, "email", ""):
        parts.append(content.email)
    for link in getattr(content, "links", None) or []:
        url = (link.get("url") or "").strip()
        if url:
            parts.append(re.sub(r"^https?://(www\.)?", "", url).rstrip("/"))
    return [p for p in parts if p]


def report(fields: dict[str, Any]) -> dict[str, Any]:
    """Lint a whole document. `fields` maps a label to a string or list of strings."""
    problems: list[str] = []
    for label, value in fields.items():
        items = value if isinstance(value, list) else [value]
        for i, item in enumerate(items):
            if not isinstance(item, str) or not item.strip():
                continue
            suffix = f"[{i + 1}]" if isinstance(value, list) else ""
            problems += lint(item, where=f"{label}{suffix}")
    return {"clean": not problems, "problems": problems}
