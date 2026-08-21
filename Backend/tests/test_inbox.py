"""Reply linking and classification — the Track loop, without a mailbox.

Every test here runs offline. The IMAP half is a thin transport; the parts
worth protecting are which application a message gets attached to and what the
message is taken to mean, because both decide whether a pipeline stage moves.
"""

from __future__ import annotations

import pytest

from agent import inbox
from agent.schema import CLASS_TO_TRACKER, LINK_CONFIDENCE_THRESHOLD


def app(app_id, company, domain, title="Backend Engineer", message_id=None, submitted="2026-08-01"):
    return {"id": app_id, "job_id": app_id * 10, "company_id": app_id * 100,
            "company_name": company, "domain": domain, "title": title,
            "message_id": message_id, "submitted_at": submitted,
            "tracker_status": "applied"}


APPS = [
    app(1, "Acme Labs", "acmelabs.com", message_id="<sent-1@quiver>"),
    app(2, "Globex", "globex.io", title="Frontend Engineer"),
    app(3, "Initech", "initech.com", title="Full Stack Engineer"),
]


def msg(**kw):
    base = {"in_reply_to": None, "references": [], "from_domain": "", "subject": ""}
    return {**base, **kw}


# ------------------------------------------------------------------ linking

def test_threaded_reply_wins_outright():
    """A reply in our own thread is near-certain, even from an unrelated
    domain — recruiters forward and reply from personal addresses."""
    link = inbox.link_message(
        msg(in_reply_to="<sent-1@quiver>", from_domain="gmail.com"), APPS)
    assert link["application_id"] == 1
    assert link["linked_by"] == "thread"
    assert link["confidence"] > LINK_CONFIDENCE_THRESHOLD


def test_references_header_also_links():
    link = inbox.link_message(
        msg(references=["<other@x>", "<sent-1@quiver>"], from_domain="x.com"), APPS)
    assert link["application_id"] == 1


def test_sender_domain_links_when_unambiguous():
    link = inbox.link_message(msg(from_domain="globex.io", subject="Next steps"), APPS)
    assert link["application_id"] == 2
    assert link["linked_by"] == "domain"
    assert link["confidence"] > LINK_CONFIDENCE_THRESHOLD


def test_two_roles_at_one_company_use_the_title():
    apps = [app(4, "Acme Labs", "acmelabs.com", title="Backend Engineer"),
            app(5, "Acme Labs", "acmelabs.com", title="Data Platform Engineer")]
    link = inbox.link_message(
        msg(from_domain="acmelabs.com", subject="Your Backend Engineer application"), apps)
    assert link["application_id"] == 4
    assert link["confidence"] > LINK_CONFIDENCE_THRESHOLD


def test_ambiguous_company_match_is_not_trusted():
    """Two applications, no title to separate them: still linked so the message
    is readable, but below the threshold so it moves nothing."""
    apps = [app(6, "Acme Labs", "acmelabs.com", title="Backend Engineer",
                submitted="2026-08-01"),
            app(7, "Acme Labs", "acmelabs.com", title="Frontend Engineer",
                submitted="2026-08-05")]
    link = inbox.link_message(msg(from_domain="acmelabs.com", subject="Hello"), apps)
    assert link["application_id"] in (6, 7)
    assert link["confidence"] < LINK_CONFIDENCE_THRESHOLD


def test_ats_mailer_plus_company_in_subject_is_trusted():
    """The case that matters most in practice, and the one that was wrong.

    A real Interfere rejection arrived from no-reply@ashbyhq.com, so matching
    the sender against interfere.com failed and only the subject named the
    company. Scored as a weak company match it sat under the threshold and the
    rejection moved nothing. An ATS only mails you about applications you
    actually made, so this is a strong link."""
    link = inbox.link_message(
        msg(from_domain="ashbyhq.com", subject="Initech Application Update"), APPS)
    assert link["application_id"] == 3
    assert link["linked_by"] == "ats"
    assert link["confidence"] >= LINK_CONFIDENCE_THRESHOLD, "an ATS reply must be able to move a stage"


def test_ats_mailers_are_recognised():
    for domain in ("ashbyhq.com", "us.greenhouse-mail.io", "hire.lever.co",
                   "myworkday.com", "smartrecruiters.com", "teamtailor.com"):
        assert inbox.is_ats_mailer(domain), domain
    for domain in ("acmelabs.com", "gmail.com", "randomblog.com"):
        assert not inbox.is_ats_mailer(domain), domain


def test_company_name_in_subject_from_a_stranger_is_weak():
    """Anyone can put a company name in a subject line. Without an ATS or a
    domain behind it the message is filed next to the application to be read,
    but it is not allowed to move the stage."""
    link = inbox.link_message(
        msg(from_domain="newsletter.example.com", subject="Your application to Initech"), APPS)
    assert link["application_id"] == 3
    assert link["linked_by"] == "company"
    assert link["confidence"] < LINK_CONFIDENCE_THRESHOLD, "a subject match must not move a stage"


def test_unplaceable_message_links_to_nothing():
    link = inbox.link_message(msg(from_domain="random.example", subject="Newsletter"), APPS)
    assert link["application_id"] is None
    assert link["linked_by"] == "none"
    assert link["confidence"] == 0.0


def test_corporate_suffixes_do_not_block_a_match():
    apps = [app(8, "Globex Inc.", "globex.io")]
    link = inbox.link_message(msg(from_domain="globex.io", subject="Hi"), apps)
    assert link["application_id"] == 8


# ----------------------------------------------------------- classification

@pytest.mark.parametrize("subject,body,expected", [
    ("Update on your application",
     "Unfortunately we have decided to move forward with other candidates.", "rejection"),
    ("Regarding your application",
     "We will not be moving forward with your application at this time.", "rejection"),
    ("Interview invitation",
     "We would like to schedule a call this week. Please book a time.", "interview"),
    ("Interview request for the Backend Engineer role", "Are you free Thursday?", "interview"),
    ("Next steps", "Here is my calendly.com link to pick a time.", "interview"),
    ("Your coding challenge",
     "Please complete the take-home assessment on HackerRank.", "assessment"),
    ("Offer of employment", "We are pleased to offer you the position.", "offer"),
    ("Thanks for applying",
     "We have received your application and are reviewing it.", "acknowledgment"),
    ("Verify your email", "Please confirm your email to finish signing up.", "verification"),
    ("Reminder", "Action required: complete your application before Friday.", "reminder"),
    ("Delivery Status Notification (Failure)",
     "Address not found. Your message could not be delivered.", "bounce"),
])
def test_rules_classify_real_phrasings(subject, body, expected):
    klass, confidence, how = inbox.classify(subject, body, use_llm=False)
    assert klass == expected, f"{subject!r} -> {klass}"
    assert how == "rules"
    assert confidence >= 0.85


def test_rejection_beats_interview_when_both_appear():
    """"We will not be moving forward after your interview" is a rejection.
    Rule order is what guarantees this, so it is worth pinning down."""
    klass, _, _ = inbox.classify(
        "Following up",
        "Thank you for your interview. We will not be moving forward with your application.",
        use_llm=False)
    assert klass == "rejection"


def test_subject_match_scores_higher_than_body_match():
    """The same phrase is a stronger signal in the subject than in a body that
    may simply be quoting an earlier message."""
    klass, subject_conf, _ = inbox.classify(
        "Interview invitation", "Details attached.", use_llm=False)
    assert klass == "interview"
    _, body_conf, _ = inbox.classify(
        "Hello", "We would like to schedule a call.", use_llm=False)
    assert subject_conf > body_conf


def test_unknown_text_falls_through_without_the_llm():
    klass, confidence, how = inbox.classify("Hello", "Just checking in.", use_llm=False)
    assert klass == "other"
    assert how == "default"
    assert confidence < LINK_CONFIDENCE_THRESHOLD


# ------------------------------------------------------------ stage mapping

def test_only_unambiguous_classes_move_a_stage():
    assert CLASS_TO_TRACKER["interview"] == "interviewing"
    assert CLASS_TO_TRACKER["offer"] == "offer"
    assert CLASS_TO_TRACKER["rejection"] == "rejected"
    # These say nothing certain about where the application stands.
    for klass in ("acknowledgment", "reminder", "verification", "bounce", "other"):
        assert klass not in CLASS_TO_TRACKER


def test_stage_order_never_goes_backwards():
    order = inbox.STAGE_ORDER
    assert order["applied"] < order["interviewing"] < order["offer"]
    assert order["rejected"] > order["interviewing"]


def test_noise_senders_are_recognised():
    for sender in ("jobalerts@linkedin.com", "no-reply@linkedin.com",
                   "digest@indeed.com", "newsletter@company.com"):
        assert inbox.NOISE_SENDERS.search(sender), sender
    for sender in ("careers@acmelabs.com", "hr@globex.io", "jane.smith@initech.com"):
        assert not inbox.NOISE_SENDERS.search(sender), sender
