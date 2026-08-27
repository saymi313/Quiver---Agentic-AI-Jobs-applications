"""
Tests for Autonomous Alumni & Warm Referral Outreach Engine.
"""

from __future__ import annotations

from agent import alumni_outreach


def test_warm_referral_messages_generation():
    res = alumni_outreach.generate_warm_referral_messages(
        candidate_name="Usairam Saeed",
        target_company="Linear",
        role_title="Full Stack Engineer",
        contact_name="Sarah Jenkins",
        alma_mater="FAST-NUCES",
        skills_highlight="React, Node.js, and Python backend systems",
    )

    assert res["company"] == "Linear"
    assert res["role"] == "Full Stack Engineer"
    assert "FAST-NUCES" in res["alma_mater"]

    variants = res["variants"]
    assert "alumni" in variants
    assert "technical_peer" in variants
    assert "hiring_manager" in variants

    # Check that FAST-NUCES is mentioned in the alumni pitch
    assert "FAST-NUCES" in variants["alumni"]["body"]
    assert "Linear" in variants["alumni"]["body"]
    assert "Sarah" in variants["alumni"]["body"]
    assert "Usairam Saeed" in variants["alumni"]["body"]

    # Check that technical peer pitch contains engineering details
    assert "React, Node.js, and Python" in variants["technical_peer"]["body"]

