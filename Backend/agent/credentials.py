"""
Credentials for the sites that will not take an application without an account.

Workday and iCIMS are the two that matter: both make you sign in, or register,
before the form is even shown. Tsenta's answer is a *separate application
password* set during onboarding, used only for the throwaway accounts the agent
creates on employer systems, so the user's real passwords never enter the
picture. This is that store.

Where it lives is the whole point. The secret goes in `Backend/credentials.json`
— already in `.gitignore`, the same trust model as `Backend/.env`, which already
holds the Gmail app password in plain text. It never touches the settings
database (which is dumped into API responses and the overview) and it never
reaches the repository. `list_domains()` and the API built on it return whether a
password is set, never the password itself.

Two things are kept here:

  * Per-domain login credentials — a username and password for a site's own
    account wall, plus the shared *application password* used when the agent has
    to register a new account.
  * A one-time code the user was sent, parked against a job id so the next apply
    run for that job can type it in. This is the local stand-in for Tsenta's
    `POST /applications/{id}/otp`: the browser does not stay alive between runs,
    so the code waits in the store instead of in a live session.
"""

from __future__ import annotations

import json
import secrets
import string
import threading
from typing import Any
from urllib.parse import urlparse

from api.config import BASE_DIR

STORE = BASE_DIR / "credentials.json"
_lock = threading.Lock()


def _read() -> dict[str, Any]:
    if not STORE.is_file():
        return {"domains": {}, "app_password": "", "otp": {}}
    try:
        data = json.loads(STORE.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {"domains": {}, "app_password": "", "otp": {}}
    data.setdefault("domains", {})
    data.setdefault("app_password", "")
    data.setdefault("otp", {})
    return data


def _write(data: dict[str, Any]) -> None:
    # 0o600 where the platform honours it: this file is a password on disk.
    STORE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        STORE.chmod(0o600)
    except OSError:
        pass


def domain_of(url_or_domain: str) -> str:
    """The registrable-ish host, lowercased and without a leading www."""
    value = (url_or_domain or "").strip().lower()
    if not value:
        return ""
    if "://" in value:
        value = urlparse(value).netloc or value
    value = value.split("/")[0].split("@")[-1]
    return value[4:] if value.startswith("www.") else value


# --------------------------------------------------------------------------
# The application password (shared, for accounts the agent creates)
# --------------------------------------------------------------------------

def application_password() -> str:
    """The password used for accounts the agent registers. Empty if unset."""
    with _lock:
        return _read().get("app_password", "")


def set_application_password(password: str) -> None:
    with _lock:
        data = _read()
        data["app_password"] = password or ""
        _write(data)


def generate_password(length: int = 20) -> str:
    """A strong password for a new employer account, meeting the usual rules."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*-_"
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(length))
        if (any(c.islower() for c in pw) and any(c.isupper() for c in pw)
                and any(c.isdigit() for c in pw) and any(c in "!@#$%^&*-_" for c in pw)):
            return pw


# --------------------------------------------------------------------------
# Per-domain login credentials
# --------------------------------------------------------------------------

def set_credential(domain: str, username: str, password: str) -> dict[str, Any]:
    key = domain_of(domain)
    if not key:
        return {"ok": False, "error": "A site domain is required."}
    if not username or not password:
        return {"ok": False, "error": "Both a username and a password are required."}
    with _lock:
        data = _read()
        data["domains"][key] = {"username": username, "password": password}
        _write(data)
    return {"ok": True, "domain": key}


def get_credential(domain: str) -> dict[str, str] | None:
    """The username/password for a domain, or None. Used only by the applier."""
    with _lock:
        return _read()["domains"].get(domain_of(domain))


def delete_credential(domain: str) -> bool:
    with _lock:
        data = _read()
        if domain_of(domain) in data["domains"]:
            del data["domains"][domain_of(domain)]
            _write(data)
            return True
    return False


def list_domains() -> list[dict[str, Any]]:
    """Every stored site, with the username but never the password."""
    with _lock:
        data = _read()
    return [{"domain": d, "username": v.get("username", ""), "hasPassword": bool(v.get("password"))}
            for d, v in sorted(data["domains"].items())]


def status() -> dict[str, Any]:
    """A safe summary for the settings screen — counts and usernames, no secrets."""
    with _lock:
        data = _read()
    return {
        "domains": [{"domain": d, "username": v.get("username", ""),
                     "hasPassword": bool(v.get("password"))}
                    for d, v in sorted(data["domains"].items())],
        "hasApplicationPassword": bool(data.get("app_password")),
    }


# --------------------------------------------------------------------------
# One-time codes, parked against a job for the next run
# --------------------------------------------------------------------------

def set_otp(job_id: int, code: str) -> None:
    with _lock:
        data = _read()
        data["otp"][str(int(job_id))] = (code or "").strip()
        _write(data)


def pop_otp(job_id: int) -> str | None:
    """Take the code for a job, if one is waiting. Removed on read — a code is
    single use, and leaving it would replay a stale one on the next attempt."""
    with _lock:
        data = _read()
        code = data["otp"].pop(str(int(job_id)), None)
        if code is not None:
            _write(data)
        return code


def awaiting_otp() -> list[int]:
    with _lock:
        return [int(k) for k in _read()["otp"]]
