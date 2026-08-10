"""Applier decision logic that needs no browser: is this an application form
at all, and which profile value answers a given field label."""

from __future__ import annotations

from agent import applier as A


def field(**kw):
    return {"type": "text", "label": "", "name": "", "required": False, **kw}


# ------------------------------------------------- is this an application?

def test_a_lone_email_box_is_not_an_application():
    """The bug this encodes: a job board's newsletter signup was filled with
    the candidate's address and nearly submitted as an application."""
    assert not A.looks_like_application([field(label="Email")])
    assert not A.looks_like_application([field(label="Email"), field(label="Subscribe")])
    assert not A.looks_like_application([])


def test_a_file_upload_settles_it():
    assert A.looks_like_application([field(type="file", label="Attach")])


def test_application_shaped_questions_count():
    for label in ("First Name", "Resume/CV", "Cover Letter", "LinkedIn Profile",
                  "Notice period", "Work authorization"):
        assert A.looks_like_application([field(label=label)]), label


def test_enough_fields_counts():
    assert A.looks_like_application([field(label=f"q{i}") for i in range(4)])
    assert not A.looks_like_application([field(label=f"q{i}") for i in range(3)])


# ------------------------------------------------------------ field rules

def test_country_and_city_beat_the_general_location_rule():
    """Order matters: `_match_rule` returns the first pattern that hits, and
    a Greenhouse form asks for Country and Location (City) separately."""
    assert A._match_rule("Country*") == "_country"
    assert A._match_rule("Location (City)*") == "_city"
    assert A._match_rule("City") == "_city"
    assert A._match_rule("Location") == "location"


def test_identity_rules_still_hold():
    assert A._match_rule("First Name*") == "_first_name"
    assert A._match_rule("Last Name") == "_last_name"
    assert A._match_rule("Email*") == "email"
    assert A._match_rule("Phone*") == "phone"
    assert A._match_rule("Nothing recognisable") is None


def test_apply_link_text_matches_real_button_labels():
    for label in ("Apply", "Apply Now", "Apply now", "Apply for this job",
                  "I'm interested", "Submit application"):
        assert A.APPLY_LINK_TEXT.match(label), label
    for label in ("Apply filters", "How to apply for a visa", "Applications"):
        assert not A.APPLY_LINK_TEXT.match(label), label
