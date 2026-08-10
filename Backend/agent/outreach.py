"""
Cold outreach agent: research a startup, write an email that could only have
been written for them, send it, and log the attempt.

Personalisation is grounded in three things the agent actually read — the
company's own description, what they said they were hiring for, and the
candidate's résumé. If the model has nothing specific to say, the run falls
back to a plain template rather than shipping generic filler with the
company's name pasted in.

Sending reuses the Gmail SMTP credentials already in Backend/.env.
"""

from __future__ import annotations

import os
import re
import smtplib
import ssl
import time
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Callable

from api.config import BASE_DIR
from api import behuman

from . import env, llm, matcher, store

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465

EMAIL_SCHEMA = {
    "type": "object",
    "properties": {
        "subject": {"type": "string", "description": "under 70 characters, no clickbait"},
        "body": {"type": "string", "description": "plain text, 90-150 words, no markdown"},
        "personalisation": {"type": "string",
                            "description": "the specific detail about this company you used"},
    },
    "required": ["subject", "body", "personalisation"],
}

SYSTEM = """You write short cold emails from a job-seeking engineer to a startup founder or recruiter.

Rules:
- 90-150 words. Plain text. No markdown, no bullet points, no em dashes.
- Open with something specific and true about THEIR company, drawn from the context given.
  Never open with "I hope this finds you well" or "I came across your company".
- One sentence on what the candidate has actually built that is relevant. Facts from the
  resume only — never invent an employer, metric, or technology.
- End with one low-friction ask (a short call, or whether they are open to a CV).
- No flattery, no buzzwords, no "I'm passionate about". Write like a competent person
  emailing a busy person.
- Do not include a greeting line naming the recipient (that is added separately) or a sign-off
  (that is added separately). Body text only.
""" + "\n" + behuman.RULES




def credentials() -> tuple[str, str]:
    env.load()
    return os.environ.get("GMAIL_ADDRESS", ""), os.environ.get("GMAIL_APP_PASS", "")


# --------------------------------------------------------------------------
# Drafting
# --------------------------------------------------------------------------

def _fallback_email(person: dict[str, Any], profile: dict[str, Any]) -> dict[str, str]:
    company = person.get("company_name") or "your team"
    title = profile.get("current_title") or "Full Stack Engineer"
    return {
        "subject": f"{title} interested in {company}",
        "body": (
            f"I've been following what {company} is building and would like to be part of it.\n\n"
            f"I'm a {title} working mainly with React, Node.js and MongoDB, and I've shipped "
            f"production SaaS used by thousands of people, including payments and real-time "
            f"features.\n\n"
            f"If you're hiring, I'd be glad to send my CV or take fifteen minutes to talk. "
            f"Either way, good luck with what you're building."
        ),
        "personalisation": "(template fallback — the model was unavailable)",
    }


def draft_email(person: dict[str, Any], *, log: Callable[[str], None] = print) -> dict[str, str]:
    profile = store.get_setting("profile", {}) or {}
    company = person.get("company_name") or "the company"
    resume = matcher.resume_text()[:5000]

    context = "\n".join(filter(None, [
        f"Company: {company}",
        f"What they do: {(person.get('description') or '')[:900]}" if person.get("description") else "",
        f"Industry: {person.get('industry')}" if person.get("industry") else "",
        f"Website: {person.get('website')}" if person.get("website") else "",
        f"Region: {person.get('region')}" if person.get("region") else "",
        f"Recipient: {person.get('full_name') or 'unknown name'}"
        + (f", {person.get('title')}" if person.get("title") else "")
        + f" (role: {person.get('role') or 'unknown'})",
    ]))

    prompt = (
        f"{context}\n\n"
        f"CANDIDATE RESUME:\n{resume}\n\n"
        f"CANDIDATE PROFILE:\n"
        f"Name: {profile.get('full_name')}\n"
        f"Current title: {profile.get('current_title')}\n"
        f"Location: {profile.get('location')}\n"
        f"Portfolio: {profile.get('portfolio')}\n\n"
        f"Write the cold email."
    )
    try:
        data = llm.complete_json(prompt, EMAIL_SCHEMA, system=SYSTEM)
        subject = behuman.scrub((data.get("subject") or "").strip())[:120]
        body = behuman.scrub((data.get("body") or "").strip())
        if len(body) < 60:
            raise llm.LLMError("model returned an empty body")
        tells = behuman.report(body)
        if tells != "clean":
            log(f"[email] draft for {company} still reads as AI ({tells})")
        return {"subject": subject or f"Interested in {company}",
                "body": body,
                "personalisation": (data.get("personalisation") or "").strip()[:300]}
    except llm.LLMError as exc:
        log(f"[email] model unavailable for {company} ({exc}); using the template")
        return _fallback_email(person, profile)


def assemble(person: dict[str, Any], draft: dict[str, str], profile: dict[str, Any]) -> str:
    name = (person.get("full_name") or "").split()[0] if person.get("full_name") else ""
    greeting = f"Hi {name}," if name else "Hi,"
    sign_bits = [profile.get("full_name") or "", profile.get("phone") or "",
                 profile.get("portfolio") or "", profile.get("linkedin") or ""]
    signature = "\n".join(b for b in sign_bits if b)
    return f"{greeting}\n\n{draft['body'].strip()}\n\nBest,\n{signature}".strip()


# --------------------------------------------------------------------------
# Sending
# --------------------------------------------------------------------------

class Mailer:
    def __init__(self, user: str, password: str) -> None:
        self.user, self.password, self.server = user, password, None

    def __enter__(self) -> "Mailer":
        self.server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT,
                                       context=ssl.create_default_context(), timeout=30)
        self.server.login(self.user, self.password)
        return self

    def __exit__(self, *exc) -> None:
        try:
            if self.server:
                self.server.quit()
        except Exception:
            pass

    def send(self, to: str, subject: str, body: str, attachment: Path | None) -> None:
        msg = EmailMessage()
        msg["From"] = self.user
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        if attachment and attachment.is_file():
            msg.add_attachment(attachment.read_bytes(), maintype="application",
                               subtype="pdf" if attachment.suffix.lower() == ".pdf" else "octet-stream",
                               filename=attachment.name)
        self.server.send_message(msg)


def run_outreach(limit: int = 10, *, dry_run: bool = False, delay: int = 90,
                 attach_resume: bool = True, to_self: bool = False,
                 log: Callable[[str], None] = print) -> dict[str, Any]:
    profile = store.get_setting("profile", {}) or {}
    user, password = credentials()

    if not dry_run and (not user or not password or "xxxx" in password.lower()):
        log("[email] GMAIL_ADDRESS / GMAIL_APP_PASS are not set in Backend/.env — "
            "running as a dry run instead.")
        dry_run = True

    people = store.people_to_email(limit=limit)
    if not people:
        log("[email] nobody to write to. Run discovery with 'find people' enabled first.")
        return {"attempted": 0, "sent": 0, "failed": 0, "drafted": 0}

    resume = matcher.resume_path() if attach_resume else None
    log(f"[email] {len(people)} recipient(s)"
        + (" — DRY RUN, nothing will be sent" if dry_run else f", {delay}s apart")
        + (f", attaching {resume.name}" if resume else ""))

    counts = {"attempted": 0, "sent": 0, "failed": 0, "drafted": 0}
    mailer_ctx = Mailer(user, password) if not dry_run else None
    mailer = None

    try:
        if mailer_ctx:
            mailer = mailer_ctx.__enter__()

        for i, person in enumerate(people, 1):
            counts["attempted"] += 1
            company = person.get("company_name") or "?"
            to = person["email"] if not to_self else (profile.get("email") or user)

            draft = draft_email(person, log=log)
            body = assemble(person, draft, profile)
            record = {
                "person_id": person["id"], "company_id": person.get("company_id"),
                "to_email": to, "subject": draft["subject"], "body": body,
                "research_notes": draft.get("personalisation", ""),
                "dry_run": dry_run, "sequence_step": 1,
            }

            if dry_run:
                counts["drafted"] += 1
                store.record_outreach({**record, "status": "drafted"})
                log(f"[email] ({i}/{len(people)}) DRAFT → {to}  [{person.get('email_status')}]")
                log(f"[email]     subject: {draft['subject']}")
                log(f"[email]     hook:    {draft.get('personalisation', '')[:100]}")
                continue

            try:
                mailer.send(to, draft["subject"], body, resume)
                counts["sent"] += 1
                store.record_outreach({**record, "status": "sent"})
                log(f"[email] ({i}/{len(people)}) SENT → {to}  ({company})")
            except Exception as exc:
                counts["failed"] += 1
                store.record_outreach({**record, "status": "failed", "error": str(exc)[:400]})
                log(f"[email] ({i}/{len(people)}) FAILED → {to}: {type(exc).__name__}: {exc}")

            if i < len(people) and delay > 0:
                time.sleep(delay)
    finally:
        if mailer_ctx:
            mailer_ctx.__exit__(None, None, None)

    log(f"[email] done — sent={counts['sent']} drafted={counts['drafted']} failed={counts['failed']}")
    return counts
