"""
The agent's brain — a thin provider layer over free LLM endpoints.

Providers, in the order they are usually worth trying:

  gemini      Google AI Studio free tier. ~1,500 requests/day, no card.
              https://aistudio.google.com/apikey
  groq        Groq free tier, OpenAI-compatible. Very fast.
              https://console.groq.com/keys
  openrouter  One key, several ':free' models.
              https://openrouter.ai/keys
  ollama      Fully local, no signup, no network. http://localhost:11434

Everything goes through `complete()` (free text) or `complete_json()` (schema
constrained). Calls are made with `requests` so there is no extra SDK to keep
in step, and every provider degrades to a clear error string rather than
raising into the agent loop.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from typing import Any

import requests

from api.config import BASE_DIR

from . import env, store

TIMEOUT = 90

# --------------------------------------------------------------------------
# Budget, cache, throttle
# --------------------------------------------------------------------------
#
# The free tiers this runs on are quota-bound, and the scheduler can spend that
# quota unattended overnight. Four defences, all here so no call site can
# forget them:
#
#   throttle  a minimum interval between real provider calls, so a burst of
#             tailoring does not trip the per-minute limit and die on 429s.
#   budget    a daily call ceiling, plus a per-purpose share so one bulk job
#             cannot eat the day. Answering questions on a live application
#             form is never share-limited: failing mid-submit costs the most.
#   rotation  Gemini's daily allowance is per MODEL, so a model that reports
#             its day exhausted leaves the rotation and the next one is tried.
#   cache     classification and contact extraction are pure functions of
#             their input — the same page asked twice should cost one call.
#
# A budget refusal raises LLMError like any other failure; every caller
# already treats LLMError as "work without the model".

# Measured against this account, 2026-08: the free tier allows 20 requests per
# day *per model*, not the ~1,500 per key the docs' headline number suggests.
# `gemini-flash-latest` is an alias and shares its bucket with the model it
# points at, so the four fallbacks are really about three buckets.
GEMINI_FREE_PER_MODEL_PER_DAY = 20
DAILY_BUDGET_DEFAULT = 60
MIN_INTERVAL_S = 5.0

# The most of the daily budget any one purpose may spend on itself. These
# deliberately over-subscribe: on a quiet day a single purpose can take more
# than an equal split, but nothing can take everything. `apply` is exempt.
PURPOSE_SHARE: dict[str, float] = {
    "apply": 1.0,        # never share-limited — only the hard cap stops it
    "tailor": 0.60,
    "outreach": 0.30,
    "classify": 0.30,
    "extract": 0.20,     # contact extraction is bulk work; it goes first
}
DEFAULT_SHARE = 0.25

_throttle_lock = threading.Lock()
_last_call_at = 0.0


def _daily_budget() -> int:
    cfg = store.get_setting("llm", {}) or {}
    try:
        return max(1, int(cfg.get("daily_budget") or DAILY_BUDGET_DEFAULT))
    except (TypeError, ValueError):
        return DAILY_BUDGET_DEFAULT


def budget_status() -> dict[str, Any]:
    """Spend so far today against the cap — surfaced in /api/health."""
    try:
        spent = store.llm_spent_today()
    except Exception:
        spent = {"total": 0}
    cap = _daily_budget()
    return {"cap": cap, "spent": spent.get("total", 0),
            "remaining": max(0, cap - spent.get("total", 0)),
            "byPurpose": {k: v for k, v in spent.items() if k != "total"},
            "restingModels": sorted(_resting_models())}


def _check_budget(purpose: str) -> None:
    spent = store.llm_spent_today()
    cap = _daily_budget()
    total = spent.get("total", 0)
    if total >= cap:
        raise LLMError(
            f"Daily LLM budget spent ({total}/{cap} calls). It resets tomorrow; "
            f"raise llm.daily_budget in Settings if your quota allows more.")

    share = int(cap * PURPOSE_SHARE.get(purpose, DEFAULT_SHARE))
    mine = spent.get(purpose, 0)
    if share and mine >= share:
        raise LLMError(
            f"'{purpose}' has used its share of today's LLM budget "
            f"({mine}/{share} of {cap} calls). Other work can still run; this "
            f"purpose resumes tomorrow.")


# --------------------------------------------------------------------------
# Per-model day quota
# --------------------------------------------------------------------------
#
# A model that answers 429 with a per-day quota violation is put to rest
# rather than retried: its allowance is gone until Google's own reset, which
# happens on Pacific time while this store counts UTC days. Rather than model
# that mismatch, a resting model is simply re-checked after a few hours — an
# early re-check costs one rejected round trip, and a rejected request does
# not consume quota.

_MODEL_STATE_KEY = "llm_model_state"
REST_FOR_S = 4 * 3600


def _model_state() -> dict[str, str]:
    try:
        return dict(store.get_setting(_MODEL_STATE_KEY, {}) or {})
    except Exception:
        return {}


def _resting_models() -> set[str]:
    """Models whose daily quota reported empty recently."""
    now = time.time()
    resting: set[str] = set()
    for model, marked in _model_state().items():
        try:
            when = float(marked)
        except (TypeError, ValueError):
            continue
        if now - when < REST_FOR_S:
            resting.add(model)
    return resting


def _rest_model(model: str) -> None:
    state = {m: v for m, v in _model_state().items() if m in _resting_models()}
    state[model] = f"{time.time():.0f}"
    try:
        store.set_setting(_MODEL_STATE_KEY, state)
    except Exception:
        pass


def _quota_scope(payload: dict[str, Any]) -> str:
    """'day', 'minute' or 'unknown', read out of Google's QuotaFailure detail."""
    for detail in (payload.get("error", {}) or {}).get("details", []) or []:
        if not str(detail.get("@type", "")).endswith("QuotaFailure"):
            continue
        for violation in detail.get("violations", []) or []:
            quota_id = str(violation.get("quotaId", ""))
            if "PerDay" in quota_id:
                return "day"
            if "PerMinute" in quota_id:
                return "minute"
    return "unknown"


def _throttle() -> None:
    """At most one real provider call per MIN_INTERVAL_S, process-wide."""
    global _last_call_at
    with _throttle_lock:
        wait = _last_call_at + MIN_INTERVAL_S - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_call_at = time.monotonic()


def _cache_key(provider: str, model: str, prompt: str, system: str,
               schema: dict | None) -> str:
    blob = "\x1f".join([provider, model, system, prompt,
                        json.dumps(schema, sort_keys=True) if schema else ""])
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OLLAMA_URL = "http://localhost:11434/api/chat"

# Tried in order when the configured model 404s or is rate-limited. Free-tier
# model availability moves constantly — `gemini-flash-latest` tracks whatever
# the current flash model is, the rest are explicit anchors behind it.
# Verified against this account 2026-08: 3.6/3.5/latest/3.1-lite all answer,
# gemini-2.5-flash is closed to new keys and 2.0-flash is quota-exhausted.
GEMINI_FALLBACKS = [
    "gemini-flash-latest",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
]
# Verified live against this key, 2026-08: Groq has retired the Llama chat
# models for this account and serves GPT-OSS and Qwen instead. Ordered strongest
# first, with a smaller/faster one behind it.
GROQ_FALLBACKS = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.6-27b"]
OPENROUTER_FALLBACKS = ["meta-llama/llama-3.3-70b-instruct:free", "google/gemma-2-9b-it:free"]

# Where each provider's key is read from the environment. Groq accepts the
# common "GROK" misspelling too — a key that starts with `gsk_` is a Groq key
# whichever way the variable was named.
_PROVIDER_ENV: dict[str, tuple[str, ...]] = {
    "gemini": ("GEMINI_API_KEY",),
    "groq": ("GROQ_API_KEY", "GROK_API_KEY"),
    "openrouter": ("OPENROUTER_API_KEY",),
}
# The order fallback providers are tried in after the configured one.
_FALLBACK_ORDER = ("gemini", "groq", "openrouter")


def _env_key(provider: str) -> str:
    """The API key for a provider from the environment, or empty."""
    for name in _PROVIDER_ENV.get(provider, ()):
        value = os.environ.get(name, "")
        if value:
            return value
    return ""


def _provider_chain(cfg: dict[str, Any]) -> list[tuple[str, str]]:
    """
    The providers to try, in order: the configured one, then every other free
    provider whose key is present.

    This is the cross-provider fallback — when Gemini's daily quota is spent, the
    call rolls to Groq (or OpenRouter) rather than failing. A provider with no
    key is skipped; Ollama needs none, so it stands on its own.
    """
    primary = cfg.get("provider", "gemini")
    chain: list[tuple[str, str]] = []
    primary_key = (cfg.get("api_key") or "").strip() or _env_key(primary)
    if primary == "ollama" or primary_key:
        chain.append((primary, primary_key))
    for provider in _FALLBACK_ORDER:
        if provider == primary:
            continue
        key = _env_key(provider)
        if key:
            chain.append((provider, key))
    return chain


def _call_provider(provider: str, key: str, model: str, prompt: str,
                   system: str, schema: dict | None) -> str:
    """One real call to a single provider, throttled. Raises LLMError on failure."""
    if provider == "gemini":
        _throttle()
        return _gemini(prompt, system, schema, model or GEMINI_FALLBACKS[0], key)
    if provider == "groq":
        _throttle()
        return _openai_compatible(GROQ_URL, prompt, system, schema,
                                  model or GROQ_FALLBACKS[0], key, GROQ_FALLBACKS)
    if provider == "openrouter":
        _throttle()
        return _openai_compatible(
            OPENROUTER_URL, prompt, system, schema,
            model or OPENROUTER_FALLBACKS[0], key, OPENROUTER_FALLBACKS,
            {"HTTP-Referer": "http://localhost", "X-Title": "Quiver"})
    if provider == "ollama":
        return _ollama(prompt, system, schema, model)
    raise LLMError(f"Unknown provider '{provider}'.")


class LLMError(RuntimeError):
    """`retryable` means waiting and asking again could work — a per-minute
    rate limit. A daily quota is not retryable, and retrying one wastes 40
    seconds per call for nothing."""

    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


_ENV_LOADED = False




def config() -> dict[str, Any]:
    env.load()
    cfg = dict(store.DEFAULT_SETTINGS["llm"])
    cfg.update(store.get_setting("llm", {}) or {})
    if not cfg.get("api_key"):
        cfg["api_key"] = _env_key(cfg.get("provider", ""))
    return cfg


def available() -> tuple[bool, str]:
    cfg = config()
    provider = cfg.get("provider", "gemini")
    if provider == "ollama":
        try:
            requests.get("http://localhost:11434/api/tags", timeout=4).raise_for_status()
            return True, "Ollama is running locally."
        except Exception:
            return False, "Ollama is not reachable on localhost:11434. Start it with `ollama serve`."
    chain = _provider_chain(cfg)
    keyed = [p for p, k in chain if k]
    if keyed:
        head = chain[0][0]
        extra = [p for p in keyed if p != head]
        msg = f"{head} ready ({cfg.get('model')})."
        if extra:
            msg += f" Fallback: {', '.join(extra)}."
        return True, msg
    where = {
        "gemini": "https://aistudio.google.com/apikey",
        "groq": "https://console.groq.com/keys",
        "openrouter": "https://openrouter.ai/keys",
    }.get(provider, "")
    return False, f"No API key set for {provider}. Get a free one at {where} and paste it in Settings."


# --------------------------------------------------------------------------
# Providers
# --------------------------------------------------------------------------

def _gemini(prompt: str, system: str, schema: dict | None, model: str, key: str) -> str:
    body: dict[str, Any] = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        # Gemini 3.x models think before answering, and those thinking tokens
        # count against maxOutputTokens. An 8k cap silently starves the answer
        # on a long prompt: finishReason comes back MAX_TOKENS with empty parts.
        # These models allow 65k out, so leave real headroom.
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 32768},
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    if schema:
        body["generationConfig"]["responseMimeType"] = "application/json"
        body["generationConfig"]["responseSchema"] = _gemini_schema(schema)

    order = [model, *[m for m in GEMINI_FALLBACKS if m != model]]
    resting = _resting_models()
    # A model resting on an empty day quota is skipped outright; if every one
    # is resting the list would be empty, so fall back to trying them anyway
    # rather than refusing without asking.
    candidates = [m for m in order if m not in resting] or order

    last_error = ""
    exhausted: list[str] = []
    for candidate in candidates:
        resp = requests.post(
            GEMINI_URL.format(model=candidate),
            params={"key": key},
            json=body,
            timeout=TIMEOUT,
        )
        if resp.status_code == 404:
            last_error = f"model {candidate} not found"
            continue
        if resp.status_code == 429:
            # The daily allowance is per model, so a spent day on one model
            # says nothing about the next: rest this one and move along.
            try:
                scope = _quota_scope(resp.json())
            except Exception:
                scope = "unknown"
            if scope == "day":
                _rest_model(candidate)
                exhausted.append(candidate)
                last_error = f"{candidate}: daily quota spent"
                continue
            raise LLMError(
                f"{candidate} hit a per-minute rate limit. Waiting and retrying.",
                retryable=True)
        if resp.status_code in (500, 502, 503, 504):
            # A transient server-side spike ("UNAVAILABLE — high demand"), not a
            # spent quota. Worth waiting out and asking again, so one busy moment
            # does not sink a whole apply run's cover letter and answers.
            raise LLMError(f"Gemini {resp.status_code}: temporarily unavailable, retrying.",
                           retryable=True)
        if not resp.ok:
            raise LLMError(f"Gemini {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        candidates = data.get("candidates") or []
        if not candidates:
            block = (data.get("promptFeedback") or {}).get("blockReason")
            if block:
                raise LLMError(f"Gemini blocked the prompt ({block}).")
            raise LLMError(f"Gemini returned no candidates: {json.dumps(data)[:300]}")

        first = candidates[0]
        parts = first.get("content", {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts)
        if text.strip():
            return text

        # Empty output is a real failure, not an empty answer. Say which kind,
        # so it surfaces instead of silently becoming a default value.
        reason = first.get("finishReason", "unknown")
        if reason == "MAX_TOKENS":
            raise LLMError("Gemini hit the output limit before answering (thinking tokens "
                           "consumed the budget). Shorten the prompt or raise maxOutputTokens.")
        raise LLMError(f"Gemini returned no text (finishReason={reason}).")

    if exhausted:
        # Not retryable: waiting twenty seconds does not refill a day.
        raise LLMError(
            f"Every Gemini model has spent its free-tier day "
            f"({GEMINI_FREE_PER_MODEL_PER_DAY} requests per model): "
            f"{', '.join(exhausted)}. The allowance resets once a day. "
            f"Add a second provider in Settings (Groq is also free) to keep "
            f"working today.")
    raise LLMError(f"No usable Gemini model ({last_error}).")


def _gemini_schema(schema: dict) -> dict:
    """Gemini's responseSchema is OpenAPI-flavoured — strip what it rejects."""
    drop = {"additionalProperties", "$schema", "definitions", "$defs", "default", "examples"}
    if not isinstance(schema, dict):
        return schema
    out: dict[str, Any] = {}
    for key, value in schema.items():
        if key in drop:
            continue
        if key == "properties" and isinstance(value, dict):
            out[key] = {k: _gemini_schema(v) for k, v in value.items()}
        elif key == "items":
            out[key] = _gemini_schema(value)
        elif isinstance(value, dict):
            out[key] = _gemini_schema(value)
        else:
            out[key] = value
    return out


def _openai_compatible(url: str, prompt: str, system: str, schema: dict | None,
                       model: str, key: str, fallbacks: list[str],
                       extra_headers: dict | None = None) -> str:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    if schema:
        prompt = (f"{prompt}\n\nRespond with JSON only, matching this schema exactly:\n"
                  f"{json.dumps(schema)}")
    messages.append({"role": "user", "content": prompt})

    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    headers.update(extra_headers or {})

    last_error = ""
    for candidate in [model, *[m for m in fallbacks if m != model]]:
        body: dict[str, Any] = {"model": candidate, "messages": messages, "temperature": 0.4}
        if schema:
            body["response_format"] = {"type": "json_object"}
        resp = requests.post(url, headers=headers, json=body, timeout=TIMEOUT)
        if resp.status_code in (400, 404):
            last_error = f"{candidate}: {resp.text[:160]}"
            continue
        if resp.status_code == 429:
            raise LLMError("Provider rate limit hit. Wait a minute and retry.",
                           retryable=True)
        if not resp.ok:
            raise LLMError(f"{resp.status_code}: {resp.text[:300]}")
        return resp.json()["choices"][0]["message"]["content"]
    raise LLMError(f"No usable model ({last_error}).")


def _ollama(prompt: str, system: str, schema: dict | None, model: str) -> str:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    if schema:
        prompt = (f"{prompt}\n\nRespond with JSON only, matching this schema exactly:\n"
                  f"{json.dumps(schema)}")
    messages.append({"role": "user", "content": prompt})

    body: dict[str, Any] = {"model": model or "llama3.1", "messages": messages, "stream": False}
    if schema:
        body["format"] = "json"
    resp = requests.post(OLLAMA_URL, json=body, timeout=TIMEOUT * 3)
    if not resp.ok:
        raise LLMError(f"Ollama {resp.status_code}: {resp.text[:300]}")
    return resp.json().get("message", {}).get("content", "")


# --------------------------------------------------------------------------
# Public surface
# --------------------------------------------------------------------------

def complete(prompt: str, *, system: str = "", schema: dict | None = None,
             retries: int = 2, purpose: str = "general",
             cacheable: bool = False) -> str:
    """
    One model call, with the quota defences applied in order: cache lookup
    (free), budget check (may refuse), throttle (may wait), provider call
    (spends), cache store.

    `purpose` names what the call is for — it decides the budget ceiling and
    shows up in /api/health. `cacheable` is for calls that are pure functions
    of their prompt (classification, JD analysis), never for creative ones.
    """
    cfg = config()
    model = cfg.get("model") or ""

    # The providers to try, in order: the configured one, then any other free
    # provider whose key is present. When Gemini's daily quota is spent, the call
    # rolls to the next rather than failing — the fallback the user asked for.
    chain = _provider_chain(cfg)
    if not chain:
        ok, reason = available()
        raise LLMError(reason if not ok else "No LLM provider is configured.")

    primary = chain[0][0]

    cache_key = ""
    if cacheable:
        # Keyed on the primary provider/model so it stays stable run to run — a
        # cached answer is a cached answer whichever provider produced it.
        cache_key = _cache_key(primary, model, prompt, system, schema)
        try:
            hit = store.llm_cache_get(cache_key)
        except Exception:
            hit = None
        if hit is not None:
            return hit

    # The daily budget is a ceiling on real calls, counted across providers, so
    # it is checked once up front. Ollama is local and free, so it is exempt.
    if primary != "ollama":
        _check_budget(purpose)

    last: Exception | None = None
    for provider, key in chain:
        # Only the configured provider uses the configured model name; a fallback
        # provider would not know it, so it picks its own default.
        pmodel = model if provider == primary else ""
        for attempt in range(retries + 1):
            try:
                out = _call_provider(provider, key, pmodel, prompt, system, schema)
                if provider != "ollama":
                    try:
                        store.llm_spend(purpose)
                    except Exception:
                        pass          # a failed usage write must not fail the answer
                if cacheable and cache_key and out.strip():
                    try:
                        store.llm_cache_put(cache_key, out)
                    except Exception:
                        pass
                return out
            except LLMError as exc:
                last = exc
                # A per-minute limit is worth waiting out on the same provider;
                # anything else — a spent day, a hard error — rolls to the next
                # provider in the chain instead.
                if getattr(exc, "retryable", False) and attempt < retries:
                    time.sleep(20 * (attempt + 1))
                    continue
                break
            except requests.RequestException as exc:
                last = exc
                if attempt < retries:
                    time.sleep(3 * (attempt + 1))
                    continue
                break
    raise LLMError(str(last) if last else "No LLM provider produced an answer.")


def complete_json(prompt: str, schema: dict, *, system: str = "",
                  default: Any = None, purpose: str = "general",
                  cacheable: bool = False) -> Any:
    """Schema-constrained call. Returns `default` instead of raising on a bad shape."""
    try:
        raw = complete(prompt, system=system, schema=schema,
                       purpose=purpose, cacheable=cacheable)
    except LLMError:
        if default is not None:
            return default
        raise

    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\s*|\s*```$", "", text, flags=re.I | re.S).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"[\[{].*[\]}]", text, re.S)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    if default is not None:
        return default
    raise LLMError(f"Model did not return valid JSON: {text[:200]}")
