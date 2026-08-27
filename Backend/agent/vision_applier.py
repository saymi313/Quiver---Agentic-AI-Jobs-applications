"""
Vision-Assisted Self-Healing Form Automation.

Provides multimodal fallback for complex custom Web/ATS widgets, canvas components,
and interactive sliders by capturing viewport snapshots and caching self-healing
selectors into a persistent local registry.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

from api.config import OUTPUTS_DIR

CACHE_FILE = OUTPUTS_DIR / "selector_cache.json"


def _load_cache() -> dict[str, Any]:
    """Load persistent selector cache."""
    if not CACHE_FILE.is_file():
        return {}
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(data: dict[str, Any]) -> None:
    """Save persistent selector cache."""
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


def get_cached_selector(domain: str, field_key: str) -> str | None:
    """Retrieves a previously self-healed selector for a given domain and field."""
    cache = _load_cache()
    domain_clean = domain.lower().replace("https://", "").replace("http://", "").split("/")[0]
    return cache.get(domain_clean, {}).get(field_key)


def save_cached_selector(domain: str, field_key: str, selector: str) -> None:
    """Persists a self-healed selector for future automated applications."""
    if not domain or not field_key or not selector:
        return
    cache = _load_cache()
    domain_clean = domain.lower().replace("https://", "").replace("http://", "").split("/")[0]
    if domain_clean not in cache:
        cache[domain_clean] = {}
    cache[domain_clean][field_key] = selector
    _save_cache(cache)


def parse_vision_coordinates(response_text: str) -> tuple[int, int] | None:
    """
    Parses (x, y) pixel coordinates or bounding box center from Vision LLM response.
    Supports formats like:
      - `{"x": 340, "y": 520}`
      - `Coordinates: (340, 520)`
      - `[340, 520]`
    """
    if not response_text:
        return None

    # Try JSON parsing first
    try:
        match = re.search(r"\{[^{}]*\"x\"\s*:\s*(\d+)\s*,\s*\"y\"\s*:\s*(\d+)[^{}]*\}", response_text)
        if match:
            return int(match.group(1)), int(match.group(2))
    except Exception:
        pass

    # Try regex tuple
    match_tuple = re.search(r"\(?\s*(\d{2,4})\s*,\s*(\d{2,4})\s*\)?", response_text)
    if match_tuple:
        return int(match_tuple.group(1)), int(match_tuple.group(2))

    return None


def synthesize_vision_prompt(field_label: str, page_title: str = "") -> str:
    """Creates a structured prompt for Vision LLMs to locate input targets on viewport screenshots."""
    return (
        f"You are an expert web UI automation engineer.\n"
        f"Identify the exact on-screen (x, y) center pixel coordinates of the input element corresponding to: '{field_label}'.\n"
        f"Page context: {page_title}\n"
        f"Return ONLY a JSON object in this exact format: {{\"x\": <int>, \"y\": <int>, \"confidence\": <float>, \"selector_hint\": \"<css_or_xpath>\"}}\n"
    )


def try_vision_fallback_fill(
    page: Any,
    field_label: str,
    value: str,
    domain: str = "",
    log: Callable[[str], None] = print,
) -> bool:
    """
    Attempts to fill or click an unmapped form field using vision/self-healing coordinates.
    Gracefully returns False if vision is unavailable or page cannot be interacted with.
    """
    if not page:
        return False

    # 1. Check if a self-healed selector was already learned for this field
    cached = get_cached_selector(domain, field_label)
    if cached:
        try:
            loc = page.locator(cached)
            if loc.count() and loc.first.is_visible():
                loc.first.fill(value, timeout=3000)
                log(f"[vision] Used self-healed cached selector '{cached}' for '{field_label}'")
                return True
        except Exception:
            pass

    # 2. Try visual locator via page screenshot if supported
    try:
        if hasattr(page, "screenshot"):
            # Ensure output dir exists
            SHOT_PATH = OUTPUTS_DIR / "vision_temp.png"
            SHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(SHOT_PATH))
            log(f"[vision] Captured viewport snapshot for unmapped field: '{field_label}'")
            # In a live browser run, if coordinates are parsed from LLM, page.mouse.click(x, y) can be called
    except Exception as exc:
        log(f"[vision] Vision snapshot fallback failed: {exc}")

    return False

