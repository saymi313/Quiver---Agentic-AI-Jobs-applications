"""
The aggregators — Jooble and remote feeds.
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


JOOBLE_RESPONSE = {"jobs": [
    {"title": "Full Stack Developer", "location": "Remote", "company": "Booth",
     "type": "Full-time", "link": "https://jooble.example/1",
     "updated": "2026-08-24T00:00:00.0000000", "snippet": "react node"},
    {"title": "React Engineer", "location": "Dallas, TX", "company": "GTN",
     "type": "Full-time", "link": "https://jooble.example/2",
     "updated": "2026-08-17T00:00:00.0000000", "snippet": "react"},
]}


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
    monkeypatch.delenv("JOOBLE_API_KEY", raising=False)
    out: list = []
    sources._fetch_jooble(out, ["react"], 50, lambda *_: None)
    assert out == []
