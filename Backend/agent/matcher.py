"""
Decide whether a job is worth applying to.

Reuses the ATS engine from `api/ats.py` so a job's fit score is computed the
same way the Resume Tailor scores keyword coverage — one scoring model across
the whole product rather than two that drift apart.

Score (0-100):
    title match      30   does the role title match what you asked for
    keyword coverage 45   weighted JD terms your resume already evidences
    location fit     15   region and remote preferences
    seniority fit    10   penalises roles clearly above or below your level
"""

from __future__ import annotations

import re
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from api.ats import analyze_jd, match_keywords
from api.config import BASE_DIR
from api.resume_parse import parse_resume

from . import experience, jobmeta, store

SENIOR_MARKERS = ("staff", "principal", "director", "vp", "head of", "chief", "distinguished",
                  "lead engineer", "engineering manager", "architect")
JUNIOR_MARKERS = ("intern", "internship", "graduate", "trainee", "apprentice", "working student")


@lru_cache(maxsize=4)
def _resume_text(path_str: str) -> str:
    path = Path(path_str)
    if not path.is_file():
        return ""
    try:
        return parse_resume(path).raw_text
    except Exception:
        return ""


def resume_path() -> Path | None:
    """
    The résumé the agent uploads to application forms.

    Order: the profile's `default_resume` (resolved against Backend/ or cv_data/),
    then the newest generated resume in cv_data/, then anything at Backend root.
    cv_data/ comes first because `tools/build_resumes.py` writes the current
    master resumes there.
    """
    profile = store.get_setting("profile", {}) or {}
    configured = (profile.get("default_resume") or "").strip()
    if configured:
        for base in (Path(configured), BASE_DIR / configured, BASE_DIR / "cv_data" / configured):
            if base.is_file():
                return base

    pool: list[Path] = []
    for folder in (BASE_DIR / "cv_data", BASE_DIR):
        pool += list(folder.glob("*.pdf")) + list(folder.glob("*.docx"))
        if pool:
            break
    pool = [p for p in pool if not p.name.startswith("~$")]
    if not pool:
        return None
    return max(pool, key=lambda p: p.stat().st_mtime)


def resume_text() -> str:
    path = resume_path()
    return _resume_text(str(path)) if path else ""


GENERIC_TITLE_WORDS = {
    "engineer", "developer", "specialist", "designer", "architect",
    "lead", "senior", "junior", "mid", "staff", "programmer",
}

_TITLE_NOISE_RE = re.compile(
    r"\s*[\(\[\{]\s*(?:m/w/d|w/m/d|f/m/d|d/m/w|m/f/d|all genders|remote|hybrid|onsite|full[- ]time|part[- ]time|contract|permanent|direct hire|urgent)\s*[\)\]\}]|\s*-\s*(?:remote|hybrid|onsite)\b|\s*\|\s*(?:remote|hybrid)\b",
    re.I,
)

# Canonical role alias groupings
ROLE_ALIASES: dict[str, list[str]] = {
    "software engineer": [
        "software developer", "software engineer", "swe", "programmer", "developer",
        "backend engineer", "frontend engineer", "full stack engineer", "fullstack developer",
        "application developer", "node developer", "react developer", "web developer"
    ],
    "full stack engineer": [
        "full stack", "fullstack", "full-stack", "mern", "mean", "software engineer",
        "software developer", "web developer", "node developer", "react developer", "fullstack engineer"
    ],
    "backend engineer": [
        "backend", "back-end", "node developer", "node.js developer", "nodejs developer",
        "python developer", "api developer", "backend developer", "server developer", "golang developer"
    ],
    "frontend engineer": [
        "frontend", "front-end", "react developer", "react.js developer", "ui developer",
        "web developer", "javascript developer", "frontend developer", "vue developer", "angular developer"
    ],
    "react developer": [
        "react", "react.js", "reactjs", "frontend", "front-end", "full stack", "fullstack", "web developer"
    ],
    "ai engineer": [
        "ai engineer", "ai developer", "ai/ml", "machine learning engineer", "ml engineer",
        "genai", "deep learning", "nlp engineer", "ai software engineer", "data scientist"
    ],
    "ai software engineer": [
        "ai software engineer", "ai engineer", "ai developer", "ai/ml", "machine learning",
        "ml engineer", "genai", "deep learning"
    ],
    "product designer": [
        "product design", "product designer", "ui/ux designer", "ui/ux", "ux/ui",
        "ui designer", "ux designer", "user experience designer", "interaction designer"
    ],
    "ui_ux": [
        "ui/ux", "ux/ui", "product design", "product designer", "ui designer",
        "ux designer", "visual designer"
    ],
    "product_design": [
        "product design", "product designer", "ui/ux", "ui designer", "ux designer"
    ],
}

LOCATION_ALIASES: dict[str, list[str]] = {
    "united kingdom": [
        "uk", "u.k.", "united kingdom", "great britain", "gb", "england", "scotland", "wales",
        "london", "manchester", "birmingham", "edinburgh", "bristol", "leeds", "glasgow", "cambridge", "oxford"
    ],
    "germany": [
        "germany", "deutschland", "de", "berlin", "munich", "münchen", "frankfurt", "hamburg",
        "cologne", "köln", "stuttgart", "dusseldorf", "düsseldorf"
    ],
    "united arab emirates": [
        "uae", "u.a.e.", "united arab emirates", "dubai", "abu dhabi", "sharjah"
    ],
    "saudi arabia": [
        "saudi arabia", "ksa", "k.s.a.", "riyadh", "jeddah", "dammam", "khobar"
    ],
    "netherlands": [
        "netherlands", "holland", "nl", "amsterdam", "rotterdam", "utrecht", "the hague", "eindhoven"
    ],
    "ireland": [
        "ireland", "ie", "dublin", "cork", "galway", "limerick"
    ],
    "pakistan": [
        "pakistan", "pk", "islamabad", "lahore", "karachi", "rawalpindi", "peshawar", "faisalabad"
    ],
    "europe": [
        "europe", "eu", "emea"
    ],
    "remote": [
        "remote", "worldwide", "anywhere", "global", "work from home", "wfh", "virtual"
    ],
}


def _title_score(title: str, targeting: dict[str, Any], category: str | None = None) -> tuple[float, str]:
    raw_low = (title or "").lower()
    low = _TITLE_NOISE_RE.sub("", raw_low).strip()
    if not low:
        return 0.0, "no title"

    for bad in targeting.get("exclude_titles") or []:
        if bad and bad.lower() in raw_low:
            return 0.0, f"excluded by '{bad}'"

    wanted = [t.lower() for t in (targeting.get("titles") or []) if t]
    if not wanted:
        return 24.0, "no title filter set"

    # 1. Direct exact or substring match in cleaned title
    for want in wanted:
        if want in low or want in raw_low:
            return 30.0, f"title matches '{want}'"

    # 2. Canonical alias match (e.g. "node developer" matches "backend engineer" or "react developer" matches "frontend engineer")
    for want in wanted:
        aliases = ROLE_ALIASES.get(want, [])
        for alias in aliases:
            if alias in low or alias in raw_low:
                return 28.5, f"title matches role alias '{alias}'"

    # 3. Target keywords in title (e.g. 'node', 'react', 'full stack', 'python', 'typescript', 'ai')
    target_keywords = [k.lower() for k in (targeting.get("keywords") or []) if len(k) > 2]
    title_kw_hits = [k for k in target_keywords if k in low or k in raw_low]
    if title_kw_hits:
        return 27.0, f"title contains target tech ({', '.join(title_kw_hits[:2])})"

    # 4. Partial word match
    best, best_want = 0.0, ""
    for want in wanted:
        words = [w for w in re.findall(r"[a-z]+", want) if len(w) > 2]
        if not words:
            continue
        specific_words = [w for w in words if w not in GENERIC_TITLE_WORDS]
        if specific_words and not any(w in low for w in specific_words):
            continue
        hit = sum(1 for w in words if w in low) / len(words)
        if hit > best:
            best, best_want = hit, want
    if best >= 0.5:
        return round(30 * best, 1), f"partial match on '{best_want}'"

    # 5. Classified category match fallback
    if category and category in (targeting.get("categories") or []):
        return 25.0, f"matches target category '{category}'"

    return 10.0, "title loosely related"


def _location_score(job: dict[str, Any], targeting: dict[str, Any]) -> tuple[float, str]:
    loc = f"{job.get('location') or ''}".lower().strip()
    remote = bool(job.get("remote")) or "remote" in loc or "anywhere" in loc or "worldwide" in loc
    wanted = [w.lower().strip() for w in (targeting.get("locations") or []) if w]

    if not wanted:
        return 14.0, "no location filter"

    # If role is remote and user accepts remote
    if remote and any(w in ("remote", "anywhere", "worldwide") for w in wanted):
        return 15.0, "remote, which you accept"

    # Direct match or alias match
    for want in wanted:
        if want and want in loc:
            return 15.0, f"location matches '{want}'"
        # Check alias expansions
        aliases = LOCATION_ALIASES.get(want, [])
        for alias in aliases:
            if len(alias) <= 3:
                if re.search(rf"\b{re.escape(alias)}\b", loc):
                    return 15.0, f"location matches '{want}' ({alias.upper()})"
            else:
                if alias in loc:
                    return 15.0, f"location matches '{want}' ({alias})"

    # Check reverse lookup: if any token in loc matches target country alias
    for target_country, aliases in LOCATION_ALIASES.items():
        if target_country in wanted or any(a in wanted for a in aliases):
            for alias in aliases:
                if len(alias) <= 3:
                    if re.search(rf"\b{re.escape(alias)}\b", loc):
                        return 15.0, f"location matches '{target_country}'"
                else:
                    if alias in loc:
                        return 15.0, f"location matches '{target_country}'"

    if remote:
        return 14.0, "remote role"

    if not loc:
        return 11.0, "location not specified"

    return 7.0, f"location '{job.get('location') or 'unstated'}'"


def _seniority_score(title: str, years: str) -> tuple[float, str]:
    low = (title or "").lower()
    try:
        yrs = float(re.sub(r"[^\d.]", "", str(years)) or 0)
    except ValueError:
        yrs = 0.0

    if any(m in low for m in JUNIOR_MARKERS):
        return (10.0, "entry-level role") if yrs < 2 else (4.0, "likely below your level")
    if any(m in low for m in SENIOR_MARKERS):
        return (10.0, "senior role matching your experience") if yrs >= 5 else (4.0, "likely above your level")
    if "senior" in low:
        return (10.0, "senior role") if yrs >= 3 else (7.0, "senior title")
    return 10.0, "level looks appropriate"


def score_job(job: dict[str, Any], *, resume: str | None = None,
              targeting: dict[str, Any] | None = None) -> dict[str, Any]:
    targeting = targeting or (store.get_setting("targeting", {}) or {})
    profile = store.get_setting("profile", {}) or {}
    resume = resume if resume is not None else resume_text()

    category = job.get("role_category")
    title_pts, title_why = _title_score(job.get("title", ""), targeting, category=category)
    loc_pts, loc_why = _location_score(job, targeting)
    sen_pts, sen_why = _seniority_score(job.get("title", ""), profile.get("years_experience", ""))

    description = job.get("description") or ""
    if description and resume:
        jd = analyze_jd(f"{job.get('title','')}\n\n{description}")
        match = match_keywords(resume, jd)
        
        # Hard tech skills count more heavily than noisy generic n-grams
        hard_jd = [k for k in jd.get("keywords", []) if k.get("category") == "hard"]
        hard_matched = [k for k in match.get("matched", []) if k.get("category") == "hard"]
        
        if hard_jd:
            hard_coverage = len(hard_matched) / len(hard_jd)
            overall_coverage = match.get("coverage", 0.0)
            blended_coverage = (0.75 * hard_coverage) + (0.25 * overall_coverage)
        else:
            blended_coverage = match.get("coverage", 0.0)

        # Calibrated ATS scoring: 55%+ coverage maps to top-tier score (up to 45 pts)
        kw_pts = round(min(blended_coverage / 0.55, 1.0) * 45, 1)
        missing = [m["term"] for m in match.get("missing", [])[:6] if m.get("category") == "hard"] or [m["term"] for m in match.get("missing", [])[:6]]
        kw_why = (f"{len(match['matched'])}/{len(jd['keywords'])} JD terms in your resume"
                  + (f"; missing {', '.join(missing[:4])}" if missing else ""))
    else:
        # No description published — score based on title keywords and domain targeting
        blob = f"{job.get('title','')} {job.get('department','')}".lower()
        keys = [k.lower() for k in (targeting.get("keywords") or []) if k]
        hit = sum(1 for k in keys if k in blob)
        kw_pts = round((hit / len(keys)) * 40, 1) if keys else 30.0
        kw_why = "no job description published; scored on title tech keywords"
        missing = []

    total = min(round(title_pts + kw_pts + loc_pts + sen_pts, 1), 100.0)
    reason = " · ".join([title_why, kw_why, loc_why, sen_why])

    return {
        "score": total,
        "reason": reason[:900],
        "breakdown": {
            "title": title_pts, "keywords": kw_pts,
            "location": loc_pts, "seniority": sen_pts,
        },
        "missing": missing,
    }


def enrich_pending(limit: int = 400, *, log=print) -> int:
    """
    Parse detail into any scored job that has never been parsed.

    Scoring enriches as it goes, so this only ever finds rows that predate the
    parser. It is idempotent — a parsed row has a non-null `skills` list and is
    not returned again — so it is safe to run on every discovery.
    """
    pending = store.jobs_needing_meta(limit)
    done = 0
    for job in pending:
        try:
            meta = jobmeta.enrich(job)
            # Store a list either way, so a job with a description but no
            # recognised skills is still marked parsed and not re-visited.
            meta.setdefault("skills", [])
            store.set_job_meta(job["id"], meta)
            done += 1
        except Exception as exc:
            log(f"[match] could not parse detail for job {job.get('id')}: {exc}")
    if done:
        log(f"[match] parsed detail into {done} earlier job(s)")
    return done


# North America is rarely written as "United States" on a job — it is a city and
# a two-letter state ("San Francisco, CA"). These catch the common shapes a bare
# country-name list misses. A comma-prefixed state code is US-specific enough to
# be safe; a handful of unmistakable NA cities cover the rest.
_US_STATE = re.compile(
    r",\s*(a[klzr]|c[aot]|d[ce]|fl|ga|hi|i[adln]|k[sy]|la|m[adeinost]|n[cdehjmvy]|"
    r"o[hkr]|pa|ri|s[cd]|t[nx]|ut|v[at]|w[aivy])\b", re.I)
_NA_CITY = re.compile(
    r"\b(new york|nyc|san francisco|sf bay|bay area|silicon valley|los angeles|"
    r"chicago|seattle|boston|austin|denver|atlanta|dallas|houston|miami|"
    r"washington dc|toronto|vancouver|montreal|ottawa|calgary)\b", re.I)


def location_excluded(location: str, exclude: list[str]) -> str | None:
    """
    The excluded country a posting's location matches, or None.

    Pakistan is always kept, and a location with no country (a bare "Remote") is
    never excluded on this — the regions the user does not want are filtered, not
    everything without an explicit match. North America is also caught by state
    code and major city, since postings there rarely name the country.
    """
    if not exclude:
        return None
    loc = f" {(location or '').lower()} "
    if not loc.strip() or "pakistan" in loc:
        return None
    for token in exclude:
        # Keep the token's own spacing — " US " is padded on purpose so it does
        # not match "aUStria" or "hoUSe"; stripping it would.
        t = (token or "").lower()
        if t.strip() and t in loc:
            return token.strip()
    if _US_STATE.search(location or "") or _NA_CITY.search(location or ""):
        return "North America"
    return None


def regate_experience(*, log=print) -> dict[str, int]:
    """
    Re-run the experience gate over jobs already scored, and skip the ones it now
    rejects.

    The gate improves over time — a title-versus-board-level fix, a new senior
    keyword — but a change only reaches jobs scored afterwards. This applies the
    current gate to everything still in the actionable pool, so a "Senior" role
    that slipped an older gate is filtered out without clearing and re-fetching.
    Applied rows are never touched: your own history is not housekeeping.
    """
    targeting = store.get_setting("targeting", {}) or {}
    min_years = int(targeting.get("min_years_experience", 1))
    max_years = int(targeting.get("max_years_experience", 3))
    allow_interns = bool(targeting.get("allow_internships", False))
    max_age_days = int(targeting.get("max_age_days", 3) or 0)
    stale_cutoff = int(time.time() - max_age_days * 86400) if max_age_days > 0 else 0
    exclude_locations = list(targeting.get("exclude_locations")
                             or store.DEFAULT_SETTINGS["targeting"]["exclude_locations"])

    jobs = store.list_jobs(limit=2000, status="not_applied")
    demoted = 0
    for job in jobs:
        bad_loc = location_excluded(job.get("location") or "", exclude_locations)
        if bad_loc:
            store.set_job_fit(job["id"], 0.0,
                              f"Region gate: {job.get('location')} outside your regions",
                              "skipped")
            demoted += 1
            log(f"[regate] skipped {job.get('company_name') or '?'} — "
                f"{job['title'][:44]} ({job.get('location')})")
            continue
        posted = job.get("posted_ts")
        if stale_cutoff and posted and posted < stale_cutoff:
            days = int((time.time() - posted) / 86400)
            store.set_job_fit(job["id"], 0.0,
                              f"Freshness gate: posted {days} days ago", "skipped")
            demoted += 1
            log(f"[regate] skipped {job.get('company_name') or '?'} — "
                f"{job['title'][:48]} (posted {days}d ago)")
            continue
        fits, why = experience.verdict(job, min_years=min_years, max_years=max_years,
                                       allow_internships=allow_interns)
        if not fits:
            store.set_job_fit(job["id"], 0.0, f"Experience gate: {why}", "skipped")
            demoted += 1
            log(f"[regate] skipped {job.get('company_name') or '?'} — {job['title'][:48]} ({why})")
    log(f"[regate] {demoted} of {len(jobs)} actionable job(s) now filtered out "
        f"by the freshness and experience gates")
    return {"checked": len(jobs), "demoted": demoted}


def score_pending(limit: int = 200, *, log=print) -> dict[str, int]:
    """Score every unscored job in the store and set its status."""
    targeting = store.get_setting("targeting", {}) or {}
    threshold = float(targeting.get("min_fit_score", 55))
    resume = resume_text()
    if not resume:
        log("[match] no resume found — scoring on title/location only. "
            "Set profile.default_resume in Settings for keyword scoring.")

    min_years = int(targeting.get("min_years_experience", 1))
    max_years = int(targeting.get("max_years_experience", 3))
    allow_interns = bool(targeting.get("allow_internships", False))
    max_age_days = int(targeting.get("max_age_days", 3) or 0)
    stale_cutoff = int(time.time() - max_age_days * 86400) if max_age_days > 0 else 0
    exclude_locations = list(targeting.get("exclude_locations")
                             or store.DEFAULT_SETTINGS["targeting"]["exclude_locations"])

    jobs = store.jobs_needing_scoring(limit)
    matched = skipped = out_of_range = stale = off_region = 0

    for job in jobs:
        # Region is the first gate: a posting in a country the user is not
        # targeting is filtered out however well it otherwise matches. Remote and
        # Pakistan are always kept (see location_excluded).
        bad_loc = location_excluded(job.get("location") or "", exclude_locations)
        if bad_loc:
            off_region += 1
            store.set_job_fit(job["id"], 0.0,
                              f"Region gate: {job.get('location')} is outside your "
                              f"target regions", "skipped")
            continue

        # Freshness is the next gate. A three-week-old posting has hundreds of
        # applicants already in the pile, so it is filtered out of the actionable
        # list here — not only at apply-selection, where the dashboard and a
        # direct apply could still reach it. A posting with no date is left to
        # the experience/fit gates rather than assumed stale.
        posted = job.get("posted_ts")
        if stale_cutoff and posted and posted < stale_cutoff:
            days = int((time.time() - posted) / 86400)
            stale += 1
            store.set_job_fit(job["id"], 0.0,
                              f"Freshness gate: posted {days} days ago, past your "
                              f"{max_age_days}-day window", "skipped")
            continue

        # Experience is a hard gate, checked before scoring: a role demanding
        # eight years is not a candidate no matter how well the keywords line up.
        fits, why = experience.verdict(job, min_years=min_years, max_years=max_years,
                                       allow_internships=allow_interns)
        if not fits:
            out_of_range += 1
            store.set_job_fit(job["id"], 0.0, f"Experience gate: {why}", "skipped")
            continue

        result = score_job(job, resume=resume, targeting=targeting)
        status = "matched" if result["score"] >= threshold else "skipped"
        store.set_job_fit(job["id"], result["score"],
                          f"{result['reason']} · experience: {why}", status)

        # Parse the posting into fields while we already hold it — salary,
        # seniority, work arrangement, skills, deadline. Deterministic and free,
        # so it runs for every job rather than only matched ones; a skipped role
        # can still be searched and filtered on its parsed detail.
        try:
            meta = jobmeta.enrich(job)
            if meta:
                store.set_job_meta(job["id"], meta)
        except Exception as exc:  # parsing must never sink a scoring run
            log(f"[match] could not parse detail for job {job.get('id')}: {exc}")
        if status == "matched":
            matched += 1
            log(f"[match] {result['score']:5.1f}  {job.get('company_name') or '?'} — "
                f"{job['title'][:48]}  ({experience.describe(job)})")
        else:
            skipped += 1

    log(f"[match] {matched} matched, {skipped} below the {threshold:.0f} threshold, "
        f"{out_of_range} outside the {min_years}-{max_years} year window, "
        f"{stale} past the {max_age_days}-day freshness window, "
        f"{off_region} outside your target regions")
    return {"scored": len(jobs), "matched": matched, "skipped": skipped,
            "outOfExperienceRange": out_of_range, "stale": stale,
            "offRegion": off_region}


def rescore_all_jobs(limit: int = 2000, *, log=print) -> dict[str, int]:
    """Re-score all actionable jobs in the database using updated matching criteria."""
    targeting = store.get_setting("targeting", {}) or {}
    threshold = float(targeting.get("min_fit_score", 55))
    resume = resume_text()
    exclude_locations = list(targeting.get("exclude_locations")
                             or store.DEFAULT_SETTINGS["targeting"]["exclude_locations"])

    jobs = store.list_jobs(limit=limit)
    rescored = 0
    matched = 0
    for job in jobs:
        if job.get("status") in ("applied", "interviewing", "offer", "rejected"):
            continue

        # Region gate
        bad_loc = location_excluded(job.get("location") or "", exclude_locations)
        if bad_loc:
            continue

        fits, why = experience.verdict(job, min_years=int(targeting.get("min_years_experience", 1)),
                                       max_years=int(targeting.get("max_years_experience", 3)),
                                       allow_internships=bool(targeting.get("allow_internships", False)))
        if not fits:
            continue

        result = score_job(job, resume=resume, targeting=targeting)
        status = "matched" if result["score"] >= threshold else "skipped"
        store.set_job_fit(job["id"], result["score"],
                          f"{result['reason']} · experience: {why}", status)
        rescored += 1
        if status == "matched":
            matched += 1
    log(f"[match] rescored {rescored} jobs ({matched} above {threshold:.0f} fit threshold)")
    return {"rescored": rescored, "matched": matched}
