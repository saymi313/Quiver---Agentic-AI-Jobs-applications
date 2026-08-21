"""
The two storage backends must stay interchangeable.

`agent/store.py` picks one at import time and nothing downstream knows which,
so a function that exists on SQLite and not on MongoDB is a crash waiting for
whoever runs without `JOBSCRIPT_FORCE_SQLITE`.

Signature parity alone is not enough, and this suite exists because of a real
bug: `proposals()` was added to both backends with identical signatures, and
the MongoDB copy called `_job_rows` — a helper that only exists on the SQLite
side. It imported fine, matched signatures fine, and raised `NameError` the
first time anything called it. The name-resolution test below catches that
class of mistake without needing a live cluster.
"""

from __future__ import annotations

import ast
import builtins
import inspect
from pathlib import Path

import pytest

from agent import mongo_store, sqlite_store

# Legitimately backend-specific: a SQLite transaction manager, and the probes
# agent/store.py uses to decide which backend to select.
BACKEND_ONLY = {"tx", "available", "configured", "db_name", "uri"}


def _public(module) -> set[str]:
    return {
        name for name, fn in vars(module).items()
        if not name.startswith("_") and inspect.isfunction(fn)
        and fn.__module__ == module.__name__
    } - BACKEND_ONLY


def test_the_same_functions_exist_on_both():
    a, b = _public(sqlite_store), _public(mongo_store)
    assert not (a - b), f"missing from mongo_store: {sorted(a - b)}"
    assert not (b - a), f"missing from sqlite_store: {sorted(b - a)}"


def test_signatures_match_exactly():
    """A caller written against one backend must work against the other."""
    for name in sorted(_public(sqlite_store)):
        one = inspect.signature(getattr(sqlite_store, name))
        two = inspect.signature(getattr(mongo_store, name))
        assert str(one) == str(two), f"{name}: sqlite{one} != mongo{two}"


@pytest.mark.parametrize("module", [sqlite_store, mongo_store],
                         ids=["sqlite_store", "mongo_store"])
def test_every_name_a_function_uses_actually_exists(module):
    """
    Static check for the `_job_rows` bug: a helper borrowed from the other
    backend that resolves at import time to nothing.

    Walks each function body for global name loads and confirms every one is
    defined in that module, imported into it, or a builtin. Cheap, and it does
    not need a database.
    """
    source = Path(module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    module_names = set(vars(module)) | set(dir(builtins))

    problems: list[str] = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        # Names bound inside the function: arguments, assignments, imports,
        # comprehension targets. Anything else that is loaded must be global.
        local: set[str] = {a.arg for a in node.args.args}
        local |= {a.arg for a in node.args.kwonlyargs}
        if node.args.vararg:
            local.add(node.args.vararg.arg)
        if node.args.kwarg:
            local.add(node.args.kwarg.arg)

        for inner in ast.walk(node):
            if isinstance(inner, ast.Name) and isinstance(inner.ctx, ast.Store):
                local.add(inner.id)
            elif isinstance(inner, (ast.Import, ast.ImportFrom)):
                for alias in inner.names:
                    local.add(alias.asname or alias.name.split(".")[0])
            elif isinstance(inner, ast.ExceptHandler) and inner.name:
                local.add(inner.name)
            elif isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                if isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    local.add(inner.name)
                    local |= {a.arg for a in inner.args.args}
                else:
                    local |= {a.arg for a in inner.args.args}

        for inner in ast.walk(node):
            if isinstance(inner, ast.Name) and isinstance(inner.ctx, ast.Load):
                if inner.id not in local and inner.id not in module_names:
                    problems.append(f"{node.name}() uses undefined {inner.id!r}")

    assert not problems, (
        f"{module.__name__} references names that do not exist:\n  "
        + "\n  ".join(sorted(set(problems))))


def test_the_tracking_surface_is_present_on_both():
    """The functions added for Track, Prep and Auto Apply, named explicitly so
    a half-finished port is a failing test rather than a runtime surprise."""
    required = {
        # Track
        "application", "set_application_status", "set_tracker_status",
        "tracked_applications", "applications_for_linking", "record_message",
        "list_messages", "unread_count", "mark_message_read",
        "known_message_ids", "tracker_counts", "message_counts",
        # Prep
        "approve_job_resume", "job_by_url",
        # Auto Apply
        "propose_job", "decide_proposal", "proposals", "proposed_today",
    }
    for module in (sqlite_store, mongo_store):
        missing = required - _public(module)
        assert not missing, f"{module.__name__} is missing {sorted(missing)}"
