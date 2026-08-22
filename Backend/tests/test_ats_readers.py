"""
The ATS board readers, driven offline from recorded fixtures (NFR-4).

A reader normalises one vendor's board into Quiver's job shape. The failure
mode is silent: a vendor tweaks a field name, the reader keeps returning rows
that are subtly wrong — a blank location, a link that 404s — and nothing
complains until an application goes to the wrong place. So each reader is pinned
against a saved response, network patched out, and asserted on the fields that
actually get used: title, location, remote, url, description.

Adding a reader means adding a fixture and a case here. That is the whole
discipline NFR-4 asks for: a new system cannot regress the others, because every
one of them is checked without a network.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent import sources

FIX = Path(__file__).parent / "fixtures" / "ats"


def _load(name: str):
    text = (FIX / name).read_text(encoding="utf-8")
    return json.loads(text) if name.endswith(".json") else text


@pytest.fixture()
def no_network(monkeypatch):
    """Any reader that reaches for the network in a test is a bug in the test."""
    def boom(*a, **k):
        raise AssertionError("a reader hit the network instead of the fixture")
    monkeypatch.setattr(sources, "_get", boom)


def _patch_get(monkeypatch, payload):
    monkeypatch.setattr(sources, "_get", lambda *a, **k: payload)


def test_greenhouse(monkeypatch):
    _patch_get(monkeypatch, _load("greenhouse.json"))
    jobs = sources.fetch_ats_jobs("greenhouse", "acme")
    assert len(jobs) == 2
    j = jobs[0]
    assert j["title"] == "Senior Backend Engineer"
    assert j["remote"] is True and "Remote" in j["location"]
    assert j["url"].endswith("/jobs/101")
    assert "APIs" in j["description"] and "<b>" not in j["description"]  # html stripped
    assert j["source"] == "greenhouse"


def test_lever(monkeypatch):
    _patch_get(monkeypatch, _load("lever.json"))
    jobs = sources.fetch_ats_jobs("lever", "acme")
    assert len(jobs) == 1
    j = jobs[0]
    assert j["title"] == "Full Stack Engineer"
    assert j["remote"] is True
    assert j["apply_url"].endswith("/apply")
    assert "React" in j["description"]


def test_ashby_skips_unlisted(monkeypatch):
    _patch_get(monkeypatch, _load("ashby.json"))
    jobs = sources.fetch_ats_jobs("ashby", "acme")
    # The unlisted second posting must be dropped.
    assert [j["title"] for j in jobs] == ["Machine Learning Engineer"]
    assert jobs[0]["employment_type"] == "FullTime"
    assert "PyTorch" in jobs[0]["description"]


def test_bamboohr(monkeypatch):
    _patch_get(monkeypatch, _load("bamboohr.json"))
    jobs = sources.fetch_ats_jobs("bamboohr", "acme")
    assert [j["title"] for j in jobs] == ["DevOps Engineer", "Remote Data Analyst"]
    assert jobs[0]["location"] == "Austin, TX, USA"
    assert jobs[0]["url"] == "https://acme.bamboohr.com/careers/501"
    assert jobs[1]["remote"] is True  # "Remote" in the country field


def test_personio_xml(monkeypatch):
    _patch_get(monkeypatch, _load("personio.xml"))
    jobs = sources.fetch_ats_jobs("personio", "acme")
    assert len(jobs) == 1
    j = jobs[0]
    assert j["title"] == "Backend Engineer (m/f/d)"
    assert j["location"] == "Berlin"
    assert j["department"] == "Engineering"
    # The description is assembled from the feed's sections, html stripped.
    assert "Build services in Python" in j["description"]
    assert "5+ years experience" in j["description"]
    assert "<p>" not in j["description"]


def _detect(blob: str):
    for platform, pattern in sources.ATS_PATTERNS:
        m = pattern.search(blob)
        if m:
            return platform, m.group(1)
    return None, None


def test_detection_recognises_the_new_systems():
    # The discovery patterns resolve a board URL to the right platform + token,
    # so a company page linking to one is picked up.
    assert _detect("careers at https://acme.bamboohr.com/careers/501") == ("bamboohr", "acme")
    assert _detect("apply at https://acme.jobs.personio.de/job/9001") == ("personio", "acme")


def test_every_registered_platform_has_a_reader():
    # Detection and fetching must not drift apart: a platform the patterns can
    # name but no reader can fetch is a silent dead end, so every detected
    # platform must resolve to a fetcher.
    readers = {"greenhouse", "lever", "ashby", "smartrecruiters", "workable",
               "recruitee", "breezy", "rippling", "bamboohr", "personio"}
    for platform, _ in sources.ATS_PATTERNS:
        assert platform in readers, f"{platform} can be detected but has no reader"


def test_unknown_platform_returns_empty(no_network):
    # A platform with no reader must return [] without touching the network.
    assert sources.fetch_ats_jobs("nonesuch", "acme") == []
    assert sources.fetch_ats_jobs("greenhouse", "") == []
