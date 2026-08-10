"""
MongoDB backend for the agent store.

Mirrors agent/sqlite_store.py function for function, so agent/store.py can pick
either one and nothing else in the codebase knows which is in use.

Two deliberate choices:

  * Integer ids, not ObjectIds. Every caller already passes `company_id` and
    `job_id` around as integers and the frontend renders them, so a `counters`
    collection issues sequences and the public shape stays identical.
  * Joins are done in Python, not aggregation pipelines. These collections hold
    hundreds of documents, one extra round trip is cheaper than the complexity,
    and the resulting rows match the SQLite backend's shape exactly.
"""

from __future__ import annotations

from . import env

import json
import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from api.config import BASE_DIR

from .schema import (APPLICATION_FIELDS, COMPANY_FIELDS, DEFAULT_SETTINGS, JOB_FIELDS,
                     with_job_defaults,
                     OUTREACH_FIELDS, PERSON_FIELDS, merge_settings, now,
                     retry_policy)

_client = None
_db = None
_lock = threading.Lock()

CONNECT_TIMEOUT_MS = 8000


# --------------------------------------------------------------------------
# Connection
# --------------------------------------------------------------------------



def uri() -> str:
    env.load()
    return os.environ.get("MONGODB_URI", "").strip()


def db_name() -> str:
    env.load()
    return os.environ.get("MONGODB_DB", "jobscript").strip() or "jobscript"


def configured() -> bool:
    return bool(uri())


def available() -> tuple[bool, str]:
    """Is Mongo configured and actually reachable right now?"""
    if not configured():
        return False, "MONGODB_URI is not set."
    try:
        _connect().command("ping")
        return True, f"Connected to MongoDB database '{db_name()}'."
    except Exception as exc:
        return False, f"{type(exc).__name__}: {str(exc)[:180]}"


def _connect():
    global _client, _db
    if _db is not None:
        return _db
    with _lock:
        if _db is not None:
            return _db
        from pymongo import MongoClient

        _client = MongoClient(
            uri(),
            serverSelectionTimeoutMS=CONNECT_TIMEOUT_MS,
            connectTimeoutMS=CONNECT_TIMEOUT_MS,
            retryWrites=True,
            appname="quiver",
        )
        _client.admin.command("ping")
        _db = _client[db_name()]
        _ensure_indexes(_db)
        return _db


def _ensure_indexes(db) -> None:
    from pymongo import ASCENDING, DESCENDING

    db.companies.create_index([("name", ASCENDING), ("source", ASCENDING)], unique=True)
    db.companies.create_index([("id", ASCENDING)], unique=True)
    db.companies.create_index([("domain", ASCENDING)])

    db.jobs.create_index([("url", ASCENDING)], unique=True)
    db.jobs.create_index([("id", ASCENDING)], unique=True)
    db.jobs.create_index([("status", ASCENDING)])
    db.jobs.create_index([("fit_score", DESCENDING)])
    db.jobs.create_index([("posted_ts", DESCENDING)])
    db.jobs.create_index([("dedupe_hash", ASCENDING)])

    db.people.create_index([("company_id", ASCENDING), ("email", ASCENDING)], unique=True)
    db.people.create_index([("id", ASCENDING)], unique=True)
    db.people.create_index([("email_status", ASCENDING)])

    db.applications.create_index([("id", ASCENDING)], unique=True)
    db.applications.create_index([("job_hash", ASCENDING)])
    db.outreach.create_index([("id", ASCENDING)], unique=True)
    db.outreach.create_index([("status", ASCENDING)])
    db.runs.create_index([("id", ASCENDING)], unique=True)
    db.tasks.create_index([("id", ASCENDING)], unique=True)
    db.tasks.create_index([("dedupe_key", ASCENDING)], unique=True, sparse=True)
    db.tasks.create_index([("status", ASCENDING), ("next_run_at", ASCENDING)])


def init() -> None:
    _connect()


def _next_id(name: str) -> int:
    """Auto-increment sequence, so ids stay integers like the SQLite backend."""
    doc = _connect().counters.find_one_and_update(
        {"_id": name}, {"$inc": {"seq": 1}}, upsert=True, return_document=True)
    return int(doc["seq"])


def _clean(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    if doc is None:
        return None
    doc.pop("_id", None)
    return doc


def _cleaned(docs: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [d for d in (_clean(dict(x)) for x in docs) if d is not None]


def _set_of(payload: dict[str, Any], skip: Iterable[str] = ()) -> dict[str, Any]:
    """COALESCE semantics: only overwrite with values that are actually present."""
    skip = set(skip)
    return {k: v for k, v in payload.items() if k not in skip and v is not None and v != ""}


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------

def get_setting(key: str, default: Any = None) -> Any:
    fallback = DEFAULT_SETTINGS.get(key, default)
    doc = _connect().settings.find_one({"_id": key})
    if doc is None:
        return fallback
    try:
        stored = json.loads(doc["value"])
    except (KeyError, json.JSONDecodeError):
        return fallback
    # Layer over the defaults so settings added in a later version are visible
    # to installs whose stored document predates them.
    if isinstance(fallback, dict) and isinstance(stored, dict):
        return {**fallback, **stored}
    return stored


def set_setting(key: str, value: Any) -> None:
    _connect().settings.update_one(
        {"_id": key},
        {"$set": {"value": json.dumps(value), "updated_at": now()}},
        upsert=True)


def all_settings() -> dict[str, Any]:
    stored: dict[str, Any] = {}
    for doc in _connect().settings.find():
        try:
            stored[doc["_id"]] = json.loads(doc["value"])
        except (KeyError, json.JSONDecodeError):
            continue
    return merge_settings(stored)


# --------------------------------------------------------------------------
# Companies
# --------------------------------------------------------------------------

def upsert_company(data: dict[str, Any]) -> int:
    payload = {k: data.get(k) for k in COMPANY_FIELDS}
    if isinstance(payload.get("tags"), (list, tuple)):
        payload["tags"] = json.dumps(list(payload["tags"]))

    db = _connect()
    key = {"name": payload["name"], "source": payload["source"]}
    existing = db.companies.find_one(key, {"id": 1})
    if existing:
        updates = _set_of(payload, skip=("name", "source"))
        if updates:
            db.companies.update_one(key, {"$set": updates})
        return int(existing["id"])

    doc = {**payload, **key, "id": _next_id("companies"), "discovered_at": now(),
           "last_scanned_at": None}
    try:
        db.companies.insert_one(doc)
    except Exception:
        # Lost a race against a concurrent insert — take the winner's id.
        found = db.companies.find_one(key, {"id": 1})
        if found:
            return int(found["id"])
        raise
    return int(doc["id"])


def list_companies(limit: int = 200, source: str | None = None,
                   with_ats: bool = False) -> list[dict[str, Any]]:
    query: dict[str, Any] = {}
    if source:
        query["source"] = source
    if with_ats:
        query["ats_platform"] = {"$ne": None}
        query["ats_token"] = {"$ne": None}
    cur = _connect().companies.find(query).sort("discovered_at", -1).limit(int(limit))
    return _cleaned(cur)


def company(company_id: int) -> dict[str, Any] | None:
    return _clean(_connect().companies.find_one({"id": int(company_id)}))


def mark_company_scanned(company_id: int) -> None:
    _connect().companies.update_one({"id": int(company_id)},
                                    {"$set": {"last_scanned_at": now()}})


def _company_names() -> dict[int, dict[str, Any]]:
    return {int(c["id"]): c for c in _connect().companies.find(
        {}, {"id": 1, "name": 1, "domain": 1, "region": 1, "ats_platform": 1,
             "description": 1, "website": 1, "industry": 1})}


# --------------------------------------------------------------------------
# Jobs
# --------------------------------------------------------------------------

def upsert_job(data: dict[str, Any], *, company_name: str = "") -> int | None:
    if not data.get("url") or not data.get("title"):
        return None

    from . import sources

    payload = {k: data.get(k) for k in JOB_FIELDS}
    payload["remote"] = 1 if payload.get("remote") else 0

    if payload.get("posted_ts") is None:
        payload["posted_ts"] = sources.parse_posted_at(payload.get("posted_at"))
    if not payload.get("dedupe_hash"):
        name = company_name
        if not name and payload.get("company_id"):
            c = company(int(payload["company_id"]))
            name = (c or {}).get("name", "")
        payload["dedupe_hash"] = sources.dedupe_hash(
            name, payload.get("title") or "", payload.get("location") or "",
            url=payload.get("url") or "")

    db = _connect()
    key = {"url": payload["url"]}
    existing = db.jobs.find_one(key, {"id": 1})
    if existing:
        updates = _set_of(payload, skip=("url",))
        updates["remote"] = payload["remote"]          # 0 is meaningful here
        db.jobs.update_one(key, {"$set": updates})
        return int(existing["id"])

    doc = {**payload, "id": _next_id("jobs"), "discovered_at": now(),
           "fit_score": None, "fit_reason": None, "status": "new"}
    try:
        db.jobs.insert_one(doc)
    except Exception:
        found = db.jobs.find_one(key, {"id": 1})
        return int(found["id"]) if found else None
    return int(doc["id"])


def set_job_fit(job_id: int, score: float, reason: str, status: str) -> None:
    _connect().jobs.update_one(
        {"id": int(job_id)},
        {"$set": {"fit_score": float(score), "fit_reason": reason, "status": status}})


def set_job_status(job_id: int, status: str) -> None:
    _connect().jobs.update_one({"id": int(job_id)}, {"$set": {"status": status}})


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

    Returns the count and the resume files that are now orphaned, so the caller
    can remove them from disk.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=max(0, int(days)))).isoformat()
    query: dict[str, Any] = {"discovered_at": {"$lt": cutoff}}
    if keep_applied:
        query["status"] = {"$ne": "applied"}

    db = _connect()
    doomed = list(db.jobs.find(query, {"id": 1, "resume_path": 1, "status": 1}))
    resumes = [d["resume_path"] for d in doomed if d.get("resume_path")]
    if doomed:
        db.jobs.delete_many({"id": {"$in": [int(d["id"]) for d in doomed]}})
    return {"deleted": len(doomed), "resumes": resumes, "cutoff": cutoff}


# --------------------------------------------------------------------------
# Task queue — mirrors sqlite_store function for function
# --------------------------------------------------------------------------

def enqueue_task(kind: str, payload: dict[str, Any], *, dedupe_key: str,
                 priority: int = 0, delay_s: int = 0) -> int | None:
    """Queue one retryable unit of work. Idempotent on dedupe_key."""
    db = _connect()
    if db.tasks.find_one({"dedupe_key": dedupe_key}, {"id": 1}):
        return None
    policy = retry_policy(kind)
    due = (datetime.now(timezone.utc) + timedelta(seconds=delay_s)).isoformat()
    doc = {"id": _next_id("tasks"), "kind": kind, "payload": json.dumps(payload),
           "status": "pending", "attempts": 0, "max_attempts": policy["max_attempts"],
           "next_run_at": due, "last_error": None, "priority": int(priority),
           "dedupe_key": dedupe_key, "created_at": now(), "finished_at": None}
    try:
        db.tasks.insert_one(doc)
    except Exception:
        return None          # lost a race on the unique index — already queued
    return int(doc["id"])


def claim_due_tasks(limit: int = 50) -> list[dict[str, Any]]:
    """Atomically take the due tasks: mark running, return them."""
    db = _connect()
    cutoff = now()
    claimed: list[dict[str, Any]] = []
    for _ in range(int(limit)):
        doc = db.tasks.find_one_and_update(
            {"status": {"$in": ["pending", "failed"]}, "next_run_at": {"$lte": cutoff}},
            {"$set": {"status": "running"}},
            sort=[("priority", -1), ("next_run_at", 1)],
            return_document=True)
        if not doc:
            break
        doc.pop("_id", None)
        try:
            doc["payload"] = json.loads(doc.get("payload") or "{}")
        except json.JSONDecodeError:
            doc["payload"] = {}
        claimed.append(doc)
    return claimed


def complete_task(task_id: int) -> None:
    _connect().tasks.update_one(
        {"id": int(task_id)},
        {"$set": {"status": "done", "finished_at": now()}})


def fail_task(task_id: int, error: str) -> str:
    """Record a failure; back off exponentially, or mark dead past the cap.
    Returns the resulting status."""
    db = _connect()
    row = db.tasks.find_one({"id": int(task_id)})
    if not row:
        return "missing"
    attempts = int(row.get("attempts") or 0) + 1
    policy = retry_policy(row["kind"])
    if attempts >= int(row.get("max_attempts") or policy["max_attempts"]):
        status, due, fin = "dead", None, now()
    else:
        status = "failed"
        due = (datetime.now(timezone.utc)
               + timedelta(seconds=policy["backoff_base_s"] * (2 ** (attempts - 1)))).isoformat()
        fin = None
    db.tasks.update_one({"id": int(task_id)}, {"$set": {
        "status": status, "attempts": attempts, "last_error": (error or "")[:400],
        "next_run_at": due, "finished_at": fin}})
    return status


def task_stats() -> dict[str, int]:
    out: dict[str, int] = {}
    for doc in _connect().tasks.aggregate([{"$group": {"_id": "$status", "n": {"$sum": 1}}}]):
        out[str(doc["_id"])] = int(doc["n"])
    return out


def known_hashes() -> set[str]:
    """
    Every job already in the table, by dedupe hash.

    Discovery checks this before fetching a description or building a resume, so
    a job seen on a previous run costs nothing on this one.
    """
    cur = _connect().jobs.find({"dedupe_hash": {"$ne": None}}, {"dedupe_hash": 1})
    return {d["dedupe_hash"] for d in cur if d.get("dedupe_hash")}


def set_job_category(job_id: int, category: str | None) -> None:
    _connect().jobs.update_one({"id": int(job_id)}, {"$set": {"role_category": category}})


def set_job_description(job_id: int, description: str, source: str) -> None:
    _connect().jobs.update_one(
        {"id": int(job_id)},
        {"$set": {"description": description, "description_source": source}})


def set_job_recruiter(job_id: int, email: str, name: str = "") -> None:
    """Only ever called with an address that was actually found."""
    if not email:
        return
    _connect().jobs.update_one(
        {"id": int(job_id)},
        {"$set": {"recruiter_email": email, "recruiter_name": name or ""}})


def set_job_resume(job_id: int, path: str, version: str) -> None:
    _connect().jobs.update_one(
        {"id": int(job_id)},
        {"$set": {"resume_path": path, "resume_version": version,
                  "resume_built_at": now()}})


def set_job_applied(job_id: int, *, resume_version: str = "") -> None:
    _connect().jobs.update_one(
        {"id": int(job_id)},
        {"$set": {"status": "applied", "applied_at": now(),
                  "resume_version": resume_version or None, "failure_reason": None}})


def mark_job_failed(job_id: int, reason: str) -> None:
    """A form that could not be completed is recorded, never skipped silently."""
    _connect().jobs.update_one(
        {"id": int(job_id)},
        {"$set": {"status": "failed", "failure_reason": (reason or "")[:400]}})


def job(job_id: int) -> dict[str, Any] | None:
    row = _clean(_connect().jobs.find_one({"id": int(job_id)}))
    return _attach_company([row])[0] if row else None


def jobs_by_ids(job_ids: list[int]) -> list[dict[str, Any]]:
    ids = [int(i) for i in job_ids]
    rows = _attach_company(_cleaned(_connect().jobs.find({"id": {"$in": ids}})))
    order = {j: i for i, j in enumerate(ids)}
    return sorted(rows, key=lambda r: order.get(int(r["id"]), 1e9))


def _attach_company(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    companies = _company_names()
    for r in rows:
        with_job_defaults(r)
        c = companies.get(int(r.get("company_id") or -1)) or {}
        r["company_name"] = c.get("name")
        r.setdefault("domain", c.get("domain"))
        r["region"] = c.get("region")
        r["ats_platform"] = c.get("ats_platform")
    return rows


def jobs_needing_scoring(limit: int = 200) -> list[dict[str, Any]]:
    cur = _connect().jobs.find({"status": "new"}).sort("discovered_at", -1).limit(int(limit))
    return _attach_company(_cleaned(cur))


def applied_hashes() -> set[str]:
    cur = _connect().applications.find(
        {"job_hash": {"$ne": None}, "status": {"$in": ["submitted", "filled"]}, "dry_run": 0},
        {"job_hash": 1})
    return {d["job_hash"] for d in cur if d.get("job_hash")}


def jobs_to_apply(limit: int = 20, min_score: float = 55.0, *,
                  max_age_days: int | None = 3, require_posted_date: bool = True,
                  order: str = "recent") -> dict[str, Any]:
    cutoff = None
    if max_age_days is not None and max_age_days > 0:
        cutoff = int(time.time() - max_age_days * 86400)

    cur = _connect().jobs.find({
        "status": {"$in": ["matched", "queued"]},
        "fit_score": {"$gte": float(min_score)},
    }).sort("fit_score", -1)
    candidates = _attach_company(_cleaned(cur))

    seen = applied_hashes()
    fresh: list[dict[str, Any]] = []
    stale = undated = duplicate = 0

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
        fresh.sort(key=lambda j: (-(j.get("posted_ts") or 0), -(j.get("fit_score") or 0)))
    else:
        fresh.sort(key=lambda j: (-(j.get("fit_score") or 0), -(j.get("posted_ts") or 0)))

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


def list_jobs(limit: int = 100, status: str | None = None, *,
              category: str | None = None, source: str | None = None,
              q: str | None = None) -> list[dict[str, Any]]:
    query: dict[str, Any] = {}
    if status:
        # "not_applied" means open AND actionable: a role the experience gate
        # rejected is not something the user can apply to, so it does not belong
        # in the default view even though it is technically un-applied.
        query["status"] = ({"$nin": ["applied", "failed", "skipped", "duplicate"]}
                           if status == "not_applied" else status)
    if category:
        query["role_category"] = category
    if source:
        query["source"] = source
    if q:
        rx = {"$regex": re.escape(q), "$options": "i"}
        query["$or"] = [{"title": rx}, {"location": rx}, {"description": rx}]
    cur = _connect().jobs.find(query).sort([("posted_ts", -1), ("fit_score", -1)]).limit(int(limit))
    rows = _attach_company(_cleaned(cur))
    applied = applied_hashes()
    for r in rows:
        ts = r.get("posted_ts")
        r["age_days"] = round((time.time() - ts) / 86400.0, 1) if ts else None
        r["already_applied"] = bool(r.get("dedupe_hash") and r["dedupe_hash"] in applied)
    return rows


# --------------------------------------------------------------------------
# People
# --------------------------------------------------------------------------

def upsert_person(data: dict[str, Any]) -> int | None:
    payload = {k: data.get(k) for k in PERSON_FIELDS}
    if not payload.get("email"):
        return None
    payload["email"] = payload["email"].strip().lower()

    db = _connect()
    key = {"company_id": payload.get("company_id"), "email": payload["email"]}
    existing = db.people.find_one(key, {"id": 1})
    if existing:
        updates = _set_of(payload, skip=("company_id", "email"))
        if updates:
            db.people.update_one(key, {"$set": updates})
        return int(existing["id"])

    doc = {**payload, "id": _next_id("people"), "discovered_at": now(), "verified_at": None}
    doc.setdefault("email_status", "unknown")
    try:
        db.people.insert_one(doc)
    except Exception:
        found = db.people.find_one(key, {"id": 1})
        return int(found["id"]) if found else None
    return int(doc["id"])


def people_to_email(limit: int = 20) -> list[dict[str, Any]]:
    db = _connect()
    contacted = {d["person_id"] for d in db.outreach.find(
        {"status": {"$in": ["sent", "replied"]}}, {"person_id": 1}) if d.get("person_id")}

    rows = _cleaned(db.people.find({"email_status": {"$in": ["valid", "risky"]}}))
    rows = [r for r in rows if r["id"] not in contacted]

    companies = _company_names()
    for r in rows:
        c = companies.get(int(r.get("company_id") or -1)) or {}
        r["company_name"] = c.get("name")
        r["domain"] = c.get("domain")
        r["description"] = c.get("description")
        r["website"] = c.get("website")
        r["industry"] = c.get("industry")
        r["region"] = c.get("region")

    status_rank = {"valid": 0, "risky": 1}
    role_rank = {"founder": 0, "recruiter": 1}
    rows.sort(key=lambda r: (status_rank.get(r.get("email_status"), 2),
                             role_rank.get(r.get("role"), 2),
                             -(r.get("email_score") or 0)))
    return rows[:limit]


def list_people(limit: int = 200, status: str | None = None) -> list[dict[str, Any]]:
    query = {"email_status": status} if status else {}
    cur = _connect().people.find(query).sort("discovered_at", -1).limit(int(limit))
    rows = _cleaned(cur)
    companies = _company_names()
    for r in rows:
        c = companies.get(int(r.get("company_id") or -1)) or {}
        r["company_name"] = c.get("name")
        r["region"] = c.get("region")
    return rows


# --------------------------------------------------------------------------
# Applications & outreach
# --------------------------------------------------------------------------

def record_application(data: dict[str, Any]) -> int:
    payload = {k: data.get(k) for k in APPLICATION_FIELDS}
    for key in ("fields_filled", "unanswered"):
        if isinstance(payload.get(key), (dict, list)):
            payload[key] = json.dumps(payload[key])
    payload["dry_run"] = 1 if payload.get("dry_run") else 0
    doc = {**payload, "id": _next_id("applications"), "created_at": now(),
           "submitted_at": now() if payload.get("status") == "submitted" else None}
    _connect().applications.insert_one(doc)
    return int(doc["id"])


def record_outreach(data: dict[str, Any]) -> int:
    payload = {k: data.get(k) for k in OUTREACH_FIELDS}
    payload["dry_run"] = 1 if payload.get("dry_run") else 0
    payload["sequence_step"] = payload.get("sequence_step") or 1
    doc = {**payload, "id": _next_id("outreach"), "created_at": now(),
           "sent_at": now() if payload.get("status") == "sent" else None,
           "replied_at": None}
    _connect().outreach.insert_one(doc)
    return int(doc["id"])


def list_applications(limit: int = 100) -> list[dict[str, Any]]:
    db = _connect()
    rows = _cleaned(db.applications.find().sort("created_at", -1).limit(int(limit)))
    jobs = {int(j["id"]): j for j in db.jobs.find({}, {"id": 1, "title": 1, "url": 1})}
    companies = _company_names()
    for r in rows:
        j = jobs.get(int(r.get("job_id") or -1)) or {}
        r["title"] = j.get("title")
        r["url"] = j.get("url")
        r["company_name"] = (companies.get(int(r.get("company_id") or -1)) or {}).get("name")
    return rows


def list_outreach(limit: int = 100) -> list[dict[str, Any]]:
    db = _connect()
    rows = _cleaned(db.outreach.find().sort("created_at", -1).limit(int(limit)))
    people = {int(p["id"]): p for p in db.people.find({}, {"id": 1, "full_name": 1, "role": 1})}
    companies = _company_names()
    for r in rows:
        p = people.get(int(r.get("person_id") or -1)) or {}
        r["full_name"] = p.get("full_name")
        r["role"] = p.get("role")
        r["company_name"] = (companies.get(int(r.get("company_id") or -1)) or {}).get("name")
    return rows


# --------------------------------------------------------------------------
# Runs & stats
# --------------------------------------------------------------------------

def start_run(mode: str, options: dict[str, Any]) -> int:
    doc = {"id": _next_id("runs"), "mode": mode, "status": "running",
           "options": json.dumps(options, default=str), "stats": None, "error": None,
           "started_at": now(), "finished_at": None}
    _connect().runs.insert_one(doc)
    return int(doc["id"])


def finish_run(run_id: int, status: str, stats: dict[str, Any], error: str | None = None) -> None:
    _connect().runs.update_one(
        {"id": int(run_id)},
        {"$set": {"status": status, "stats": json.dumps(stats, default=str),
                  "error": error, "finished_at": now()}})


def list_runs(limit: int = 20) -> list[dict[str, Any]]:
    return _cleaned(_connect().runs.find().sort("started_at", -1).limit(int(limit)))


def stats() -> dict[str, Any]:
    db = _connect()

    def group(collection: str, field: str) -> dict[str, int]:
        pipeline = [{"$group": {"_id": f"${field}", "n": {"$sum": 1}}}]
        return {str(d["_id"]): int(d["n"]) for d in db[collection].aggregate(pipeline)
                if d["_id"] is not None}

    job_status = group("jobs", "status")
    return {
        "companies": db.companies.count_documents({}),
        "companiesBySource": group("companies", "source"),
        "companiesWithAts": db.companies.count_documents({"ats_token": {"$ne": None}}),
        "jobs": db.jobs.count_documents({}),
        "jobsByStatus": job_status,
        "matchedJobs": job_status.get("matched", 0) + job_status.get("queued", 0),
        "people": db.people.count_documents({}),
        "peopleByStatus": group("people", "email_status"),
        "applications": db.applications.count_documents({}),
        "applicationsSubmitted": db.applications.count_documents({"status": "submitted"}),
        "outreachSent": db.outreach.count_documents({"status": "sent"}),
        "outreachReplied": db.outreach.count_documents({"status": "replied"}),
    }
