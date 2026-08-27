"""
Tests for Core AI endpoints: RAG ranking, Typst compile, and Alumni referral generation.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


def test_api_rag_rank_bullets():
    payload = {
        "job_description": "Senior Python Developer with FastAPI, Docker, and PostgreSQL experience.",
        "bullets": [
            "Architected FastAPI microservices with PostgreSQL databases.",
            "Designed logos and marketing banners.",
        ],
        "top_k": 2,
    }
    res = client.post("/api/agent/rag/rank_bullets", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["count"] == 2
    assert "FastAPI" in data["bullets"][0]["text"]
    assert data["bullets"][0]["score"] > 0.0


def test_api_alumni_referral():
    payload = {
        "company_name": "Motive",
        "role_title": "Software Engineer II",
        "contact_name": "Ali Khan",
        "alma_mater": "FAST-NUCES",
        "skills_highlight": "Distributed systems and Python APIs",
    }
    res = client.post("/api/agent/outreach/alumni_referral", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    variants = data["data"]["variants"]
    assert "alumni" in variants
    assert "FAST-NUCES" in variants["alumni"]["body"]
    assert "Motive" in variants["alumni"]["body"]


def test_api_typst_compile():
    payload = {
        "profile": {
            "full_name": "Usairam Saeed",
            "email": "saeed.usairam@gmail.com",
            "experience": [{"title": "Software Engineer", "company": "Tech", "bullets": ["Built backend APIs."]}],
        },
        "font": "times",
        "font_size": 10.5,
    }
    res = client.post("/api/agent/resume/typst_compile", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert "Usairam Saeed" in data["typSource"]

