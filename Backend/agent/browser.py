"""
Persistent Authenticated Browser Context & Multi-Tab Lifecycle Manager.

Preserves logged-in sessions (LinkedIn, Workday, Google, Indeed) across runs
using Playwright's persistent context and storage state persistence.
"""

from __future__ import annotations

import json
import os
import socket
from pathlib import Path
from typing import Any, Callable, Tuple

from api.config import OUTPUTS_DIR
from . import store

USER_DATA_DIR = OUTPUTS_DIR / "browser_profile"
SESSION_STATE_FILE = USER_DATA_DIR / "session_state.json"
USER_DATA_DIR.mkdir(parents=True, exist_ok=True)


def get_browser_context(
    playwright: Any,
    *,
    headless: bool = True,
    user_data_dir: Path | None = None,
    proxy_url: str | None = None,
    log: Callable[[str], None] = print,
) -> Tuple[Any, Any, bool]:
    """
    Acquires an active browser context in priority order:
    1. Active Chrome CDP session on port 9222 (1-tab integration)
    2. Playwright persistent context preserving user session profile & cookies
    """
    profile_dir = user_data_dir or USER_DATA_DIR
    profile_dir.mkdir(parents=True, exist_ok=True)

    # 1. Fast socket probe for active CDP browser session
    try:
        with socket.create_connection(("127.0.0.1", 9222), timeout=0.15):
            browser = playwright.chromium.connect_over_cdp("http://127.0.0.1:9222")
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            log("[browser] connected to active Chrome CDP session (port 9222)")
            return browser, context, True
    except Exception:
        pass

    # 2. Launch persistent Playwright context
    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
        "--no-sandbox",
    ]

    kwargs: dict[str, Any] = {
        "user_data_dir": str(profile_dir),
        "headless": headless,
        "args": launch_args,
        "viewport": {"width": 1440, "height": 950},
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        ),
        "locale": "en-US",
        "timezone_id": "Asia/Karachi",
        "accept_downloads": False,
    }

    if proxy_url:
        kwargs["proxy"] = {"server": proxy_url}

    browser_inst = playwright.chromium.launch(
        headless=headless,
        args=launch_args,
        proxy={"server": proxy_url} if proxy_url else None,
    )
    context = browser_inst.new_context(
        viewport={"width": 1440, "height": 950},
        user_agent=kwargs["user_agent"],
        locale="en-US",
        timezone_id="Asia/Karachi",
    )

    # Anti-bot stealth initialization scripts
    try:
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            "window.chrome = { runtime: {}, app: {}, csi: () => {}, loadTimes: () => {} };"
            "Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en', 'en-GB']});"
        )
    except Exception:
        pass

    # Inject stored LinkedIn cookie if available
    try:
        linkedin_cfg = store.get_setting("linkedin", {}) or {}
        li_at = (
            linkedin_cfg.get("li_at")
            or linkedin_cfg.get("cookie")
            or os.getenv("LINKEDIN_LI_AT")
        )
        if li_at:
            context.add_cookies([{
                "name": "li_at",
                "value": str(li_at).strip(),
                "domain": ".linkedin.com",
                "path": "/",
                "httpOnly": True,
                "secure": True,
            }])
    except Exception:
        pass

    return browser_inst, context, False

def save_browser_storage_state(context: Any, path: Path | None = None) -> bool:
    """Persists active cookies and storage state for future headless runs."""
    if not context:
        return False
    target = path or SESSION_STATE_FILE
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if hasattr(context, "storage_state"):
            context.storage_state(path=str(target))
    except Exception:
        pass
    return False


def verify_or_prompt_linkedin_auth(
    context: Any,
    page: Any,
    *,
    timeout_s: int = 120,
    log: Callable[[str], None] = print,
) -> bool:
    """
    Checks if LinkedIn session is authenticated. If hitting guest paywall or login page,
    prompts the user via Rescue Mode to log in once, then saves the authenticated storage state.
    """
    if not page:
        return False

    try:
        page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(2000)

        # Check if authenticated into feed
        if "/feed" in page.url and page.locator(".feed-identity-module, .global-nav__me").count() > 0:
            log("[auth] LinkedIn session is actively authenticated.")
            save_browser_storage_state(context)
            return True

        if "/login" in page.url or "/checkpoint" in page.url or "/authwall" in page.url:
            log("[auth] LinkedIn login required — initiating Rescue Mode.")
            from . import applier
            ok = applier.trigger_rescue_mode(
                job_id=0,
                company="LinkedIn",
                blocker_type="LinkedIn Login Required",
                page=page,
                timeout_s=timeout_s,
                log=log,
            )
            if ok:
                save_browser_storage_state(context)
                return True
    except Exception as exc:
        log(f"[auth] LinkedIn auth verification check error ({exc})")

    return False
