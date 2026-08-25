"""
The keyed aggregators — Adzuna and Jooble.

These add global reach through one clean feed, but only when their free keys are
present. The tests pin that contract (no key → nothing), that each provider's
response shape is mapped onto a job entry, and that the region pre-filter drops a
result outside the target regions before it is ever stored — all without a
network call.
"""

from __future__ import annotations

import pytest

from agent import sources

TARGETING = {"regions": ["eu", "uk", "me", "remote", "pk"],
             "exclude_locations": ["India", "United States", "USA", " US ", "Canada"]}


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    from agent import store
    monkeypatch.setattr(store, "get_setting",
                        lambda key, default=None: TARGETING if key == "targeting" else (default or {}))


ADZUNA_RESPONSE = {"results": [
    {"title": "Full Stack Engineer", "company": {"display_name": "Ocho"},
     "location": {"display_name": "Belfast, Northern Ireland"},
     "redirect_url": "https://adzuna.example/1", "created": "2026-08-24T14:42:50Z",
     "category": {"label": "IT Jobs"}, "description": "React and Node role"},
    {"title": "Backend Engineer", "company": {"display_name": "AcmeUS"},
     "location": {"display_name": "Austin, TX"},
     "redirect_url": "https://adzuna.example/2", "created": "2026-08-20T00:00:00Z",
     "category": {"label": "IT Jobs"}, "description": "node role"},
]}

JOOBLE_RESPONSE = {"jobs": [
    {"title": "Full Stack Developer", "location": "Remote", "company": "Booth",
     "type": "Full-time", "link": "https://jooble.example/1",
     "updated": "2026-08-24T00:00:00.0000000", "snippet": "react node"},
    {"title": "React Engineer", "location": "Dallas, TX", "company": "GTN",
     "type": "Full-time", "link": "https://jooble.example/2",
     "updated": "2026-08-17T00:00:00.0000000", "snippet": "react"},
]}


def test_adzuna_maps_and_drops_us(monkeypatch):
    monkeypatch.setenv("ADZUNA_APP_ID", "id")
    monkeypatch.setenv("ADZUNA_APP_KEY", "key")
    monkeypatch.setattr(sources, "_get", lambda url, params=None, **k: ADZUNA_RESPONSE)
    out: list = []
    sources._fetch_adzuna(out, ["react", "node"], 50, lambda *_: None)
    titles = [e["_job"]["title"] for e in out]
    # Belfast is kept; Austin, TX is dropped by the region pre-filter.
    assert "Full Stack Engineer" in titles
    assert "Backend Engineer" not in titles
    assert out[0]["_job"]["url"] == "https://adzuna.example/1"
    assert out[0]["_job"]["source"] == "adzuna"


def test_jooble_maps_and_drops_us(monkeypatch):
    monkeypatch.setenv("JOOBLE_API_KEY", "k")

    class _Resp:
        def raise_for_status(self): pass
        def json(self): return JOOBLE_RESPONSE
    monkeypatch.setattr("requests.post", lambda *a, **k: _Resp())

    out: list = []
    sources._fetch_jooble(out, ["react", "node"], 50, lambda *_: None)
    titles = [e["_job"]["title"] for e in out]
    assert "Full Stack Developer" in titles     # Remote → kept
    assert "React Engineer" not in titles        # Dallas, TX → dropped


def test_no_keys_means_no_calls(monkeypatch):
    monkeypatch.delenv("ADZUNA_APP_ID", raising=False)
    monkeypatch.delenv("ADZUNA_APP_KEY", raising=False)
    monkeypatch.delenv("JOOBLE_API_KEY", raising=False)
    out: list = []
    sources._fetch_adzuna(out, ["react"], 50, lambda *_: None)
    sources._fetch_jooble(out, ["react"], 50, lambda *_: None)
    assert out == []
