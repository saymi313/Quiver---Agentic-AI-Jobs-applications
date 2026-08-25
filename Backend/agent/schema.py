"""
Shared schema for the agent's data, independent of where it is stored.

Both the SQLite and MongoDB backends import from here, so the field lists and
default settings exist in exactly one place and cannot drift apart.
"""

from __future__ import annotations

import json
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
    # The tailoring the resume went through, and whether a human has signed it
    # off. `resume_changes` is the before/after list the review screen shows.
    "resume_mode", "resume_changes", "resume_approved",
    # Auto Apply's review queue. The agent proposes; a human decides.
    "proposed_at", "proposal_reason", "proposal_decision",
    # The posting parsed into fields rather than left as prose: what a
    # keyword-aligned resume is aimed at, and what the feed filters on. Filled
    # by agent/jobmeta.py at scoring time. `skills` is a JSON list; `saved` is
    # the user's bookmark, which survives the retention purge.
    "salary_min", "salary_max", "salary_currency", "seniority",
    "work_arrangement", "skills", "deadline", "saved",
)

# What a human said about a proposal. `None` means undecided — the row is
# sitting in the queue waiting to be looked at.
PROPOSAL_DECISIONS = ("approved", "rejected")

# Rows written before the tracking columns existed simply do not carry them —
# MongoDB is schemaless and SQLite backfills NULL. Every read path runs through
# this so the API and the UI see one stable shape instead of guarding each key.
JOB_VIEW_DEFAULTS: dict[str, Any] = {
    "role_category": None, "recruiter_email": None, "recruiter_name": None,
    "description_source": None, "resume_path": None, "resume_version": None,
    "resume_built_at": None, "applied_at": None, "failure_reason": None,
    "resume_mode": None, "resume_changes": None, "resume_approved": None,
    "proposed_at": None, "proposal_reason": None, "proposal_decision": None,
    "salary_min": None, "salary_max": None, "salary_currency": None,
    "seniority": None, "work_arrangement": None, "deadline": None, "saved": 0,
}


def with_job_defaults(row: dict[str, Any]) -> dict[str, Any]:
    for key, value in JOB_VIEW_DEFAULTS.items():
        row.setdefault(key, value)
    row["has_resume"] = bool(row.get("resume_path"))
    # `skills` is stored as a JSON string on SQLite and as a list on Mongo.
    # Callers get a list either way, so the frontend never has to know which
    # backend answered.
    skills = row.get("skills")
    if isinstance(skills, str):
        try:
            row["skills"] = json.loads(skills) if skills.strip() else []
        except (ValueError, TypeError):
            row["skills"] = []
    elif skills is None:
        row["skills"] = []
    row["saved"] = bool(row.get("saved"))
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
    # Where this application sits in the hiring pipeline, and the thread that
    # moved it there. `tracker_status` is the user's view; `status` above is
    # the machine's record of the submission attempt itself.
    "tracker_status", "message_id", "last_message_at",
)

# --------------------------------------------------------------------------
# Application lifecycle
# --------------------------------------------------------------------------
#
# The submission attempt, as a state machine. Terminal means terminal: an
# application ends `submitted` or `failed` and nothing else, so a caller can
# stop polling on either without wondering whether a third outcome exists.
#
# `needs_review` is the state that previously had no name. A form the agent
# filled but could not honestly finish — an unanswerable required question, a
# login wall, a one-time code — was recorded as `failed`, which conflated "we
# tried and the site rejected it" with "we stopped and are waiting for you".

APPLICATION_STATUSES = ("queued", "running", "needs_review", "submitted", "failed")

APPLICATION_STATUS_HELP: dict[str, str] = {
    "queued": "Accepted, not started.",
    "running": "In progress.",
    "needs_review": "Paused. Answers are waiting on your decision.",
    "submitted": "Terminal, success. The form was accepted.",
    "failed": "Terminal. Nothing was submitted.",
}

TERMINAL_APPLICATION_STATUSES = ("submitted", "failed")

# Rows written before the state machine existed carry the old vocabulary.
LEGACY_APPLICATION_STATUS: dict[str, str] = {
    "pending": "queued",
    "filled": "needs_review",
    "skipped": "failed",
}

# --------------------------------------------------------------------------
# Pipeline tracking
# --------------------------------------------------------------------------
#
# Where an application has got to, from the candidate's point of view. This is
# the column the user edits by hand; the agent only advances it when it links a
# message to an application with high confidence, and never overrides a value
# the user set themselves.

TRACKER_STATUSES = ("applied", "interviewing", "offer", "rejected", "ghosted")

# What an incoming message *is*. Classified rules-first, because a phrase table
# answers the large majority for nothing and the LLM budget is small.
MESSAGE_CLASSES = (
    "acknowledgment", "interview", "assessment", "offer",
    "rejection", "reminder", "verification", "bounce", "other",
)

# A class maps to a pipeline stage only where the meaning is unambiguous. An
# assessment or a reminder says nothing certain about the stage, so it moves
# nothing.
CLASS_TO_TRACKER: dict[str, str] = {
    "interview": "interviewing",
    "assessment": "interviewing",
    "offer": "offer",
    "rejection": "rejected",
}

MESSAGE_FIELDS = (
    "application_id", "job_id", "company_id", "message_id", "thread_id",
    "from_addr", "from_domain", "subject", "snippet", "klass", "confidence",
    "received_at", "read_at", "linked_by",
    # The full message text (capped when fetched), so the inbox can show and
    # search whole messages rather than only the snippet it leads with.
    "body",
)

# Below this, a link is a guess: the message is stored for the user to read but
# moves nothing on its own.
LINK_CONFIDENCE_THRESHOLD = 0.75

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
        "locations": ["Remote", "Europe", "United Kingdom", "Germany", "Netherlands",
                      "Ireland", "United Arab Emirates", "Saudi Arabia", "Qatar", "Pakistan"],
        "keywords": ["react", "node", "typescript", "javascript", "mongodb", "full stack"],
        "min_fit_score": 55,
        "regions": ["eu", "uk", "me", "remote", "pk"],
        # Countries whose postings are filtered out even when they otherwise
        # match — the regions the user is not targeting. Pakistan is always kept,
        # and a purely-remote posting with no country is never excluded on this.
        "exclude_locations": ["India", "Bangladesh", "Sri Lanka", "Nepal", "Bhutan",
                              "United States", "USA", " US ", "U.S.", "Canada"],
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
    # Being told when a strong match appears, within one scan cycle of it being
    # found. Two independent channels: a desktop notification while the
    # dashboard is open, and an email that arrives even when it is not — the one
    # that matters for a scheduled run nobody is watching.
    "notify": {
        "enabled": True,
        "min_score": 75,
        "desktop": True,
        "email": False,
    },
    # What a manual "Find new jobs" run does. These used to live in the Jobs
    # screen's own React state, which meant the controls had to be on the same
    # page as the button. Storing them lets the button be pressed from anywhere
    # and lets the settings be edited somewhere they are not in the way.
    "search": {
        "sources": ["yc", "hn", "remote", "hidden"],
        "depth": 25,
        "scan_ats": True,
        "find_people": True,
    },
    # How far the model may go when rewriting the resume for a posting, and
    # whether the result needs a human's eyes before it can be used.
    #
    #   off         send the curated resume unchanged
    #   honest      reword using only what the profile already says
    #   aggressive  rewrite freely for keyword match; always needs review
    #
    # The fact gate applies in every mode: no rewrite may assert a number,
    # employer or technology the profile does not carry. The mode governs how
    # far the prose travels, never what it may claim.
    "tailoring": {
        "mode": "honest",
        "auto_approve": True,
        "review_form_before_submit": False,
    },
    # A single identity for the accounts the agent has to create on employer
    # sites that will not show the form until you register. The email lives here
    # (it is not a secret and forms ask for it directly); the password lives in
    # credentials.json alongside the per-site logins, never in this settings
    # store, because settings are dumped into API responses. Empty email falls
    # back to the profile email, so the common case needs no configuration.
    #
    # When a fresh account triggers an email confirmation link or a one-time
    # code, the agent does not guess: it parks the job as "input required" and
    # waits for you to hand back the code or the link.
    "signup": {
        "enabled": True,
        "email": "",
    },
    # Saved answers to the questions a profile cannot hold — "Are you open to
    # co-living?", "What's your favourite project?". Each is {match, answer}:
    # the agent reuses the answer wherever a form asks the same thing, so a
    # question answered by hand once never stops a run again. These fill only
    # where the truthful profile rules had nothing to say.
    "custom_answers": [],
    # Auto Apply, as a review queue rather than a free hand.
    #
    # Tsenta's version picks roles and submits them. Jobenzy's picks roles and
    # *proposes* them: a human approves the batch, and only then do those job
    # ids reach the applier. `agent_apply` still refuses to run without explicit
    # ids, so the guarantee is structural rather than a promise — no setting,
    # however misconfigured, can make the agent submit something nobody saw.
    #
    # Off by default. Turning it on is a decision, not a side effect.
    "auto_apply": {
        "enabled": False,
        # Only propose roles at least this good a match.
        "min_score": 70,
        # And no more than this many in a day, however many qualify.
        "daily_cap": 10,
        # Empty means "any category the targeting settings already allow".
        "categories": [],
        # Only propose roles whose tailored resume is built and signed off.
        "require_resume": True,
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
        # Reading the mailbox is cheap and the answer is time-sensitive: an
        # interview invitation sitting unseen for six hours is the one failure
        # mode this whole feature exists to prevent.
        "inbox_every_minutes": 20,
        "sources": ["yc", "hn", "remote", "hidden"],
        "discover_limit": 25,
        # Local hours [start, end) during which nothing fires.
        "quiet_hours": [1, 7],
    },
}


# The profile fields an application form asks for most, in the order a form
# usually asks them. Completeness is measured against these rather than every
# field, because a missing portfolio link never stops an application and a
# missing work authorization answer does.
PROFILE_IMPORTANT: tuple[tuple[str, str], ...] = (
    ("full_name", "Full name"),
    ("email", "Email"),
    ("phone", "Phone"),
    ("location", "Location"),
    ("current_title", "Current title"),
    ("years_experience", "Years of experience"),
    ("work_authorization", "Work authorisation"),
    ("linkedin", "LinkedIn"),
    ("highest_degree", "Highest degree"),
    ("university", "University"),
    ("default_resume", "Default resume"),
)


def profile_completeness(profile: dict[str, Any]) -> dict[str, Any]:
    """
    How ready the profile is to be poured into a form, and what is missing.

    A percentage over the commonly-required fields, plus the list of the ones
    still blank — the same "N% complete" a form-filler wants to see before it
    discovers a gap mid-application rather than the user discovering it there.
    """
    profile = profile or {}
    missing = [{"key": key, "label": label}
               for key, label in PROFILE_IMPORTANT
               if not str(profile.get(key) or "").strip()]
    total = len(PROFILE_IMPORTANT)
    filled = total - len(missing)
    return {
        "percent": round(filled / total * 100) if total else 100,
        "filled": filled,
        "total": total,
        "missing": missing,
    }


def merge_settings(stored: dict[str, Any]) -> dict[str, Any]:
    """Overlay whatever is stored on top of the defaults, key by key."""
    merged: dict[str, Any] = {}
    for key, default in DEFAULT_SETTINGS.items():
        value = stored.get(key, {})
        merged[key] = {**default, **value} if isinstance(default, dict) else stored.get(key, default)
    return merged
