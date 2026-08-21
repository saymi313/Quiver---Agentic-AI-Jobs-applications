"""Shared paths and settings for the dashboard API."""

from __future__ import annotations

from pathlib import Path

# Repo layout:  <root>/Backend/api/config.py  ->  BASE_DIR is <root>/Backend
BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent
FRONTEND_DIR = PROJECT_ROOT / "Frontend"

CSV_FILE = BASE_DIR / "companies_dataset.csv"
SEND_LOG = BASE_DIR / "send_log.jsonl"
CV_DATA = BASE_DIR / "cv_data"
OUTPUTS_DIR = BASE_DIR / "outputs"
DASHBOARD_OUT = OUTPUTS_DIR / "dashboard"
UPLOADS_DIR = DASHBOARD_OUT / "uploads"
DIST_DIR = FRONTEND_DIR / "dist"

for _d in (OUTPUTS_DIR, DASHBOARD_OUT, UPLOADS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # 15 MB
ALLOWED_RESUME_EXT = {".pdf", ".docx", ".txt", ".md"}

# Everything the dashboard is allowed to launch. Nothing else can be executed.
#
# The CSV pipeline is deliberately down to two entries — crawl and send. The
# Excel workbook, Sheets sync and one-off patch scripts were retired; applying
# is absent on purpose, because it only ever runs on job ids the user picked.
RUNNABLE = {
    "prospect": {
        "label": "Discover companies",
        "script": "prospecting_pipeline.py",
        "description": "Crawl every company site for careers / ATS / contact emails, then write companies_dataset.csv.",
        "flags": [],
    },
    "send": {
        "label": "Send applications",
        "script": "send_applications.py",
        "description": "Send personalised cold emails via Gmail SMTP and write results back to the CSV.",
        "flags": ["dry_run", "limit", "delay", "to_self", "vertical"],
    },
    # ---- Agent tasks (run as modules, not scripts) -------------------------
    "agent_discover": {
        "label": "Research startups",
        "module": "agent.runner",
        "subcommand": "discover",
        "description": "Scan Y Combinator, Hacker News 'Who is hiring', company career portals "
                       "and remote/EU job boards. Finds openings, founders and recruiter emails, "
                       "verifies each address, and scores every role against your resume.",
        "flags": ["sources", "limit", "no_people", "no_ats"],
    },
    "agent_apply": {
        "label": "Apply to selected jobs",
        "module": "agent.runner",
        "subcommand": "apply",
        "description": "Open the application form for each job you selected, fill every field "
                       "from your profile, upload that job's tailored resume, and submit. "
                       "Only ever runs on jobs you picked.",
        "flags": ["job_ids", "dry_run", "headed", "workers"],
    },
    "agent_resumes": {
        "label": "Generate tailored resumes",
        "module": "agent.runner",
        "subcommand": "resumes",
        "description": "Build a resume tailored to each selected job's description, using the "
                       "same engine and house style as the Resume Tailor tab.",
        "flags": ["job_ids"],
    },
    "agent_tasks": {
        "label": "Retry failed steps",
        "module": "agent.runner",
        "subcommand": "tasks",
        "description": "Work through the retry queue: job descriptions that would not load, "
                       "resume builds that errored, and email checks the mail server asked "
                       "us to retry later.",
        "flags": ["limit"],
    },
    "agent_inbox": {
        "label": "Read replies",
        "module": "agent.runner",
        "subcommand": "inbox",
        "description": "Read your mailbox, match each employer reply to the application it "
                       "belongs to, work out whether it is an interview, an assessment, an "
                       "offer or a rejection, and move the pipeline on.",
        "flags": ["limit", "max_age"],
    },
    "agent_outreach": {
        "label": "Cold email founders",
        "module": "agent.runner",
        "subcommand": "outreach",
        "description": "Research each verified contact, write an email personalised to what that "
                       "company actually does, and send it from your Gmail.",
        "flags": ["limit", "delay", "dry_run", "to_self", "no_attach"],
    },
}
