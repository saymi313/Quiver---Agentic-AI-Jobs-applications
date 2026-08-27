"""
Tests for the Chrome Extension import endpoint and multi-step wizard helpers.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app
from agent.applier import _find_next_button, _match_rule


def test_extension_import_creates_job(fresh_store):
    client = TestClient(app)

    payload = {
        "url": "https://www.linkedin.com/jobs/view/4123456789",
        "title": "Senior React Developer",
        "company": "Stripe",
        "location": "Remote, Europe",
        "description": "We are looking for a Senior React Developer with TypeScript and Node.js experience.",
        "apply_url": "https://boards.greenhouse.io/stripe/jobs/123",
        "source": "linkedin",
    }

    res = client.post("/api/agent/extension/import", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert data["ok"] is True
    assert data["created"] is True
    assert data["title"] == "Senior React Developer"
    assert data["company"] == "Stripe"
    assert data["category"] == "frontend"
    assert data["id"] is not None

    # Importing the same URL again should return already tracked
    res2 = client.post("/api/agent/extension/import", json=payload)
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["created"] is False
    assert data2["message"] == "Already tracked."


def test_extension_import_rejects_bad_url():
    client = TestClient(app)
    res = client.post("/api/agent/extension/import", json={"url": "not-a-url"})
    assert res.status_code == 400


def test_eeoc_field_rule_matching():
    assert _match_rule("Gender") == "_eeoc_gender"
    assert _match_rule("Voluntary Self-Identification of Disability") == "_eeoc_disability"
    assert _match_rule("Veteran Status") == "_eeoc_veteran"
    assert _match_rule("Race / Ethnicity") == "_eeoc_race"

