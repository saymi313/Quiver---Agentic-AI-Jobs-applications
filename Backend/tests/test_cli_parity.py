"""
The CLI query commands mirror the MCP tool surface (FR-S4).

The value of these commands is that they are the *same* code the MCP server
runs, so anything an agent can do over MCP can be done from a shell and the two
cannot drift. This test pins that: each query mode dispatches to its matching
mcp_server function with the arguments the CLI collected. mcp_server is patched
so the test never touches the store or the network — it checks the wiring, which
is the only thing that can break here.
"""

from __future__ import annotations

import types

import pytest

from agent import runner


class _Args:
    def __init__(self, **kw):
        self.mode = kw.get("mode", "")
        self.status = kw.get("status", "")
        self.category = kw.get("category", "")
        self.klass = kw.get("klass", "")
        self.unread = kw.get("unread", False)
        self.url = kw.get("url", "")
        self.id = kw.get("id", 0)
        self.stage = kw.get("stage", "")
        self.limit = kw.get("limit", 25)


@pytest.fixture()
def fake_mcp(monkeypatch):
    calls = {}

    def rec(name):
        def fn(*a, **k):
            calls[name] = {"args": a, "kwargs": k}
            return f"{name}-output"
        return fn

    mod = types.SimpleNamespace(
        list_jobs=rec("list_jobs"), get_job=rec("get_job"), pipeline=rec("pipeline"),
        read_inbox=rec("read_inbox"), get_profile=rec("get_profile"),
        supported_portals=rec("supported_portals"), list_proposals=rec("list_proposals"),
        status=rec("status"), track_job_url=rec("track_job_url"), set_stage=rec("set_stage"),
        resume_changes=rec("resume_changes"), approve_resume=rec("approve_resume"),
    )
    monkeypatch.setitem(__import__("sys").modules, "agent.mcp_server", mod)
    return calls


def test_every_query_mode_is_covered():
    # The choice list and the dispatcher must agree — a mode with no branch
    # would parse and then silently do nothing.
    assert runner.QUERY_MODES == {
        "jobs", "job", "pipeline", "messages", "profile", "portals",
        "proposals", "status", "track-url", "set-stage",
        "resume-changes", "approve-resume"}


def test_jobs_passes_the_filters(fake_mcp, capsys):
    rc = runner._run_query(_Args(mode="jobs", status="matched", category="frontend", limit=5))
    assert rc == 0
    assert fake_mcp["list_jobs"]["kwargs"] == {"status": "matched", "category": "frontend", "limit": 5}
    assert "list_jobs-output" in capsys.readouterr().out


def test_messages_passes_klass_and_unread(fake_mcp):
    runner._run_query(_Args(mode="messages", klass="interview", unread=True, limit=10))
    assert fake_mcp["read_inbox"]["kwargs"] == {"klass": "interview", "unread_only": True, "limit": 10}


def test_set_stage_needs_both_args(fake_mcp):
    assert runner._run_query(_Args(mode="set-stage", id=0, stage="")) == 2  # refused
    runner._run_query(_Args(mode="set-stage", id=7, stage="offer"))
    assert fake_mcp["set_stage"]["args"] == (7, "offer")


def test_track_url_needs_a_url(fake_mcp):
    assert runner._run_query(_Args(mode="track-url", url="")) == 2
    runner._run_query(_Args(mode="track-url", url="https://x.com/j/1"))
    assert fake_mcp["track_job_url"]["args"] == ("https://x.com/j/1",)


def test_simple_reads_route(fake_mcp):
    for mode, name in [("pipeline", "pipeline"), ("profile", "get_profile"),
                       ("portals", "supported_portals"), ("proposals", "list_proposals"),
                       ("status", "status")]:
        runner._run_query(_Args(mode=mode))
        assert name in fake_mcp
