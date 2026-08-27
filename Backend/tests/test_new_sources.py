"""
Tests for newly added job sources: StillHiring, HiringCafe, and Contra.
"""

from __future__ import annotations

import pytest
from agent import sources


def test_stillhiring_collector_schema():
    """Verify StillHiring collector returns correctly formatted board entry objects."""
    results = sources.fetch_stillhiring(limit=5)
    assert isinstance(results, list)
    for entry in results:
        assert "name" in entry
        assert entry["source"] == "directory"
        assert entry["source_ref"] == "stillhiring"
        assert "_job" in entry
        job = entry["_job"]
        assert "title" in job
        assert "url" in job
        assert job["source"] == "stillhiring"


def test_contra_collector_schema():
    """Verify Contra collector returns correctly formatted board entry objects."""
    results = sources.fetch_contra(limit=5)
    assert isinstance(results, list)
    for entry in results:
        assert "name" in entry
        assert entry["source"] == "directory"
        assert entry["source_ref"] == "contra"
        assert "_job" in entry
        job = entry["_job"]
        assert "title" in job
        assert "url" in job
        assert job["source"] == "contra"


def test_board_entry_formatting():
    entry = sources._board_entry(
        name="Acme Corp",
        source="hiringcafe",
        location="Remote",
        remote=True,
        title="Fullstack Engineer",
        url="https://hiringcafe.com/job/fullstack-acme-123",
        description="Looking for an engineer.",
        tags=["python", "react"],
        posted_at=None,
    )
    assert entry["name"] == "Acme Corp"
    assert entry["source_ref"] == "hiringcafe"
    assert entry["_job"]["title"] == "Fullstack Engineer"
    assert entry["_job"]["remote"] is True
    assert entry["_job"]["source"] == "hiringcafe"

