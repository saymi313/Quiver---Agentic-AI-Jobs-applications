"""
Telling the user a strong match appeared.

The point of watching boards on a schedule is to be first, and being first means
hearing about a role within a scan cycle of it being found — not the next time
someone happens to open the dashboard. Two channels do that, and they are kept
independent so one being off never silences the other:

  * Email, here. It arrives whether or not anything is open, which is the whole
    reason a scheduled run has to reach out rather than wait to be looked at. It
    goes over the same Gmail credentials the outreach and inbox already use, and
    a role is emailed exactly once — `notified_at` is stamped as it goes.

  * Desktop, in the browser. That lives in the frontend, keyed off what the
    client last saw, so it never competes with this for the "already told them"
    flag.
"""

from __future__ import annotations

from typing import Any, Callable

from . import store


def _fmt(job: dict[str, Any]) -> str:
    score = round(job.get("fit_score") or 0)
    company = job.get("company_name") or "Unknown company"
    where = job.get("location") or ("Remote" if job.get("remote") else "")
    line = f"  {score:>3}  {job.get('title', 'Untitled role')} — {company}"
    return f"{line}\n       {where}\n       {job.get('url', '')}" if where else f"{line}\n       {job.get('url', '')}"


def notify_new_matches(*, log: Callable[[str], None] = print) -> dict[str, Any]:
    """
    Email the strong matches found since the last time, once each.

    Reads the notify settings, does nothing unless email is on, and never raises
    — a discovery run must not fail because the mail server hiccuped.
    """
    settings = store.get_setting("notify", {}) or {}
    if not settings.get("enabled", True) or not settings.get("email"):
        return {"emailed": 0, "reason": "email notifications off"}

    min_score = float(settings.get("min_score", 75))
    matches = store.unnotified_matches(min_score=min_score, limit=25)
    if not matches:
        return {"emailed": 0, "reason": "nothing new above the bar"}

    from . import outreach  # reuses the SMTP sender and credentials

    user, password = outreach.credentials()
    if not user or not password or "xxxx" in (password or "").lower():
        # No mail set up: leave the roles unmarked so the desktop channel, or a
        # later run once mail is configured, can still announce them.
        log("[notify] email notifications are on but GMAIL_* are not set — skipping")
        return {"emailed": 0, "reason": "no mail credentials"}

    subject = (f"{len(matches)} new match{'es' if len(matches) != 1 else ''} — "
               f"top {round(matches[0].get('fit_score') or 0)}")
    body = ("Quiver found roles that scored at or above your "
            f"{round(min_score)} threshold:\n\n"
            + "\n\n".join(_fmt(j) for j in matches)
            + "\n\nOpen the dashboard to review or apply.")

    try:
        with outreach.Mailer(user, password) as mailer:
            mailer.send(user, subject, body, None)  # to yourself
    except Exception as exc:
        log(f"[notify] could not send the match email: {type(exc).__name__}: {exc}")
        return {"emailed": 0, "reason": str(exc)}

    store.mark_notified([j["id"] for j in matches])
    log(f"[notify] emailed {len(matches)} new match(es) to {user}")
    return {"emailed": len(matches)}
