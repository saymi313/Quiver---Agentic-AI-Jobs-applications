"""
Audit a generated resume PDF against the house style.

Everything here is checked against the *extracted* text and the PDF's own
drawing operators, not against the LaTeX source. That is the point: the source
can look correct while the PDF a parser sees is wrong, which is how a previous
build shipped merged words and hyphen-broken lines.

`audit_pdf()` is the hard gate: the tailor refuses to record a PDF that fails
it, and `/api/ats/build` reports the failures. `tools/check_resume.py` wraps
the same function as a CLI.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import resume_style as S
from .config import CV_DATA

# The document budget. Two pages fits every role and project at healthy bullet
# counts; anything longer means the fitter failed and must not be sent out.
MAX_PAGES = 2

# The reference layout's sections, in its order. Legacy headings stay in
# SECTIONS so boundary detection still works on older documents.
SECTIONS = ("SUMMARY", "SKILLS", "TECHNICAL SKILLS", "PROFESSIONAL EXPERIENCE",
            "PROJECTS", "EDUCATION", "CERTIFICATIONS", "AWARDS", "LANGUAGES",
            "ACHIEVEMENTS & CERTIFICATIONS", "AWARDS AND CERTIFICATIONS",
            "CERTIFICATIONS AND AWARDS")
ORDER = ["SUMMARY", "PROFESSIONAL EXPERIENCE", "PROJECTS", "TECHNICAL SKILLS",
         "EDUCATION", "ACHIEVEMENTS & CERTIFICATIONS"]

# Hyphens inside a URL or an email are part of the address, not style.
URLISH = re.compile(r"\S*(?:https?://|www\.|@|\.com|\.app|\.io|\.dev|\.pk)\S*")


def _intentional_camel() -> set[str]:
    """Camel-cased words that appear in the source content, so are not artefacts."""
    words: set[str] = set()
    profile = CV_DATA / "profile.yaml"
    if profile.is_file():
        words |= {w for w in re.findall(r"\b[A-Za-z]{4,}\b",
                                        profile.read_text(encoding="utf-8"))
                  if re.search(r"[a-z][A-Z]", w)}
    return words


def audit_pdf(pdf: Path) -> list[str]:
    """Every house-style violation in the PDF. Empty list means it passes."""
    import pdfplumber

    fails: list[str] = []
    with pdfplumber.open(pdf) as doc:
        pages = len(doc.pages)
        text = "\n".join(p.extract_text() or "" for p in doc.pages)
        chars = [c for p in doc.pages for c in p.chars]
        rects = [r for p in doc.pages for r in p.rects]
        curves = [c for p in doc.pages for c in p.curves]

    # -- length ------------------------------------------------------------
    if pages > MAX_PAGES:
        fails.append(f"{pages} pages, the document budget is {MAX_PAGES}")

    # -- colour ------------------------------------------------------------
    coloured = {tuple(c["non_stroking_color"]) for c in chars
                if c.get("non_stroking_color")
                and tuple(c["non_stroking_color"]) not in ((0,), (0.0,), (0, 0, 0), (0.0, 0.0, 0.0))}
    if coloured:
        fails.append(f"non-black text: {sorted(coloured)}")

    # -- shaded blocks -----------------------------------------------------
    # A section hairline is a filled rect a fraction of a point tall. Anything
    # thicker is the solid bar the house style bans.
    bars = [r for r in rects if (r["y1"] - r["y0"]) > 2.0]
    if bars:
        fails.append(f"{len(bars)} filled block(s) taller than a hairline "
                     f"(first: {bars[0]['x1'] - bars[0]['x0']:.0f}x{bars[0]['y1'] - bars[0]['y0']:.0f}pt)")
    if curves:
        fails.append(f"{len(curves)} curve/shading operator(s)")

    # -- fonts -------------------------------------------------------------
    fonts = {c["fontname"].split("+")[-1] for c in chars}
    non_times = {f for f in fonts if not re.search(r"(Times|NimbusRom|Termes|TeXGyreTermes|txtt|ntx)", f, re.I)}
    if non_times:
        fails.append(f"non-Times fonts: {sorted(non_times)}")

    # -- sizes -------------------------------------------------------------
    body = [round(c["size"], 1) for c in chars]
    if body:
        common = max(set(body), key=body.count)
        if not (10.4 <= common <= 11.1):
            fails.append(f"body text is {common}pt, house style is 10.5 to 11pt")
        biggest = max(body)
        # The FAANG-template look sets the name at 22pt small caps.
        if not (15.9 <= biggest <= 24.5):
            fails.append(f"largest text is {biggest}pt, the name should be 16 to 24pt")

    # -- hyphens, dashes, emoji -------------------------------------------
    stripped = URLISH.sub(" ", text)
    bad = re.findall(rf"\S*[{S.DASHES}\-]\S*", stripped)
    if bad:
        fails.append(f"{len(bad)} hyphen/dash outside a URL: {sorted(set(bad))[:6]}")
    if S.EMOJI.search(text):
        fails.append("emoji present")

    # -- first person ------------------------------------------------------
    fp = S.FIRST_PERSON.findall(text)
    if fp:
        fails.append(f"first person: {sorted(set(fp))}")
    weak = [ln for ln in text.split("\n") if S.WEAK_OPENERS.match(ln.lstrip("• "))]
    if weak:
        fails.append(f"{len(weak)} weak opener(s): {weak[:2]}")

    # -- merged words ------------------------------------------------------
    # "ImplementedStripe" — a lowercase letter immediately followed by an
    # uppercase one, which is what justified line-shrink produced before.
    #
    # Plenty of legitimate words look like that (DevOps, LinkedIn, MongoDB), so
    # the allowlist is derived from the source content rather than hand-kept: a
    # camel-cased token that appears in profile.yaml was written deliberately,
    # and anything else in the PDF is an extraction artefact.
    merged = [w for w in re.findall(r"\b[A-Za-z]{6,}\b", text)
              if re.search(r"[a-z][A-Z]", w) and w not in _intentional_camel()]
    if merged:
        fails.append(f"words fused on extraction: {sorted(set(merged))[:6]}")

    # -- structure ---------------------------------------------------------
    # Headings render in small caps of mixed-case text, so extraction returns
    # "Professional Experience", not "PROFESSIONAL EXPERIENCE". Match either.
    found = [s for s in ORDER if re.search(rf"^{s}$", text, re.M | re.I)]
    if "PROFESSIONAL EXPERIENCE" not in found:
        fails.append("no PROFESSIONAL EXPERIENCE heading")
    if found != [s for s in ORDER if s in found]:
        fails.append(f"sections out of house order: {found}")

    # -- bullets per role --------------------------------------------------
    lines = text.split("\n")
    upper = [l.strip().upper() for l in lines]
    try:
        start = upper.index("PROFESSIONAL EXPERIENCE")
        end = next((i for i in range(start + 1, len(lines))
                    if upper[i] in SECTIONS), len(lines))
    except ValueError:
        start = end = 0
    roles, counts = [], []
    for ln in lines[start + 1:end]:
        if ln.strip().startswith("•"):
            if counts:
                counts[-1] += 1
        elif ln.strip() and not ln.startswith(" "):
            if re.search(r"\b(19|20)\d{2}\b|Present", ln):
                roles.append(ln.strip()[:40])
                counts.append(0)
    for role, n in zip(roles, counts):
        if n and n < 3:
            fails.append(f"only {n} bullet(s) under {role!r}, house style needs 3 to 5")
        if n > 5:
            fails.append(f"{n} bullets under {role!r}, house style caps at 5")

    # -- skills categorised ------------------------------------------------
    # Reference layout: bold-label lines ("Languages: JavaScript, ..."), each
    # one a category. Every line must carry a category colon.
    try:
        s0 = upper.index("TECHNICAL SKILLS") if "TECHNICAL SKILLS" in upper \
            else upper.index("SKILLS")
        s1 = next(i for i in range(s0 + 1, len(lines)) if upper[i] in SECTIONS)
        skill_lines = [l.strip() for l in lines[s0 + 1:s1] if l.strip()]
        if not skill_lines:
            fails.append("TECHNICAL SKILLS is empty")
        elif sum(":" in l for l in skill_lines) < len(skill_lines) * 0.6:
            fails.append("TECHNICAL SKILLS has uncategorised lines")
    except (ValueError, StopIteration):
        fails.append("no TECHNICAL SKILLS section")

    # -- summary length ----------------------------------------------------
    # Two lines read as thin on a senior resume; four is the ceiling before the
    # summary starts eating the space the experience needs. Anything in the
    # three-to-four range is house style now.
    try:
        u0 = upper.index("SUMMARY")
        u1 = next(i for i in range(u0 + 1, len(lines)) if upper[i] in SECTIONS)
        n = len([l for l in lines[u0 + 1:u1] if l.strip()])
        if n > 4:
            fails.append(f"SUMMARY runs to {n} lines, house style is at most 4")
    except (ValueError, StopIteration):
        pass

    return fails


def page_count(pdf: Path) -> int:
    import pdfplumber

    with pdfplumber.open(pdf) as doc:
        return len(doc.pages)
