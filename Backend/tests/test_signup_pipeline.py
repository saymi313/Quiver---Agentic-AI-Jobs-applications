"""
The auto-signup pipeline (FR-A5, extended).

When a site will not show the form until you register, the agent creates one
account from a single stored identity, reuses it everywhere, and — when a fresh
account triggers a code or a confirmation link it cannot invent — parks the job
in an "input required" queue and waits for the user to hand the piece back.

These pin the parts that can be tested without a live browser: the wall markers,
identity resolution, and the durable queues that carry state between runs.
"""

from __future__ import annotations

import pytest

from agent import applier


# --------------------------------------------------------------------------
# Wall detection
# --------------------------------------------------------------------------

def test_signup_markers_catch_registration_walls():
    for text in ["Create an account to continue",
                 "Sign up", "Don't have an account?",
                 "Register now to apply", "Create your profile"]:
        assert applier.SIGNUP_MARKERS.search(text), text


def test_verify_markers_catch_the_confirmation_link_page():
    for text in ["Check your email to confirm your account",
                 "We've sent you a confirmation link",
                 "Click the verification link to activate",
                 "A link to activate your account is on its way"]:
        assert applier.VERIFY_MARKERS.search(text), text


def test_verify_markers_do_not_fire_on_an_ordinary_form():
    assert not applier.VERIFY_MARKERS.search(
        "First name, last name, email, upload your resume, submit application")


# --------------------------------------------------------------------------
# Identity resolution
# --------------------------------------------------------------------------

@pytest.fixture()
def creds(tmp_path, monkeypatch):
    from agent import credentials as mod
    monkeypatch.setattr(mod, "STORE", tmp_path / "credentials.json")
    return mod


def _settings(monkeypatch, signup):
    from agent import store
    monkeypatch.setattr(store, "get_setting",
                        lambda key, default=None: signup if key == "signup" else default)


def test_identity_needs_both_an_email_and_a_password(creds, monkeypatch):
    _settings(monkeypatch, {"enabled": True, "email": "me@x.com"})
    # No application password set yet — half an identity is no identity.
    assert creds.signup_identity() is None
    creds.set_application_password("Str0ng!pass")
    assert creds.signup_identity() == {"username": "me@x.com", "password": "Str0ng!pass"}


def test_identity_falls_back_to_the_profile_email(creds, monkeypatch):
    _settings(monkeypatch, {"enabled": True, "email": ""})
    creds.set_application_password("Str0ng!pass")
    ident = creds.signup_identity(fallback_email="profile@x.com")
    assert ident["username"] == "profile@x.com"


def test_signup_can_be_turned_off(creds, monkeypatch):
    _settings(monkeypatch, {"enabled": False, "email": "me@x.com"})
    assert creds.signup_enabled() is False


# --------------------------------------------------------------------------
# The input-required queue and the parked link
# --------------------------------------------------------------------------

def test_pending_input_queue_round_trips(creds):
    creds.set_pending_input(7, "otp", domain="acme.com", prompt="Paste the code.")
    creds.set_pending_input(9, "link", domain="beta.com", prompt="Paste the link.")

    rows = creds.awaiting_input()
    assert {r["job_id"] for r in rows} == {7, 9}
    assert creds.pending_input(7)["kind"] == "otp"

    creds.clear_pending_input(7)
    assert creds.pending_input(7) is None
    assert {r["job_id"] for r in creds.awaiting_input()} == {9}


def test_confirmation_link_is_single_use(creds):
    creds.set_confirmation_link(3, "https://acme.com/verify?t=abc")
    assert creds.pop_confirmation_link(3) == "https://acme.com/verify?t=abc"
    # Spent on read — a second run must not replay a stale link.
    assert creds.pop_confirmation_link(3) is None
