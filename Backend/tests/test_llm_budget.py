"""Budget shares, per-model day quotas and cache keys — no network involved."""

from __future__ import annotations

import json
import time

import pytest

import agent.llm as L

CAP = 100


class _FakeStore:
    """Just enough store for the budget and model-rotation code paths."""

    def __init__(self, spent: dict[str, int] | None = None,
                 model_state: dict[str, str] | None = None):
        self.spent = dict(spent or {})
        self.spent.setdefault("total", sum(
            v for k, v in self.spent.items() if k != "total"))
        self.settings = {"llm": {"daily_budget": CAP},
                         "llm_model_state": dict(model_state or {})}

    def llm_spent_today(self):
        return dict(self.spent)

    def get_setting(self, key, default=None):
        return self.settings.get(key, default if default is not None else {})

    def set_setting(self, key, value):
        self.settings[key] = value


@pytest.fixture()
def fake(monkeypatch):
    def use(**kwargs):
        st = _FakeStore(**kwargs)
        monkeypatch.setattr(L, "store", st)
        return st
    return use


# ------------------------------------------------ cross-provider fallback

def test_env_key_accepts_the_grok_misspelling(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("GROK_API_KEY", "gsk_test")
    assert L._env_key("groq") == "gsk_test"


def test_chain_adds_groq_behind_gemini(monkeypatch):
    monkeypatch.setenv("GROK_API_KEY", "gsk_test")
    chain = L._provider_chain({"provider": "gemini", "api_key": "gem_key"})
    assert [p for p, _ in chain] == ["gemini", "groq"]


def test_a_spent_gemini_day_rolls_to_groq(fake, monkeypatch):
    fake()
    monkeypatch.setenv("GROK_API_KEY", "gsk_test")
    monkeypatch.setattr(L, "config",
                        lambda: {"provider": "gemini", "api_key": "gem_key", "model": ""})
    monkeypatch.setattr(L, "_throttle", lambda: None)
    monkeypatch.setattr(L, "_check_budget", lambda purpose: None)

    def spent_gemini(*a, **k):
        raise L.LLMError("Every Gemini model has spent its free-tier day")
    monkeypatch.setattr(L, "_gemini", spent_gemini)
    monkeypatch.setattr(L, "_openai_compatible",
                        lambda *a, **k: "groq answered")

    assert L.complete("hi", purpose="apply") == "groq answered"


def test_no_key_anywhere_raises(fake, monkeypatch):
    fake()
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GROK_API_KEY", raising=False)
    monkeypatch.setattr(L, "config",
                        lambda: {"provider": "gemini", "api_key": "", "model": ""})
    with pytest.raises(L.LLMError):
        L.complete("hi", purpose="apply")


# --------------------------------------------------------------- budget

def test_bulk_purposes_cut_before_apply(fake):
    # extract has spent its 20% share; apply is exempt from shares.
    fake(spent={"extract": 20, "tailor": 5})
    with pytest.raises(L.LLMError, match="share"):
        L._check_budget("extract")
    L._check_budget("apply")
    L._check_budget("tailor")


def test_share_is_per_purpose_not_total(fake):
    """One purpose exhausting its share must not block a different one."""
    fake(spent={"extract": 20})
    with pytest.raises(L.LLMError):
        L._check_budget("extract")
    L._check_budget("classify")     # its own share is untouched


def test_hard_cap_stops_everything(fake):
    fake(spent={"apply": CAP})
    for purpose in ("classify", "tailor", "outreach", "apply", "general"):
        with pytest.raises(L.LLMError, match="Daily LLM budget spent"):
            L._check_budget(purpose)


def test_nothing_blocked_when_fresh(fake):
    fake()
    for purpose in ("classify", "tailor", "outreach", "apply", "general"):
        L._check_budget(purpose)


# ---------------------------------------------------------- model quotas

def test_quota_scope_reads_googles_detail():
    day = {"error": {"details": [{
        "@type": "type.googleapis.com/google.rpc.QuotaFailure",
        "violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier",
                        "quotaValue": "20"}]}]}}
    minute = {"error": {"details": [{
        "@type": "type.googleapis.com/google.rpc.QuotaFailure",
        "violations": [{"quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"}]}]}}
    assert L._quota_scope(day) == "day"
    assert L._quota_scope(minute) == "minute"
    assert L._quota_scope({}) == "unknown"
    assert L._quota_scope({"error": {"details": [{"@type": "other"}]}}) == "unknown"


def test_resting_models_expire(fake):
    st = fake(model_state={"fresh": f"{time.time():.0f}",
                           "stale": f"{time.time() - L.REST_FOR_S - 60:.0f}",
                           "junk": "not-a-number"})
    resting = L._resting_models()
    assert resting == {"fresh"}, "a rest older than REST_FOR_S must expire"


def test_rest_model_persists_and_prunes(fake):
    st = fake(model_state={"stale": f"{time.time() - L.REST_FOR_S - 60:.0f}"})
    L._rest_model("gemini-3.6-flash")
    saved = st.settings["llm_model_state"]
    assert "gemini-3.6-flash" in saved
    assert "stale" not in saved, "expired entries must not accumulate"


class _Resp:
    def __init__(self, status, payload):
        self.status_code = status
        self.ok = 200 <= status < 300
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


DAY_429 = {"error": {"details": [{
    "@type": "type.googleapis.com/google.rpc.QuotaFailure",
    "violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}]}}
GOOD = {"candidates": [{"content": {"parts": [{"text": "READY"}]},
                        "finishReason": "STOP"}]}


def test_day_quota_rotates_to_the_next_model(fake, monkeypatch):
    """The whole point: a spent day on one model must not fail the call."""
    st = fake()
    tried: list[str] = []

    def fake_post(url, **kwargs):
        model = url.rsplit("/", 1)[-1].split(":")[0]
        tried.append(model)
        return _Resp(429, DAY_429) if model == L.GEMINI_FALLBACKS[0] else _Resp(200, GOOD)

    monkeypatch.setattr(L.requests, "post", fake_post)
    out = L._gemini("hi", "", None, L.GEMINI_FALLBACKS[0], "key")
    assert out == "READY"
    assert len(tried) == 2, f"should have moved on after one 429, tried {tried}"
    assert L.GEMINI_FALLBACKS[0] in st.settings["llm_model_state"]


def test_all_models_spent_is_not_retryable(fake, monkeypatch):
    fake()
    monkeypatch.setattr(L.requests, "post", lambda url, **kw: _Resp(429, DAY_429))
    with pytest.raises(L.LLMError) as excinfo:
        L._gemini("hi", "", None, L.GEMINI_FALLBACKS[0], "key")
    assert not excinfo.value.retryable, "a spent day must not be slept on and retried"
    assert "free-tier day" in str(excinfo.value)


def test_resting_models_are_skipped(fake, monkeypatch):
    """A model already known to be spent costs no round trip at all."""
    fake(model_state={L.GEMINI_FALLBACKS[0]: f"{time.time():.0f}"})
    tried: list[str] = []

    def fake_post(url, **kwargs):
        tried.append(url.rsplit("/", 1)[-1].split(":")[0])
        return _Resp(200, GOOD)

    monkeypatch.setattr(L.requests, "post", fake_post)
    L._gemini("hi", "", None, L.GEMINI_FALLBACKS[0], "key")
    assert L.GEMINI_FALLBACKS[0] not in tried
    assert tried == [L.GEMINI_FALLBACKS[1]]


# ----------------------------------------------------------------- cache

def test_cache_key_stability():
    k1 = L._cache_key("gemini", "m", "prompt", "sys", {"a": 1, "b": 2})
    k2 = L._cache_key("gemini", "m", "prompt", "sys", {"b": 2, "a": 1})
    assert k1 == k2, "schema key order must not change the cache key"
    assert k1 != L._cache_key("gemini", "m", "prompt2", "sys", {"a": 1})
    assert k1 != L._cache_key("groq", "m", "prompt", "sys", {"a": 1})
