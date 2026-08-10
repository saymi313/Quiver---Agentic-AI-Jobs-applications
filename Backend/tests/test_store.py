"""Store round-trips on a throwaway SQLite file: dedupe, retention, the task
queue, and the LLM budget tables."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _seed_job(store, *, url="https://acme.dev/jobs/1", status=None,
              discovered_days_ago=0):
    cid = store.upsert_company({"name": "Acme", "source": "yc"})
    jid = store.upsert_job({"company_id": cid, "title": "Backend Engineer",
                            "url": url, "source": "yc"}, company_name="Acme")
    if status:
        store.set_job_status(jid, status)
    if discovered_days_ago:
        import agent.sqlite_store as s
        old = (datetime.now(timezone.utc)
               - timedelta(days=discovered_days_ago)).isoformat()
        with s.tx() as c:
            c.execute("UPDATE jobs SET discovered_at=? WHERE id=?", (old, jid))
    return cid, jid


def test_job_upsert_fills_dedupe_hash(fresh_store):
    _, jid = _seed_job(fresh_store)
    row = fresh_store.job(jid)
    assert row["dedupe_hash"] and len(row["dedupe_hash"]) == 20
    assert row["company_name"] == "Acme"


def test_purge_protects_applied(fresh_store):
    _, old_applied = _seed_job(fresh_store, url="https://a.dev/1",
                               status="applied", discovered_days_ago=10)
    _, old_new = _seed_job(fresh_store, url="https://a.dev/2",
                           discovered_days_ago=10)
    _, fresh = _seed_job(fresh_store, url="https://a.dev/3")

    fresh_store.purge_old_jobs(3, keep_applied=True)
    assert fresh_store.job(old_applied) is not None, "applied row must survive"
    assert fresh_store.job(old_new) is None, "stale unapplied row must go"
    assert fresh_store.job(fresh) is not None


def test_task_queue_semantics(fresh_store):
    s = fresh_store
    tid = s.enqueue_task("jd_fetch", {"job_id": 1}, dedupe_key="jd:1")
    assert tid is not None
    assert s.enqueue_task("jd_fetch", {"job_id": 1}, dedupe_key="jd:1") is None, \
        "duplicate dedupe_key must be rejected"

    claimed = s.claim_due_tasks(10)
    assert len(claimed) == 1 and claimed[0]["payload"] == {"job_id": 1}
    assert s.claim_due_tasks(10) == [], "a running task must not be re-claimed"

    # Failure backs off — not immediately due again.
    assert s.fail_task(claimed[0]["id"], "boom") == "failed"
    assert s.claim_due_tasks(10) == []

    # Past max_attempts the task dies.
    import agent.sqlite_store as sq
    with sq.tx() as c:
        c.execute("UPDATE tasks SET next_run_at=?, attempts=2 WHERE id=?",
                  ("2000-01-01T00:00:00+00:00", claimed[0]["id"]))
    again = s.claim_due_tasks(10)
    assert len(again) == 1
    assert s.fail_task(again[0]["id"], "boom") == "dead"
    assert s.task_stats().get("dead") == 1


def test_delayed_task_not_due_yet(fresh_store):
    fresh_store.enqueue_task("resume_build", {"job_id": 2},
                             dedupe_key="rb:2", delay_s=3600)
    assert fresh_store.claim_due_tasks(10) == []


def test_llm_usage_and_cache(fresh_store):
    s = fresh_store
    s.llm_spend("classify")
    s.llm_spend("classify")
    s.llm_spend("apply")
    spent = s.llm_spent_today()
    assert spent == {"classify": 2, "apply": 1, "total": 3}

    s.llm_cache_put("key1", "answer")
    assert s.llm_cache_get("key1") == "answer"
    assert s.llm_cache_get("nope") is None
