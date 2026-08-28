"""
Fetch the full text of a job posting from its listing page.

Boards vary in what they hand back. Greenhouse and Lever return the whole
description in their API; Remotive and Arbeitnow return it as HTML; The Muse and
Jobicy return a summary; RSS feeds often return two sentences. Tailoring a
resume against a two-sentence teaser produces a worse document than not
tailoring at all, so anything short gets fetched from the source page.

Order of attempts, cheapest first:

  1. What the source already gave us, if it is long enough to be the real thing.
  2. A plain HTTP GET, with the boilerplate stripped out.
  3. Playwright, only for hosts that render the description client-side.

Never raises. Returns (text, source) where source is one of `api`, `fetched`,
`rendered` or `unavailable`, and the caller records which.
"""

from __future__ import annotations

import re
from typing import Any, Callable

from . import sources

# Below this a "description" is a teaser, not a posting.
MIN_USEFUL = 400

# Hosts whose posting body is injected by JavaScript, so a plain GET returns an
# empty shell. Confirmed by fetching each one and finding no description text.
JS_HOSTS = ("ashbyhq.com", "jobs.ashbyhq.com", "workable.com", "recruitee.com",
            "personio.de", "join.com", "teamtailor.com",
            # Greenhouse's newer job-boards host renders the posting client
            # side. A plain GET returns the board's *list* page, which is long
            # enough to pass the length check, so a pasted link was storing the
            # company blurb and a neighbouring vacancy's title as the job.
            "job-boards.greenhouse.io", "job-boards.eu.greenhouse.io",
            "myworkdayjobs.com")

# Text that means "this is a board index", not "this is one posting". Length
# alone cannot tell them apart: a list page is easily longer than a short JD.
LOOKS_LIKE_A_BOARD = re.compile(
    r"\b(current openings|all openings|open (?:roles|positions)|"
    r"view all jobs|jobs at\b|browse (?:roles|jobs)|no openings)\b", re.I)

# The posting existed and does not any more. Worth telling apart from "could
# not read the page": one means try again, the other means do not bother.
CLOSED_POSTING = re.compile(
    r"(no longer (?:open|available|accepting)|this (?:job|position|role) (?:is )?"
    r"(?:has been )?(?:closed|filled|expired)|position has been filled|"
    r"applications are closed|we are no longer accepting)", re.I)


def is_closed(text: str) -> bool:
    return bool(CLOSED_POSTING.search((text or "")[:800]))

# Chrome and page furniture that survives tag stripping and would otherwise be
# fed to the tailor as if it were requirements.
BOILERPLATE = re.compile(
    r"^(cookie|we use cookies|accept all|privacy policy|terms of service|"
    r"skip to (?:main )?content|back to jobs|all jobs|share this job|apply now|"
    r"sign in|log in|log out|sign up|create an account|powered by|©|copyright|"
    r"dark mode|light mode|menu|home|about us?|contact us?|faq|blog|pricing|"
    r"post a job|hire|for employers|newsletter|subscribe|follow us|"
    r"remote jobs?|frontpage|search|filter|sort by|view all|show more|"
    r"join .{0,24}$|\d+ jobs?$)",
    re.I,
)

# Where the real content lives, most specific first.
CONTENT_HINTS = (
    "content", "description", "job-description", "posting", "job-post",
    "opening", "details", "body", "main",
)


def _clean(text: str) -> str:
    """Drop nav, cookie banners and blank runs; keep the prose."""
    lines: list[str] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or BOILERPLATE.match(line):
            continue
        # A line of pure punctuation or a lone nav word carries nothing.
        if len(line) < 3 and not line[:1].isalnum():
            continue
        lines.append(line)

    out: list[str] = []
    for line in lines:                      # collapse repeated headers/footers
        if not out or line != out[-1]:
            out.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def _prose_ratio(text: str) -> float:
    """
    Share of lines long enough to be sentences rather than nav links.

    This is what separates a job description from a sidebar. "Dark mode",
    "Log in" and "Remote jobs" are all short lines; requirements and
    responsibilities are not. Picking the *longest* block gets this wrong on
    aggregators, whose chrome is bigger than the posting.
    """
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return 0.0
    return sum(1 for l in lines if len(l) >= 55) / len(lines)


def _score(text: str) -> float:
    """Length, discounted hard when the block reads like navigation."""
    ratio = _prose_ratio(text)
    if len(text) < 200 or ratio < 0.25:
        return 0.0
    return len(text) * ratio


def _from_html(html: str) -> str:
    """
    Pull the posting body out of a page.

    Tries the containers boards actually use, scoring each by prose density,
    before falling back to the whole document — a whole-page strip drags in the
    header, the footer and every other job in the sidebar.
    """
    if not html:
        return ""
    body = re.sub(r"(?is)<(script|style|nav|header|footer|svg|noscript|form|aside)[^>]*>.*?</\1>",
                  " ", html)

    best, best_score = "", 0.0
    for hint in CONTENT_HINTS:
        pattern = (rf'(?is)<(div|section|article|main)[^>]*'
                   rf'(?:class|id)="[^"]*{re.escape(hint)}[^"]*"[^>]*>(.*?)</\1>')
        for match in re.finditer(pattern, body):
            text = _clean(sources.strip_html(match.group(2)))
            score = _score(text)
            if score > best_score:
                best, best_score = text, score

    whole = _clean(sources.strip_html(body))
    if _score(whole) > best_score:
        best = whole
    return best


def _render(url: str, *, timeout_ms: int = 25000) -> str:
    """Last resort: run the page in a browser and read the DOM."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return ""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=sources.UA.get("User-Agent", ""))
            page.set_default_timeout(timeout_ms)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                page.wait_for_timeout(2500)
                return _from_html(page.content())
            finally:
                browser.close()
    except Exception:
        return ""


def needs_fetch(job: dict[str, Any]) -> bool:
    return len(sources.strip_html(job.get("description") or "")) < MIN_USEFUL


def fetch_description(job: dict[str, Any], *,
                      log: Callable[[str], None] = print) -> tuple[str, str]:
    """
    Best available description for this job, and where it came from.

    The existing text wins when it is already substantial — re-fetching a
    Greenhouse posting the API returned in full is a wasted round trip.
    """
    existing = _clean(sources.strip_html(job.get("description") or ""))
    if len(existing) >= MIN_USEFUL:
        return existing, "api"

    url = job.get("url") or job.get("apply_url") or ""
    if not url:
        return existing, "unavailable" if not existing else "api"

    # Fast direct endpoint for LinkedIn postings
    if "linkedin.com/jobs" in url:
        m = re.search(r"(\d{9,12})", url)
        if m:
            job_id = m.group(1)
            api_url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
            l_html = sources._safe(lambda: sources._get(api_url, as_json=False, timeout=12), on_error="")
            if l_html:
                try:
                    from bs4 import BeautifulSoup
                    dsoup = BeautifulSoup(l_html, "html.parser")
                    desc_el = dsoup.find("div", class_="show-more-less-html__markup")
                    if desc_el:
                        l_text = _clean(desc_el.get_text(separator="\n", strip=True))
                        if len(l_text) >= MIN_USEFUL:
                            return l_text, "fetched"
                except Exception:
                    pass

    html = sources._safe(
        lambda: sources._get(url, as_json=False), on_error="") or ""
    fetched = _from_html(html) if isinstance(html, str) else ""

    # Long enough is not the same as right. Greenhouse's job-boards host answers
    # a plain GET with the board's *index*, which sails past the length check —
    # so a pasted link stored the company blurb and a neighbouring vacancy's
    # title as the job. Anything that reads as an index goes to the renderer
    # however long it is.
    looks_wrong = bool(LOOKS_LIKE_A_BOARD.search(fetched[:600]))
    if len(fetched) >= MIN_USEFUL and not looks_wrong:
        return fetched, "fetched"

    if looks_wrong or any(host in url for host in JS_HOSTS):
        rendered = _render(url)
        if is_closed(rendered):
            log(f"[jd] the posting at {url[:60]} is closed")
            return "", "closed"
        if len(rendered) >= MIN_USEFUL and not LOOKS_LIKE_A_BOARD.search(rendered[:600]):
            log(f"[jd] rendered {url[:70]}")
            return rendered, "rendered"

    if len(fetched) >= MIN_USEFUL:
        return fetched, "fetched"

    best = max((existing, fetched), key=len)
    if not best:
        return "", "unavailable"
    # Short but real — better than nothing, and the caller can see it is thin.
    return best, "fetched" if best is fetched else "api"


# Words that mean the line is page furniture, not a job title.
_NOT_A_TITLE = re.compile(
    r"^(apply|back to|share|home|careers?|jobs?|about|menu|search|sign in|log in|"
    r"cookie|privacy|we are hiring|open (roles|positions))\b", re.I)

_TITLE_SHAPE = re.compile(
    r"\b(engineer|developer|designer|scientist|architect|analyst|manager|lead|"
    r"programmer|consultant|specialist|intern)\b", re.I)


def guess_title(text: str, url: str = "") -> str:
    """
    The role's title, read out of the description text or failing that the URL.

    Only used for a job the user pasted a link to: everything discovered from a
    board arrives with its title already attached. The first line that looks
    like a job title wins, and "looks like" means it names a role — otherwise
    the heading of a careers page ends up as the job title.
    """
    for line in (text or "").split("\n")[:40]:
        line = line.strip(" \t·|-—–")
        if not (6 <= len(line) <= 90) or _NOT_A_TITLE.match(line):
            continue
        if _TITLE_SHAPE.search(line):
            return re.sub(r"\s{2,}", " ", line)

    # The slug in an ATS URL is usually the title: /jobs/senior-backend-engineer
    for chunk in reversed([c for c in (url or "").split("/") if c]):
        if "-" in chunk and not chunk.isdigit():
            words = [w for w in re.split(r"[-_]", chunk) if w and not w.isdigit()]
            if len(words) >= 2:
                candidate = " ".join(words).title()
                if _TITLE_SHAPE.search(candidate):
                    return candidate
    return ""


_H1 = re.compile(r"<h1[^>]*>(.*?)</h1>", re.I | re.S)
_TITLE_TAG = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
# "Full Stack Developer at ecosio", "Backend Engineer | Acme", "Role - Careers"
_TITLE_SUFFIX = re.compile(r"\s*[|\u2013\u2014-]\s*[^|]{1,40}$|\s+at\s+[\w .&-]{1,40}$", re.I)


def fetch_page_title(url: str) -> str:
    """
    The role's title read from the page's own <h1> or <title>.

    Preferred over scanning the extracted body text, which on a real Greenhouse
    board picked the heading of an unrelated vacancy listed further down the
    page — the pasted link said Full Stack Developer and the row came out as
    "E-invoicing & EDI Integration Engineer".
    """
    html_text = sources._safe(lambda: sources._get(url, as_json=False, timeout=15), "") or ""
    if not isinstance(html_text, str):
        return ""

    for pattern in (_H1, _TITLE_TAG):
        hit = pattern.search(html_text)
        if not hit:
            continue
        text = sources.strip_html(hit.group(1))
        text = re.sub(r"\s+", " ", text).strip()
        if pattern is _TITLE_TAG:
            text = _TITLE_SUFFIX.sub("", text).strip()
        if 4 <= len(text) <= 120 and not _NOT_A_TITLE.match(text):
            return text
    return ""
