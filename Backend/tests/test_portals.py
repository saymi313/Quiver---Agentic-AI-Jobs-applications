"""
The portal capability table, and the field logic driven against recorded HTML.

The fixture tests are the point of NFR-4. Every portal fix so far was found by
pointing a browser at a live posting, which means the next change to the fill
logic could silently break a portal that used to work and nobody would know
until an application failed. A recorded page has no network, no rate limit and
no posting that closes underneath the test.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent import applier, portals

FIXTURES = Path(__file__).parent / "fixtures" / "portals"


# ----------------------------------------------------------- the capability table

def test_every_portal_declares_both_capabilities():
    for p in portals.PORTALS:
        assert isinstance(p["detects"], bool), p["slug"]
        assert p["submits"] in (portals.PROVEN, portals.LIKELY,
                                portals.UNPROVEN, portals.NO), p["slug"]
        assert p["name"], p["slug"]


def test_slugs_are_unique():
    slugs = [p["slug"] for p in portals.PORTALS]
    assert len(slugs) == len(set(slugs))


def test_detection_claims_match_the_readers_that_exist():
    """`detects: True` must mean a reader is actually wired up, or the table is
    telling the user something the code cannot do."""
    from agent import sources

    readers = {"greenhouse", "lever", "ashby", "smartrecruiters", "workable",
               "recruitee", "breezy", "rippling"}
    aggregators = {"arbeitnow", "remoteok", "remotive", "weworkremotely",
                   "workingnomads", "landingjobs", "themuse", "yc", "hn"}
    for p in portals.PORTALS:
        if p["detects"]:
            assert p["slug"] in readers | aggregators, (
                f"{p['slug']} claims detection with no reader behind it")
    # And every board reader is represented in the table.
    for slug in readers:
        assert portals.can_detect(slug), f"{slug} has a reader but the table says no"


def test_aggregators_are_not_claimed_as_submittable():
    for slug in ("arbeitnow", "remoteok", "yc", "hn"):
        assert portals.submit_support(slug) == portals.NO
        assert not portals.can_submit(slug)


def test_unknown_portal_is_unproven_not_broken():
    """A system nobody has catalogued should still be attempted: the generic
    driver handles most standard forms, and refusing would mean never learning
    which ones work."""
    assert portals.submit_support("something-new") == portals.UNPROVEN
    assert portals.can_submit("something-new") is True
    assert portals.name_of("something-new") == "something-new"


def test_proven_means_an_application_actually_went_through():
    proven = {p["slug"] for p in portals.PORTALS if p["submits"] == portals.PROVEN}
    assert proven == {"greenhouse", "ashby"}, (
        "only claim `proven` for a system a real application has been submitted "
        "through; everything else is `likely` or `unproven`")


# ------------------------------------------------------- walls and one-time codes

def test_a_one_time_code_pauses_rather_than_fails():
    """A code the site just sent is something the user can supply. Recording it
    as a failure buried applications that were one step from going through."""
    for text in ("Enter the 6 digit code we sent you",
                 "Your verification code is on its way",
                 "We emailed you a code to continue"):
        assert applier.OTP_MARKERS.search(text), text


def test_ordinary_form_text_is_not_mistaken_for_a_code():
    for text in ("Enter your postal code", "Country code", "Please enter your details"):
        assert not applier.OTP_MARKERS.search(text), text


def test_login_wall_markers():
    for text in ("Sign in to apply", "You must be logged in", "Create an account to apply"):
        assert applier.LOGIN_MARKERS.search(text), text


# --------------------------------------------------- the fill logic, offline

pytestmark_playwright = pytest.mark.skipif(
    not (FIXTURES / "greenhouse.html").is_file(),
    reason="no recorded portal fixture")


@pytest.fixture(scope="module")
def greenhouse_page():
    """A real Greenhouse application form, served from disk."""
    playwright = pytest.importorskip("playwright.sync_api")
    if not (FIXTURES / "greenhouse.html").is_file():
        pytest.skip("no recorded greenhouse fixture")

    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context(viewport={"width": 1440, "height": 1200}).new_page()
        # file:// rather than a server: the point is that this needs nothing.
        page.goto((FIXTURES / "greenhouse.html").resolve().as_uri(),
                  wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(400)
        yield page
        browser.close()


def test_field_collection_finds_the_real_questions(greenhouse_page):
    fields = applier._collect_fields(greenhouse_page)
    labels = " ".join((f["label"] or "") for f in fields).lower()
    assert len(fields) >= 8, f"only found {len(fields)} fields on a real form"
    for expected in ("first name", "last name", "email"):
        assert expected in labels, f"{expected!r} missing from {labels[:200]}"


def test_field_collection_skips_the_furniture(greenhouse_page):
    """The bug this pins down: a newsletter box and a phone widget's own
    country search were being offered up as application questions."""
    fields = applier._collect_fields(greenhouse_page)
    for f in fields:
        blob = f"{f.get('label', '')} {f.get('name', '')} {f.get('id', '')}".lower()
        assert "newsletter" not in blob and "subscribe" not in blob, blob
        assert f["type"] != "search", blob
        assert "iti-" not in (f.get("id") or ""), f.get("id")


def test_the_form_reads_as_an_application(greenhouse_page):
    fields = applier._collect_fields(greenhouse_page)
    assert applier.looks_like_application(fields)


def test_identity_fields_map_to_profile_keys(greenhouse_page):
    """Every field the rules should answer, answered — checked against a real
    form rather than against labels invented for a test."""
    fields = applier._collect_fields(greenhouse_page)
    matched = {applier._match_rule(f["label"] or f["name"]) for f in fields}
    for key in ("_first_name", "_last_name", "email"):
        assert key in matched, f"{key} unmatched on a real Greenhouse form"


def test_no_captcha_wall_on_a_normal_form(greenhouse_page):
    """The regression that mattered most: Greenhouse's invisible reCAPTCHA
    badge was read as a challenge, so every one of its forms was abandoned."""
    assert applier.diagnose_wall(greenhouse_page) is None
