"""Budget ceilings and cache keys — no network involved."""

from __future__ import annotations

import pytest

import agent.llm as L


class _FakeStore:
    def __init__(self, spent_total: int):
        self._spent = spent_total

    def llm_spent_today(self):
        return {"total": self._spent}

    def get_setting(self, key, default=None):
        return {"daily_budget": 100}


@pytest.fixture()
def fake_store(monkeypatch):
    def use(spent: int):
        monkeypatch.setattr(L, "store", _FakeStore(spent))
    return use


def test_classify_cut_before_apply(fake_store):
    fake_store(70)  # 70% of a 100-call budget
    with pytest.raises(L.LLMError):
        L._check_budget("classify")
    L._check_budget("apply")        # apply runs to the full cap
    L._check_budget("tailor")       # tailor's ceiling is 85%


def test_everything_stops_at_the_cap(fake_store):
    fake_store(100)
    for purpose in ("classify", "tailor", "outreach", "apply", "general"):
        with pytest.raises(L.LLMError):
            L._check_budget(purpose)


def test_nothing_blocked_when_fresh(fake_store):
    fake_store(0)
    for purpose in ("classify", "tailor", "outreach", "apply", "general"):
        L._check_budget(purpose)


def test_cache_key_stability():
    k1 = L._cache_key("gemini", "m", "prompt", "sys", {"a": 1, "b": 2})
    k2 = L._cache_key("gemini", "m", "prompt", "sys", {"b": 2, "a": 1})
    assert k1 == k2, "schema key order must not change the cache key"
    assert k1 != L._cache_key("gemini", "m", "prompt2", "sys", {"a": 1})
    assert k1 != L._cache_key("groq", "m", "prompt", "sys", {"a": 1})
