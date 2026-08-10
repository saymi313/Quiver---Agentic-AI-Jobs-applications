"""
Shared schema for the agent's data, independent of where it is stored.

Both the SQLite and MongoDB backends import from here, so the field lists and
default settings exist in exactly one place and cannot drift apart.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def now() -> str:
    """Timestamps are ISO-8601 UTC strings everywhere, in both backends."""
    return datetime.now(timezone.utc).isoformat()


COMPANY_FIELDS = (
    "name", "domain", "website", "source", "source_ref", "description", "industry",
    "location", "region", "team_size", "founded", "ats_platform", "ats_token",
    "careers_url", "tags",
)

JOB_FIELDS = (
    "company_id", "external_id", "title", "location", "remote", "url", "apply_url",
    "description", "department", "employment_type", "source", "posted_at",
    "posted_ts", "dedupe_hash",
    # Tracking columns. `role_category` is a slug from agent/categories.py;
    # `recruiter_email` stays empty unless a real address was found and verified.
    "role_category", "recruiter_email", "recruiter_name", "description_source",
    "resume_path", "resume_version", "resume_built_at", "applied_at", "failure_reason",
)

# Rows written before the tracking columns existed simply do not carry them —
# MongoDB is schemaless and SQLite backfills NULL. Every read path runs through
# this so the API and the UI see one stable shape instead of guarding each key.
JOB_VIEW_DEFAULTS: dict[str, Any] = {
    "role_category": None, "recruiter_email": None, "recruiter_name": None,
    "description_source": None, "resume_path": None, "resume_version": None,
    "resume_built_at": None, "applied_at": None, "failure_reason": None,
}


def with_job_defaults(row: dict[str, Any]) -> dict[str, Any]:
    for key, value in JOB_VIEW_DEFAULTS.items():
        row.setdefault(key, value)
    row["has_resume"] = bool(row.get("resume_path"))
    return row

# --------------------------------------------------------------------------
# Task queue
# --------------------------------------------------------------------------
#
# A task is one retryable unit of background work: fetch a JD that timed out,
# rebuild a resume whose LaTeX pass failed, re-verify a greylisted address.
# Failures used to be a log line and then silence; now they are rows that the
# `tasks` runner mode drains on its own cadence.
#
# `dedupe_key` makes enqueueing idempotent — discovering the same job twice
# must not queue its JD fetch twice.

TASK_FIELDS = (
    "kind", "payload", "status", "attempts", "max_attempts",
    "next_run_at", "last_error", "priority", "dedupe_key",
)

TASK_STATUSES = ("pending", "running", "done", "failed", "dead")

# Retry behaviour lives here as data, not scattered through call sites.
# `backoff_base_s` doubles per attempt: base, 2x, 4x...
RETRY_POLICIES: dict[str, dict[str, int]] = {
    "jd_fetch":              {"max_attempts": 3, "backoff_base_s": 600},
    "resume_build":          {"max_attempts": 3, "backoff_base_s": 900},
    "verify_email_greylist": {"max_attempts": 4, "backoff_base_s": 900},
}


def retry_policy(kind: str) -> dict[str, int]:
    return RETRY_POLICIES.get(kind, {"max_attempts": 3, "backoff_base_s": 600})


PERSON_FIELDS = (
    "company_id", "full_name", "role", "title", "email", "email_source",
    "email_status", "email_score", "verify_detail", "linkedin", "github",
)

APPLICATION_FIELDS = (
    "job_id", "company_id", "job_hash", "status", "resume_path", "cover_letter",
    "fields_filled", "unanswered", "screenshot", "error", "dry_run",
)

OUTREACH_FIELDS = (
    "person_id", "company_id", "to_email", "subject", "body", "research_notes",
    "status", "error", "dry_run", "sequence_step",
)

DEFAULT_SETTINGS: dict[str, Any] = {
    "profile": {
        "full_name": "",
        "email": "",
        "phone": "",
        "location": "",
        "linkedin": "",
        "github": "",
        "portfolio": "",
        "current_title": "",
        "current_company": "",
        "years_experience": "",
        "highest_degree": "",
        "university": "",
        "work_authorization": "",
        "requires_sponsorship": "No",
        "notice_period": "",
        "salary_expectation": "",
        "willing_to_relocate": "Yes",
        "pronouns": "",
        "how_did_you_hear": "Company website",
        "why_this_company": "",
        "default_resume": "",
    },
    "targeting": {
        # The ten role categories the agent searches. Anything outside them is
        # never tracked. Slugs come from agent/categories.py.
        "categories": ["backend", "frontend", "fullstack", "software_engineer",
                       "ai_engineer", "ai_software_engineer", "product_design",
                       "ui_ux", "ui_design", "ux_design"],
        "classify_with_llm": False,
        "titles": ["Full Stack Engineer", "Software Engineer", "Frontend Engineer",
                   "Backend Engineer", "React Developer"],
        "exclude_titles": ["Senior Staff", "Principal", "Director", "VP", "Manager",
                           "Head of", "Intern"],
        "locations": ["Remote", "Europe", "Pakistan"],
        "keywords": ["react", "node", "typescript", "javascript", "mongodb", "full stack"],
        "min_fit_score": 55,
        "regions": ["us", "eu", "remote", "pk"],
        # Freshness: applying to a week-old posting means joining hundreds of
        # applicants already in the pile.
        "max_age_days": 3,
        "require_posted_date": True,
        "apply_order": "recent",          # recent | fit
        # Experience window. max_years is the ceiling on what a posting may
        # DEMAND, not the candidate's own experience.
        "min_years_experience": 1,
        "max_years_experience": 3,
        "allow_internships": False,
    },
    "limits": {
        "max_applications_per_run": 10,
        "max_emails_per_run": 20,
        "email_delay_seconds": 90,
        "max_companies_per_source": 60,
        # A tailored resume costs an LLM call plus a LaTeX compile, so the run
        # builds them only for jobs that cleared every gate, and stops here.
        # The rest get a "Generate resume" button in the jobs table.
        "max_resumes_per_run": 10,
        # Housekeeping. A job discovered longer ago than this can no longer be
        # fresh, so it is deleted at the start of the next search along with its
        # tailored resume. Rows you actually applied to are never deleted —
        # losing your own application history is not housekeeping.
        "retention_days": 3,
        "purge_keeps_applied": True,
    },
    "llm": {
        "provider": "gemini",
        "model": "gemini-flash-latest",
        "api_key": "",
        "base_url": "",
        # Real provider calls allowed per day, across every purpose. Gemini's
        # free tier is 20 requests per day *per model*, and the fallback list
        # covers about three distinct models, so 60 is the honest ceiling.
        # See agent/llm.py for the per-purpose shares underneath it.
        "daily_budget": 60,
    },
    # The scheduler. Off by default: turning on unattended runs is a decision,
    # not a side effect of an upgrade. When on, it fires discovery and the
    # retry queue on their own cadences — applying is not schedulable at all.
    "schedule": {
        "enabled": False,
        "discover_every_hours": 6,
        "tasks_every_minutes": 30,
        "sources": ["yc", "hn", "remote", "hidden"],
        "discover_limit": 25,
        # Local hours [start, end) during which nothing fires.
        "quiet_hours": [1, 7],
    },
}


def merge_settings(stored: dict[str, Any]) -> dict[str, Any]:
    """Overlay whatever is stored on top of the defaults, key by key."""
    merged: dict[str, Any] = {}
    for key, default in DEFAULT_SETTINGS.items():
        value = stored.get(key, {})
        merged[key] = {**default, **value} if isinstance(default, dict) else stored.get(key, default)
    return merged
