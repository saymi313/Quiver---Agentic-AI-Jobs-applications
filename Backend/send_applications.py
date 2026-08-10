"""
Automated Cold-Email Sender
---------------------------
Reads companies_dataset.csv (produced by prospecting_pipeline.py) and sends
a personalised cold email to each pending company:

    1. Picks the best template for the vertical (email_templates.py).
    2. Renders placeholders from the CSV row.
    3. Attaches the correct resume PDF per vertical.
    4. Sends via Gmail SMTP using an App Password (stdlib only - no deps).
    5. Throttles sending (default: 60s between emails, 30 emails / day).
    6. Writes the outcome back into the CSV ('Application Status' column:
       Applied / Failed / Skipped) and appends a JSON line to send_log.jsonl.
    7. Idempotent: rerun-safe - rows already 'Applied' are skipped.

USAGE
=====
    # 0) One-time: create a Gmail App Password
    #    https://myaccount.google.com/apppasswords  (requires 2FA enabled)
    #
    # 1) Set env vars (or use the .env file loaded automatically below)
    #        GMAIL_ADDRESS   = saeed.usairam@gmail.com
    #        GMAIL_APP_PASS  = xxxx xxxx xxxx xxxx
    #
    # 2) Preview what would be sent (no email leaves your machine)
    #        python send_applications.py --dry-run
    #
    # 3) Send a small batch to test deliverability
    #        python send_applications.py --limit 3 --to-self
    #
    # 4) Real run (respect Gmail daily limits)
    #        python send_applications.py --limit 30 --delay 60
    #
    # 5) Resume next day (already-Applied rows are skipped automatically)
    #        python send_applications.py --limit 30 --delay 60

IMPORTANT - GMAIL LIMITS
========================
    * Free Gmail:     ~500 messages / rolling 24h
    * Google Workspace: ~2000 messages / rolling 24h
    * To avoid spam flags, send 20-40/day with a 60-90s gap and warm up
      a fresh account gradually over 2-3 weeks.
"""

import argparse
import csv
import json
import os
import smtplib
import ssl
import sys
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

from email_templates import (
    CANDIDATE_EMAIL,
    pick_template_for_vertical,
    render,
)


BASE_DIR = Path(__file__).parent
CSV_FILE = BASE_DIR / "companies_dataset.csv"
LOG_FILE = BASE_DIR / "send_log.jsonl"
ENV_FILE = BASE_DIR / ".env"

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465  # SSL

# Do not re-send until you set "Application Status" back to "Pending" (e.g. after fixing email).
SENT_STATUSES = {"Applied", "Interview", "Offer", "Failed"}
TERMINAL_FAIL_STATUSES = {"Rejected"}              # respect rejections


# ---------------------------------------------------------------------------
# CONFIG LOADING
# ---------------------------------------------------------------------------

def load_env_file():
    """Delegates to the one shared loader in agent/env.py."""
    from agent import env

    env.load()


# ---------------------------------------------------------------------------
# EMAIL CONSTRUCTION
# ---------------------------------------------------------------------------

def pick_target_email(row):
    """
    Choose the most relevant address for each company. Priority:
        Apply Email (careers/apply) > HR Email > Info Email.
    Guessed hr@ was often wrong; careers@ / public apply inboxes are preferred.
    """
    for key in ("Apply Email", "HR Email", "Info Email"):
        email = (row.get(key) or "").strip()
        if email and "@" in email:
            return email, key
    return "", ""


def build_context(row):
    """Build the placeholder dict fed into email_templates.render()."""
    return {
        "Company":              row.get("Organization Name", ""),
        "Vertical":             row.get("Vertical", ""),
        "OneLineAboutCompany":  row.get("Notes", ""),
        "CustomRequirement":    row.get("Custom Requirement", ""),
        "HiringManager":        "Hiring Team",
    }


def pick_resume_path(row):
    """
    Prefer a tailored per-row PDF when the CSV names one, else the static
    'Resume to Send'. 'Generated Resume' is a repo-relative path.
    """
    for key in ("Generated Resume", "Tailored PDF"):
        p = (row.get(key) or "").strip()
        if p:
            path = (BASE_DIR / p).resolve()
            if path.is_file():
                return path, p, key
    resume_file = (row.get("Resume to Send") or "").strip()
    if resume_file:
        path = (BASE_DIR / resume_file).resolve()
        if path.is_file():
            return path, resume_file, "Resume to Send"
    return None, "", ""


def build_message(row, sender, resume_path):
    """Return a ready-to-send EmailMessage with the right resume attached."""
    template = pick_template_for_vertical(row.get("Vertical", ""))
    subject, body = render(template, build_context(row))

    to_email, _ = pick_target_email(row)

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to_email
    msg["Reply-To"] = CANDIDATE_EMAIL
    msg["Subject"] = subject
    msg.set_content(body)

    if resume_path and resume_path.exists():
        with open(resume_path, "rb") as fh:
            msg.add_attachment(
                fh.read(),
                maintype="application",
                subtype="pdf",
                filename=resume_path.name,
            )
    return msg, template["id"], to_email


# ---------------------------------------------------------------------------
# SMTP TRANSPORT
# ---------------------------------------------------------------------------

class Mailer:
    """Persistent SMTP-over-SSL connection to smtp.gmail.com."""

    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.server = None

    def __enter__(self):
        context = ssl.create_default_context()
        self.server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context, timeout=30)
        self.server.login(self.username, self.password)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if self.server is not None:
                self.server.quit()
        except Exception:
            pass

    def send(self, msg):
        self.server.send_message(msg)


# ---------------------------------------------------------------------------
# CSV READ / WRITE (preserves ordering + all columns)
# ---------------------------------------------------------------------------

def read_csv():
    if not CSV_FILE.exists():
        print(f"[ERROR] {CSV_FILE.name} not found. Run prospecting_pipeline.py first.")
        sys.exit(1)
    with open(CSV_FILE, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)


def write_csv(fieldnames, rows):
    with open(CSV_FILE, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def append_log(entry):
    """Atomic JSONL append - one line per send attempt."""
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# DRIVER
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(description="Automated cold-email sender")
    parser.add_argument("--dry-run", action="store_true",
                        help="Render and preview emails but do NOT send.")
    parser.add_argument("--limit", type=int, default=30,
                        help="Max emails to send in this run (default: 30).")
    parser.add_argument("--delay", type=int, default=60,
                        help="Seconds to wait between sends (default: 60).")
    parser.add_argument("--to-self", action="store_true",
                        help="Redirect every email to CANDIDATE_EMAIL - safe test mode.")
    parser.add_argument("--vertical", default=None,
                        help="Only send to rows in this vertical (exact match).")
    return parser.parse_args()


def should_skip(row):
    """Return a reason-to-skip string, or '' if the row is eligible."""
    status = (row.get("Application Status") or "").strip()
    if status in SENT_STATUSES:
        return f"already '{status}'"
    if status in TERMINAL_FAIL_STATUSES:
        return f"status is '{status}'"
    to_email, _ = pick_target_email(row)
    if not to_email:
        return "no target email"
    return ""


def main():
    args = parse_args()
    load_env_file()

    gmail_user = os.environ.get("GMAIL_ADDRESS")
    gmail_pass = os.environ.get("GMAIL_APP_PASS")

    if not args.dry_run:
        if not gmail_user or not gmail_pass:
            print("[ERROR] GMAIL_ADDRESS and GMAIL_APP_PASS must be set "
                  "(either in .env or as env vars).")
            sys.exit(1)

    fieldnames, rows = read_csv()

    if "Application Status" not in fieldnames:
        print("[ERROR] CSV is missing 'Application Status' column.")
        sys.exit(1)

    sent_count = 0
    skipped_count = 0
    failed_count = 0

    print(f"[INFO] Loaded {len(rows)} rows. Dry-run={args.dry_run}, "
          f"limit={args.limit}, delay={args.delay}s, to_self={args.to_self}")

    mailer_ctx = Mailer(gmail_user, gmail_pass) if not args.dry_run else None

    try:
        mailer = mailer_ctx.__enter__() if mailer_ctx else None

        for idx, row in enumerate(rows, start=1):
            if sent_count >= args.limit:
                break

            if args.vertical and row.get("Vertical") != args.vertical:
                continue

            skip_reason = should_skip(row)
            if skip_reason:
                skipped_count += 1
                print(f"  [SKIP] ({idx}) {row.get('Organization Name'):<30} - {skip_reason}")
                continue

            resume_path, resume_ref, resume_source = pick_resume_path(row)
            if not resume_path or not resume_path.is_file():
                skipped_count += 1
                print(
                    f"  [SKIP] ({idx}) {row.get('Organization Name'):<30} - "
                    f"resume file not found (Generated Resume / Resume to Send)"
                )
                continue

            sender = gmail_user or CANDIDATE_EMAIL
            msg, template_id, to_email = build_message(row, sender, resume_path)

            if args.to_self:
                msg.replace_header("To", CANDIDATE_EMAIL)
                to_email = CANDIDATE_EMAIL

            company = row.get("Organization Name", "")
            vertical = row.get("Vertical", "")
            label = f"{company[:28]:<28} [{vertical[:18]:<18}] via {template_id}"

            if args.dry_run:
                print(f"  [DRY ] ({idx}) {label} -> {to_email}")
                print(f"         Subject: {msg['Subject']}")
                print(
                    f"         Resume:  {resume_ref}  ({resume_source})"
                )
                sent_count += 1
                continue

            try:
                mailer.send(msg)
                row["Application Status"] = "Applied"
                sent_count += 1
                print(f"  [SENT] ({idx}) {label} -> {to_email}")
                append_log({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "company": company,
                    "vertical": vertical,
                    "to": to_email,
                    "template": template_id,
                    "resume": resume_ref,
                    "resume_source": resume_source,
                    "status": "Applied",
                })
                write_csv(fieldnames, rows)  # persist after every success
                if sent_count < args.limit:
                    time.sleep(args.delay)
            except Exception as exc:
                failed_count += 1
                print(f"  [FAIL] ({idx}) {label} -> {to_email}  ({exc})")
                append_log({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "company": company,
                    "vertical": vertical,
                    "to": to_email,
                    "template": template_id,
                    "resume": resume_ref,
                    "resume_source": resume_source,
                    "status": "Failed",
                    "error": str(exc),
                })
    finally:
        if mailer_ctx:
            mailer_ctx.__exit__(None, None, None)

    if not args.dry_run:
        write_csv(fieldnames, rows)

    print(
        f"\n[DONE] Sent={sent_count}  Skipped={skipped_count}  Failed={failed_count}\n"
        f"       CSV updated: {CSV_FILE.name}\n"
        f"       Log: {LOG_FILE.name}"
    )


if __name__ == "__main__":
    main()
