"""
Run the existing pipeline scripts as child processes and stream their output.

Only the scripts declared in config.RUNNABLE can be launched, and their flags
are rebuilt from typed values here — the browser never supplies a command line.
Exactly one job runs at a time, because several of these scripts read/modify
companies_dataset.csv.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .config import BASE_DIR, RUNNABLE

MAX_LINES = 4000


@dataclass
class Job:
    id: str
    key: str
    label: str
    command: list[str]
    status: str = "running"          # running | finished | failed | stopped
    returncode: int | None = None
    started_at: str = ""
    finished_at: str | None = None
    lines: list[str] = field(default_factory=list)
    truncated: int = 0
    proc: subprocess.Popen | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)

    def summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "key": self.key,
            "label": self.label,
            # command[0] is the interpreter and command[1] is "-u"; the UI shows
            # the script and its flags only.
            "command": " ".join(self.command[2:]),
            "status": self.status,
            "returncode": self.returncode,
            "startedAt": self.started_at,
            "finishedAt": self.finished_at,
            "lineCount": len(self.lines) + self.truncated,
        }


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._order: list[str] = []
        self._guard = threading.Lock()

    # ---------------------------------------------------------------- helpers
    def active(self) -> Job | None:
        with self._guard:
            for jid in reversed(self._order):
                job = self._jobs[jid]
                if job.status == "running":
                    return job
        return None

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def recent(self, limit: int = 12) -> list[dict[str, Any]]:
        with self._guard:
            ids = list(reversed(self._order))[:limit]
        return [self._jobs[i].summary() for i in ids]

    # ------------------------------------------------------------------ start
    def build_command(self, key: str, options: dict[str, Any]) -> list[str]:
        """
        Rebuild the command line from typed, range-clamped values. The browser
        never supplies argv — only which task and which options.
        """
        spec = RUNNABLE[key]
        if "module" in spec:
            cmd = [sys.executable, "-u", "-m", spec["module"], spec["subcommand"]]
        else:
            cmd = [sys.executable, "-u", spec["script"]]
        allowed = set(spec["flags"])

        # boolean switches
        for flag, arg in (("dry_run", "--dry-run"), ("to_self", "--to-self"),
                          ("no_people", "--no-people"), ("no_ats", "--no-ats"),
                          ("no_attach", "--no-attach"), ("headed", "--headed"),
                          ("no_review", "--no-review")):
            if flag in allowed and options.get(flag):
                cmd.append(arg)

        if "limit" in allowed and options.get("limit") is not None:
            cmd += ["--limit", str(max(1, min(int(options["limit"]), 500)))]
        if "workers" in allowed and options.get("workers") is not None:
            cmd += ["--workers", str(max(1, min(int(options["workers"]), 3)))]
        if "max_age" in allowed and options.get("max_age") is not None:
            cmd += ["--max-age", str(max(1, min(int(options["max_age"]), 365)))]
        if "delay" in allowed and options.get("delay") is not None:
            cmd += ["--delay", str(max(0, min(int(options["delay"]), 3600)))]
        if "vertical" in allowed and options.get("vertical"):
            cmd += ["--vertical", str(options["vertical"])[:80]]
        if "sources" in allowed and options.get("sources"):
            raw = options["sources"]
            picked = raw if isinstance(raw, list) else str(raw).split(",")
            allowed_sources = {"yc", "hn", "remote", "hidden"}
            clean = [s.strip().lower() for s in picked if s.strip().lower() in allowed_sources]
            if clean:
                cmd += ["--sources", ",".join(dict.fromkeys(clean))]
        if "job_ids" in allowed and options.get("job_ids"):
            raw = options["job_ids"]
            picked = raw if isinstance(raw, list) else str(raw).split(",")
            # Integers only, and capped — this is the one option that decides
            # which real applications get submitted.
            ids = [str(int(x)) for x in picked if str(x).strip().lstrip("-").isdigit()][:100]
            if ids:
                cmd += ["--job-ids", ",".join(dict.fromkeys(ids))]
        return cmd

    def start(self, key: str, options: dict[str, Any]) -> Job:
        if key not in RUNNABLE:
            raise KeyError(f"Unknown task: {key}")
        running = self.active()
        if running is not None:
            raise RuntimeError(
                f"'{running.label}' is still running. Stop it before starting another task — "
                "these scripts share companies_dataset.csv."
            )

        spec = RUNNABLE[key]
        if "module" in spec:
            package = spec["module"].split(".")[0]
            if not (BASE_DIR / package).is_dir():
                raise FileNotFoundError(f"Package '{package}' not found in {BASE_DIR}")
        else:
            if not (BASE_DIR / spec["script"]).is_file():
                raise FileNotFoundError(f"{spec['script']} not found in {BASE_DIR}")

        cmd = self.build_command(key, options)
        job = Job(
            id=uuid.uuid4().hex[:12],
            key=key,
            label=spec["label"],
            command=cmd,
            started_at=datetime.now(timezone.utc).isoformat(),
        )

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"

        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

        job.proc = subprocess.Popen(
            cmd,
            cwd=str(BASE_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=env,
            creationflags=creationflags,
        )

        with self._guard:
            self._jobs[job.id] = job
            self._order.append(job.id)
            if len(self._order) > 40:
                old = self._order.pop(0)
                self._jobs.pop(old, None)

        self._append(job, f"$ python {' '.join(cmd[2:])}")
        threading.Thread(target=self._pump, args=(job,), daemon=True).start()
        return job

    # ------------------------------------------------------------------- pump
    def _append(self, job: Job, line: str) -> None:
        with job.lock:
            job.lines.append(line)
            if len(job.lines) > MAX_LINES:
                drop = len(job.lines) - MAX_LINES
                del job.lines[:drop]
                job.truncated += drop

    def _pump(self, job: Job) -> None:
        assert job.proc is not None
        try:
            for raw in job.proc.stdout:  # type: ignore[union-attr]
                self._append(job, raw.rstrip("\n"))
        except Exception as exc:  # pragma: no cover
            self._append(job, f"[reader error] {exc}")
        finally:
            code = job.proc.wait()
            job.returncode = code
            if job.status == "stopping":
                job.status = "stopped"
                self._append(job, "[stopped by user]")
            elif code == 0:
                job.status = "finished"
                self._append(job, "[done]")
            else:
                job.status = "failed"
                self._append(job, f"[exited with code {code}]")
            job.finished_at = datetime.now(timezone.utc).isoformat()

    # ------------------------------------------------------------------- stop
    def stop(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None or job.proc is None or job.status != "running":
            return False
        job.status = "stopping"
        try:
            job.proc.terminate()
        except Exception:
            return False
        threading.Thread(target=self._force_kill, args=(job,), daemon=True).start()
        return True

    def _force_kill(self, job: Job) -> None:
        deadline = time.time() + 8
        while time.time() < deadline:
            if job.proc is None or job.proc.poll() is not None:
                return
            time.sleep(0.25)
        try:
            if job.proc is not None:
                job.proc.kill()
        except Exception:
            pass

    # ------------------------------------------------------------------ reads
    def slice_lines(self, job: Job, start: int) -> tuple[list[str], int]:
        with job.lock:
            base = job.truncated
            if start < base:
                start = base
            idx = start - base
            return list(job.lines[idx:]), base + len(job.lines)


manager = JobManager()
