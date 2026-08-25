"""
Jobenzy over MCP: the agent's own surface, for Claude Code and anything else
that speaks the protocol.

    claude mcp add jobenzy -- python -m agent.mcp_server

Local stdio, not hosted HTTP with OAuth. There is no account to authenticate
against: the server runs as you, on your machine, against the same database the
dashboard uses. A token would be ceremony around a trust boundary that does not
exist here.

The one rule this surface inherits from everything else: **no tool submits an
application.** `apply` hands job ids to the same `apply_to_ids` the dashboard
button uses, and that path already refuses to run without explicit ids — but an
assistant reading a job board should not be able to decide, on its own reading
of a conversation, to send your name to an employer. So applying is exposed as
`propose_applications`, which fills the review queue, and the actual submission
stays a thing you do.
"""

# Deliberately no `from __future__ import annotations`: FastMCP introspects
# each tool's real annotation objects to build its schema, and postponed
# evaluation hands it strings instead. Python 3.11 understands `list[int]`
# natively, so nothing is lost.
import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import portals, store

mcp = FastMCP("jobenzy")


def _ok(payload: Any) -> str:
    """Tools return text, and JSON is the most useful text for a caller."""
    return json.dumps(payload, indent=2, default=str)


def _job_brief(row: dict[str, Any]) -> dict[str, Any]:
    """The fields worth spending an assistant's context on."""
    return {
        "id": row.get("id"),
        "title": row.get("title"),
        "company": row.get("company_name"),
        "location": row.get("location"),
        "category": row.get("role_category"),
        "portal": row.get("source"),
        "score": round(row["fit_score"]) if row.get("fit_score") else None,
        "why": row.get("fit_reason"),
        "status": row.get("status"),
        "hasResume": bool(row.get("resume_path")),
        "resumeApproved": row.get("resume_approved"),
        "url": row.get("url"),
    }


# --------------------------------------------------------------------------
# Find
# --------------------------------------------------------------------------

@mcp.tool()
def list_jobs(status: str = "matched", category: str = "", portal: str = "",
              min_score: int = 0, query: str = "", limit: int = 25) -> str:
    """
    Tracked roles, newest and best-matching first.

    status: matched | new | applied | failed | skipped, or "" for everything.
    category: one of the ten role slugs, e.g. backend, ai_engineer, ui_ux.
    portal: greenhouse, ashby, lever, remoteok...
    min_score: 0 to 100.
    """
    store.init()
    rows = store.list_jobs(max(1, min(limit * 4, 400)), status or None,
                           category=category or None, source=portal or None,
                           q=query or None)
    if min_score:
        rows = [r for r in rows if (r.get("fit_score") or 0) >= min_score]
    rows.sort(key=lambda r: -(r.get("fit_score") or 0))
    return _ok({"count": len(rows[:limit]), "jobs": [_job_brief(r) for r in rows[:limit]]})


@mcp.tool()
def get_job(job_id: int) -> str:
    """One role in full, including its description."""
    store.init()
    row = store.job(job_id)
    if not row:
        return _ok({"error": f"No job {job_id}."})
    brief = _job_brief(row)
    brief["description"] = (row.get("description") or "")[:6000]
    brief["recruiter"] = row.get("recruiter_email")
    return _ok(brief)


@mcp.tool()
def track_job_url(url: str) -> str:
    """
    Track a job from its URL: read the posting, work out the role, score it.

    The same pipeline discovery uses, entered where the link is already known.
    Says so plainly when the posting is closed rather than storing a stub.
    """
    from agent import categories, jobdesc, matcher, sources

    store.init()
    if not url.lower().startswith(("http://", "https://")):
        return _ok({"error": "That does not look like a job URL."})

    existing = store.job_by_url(url)
    if existing:
        return _ok({"created": False, "job": _job_brief(existing),
                    "message": "Already tracked."})

    portal, _token = sources.portal_from_url(url)
    row: dict[str, Any] = {"url": url, "apply_url": url,
                           "source": portal or "manual", "title": "", "description": ""}
    text, origin = jobdesc.fetch_description(row, log=lambda _: None)
    if origin == "closed":
        return _ok({"created": False,
                    "error": "That posting is closed. Nothing was added."})
    if not text or jobdesc.LOOKS_LIKE_A_BOARD.search(text[:600]):
        return _ok({"created": False,
                    "error": "That link opens a board or a page that could not be read, "
                             "not a single posting."})

    title = jobdesc.fetch_page_title(url)
    if not title or jobdesc.LOOKS_LIKE_A_BOARD.search(title):
        title = jobdesc.guess_title(text, url)
    company = sources.company_from_url(url) or "Unknown"
    row.update({
        "description": text, "description_source": origin,
        "title": title or "Untitled role",
        "company_id": store.upsert_company({"name": company, "source": "manual",
                                            "domain": sources.domain_of(url)}),
        "role_category": categories.classify(title or "", text),
        "dedupe_hash": sources.dedupe_hash(company, title or "", "", url=url),
    })
    job_id = store.upsert_job(row, company_name=company)
    if not job_id:
        return _ok({"created": False, "error": "Could not store that job."})
    matcher.score_pending(limit=5, log=lambda _: None)
    return _ok({"created": True, "job": _job_brief(store.job(int(job_id)) or {})})


# --------------------------------------------------------------------------
# Prep
# --------------------------------------------------------------------------

@mcp.tool()
def build_resume(job_id: int, mode: str = "") -> str:
    """
    Tailor and compile a resume for one role.

    mode: off | honest | aggressive. Blank uses the saved setting. No mode may
    claim anything the profile does not carry — that gate is mechanical and
    applies identically to all three.
    """
    from . import tailor

    store.init()
    row = store.job(job_id)
    if not row:
        return _ok({"error": f"No job {job_id}."})
    out = tailor.build_and_record(row, mode=(mode or None), log=lambda _: None)
    return _ok({
        "ok": out["ok"], "reason": out.get("reason"), "mode": out.get("mode"),
        "pages": out.get("pages"), "version": out.get("version"),
        "changes": out.get("changes"), "approved": out.get("approved"),
        "resume": str(out["pdf"]) if out.get("pdf") else None,
    })


@mcp.tool()
def resume_changes(job_id: int) -> str:
    """What the rewrite changed for this role, and whether it is approved yet."""
    store.init()
    row = store.job(job_id)
    if not row:
        return _ok({"error": f"No job {job_id}."})
    raw = row.get("resume_changes")
    try:
        changes = json.loads(raw) if isinstance(raw, str) and raw.strip() else (raw or [])
    except json.JSONDecodeError:
        changes = []
    return _ok({"mode": row.get("resume_mode"), "approved": row.get("resume_approved"),
                "changes": changes})


@mcp.tool()
def approve_resume(job_id: int) -> str:
    """Sign off a tailored resume so it may be sent."""
    store.init()
    if not store.job(job_id):
        return _ok({"error": f"No job {job_id}."})
    store.approve_job_resume(job_id)
    return _ok({"ok": True, "id": job_id, "approved": True})


# --------------------------------------------------------------------------
# Apply — proposing only
# --------------------------------------------------------------------------

@mcp.tool()
def propose_applications(job_ids: list[int]) -> str:
    """
    Put roles in the review queue for the user to approve.

    This is as far as any assistant goes. Submitting an application is not
    exposed over MCP at all: it puts the user's name in front of an employer,
    and that decision stays theirs, made on the Jobs screen. The queue this
    fills is the same one Auto Apply uses.
    """
    store.init()
    queued: list[int] = []
    for job_id in job_ids:
        row = store.job(int(job_id))
        if not row:
            continue
        score = row.get("fit_score")
        store.propose_job(int(job_id),
                          f"proposed over MCP"
                          + (f" · scored {round(score)}" if score else ""))
        queued.append(int(job_id))
    return _ok({
        "queued": queued,
        "message": f"{len(queued)} role(s) are waiting for approval on the Jobs "
                   f"screen. Nothing has been submitted.",
    })


@mcp.tool()
def list_proposals() -> str:
    """Roles currently waiting for the user's approval."""
    store.init()
    return _ok({"waiting": [_job_brief(r) for r in store.proposals()]})


# --------------------------------------------------------------------------
# Track
# --------------------------------------------------------------------------

@mcp.tool()
def pipeline() -> str:
    """Where every application stands, and how many replies are unread."""
    store.init()
    rows = store.tracked_applications(200)
    return _ok({
        "counts": store.tracker_counts(),
        "unread": store.unread_count(),
        "applications": [{
            "id": r.get("id"), "title": r.get("title"), "company": r.get("company_name"),
            "stage": r.get("tracker_status"), "submittedAt": r.get("submitted_at"),
            "replies": r.get("message_count"), "lastReply": r.get("last_message_at"),
        } for r in rows[:50]],
    })


@mcp.tool()
def read_inbox(klass: str = "", unread_only: bool = False, limit: int = 20) -> str:
    """
    Employer replies, matched to the applications they belong to.

    klass: interview | assessment | offer | rejection | acknowledgment |
    reminder | verification | bounce | other.
    """
    store.init()
    rows = store.list_messages(max(1, min(limit, 100)),
                               klass=klass or None, unread_only=unread_only)
    return _ok({
        "unread": store.unread_count(),
        "messages": [{
            "id": r.get("id"), "kind": r.get("klass"), "subject": r.get("subject"),
            "from": r.get("from_addr"), "company": r.get("company_name"),
            "receivedAt": r.get("received_at"), "read": bool(r.get("read_at")),
            "snippet": (r.get("snippet") or "")[:300],
            "linkedTo": r.get("application_id"),
        } for r in rows],
    })


@mcp.tool()
def set_stage(application_id: int, stage: str) -> str:
    """Move an application by hand: applied, interviewing, offer, rejected, ghosted."""
    store.init()
    if not store.set_tracker_status(application_id, stage):
        from .schema import TRACKER_STATUSES

        return _ok({"error": f"Stage must be one of {', '.join(TRACKER_STATUSES)}."})
    return _ok({"ok": True, "id": application_id, "stage": stage})


# --------------------------------------------------------------------------
# Account and capability
# --------------------------------------------------------------------------

@mcp.tool()
def status() -> str:
    """What Jobenzy knows and what it can do right now."""
    from . import inbox, llm

    store.init()
    mail_ok, mail_why = inbox.available()
    llm_ok, llm_why = llm.available()
    return _ok({
        "store": store.backend_status(),
        "stats": store.stats(),
        "llm": {"available": llm_ok, "reason": llm_why, "budget": llm.budget_status()},
        "mailbox": {"available": mail_ok, "reason": mail_why},
        "portals": portals.summary(),
        "queue": store.task_stats(),
        "proposalsWaiting": len(store.proposals()),
    })


@mcp.tool()
def supported_portals() -> str:
    """Which application systems Jobenzy can read, and which it can submit to."""
    return _ok({"summary": portals.summary(), "portals": portals.table()})


@mcp.tool()
def get_profile() -> str:
    """The stock answers Jobenzy puts into application forms."""
    store.init()
    profile = dict(store.get_setting("profile", {}) or {})
    profile.pop("default_resume", None)
    return _ok(profile)


def main() -> None:
    store.init()
    mcp.run()


if __name__ == "__main__":
    main()
