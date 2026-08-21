"""
SQLite backend for the agent store.

Selected by agent/store.py when MongoDB is not configured or not reachable.

The CSV pipeline stays exactly as it is — this is a separate database for
everything the agent discovers, so the two can run side by side without
fighting over one file.

Tables
------
companies    startups discovered from YC / HN / ATS boards / directories
jobs         open roles pulled from a company's job board
people       founders and recruiters, with verified contact addresses
applications one row per role the apply agent attempted
outreach     one row per cold email the outreach agent sent
runs         one row per agent run, for the history view
settings     key/value store for profile + agent configuration
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

from api.config import BASE_DIR

from .schema import (APPLICATION_FIELDS, COMPANY_FIELDS, DEFAULT_SETTINGS, JOB_FIELDS,
                     LEGACY_APPLICATION_STATUS, MESSAGE_FIELDS, OUTREACH_FIELDS,
                     PERSON_FIELDS, PROPOSAL_DECISIONS, TRACKER_STATUSES, merge_settings, now,
                     retry_policy,
                     with_job_defaults)

# Overridable so the test suite can point the store at a throwaway file.
import os as _os

DB_PATH = Path(_os.environ.get("JOBSCRIPT_DB_PATH") or BASE_DIR / "agent_data.sqlite3")

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS companies (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    domain          TEXT,
    website         TEXT,
    source          TEXT NOT NULL,          -- yc | hn | ats | directory | manual
    source_ref      TEXT,                   -- batch, thread id, board token…
    description     TEXT,
    industry        TEXT,
    location        TEXT,
    region          TEXT,                   -- us | eu | remote | pk | other
    team_size       TEXT,
    founded         TEXT,
    ats_platform    TEXT,                   -- greenhouse | lever | ashby | …
    ats_token       TEXT,                   -- board identifier for the API
    careers_url     TEXT,
    tags            TEXT,                   -- JSON array
    discovered_at   TEXT NOT NULL,
    last_scanned_at TEXT,
    UNIQUE(name, source)
);

CREATE TABLE IF NOT EXISTS jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id      INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    external_id     TEXT,
    title           TEXT NOT NULL,
    location        TEXT,
    remote          INTEGER DEFAULT 0,
    url             TEXT NOT NULL,
    apply_url       TEXT,
    description     TEXT,
    department      TEXT,
    employment_type TEXT,
    source          TEXT NOT NULL,
    posted_at       TEXT,
    posted_ts       INTEGER,                -- normalised UTC epoch, for freshness
    dedupe_hash     TEXT,                   -- company+title+location identity
    discovered_at   TEXT NOT NULL,
    fit_score       REAL,                   -- 0-100 from the ATS matcher
    fit_reason      TEXT,
    status          TEXT NOT NULL DEFAULT 'new',
        -- new | matched | skipped | queued | applied | failed | closed | stale | duplicate
    UNIQUE(url)
);

CREATE TABLE IF NOT EXISTS people (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id      INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    full_name       TEXT,
    role            TEXT,                   -- founder | recruiter | engineer | unknown
    title           TEXT,
    email           TEXT,
    email_source    TEXT,                   -- site | hn | github | pattern | manual
    email_status    TEXT DEFAULT 'unknown', -- valid | risky | invalid | unknown
    email_score     REAL,                   -- 0-1 confidence
    verify_detail   TEXT,
    linkedin        TEXT,
    github          TEXT,
    discovered_at   TEXT NOT NULL,
    verified_at     TEXT,
    UNIQUE(company_id, email)
);

CREATE TABLE IF NOT EXISTS applications (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          INTEGER REFERENCES jobs(id) ON DELETE CASCADE,
    company_id      INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    job_hash        TEXT,                   -- same identity as jobs.dedupe_hash
    status          TEXT NOT NULL,          -- pending | filled | submitted | failed | skipped
    resume_path     TEXT,
    cover_letter    TEXT,
    fields_filled   TEXT,                   -- JSON of what went into the form
    unanswered      TEXT,                   -- JSON of questions it could not answer
    screenshot      TEXT,
    error           TEXT,
    dry_run         INTEGER DEFAULT 0,
    created_at      TEXT NOT NULL,
    submitted_at    TEXT
);

CREATE TABLE IF NOT EXISTS outreach (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id       INTEGER REFERENCES people(id) ON DELETE CASCADE,
    company_id      INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    to_email        TEXT NOT NULL,
    subject         TEXT,
    body            TEXT,
    research_notes  TEXT,
    status          TEXT NOT NULL,          -- drafted | sent | failed | bounced | replied
    error           TEXT,
    dry_run         INTEGER DEFAULT 0,
    sequence_step   INTEGER DEFAULT 1,
    created_at      TEXT NOT NULL,
    sent_at         TEXT,
    replied_at      TEXT
);

CREATE TABLE IF NOT EXISTS runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    mode            TEXT NOT NULL,          -- discover | apply | outreach
    status          TEXT NOT NULL,          -- running | finished | failed | stopped
    options         TEXT,
    stats           TEXT,
    error           TEXT,
    started_at      TEXT NOT NULL,
    finished_at     TEXT
);

CREATE TABLE IF NOT EXISTS tasks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    kind            TEXT NOT NULL,          -- jd_fetch | resume_build | verify_email_greylist
    payload         TEXT,                   -- JSON args for the handler
    status          TEXT NOT NULL DEFAULT 'pending',
        -- pending | running | done | failed | dead
    attempts        INTEGER DEFAULT 0,
    max_attempts    INTEGER DEFAULT 3,
    next_run_at     TEXT,                   -- ISO UTC; due when <= now
    last_error      TEXT,
    priority        INTEGER DEFAULT 0,
    dedupe_key      TEXT,                   -- idempotent enqueue
    created_at      TEXT NOT NULL,
    finished_at     TEXT,
    UNIQUE(dedupe_key)
);

CREATE TABLE IF NOT EXISTS settings (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id  INTEGER REFERENCES applications(id) ON DELETE SET NULL,
    job_id          INTEGER REFERENCES jobs(id) ON DELETE SET NULL,
    company_id      INTEGER REFERENCES companies(id) ON DELETE SET NULL,
    message_id      TEXT,                   -- RFC 5322 Message-ID, the join key
    thread_id       TEXT,                   -- In-Reply-To / References root
    from_addr       TEXT,
    from_domain     TEXT,
    subject         TEXT,
    snippet         TEXT,
    klass           TEXT,                   -- see schema.MESSAGE_CLASSES
    confidence      REAL,                   -- 0-1 that the link is right
    linked_by       TEXT,                   -- thread | domain | company | none
    received_at     TEXT,
    read_at         TEXT,
    created_at      TEXT NOT NULL,
    UNIQUE(message_id)
);

CREATE TABLE IF NOT EXISTS llm_usage (
    day             TEXT NOT NULL,          -- UTC date, YYYY-MM-DD
    purpose         TEXT NOT NULL,          -- apply | classify | tailor | ...
    calls           INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (day, purpose)
);

CREATE TABLE IF NOT EXISTS llm_cache (
    key             TEXT PRIMARY KEY,       -- sha1 of provider+model+prompt+schema
    value           TEXT NOT NULL,
    created_at      TEXT NOT NULL
);
"""

# Indexes are created after migrations, so they can reference columns
# that were added to an already-existing database.
INDEXES = """
CREATE INDEX IF NOT EXISTS idx_companies_domain ON companies(domain);
CREATE INDEX IF NOT EXISTS idx_companies_ats    ON companies(ats_platform);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_fit    ON jobs(fit_score DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_posted ON jobs(posted_ts DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_hash   ON jobs(dedupe_hash);
CREATE INDEX IF NOT EXISTS idx_people_status ON people(email_status);
CREATE INDEX IF NOT EXISTS idx_outreach_status ON outreach(status);
CREATE INDEX IF NOT EXISTS idx_app_hash ON applications(job_hash);
CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(status, next_run_at);
CREATE INDEX IF NOT EXISTS idx_messages_app ON messages(application_id);
CREATE INDEX IF NOT EXISTS idx_messages_klass ON messages(klass, received_at DESC);
CREATE INDEX IF NOT EXISTS idx_app_tracker ON applications(tracker_status);
"""

# Columns added after the first release, applied to existing databases on open.
MIGRATIONS: list[tuple[str, str]] = [
    ("jobs", "posted_ts INTEGER"),
    ("jobs", "dedupe_hash TEXT"),
    ("applications", "job_hash TEXT"),
    # Tracking columns for the job-application agent.
    ("jobs", "role_category TEXT"),
    ("jobs", "recruiter_email TEXT"),
    ("jobs", "recruiter_name TEXT"),
    ("jobs", "description_source TEXT"),
    ("jobs", "resume_path TEXT"),
    ("jobs", "resume_version TEXT"),
    ("jobs", "resume_built_at TEXT"),
    ("jobs", "applied_at TEXT"),
    ("jobs", "failure_reason TEXT"),
    # Pipeline tracking, added with the inbox.
    ("jobs", "resume_mode TEXT"),
    ("jobs", "resume_changes TEXT"),
    ("jobs", "resume_approved INTEGER"),
    ("jobs", "proposed_at TEXT"),
    ("jobs", "proposal_reason TEXT"),
    ("jobs", "proposal_decision TEXT"),
    ("applications", "tracker_status TEXT"),
    ("applications", "message_id TEXT"),
    ("applications", "last_message_at TEXT"),
    # The posting parsed into fields (agent/jobmeta.py), plus the user's
    # bookmark. `skills` is a JSON list; `saved` is 0/1 and survives the purge.
    ("jobs", "salary_min REAL"),
    ("jobs", "salary_max REAL"),
    ("jobs", "salary_currency TEXT"),
    ("jobs", "seniority TEXT"),
    ("jobs", "work_arrangement TEXT"),
    ("jobs", "skills TEXT"),
    ("jobs", "deadline TEXT"),
    ("jobs", "saved INTEGER DEFAULT 0"),
    # An application a person entered or imported by hand, rather than one the
    # agent submitted. Tracked so the manual rows are never mistaken for
    # submissions the applier made.
    ("applications", "source TEXT"),
    ("applications", "title TEXT"),
    ("applications", "company_name TEXT"),
    ("applications", "url TEXT"),
    ("applications", "notes TEXT"),
    ("applications", "applied_on TEXT"),
    # The full message text, so the inbox is a mail client rather than a list
    # of snippets — read the whole thing, and search it.
    ("messages", "body TEXT"),
]


def _migrate(conn: sqlite3.Connection) -> None:
    for table, column_def in MIGRATIONS:
        column = column_def.split()[0]
        existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column_def}")
    conn.commit()

_local = threading.local()


def _conn() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(str(DB_PATH), timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.executescript(SCHEMA)
        _migrate(conn)
        conn.executescript(INDEXES)
        _local.conn = conn
    return conn


@contextmanager
def tx() -> Iterator[sqlite3.Connection]:
    conn = _conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise




def init() -> None:
    _conn()


def _row(r: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(r) if r is not None else None


def _rows(rs: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(r) for r in rs]


def _job_rows(rs: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    """Job reads get the tracking columns filled in, so the shape is stable."""
    return [with_job_defaults(dict(r)) for r in rs]


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------



def get_setting(key: str, default: Any = None) -> Any:
    fallback = DEFAULT_SETTINGS.get(key, default)
    row = _conn().execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if row is None:
        return fallback
    try:
        stored = json.loads(row["value"])
    except json.JSONDecodeError:
        return fallback
    # Same layering as the Mongo backend: newer defaults must reach older rows.
    if isinstance(fallback, dict) and isinstance(stored, dict):
        return {**fallback, **stored}
    return stored


def set_setting(key: str, value: Any) -> None:
    with tx() as c:
        c.execute(
            "INSERT INTO settings(key, value, updated_at) VALUES(?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, json.dumps(value), now()),
        )


def all_settings() -> dict[str, Any]:
    stored = {r["key"]: json.loads(r["value"]) for r in _conn().execute("SELECT key, value FROM settings")}
    return merge_settings(stored)


# --------------------------------------------------------------------------
# Companies
# --------------------------------------------------------------------------



def upsert_company(data: dict[str, Any]) -> int:
    payload = {k: data.get(k) for k in COMPANY_FIELDS}
    if isinstance(payload.get("tags"), (list, tuple)):
        payload["tags"] = json.dumps(list(payload["tags"]))
    payload["discovered_at"] = now()

    cols = ", ".join(payload)
    marks = ", ".join("?" for _ in payload)
    updates = ", ".join(
        f"{k}=COALESCE(excluded.{k}, {k})" for k in payload if k not in ("name", "source", "discovered_at")
    )
    with tx() as c:
        c.execute(
            f"INSERT INTO companies ({cols}) VALUES ({marks}) "
            f"ON CONFLICT(name, source) DO UPDATE SET {updates}",
            tuple(payload.values()),
        )
        # Always look the id up by the unique key. `cursor.lastrowid` is NOT
        # reset when ON CONFLICT takes the UPDATE branch — it still holds the
        # previous successful INSERT's rowid, which would silently attach this
        # company's jobs to whichever company was inserted last.
        row = c.execute(
            "SELECT id FROM companies WHERE name = ? AND source = ?",
            (payload["name"], payload["source"]),
        ).fetchone()
        return int(row["id"])


def list_companies(limit: int = 200, source: str | None = None,
                   with_ats: bool = False) -> list[dict[str, Any]]:
    sql = "SELECT * FROM companies"
    where, args = [], []
    if source:
        where.append("source = ?")
        args.append(source)
    if with_ats:
        where.append("ats_platform IS NOT NULL AND ats_token IS NOT NULL")
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY discovered_at DESC LIMIT ?"
    args.append(limit)
    return _rows(_conn().execute(sql, args))


def company(company_id: int) -> dict[str, Any] | None:
    return _row(_conn().execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone())


def mark_company_scanned(company_id: int) -> None:
    with tx() as c:
        c.execute("UPDATE companies SET last_scanned_at = ? WHERE id = ?", (now(), company_id))


# --------------------------------------------------------------------------
# Jobs
# --------------------------------------------------------------------------



def upsert_job(data: dict[str, Any], *, company_name: str = "") -> int | None:
    if not data.get("url") or not data.get("title"):
        return None

    from . import sources  # imported here to keep store dependency-free at import time

    payload = {k: data.get(k) for k in JOB_FIELDS}
    payload["remote"] = 1 if payload.get("remote") else 0

    if payload.get("posted_ts") is None:
        payload["posted_ts"] = sources.parse_posted_at(payload.get("posted_at"))
    if not payload.get("dedupe_hash"):
        name = company_name
        if not name and payload.get("company_id"):
            row = _conn().execute("SELECT name FROM companies WHERE id = ?",
                                  (payload["company_id"],)).fetchone()
            name = row["name"] if row else ""
        payload["dedupe_hash"] = sources.dedupe_hash(
            name, payload.get("title") or "", payload.get("location") or "",
            url=payload.get("url") or "")

    payload["discovered_at"] = now()

    cols = ", ".join(payload)
    marks = ", ".join("?" for _ in payload)
    updates = ", ".join(
        f"{k}=COALESCE(excluded.{k}, {k})" for k in payload if k not in ("url", "discovered_at")
    )
    with tx() as c:
        c.execute(
            f"INSERT INTO jobs ({cols}) VALUES ({marks}) "
            f"ON CONFLICT(url) DO UPDATE SET {updates}",
            tuple(payload.values()),
        )
        row = c.execute("SELECT id FROM jobs WHERE url = ?", (payload["url"],)).fetchone()
        return int(row["id"]) if row else None


def set_job_fit(job_id: int, score: float, reason: str, status: str) -> None:
    with tx() as c:
        c.execute(
            "UPDATE jobs SET fit_score = ?, fit_reason = ?, status = ? WHERE id = ?",
            (score, reason, status, job_id),
        )


def set_job_status(job_id: int, status: str) -> None:
    with tx() as c:
        c.execute("UPDATE jobs SET status = ? WHERE id = ?", (status, job_id))


# The columns agent/jobmeta.py fills. Kept as a set so set_job_meta can only
# ever write parsed fields, never an arbitrary key from a caller's dict.
_META_COLUMNS = {"salary_min", "salary_max", "salary_currency", "seniority",
                 "work_arrangement", "skills", "deadline", "employment_type"}


def set_job_meta(job_id: int, meta: dict[str, Any]) -> None:
    """Store the parsed job fields. `skills` is JSON-encoded on the way in."""
    updates = {k: v for k, v in meta.items() if k in _META_COLUMNS}
    if not updates:
        return
    if "skills" in updates and not isinstance(updates["skills"], str):
        updates["skills"] = json.dumps(updates["skills"])
    sets = ", ".join(f"{k} = ?" for k in updates)
    with tx() as c:
        c.execute(f"UPDATE jobs SET {sets} WHERE id = ?",
                  [*updates.values(), job_id])


def set_job_saved(job_id: int, saved: bool = True) -> None:
    """Bookmark or un-bookmark a job. A saved job survives the retention purge."""
    with tx() as c:
        c.execute("UPDATE jobs SET saved = ? WHERE id = ?", (1 if saved else 0, job_id))


def pass_job(job_id: int) -> None:
    """
    The user passed on a role from the feed.

    Recorded as `skipped` so it drops out of the ready view exactly as a
    gate-rejected role does, but with a reason that says a person did it — the
    two are different intents and the row should say which.
    """
    with tx() as c:
        c.execute("UPDATE jobs SET status = 'skipped', fit_reason = ? WHERE id = ?",
                  ("Passed by you", job_id))


def purge_old_jobs(days: int = 3, *, keep_applied: bool = True) -> dict[str, Any]:
    """
    Delete jobs discovered more than `days` ago.

    A posting older than the freshness window can never be applied to, so
    keeping it only makes the table harder to read. Deleting it also frees the
    dedupe hash, which is correct: if the same role is re-posted later it should
    be treated as new.

    `keep_applied` protects rows you actually applied to. Deleting those would
    erase your own record of where you applied — the double-apply guard itself
    survives either way, because it reads the applications table rather than
    this one, but the history would be gone from the UI.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=max(0, int(days)))).isoformat()
    # A bookmarked job is kept on purpose; ageing it out would quietly discard a
    # shortlist the user built by hand.
    sql = "SELECT id, resume_path FROM jobs WHERE discovered_at < ? AND COALESCE(saved, 0) = 0"
    args: list[Any] = [cutoff]
    if keep_applied:
        sql += " AND status != 'applied'"
    doomed = _rows(_conn().execute(sql, args))
    resumes = [d["resume_path"] for d in doomed if d.get("resume_path")]
    if doomed:
        marks = ",".join("?" * len(doomed))
        with tx() as c:
            c.execute(f"DELETE FROM jobs WHERE id IN ({marks})", [d["id"] for d in doomed])
    return {"deleted": len(doomed), "resumes": resumes, "cutoff": cutoff}


# --------------------------------------------------------------------------
# Task queue
# --------------------------------------------------------------------------

def enqueue_task(kind: str, payload: dict[str, Any], *, dedupe_key: str,
                 priority: int = 0, delay_s: int = 0) -> int | None:
    """Queue one retryable unit of work. Idempotent on dedupe_key."""
    from datetime import timedelta

    policy = retry_policy(kind)
    due = (datetime.now(timezone.utc) + timedelta(seconds=delay_s)).isoformat()
    with tx() as c:
        cur = c.execute(
            "INSERT INTO tasks (kind, payload, status, attempts, max_attempts, "
            "next_run_at, priority, dedupe_key, created_at) "
            "VALUES (?,?,?,0,?,?,?,?,?) "
            "ON CONFLICT(dedupe_key) DO NOTHING",
            (kind, json.dumps(payload), "pending", policy["max_attempts"],
             due, priority, dedupe_key, now()))
        return int(cur.lastrowid) if cur.rowcount else None


def claim_due_tasks(limit: int = 50) -> list[dict[str, Any]]:
    """Atomically take the due tasks: mark running, return them."""
    cutoff = now()
    with tx() as c:
        rows = _rows(c.execute(
            "SELECT * FROM tasks WHERE status IN ('pending','failed') "
            "AND next_run_at <= ? ORDER BY priority DESC, next_run_at LIMIT ?",
            (cutoff, limit)))
        if rows:
            marks = ",".join("?" * len(rows))
            c.execute(f"UPDATE tasks SET status='running' WHERE id IN ({marks})",
                      [r["id"] for r in rows])
    for r in rows:
        try:
            r["payload"] = json.loads(r["payload"] or "{}")
        except json.JSONDecodeError:
            r["payload"] = {}
    return rows


def complete_task(task_id: int) -> None:
    with tx() as c:
        c.execute("UPDATE tasks SET status='done', finished_at=? WHERE id=?",
                  (now(), task_id))


def fail_task(task_id: int, error: str) -> str:
    """Record a failure; back off exponentially, or mark dead past the cap.
    Returns the resulting status."""
    from datetime import timedelta

    row = _row(_conn().execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone())
    if not row:
        return "missing"
    attempts = int(row["attempts"] or 0) + 1
    policy = retry_policy(row["kind"])
    if attempts >= int(row["max_attempts"] or policy["max_attempts"]):
        status, due = "dead", None
    else:
        status = "failed"
        due = (datetime.now(timezone.utc)
               + timedelta(seconds=policy["backoff_base_s"] * (2 ** (attempts - 1)))).isoformat()
    with tx() as c:
        c.execute("UPDATE tasks SET status=?, attempts=?, last_error=?, next_run_at=?, "
                  "finished_at=? WHERE id=?",
                  (status, attempts, (error or "")[:400], due,
                   now() if status == "dead" else None, task_id))
    return status


def task_stats() -> dict[str, int]:
    return {str(r[0]): int(r[1]) for r in
            _conn().execute("SELECT status, COUNT(*) FROM tasks GROUP BY status")}


# --------------------------------------------------------------------------
# LLM budget + cache
# --------------------------------------------------------------------------

def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def llm_spend(purpose: str) -> None:
    """Count one real provider call against today's budget."""
    with tx() as c:
        c.execute(
            "INSERT INTO llm_usage(day, purpose, calls) VALUES(?,?,1) "
            "ON CONFLICT(day, purpose) DO UPDATE SET calls = calls + 1",
            (_today(), purpose))


def llm_spent_today() -> dict[str, int]:
    """Calls made today, by purpose, plus a 'total'."""
    rows = _conn().execute(
        "SELECT purpose, calls FROM llm_usage WHERE day=?", (_today(),)).fetchall()
    out = {str(r[0]): int(r[1]) for r in rows}
    out["total"] = sum(out.values())
    return out


def llm_cache_get(key: str, max_age_days: int = 14) -> str | None:
    row = _conn().execute("SELECT value, created_at FROM llm_cache WHERE key=?",
                          (key,)).fetchone()
    if row is None:
        return None
    cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat()
    if (row["created_at"] or "") < cutoff:
        return None
    return str(row["value"])


def llm_cache_put(key: str, value: str) -> None:
    with tx() as c:
        c.execute("INSERT OR REPLACE INTO llm_cache(key, value, created_at) VALUES(?,?,?)",
                  (key, value, now()))
        # Keep the cache bounded; oldest rows go first.
        c.execute("DELETE FROM llm_cache WHERE key NOT IN "
                  "(SELECT key FROM llm_cache ORDER BY created_at DESC LIMIT 2000)")


def known_hashes() -> set[str]:
    """
    Every job already in the table, by dedupe hash.

    Discovery checks this before fetching a description or building a resume, so
    a job seen on a previous run costs nothing on this one.
    """
    rows = _conn().execute(
        "SELECT DISTINCT dedupe_hash FROM jobs WHERE dedupe_hash IS NOT NULL")
    return {r["dedupe_hash"] for r in rows if r["dedupe_hash"]}


def set_job_category(job_id: int, category: str | None) -> None:
    with tx() as c:
        c.execute("UPDATE jobs SET role_category = ? WHERE id = ?", (category, job_id))


def set_job_description(job_id: int, description: str, source: str) -> None:
    with tx() as c:
        c.execute("UPDATE jobs SET description = ?, description_source = ? WHERE id = ?",
                  (description, source, job_id))


def set_job_recruiter(job_id: int, email: str, name: str = "") -> None:
    """Only ever called with an address that was actually found."""
    if not email:
        return
    with tx() as c:
        c.execute("UPDATE jobs SET recruiter_email = ?, recruiter_name = ? WHERE id = ?",
                  (email, name or "", job_id))


def set_job_resume(job_id: int, path: str, version: str, *,
                   mode: str | None = None,
                   changes: list[dict[str, Any]] | None = None,
                   approved: bool | None = None) -> None:
    with tx() as c:
        c.execute("UPDATE jobs SET resume_path = ?, resume_version = ?, "
                  "resume_built_at = ?, resume_mode = ?, resume_changes = ?, "
                  "resume_approved = ? WHERE id = ?",
                  (path, version, now(), mode,
                   json.dumps(changes or []),
                   None if approved is None else (1 if approved else 0),
                   job_id))


def propose_job(job_id: int, reason: str) -> None:
    """Put a job in the Auto Apply review queue. Proposing submits nothing."""
    with tx() as c:
        c.execute("UPDATE jobs SET proposed_at = ?, proposal_reason = ?, "
                  "proposal_decision = NULL WHERE id = ?", (now(), reason, job_id))


def decide_proposal(job_id: int, decision: str) -> bool:
    """Record the human's answer. Returns False for anything but the two values."""
    if decision not in PROPOSAL_DECISIONS:
        return False
    with tx() as c:
        c.execute("UPDATE jobs SET proposal_decision = ? WHERE id = ?", (decision, job_id))
    return True


def proposals(decision: str | None = "__undecided__") -> list[dict[str, Any]]:
    """
    Rows in the review queue.

    The default returns only what is still waiting on a person, which is the
    question the screen actually asks.
    """
    sql = ("SELECT j.*, c.name AS company_name, c.domain FROM jobs j "
           "LEFT JOIN companies c ON c.id = j.company_id "
           "WHERE j.proposed_at IS NOT NULL")
    args: list[Any] = []
    if decision == "__undecided__":
        sql += " AND j.proposal_decision IS NULL"
    elif decision:
        sql += " AND j.proposal_decision = ?"
        args.append(decision)
    sql += " ORDER BY COALESCE(j.fit_score, 0) DESC, j.proposed_at DESC"
    return _job_rows(_conn().execute(sql, args))


def proposed_today() -> int:
    """How many proposals the daily cap has already spent."""
    since = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    row = _conn().execute(
        "SELECT COUNT(*) FROM jobs WHERE proposed_at IS NOT NULL AND proposed_at >= ?",
        (since,)).fetchone()
    return int(row[0]) if row else 0


def approve_job_resume(job_id: int, changes: list[dict[str, Any]] | None = None) -> None:
    """Sign off a tailored resume. `changes` carries any edits the user made."""
    with tx() as c:
        if changes is None:
            c.execute("UPDATE jobs SET resume_approved = 1 WHERE id = ?", (job_id,))
        else:
            c.execute("UPDATE jobs SET resume_approved = 1, resume_changes = ? WHERE id = ?",
                      (json.dumps(changes), job_id))


def set_job_applied(job_id: int, *, resume_version: str = "") -> None:
    with tx() as c:
        c.execute("UPDATE jobs SET status = 'applied', applied_at = ?, "
                  "resume_version = COALESCE(NULLIF(?, ''), resume_version), "
                  "failure_reason = NULL WHERE id = ?", (now(), resume_version, job_id))


def mark_job_failed(job_id: int, reason: str) -> None:
    """A form that could not be completed is recorded, never skipped silently."""
    with tx() as c:
        c.execute("UPDATE jobs SET status = 'failed', failure_reason = ? WHERE id = ?",
                  ((reason or "")[:400], job_id))


def job(job_id: int) -> dict[str, Any] | None:
    row = _row(_conn().execute(
        "SELECT j.*, c.name AS company_name, c.domain, c.region, c.ats_platform FROM jobs j "
        "LEFT JOIN companies c ON c.id = j.company_id WHERE j.id = ?", (job_id,)).fetchone())
    return with_job_defaults(row) if row else None


def job_by_url(url: str) -> dict[str, Any] | None:
    """A job already tracked at this URL. The url column is unique."""
    row = _row(_conn().execute(
        "SELECT j.*, c.name AS company_name FROM jobs j "
        "LEFT JOIN companies c ON c.id = j.company_id WHERE j.url = ?", (url,)).fetchone())
    return with_job_defaults(row) if row else None


def jobs_by_ids(job_ids: list[int]) -> list[dict[str, Any]]:
    ids = [int(i) for i in job_ids]
    if not ids:
        return []
    marks = ",".join("?" * len(ids))
    rows = _job_rows(_conn().execute(
        f"SELECT j.*, c.name AS company_name, c.domain, c.region, c.ats_platform FROM jobs j "
        f"LEFT JOIN companies c ON c.id = j.company_id WHERE j.id IN ({marks})", ids))
    order = {j: i for i, j in enumerate(ids)}
    return sorted(rows, key=lambda r: order.get(int(r["id"]), 1 << 30))


def jobs_needing_scoring(limit: int = 200) -> list[dict[str, Any]]:
    return _job_rows(_conn().execute(
        "SELECT j.*, c.name AS company_name, c.domain FROM jobs j "
        "LEFT JOIN companies c ON c.id = j.company_id "
        "WHERE j.status = 'new' ORDER BY j.discovered_at DESC LIMIT ?", (limit,)))


def jobs_needing_meta(limit: int = 400) -> list[dict[str, Any]]:
    """
    Scored jobs that were never parsed into fields.

    The detail parser (agent/jobmeta.py) was added after these rows were
    scored, so they carry a score but no salary, skills or seniority. This
    finds them to be enriched in place, and finds nothing once a run has caught
    up — a job with a description but a null `skills` is the whole set.
    """
    return _job_rows(_conn().execute(
        "SELECT j.*, c.name AS company_name FROM jobs j "
        "LEFT JOIN companies c ON c.id = j.company_id "
        "WHERE j.skills IS NULL AND j.description IS NOT NULL AND j.description != '' "
        "ORDER BY j.discovered_at DESC LIMIT ?", (limit,)))


def applied_hashes() -> set[str]:
    """Identities already acted on, so a role is never applied to twice."""
    rows = _conn().execute(
        "SELECT DISTINCT job_hash FROM applications "
        "WHERE job_hash IS NOT NULL AND status IN ('submitted','filled') AND dry_run = 0")
    return {r["job_hash"] for r in rows if r["job_hash"]}


def jobs_to_apply(limit: int = 20, min_score: float = 55.0, *,
                  max_age_days: int | None = 3, require_posted_date: bool = True,
                  order: str = "recent") -> dict[str, Any]:
    """
    The apply queue.

    Freshness is a hard gate — a role posted a week ago has usually already
    collected hundreds of applicants. Ordering then favours the newest, because
    being early matters more than being a marginally better match.

    Returns the rows plus the counts excluded at each gate, so the runner can
    say *why* a job did not make the cut instead of silently dropping it.
    """
    cutoff = None
    if max_age_days is not None and max_age_days > 0:
        cutoff = int(time.time() - max_age_days * 86400)

    base = ("SELECT j.*, c.name AS company_name, c.domain, c.ats_platform FROM jobs j "
            "LEFT JOIN companies c ON c.id = j.company_id "
            "WHERE j.status IN ('matched','queued') AND COALESCE(j.fit_score,0) >= ?")
    candidates = _job_rows(_conn().execute(base + " ORDER BY j.fit_score DESC", (min_score,)))

    seen = applied_hashes()
    fresh, stale, undated, duplicate = [], 0, 0, 0

    for job in candidates:
        if job.get("dedupe_hash") and job["dedupe_hash"] in seen:
            duplicate += 1
            continue
        ts = job.get("posted_ts")
        if cutoff is not None:
            if ts is None:
                if require_posted_date:
                    undated += 1
                    continue
            elif ts < cutoff:
                stale += 1
                continue
        job["age_days"] = round((time.time() - ts) / 86400.0, 1) if ts else None
        fresh.append(job)

    if order == "recent":
        # Newest first; undated (only present when allowed) fall to the back.
        fresh.sort(key=lambda j: (-(j.get("posted_ts") or 0), -(j.get("fit_score") or 0)))
    else:
        fresh.sort(key=lambda j: (-(j.get("fit_score") or 0), -(j.get("posted_ts") or 0)))

    # Never apply twice to the same role inside one run either.
    picked, batch_seen = [], set()
    for job in fresh:
        h = job.get("dedupe_hash")
        if h and h in batch_seen:
            duplicate += 1
            continue
        if h:
            batch_seen.add(h)
        picked.append(job)
        if len(picked) >= limit:
            break

    return {
        "jobs": picked,
        "excluded": {"stale": stale, "undated": undated, "duplicate": duplicate,
                     "eligible": len(fresh), "considered": len(candidates)},
    }


def _as_list(value: Any) -> list[str]:
    """
    A filter that may arrive as one value, a comma-joined string or a list.

    The UI sends `category=frontend,fullstack` for a multiple selection and a
    bare `category=frontend` for one; both mean the same thing here.
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return [str(v).strip() for v in value if str(v).strip()]


# What "sorted by" can mean. Each ends with a stable tiebreak so paging through
# the same filter twice returns the same order.
JOB_SORTS = {
    "recent": "COALESCE(j.posted_ts, 0) DESC, COALESCE(j.fit_score, -1) DESC, j.id DESC",
    "score": "COALESCE(j.fit_score, -1) DESC, COALESCE(j.posted_ts, 0) DESC, j.id DESC",
    "company": "c.name COLLATE NOCASE ASC, COALESCE(j.fit_score, -1) DESC, j.id DESC",
    "title": "j.title COLLATE NOCASE ASC, j.id DESC",
}


def list_jobs(limit: int = 100, status: str | None = None, *,
              category: Any = None, source: Any = None,
              q: str | None = None, min_score: float | None = None,
              max_score: float | None = None, posted_within_days: int | None = None,
              location: str | None = None, company: str | None = None,
              remote: bool | None = None, has_resume: bool | None = None,
              min_salary: float | None = None, saved: bool | None = None,
              sort: str = "recent") -> list[dict[str, Any]]:
    sql = ("SELECT j.*, c.name AS company_name, c.region, c.ats_platform FROM jobs j "
           "LEFT JOIN companies c ON c.id = j.company_id")
    where: list[str] = []
    args: list[Any] = []
    if status == "not_applied":
        # Open AND actionable: a role the experience gate rejected is not
        # something the user can apply to, so it stays out of the default view.
        where.append("j.status NOT IN ('applied','failed','skipped','duplicate')")
    elif status:
        where.append("j.status = ?")
        args.append(status)
    categories_wanted = _as_list(category)
    if categories_wanted:
        where.append(f"j.role_category IN ({','.join('?' * len(categories_wanted))})")
        args += categories_wanted
    sources_wanted = _as_list(source)
    if sources_wanted:
        where.append(f"j.source IN ({','.join('?' * len(sources_wanted))})")
        args += sources_wanted
    if q:
        where.append("(j.title LIKE ? OR j.location LIKE ? OR j.description LIKE ?)")
        args += [f"%{q}%"] * 3
    if min_score is not None:
        where.append("COALESCE(j.fit_score, 0) >= ?")
        args.append(float(min_score))
    if max_score is not None:
        where.append("COALESCE(j.fit_score, 0) <= ?")
        args.append(float(max_score))
    if posted_within_days is not None and posted_within_days > 0:
        where.append("j.posted_ts >= ?")
        args.append(int(time.time() - posted_within_days * 86400))
    if location:
        where.append("j.location LIKE ?")
        args.append(f"%{location}%")
    if company:
        where.append("c.name LIKE ?")
        args.append(f"%{company}%")
    if remote is not None:
        # Boards disagree about where "remote" lives: some set the flag, most
        # only say so in the location. Asking both is the only way to answer
        # the question the user is actually asking.
        clause = "(j.remote = 1 OR j.location LIKE '%remote%')"
        where.append(clause if remote else f"NOT {clause}")
    if has_resume is not None:
        clause = "(j.resume_path IS NOT NULL AND j.resume_path != '')"
        where.append(clause if has_resume else f"NOT {clause}")
    if min_salary is not None:
        # Match on the top of the range where there is one, so a "40k-70k" role
        # clears a 60k floor. A posting with no parsed salary is excluded rather
        # than assumed to pass — the filter means "pays at least this", and an
        # unknown does not.
        where.append("COALESCE(j.salary_max, j.salary_min) >= ?")
        args.append(float(min_salary))
    if saved is not None:
        where.append("COALESCE(j.saved, 0) = ?" if saved else "COALESCE(j.saved, 0) = 0")
        if saved:
            args.append(1)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += f" ORDER BY {JOB_SORTS.get(sort) or JOB_SORTS['recent']} LIMIT ?"
    args.append(limit)
    rows = _job_rows(_conn().execute(sql, args))
    applied = applied_hashes()
    for r in rows:
        ts = r.get("posted_ts")
        r["age_days"] = round((time.time() - ts) / 86400.0, 1) if ts else None
        r["already_applied"] = bool(r.get("dedupe_hash") and r["dedupe_hash"] in applied)
    return rows


def job_facets() -> dict[str, Any]:
    """
    How many jobs sit under each category, portal and status.

    Counted by the database. The dashboard used to work this out by fetching a
    thousand whole rows — descriptions and all — and tallying them in Python,
    once per request, which is most of what made the jobs table slow to open.
    """
    conn = _conn()

    def tally(column: str) -> dict[str, int]:
        rows = conn.execute(
            f"SELECT {column} AS k, COUNT(*) AS n FROM jobs "
            f"WHERE {column} IS NOT NULL AND {column} != '' "
            f"GROUP BY {column} ORDER BY n DESC").fetchall()
        return {str(r["k"]): int(r["n"]) for r in rows}

    total = int(conn.execute("SELECT COUNT(*) AS n FROM jobs").fetchone()["n"])
    return {
        "total": total,
        "categories": tally("role_category"),
        "sources": tally("source"),
        "statuses": tally("status"),
    }


# --------------------------------------------------------------------------
# People
# --------------------------------------------------------------------------

def upsert_person(data: dict[str, Any]) -> int | None:
    fields = PERSON_FIELDS
    payload = {k: data.get(k) for k in fields}
    if not payload.get("email"):
        return None
    payload["email"] = payload["email"].strip().lower()
    payload["discovered_at"] = now()

    cols = ", ".join(payload)
    marks = ", ".join("?" for _ in payload)
    updates = ", ".join(
        f"{k}=COALESCE(excluded.{k}, {k})" for k in payload
        if k not in ("company_id", "email", "discovered_at")
    )
    with tx() as c:
        c.execute(
            f"INSERT INTO people ({cols}) VALUES ({marks}) "
            f"ON CONFLICT(company_id, email) DO UPDATE SET {updates}",
            tuple(payload.values()),
        )
        row = c.execute(
            "SELECT id FROM people WHERE company_id IS ? AND email = ?",
            (payload["company_id"], payload["email"]),
        ).fetchone()
        return int(row["id"]) if row else None


def people_to_email(limit: int = 20) -> list[dict[str, Any]]:
    return _rows(_conn().execute(
        "SELECT p.*, c.name AS company_name, c.domain, c.description, c.website, c.industry, c.region "
        "FROM people p LEFT JOIN companies c ON c.id = p.company_id "
        "WHERE p.email_status IN ('valid','risky') "
        "AND NOT EXISTS (SELECT 1 FROM outreach o WHERE o.person_id = p.id AND o.status IN ('sent','replied')) "
        "ORDER BY CASE p.email_status WHEN 'valid' THEN 0 ELSE 1 END, "
        "CASE p.role WHEN 'founder' THEN 0 WHEN 'recruiter' THEN 1 ELSE 2 END, "
        "COALESCE(p.email_score,0) DESC LIMIT ?", (limit,)))


def list_people(limit: int = 200, status: str | None = None) -> list[dict[str, Any]]:
    sql = ("SELECT p.*, c.name AS company_name, c.region FROM people p "
           "LEFT JOIN companies c ON c.id = p.company_id")
    args: list[Any] = []
    if status:
        sql += " WHERE p.email_status = ?"
        args.append(status)
    sql += " ORDER BY p.discovered_at DESC LIMIT ?"
    args.append(limit)
    return _rows(_conn().execute(sql, args))


# --------------------------------------------------------------------------
# Applications & outreach
# --------------------------------------------------------------------------

def record_application(data: dict[str, Any]) -> int:
    fields = APPLICATION_FIELDS
    payload = {k: data.get(k) for k in fields}
    for key in ("fields_filled", "unanswered"):
        if isinstance(payload.get(key), (dict, list)):
            payload[key] = json.dumps(payload[key])
    payload["status"] = LEGACY_APPLICATION_STATUS.get(payload.get("status") or "",
                                                      payload.get("status"))
    payload["dry_run"] = 1 if payload.get("dry_run") else 0
    # A submitted application enters the pipeline at "applied"; anything else
    # has not reached an employer, so it has no pipeline stage at all.
    if not payload.get("tracker_status") and payload.get("status") == "submitted":
        payload["tracker_status"] = "applied"
    payload["created_at"] = now()
    payload["submitted_at"] = now() if payload.get("status") == "submitted" else None

    cols = ", ".join(payload)
    marks = ", ".join("?" for _ in payload)
    with tx() as c:
        cur = c.execute(f"INSERT INTO applications ({cols}) VALUES ({marks})", tuple(payload.values()))
        return int(cur.lastrowid)


def record_outreach(data: dict[str, Any]) -> int:
    fields = OUTREACH_FIELDS
    payload = {k: data.get(k) for k in fields}
    payload["dry_run"] = 1 if payload.get("dry_run") else 0
    payload["sequence_step"] = payload.get("sequence_step") or 1
    payload["created_at"] = now()
    payload["sent_at"] = now() if payload.get("status") == "sent" else None

    cols = ", ".join(payload)
    marks = ", ".join("?" for _ in payload)
    with tx() as c:
        cur = c.execute(f"INSERT INTO outreach ({cols}) VALUES ({marks})", tuple(payload.values()))
        return int(cur.lastrowid)


MANUAL_APPLICATION_FIELDS = ("title", "company_name", "url", "notes",
                             "tracker_status", "applied_on")


def add_manual_application(data: dict[str, Any]) -> int:
    """
    An application the user made outside Quiver, entered by hand or imported.

    Recorded as a real submitted application so it counts in the tracker and the
    reply-rate figures — the user did apply — with `source='manual'` marking that
    the applier did not do it. It carries its own title and company because there
    is no job row behind it to read them from.
    """
    stage = data.get("tracker_status") or "applied"
    if stage not in TRACKER_STATUSES:
        stage = "applied"
    when = (data.get("applied_on") or "").strip() or now()
    payload = {
        "status": "submitted",
        "source": "manual",
        "dry_run": 0,
        "tracker_status": stage,
        "title": (data.get("title") or "").strip() or "Untitled role",
        "company_name": (data.get("company_name") or "").strip() or None,
        "url": (data.get("url") or "").strip() or None,
        "notes": (data.get("notes") or "").strip() or None,
        "applied_on": when,
        "created_at": now(),
        "submitted_at": when,
    }
    cols = ", ".join(payload)
    marks = ", ".join("?" for _ in payload)
    with tx() as c:
        cur = c.execute(f"INSERT INTO applications ({cols}) VALUES ({marks})",
                        tuple(payload.values()))
        return int(cur.lastrowid)


def list_applications(limit: int = 100) -> list[dict[str, Any]]:
    return _rows(_conn().execute(
        "SELECT a.*, COALESCE(j.title, a.title) AS title, "
        "       COALESCE(j.url, a.url) AS url, "
        "       COALESCE(c.name, a.company_name) AS company_name FROM applications a "
        "LEFT JOIN jobs j ON j.id = a.job_id "
        "LEFT JOIN companies c ON c.id = a.company_id "
        "ORDER BY a.created_at DESC LIMIT ?", (limit,)))


def list_outreach(limit: int = 100) -> list[dict[str, Any]]:
    return _rows(_conn().execute(
        "SELECT o.*, p.full_name, p.role, c.name AS company_name FROM outreach o "
        "LEFT JOIN people p ON p.id = o.person_id "
        "LEFT JOIN companies c ON c.id = o.company_id "
        "ORDER BY o.created_at DESC LIMIT ?", (limit,)))


# --------------------------------------------------------------------------
# Pipeline tracking
# --------------------------------------------------------------------------

def application(app_id: int) -> dict[str, Any] | None:
    return _row(_conn().execute(
        "SELECT a.*, COALESCE(j.title, a.title) AS title, "
        "       COALESCE(j.url, a.url) AS url, j.location, "
        "       COALESCE(c.name, a.company_name) AS company_name, c.domain "
        "FROM applications a "
        "LEFT JOIN jobs j ON j.id = a.job_id "
        "LEFT JOIN companies c ON c.id = a.company_id "
        "WHERE a.id = ?", (app_id,)).fetchone())


def set_application_status(app_id: int, status: str, error: str | None = None) -> None:
    """Move an application along its submission state machine."""
    status = LEGACY_APPLICATION_STATUS.get(status, status)
    with tx() as c:
        c.execute(
            "UPDATE applications SET status=?, error=COALESCE(?, error), "
            "submitted_at=CASE WHEN ?='submitted' THEN ? ELSE submitted_at END, "
            "tracker_status=CASE WHEN ?='submitted' AND tracker_status IS NULL "
            "                    THEN 'applied' ELSE tracker_status END "
            "WHERE id=?",
            (status, error, status, now(), status, app_id))


def set_tracker_status(app_id: int, status: str) -> bool:
    """Set the pipeline stage. Returns False for a status outside the set."""
    if status not in TRACKER_STATUSES:
        return False
    with tx() as c:
        c.execute("UPDATE applications SET tracker_status=? WHERE id=?", (status, app_id))
    return True


def tracked_applications(limit: int = 500) -> list[dict[str, Any]]:
    """Every application that reached an employer, newest first."""
    return _rows(_conn().execute(
        "SELECT a.*, COALESCE(j.title, a.title) AS title, "
        "       COALESCE(j.url, a.url) AS url, j.location, j.role_category, "
        "       COALESCE(c.name, a.company_name) AS company_name, c.domain, "
        "       (SELECT COUNT(*) FROM messages m WHERE m.application_id = a.id) AS message_count "
        "FROM applications a "
        "LEFT JOIN jobs j ON j.id = a.job_id "
        "LEFT JOIN companies c ON c.id = a.company_id "
        "WHERE a.status = 'submitted' OR a.tracker_status IS NOT NULL "
        "ORDER BY COALESCE(a.last_message_at, a.submitted_at, a.created_at) DESC "
        "LIMIT ?", (limit,)))


def applications_for_linking() -> list[dict[str, Any]]:
    """The candidate set an incoming message could belong to.

    Deliberately every submitted application rather than a recent window: a
    rejection can arrive months later, and matching it to the wrong company is
    worse than matching it late."""
    return _rows(_conn().execute(
        "SELECT a.id, a.job_id, a.company_id, a.message_id, a.tracker_status, "
        "       a.submitted_at, j.title, c.name AS company_name, c.domain "
        "FROM applications a "
        "LEFT JOIN jobs j ON j.id = a.job_id "
        "LEFT JOIN companies c ON c.id = a.company_id "
        "WHERE a.status = 'submitted'"))


def record_message(data: dict[str, Any]) -> int | None:
    """Store one inbox message. Idempotent on Message-ID."""
    payload = {k: data.get(k) for k in MESSAGE_FIELDS}
    payload["created_at"] = now()
    cols = ", ".join(payload)
    marks = ", ".join("?" for _ in payload)
    with tx() as c:
        cur = c.execute(
            f"INSERT INTO messages ({cols}) VALUES ({marks}) "
            f"ON CONFLICT(message_id) DO NOTHING", tuple(payload.values()))
        if not cur.rowcount:
            return None
        if payload.get("application_id"):
            c.execute(
                "UPDATE applications SET last_message_at=? WHERE id=?",
                (payload.get("received_at") or now(), payload["application_id"]))
        return int(cur.lastrowid)


def list_messages(limit: int = 200, klass: str | None = None,
                  unread_only: bool = False, q: str | None = None) -> list[dict[str, Any]]:
    sql = ("SELECT m.*, j.title, c.name AS company_name, a.tracker_status "
           "FROM messages m "
           "LEFT JOIN applications a ON a.id = m.application_id "
           "LEFT JOIN jobs j ON j.id = m.job_id "
           "LEFT JOIN companies c ON c.id = m.company_id")
    where, args = [], []
    if klass:
        where.append("m.klass = ?")
        args.append(klass)
    if unread_only:
        where.append("m.read_at IS NULL")
    if q:
        where.append("(m.subject LIKE ? OR m.from_addr LIKE ? OR m.snippet LIKE ? "
                     "OR m.body LIKE ? OR c.name LIKE ?)")
        args += [f"%{q}%"] * 5
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY COALESCE(m.received_at, m.created_at) DESC LIMIT ?"
    args.append(limit)
    return _rows(_conn().execute(sql, args))



def get_message(message_row_id: int) -> dict[str, Any] | None:
    """One message with the job and company it was matched to, or None."""
    rows = _rows(_conn().execute(
        "SELECT m.*, j.title, c.name AS company_name, a.tracker_status "
        "FROM messages m "
        "LEFT JOIN applications a ON a.id = m.application_id "
        "LEFT JOIN jobs j ON j.id = m.job_id "
        "LEFT JOIN companies c ON c.id = m.company_id "
        "WHERE m.id = ?", (message_row_id,)))
    return rows[0] if rows else None

def unread_count() -> int:
    row = _conn().execute("SELECT COUNT(*) FROM messages WHERE read_at IS NULL").fetchone()
    return int(row[0]) if row else 0


def mark_message_read(message_row_id: int, read: bool = True) -> None:
    with tx() as c:
        c.execute("UPDATE messages SET read_at=? WHERE id=?",
                  (now() if read else None, message_row_id))


def known_message_ids() -> set[str]:
    """Message-IDs already stored, so a re-scan costs no parsing."""
    return {r[0] for r in
            _conn().execute("SELECT message_id FROM messages WHERE message_id IS NOT NULL")
            if r[0]}


def tracker_counts() -> dict[str, int]:
    return {str(r[0]): int(r[1]) for r in _conn().execute(
        "SELECT tracker_status, COUNT(*) FROM applications "
        "WHERE tracker_status IS NOT NULL GROUP BY tracker_status")}


def message_counts() -> dict[str, int]:
    return {str(r[0]): int(r[1]) for r in _conn().execute(
        "SELECT klass, COUNT(*) FROM messages WHERE klass IS NOT NULL GROUP BY klass")}


# --------------------------------------------------------------------------
# Runs & stats
# --------------------------------------------------------------------------

def start_run(mode: str, options: dict[str, Any]) -> int:
    with tx() as c:
        cur = c.execute(
            "INSERT INTO runs (mode, status, options, started_at) VALUES (?,?,?,?)",
            (mode, "running", json.dumps(options), now()),
        )
        return int(cur.lastrowid)


def finish_run(run_id: int, status: str, stats: dict[str, Any], error: str | None = None) -> None:
    with tx() as c:
        c.execute(
            "UPDATE runs SET status = ?, stats = ?, error = ?, finished_at = ? WHERE id = ?",
            (status, json.dumps(stats), error, now(), run_id),
        )


def list_runs(limit: int = 20) -> list[dict[str, Any]]:
    return _rows(_conn().execute("SELECT * FROM runs ORDER BY started_at DESC LIMIT ?", (limit,)))


def stats() -> dict[str, Any]:
    c = _conn()

    def scalar(sql: str, args: tuple = ()) -> int:
        row = c.execute(sql, args).fetchone()
        return int(row[0]) if row and row[0] is not None else 0

    def group(sql: str) -> dict[str, int]:
        return {str(r[0]): int(r[1]) for r in c.execute(sql)}

    return {
        "companies": scalar("SELECT COUNT(*) FROM companies"),
        "companiesBySource": group("SELECT source, COUNT(*) FROM companies GROUP BY source"),
        "companiesWithAts": scalar("SELECT COUNT(*) FROM companies WHERE ats_token IS NOT NULL"),
        "jobs": scalar("SELECT COUNT(*) FROM jobs"),
        "jobsByStatus": group("SELECT status, COUNT(*) FROM jobs GROUP BY status"),
        "matchedJobs": scalar("SELECT COUNT(*) FROM jobs WHERE status IN ('matched','queued')"),
        "people": scalar("SELECT COUNT(*) FROM people"),
        "peopleByStatus": group("SELECT email_status, COUNT(*) FROM people GROUP BY email_status"),
        "applications": scalar("SELECT COUNT(*) FROM applications"),
        "applicationsSubmitted": scalar("SELECT COUNT(*) FROM applications WHERE status='submitted'"),
        "outreachSent": scalar("SELECT COUNT(*) FROM outreach WHERE status='sent'"),
        "outreachReplied": scalar("SELECT COUNT(*) FROM outreach WHERE status='replied'"),
    }
