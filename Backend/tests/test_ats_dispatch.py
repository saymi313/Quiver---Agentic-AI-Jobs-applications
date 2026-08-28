"""
Tests for direct ATS API dispatch (Greenhouse, Lever, Ashby, Workable).
"""

from pathlib import Path
from agent import ats_dispatch


def test_can_direct_dispatch_greenhouse():
    url = "https://boards.greenhouse.io/datadog/jobs/5123456"
    plat, params = ats_dispatch.can_direct_dispatch(url)
    assert plat == "greenhouse"
    assert params == {"board": "datadog", "job_id": "5123456"}


def test_can_direct_dispatch_lever():
    url = "https://jobs.lever.co/stripe/a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    plat, params = ats_dispatch.can_direct_dispatch(url)
    assert plat == "lever"
    assert params == {"company": "stripe", "posting_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"}


def test_can_direct_dispatch_ashby():
    url = "https://jobs.ashbyhq.com/openai/98765432-abcd-1234-5678-abcdef012345"
    plat, params = ats_dispatch.can_direct_dispatch(url)
    assert plat == "ashby"
    assert params == {"company": "openai", "job_id": "98765432-abcd-1234-5678-abcdef012345"}


def test_can_direct_dispatch_workable():
    url = "https://apply.workable.com/spotify/j/ABC123XYZ/"
    plat, params = ats_dispatch.can_direct_dispatch(url)
    assert plat == "workable"
    assert params == {"account": "spotify", "shortcode": "ABC123XYZ"}


def test_direct_apply_lever_dry_run():
    job = {
        "id": 999,
        "apply_url": "https://jobs.lever.co/acme/12345678-abcd",
        "title": "Software Engineer",
        "company_name": "Acme",
    }
    profile = {
        "full_name": "Usairam Saeed",
        "email": "usairam@example.com",
        "phone": "+447123456789",
        "linkedin": "https://linkedin.com/in/usairam",
    }
    res = ats_dispatch.direct_apply(job, profile, None, "I am interested in this role.", dry_run=True)
    assert res is not None
    assert res["status"] == "needs_review"
    assert res["direct_api"] is True
    assert res["fields_filled"]["email"] == "usairam@example.com"
