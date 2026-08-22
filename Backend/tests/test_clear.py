"""
The deliberate clear actions.

Different from the age-based purge: this is "start clean" on request, and its
whole risk is deleting more than intended. So the tests pin exactly what a clear
keeps — applied and saved jobs by default — and that a full wipe really is full.
"""

from __future__ import annotations


def _job(store, title, *, url, status=None, saved=0):
    cid = store.upsert_company({"name": "Acme", "source": "yc"})
    jid = store.upsert_job({"company_id": cid, "title": title, "url": url, "source": "yc",
                            "saved": saved}, company_name="Acme")
    if status:
        store.set_job_status(jid, status)
    if saved:
        store.set_job_saved(jid, True)
    return jid


def test_clear_jobs_keeps_applied_and_saved_by_default(fresh_store):
    _job(fresh_store, "New Role", url="https://a.dev/1")
    _job(fresh_store, "Applied Role", url="https://a.dev/2", status="applied")
    _job(fresh_store, "Saved Role", url="https://a.dev/3", saved=1)

    out = fresh_store.clear_jobs()
    assert out["deleted"] == 1 and out["kept"] == 2
    titles = sorted(j["title"] for j in fresh_store.list_jobs(50))
    assert titles == ["Applied Role", "Saved Role"]


def test_clear_jobs_full_wipe(fresh_store):
    _job(fresh_store, "New Role", url="https://a.dev/1")
    _job(fresh_store, "Applied Role", url="https://a.dev/2", status="applied")
    _job(fresh_store, "Saved Role", url="https://a.dev/3", saved=1)

    out = fresh_store.clear_jobs(keep_applied=False, keep_saved=False)
    assert out["deleted"] == 3 and out["kept"] == 0
    assert fresh_store.list_jobs(50) == []


def test_clear_jobs_returns_orphaned_resumes(fresh_store):
    cid = fresh_store.upsert_company({"name": "Acme", "source": "yc"})
    jid = fresh_store.upsert_job({"company_id": cid, "title": "R", "url": "https://a.dev/9",
                                  "source": "yc", "resume_path": "/tmp/tailored.pdf"},
                                 company_name="Acme")
    out = fresh_store.clear_jobs(keep_applied=False, keep_saved=False)
    assert "/tmp/tailored.pdf" in out["resumes"]


def test_clear_tracker_empties_applications_and_messages(fresh_store):
    fresh_store.add_manual_application({"title": "Role", "company_name": "Acme"})
    fresh_store.record_message({"message_id": "<m@x>", "from_addr": "r@acme.com",
                                "subject": "Hi", "snippet": "hi", "klass": "interview",
                                "received_at": "2026-08-22T10:00:00+00:00"})
    out = fresh_store.clear_tracker()
    assert out["applications"] == 1 and out["messages"] == 1
    assert fresh_store.tracked_applications(50) == []
    assert fresh_store.list_messages() == []
