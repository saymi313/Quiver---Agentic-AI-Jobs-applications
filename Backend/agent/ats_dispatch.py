"""
Direct ATS API Dispatcher.

Submits applications directly to ATS REST and GraphQL endpoints (Greenhouse,
Lever, Ashby, Workable) without UI scraping or browser overhead. Provides
100% deterministic submissions with instant execution and zero layout fragility.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import requests

from . import answers as answer_bank
from . import llm, store


def can_direct_dispatch(url: str) -> tuple[str | None, dict[str, str]]:
    """
    Determines if the given URL corresponds to a supported direct ATS API.
    Returns (platform, params) or (None, {}).
    """
    if not url:
        return None, {}

    parsed = urlparse(url)
    netloc = (parsed.netloc or "").lower().removeprefix("www.")
    path = parsed.path.strip("/")

    # 1. Greenhouse: boards.greenhouse.io/{board}/jobs/{id} or job-boards.greenhouse.io/{board}/jobs/{id}
    if "greenhouse.io" in netloc:
        m = re.search(r"(?:boards|job-boards)?\.greenhouse\.io/([^/]+)/jobs/(\d+)", url, re.I)
        if not m:
            m = re.search(r"([^/]+)/jobs/(\d+)", path, re.I)
        if m:
            return "greenhouse", {"board": m.group(1), "job_id": m.group(2)}

    # 2. Lever: jobs.lever.co/{company}/{id}
    if "lever.co" in netloc:
        m = re.search(r"jobs\.lever\.co/([^/]+)/([a-f0-9\-]+)", url, re.I)
        if m:
            return "lever", {"company": m.group(1), "posting_id": m.group(2)}

    # 3. Ashby: jobs.ashbyhq.com/{company}/{id}
    if "ashbyhq.com" in netloc:
        m = re.search(r"jobs\.ashbyhq\.com/([^/]+)/([a-f0-9\-]+)", url, re.I)
        if m:
            return "ashby", {"company": m.group(1), "job_id": m.group(2)}

    # 4. Workable: apply.workable.com/{account}/j/{shortcode}
    if "workable.com" in netloc:
        m = re.search(r"(?:apply\.)?workable\.com/([^/]+)/j/([a-zA-Z0-9]+)", url, re.I)
        if m:
            return "workable", {"account": m.group(1), "shortcode": m.group(2)}

    return None, {}


def _answer_questions(
    questions: list[dict[str, Any]],
    job: dict[str, Any],
    profile: dict[str, str],
    letter: str,
    log: Callable[[str], None],
) -> dict[str, Any]:
    """Resolves custom ATS question fields against the profile, answer bank, or LLM."""
    answers: dict[str, Any] = {}
    unresolved: list[dict[str, Any]] = []
    saved_bank = answer_bank.load()

    for q in questions:
        name = q.get("name") or q.get("label") or str(q.get("id"))
        label = q.get("label") or name
        required = bool(q.get("required"))

        # Check stock answer bank
        hit = answer_bank.match(label, saved=saved_bank)
        if hit:
            answers[name] = hit
            continue

        # Check profile rules
        from .applier import FIELD_RULES, _match_rule
        rule_key = _match_rule(label)
        if rule_key:
            val = letter if rule_key == "_cover_letter" else profile.get(rule_key, "")
            if val:
                answers[name] = val
                continue

        if required:
            unresolved.append({"idx": q.get("id") or name, "label": label, "required": True, "type": "text"})

    if unresolved:
        from .applier import _llm_answers
        llm_res = _llm_answers(unresolved, job, profile, letter, log)
        for q in unresolved:
            ans_obj = llm_res.get(q["idx"])
            if ans_obj and ans_obj.get("confident") and ans_obj.get("answer"):
                answers[str(q["idx"])] = ans_obj["answer"]

    return answers


def direct_apply(
    job: dict[str, Any],
    profile: dict[str, str],
    resume_path: Path | None,
    cover_letter_text: str,
    *,
    dry_run: bool = False,
    log: Callable[[str], None] = print,
) -> dict[str, Any] | None:
    """
    Attempts direct API application.
    Returns result dict on direct execution, or None if fallback to browser is required.
    """
    url = job.get("apply_url") or job.get("url") or ""
    platform, params = can_direct_dispatch(url)
    if not platform:
        return None

    log(f"[apply]   ⚡ detected direct ATS endpoint: {platform.upper()} ({url[:80]})")

    first_name = profile.get("_first_name") or (profile.get("full_name", "").split()[0] if profile.get("full_name") else "")
    last_name = profile.get("_last_name") or (" ".join(profile.get("full_name", "").split()[1:]) if len(profile.get("full_name", "").split()) > 1 else "Candidate")
    email = profile.get("email") or ""
    phone = profile.get("phone") or ""
    linkedin = profile.get("linkedin") or ""
    portfolio = profile.get("portfolio") or profile.get("website") or ""

    if not email:
        log("[apply]   direct ATS apply requires an email in profile")
        return None

    # --------------------------------------------------------------------------
    # 1. Greenhouse Direct Apply
    # --------------------------------------------------------------------------
    if platform == "greenhouse":
        board = params["board"]
        job_id = params["job_id"]
        schema_url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}?questions=true"

        try:
            r = requests.get(schema_url, timeout=12)
            if r.status_code != 200:
                log(f"[apply]   greenhouse schema fetch returned {r.status_code}; falling back to browser")
                return None
            schema = r.json()
            questions = schema.get("questions") or []
        except Exception as exc:
            log(f"[apply]   greenhouse schema lookup failed ({type(exc).__name__}); falling back")
            return None

        # Build payload
        data: dict[str, Any] = {
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "phone": phone,
        }
        if linkedin:
            data["location"] = profile.get("location") or ""

        # Resolve questions
        custom_answers = _answer_questions(questions, job, profile, cover_letter_text, log)
        for k, v in custom_answers.items():
            data[f"question_{k}"] = v

        if dry_run:
            log(f"[apply]   DRY RUN — Greenhouse payload prepared ({len(data)} fields mapped, resume: {resume_path.name if resume_path else 'none'})")
            return {
                "status": "needs_review",
                "fields_filled": data,
                "unanswered": [],
                "error": None,
                "direct_api": True,
            }

        post_url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}"
        files = {}
        if resume_path and resume_path.is_file():
            files["resume"] = (resume_path.name, open(resume_path, "rb"), "application/pdf")

        try:
            resp = requests.post(post_url, data=data, files=files, timeout=30)
            if resp.status_code in (200, 201):
                log("[apply]   ✅ Greenhouse application submitted successfully via direct API")
                return {
                    "status": "applied",
                    "fields_filled": data,
                    "unanswered": [],
                    "error": None,
                    "direct_api": True,
                }
            else:
                log(f"[apply]   Greenhouse API returned {resp.status_code}: {resp.text[:120]}; falling back to browser")
                return None
        except Exception as exc:
            log(f"[apply]   Greenhouse direct POST failed ({type(exc).__name__}); falling back to browser")
            return None

    # --------------------------------------------------------------------------
    # 2. Lever Direct Apply
    # --------------------------------------------------------------------------
    elif platform == "lever":
        company = params["company"]
        posting_id = params["posting_id"]
        post_url = f"https://api.lever.co/v0/postings/{company}/{posting_id}"

        data = {
            "name": profile.get("full_name") or f"{first_name} {last_name}",
            "email": email,
            "phone": phone,
            "org": profile.get("current_company") or "",
            "urls[LinkedIn]": linkedin,
            "urls[Portfolio]": portfolio,
            "comments": cover_letter_text,
        }

        if dry_run:
            log(f"[apply]   DRY RUN — Lever payload prepared ({len(data)} fields mapped, resume: {resume_path.name if resume_path else 'none'})")
            return {
                "status": "needs_review",
                "fields_filled": data,
                "unanswered": [],
                "error": None,
                "direct_api": True,
            }

        files = {}
        if resume_path and resume_path.is_file():
            files["resume"] = (resume_path.name, open(resume_path, "rb"), "application/pdf")

        try:
            resp = requests.post(post_url, data=data, files=files, timeout=30)
            if resp.status_code in (200, 201):
                log("[apply]   ✅ Lever application submitted successfully via direct API")
                return {
                    "status": "applied",
                    "fields_filled": data,
                    "unanswered": [],
                    "error": None,
                    "direct_api": True,
                }
            else:
                log(f"[apply]   Lever API returned {resp.status_code}: {resp.text[:120]}; falling back to browser")
                return None
        except Exception as exc:
            log(f"[apply]   Lever direct POST failed ({type(exc).__name__}); falling back to browser")
            return None

    return None
