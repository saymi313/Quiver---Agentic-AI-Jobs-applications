"""
Match notifications, the email half (FR-F7).

The two things worth pinning: a role is announced once, and a role is announced
only when it clears the bar. Both are about not training the user to ignore the
alert — the failure mode notifications have.
"""

from __future__ import annotations

import time

from agent import notify


def _job(store, title, score, *, url, status="matched"):
    cid = store.upsert_company({"name": "Acme", "source": "yc"})
    jid = store.upsert_job({"company_id": cid, "title": title, "url": url, "source": "yc",
                            "posted_ts": int(time.time())}, company_name="Acme")
    store.set_job_fit(jid, score, "seeded", status)
    return jid


def test_unnotified_matches_respects_the_bar_and_status(fresh_store):
    _job(fresh_store, "Strong Match", 90, url="https://a.dev/1")
    _job(fresh_store, "Weak Match", 50, url="https://a.dev/2")
    _job(fresh_store, "Applied Already", 95, url="https://a.dev/3", status="applied")

    got = fresh_store.unnotified_matches(min_score=75)
    assert [j["title"] for j in got] == ["Strong Match"]  # weak below bar, applied excluded


def test_marking_notified_stops_it_repeating(fresh_store):
    jid = _job(fresh_store, "Strong Match", 90, url="https://a.dev/1")
    assert len(fresh_store.unnotified_matches(min_score=75)) == 1
    fresh_store.mark_notified([jid])
    assert fresh_store.unnotified_matches(min_score=75) == []


def test_email_off_sends_nothing(fresh_store, monkeypatch):
    fresh_store.set_setting("notify", {"enabled": True, "email": False, "min_score": 75})
    _job(fresh_store, "Strong Match", 90, url="https://a.dev/1")
    out = notify.notify_new_matches(log=lambda *_: None)
    assert out["emailed"] == 0
    # And the match is left unmarked, so the desktop channel can still show it.
    assert len(fresh_store.unnotified_matches(min_score=75)) == 1


def test_email_on_sends_once_and_marks(fresh_store, monkeypatch):
    fresh_store.set_setting("notify", {"enabled": True, "email": True, "min_score": 75})
    _job(fresh_store, "Strong Match", 90, url="https://a.dev/1")

    sent = {}

    class FakeMailer:
        def __init__(self, *a): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def send(self, to, subject, body, attachment):
            sent.update(to=to, subject=subject, body=body)

    from agent import outreach
    monkeypatch.setattr(outreach, "credentials", lambda: ("me@gmail.com", "app-password-here"))
    monkeypatch.setattr(outreach, "Mailer", FakeMailer)

    out = notify.notify_new_matches(log=lambda *_: None)
    assert out["emailed"] == 1
    assert "Strong Match" in sent["body"] and sent["to"] == "me@gmail.com"
    # Marked, so a second run says there is nothing new.
    assert notify.notify_new_matches(log=lambda *_: None)["emailed"] == 0
