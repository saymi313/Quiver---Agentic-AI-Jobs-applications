"""
The one .env loader.

Four modules used to carry their own copy of this loop, each with its own
"already loaded" flag. Values never overwrite variables that are already set
(`setdefault`), so exporting a variable in the shell still wins over the file.
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

_loaded = False


def load(force: bool = False) -> None:
    global _loaded
    if _loaded and not force:
        return
    _loaded = True
    if not ENV_FILE.exists():
        return
    for raw in ENV_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def get(name: str, default: str = "") -> str:
    load()
    return os.environ.get(name, default).strip()
