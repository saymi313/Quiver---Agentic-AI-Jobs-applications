"""
One tailored resume per job, built by the resume engine the rest of the project
already uses.

This module is deliberately thin. It does not know how to lay out a resume — it
loads the curated profile, hands the job description to `api/latex_resume.py`,
and files the result. Every house style rule (Times, no hyphens, three to five
bullets per role, one page) therefore applies here exactly as it does in the
Resume Tailor tab, because it is the same `build()` call. Nothing bypasses it.

Resumes live in `Backend/outputs/agent_resumes/` as a `.tex` and a `.pdf` per
job. The version recorded against the job is the file stem plus a short content
hash, so rebuilding after the profile changes produces a genuinely new version
rather than silently overwriting the one that was already sent somewhere.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Callable

from api.config import OUTPUTS_DIR

RESUME_DIR = OUTPUTS_DIR / "agent_resumes"

# A description this short is a teaser. Tailoring against it would reorder
# bullets on noise, so the master resume is used unchanged instead.
MIN_JD_CHARS = 220


def stem_for(job: dict[str, Any]) -> str:
    """House naming: Usairam_Saeed_CompanyName_Role, prefixed with the job id
    so two openings at the same company cannot overwrite each other."""
    from api import resume_style

    from . import store

    profile = store.get_setting("profile", {}) or {}
    candidate = profile.get("full_name") or "Resume"
    stem = resume_style.file_stem(candidate, job.get("company_name") or job.get("company") or "",
                                  job.get("title") or "")
    return f"{stem}_j{job.get('id')}"


def paths_for(job: dict[str, Any]) -> dict[str, Path]:
    stem = stem_for(job)
    return {"tex": RESUME_DIR / f"{stem}.tex", "pdf": RESUME_DIR / f"{stem}.pdf"}


def existing(job: dict[str, Any]) -> Path | None:
    """The tailored PDF already on disk for this job, if any."""
    stored = (job.get("resume_path") or "").strip()
    if stored:
        p = Path(stored)
        if p.is_file():
            return p
    p = paths_for(job)["pdf"]
    return p if p.is_file() else None


def build_for_job(job: dict[str, Any], *, use_llm: bool = True,
                  log: Callable[[str], None] = print) -> dict[str, Any]:
    """
    Tailor and compile a resume for one job. Never raises.

    Returns {ok, pdf, tex, version, pages, reason}. On any failure `ok` is False
    and `reason` says why, so the caller can record it against the job instead
    of dropping it.
    """
    from api import ats, behuman, latex_resume

    result: dict[str, Any] = {"ok": False, "pdf": None, "tex": None,
                              "version": "", "pages": None, "reason": ""}
    title = job.get("title") or "role"
    company = job.get("company_name") or "?"

    if not latex_resume.PROFILE_PATH.is_file():
        result["reason"] = "cv_data/profile.yaml is missing — nothing to tailor from."
        return result

    description = (job.get("description") or "").strip()
    jd_text = f"{title}\n\n{description}"

    try:
        content = latex_resume.from_profile()
    except Exception as exc:
        result["reason"] = f"could not read profile.yaml: {type(exc).__name__}: {exc}"
        return result

    RESUME_DIR.mkdir(parents=True, exist_ok=True)
    stem = stem_for(job)

    try:
        if len(description) >= MIN_JD_CHARS:
            jd = ats.analyze_jd(jd_text)
            latex_resume.tailor(content, jd_text, jd, use_llm=use_llm,
                                log=lambda m: log(f"[resume]   {m}"))
        else:
            log(f"[resume]   description is {len(description)} chars — "
                f"building the master resume rather than tailoring to a teaser")

        out = latex_resume.build(content, RESUME_DIR, stem, one_page=True,
                                 log=lambda m: log(f"[resume]   {m}"))
    except Exception as exc:
        result["reason"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        log(f"[resume] FAILED {company} — {title[:40]}: {result['reason']}")
        return result

    if not out.get("pdf"):
        result["tex"] = out.get("tex")
        result["reason"] = out.get("message") or "no LaTeX engine — only the .tex was written"
        log(f"[resume] {company} — {title[:40]}: {result['reason']}")
        return result

    # Version identifies the content, not just the file, so a rebuild after the
    # profile changes is distinguishable from the copy already sent out.
    digest = hashlib.sha1((out.get("texSource") or "").encode("utf-8")).hexdigest()[:8]
    body = " ".join([content.summary]
                    + [b.text for blk in content.experience + content.projects
                       for b in blk.bullets])

    result.update({
        "ok": True,
        "pdf": out["pdf"],
        "tex": out["tex"],
        "version": f"{stem}-{digest}",
        "pages": out.get("pages"),
        "behuman": behuman.report(body),
    })
    log(f"[resume] {company} — {title[:44]} -> {out['pdf'].name} "
        f"({out.get('pages')} page, {result['behuman']})")
    return result


def build_and_record(job: dict[str, Any], *, use_llm: bool = True,
                     log: Callable[[str], None] = print) -> dict[str, Any]:
    """Build, then write the path and version onto the job record."""
    from . import store

    out = build_for_job(job, use_llm=use_llm, log=log)
    if out["ok"]:
        store.set_job_resume(int(job["id"]), str(out["pdf"]), out["version"])
    return out
