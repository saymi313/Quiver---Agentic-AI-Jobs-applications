"""Read-only views over companies_dataset.csv, send_log.jsonl and .env."""

from __future__ import annotations

import csv
import json
import os
from collections import Counter
from typing import Any

from .config import APP_LOG, BASE_DIR, CSV_FILE, SEND_LOG

TERMINAL = {"Applied", "Interview", "Offer", "Rejected", "Failed"}


def _read_rows() -> tuple[list[str], list[dict[str, str]]]:
    if not CSV_FILE.is_file():
        return [], []
    with open(CSV_FILE, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


def pipeline_stats() -> dict[str, Any]:
    fieldnames, rows = _read_rows()
    if not rows:
        return {
            "csvPresent": CSV_FILE.is_file(),
            "total": 0, "statuses": {}, "verticals": [], "applyMethods": {},
            "withEmail": 0, "readyToSend": 0, "tailoredResumes": 0, "columns": fieldnames,
        }

    statuses = Counter((r.get("Application Status") or "Pending").strip() or "Pending" for r in rows)
    verticals = Counter((r.get("Vertical") or "—").strip() for r in rows)
    methods = Counter((r.get("Apply Method") or "Unknown").strip() for r in rows)

    def target_email(row: dict[str, str]) -> str:
        for key in ("Apply Email", "HR Email", "Info Email"):
            v = (row.get(key) or "").strip()
            if v and "@" in v:
                return v
        return ""

    with_email = sum(1 for r in rows if target_email(r))
    ready = sum(
        1 for r in rows
        if target_email(r) and (r.get("Application Status") or "Pending").strip() not in TERMINAL
    )
    tailored = sum(1 for r in rows if (r.get("Generated Resume") or "").strip())

    vert_list = [
        {
            "name": name,
            "total": count,
            "applied": sum(
                1 for r in rows
                if (r.get("Vertical") or "—").strip() == name
                and (r.get("Application Status") or "").strip() == "Applied"
            ),
        }
        for name, count in verticals.most_common()
    ]

    return {
        "csvPresent": True,
        "total": len(rows),
        "statuses": dict(statuses),
        "verticals": vert_list,
        "applyMethods": dict(methods.most_common(8)),
        "withEmail": with_email,
        "readyToSend": ready,
        "tailoredResumes": tailored,
        "columns": fieldnames,
    }


def _tail_jsonl(path, limit: int) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out[-limit:][::-1]


def send_log(limit: int = 40) -> list[dict[str, Any]]:
    return _tail_jsonl(SEND_LOG, limit)


def application_log(limit: int = 25) -> list[dict[str, Any]]:
    return _tail_jsonl(APP_LOG, limit)


def environment() -> dict[str, Any]:
    env_file = BASE_DIR / ".env"
    gmail = ""
    if env_file.is_file():
        for raw in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if line.startswith("GMAIL_ADDRESS="):
                gmail = line.partition("=")[2].strip().strip('"').strip("'")
    gmail = gmail or os.environ.get("GMAIL_ADDRESS", "")

    has_pass = False
    if env_file.is_file():
        text = env_file.read_text(encoding="utf-8", errors="replace")
        for raw in text.splitlines():
            if raw.strip().startswith("GMAIL_APP_PASS="):
                value = raw.partition("=")[2].strip().strip('"').strip("'")
                has_pass = bool(value) and "xxxx" not in value.lower()
    has_pass = has_pass or bool(os.environ.get("GMAIL_APP_PASS"))

    return {
        "envFilePresent": env_file.is_file(),
        "gmailAddress": gmail,
        "gmailPasswordSet": has_pass,
        "credentialsJson": (BASE_DIR / "credentials.json").is_file(),
        "profileYaml": (BASE_DIR / "cv_data" / "profile.yaml").is_file(),
        "sendLogPresent": SEND_LOG.is_file(),
    }


def verticals() -> list[str]:
    _, rows = _read_rows()
    return sorted({(r.get("Vertical") or "").strip() for r in rows if (r.get("Vertical") or "").strip()})
