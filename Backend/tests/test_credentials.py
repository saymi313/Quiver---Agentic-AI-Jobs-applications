"""
The employer-account credential store.

This holds passwords, so the tests that matter are the ones about what it does
*not* expose: `status()` and `list_domains()` must never carry a password out,
and a spent one-time code must not be replayed on the next run.
"""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture()
def creds(tmp_path, monkeypatch):
    from agent import credentials as mod
    # Point the store at a throwaway file so the test never touches the real one.
    monkeypatch.setattr(mod, "STORE", tmp_path / "credentials.json")
    return importlib.reload(mod) if False else mod


def test_domain_is_normalised():
    from agent import credentials
    assert credentials.domain_of("https://www.Acme.com/careers/1") == "acme.com"
    assert credentials.domain_of("ACME.WD1.myworkdayjobs.com") == "acme.wd1.myworkdayjobs.com"
    assert credentials.domain_of("") == ""


def test_credential_round_trips_but_status_hides_the_password(creds):
    creds.set_credential("acme.com", "me@x.com", "s3cret!")
    got = creds.get_credential("https://acme.com/jobs/5")  # a URL resolves to the domain
    assert got == {"username": "me@x.com", "password": "s3cret!"}

    status = creds.status()
    row = next(d for d in status["domains"] if d["domain"] == "acme.com")
    assert row["username"] == "me@x.com"
    assert row["hasPassword"] is True
    # The password must not appear anywhere in the safe summary.
    assert "s3cret!" not in repr(status)


def test_credential_requires_both_fields(creds):
    assert creds.set_credential("acme.com", "", "pw")["ok"] is False
    assert creds.set_credential("", "u", "pw")["ok"] is False


def test_delete_removes_it(creds):
    creds.set_credential("acme.com", "u", "p")
    assert creds.delete_credential("acme.com") is True
    assert creds.get_credential("acme.com") is None


def test_application_password_is_write_only_shaped(creds):
    assert creds.status()["hasApplicationPassword"] is False
    creds.set_application_password("Whatever-123!")
    assert creds.status()["hasApplicationPassword"] is True
    assert "Whatever-123!" not in repr(creds.status())


def test_generated_password_meets_the_rules(creds):
    pw = creds.generate_password()
    assert len(pw) >= 16
    assert any(c.islower() for c in pw) and any(c.isupper() for c in pw)
    assert any(c.isdigit() for c in pw) and any(c in "!@#$%^&*-_" for c in pw)


def test_otp_is_single_use(creds):
    creds.set_otp(42, "123456")
    assert creds.awaiting_otp() == [42]
    assert creds.pop_otp(42) == "123456"
    # Spent on read: a second run must not replay a stale code.
    assert creds.pop_otp(42) is None
    assert creds.awaiting_otp() == []
