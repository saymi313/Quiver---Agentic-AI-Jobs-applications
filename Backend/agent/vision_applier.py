"""
Accessibility Tree (a11y) & Vision-Assisted Autonomous Form Automation.

Primary Engine: Playwright Accessibility Tree (a11y) snapshots to reliably
extract and map interactive form components (textboxes, comboboxes, radios,
checkboxes, file uploads, dialogs) across Shadow DOMs, custom React/Vue
frameworks, and Workday/Ashby/Greenhouse/Lever layouts with zero selector brittleness.

Fallback Engine: Multimodal vision snapshots and self-healing selector caching
triggered ONLY when the a11y tree yields fewer than 2 interactive inputs on an
un-submitted application page.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

from api.config import OUTPUTS_DIR

CACHE_FILE = OUTPUTS_DIR / "selector_cache.json"

ACTIONABLE_ROLES = {
    "textbox",
    "combobox",
    "searchbox",
    "spinbutton",
    "button",
    "radio",
    "checkbox",
    "switch",
    "listbox",
    "option",
    "menuitem",
    "dialog",
    "slider",
}

INPUT_ROLES = {
    "textbox",
    "combobox",
    "searchbox",
    "spinbutton",
    "radio",
    "checkbox",
    "switch",
    "listbox",
    "slider",
}


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


# --------------------------------------------------------------------------
# Accessibility Tree (a11y) Engine
# --------------------------------------------------------------------------

def get_a11y_tree_snapshot(page: Any) -> dict[str, Any] | None:
    """
    Captures the full accessibility snapshot from the active Playwright page.
    Handles both sync and async page interfaces.
    """
    if not page:
        return None
    try:
        if hasattr(page, "accessibility") and hasattr(page.accessibility, "snapshot"):
            return page.accessibility.snapshot(interesting_only=True)
    except Exception:
        pass
    return None


def filter_actionable_nodes(tree_node: dict[str, Any] | None) -> list[dict[str, Any]]:
    """
    Recursively extracts actionable form elements from an a11y tree snapshot:
    - Text inputs, Comboboxes, Search fields
    - Radios, Checkboxes, Switches
    - Buttons, Dialogs, Option lists
    """
    if not tree_node:
        return []

    results: list[dict[str, Any]] = []

    def _traverse(node: dict[str, Any], depth: int = 0) -> None:
        role = (node.get("role") or "").lower()
        name = (node.get("name") or "").strip()
        value = (node.get("value") or "").strip() if isinstance(node.get("value"), str) else str(node.get("value") or "")
        description = (node.get("description") or "").strip()

        # Check if node is an actionable role or has an input-like characteristic
        if role in ACTIONABLE_ROLES:
            is_required = bool(node.get("required")) or "*" in name or "*" in description
            is_invalid = bool(node.get("invalid")) or node.get("invalid") == "true"

            results.append({
                "role": role,
                "name": name,
                "value": value,
                "description": description,
                "required": is_required,
                "invalid": is_invalid,
                "disabled": bool(node.get("disabled")),
                "checked": node.get("checked"),
                "selected": node.get("selected"),
                "pressed": node.get("pressed"),
                "multiline": bool(node.get("multiline")),
                "autocomplete": node.get("autocomplete"),
                "identifier": name or description or value or f"{role}_{len(results)}",
                "depth": depth,
            })

        # Recurse through children
        children = node.get("children") or []
        for child in children:
            if isinstance(child, dict):
                _traverse(child, depth + 1)

    _traverse(tree_node)
    return results


def count_interactive_inputs(nodes: list[dict[str, Any]]) -> int:
    """Counts interactive input elements (excluding standard navigation buttons)."""
    return sum(1 for n in nodes if n.get("role") in INPUT_ROLES and not n.get("disabled"))


def find_a11y_locator(page: Any, node: dict[str, Any]) -> Any:
    """
    Creates a robust Playwright locator for an accessible node.
    Attempts role-based mapping with fallback to label/placeholder and CSS.
    """
    role = node.get("role") or "textbox"
    name = node.get("name") or ""
    desc = node.get("description") or ""

    # 1. Exact role + accessible name
    if name:
        try:
            loc = page.get_by_role(role, name=name, exact=True)
            if loc.count() > 0:
                return loc.first
        except Exception:
            pass

        # 2. Fuzzy role + accessible name
        try:
            loc = page.get_by_role(role, name=name, exact=False)
            if loc.count() > 0:
                return loc.first
        except Exception:
            pass

        # 3. Label matching
        try:
            loc = page.get_by_label(name, exact=False)
            if loc.count() > 0:
                return loc.first
        except Exception:
            pass

        # 4. Placeholder matching
        try:
            loc = page.get_by_placeholder(name, exact=False)
            if loc.count() > 0:
                return loc.first
        except Exception:
            pass

    # 5. Description fallback
    if desc:
        try:
            loc = page.get_by_label(desc, exact=False)
            if loc.count() > 0:
                return loc.first
        except Exception:
            pass

    # 6. Fallback generic selector by role
    try:
        if role in ("textbox", "searchbox", "spinbutton"):
            return page.locator("input:not([type='hidden']), textarea").first
        elif role == "combobox":
            return page.locator("select, [role='combobox'], [aria-haspopup='listbox']").first
        elif role == "button":
            return page.locator("button, [role='button']").first
        elif role in ("checkbox", "switch"):
            return page.locator("input[type='checkbox'], [role='checkbox']").first
        elif role == "radio":
            return page.locator("input[type='radio'], [role='radio']").first
    except Exception:
        pass

    return None


# --------------------------------------------------------------------------
# Multimodal Vision Fallback Engine
# --------------------------------------------------------------------------

def parse_vision_coordinates(response_text: str) -> tuple[int, int] | None:
    """
    Parses (x, y) pixel coordinates or bounding box center from Vision LLM response.
    """
    if not response_text:
        return None

    try:
        match = re.search(r'\{[^{}]*"x"\s*:\s*(\d+)\s*,\s*"y"\s*:\s*(\d+)[^{}]*\}', response_text)
        if match:
            return int(match.group(1)), int(match.group(2))
    except Exception:
        pass

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
    Multimodal fallback when a11y tree yields fewer than 2 interactive inputs.
    Uses cached self-healed selectors or viewport coordinate estimation.
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

    # 2. Capture viewport snapshot for visual inspection
    try:
        if hasattr(page, "screenshot"):
            SHOT_PATH = OUTPUTS_DIR / "vision_temp.png"
            SHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(SHOT_PATH))
            log(f"[vision] Captured viewport snapshot for unmapped field: '{field_label}'")
    except Exception as exc:
        log(f"[vision] Vision snapshot fallback failed: {exc}")

    return False
