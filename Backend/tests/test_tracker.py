"""
The tracker's new surface: manual applications, and the inbox as a searchable
store of whole messages.

Both are things a row set is easy to get subtly wrong — a manual application
that does not show its own title because the code assumed a job behind it, or a
search that matches everything because a clause was dropped. Each test asserts
on the rows that come back, not just their count.
"""

from __future__ import annotations


# ---- manual applications --------------------------------------------------

def test_manual_application_carries_its_own_title(fresh_store):
    app_id = fresh_store.add_manual_application({
        "title": "Product Designer", "company_name": "Figma",
        "tracker_status": "interviewing", "url": "https://figma.com/jobs/1",
    })
    row = fresh_store.application(app_id)
    # No job row behind it, so the title and company must come from the
    # application's own columns.
    assert row["title"] == "Product Designer"
    assert row["company_name"] == "Figma"
    assert row["tracker_status"] == "interviewing"
    assert row["source"] == "manual"


def test_manual_application_appears_in_the_tracker(fresh_store):
    fresh_store.add_manual_application({"title": "Backend Engineer", "company_name": "Acme"})
    rows = fresh_store.tracked_applications(50)
    assert any(r["title"] == "Backend Engineer" and r["company_name"] == "Acme" for r in rows)


def test_manual_application_defaults_a_bad_stage_to_applied(fresh_store):
    app_id = fresh_store.add_manual_application({"title": "Role", "tracker_status": "nonsense"})
    assert fresh_store.application(app_id)["tracker_status"] == "applied"


# ---- messages: body + search ---------------------------------------------

def _seed_message(store, **over):
    base = {
        "message_id": over.get("message_id", "<m1@x>"),
        "from_addr": "recruiter@acme.com",
        "from_domain": "acme.com",
        "subject": "Interview invitation",
        "snippet": "We would like to schedule a call",
        "body": "We would like to schedule a call about your application to Acme.",
        "klass": "interview",
        "confidence": 0.9,
        "received_at": "2026-08-22T10:00:00+00:00",
    }
    base.update(over)
    return store.record_message(base)


def test_get_message_returns_the_full_body(fresh_store):
    mid = _seed_message(fresh_store)
    row = fresh_store.get_message(mid)
    assert row["body"].endswith("your application to Acme.")
    assert row["subject"] == "Interview invitation"


def test_message_search_matches_subject_body_and_sender(fresh_store):
    _seed_message(fresh_store, message_id="<a@x>", subject="Interview invitation",
                  body="scheduling a call")
    _seed_message(fresh_store, message_id="<b@x>", subject="Application received",
                  from_addr="no-reply@boltjobs.com", body="thanks for applying to Bolt")

    assert len(fresh_store.list_messages(q="interview")) == 1
    assert len(fresh_store.list_messages(q="Bolt")) == 1      # body
    assert len(fresh_store.list_messages(q="boltjobs")) == 1  # sender
    assert len(fresh_store.list_messages(q="zzznomatch")) == 0
    assert len(fresh_store.list_messages()) == 2              # no query = all


# ---- completeness ---------------------------------------------------------

def test_profile_completeness_counts_and_lists_gaps():
    from agent.schema import profile_completeness

    full = {k: "x" for k, _ in __import__("agent.schema", fromlist=["PROFILE_IMPORTANT"]).PROFILE_IMPORTANT}
    assert profile_completeness(full)["percent"] == 100
    assert profile_completeness(full)["missing"] == []

    partial = dict(full)
    del partial["phone"]
    del partial["linkedin"]
    out = profile_completeness(partial)
    assert out["percent"] < 100
    assert {m["key"] for m in out["missing"]} == {"phone", "linkedin"}
