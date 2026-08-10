"""
The scheduler: unattended discovery and retry-queue drains.

A daemon thread inside the API process wakes every 60 seconds, reads
`settings.schedule`, and — when a cadence is due — dispatches through the exact
same `manager.start()` path the dashboard buttons use. That is the whole trick:
scheduled runs get SSE streaming, run history, and the one-at-a-time invariant
for free, because they are ordinary jobs that happen to have been started by a
clock instead of a click.

Safety properties, enforced structurally rather than by configuration:

  * Only the tasks in SCHEDULABLE can ever be dispatched. `agent_apply` is not
    in the tuple, so no schedule, however misconfigured, can submit a real
    application. Applying stays a human decision.
  * Off by default. `schedule.enabled` starts False; turning on unattended
    runs is a decision the user makes in Settings, not a side effect.
  * One job at a time. If anything is already running — scheduled or manual —
    the tick skips and tries again next minute.
  * Quiet hours. Nothing fires inside the local-time window, so a laptop left
    open overnight stays silent.
  * Restart-safe. Last-fired timestamps persist in settings, so rebooting the
    API does not re-fire everything immediately.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

from .jobs import manager

# The complete set of schedulable work. Everything else — applying above all —
# is structurally unreachable from here.
SCHEDULABLE = ("agent_discover", "agent_tasks")

POLL_S = 60
_STATE_KEY = "schedule_state"

_thread: threading.Thread | None = None
_stop = threading.Event()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def _in_quiet_hours(quiet: Any, local_hour: int) -> bool:
    """quiet_hours is [start, end) in local hours; it may span midnight."""
    try:
        start, end = int(quiet[0]), int(quiet[1])
    except (TypeError, ValueError, IndexError):
        return False
    if start == end:
        return False
    if start < end:
        return start <= local_hour < end
    return local_hour >= start or local_hour < end  # e.g. [22, 6)


def _due(kind: str, sched: dict[str, Any], state: dict[str, Any],
         now: datetime) -> bool:
    last = _parse(state.get(f"last_{kind}_at"))
    if kind == "discover":
        interval_s = max(1, int(sched.get("discover_every_hours") or 6)) * 3600
    else:
        interval_s = max(1, int(sched.get("tasks_every_minutes") or 30)) * 60
    return last is None or (now - last).total_seconds() >= interval_s


def _dispatch(key: str, options: dict[str, Any]) -> None:
    assert key in SCHEDULABLE, f"scheduler tried to start non-schedulable task {key!r}"
    manager.start(key, options)


def _tick() -> None:
    from agent import store

    sched = store.all_settings().get("schedule") or {}
    if not sched.get("enabled"):
        return
    if _in_quiet_hours(sched.get("quiet_hours"), datetime.now().hour):
        return
    if manager.active() is not None:
        return  # something is running — scheduled or manual, wait it out

    now = _now()
    state = store.get_setting(_STATE_KEY, {}) or {}

    # Discovery first: it is the rarer, heavier cadence, and it feeds the queue
    # the tasks drain works through. Whichever fires, the other waits for a
    # later tick — the manager runs one job at a time anyway.
    if _due("discover", sched, state, now):
        _dispatch("agent_discover", {
            "sources": sched.get("sources") or ["yc", "hn", "remote", "hidden"],
            "limit": int(sched.get("discover_limit") or 25),
        })
        state["last_discover_at"] = now.isoformat()
        store.set_setting(_STATE_KEY, state)
        return

    if _due("tasks", sched, state, now):
        # Skip the subprocess entirely when the queue has nothing due-able.
        stats = store.task_stats()
        if not (stats.get("pending") or stats.get("failed")):
            state["last_tasks_at"] = now.isoformat()
            store.set_setting(_STATE_KEY, state)
            return
        _dispatch("agent_tasks", {"limit": 50})
        state["last_tasks_at"] = now.isoformat()
        store.set_setting(_STATE_KEY, state)


def _loop() -> None:
    from agent import store

    store.init()
    while not _stop.wait(POLL_S):
        try:
            _tick()
        except Exception as exc:  # a bad tick must never kill the thread
            print(f"[scheduler] tick failed: {type(exc).__name__}: {exc}")


def start() -> None:
    """Idempotent: called from the API's startup hook."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="quiver-scheduler", daemon=True)
    _thread.start()


def stop() -> None:
    _stop.set()


def status() -> dict[str, Any]:
    """What the schedule will do next — shown in the agent overview."""
    from agent import store

    sched = store.all_settings().get("schedule") or {}
    state = store.get_setting(_STATE_KEY, {}) or {}
    now = _now()

    def next_at(kind: str, interval_s: int) -> str | None:
        if not sched.get("enabled"):
            return None
        last = _parse(state.get(f"last_{kind}_at"))
        if last is None:
            return now.isoformat()  # fires on the next tick
        from datetime import timedelta
        return (last + timedelta(seconds=interval_s)).isoformat()

    return {
        "enabled": bool(sched.get("enabled")),
        "running": _thread is not None and _thread.is_alive(),
        "quietHours": sched.get("quiet_hours"),
        "nextDiscoverAt": next_at(
            "discover", max(1, int(sched.get("discover_every_hours") or 6)) * 3600),
        "nextTasksAt": next_at(
            "tasks", max(1, int(sched.get("tasks_every_minutes") or 30)) * 60),
        "lastDiscoverAt": state.get("last_discover_at"),
        "lastTasksAt": state.get("last_tasks_at"),
        "schedulable": list(SCHEDULABLE),
    }
