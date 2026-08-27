"""
Tests for Local Vector RAG Matcher.
"""

from __future__ import annotations

import pytest
from agent import rag_matcher


def test_rag_empty_inputs():
    assert rag_matcher.rank_bullets_by_relevance("", []) == []
    assert rag_matcher.rank_bullets_by_relevance("Some job text", []) == []
    assert rag_matcher.rank_bullets_by_relevance("", ["Built React apps"]) == []


def test_rag_semantic_ranking():
    jd = "Looking for a Senior Backend Engineer proficient in Python, FastAPI, Docker, and PostgreSQL databases."
    bullets = [
        "Led frontend development using Vue.js, Tailwind CSS, and Figma mockups.",
        "Architected scalable Python FastAPI microservices with PostgreSQL and Docker containers.",
        "Created marketing campaigns and analyzed user retention in Google Analytics.",
        "Optimized SQL queries and database indexes in PostgreSQL, reducing query latency by 40%.",
    ]

    results = rag_matcher.rank_bullets_by_relevance(jd, bullets, top_k=2)

    assert len(results) == 2
    # The FastAPI + Docker + PostgreSQL bullet must be ranked #1
    assert "FastAPI" in results[0]["text"]
    assert results[0]["score"] > results[1]["score"]
    assert results[0]["rank"] == 1
    assert "python" in [k.lower() for k in results[0]["matched_keywords"]] or "fastapi" in [k.lower() for k in results[0]["matched_keywords"]]


def test_rag_dict_bullets():
    jd = "Full stack developer with React, TypeScript, and AWS Lambda serverless experience."
    bullets = [
        {"id": 1, "text": "Implemented serverless microservices using AWS Lambda and TypeScript."},
        {"id": 2, "text": "Designed high-fidelity user flows in Adobe XD."},
    ]

    results = rag_matcher.rank_bullets_by_relevance(jd, bullets, top_k=2)
    assert len(results) == 2
    assert results[0]["original"]["id"] == 1
    assert results[0]["score"] > 0.0

