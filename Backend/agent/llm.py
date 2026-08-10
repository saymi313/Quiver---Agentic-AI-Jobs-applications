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

import json
import os
import re
import time
from typing import Any

import requests

from api.config import BASE_DIR

from . import store

TIMEOUT = 90

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
GROQ_FALLBACKS = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]
OPENROUTER_FALLBACKS = ["meta-llama/llama-3.3-70b-instruct:free", "google/gemma-2-9b-it:free"]


class LLMError(RuntimeError):
    pass


_ENV_LOADED = False


def _load_env() -> None:
    """Read Backend/.env once so keys live beside the Gmail credentials."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def config() -> dict[str, Any]:
    _load_env()
    cfg = dict(store.DEFAULT_SETTINGS["llm"])
    cfg.update(store.get_setting("llm", {}) or {})
    if not cfg.get("api_key"):
        env_key = {
            "gemini": "GEMINI_API_KEY",
            "groq": "GROQ_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
        }.get(cfg.get("provider", ""), "")
        if env_key:
            cfg["api_key"] = os.environ.get(env_key, "")
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
    if not cfg.get("api_key"):
        where = {
            "gemini": "https://aistudio.google.com/apikey",
            "groq": "https://console.groq.com/keys",
            "openrouter": "https://openrouter.ai/keys",
        }.get(provider, "")
        return False, f"No API key set for {provider}. Get a free one at {where} and paste it in Settings."
    return True, f"{provider} ready ({cfg.get('model')})."


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

    last_error = ""
    for candidate in [model, *[m for m in GEMINI_FALLBACKS if m != model]]:
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
            raise LLMError("Gemini free-tier rate limit hit. Wait a minute and retry.")
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
            raise LLMError("Provider rate limit hit. Wait a minute and retry.")
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
             retries: int = 2) -> str:
    cfg = config()
    provider = cfg.get("provider", "gemini")
    model = cfg.get("model") or ""
    key = cfg.get("api_key") or ""

    ok, reason = available()
    if not ok:
        raise LLMError(reason)

    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            if provider == "gemini":
                return _gemini(prompt, system, schema, model or GEMINI_FALLBACKS[0], key)
            if provider == "groq":
                return _openai_compatible(GROQ_URL, prompt, system, schema,
                                          model or GROQ_FALLBACKS[0], key, GROQ_FALLBACKS)
            if provider == "openrouter":
                return _openai_compatible(
                    OPENROUTER_URL, prompt, system, schema,
                    model or OPENROUTER_FALLBACKS[0], key, OPENROUTER_FALLBACKS,
                    {"HTTP-Referer": "http://localhost", "X-Title": "Quiver"})
            if provider == "ollama":
                return _ollama(prompt, system, schema, model)
            raise LLMError(f"Unknown provider '{provider}'.")
        except LLMError as exc:
            last = exc
            if "rate limit" in str(exc).lower() and attempt < retries:
                time.sleep(20 * (attempt + 1))
                continue
            raise
        except requests.RequestException as exc:
            last = exc
            if attempt < retries:
                time.sleep(3 * (attempt + 1))
                continue
            raise LLMError(f"Network error talking to {provider}: {exc}") from exc
    raise LLMError(str(last))


def complete_json(prompt: str, schema: dict, *, system: str = "",
                  default: Any = None) -> Any:
    """Schema-constrained call. Returns `default` instead of raising on a bad shape."""
    try:
        raw = complete(prompt, system=system, schema=schema)
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
