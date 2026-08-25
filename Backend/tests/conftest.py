"""
Test harness: every test runs against a throwaway SQLite file.

The two env vars must be set before anything imports `agent.store`, which is
why this happens at module import time rather than inside a fixture.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

_tmp = tempfile.mkdtemp(prefix="jobenzy-tests-")
os.environ["JOBSCRIPT_FORCE_SQLITE"] = "1"
os.environ["JOBSCRIPT_DB_PATH"] = str(Path(_tmp) / "test.sqlite3")

import pytest  # noqa: E402


@pytest.fixture()
def fresh_store():
    """The agent store, wiped clean for this test."""
    from agent import sqlite_store, store

    store.init()
    with sqlite_store.tx() as c:
        for table in ("applications", "outreach", "tasks", "jobs", "people",
                      "companies", "runs", "llm_usage", "llm_cache", "settings",
                      "messages"):
            c.execute(f"DELETE FROM {table}")
    return store
