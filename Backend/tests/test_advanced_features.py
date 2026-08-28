"""
Unit tests for Advanced Job Hunter Features:
- Multi-profile resume routing
- Warm alumni outreach generation
- ATS keyword penetration audit
- Interview prep guide generator
"""

from fastapi.testclient import TestClient
from api.main import app
from agent import matcher, store


def test_resume_path_role_category():
    # Design category should select UI/UX resume
    design_path = matcher.resume_path("ui_ux")
    assert design_path is not None
    assert "UIUX" in design_path.name or "design" in design_path.name

    # Software Engineer category should select standard master resume
    swe_path = matcher.resume_path("fullstack")
    assert swe_path is not None


def test_outreach_endpoint():
    client = TestClient(app)
    store.init()
    cid = store.upsert_company({"name": "Acme Tech", "source": "test"})
    job_id = store.upsert_job({
        "company_id": cid,
        "url": "https://example.com/job/outreach-test",
        "title": "Senior React Engineer",
        "company_name": "Acme Tech",
        "location": "Remote",
        "role_category": "frontend",
        "skills": ["React", "TypeScript", "Node.js"],
        "source": "test",
    }, company_name="Acme Tech")

    resp = client.get(f"/api/agent/jobs/{job_id}/outreach")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["company"] == "Acme Tech"
    assert "pitches" in data
    assert "alumni" in data["pitches"]
    assert "technical_peer" in data["pitches"]
    assert "hiring_manager" in data["pitches"]


def test_ats_audit_endpoint():
    client = TestClient(app)
    store.init()
    job_id = store.upsert_job({
        "url": "https://example.com/job/ats-audit-test",
        "title": "Full Stack Developer",
        "company_name": "FinTech Corp",
        "location": "London, UK",
        "role_category": "fullstack",
        "description": "Looking for a Full Stack Developer skilled in TypeScript, React, Docker, and Kubernetes.",
        "skills": ["TypeScript", "React", "Docker", "Kubernetes"],
        "source": "test",
    })

    resp = client.get(f"/api/agent/jobs/{job_id}/ats-audit")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "skills_density" in data
    assert "matched_count" in data
    assert "missing_count" in data


def test_interview_prep_endpoint(monkeypatch):
    from agent import llm as agent_llm
    monkeypatch.setattr(agent_llm, "complete", lambda prompt, purpose="": '{"company_context": "FinTech leader", "behavioral_questions": [{"question": "Describe a system you scaled.", "star_tip": "Focus on metrics."}], "technical_questions": [{"topic": "Architecture", "question": "Design a high-throughput queue.", "key_concept": "Kafka partition"}], "questions_to_ask_interviewer": ["What is the main challenge?"]}')

    client = TestClient(app)
    store.init()
    job_id = store.upsert_job({
        "url": "https://example.com/job/prep-test",
        "title": "Backend Software Engineer",
        "company_name": "CloudScale Inc",
        "location": "Berlin, Germany",
        "role_category": "backend",
        "description": "We are seeking a backend engineer experienced in building distributed systems.",
        "skills": ["Node.js", "PostgreSQL", "Kafka"],
        "source": "test",
    })

    resp = client.get(f"/api/agent/jobs/{job_id}/interview-prep")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "guide" in data
    assert "behavioral_questions" in data["guide"]
    assert "technical_questions" in data["guide"]
