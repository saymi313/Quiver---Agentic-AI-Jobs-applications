"""
The agent's data store — a thin facade over one of two interchangeable backends.

    MONGODB_URI set and the cluster reachable  ->  agent/mongo_store.py
    otherwise                                  ->  agent/sqlite_store.py

Both implement the same functions with the same shapes, so nothing that imports
this module knows or cares which one is live. The fallback matters: a laptop on
a plane, a paused Atlas cluster, or a DNS hiccup should degrade to local SQLite
rather than take the whole agent down.

Every attribute is forwarded through `__getattr__`, so `store.upsert_company`,
`store.DEFAULT_SETTINGS` and everything else resolve against the active backend.
"""

from __future__ import annotations

import os
from typing import Any

from . import sqlite_store
from .schema import DEFAULT_SETTINGS, merge_settings, now  # re-exported for callers

_backend: Any = None
_status: dict[str, Any] = {"backend": "sqlite", "reason": "not initialised", "fallback": False}


def _select() -> Any:
    """Choose a backend once, on first use."""
    global _backend, _status
    if _backend is not None:
        return _backend

    if os.environ.get("JOBSCRIPT_FORCE_SQLITE", "").strip().lower() in ("1", "true", "yes"):
        _backend = sqlite_store
        _status = {"backend": "sqlite", "reason": "forced by JOBSCRIPT_FORCE_SQLITE",
                   "fallback": False}
        return _backend

    try:
        from . import mongo_store
    except ImportError as exc:
        _backend = sqlite_store
        _status = {"backend": "sqlite", "reason": f"pymongo not installed ({exc})",
                   "fallback": False}
        return _backend

    if not mongo_store.configured():
        _backend = sqlite_store
        _status = {"backend": "sqlite", "reason": "MONGODB_URI is not set", "fallback": False}
        return _backend

    ok, reason = mongo_store.available()
    if ok:
        _backend = mongo_store
        _status = {"backend": "mongodb", "reason": reason, "fallback": False,
                   "database": mongo_store.db_name()}
    else:
        # Configured but unreachable: keep working locally and say so loudly.
        _backend = sqlite_store
        _status = {"backend": "sqlite", "fallback": True,
                   "reason": f"MongoDB unreachable, using local SQLite instead. {reason}"}
    return _backend


def backend_status() -> dict[str, Any]:
    """Which store is live, and why. Surfaced in the dashboard."""
    _select()
    return dict(_status)


def backend_name() -> str:
    _select()
    return str(_status.get("backend", "sqlite"))


def init() -> None:
    _select().init()


def use_sqlite() -> Any:
    """Force the local backend. Used by the migration tool to read the source."""
    global _backend, _status
    _backend = sqlite_store
    _status = {"backend": "sqlite", "reason": "explicitly selected", "fallback": False}
    return _backend


def use_mongo() -> Any:
    """Force the Mongo backend. Used by the migration tool to write the target."""
    global _backend, _status
    from . import mongo_store

    _backend = mongo_store
    _status = {"backend": "mongodb", "reason": "explicitly selected", "fallback": False,
               "database": mongo_store.db_name()}
    return _backend


def __getattr__(name: str) -> Any:
    """Forward every other attribute to whichever backend is active."""
    if name.startswith("__"):
        raise AttributeError(name)
    return getattr(_select(), name)


__all__ = ["DEFAULT_SETTINGS", "merge_settings", "now", "init",
           "backend_status", "backend_name", "use_sqlite", "use_mongo"]
