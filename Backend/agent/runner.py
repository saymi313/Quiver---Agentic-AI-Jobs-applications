"""
The agent loop.

  discover  boards and career portals -> tracked jobs, contacts, tailored resumes
  resumes   build a tailored resume for specific jobs, on demand
  apply     fill and submit the forms for specific jobs the user chose
  outreach  research each verified contact, write a personal email, send it
  full      discover + outreach. Deliberately never applies.

Applying is user-triggered only. Discovery and resume generation are safe to
automate; submitting an application on someone's behalf without them asking is
not, so `apply` requires explicit --job-ids and `full` stops short of it.

Invoked as a script so the dashboard can stream stdout through the existing job
console:

    python -m agent.runner discover --sources yc,hn,remote,hidden --limit 40
    python -m agent.runner resumes --job-ids 12,15
    python -m agent.runner apply --job-ids 12,15 --dry-run
    python -m agent.runner outreach --limit 10 --delay 90 --dry-run
    python -m agent.runner full --limit 25
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
import time
import traceback
from typing import Any, Callable

from . import (applier, categories, experience, jobdesc, matcher, outreach,
               people as people_mod, sources, store, tailor)


# A bare Windows console defaults to cp1252 and chokes on anything non-ASCII
# that scraped pages inevitably contain. The dashboard sets PYTHONIOENCODING,
# but make a direct `python -m agent.runner` safe too.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def _log(message: str) -> None:
    try:
        print(message, flush=True)
    except UnicodeEncodeError:
        print(message.encode("ascii", "replace").decode("ascii"), flush=True)


def _rule(title: str) -> str:
    return f"\n--- {title} " + "-" * max(0, 46 - len(title))


# --------------------------------------------------------------------------
# Discovery
# --------------------------------------------------------------------------

class Tracker:
    """
    The one gate every discovered job passes through.

    Two rules from the spec live here and nowhere else, so no source can route
    around them:

      * a job outside the ten role categories is never tracked;
      * a job already in the database is skipped without being reprocessed,
        which is what makes each run incremental rather than a repeat.

    The hash check runs against `store.known_hashes()` loaded once at the start,
    plus everything added during this run, so a role listed on two boards is
    stored once.
    """

    def __init__(self, targeting: dict[str, Any], log: Callable[[str], None]) -> None:
        self.enabled = categories.enabled_slugs(targeting)
        self.use_llm = bool(targeting.get("classify_with_llm", False))
        self.seen = store.known_hashes()
        self.log = log
        self.new_ids: list[int] = []
        self.counts = {"off_category": 0, "already_tracked": 0, "new": 0}
        log(f"[track] {len(self.seen)} job(s) already tracked · "
            f"{len(self.enabled)} categor{'y' if len(self.enabled) == 1 else 'ies'} enabled")

    def add(self, job: dict[str, Any], company_id: int, company_name: str) -> int | None:
        title = job.get("title") or ""
        category = categories.classify(title, job.get("description") or "",
                                       use_llm=self.use_llm, log=self.log)
        if not category or category not in self.enabled:
            self.counts["off_category"] += 1
            return None

        job_hash = job.get("dedupe_hash") or sources.dedupe_hash(
            company_name, title, job.get("location") or "", url=job.get("url") or "")
        if job_hash in self.seen:
            self.counts["already_tracked"] += 1
            return None
        self.seen.add(job_hash)

        job_id = store.upsert_job(
            {**job, "company_id": company_id, "dedupe_hash": job_hash,
             "role_category": category},
            company_name=company_name)
        if job_id:
            self.new_ids.append(int(job_id))
            self.counts["new"] += 1
        return job_id

    def summary(self) -> str:
        c = self.counts
        return (f"{c['new']} new · {c['already_tracked']} already tracked · "
                f"{c['off_category']} outside the ten categories")


def backfill_categories(log: Callable[[str], None] = _log) -> int:
    """Classify rows stored before the category column existed. Rules only, no LLM."""
    rows = [r for r in store.list_jobs(1000) if not r.get("role_category")]
    fixed = 0
    for row in rows:
        slug = categories.classify(row.get("title") or "")
        if slug:
            store.set_job_category(int(row["id"]), slug)
            fixed += 1
    if rows:
        log(f"[track] backfilled {fixed}/{len(rows)} older row(s) with a role category")
    return fixed


def purge_stale(*, log: Callable[[str], None] = _log) -> dict[str, Any]:
    """
    Housekeeping, run at the start of every search.

    A job discovered longer ago than `limits.retention_days` cannot still be
    fresh, so it goes, and its tailored resume goes with it — those files are
    only meaningful next to the row that names them.

    Applied jobs are kept. The double-apply guard reads the applications table
    so it would survive either way, but deleting the row would erase your own
    record of where you applied, which is not what housekeeping means.
    """
    limits = store.get_setting("limits", {}) or {}
    days = int(limits.get("retention_days", 3))
    keep_applied = bool(limits.get("purge_keeps_applied", True))
    if days <= 0:
        return {"deleted": 0, "files": 0}

    out = store.purge_old_jobs(days, keep_applied=keep_applied)
    removed = 0
    for path in out.get("resumes") or []:
        for candidate in (Path(path), Path(path).with_suffix(".tex")):
            try:
                if candidate.is_file():
                    candidate.unlink()
                    removed += 1
            except OSError:
                pass

    if out["deleted"]:
        log(f"[purge] removed {out['deleted']} job(s) discovered more than {days} day(s) ago"
            + (f", and {removed} resume file(s)" if removed else "")
            + (" — applied jobs kept" if keep_applied else ""))
    return {"deleted": out["deleted"], "files": removed}


def build_resumes_for(job_ids: list[int], *, log: Callable[[str], None] = _log) -> dict[str, Any]:
    """Tailor a resume for each of these jobs. Used by the table's Generate button."""
    rows = store.jobs_by_ids([int(i) for i in job_ids])
    if not rows:
        log("[resume] none of those job ids exist.")
        return {"built": 0, "failed": 0}
    built = failed = 0
    for row in rows:
        out = tailor.build_and_record(row, log=log)
        built, failed = built + bool(out["ok"]), failed + (not out["ok"])
        if not out["ok"]:
            log(f"[resume] FAILED job {row['id']}: {out['reason']}")
    log(f"[resume] done — built={built} failed={failed}")
    return {"built": built, "failed": failed}


def discover(*, which: list[str], limit: int, find_people: bool,
             scan_ats: bool, build_resumes: bool = True,
             log: Callable[[str], None] = _log) -> dict[str, Any]:
    targeting = store.get_setting("targeting", {}) or {}
    limits = store.get_setting("limits", {}) or {}
    regions = [r.lower() for r in (targeting.get("regions") or [])]
    keywords = targeting.get("keywords") or []
    per_source = int(limits.get("max_companies_per_source", 60))

    counts = {"companies": 0, "jobs": 0, "people": 0, "verified": 0}
    company_rows: list[tuple[int, dict[str, Any]]] = []

    # Housekeeping first: this frees the dedupe hashes of anything expired, so
    # a role that is still live can be re-discovered rather than being skipped
    # as "already tracked" forever.
    purged = purge_stale(log=log)
    counts["purged"] = purged["deleted"]

    track = Tracker(targeting, log)
    backfill_categories(log)

    # ---- Y Combinator ----------------------------------------------------
    if "yc" in which:
        log(_rule("Y Combinator"))
        for c in sources.fetch_yc(limit=min(limit, per_source), hiring_only=True,
                                  regions=regions, log=log):
            cid = store.upsert_company(c)
            company_rows.append((cid, c))
            counts["companies"] += 1

    # ---- Hacker News "Who is hiring" ------------------------------------
    if "hn" in which:
        log(_rule("Hacker News: Who is hiring"))
        for c in sources.fetch_hn_hiring(limit=min(limit, per_source), log=log):
            hn = c.pop("_hn", {})
            cid = store.upsert_company(c)
            company_rows.append((cid, {**c, "_hn": hn, "id": cid}))
            counts["companies"] += 1
            # Emails the founder published in their own post: highest signal available.
            for email in hn.get("emails", []):
                check = people_mod.verify_email(email, log=log)
                pid = store.upsert_person({
                    "company_id": cid, "email": email, "email_source": "hn",
                    "role": people_mod.classify_role(email, hn.get("headline", "")),
                    "title": hn.get("headline", "")[:120],
                    "email_status": check["status"], "email_score": check["score"],
                    "verify_detail": check["detail"],
                })
                if pid:
                    counts["people"] += 1
                    if check["status"] in ("valid", "risky"):
                        counts["verified"] += 1
                    log(f"[hn] {email:<38} {check['status']} ({check['score']:.2f})")

    # ---- Remote / European boards ---------------------------------------
    if "remote" in which:
        log(_rule("Remote & European job boards"))
        for entry in sources.fetch_remote_boards(limit=min(limit * 3, 200),
                                                 keywords=keywords, log=log):
            job = entry.pop("_job")
            cid = store.upsert_company(entry)
            counts["companies"] += 1
            if track.add(job, cid, entry["name"]):
                counts["jobs"] += 1

    # ---- Low-competition boards -----------------------------------------
    if "hidden" in which:
        log(_rule("Hidden job market: low-competition boards"))
        for entry in sources.fetch_hidden_boards(limit=min(limit * 4, 250),
                                                 keywords=keywords, log=log):
            job = entry.pop("_job")
            cid = store.upsert_company(entry)
            counts["companies"] += 1
            if track.add(job, cid, entry["name"]):
                counts["jobs"] += 1

    # ---- Company ATS boards ---------------------------------------------
    if scan_ats and company_rows:
        log(_rule("Scanning company career portals"))
        scanned = 0
        for cid, c in company_rows:
            if scanned >= limit:
                break
            website = c.get("website") or ""
            if not website:
                continue
            stored = store.company(cid) or {}
            platform, token = stored.get("ats_platform"), stored.get("ats_token")
            if not (platform and token):
                found = sources.detect_ats(website, name=c.get("name", ""), log=log)
                if not found:
                    store.mark_company_scanned(cid)
                    continue
                store.upsert_company({**c, **found})
                platform, token = found["ats_platform"], found["ats_token"]
            for job in sources.fetch_ats_jobs(platform, token, log=log):
                if track.add(job, cid, c.get("name", "")):
                    counts["jobs"] += 1
            store.mark_company_scanned(cid)
            scanned += 1
            time.sleep(0.3)

    # ---- People ----------------------------------------------------------
    if find_people and company_rows:
        log(_rule("Finding founders & recruiters"))
        budget = min(limit, 25)
        for cid, c in company_rows:
            if budget <= 0:
                break
            if not c.get("website"):
                continue
            found = people_mod.discover_people(
                {**c, "id": cid},
                hn_emails=(c.get("_hn") or {}).get("emails", []),
                log=log)
            for person in found:
                if store.upsert_person({**person, "company_id": cid}):
                    counts["people"] += 1
                    if person["email_status"] in ("valid", "risky"):
                        counts["verified"] += 1
            budget -= 1

    # ---- Full job descriptions -------------------------------------------
    # Before scoring, not after: a fit score computed on a two-sentence teaser
    # is close to meaningless, and the tailored resume is only as good as the
    # description it was aimed at.
    if track.new_ids:
        log(_rule("Fetching full job descriptions"))
        fetched = 0
        for job_id in track.new_ids:
            row = store.job(job_id)
            if not row or not jobdesc.needs_fetch(row):
                continue
            text, origin = jobdesc.fetch_description(row, log=log)
            if text and len(text) > len(row.get("description") or ""):
                store.set_job_description(job_id, text, origin)
                fetched += 1
        log(f"[jd] filled in {fetched} description(s) from the listing pages")
        counts["descriptions"] = fetched

    # ---- Score everything found -----------------------------------------
    log(_rule("Scoring roles against your profile"))
    scored = matcher.score_pending(limit=400, log=log)
    counts.update(scored)

    # ---- Recruiter contact, per job --------------------------------------
    # Only ever written when a real address was found and verified. A job with
    # no contact keeps an empty field; nothing is guessed.
    if track.new_ids:
        log(_rule("Attaching recruiter contacts"))
        attached = 0
        by_company: dict[int, list[dict[str, Any]]] = {}
        for person in store.list_people(500):
            if person.get("email_status") in ("valid", "risky") and person.get("company_id"):
                by_company.setdefault(int(person["company_id"]), []).append(person)

        def rank(p: dict[str, Any]) -> tuple[int, float]:
            role_order = {"recruiter": 0, "founder": 1}.get(p.get("role") or "", 2)
            return (role_order, -(p.get("email_score") or 0))

        for job_id in track.new_ids:
            row = store.job(job_id)
            if not row or row.get("recruiter_email"):
                continue
            people = sorted(by_company.get(int(row.get("company_id") or -1), []), key=rank)
            if people:
                best = people[0]
                store.set_job_recruiter(job_id, best["email"], best.get("full_name") or "")
                attached += 1
        log(f"[contact] {attached} job(s) have a verified recruiter or founder address")
        counts["recruiters"] = attached

    # ---- Tailored resumes -------------------------------------------------
    if build_resumes:
        cap = int(limits.get("max_resumes_per_run", 10))
        queue = [store.job(i) for i in track.new_ids]
        queue = [j for j in queue
                 if j and j.get("status") == "matched" and not tailor.existing(j)]
        queue.sort(key=lambda j: -(j.get("fit_score") or 0))
        if queue:
            log(_rule(f"Tailoring resumes (best {min(cap, len(queue))} of {len(queue)})"))
            built = 0
            for row in queue[:cap]:
                if tailor.build_and_record(row, log=log)["ok"]:
                    built += 1
            counts["resumes"] = built
            if len(queue) > cap:
                log(f"[resume] {len(queue) - cap} matched role(s) left without a resume — "
                    f"use Generate resume in the jobs table, or raise "
                    f"limits.max_resumes_per_run")

    log(f"\n[discover] {track.summary()}")
    log(f"[discover] companies={counts['companies']} jobs={counts['jobs']} "
        f"people={counts['people']} (verified {counts['verified']}) "
        f"matched={counts.get('matched', 0)} resumes={counts.get('resumes', 0)}")
    counts.update(track.counts)
    return counts


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="agent.runner", description="Job-hunting agent")
    ap.add_argument("mode", choices=["discover", "apply", "resumes", "outreach", "full"])
    ap.add_argument("--sources", default="yc,hn,remote,hidden",
                    help="comma list: yc, hn, remote, hidden")
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--delay", type=int, default=90, help="seconds between emails")
    ap.add_argument("--max-age", type=int, default=None,
                    help="only apply to roles posted within N days (default: from Settings)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--to-self", action="store_true", help="send outreach to your own address")
    ap.add_argument("--no-people", action="store_true", help="skip founder/email discovery")
    ap.add_argument("--no-ats", action="store_true", help="skip career-portal scanning")
    ap.add_argument("--no-attach", action="store_true", help="do not attach the resume")
    ap.add_argument("--headed", action="store_true", help="show the browser while applying")
    ap.add_argument("--job-ids", default="",
                    help="comma list of job ids to apply to (per-job or bulk apply)")
    ap.add_argument("--no-resumes", action="store_true",
                    help="discover without generating tailored resumes")
    args = ap.parse_args(argv)

    store.init()
    which = [s.strip().lower() for s in args.sources.split(",") if s.strip()]
    job_ids = [int(x) for x in args.job_ids.replace(" ", "").split(",") if x.strip().isdigit()]
    run_id = store.start_run(args.mode, vars(args))
    stats: dict[str, Any] = {}

    try:
        if args.mode in ("discover", "full"):
            stats["discover"] = discover(
                which=which, limit=args.limit,
                find_people=not args.no_people, scan_ats=not args.no_ats,
                build_resumes=not args.no_resumes)

        if args.mode == "resumes":
            _log(_rule("Tailoring resumes"))
            stats["resumes"] = build_resumes_for(job_ids)

        if args.mode == "apply":
            # Apply is user-triggered only. `full` deliberately stops before it:
            # discovery and resume generation are safe to automate, submitting an
            # application on someone's behalf without them asking is not.
            if not job_ids:
                _log("[apply] no --job-ids given. Select jobs in the dashboard, or pass "
                     "--job-ids 12,15,18. Nothing was submitted.")
                stats["apply"] = {"attempted": 0}
            else:
                _log(_rule("Applying to the selected jobs"))
                stats["apply"] = applier.apply_to_ids(
                    job_ids, dry_run=args.dry_run, headless=not args.headed)

        if args.mode in ("outreach", "full"):
            _log(_rule("Cold outreach"))
            stats["outreach"] = outreach.run_outreach(
                limit=args.limit if args.mode == "outreach" else min(args.limit, 10),
                dry_run=args.dry_run, delay=args.delay,
                attach_resume=not args.no_attach, to_self=args.to_self)

        store.finish_run(run_id, "finished", stats)
        _log("\n[agent] run complete")
        return 0

    except KeyboardInterrupt:
        store.finish_run(run_id, "stopped", stats, "interrupted")
        _log("\n[agent] stopped")
        return 130
    except Exception as exc:
        store.finish_run(run_id, "failed", stats, f"{type(exc).__name__}: {exc}")
        _log(f"\n[agent] FAILED — {type(exc).__name__}: {exc}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
