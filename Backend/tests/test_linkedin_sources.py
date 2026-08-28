import pytest
from unittest.mock import patch, MagicMock
from agent import sources, runner, store
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


def test_sources_status_endpoint():
    response = client.get("/api/agent/sources/status")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert any(s["id"] == "linkedin" for s in data["sources"])
    assert any(s["id"] == "weworkremotely" for s in data["sources"])
    assert any(s["id"] == "jobicy" for s in data["sources"])


def test_linkedin_connect_endpoint():
    response = client.post("/api/agent/linkedin/connect", json={
        "profile_url": "https://linkedin.com/in/usairam-saeed",
        "li_at": "test_cookie_value"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["connected"] is True
    assert data["profile_url"] == "https://linkedin.com/in/usairam-saeed"


def test_classify_region_pakistan():
    assert sources.classify_region("Karachi, Pakistan") == "pk"
    assert sources.classify_region("Islamabad, Islāmābād, Pakistan") == "pk"
    assert sources.classify_region("Lahore, Punjab") == "pk"
    assert sources.classify_region("Remote (Worldwide)") == "remote"


@patch("agent.sources.requests.get")
def test_fetch_jobicy_mocked(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "jobs": [
            {
                "jobTitle": "Full Stack Engineer",
                "companyName": "TechCo",
                "url": "https://jobicy.com/jobs/123",
                "jobGeo": "Worldwide",
                "jobDescription": "Build full stack React and Node.js applications.",
                "pubDate": "2026-08-28",
            }
        ]
    }
    mock_get.return_value = mock_resp

    results = sources.fetch_jobicy(limit=5, keywords=["Full Stack"])
    assert len(results) == 1
    assert results[0]["name"] == "TechCo"
    assert results[0]["_job"]["title"] == "Full Stack Engineer"
    assert results[0]["_job"]["remote"] is True
