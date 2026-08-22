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


def test_a_willingness_to_move_question_is_relocation_not_sponsorship():
    # "visa" would otherwise route this to requires_sponsorship and answer it
    # backwards; a willingness-to-move question is about relocating.
    assert A._match_rule("Would you be willing to go through the visa process and move?") \
        == "willing_to_relocate"
    assert A._match_rule("Are you willing to relocate?") == "willing_to_relocate"
    assert A._match_rule("Open to relocation") == "willing_to_relocate"
    # A genuine sponsorship question still reads as sponsorship.
    assert A._match_rule("Do you require visa sponsorship?") == "requires_sponsorship"


def test_choice_rule_answers_relocation_from_the_profile():
    profile = {"willing_to_relocate": "Yes", "requires_sponsorship": "No"}
    assert A._choice_rule_answer(
        "Would you be willing to go through the visa process and move?", profile) == "Yes"
    assert A._choice_rule_answer("Do you require sponsorship?", profile) == "No"


def test_apply_link_text_matches_real_button_labels():
    for label in ("Apply", "Apply Now", "Apply now", "Apply for this job",
                  "I'm interested", "Submit application"):
        assert A.APPLY_LINK_TEXT.match(label), label


def test_apply_link_text_matches_german_labels():
    # The EU boards this reaches (arbeitnow → Personio) label the apply link in
    # the employer's language; missing these is how a German form was never
    # reached.
    for label in ("Bewerben", "Jetzt bewerben", "Auf diese Stelle bewerben"):
        assert A.APPLY_LINK_TEXT.match(label), label


def test_reveal_and_consent_labels():
    # The button that opens an inline form, in English and German.
    for label in ("Apply for this job", "Apply now", "Bewerben", "Jetzt bewerben"):
        assert A.REVEAL_FORM_LABELS.match(label), label
    # Cookie/consent buttons that gate EU forms.
    for label in ("Accept all", "Allow all cookies", "Alle akzeptieren",
                  "Akzeptieren", "Tout accepter"):
        assert A.CONSENT_LABELS.match(label), label
    # A plain "Submit" is not a consent button.
    assert not A.CONSENT_LABELS.match("Submit")
    for label in ("Apply filters", "How to apply for a visa", "Applications"):
        assert not A.APPLY_LINK_TEXT.match(label), label
