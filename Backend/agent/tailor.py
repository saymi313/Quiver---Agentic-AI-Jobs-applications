"""
One tailored resume per job, built by the resume engine the rest of the project
already uses.

This module is deliberately thin. It does not know how to lay out a resume — it
loads the curated profile, hands the job description to `api/latex_resume.py`,
and files the result. Every house style rule (Times, no hyphens, three to five
bullets per role, two pages with every project) therefore applies here exactly
as it does in the Resume Tailor tab, because it is the same `build()` call.
Nothing bypasses it — and the compiled PDF must pass the house audit before it
is recorded against the job.

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


def _audit(pdf: Path, *, log: Callable[[str], None]) -> list[str]:
    """House-style failures in the compiled PDF; [] means it passes.

    An auditor that cannot run (pdfplumber missing, unreadable file) reports
    that as a failure rather than waving the document through — an unaudited
    resume is not a passing one."""
    try:
        from api import resume_audit
        return resume_audit.audit_pdf(pdf)
    except Exception as exc:
        log(f"[resume]   audit could not run: {type(exc).__name__}: {exc}")
        return [f"audit could not run: {type(exc).__name__}"]


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


def tailoring_settings() -> dict[str, Any]:
    """The user's tailoring mode and review preference, with sane fallbacks."""
    from . import store

    cfg = dict(store.get_setting("tailoring", {}) or {})
    return {
        "mode": (cfg.get("mode") or "honest").strip().lower(),
        "auto_approve": bool(cfg.get("auto_approve", True)),
        "profile": (cfg.get("profile") or "main").strip().lower(),
    }


def build_for_job(job: dict[str, Any], *, use_llm: bool = True,
                  mode: str | None = None, profile: str | None = None,
                  log: Callable[[str], None] = print) -> dict[str, Any]:
    """
    Tailor and compile a resume for one job. Never raises.

    Returns {ok, pdf, tex, version, pages, reason}. On any failure `ok` is False
    and `reason` says why, so the caller can record it against the job instead
    of dropping it.
    """
    from api import ats, behuman, latex_resume, resume_profiles

    result: dict[str, Any] = {"ok": False, "pdf": None, "tex": None,
                              "version": "", "pages": None, "reason": "",
                              "mode": "", "changes": [], "needsReview": False,
                              "profile": ""}
    title = job.get("title") or "role"
    company = job.get("company_name") or "?"

    profile_name = profile or tailoring_settings()["profile"]
    profile_path = resume_profiles.path_for(profile_name)
    result["profile"] = profile_name
    if not profile_path.is_file():
        result["reason"] = f"the '{profile_name}' profile is missing — nothing to tailor from."
        return result

    description = (job.get("description") or "").strip()
    jd_text = f"{title}\n\n{description}"

    try:
        content = latex_resume.from_profile(profile_path)
    except Exception as exc:
        result["reason"] = (f"could not read the '{profile_name}' profile: "
                            f"{type(exc).__name__}: {exc}")
        return result

    RESUME_DIR.mkdir(parents=True, exist_ok=True)
    stem = stem_for(job)

    try:
        if len(description) >= MIN_JD_CHARS:
            jd = ats.analyze_jd(jd_text)
            tailored = latex_resume.tailor(content, jd_text, jd, mode=mode,
                                           log=lambda m: log(f"[resume]   {m}"))
            result["changes"] = tailored.get("changes") or []
            result["needsReview"] = bool(tailored.get("needsReview"))
        else:
            log(f"[resume]   description is {len(description)} chars — "
                f"building the master resume rather than tailoring to a teaser")

        out = latex_resume.build(content, RESUME_DIR, stem,
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

    # ---- Hard gate: the house-style audit ---------------------------------
    # The auditor reads the compiled PDF the way an ATS parser will. A resume
    # that fails it is never recorded against the job — a bad document sent to
    # a real employer costs more than a missing one. First failure gets one
    # retry without the LLM (rewrites are the usual culprit); a second failure
    # is loud, and the retry queue picks it up later.
    fails = _audit(out["pdf"], log=log)
    if fails and use_llm:
        log(f"[resume]   audit failed ({fails[0]}) — rebuilding without the LLM rewrite")
        try:
            content = latex_resume.from_profile(profile_path)
            if len(description) >= MIN_JD_CHARS:
                latex_resume.tailor(content, jd_text, jd, use_llm=False,
                                    log=lambda m: log(f"[resume]   {m}"))
            out = latex_resume.build(content, RESUME_DIR, stem,
                                     log=lambda m: log(f"[resume]   {m}"))
            fails = _audit(out["pdf"], log=log) if out.get("pdf") else fails
            # The retry threw the rewrite away, so the change list from the
            # first attempt no longer describes the document being kept.
            result["changes"] = []
            result["mode"] = "off"
            result["needsReview"] = False
        except Exception as exc:
            result["reason"] = f"audit retry failed: {type(exc).__name__}: {str(exc)[:160]}"
            log(f"[resume] FAILED {company} — {title[:40]}: {result['reason']}")
            return result
    if fails:
        result["tex"] = out.get("tex")
        result["reason"] = "failed the house style audit: " + "; ".join(fails[:3])
        log(f"[resume] REJECTED {company} — {title[:40]}: {result['reason']}")
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
        f"({out.get('pages')} page(s), {result['behuman']})")
    return result


def build_and_record(job: dict[str, Any], *, use_llm: bool = True,
                     mode: str | None = None, profile: str | None = None,
                     log: Callable[[str], None] = print) -> dict[str, Any]:
    """Build, then write the path, version and review state onto the job.

    A resume is approved on the spot when the user has auto-approve on and the
    mode does not force review. Otherwise it is recorded unapproved, and the
    applier will not send it until someone has looked at the changes."""
    from . import store

    out = build_for_job(job, use_llm=use_llm, mode=mode, profile=profile, log=log)
    if out["ok"]:
        settings = tailoring_settings()
        approved = settings["auto_approve"] and not out.get("needsReview")
        # Nothing was rewritten, so there is nothing to review.
        if not out.get("changes"):
            approved = True
        store.set_job_resume(int(job["id"]), str(out["pdf"]), out["version"],
                             mode=out.get("mode"), changes=out.get("changes"),
                             approved=approved)
        out["approved"] = approved
        if not approved:
            log(f"[resume]   {len(out['changes'])} change(s) waiting for your review "
                f"before this one can be sent")
    return out


def rebuild_with_edits(job: dict[str, Any], edits: list[dict[str, Any]], *,
                       log: Callable[[str], None] = print) -> dict[str, Any]:
    """
    Recompile a resume with the user's edited bullets in place of the model's.

    Approving edited text without rebuilding would ship the PDF nobody read:
    the file on disk still carries the model's wording, and the edit would live
    only in the review screen. So the edits are applied to the content, the
    document is recompiled, and it goes through the same house-style audit as
    any other build.
    """
    from api import latex_resume, resume_style

    result: dict[str, Any] = {"ok": False, "reason": "", "pdf": None}
    replacements = {
        (c.get("revised") or "").strip(): (c.get("edited") or "").strip()
        for c in edits
        if (c.get("edited") or "").strip() and c.get("edited") != c.get("revised")
    }
    if not replacements:
        result.update({"ok": True, "reason": "nothing was edited"})
        return result

    # An edit is the user's own words, so it is not fact-checked — but it still
    # has to survive the house style, because the audit gate will reject the
    # PDF otherwise and they would be left with no resume at all.
    for text in replacements.values():
        problems = resume_style.lint(resume_style.enforce(text))
        if problems:
            result["reason"] = f"that edit breaks the house style: {problems[0]}"
            return result

    try:
        content = latex_resume.from_profile()
        description = (job.get("description") or "").strip()
        if len(description) >= MIN_JD_CHARS:
            from api import ats

            jd_text = f"{job.get('title') or 'role'}\n\n{description}"
            latex_resume.tailor(content, jd_text, ats.analyze_jd(jd_text),
                                mode="off", log=lambda m: log(f"[resume]   {m}"))

        applied = 0
        for block in content.experience + content.projects:
            for b in block.bullets:
                for original, edited in replacements.items():
                    # The stored change list pairs the model's wording with the
                    # user's; the document currently holds the model's.
                    if b.text.strip() in (original, edited):
                        b.text = edited
                        applied += 1
                        break
        for original, edited in replacements.items():
            if content.summary.strip() in (original, edited):
                content.summary = edited
                applied += 1

        out = latex_resume.build(content, RESUME_DIR, stem_for(job),
                                 log=lambda m: log(f"[resume]   {m}"))
    except Exception as exc:
        result["reason"] = f"{type(exc).__name__}: {str(exc)[:160]}"
        return result

    if not out.get("pdf"):
        result["reason"] = out.get("message") or "the rebuild produced no PDF"
        return result

    fails = _audit(out["pdf"], log=log)
    if fails:
        result["reason"] = "the edited resume fails the house style audit: " + fails[0]
        return result

    import hashlib

    digest = hashlib.sha1((out.get("texSource") or "").encode("utf-8")).hexdigest()[:8]
    from . import store

    store.set_job_resume(int(job["id"]), str(out["pdf"]),
                         f"{stem_for(job)}-{digest}",
                         mode=job.get("resume_mode") or "edited",
                         changes=edits, approved=True)
    result.update({"ok": True, "pdf": out["pdf"], "applied": applied})
    log(f"[resume]   rebuilt with {applied} edited line(s)")
    return result
