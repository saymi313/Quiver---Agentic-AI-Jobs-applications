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


def _title_score(title: str, targeting: dict[str, Any]) -> tuple[float, str]:
    low = (title or "").lower()
    if not low:
        return 0.0, "no title"

    for bad in targeting.get("exclude_titles") or []:
        if bad and bad.lower() in low:
            return 0.0, f"excluded by '{bad}'"

    wanted = [t.lower() for t in (targeting.get("titles") or []) if t]
    if not wanted:
        return 20.0, "no title filter set"

    for want in wanted:
        if want in low:
            return 30.0, f"title matches '{want}'"

    # partial: share of the wanted title's words present
    best, best_want = 0.0, ""
    for want in wanted:
        words = [w for w in re.findall(r"[a-z]+", want) if len(w) > 2]
        if not words:
            continue
        hit = sum(1 for w in words if w in low) / len(words)
        if hit > best:
            best, best_want = hit, want
    if best >= 0.5:
        return round(30 * best, 1), f"partial match on '{best_want}'"
    return round(30 * best, 1), "title only loosely related"


def _location_score(job: dict[str, Any], targeting: dict[str, Any]) -> tuple[float, str]:
    loc = f"{job.get('location') or ''}".lower()
    remote = bool(job.get("remote")) or "remote" in loc
    wanted = [w.lower() for w in (targeting.get("locations") or []) if w]

    if not wanted:
        return 12.0, "no location filter"
    if remote and any(w in ("remote", "anywhere", "worldwide") for w in wanted):
        return 15.0, "remote, which you accept"
    for want in wanted:
        if want and want in loc:
            return 15.0, f"location matches '{want}'"
    if remote:
        return 11.0, "remote role"
    return 4.0, f"location '{job.get('location') or 'unstated'}' outside your list"


def _seniority_score(title: str, years: str) -> tuple[float, str]:
    low = (title or "").lower()
    try:
        yrs = float(re.sub(r"[^\d.]", "", str(years)) or 0)
    except ValueError:
        yrs = 0.0

    if any(m in low for m in JUNIOR_MARKERS):
        return (10.0, "entry-level role") if yrs < 2 else (3.0, "likely below your level")
    if any(m in low for m in SENIOR_MARKERS):
        return (10.0, "senior role matching your experience") if yrs >= 6 else (3.0, "likely above your level")
    if "senior" in low:
        return (10.0, "senior role") if yrs >= 3 else (6.0, "senior title, slightly ahead of you")
    return 9.0, "level looks appropriate"


def score_job(job: dict[str, Any], *, resume: str | None = None,
              targeting: dict[str, Any] | None = None) -> dict[str, Any]:
    targeting = targeting or (store.get_setting("targeting", {}) or {})
    profile = store.get_setting("profile", {}) or {}
    resume = resume if resume is not None else resume_text()

    title_pts, title_why = _title_score(job.get("title", ""), targeting)
    loc_pts, loc_why = _location_score(job, targeting)
    sen_pts, sen_why = _seniority_score(job.get("title", ""), profile.get("years_experience", ""))

    description = job.get("description") or ""
    if description and resume:
        jd = analyze_jd(f"{job.get('title','')}\n\n{description}")
        match = match_keywords(resume, jd)
        kw_pts = round(min(match["coverage"] / 0.7, 1.0) * 45, 1)
        missing = [m["term"] for m in match["missing"][:6]]
        kw_why = (f"{len(match['matched'])}/{len(jd['keywords'])} JD terms in your resume"
                  + (f"; missing {', '.join(missing[:4])}" if missing else ""))
    else:
        # No description on this board — fall back to the configured keywords.
        blob = f"{job.get('title','')} {job.get('department','')}".lower()
        keys = [k.lower() for k in (targeting.get("keywords") or []) if k]
        hit = sum(1 for k in keys if k in blob)
        kw_pts = round((hit / len(keys)) * 30, 1) if keys else 15.0
        kw_why = "no job description published; scored on title keywords only"
        missing = []

    total = round(title_pts + kw_pts + loc_pts + sen_pts, 1)
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

    jobs = store.jobs_needing_scoring(limit)
    matched = skipped = out_of_range = 0

    for job in jobs:
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
        f"{out_of_range} outside the {min_years}-{max_years} year window")
    return {"scored": len(jobs), "matched": matched, "skipped": skipped,
            "outOfExperienceRange": out_of_range}
