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
            "personio.de", "join.com", "teamtailor.com")

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

    html = sources._safe(
        lambda: sources._get(url, as_json=False), on_error="") or ""
    fetched = _from_html(html) if isinstance(html, str) else ""
    if len(fetched) >= MIN_USEFUL:
        return fetched, "fetched"

    if any(host in url for host in JS_HOSTS):
        rendered = _render(url)
        if len(rendered) >= MIN_USEFUL:
            log(f"[jd] rendered {url[:70]}")
            return rendered, "rendered"

    best = max((existing, fetched), key=len)
    if not best:
        return "", "unavailable"
    # Short but real — better than nothing, and the caller can see it is thin.
    return best, "fetched" if best is fetched else "api"
