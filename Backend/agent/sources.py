"""
Company and job discovery from free, public sources.

Every endpoint below is either an official public JSON API or a community
mirror. Nothing here needs a key, a paid plan, or scraping a site that forbids
it — LinkedIn and Indeed are deliberately absent because they block automation.

Verified working (probed 2026-08):
  YC             https://yc-oss.github.io/api/companies/all.json    6,129 companies
  HN hiring      http://hn.algolia.com/api/v1/...                   ~200 posts/month
  Greenhouse     https://boards-api.greenhouse.io/v1/boards/{t}/jobs?content=true
  Lever          https://api.lever.co/v0/postings/{t}?mode=json
  Ashby          https://api.ashbyhq.com/posting-api/job-board/{t}
  SmartRecruiters https://api.smartrecruiters.com/v1/companies/{t}/postings
  Workable       https://apply.workable.com/api/v3/accounts/{t}/jobs
  Recruitee      https://{t}.recruitee.com/api/offers/
  Arbeitnow (EU) https://www.arbeitnow.com/api/job-board-api
  Remotive       https://remotive.com/api/remote-jobs
  RemoteOK       https://remoteok.com/api
  Himalayas      https://himalayas.app/jobs/api
"""

from __future__ import annotations

import hashlib
import html
import re
import time
from datetime import datetime, timezone
from typing import Any, Callable, Iterable
from urllib.parse import urljoin, urlparse

import requests

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html;q=0.9,*/*;q=0.8",
}
TIMEOUT = 25

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]{2,}")
URL_RE = re.compile(r"https?://[^\s\"'<>)\]]+")

EU_HINTS = {
    "united kingdom", "uk", "england", "scotland", "ireland", "germany", "berlin",
    "munich", "france", "paris", "spain", "madrid", "barcelona", "netherlands",
    "amsterdam", "sweden", "stockholm", "denmark", "copenhagen", "norway", "oslo",
    "finland", "helsinki", "poland", "warsaw", "portugal", "lisbon", "italy",
    "milan", "rome", "switzerland", "zurich", "austria", "vienna", "belgium",
    "brussels", "czech", "prague", "estonia", "tallinn", "romania", "bucharest",
    "london", "dublin", "europe", "eu", "emea",
}
US_HINTS = {"united states", "usa", "us", "san francisco", "new york", "nyc", "seattle",
            "austin", "boston", "chicago", "los angeles", "denver", "california", "texas"}
PK_HINTS = {"pakistan", "karachi", "lahore", "islamabad", "rawalpindi", "peshawar", "mansehra"}


def _get(url: str, params: dict | None = None, *, as_json: bool = True,
         timeout: int = TIMEOUT) -> Any:
    resp = requests.get(url, params=params, headers=UA, timeout=timeout)
    resp.raise_for_status()
    return resp.json() if as_json else resp.text


def _safe(fn: Callable[[], Any], on_error: Any = None) -> Any:
    try:
        return fn()
    except Exception:
        return on_error


def domain_of(url: str | None) -> str:
    if not url:
        return ""
    try:
        host = urlparse(url if "//" in url else f"https://{url}").netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def classify_region(*texts: str) -> str:
    blob = " ".join(t.lower() for t in texts if t)
    if not blob:
        return "other"
    if any(h in blob for h in PK_HINTS):
        return "pk"
    if "remote" in blob and not any(h in blob for h in EU_HINTS | US_HINTS):
        return "remote"
    if any(re.search(rf"\b{re.escape(h)}\b", blob) for h in EU_HINTS):
        return "eu"
    if any(re.search(rf"\b{re.escape(h)}\b", blob) for h in US_HINTS):
        return "us"
    if "remote" in blob:
        return "remote"
    return "other"


def parse_posted_at(value: Any) -> int | None:
    """
    Normalise a posting date to a UTC unix timestamp.

    Every board reports this differently: Lever sends epoch milliseconds,
    Arbeitnow epoch seconds, Greenhouse an ISO string with an offset, Remotive
    a naive ISO string, RemoteOK an ISO string with 'Z'. Returning one integer
    makes "posted in the last N days" a comparison instead of a guess.
    """
    if value is None or value == "":
        return None

    # Numeric epochs — seconds or milliseconds.
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.strip().isdigit()):
        try:
            n = float(value)
        except (TypeError, ValueError):
            return None
        if n > 1e11:          # milliseconds
            n /= 1000.0
        if n < 946_684_800:   # before 2000-01-01, almost certainly not a date
            return None
        return int(n)

    text = str(value).strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")

    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except ValueError:
        pass

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y",
                "%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S.%f%z"):
        try:
            dt = datetime.strptime(text, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp())
        except ValueError:
            continue
    return None


def age_days(ts: int | None) -> float | None:
    if not ts:
        return None
    return max(0.0, (datetime.now(timezone.utc).timestamp() - ts) / 86400.0)


UNKNOWN_COMPANY = {"", "unknown", "n/a", "na", "confidential", "undisclosed", "private"}


def dedupe_hash(company: str, title: str, location: str = "", url: str = "") -> str:
    """
    Stable identity for a role across boards and re-posts.

    Deliberately not the URL: the same job shows up on RemoteOK and Remotive
    with different links, gets re-posted with a fresh id, and picks up tracking
    parameters. Company + title + location survives all three.

    The exception is a posting whose employer is not published (Landing.jobs
    never names one). Hashing "unknown | software engineer | europe" would make
    every anonymous listing collide, so those fall back to the URL and stay
    distinct — at the cost of not catching a genuine cross-board duplicate,
    which is the safer way to be wrong.
    """
    def norm(s: str) -> str:
        s = re.sub(r"\(.*?\)", " ", (s or "").lower())
        s = re.sub(r"\b(remote|hybrid|onsite|on-site|full[- ]time|part[- ]time|contract)\b", " ", s)
        s = re.sub(r"[^a-z0-9]+", " ", s)
        return re.sub(r"\s+", " ", s).strip()

    company_key = norm(company)
    if company_key in UNKNOWN_COMPANY and url:
        key = f"url:{re.sub(r'[?#].*$', '', url.lower().rstrip('/'))}"
    else:
        key = f"{company_key}|{norm(title)}|{norm(location)}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]


def strip_html(text: str | None) -> str:
    if not text:
        return ""
    text = re.sub(r"<br\s*/?>|</p>|</li>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"[ \t]{2,}", " ", re.sub(r"\n{3,}", "\n\n", text)).strip()


# --------------------------------------------------------------------------
# 1. Y Combinator
# --------------------------------------------------------------------------

YC_ALL = "https://yc-oss.github.io/api/companies/all.json"
YC_HIRING = "https://yc-oss.github.io/api/companies/hiring.json"


def fetch_yc(limit: int = 60, *, hiring_only: bool = True,
             regions: Iterable[str] = (), batches: Iterable[str] = (),
             mode: str = "spread", log: Callable[[str], None] = print) -> list[dict[str, Any]]:
    """
    YC companies.

    `mode` matters more than it looks:

      newest  the most recent batches first. These are 2-10 person startups —
              the founder reads their own email, but they rarely have a job
              board yet. Best for the outreach mode.
      spread  an even sample across every batch, so the set includes
              established companies that actually run Greenhouse/Lever/Ashby
              boards. Best for the apply mode, and the default.
    """
    url = YC_HIRING if hiring_only else YC_ALL
    log(f"[yc] fetching {'actively hiring' if hiring_only else 'all'} companies…")
    raw = _safe(lambda: _get(url), [])
    if not raw:
        log("[yc] source unavailable")
        return []
    log(f"[yc] {len(raw)} companies in feed")

    wanted_regions = {r.lower() for r in regions if r}
    wanted_batches = {b.lower() for b in batches if b}

    def batch_key(c: dict) -> tuple[int, int]:
        """Sort newest batch first. The feed uses 'Winter 2012' / 'Summer 2023'."""
        b = str(c.get("batch") or "")
        season_rank = {"winter": 1, "spring": 2, "summer": 3, "fall": 4, "autumn": 4,
                       "w": 1, "s": 3, "f": 4, "x": 0}
        m = re.match(r"([A-Za-z]+)\s*(\d{2,4})", b)
        if not m:
            return (0, 0)
        year = int(m.group(2))
        if year < 100:
            year += 2000
        return (year, season_rank.get(m.group(1).lower(), 0))

    raw.sort(key=batch_key, reverse=True)

    if mode == "spread" and limit and len(raw) > limit * 2:
        # Even stride across the batch-sorted list: keeps some brand-new
        # startups and some established ones in the same pass.
        stride = max(1, len(raw) // (limit * 3))
        raw = raw[::stride]

    out: list[dict[str, Any]] = []
    for c in raw:
        if wanted_batches and str(c.get("batch", "")).lower() not in wanted_batches:
            continue
        locations = ", ".join(c.get("all_locations", "").split(";")) if isinstance(
            c.get("all_locations"), str) else ""
        region = classify_region(locations, str(c.get("regions") or ""))
        if wanted_regions and region not in wanted_regions:
            continue
        website = c.get("website") or ""
        out.append({
            "name": c.get("name") or "",
            "domain": domain_of(website),
            "website": website,
            "source": "yc",
            "source_ref": c.get("batch") or "",
            "description": (c.get("one_liner") or c.get("long_description") or "")[:1200],
            "industry": c.get("industry") or "",
            "location": locations,
            "region": region,
            "team_size": str(c.get("team_size") or ""),
            "founded": str(c.get("launched_at") or ""),
            "tags": [t for t in (c.get("tags") or []) if isinstance(t, str)][:12],
            "careers_url": urljoin(website, "/careers") if website else "",
        })
        if len(out) >= limit:
            break
    log(f"[yc] selected {len(out)} companies")
    return out


# --------------------------------------------------------------------------
# 2. Hacker News "Who is hiring?"
# --------------------------------------------------------------------------

HN_SEARCH = "http://hn.algolia.com/api/v1/search_by_date"
HN_ITEM = "http://hn.algolia.com/api/v1/items/{id}"


def _latest_hiring_thread(log: Callable[[str], None]) -> dict | None:
    data = _safe(lambda: _get(HN_SEARCH, {
        "query": "Ask HN: Who is hiring?", "tags": "story", "hitsPerPage": 20}), {})
    hits = (data or {}).get("hits") or []
    for hit in hits:
        title = (hit.get("title") or "").lower()
        if "who is hiring" in title and hit.get("author") == "whoishiring":
            return hit
    for hit in hits:
        if "who is hiring" in (hit.get("title") or "").lower():
            return hit
    log("[hn] no 'Who is hiring' thread found")
    return None


def fetch_hn_hiring(limit: int = 80, *, log: Callable[[str], None] = print) -> list[dict[str, Any]]:
    """
    Parse the current monthly thread. Posts follow a loose convention:

        Company | Role | Location | REMOTE | Full-time | url | email

    Roughly a third of posts carry a direct founder or recruiter email, which
    makes this the highest-signal source for the outreach mode.
    """
    thread = _latest_hiring_thread(log)
    if not thread:
        return []
    story_id = thread.get("objectID")
    log(f"[hn] {thread.get('title')} (#{story_id})")

    item = _safe(lambda: _get(HN_ITEM.format(id=story_id), timeout=60), {})
    children = (item or {}).get("children") or []
    log(f"[hn] {len(children)} top-level posts")

    out: list[dict[str, Any]] = []
    for child in children:
        text = child.get("text") or ""
        if not text:
            continue
        plain = strip_html(text)
        first_line = next((l.strip() for l in plain.split("\n") if l.strip()), "")
        if not first_line:
            continue

        parts = [p.strip() for p in first_line.split("|") if p.strip()]
        name = parts[0] if parts else ""
        # Links get flattened into the text, so "Snout https://snout.com" is common.
        name = URL_RE.sub("", name)
        name = re.sub(r"\s*\(.*?\)\s*$", "", name)
        name = re.sub(r"^\W+|[\s\W]+$", "", name)[:90].strip()
        if not name or len(name) < 2:
            continue

        urls = [u.rstrip(".,);:") for u in URL_RE.findall(plain)]
        site = next((u for u in urls
                     if not any(d in u for d in ("news.ycombinator", "lever.co", "greenhouse.io",
                                                 "ashbyhq", "workable", "linkedin.com",
                                                 "twitter.com", "x.com"))), "")
        board = next((u for u in urls
                      if any(d in u for d in ("lever.co", "greenhouse.io", "ashbyhq",
                                              "workable", "recruitee", "smartrecruiters"))), "")
        emails = [e.lower().rstrip(".,;:)") for e in EMAIL_RE.findall(plain)]
        emails = [e for e in emails if not e.endswith((".png", ".jpg", ".svg", ".gif"))]

        location_bits = " ".join(parts[1:5]) if len(parts) > 1 else ""
        out.append({
            "name": name,
            "domain": domain_of(site),
            "website": site,
            "source": "hn",
            "source_ref": str(story_id),
            "description": plain[:1500],
            "industry": "",
            "location": location_bits[:160],
            "region": classify_region(location_bits, plain[:400]),
            "careers_url": board or site,
            "tags": [],
            "_hn": {
                "author": child.get("author"),
                "emails": emails[:4],
                "urls": urls[:6],
                "headline": first_line[:240],
                "post_id": child.get("id"),
            },
        })
        if len(out) >= limit:
            break

    with_email = sum(1 for c in out if c["_hn"]["emails"])
    log(f"[hn] parsed {len(out)} companies, {with_email} with a direct email")
    return out


# --------------------------------------------------------------------------
# 3. ATS detection + job boards
# --------------------------------------------------------------------------

ATS_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("greenhouse", re.compile(r"(?:boards|job-boards)\.greenhouse\.io/(?:embed/job_board\?for=)?([a-z0-9_-]+)", re.I)),
    ("lever", re.compile(r"jobs\.(?:eu\.)?lever\.co/([a-z0-9_-]+)", re.I)),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/([a-z0-9_.-]+)", re.I)),
    ("workable", re.compile(r"([a-z0-9_-]+)\.workable\.com", re.I)),
    ("recruitee", re.compile(r"([a-z0-9_-]+)\.recruitee\.com", re.I)),
    ("smartrecruiters", re.compile(r"careers\.smartrecruiters\.com/([A-Za-z0-9_-]+)", re.I)),
    ("personio", re.compile(r"([a-z0-9_-]+)\.jobs\.personio\.(?:de|com)", re.I)),
    ("teamtailor", re.compile(r"([a-z0-9_-]+)\.teamtailor\.com", re.I)),
]

CAREER_PATHS = ("/careers", "/jobs", "/careers/", "/join-us", "/work-with-us", "/company/careers")


def _token_candidates(website: str, name: str = "") -> list[str]:
    """Likely board slugs for a company, most probable first."""
    out: list[str] = []
    host = domain_of(website)
    if host:
        out.append(host.split(".")[0])
        out.append(re.sub(r"[^a-z0-9]", "", host.split(".")[0]))
    if name:
        low = name.lower().strip()
        out.append(re.sub(r"[^a-z0-9]", "", low))
        out.append(re.sub(r"[^a-z0-9]+", "-", low).strip("-"))
    return [t for t in dict.fromkeys(out) if t and len(t) > 2]


# Cheap existence probes, in descending order of how common the ATS is with startups.
_PROBES: list[tuple[str, str]] = [
    ("ashby", "https://api.ashbyhq.com/posting-api/job-board/{t}"),
    ("greenhouse", "https://boards-api.greenhouse.io/v1/boards/{t}/jobs"),
    ("lever", "https://api.lever.co/v0/postings/{t}?mode=json"),
]


def probe_ats(website: str, name: str = "",
              log: Callable[[str], None] = lambda _: None) -> dict[str, str]:
    """
    Ask the ATS APIs directly whether a board exists for this company.

    Plenty of startups link their board only from a page that 404s, or from a
    Notion site the crawler cannot read — but the board itself is still public.
    Six cheap requests catch most of them.
    """
    for token in _token_candidates(website, name)[:2]:
        for platform, template in _PROBES:
            try:
                resp = requests.get(template.format(t=token), headers=UA, timeout=8)
            except requests.RequestException:
                continue
            if not resp.ok:
                continue
            try:
                data = resp.json()
            except ValueError:
                continue
            count = (len(data.get("jobs", [])) if isinstance(data, dict)
                     else len(data) if isinstance(data, list) else 0)
            if count:
                log(f"[ats] {domain_of(website) or name} -> {platform}/{token} (probed, {count} roles)")
                return {"ats_platform": platform, "ats_token": token}
    return {}


def detect_ats(website: str, *, name: str = "",
               log: Callable[[str], None] = lambda _: None) -> dict[str, str]:
    """Find a company's job board: crawl the site first, then probe the APIs."""
    if not website:
        return {}
    pages: list[str] = []
    for path in ("",) + CAREER_PATHS:
        url = urljoin(website if website.endswith("/") else website + "/", path.lstrip("/"))
        html_text = _safe(lambda u=url: _get(u, as_json=False, timeout=12), "")
        if html_text:
            pages.append(html_text)
        if len(pages) >= 3:
            break
        if pages and path:
            break

    blob = "\n".join(pages)
    for platform, pattern in ATS_PATTERNS:
        m = pattern.search(blob) if blob else None
        if m:
            token = m.group(1)
            if token.lower() in ("www", "jobs", "careers", "apply", "boards"):
                continue
            log(f"[ats] {domain_of(website)} -> {platform}/{token}")
            return {"ats_platform": platform, "ats_token": token}

    return probe_ats(website, name, log)


def fetch_ats_jobs(platform: str, token: str, *,
                   log: Callable[[str], None] = lambda _: None) -> list[dict[str, Any]]:
    """Normalised job list from a company's public board."""
    if not platform or not token:
        return []
    try:
        fetcher = {
            "greenhouse": _jobs_greenhouse,
            "lever": _jobs_lever,
            "ashby": _jobs_ashby,
            "smartrecruiters": _jobs_smartrecruiters,
            "workable": _jobs_workable,
            "recruitee": _jobs_recruitee,
        }.get(platform)
        if not fetcher:
            return []
        jobs = fetcher(token)
        log(f"[ats] {platform}/{token}: {len(jobs)} open role(s)")
        return jobs
    except Exception as exc:
        log(f"[ats] {platform}/{token} failed: {type(exc).__name__}")
        return []


def _jobs_greenhouse(token: str) -> list[dict[str, Any]]:
    data = _get(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs", {"content": "true"})
    out = []
    for j in data.get("jobs", []):
        loc = (j.get("location") or {}).get("name", "")
        out.append({
            "external_id": str(j.get("id")),
            "title": j.get("title", ""),
            "location": loc,
            "remote": "remote" in loc.lower(),
            "url": j.get("absolute_url", ""),
            "apply_url": j.get("absolute_url", ""),
            "description": strip_html(j.get("content"))[:20000],
            "department": ", ".join(d.get("name", "") for d in (j.get("departments") or [])),
            "posted_at": j.get("updated_at"),
            "source": "greenhouse",
        })
    return out


def _jobs_lever(token: str) -> list[dict[str, Any]]:
    data = _get(f"https://api.lever.co/v0/postings/{token}", {"mode": "json"})
    out = []
    for j in data:
        cats = j.get("categories") or {}
        loc = cats.get("location") or ""
        out.append({
            "external_id": j.get("id"),
            "title": j.get("text", ""),
            "location": loc,
            "remote": "remote" in f"{loc} {cats.get('commitment','')}".lower(),
            "url": j.get("hostedUrl", ""),
            "apply_url": j.get("applyUrl") or j.get("hostedUrl", ""),
            "description": (j.get("descriptionPlain") or strip_html(j.get("description")))[:20000],
            "department": cats.get("team") or cats.get("department") or "",
            "employment_type": cats.get("commitment") or "",
            "posted_at": j.get("createdAt"),
            "source": "lever",
        })
    return out


def _jobs_ashby(token: str) -> list[dict[str, Any]]:
    data = _get(f"https://api.ashbyhq.com/posting-api/job-board/{token}",
                {"includeCompensation": "false"})
    out = []
    for j in data.get("jobs", []):
        if j.get("isListed") is False:
            continue
        out.append({
            "external_id": j.get("id"),
            "title": j.get("title", ""),
            "location": j.get("location") or "",
            "remote": bool(j.get("isRemote")),
            "url": j.get("jobUrl") or j.get("applyUrl") or "",
            "apply_url": j.get("applyUrl") or j.get("jobUrl") or "",
            "description": strip_html(j.get("descriptionHtml") or j.get("descriptionPlain"))[:20000],
            "department": j.get("department") or j.get("team") or "",
            "employment_type": j.get("employmentType") or "",
            "posted_at": j.get("publishedAt"),
            "source": "ashby",
        })
    return out


def _jobs_smartrecruiters(token: str) -> list[dict[str, Any]]:
    data = _get(f"https://api.smartrecruiters.com/v1/companies/{token}/postings", {"limit": 100})
    out = []
    for j in data.get("content", []):
        loc = j.get("location") or {}
        city = ", ".join(x for x in [loc.get("city"), loc.get("country")] if x)
        pid = j.get("id")
        out.append({
            "external_id": pid,
            "title": j.get("name", ""),
            "location": city,
            "remote": bool(loc.get("remote")),
            "url": f"https://jobs.smartrecruiters.com/{token}/{pid}",
            "apply_url": f"https://jobs.smartrecruiters.com/{token}/{pid}",
            "description": "",
            "department": (j.get("department") or {}).get("label", ""),
            "employment_type": (j.get("typeOfEmployment") or {}).get("label", ""),
            "posted_at": j.get("releasedDate"),
            "source": "smartrecruiters",
        })
    return out


def _jobs_workable(token: str) -> list[dict[str, Any]]:
    data = _get(f"https://apply.workable.com/api/v3/accounts/{token}/jobs")
    out = []
    for j in data.get("results", []):
        loc = j.get("location") or {}
        city = ", ".join(x for x in [loc.get("city"), loc.get("country")] if x)
        shortcode = j.get("shortcode")
        out.append({
            "external_id": shortcode,
            "title": j.get("title", ""),
            "location": city,
            "remote": bool(j.get("remote")),
            "url": f"https://apply.workable.com/{token}/j/{shortcode}/",
            "apply_url": f"https://apply.workable.com/{token}/j/{shortcode}/apply/",
            "description": strip_html(j.get("description"))[:20000],
            "department": j.get("department") or "",
            "employment_type": j.get("employment_type") or "",
            "posted_at": j.get("published_on"),
            "source": "workable",
        })
    return out


def _jobs_recruitee(token: str) -> list[dict[str, Any]]:
    data = _get(f"https://{token}.recruitee.com/api/offers/")
    out = []
    for j in data.get("offers", []):
        out.append({
            "external_id": str(j.get("id")),
            "title": j.get("title", ""),
            "location": j.get("location") or "",
            "remote": bool(j.get("remote")),
            "url": j.get("careers_url") or j.get("url") or "",
            "apply_url": j.get("careers_apply_url") or j.get("careers_url") or "",
            "description": strip_html(j.get("description"))[:20000],
            "department": j.get("department") or "",
            "employment_type": j.get("employment_type_code") or "",
            "posted_at": j.get("published_at"),
            "source": "recruitee",
        })
    return out


# --------------------------------------------------------------------------
# 4. Remote / European job boards
# --------------------------------------------------------------------------

def _section(results: list[Any], label: str, prefix: str, log: Callable[[str], None]):
    """
    Run one board isolated.

    A board changing its response shape must not take the rest of the sweep with
    it — Landing.jobs turning `locations` into a list of dicts once aborted an
    entire run. The guard swallows the exception, reports it, and moves on.
    """
    class _Guard:
        def __enter__(self):
            self.before = len(results)
            return self

        def __exit__(self, exc_type, exc, tb):
            if exc_type:
                log(f"[{prefix}] {label} failed ({exc_type.__name__}: {str(exc)[:70]}) — skipped")
            else:
                log(f"[{prefix}] {label} -> {len(results) - self.before}")
            return True          # swallow, keep going

    return _Guard()


def fetch_remote_boards(limit: int = 120, *, keywords: Iterable[str] = (),
                        log: Callable[[str], None] = print) -> list[dict[str, Any]]:
    """
    Returns company+job pairs from open job APIs. Each entry has a `_job` key
    holding the posting so the caller can store both in one pass.
    """
    wanted = [k.lower() for k in keywords if k]
    results: list[dict[str, Any]] = []

    def matches(title: str, tags: str) -> bool:
        if not wanted:
            return True
        blob = f"{title} {tags}".lower()
        return any(k in blob for k in wanted)

    def section(label: str):
        return _section(results, label, "remote", log)

    # -- Arbeitnow (Europe-heavy)
    with section("arbeitnow"):
        data = _safe(lambda: _get("https://www.arbeitnow.com/api/job-board-api"), {})
        for j in (data or {}).get("data", [])[: limit * 2]:
            tags = " ".join(j.get("tags") or [])
            if not matches(j.get("title", ""), tags):
                continue
            results.append(_board_entry(
                name=j.get("company_name", ""), source="arbeitnow",
                location=j.get("location", ""), remote=bool(j.get("remote")),
                title=j.get("title", ""), url=j.get("url", ""),
                description=strip_html(j.get("description")), tags=j.get("tags") or [],
                posted_at=str(j.get("created_at") or "")))

    # -- Remotive
    with section("remotive"):
        data = _safe(lambda: _get("https://remotive.com/api/remote-jobs", {"limit": 200}), {})
        for j in (data or {}).get("jobs", []):
            tags = " ".join(j.get("tags") or [])
            if not matches(j.get("title", ""), tags):
                continue
            results.append(_board_entry(
                name=j.get("company_name", ""), source="remotive",
                location=j.get("candidate_required_location", "Remote"), remote=True,
                title=j.get("title", ""), url=j.get("url", ""),
                description=strip_html(j.get("description")), tags=j.get("tags") or [],
                posted_at=j.get("publication_date")))

    # -- RemoteOK (index 0 is a legal notice, not a job)
    with section("remoteok"):
        data = _safe(lambda: _get("https://remoteok.com/api"), [])
        for j in (data or [])[1:]:
            if not isinstance(j, dict):
                continue
            tags = " ".join(j.get("tags") or [])
            if not matches(j.get("position", ""), tags):
                continue
            results.append(_board_entry(
                name=j.get("company", ""), source="remoteok",
                location=j.get("location") or "Remote", remote=True,
                title=j.get("position", ""), url=j.get("url", ""),
                description=strip_html(j.get("description")), tags=j.get("tags") or [],
                posted_at=j.get("date")))

    # -- Himalayas
    with section("himalayas"):
        data = _safe(lambda: _get("https://himalayas.app/jobs/api", {"limit": 100}), {})
        for j in (data or {}).get("jobs", []):
            if not matches(j.get("title", ""), " ".join(j.get("categories") or [])):
                continue
            results.append(_board_entry(
                name=j.get("companyName", ""), source="himalayas",
                location=", ".join(j.get("locationRestrictions") or []) or "Remote", remote=True,
                title=j.get("title", ""), url=j.get("applicationLink") or j.get("guid") or "",
                description=strip_html(j.get("description") or j.get("excerpt")),
                tags=j.get("categories") or [], posted_at=str(j.get("pubDate") or "")))

    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for entry in results:
        url = entry["_job"]["url"]
        if not url or url in seen:
            continue
        seen.add(url)
        deduped.append(entry)
        if len(deduped) >= limit:
            break
    log(f"[remote] {len(deduped)} unique postings after de-duplication")
    return deduped


def fetch_hidden_boards(limit: int = 150, *, keywords: Iterable[str] = (),
                        log: Callable[[str], None] = print) -> list[dict[str, Any]]:
    """
    Smaller boards that the big aggregators do not syndicate.

    These matter because competition scales with reach. A role on LinkedIn
    collects hundreds of applicants; the same role on Jobicy or Working Nomads
    collects a handful. All free, none need a key.

      The Muse          public API, exposes an explicit experience level
      Jobicy            remote board, exposes jobLevel
      Working Nomads    curated remote board
      WeWorkRemotely    RSS, one of the oldest remote boards
      Jobspresso        RSS, curated and moderated
      Landing.jobs      European tech, salary ranges published
    """
    wanted = [k.lower() for k in keywords if k]
    results: list[dict[str, Any]] = []

    def matches(*parts: str) -> bool:
        if not wanted:
            return True
        blob = " ".join(p or "" for p in parts).lower()
        return any(k in blob for k in wanted)

    def section(label: str):
        return _section(results, label, "hidden", log)

    # -- The Muse: filterable by level, which is exactly what we want.
    with section("themuse"):
     for level in ("Entry Level", "Mid Level"):
        for page in (1, 2):
            data = _safe(lambda l=level, p=page: _get(
                "https://www.themuse.com/api/public/jobs",
                {"category": "Software Engineering", "level": l, "page": p}), {})
            for j in (data or {}).get("results", []):
                title = j.get("name", "")
                company = (j.get("company") or {}).get("name", "")
                if not matches(title, j.get("contents", "")[:400]):
                    continue
                locs = [l.get("name", "") for l in (j.get("locations") or [])]
                results.append(_board_entry(
                    name=company, source="themuse",
                    location=", ".join(locs[:2]) or "Unspecified",
                    remote=any("flexible" in l.lower() or "remote" in l.lower() for l in locs),
                    title=title, url=(j.get("refs") or {}).get("landing_page", ""),
                    description=strip_html(j.get("contents")), tags=[
                        n.get("name", "") for n in (j.get("categories") or [])],
                    posted_at=j.get("publication_date"),
                    level=", ".join(l.get("name", "") for l in (j.get("levels") or []))))

    # -- Jobicy
    with section("jobicy"):
     data = _safe(lambda: _get("https://jobicy.com/api/v2/remote-jobs", {"count": 50}), {})
    for j in (data or {}).get("jobs", []):
        if not matches(j.get("jobTitle"), " ".join(j.get("jobIndustry") or [])):
            continue
        results.append(_board_entry(
            name=j.get("companyName", ""), source="jobicy",
            location=", ".join(j.get("jobGeo", "").split(",")[:2]) or "Remote", remote=True,
            title=j.get("jobTitle", ""), url=j.get("url", ""),
            description=strip_html(j.get("jobDescription") or j.get("jobExcerpt")),
            tags=j.get("jobIndustry") or [], posted_at=j.get("pubDate"),
            level=j.get("jobLevel") or ""))

    # -- Working Nomads
    with section("workingnomads"):
     data = _safe(lambda: _get("https://www.workingnomads.com/api/exposed_jobs/"), [])
    for j in (data or []):
        if not isinstance(j, dict) or not matches(j.get("title"), j.get("tags") or ""):
            continue
        results.append(_board_entry(
            name=j.get("company_name", ""), source="workingnomads",
            location=j.get("location") or "Remote", remote=True,
            title=j.get("title", ""), url=j.get("url", ""),
            description=strip_html(j.get("description")),
            tags=[t.strip() for t in (j.get("tags") or "").split(",") if t.strip()][:8],
            posted_at=j.get("pub_date")))

    # -- RSS boards
    for label, feed in (("weworkremotely",
                         "https://weworkremotely.com/categories/remote-programming-jobs.rss"),
                        ("jobspresso", "https://jobspresso.co/?feed=job_feed")):
        for item in _rss_items(feed):
            title = item["title"]
            company = ""
            # WWR writes "Company: Role"; Jobspresso puts the company in a field.
            if ":" in title and label == "weworkremotely":
                company, _, title = title.partition(":")
            if not matches(title, item["description"][:400]):
                continue
            results.append(_board_entry(
                name=(company or item.get("company") or "Unknown").strip(),
                source=label, location=item.get("region") or "Remote", remote=True,
                title=title.strip(), url=item["link"],
                description=strip_html(item["description"]),
                tags=[item.get("category", "")] if item.get("category") else [],
                posted_at=item.get("pubDate")))

    # -- Landing.jobs (Europe)
    with section("landingjobs"):
     data = _safe(lambda: _get("https://landing.jobs/api/v1/jobs", {"limit": 50}), [])
    for j in (data or []):
        if not isinstance(j, dict) or not matches(j.get("title"), j.get("role_description")):
            continue
        # Landing.jobs never publishes the employer, so the listing itself is the
        # identity. The URL keeps each one distinct in the dedupe hash.
        results.append(_board_entry(
            name=(j.get("company") or {}).get("name") if isinstance(j.get("company"), dict)
            else (j.get("company_name") or f"Landing.jobs listing #{j.get('id')}"),
            source="landingjobs",
            location=_join_locations(j.get("locations"))[:80] or "Europe",
            remote=bool(j.get("remote")),
            title=j.get("title", ""),
            url=j.get("url") or f"https://landing.jobs/jobs/{j.get('id')}",
            description=strip_html(f"{j.get('role_description','')}\n\n"
                                   f"{j.get('main_requirements','')}"),
            tags=[], posted_at=j.get("published_at")))

    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for entry in results:
        url = entry["_job"]["url"]
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(entry)
        if len(out) >= limit:
            break
    log(f"[hidden] {len(out)} unique postings from low-competition boards")
    return out


def _join_locations(value: Any) -> str:
    """Boards return locations as strings, as {"name": ...} dicts, or as one string."""
    if not value:
        return ""
    if isinstance(value, str):
        return value
    parts: list[str] = []
    for item in value:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict):
            parts.append(str(item.get("name") or item.get("city") or item.get("title") or ""))
    return ", ".join(p for p in parts if p)


def _rss_items(url: str) -> list[dict[str, str]]:
    """Minimal RSS reader — these feeds are plain RSS 2.0."""
    import xml.etree.ElementTree as ET

    text = _safe(lambda: _get(url, as_json=False, timeout=25), "")
    if not text:
        return []
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    out: list[dict[str, str]] = []
    for item in root.findall(".//item"):
        def field(tag: str) -> str:
            el = item.find(tag)
            return (el.text or "").strip() if el is not None and el.text else ""

        out.append({
            "title": field("title"), "link": field("link"),
            "description": field("description"), "pubDate": field("pubDate"),
            "region": field("region"), "category": field("category"),
            "company": field("company"),
        })
    return out


def _board_entry(*, name: str, source: str, location: str, remote: bool, title: str,
                 url: str, description: str, tags: list, posted_at: str | None,
                 level: str = "") -> dict[str, Any]:
    return {
        "name": name or "Unknown",
        "domain": domain_of(url),
        "website": "",
        "source": "directory",
        "source_ref": source,
        "description": description[:1200],
        "industry": "",
        "location": location,
        "region": classify_region(location),
        "careers_url": url,
        "tags": [t for t in tags if isinstance(t, str)][:10],
        "_job": {
            "title": title,
            "location": location,
            "remote": remote,
            "url": url,
            "apply_url": url,
            "description": description[:20000],
            "source": source,
            "posted_at": posted_at,
            # Some boards state seniority outright; that beats guessing from the
            # title or scraping a number out of the description.
            "level": level,
        },
    }


# --------------------------------------------------------------------------
# Company site crawl (used by the people finder)
# --------------------------------------------------------------------------

TEAM_PATHS = ("/about", "/team", "/about-us", "/company", "/people", "/founders",
              "/contact", "/contact-us")


def crawl_company_pages(website: str, *, max_pages: int = 5,
                        log: Callable[[str], None] = lambda _: None) -> dict[str, str]:
    """Fetch the homepage plus likely team/contact pages. Returns {url: html}."""
    if not website:
        return {}
    base = website if website.endswith("/") else website + "/"
    pages: dict[str, str] = {}
    for path in ("",) + TEAM_PATHS:
        if len(pages) >= max_pages:
            break
        url = urljoin(base, path.lstrip("/"))
        text = _safe(lambda u=url: _get(u, as_json=False, timeout=12), "")
        if text and len(text) > 200:
            pages[url] = text
        time.sleep(0.2)
    if pages:
        log(f"[crawl] {domain_of(website)}: {len(pages)} page(s)")
    return pages
