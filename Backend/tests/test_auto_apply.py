"""
Auto Apply, and the guarantee that makes it safe to have at all.

Tsenta's version picks roles and submits them. Jobenzy's picks roles and
*proposes* them. The difference is the whole feature, so most of what is worth
testing here is what the proposer must never do.
"""

from __future__ import annotations

import pytest

from agent import runner
from agent.schema import PROPOSAL_DECISIONS


# ------------------------------------------------- the structural guarantee

def test_applying_is_not_schedulable():
    """No cadence, however misconfigured, may submit an application. This is
    enforced by the whitelist rather than by anyone remembering."""
    from api import scheduler

    assert "agent_apply" not in scheduler.SCHEDULABLE
    assert "agent_propose" in scheduler.SCHEDULABLE


def test_the_dispatcher_refuses_anything_off_the_whitelist():
    from api import scheduler

    with pytest.raises(AssertionError):
        scheduler._dispatch("agent_apply", {"job_ids": [1]})


def test_proposing_never_calls_the_applier(monkeypatch, fresh_store):
    """The one test that matters. If `propose` ever reaches `apply_to_ids`,
    the review queue has become decoration."""
    from agent import applier

    monkeypatch.setattr(applier, "apply_to_ids",
                        lambda *a, **k: pytest.fail("propose must never submit"))
    monkeypatch.setattr(applier, "apply_to_job",
                        lambda *a, **k: pytest.fail("propose must never open a form"))

    fresh_store.set_setting("auto_apply", {"enabled": True, "min_score": 0,
                                           "daily_cap": 5, "require_resume": False})
    cid = fresh_store.upsert_company({"name": "Acme", "source": "manual"})
    jid = fresh_store.upsert_job({"company_id": cid, "title": "Backend Engineer",
                                  "url": "https://acme.dev/j/1", "source": "greenhouse"},
                                 company_name="Acme")
    fresh_store.set_job_status(jid, "matched")

    out = runner.propose(log=lambda _: None)
    assert out["proposed"] == 1
    assert fresh_store.job(jid)["proposed_at"], "the job should be in the queue"
    assert fresh_store.job(jid)["proposal_decision"] is None, "and undecided"


def test_apply_still_refuses_without_explicit_ids(capsys):
    """The guard that predates Auto Apply, still in place underneath it."""
    from agent import applier

    out = applier.apply_to_ids([], log=lambda _: None)
    assert out["attempted"] == 0


# ------------------------------------------------------- what gets proposed

def _seed(store, *, score, category="backend", resume=True, approved=None,
          status="matched", url="https://acme.dev/j/x"):
    cid = store.upsert_company({"name": "Acme", "source": "manual"})
    jid = store.upsert_job({"company_id": cid, "title": "Backend Engineer",
                            "url": url, "source": "greenhouse",
                            "role_category": category}, company_name="Acme")
    store.set_job_status(jid, status)
    store.set_job_score(jid, score, "test") if hasattr(store, "set_job_score") else None
    if resume:
        store.set_job_resume(jid, "/tmp/r.pdf", "v1", approved=approved)
    import agent.sqlite_store as s
    with s.tx() as c:
        c.execute("UPDATE jobs SET fit_score=? WHERE id=?", (score, jid))
    return jid


def test_score_threshold_is_respected(fresh_store):
    fresh_store.set_setting("auto_apply", {"enabled": True, "min_score": 70,
                                           "daily_cap": 10, "require_resume": False})
    low = _seed(fresh_store, score=50, url="https://acme.dev/j/low")
    high = _seed(fresh_store, score=90, url="https://acme.dev/j/high")

    runner.propose(log=lambda _: None)
    assert fresh_store.job(low)["proposed_at"] is None
    assert fresh_store.job(high)["proposed_at"] is not None


def test_daily_cap_stops_the_run(fresh_store):
    fresh_store.set_setting("auto_apply", {"enabled": True, "min_score": 0,
                                           "daily_cap": 2, "require_resume": False})
    for i in range(5):
        _seed(fresh_store, score=90, url=f"https://acme.dev/j/{i}")

    out = runner.propose(log=lambda _: None)
    assert out["proposed"] == 2, "the cap is a cap, not a suggestion"
    assert len(fresh_store.proposals()) == 2


def test_off_by_default_and_does_nothing_when_off(fresh_store):
    from agent.schema import DEFAULT_SETTINGS

    assert DEFAULT_SETTINGS["auto_apply"]["enabled"] is False
    _seed(fresh_store, score=99)
    out = runner.propose(log=lambda _: None)
    assert out["proposed"] == 0
    assert fresh_store.proposals() == []


def test_a_resume_awaiting_review_is_not_proposed(fresh_store):
    """Proposing it would produce a decision the user cannot act on: the
    applier refuses an unapproved resume anyway."""
    fresh_store.set_setting("auto_apply", {"enabled": True, "min_score": 0,
                                           "daily_cap": 10, "require_resume": True})
    jid = _seed(fresh_store, score=90, resume=True, approved=False)
    runner.propose(log=lambda _: None)
    assert fresh_store.job(jid)["proposed_at"] is None


def test_categories_filter_when_set(fresh_store):
    fresh_store.set_setting("auto_apply", {"enabled": True, "min_score": 0,
                                           "daily_cap": 10, "require_resume": False,
                                           "categories": ["frontend"]})
    backend = _seed(fresh_store, score=90, category="backend",
                    url="https://acme.dev/j/b")
    frontend = _seed(fresh_store, score=90, category="frontend",
                     url="https://acme.dev/j/f")
    runner.propose(log=lambda _: None)
    assert fresh_store.job(backend)["proposed_at"] is None
    assert fresh_store.job(frontend)["proposed_at"] is not None


def test_a_rejected_proposal_is_not_offered_again(fresh_store):
    """Re-proposing something the user said no to is how an assistant becomes
    a nuisance."""
    fresh_store.set_setting("auto_apply", {"enabled": True, "min_score": 0,
                                           "daily_cap": 10, "require_resume": False})
    jid = _seed(fresh_store, score=90)
    runner.propose(log=lambda _: None)
    assert fresh_store.decide_proposal(jid, "rejected")

    runner.propose(log=lambda _: None)
    assert fresh_store.job(jid)["proposal_decision"] == "rejected"
    assert fresh_store.proposals() == [], "a decided row has left the queue"


# ------------------------------------------------------------- the decision

def test_only_the_two_decisions_are_accepted(fresh_store):
    jid = _seed(fresh_store, score=90)
    fresh_store.propose_job(jid, "test")
    assert fresh_store.decide_proposal(jid, "approved") is True
    assert fresh_store.decide_proposal(jid, "maybe") is False
    assert set(PROPOSAL_DECISIONS) == {"approved", "rejected"}


def test_undecided_is_the_default_queue_view(fresh_store):
    a = _seed(fresh_store, score=90, url="https://acme.dev/j/a")
    b = _seed(fresh_store, score=80, url="https://acme.dev/j/b")
    fresh_store.propose_job(a, "test")
    fresh_store.propose_job(b, "test")
    fresh_store.decide_proposal(b, "approved")

    waiting = fresh_store.proposals()
    assert [r["id"] for r in waiting] == [a]
    assert [r["id"] for r in fresh_store.proposals("approved")] == [b]
