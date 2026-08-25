"""
Start the dashboard. Run this from the Backend/ folder.

    python run_dashboard.py            # API + Vite dev server, opens the browser
    python run_dashboard.py --api-only # just the FastAPI backend on :8000
    python run_dashboard.py --build    # serve the built UI from FastAPI (no Node needed)

The API is served out of Backend/ and the UI out of ../Frontend/. Dev mode needs
Node; if Frontend/node_modules is missing it runs `npm install` for you the
first time.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

BASE_DIR = Path(__file__).parent          # <root>/Backend
PROJECT_ROOT = BASE_DIR.parent            # <root>
FRONTEND = PROJECT_ROOT / "Frontend"
API_PORT = 8000
UI_PORT = 5173


def npm_cmd() -> str | None:
    for candidate in ("npm.cmd", "npm") if os.name == "nt" else ("npm",):
        found = shutil.which(candidate)
        if found:
            return found
    return None


def ensure_node_modules(npm: str) -> bool:
    if (FRONTEND / "node_modules").is_dir():
        return True
    print("[setup] installing Frontend dependencies (first run only)...")
    result = subprocess.run([npm, "install"], cwd=str(FRONTEND))
    if result.returncode != 0:
        print("[setup] npm install failed.", file=sys.stderr)
        return False
    return True


def start_api(port: int) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(BASE_DIR),
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the Jobenzy dashboard")
    ap.add_argument("--api-only", action="store_true", help="Start only the FastAPI backend")
    ap.add_argument("--build", action="store_true", help="Build the UI, then serve it from FastAPI")
    ap.add_argument("--no-browser", action="store_true", help="Do not open a browser window")
    ap.add_argument("--port", type=int, default=API_PORT)
    args = ap.parse_args()

    npm = npm_cmd()

    if args.build:
        if not npm:
            print("[error] npm not found on PATH — install Node.js to build the UI.", file=sys.stderr)
            return 1
        if not ensure_node_modules(npm):
            return 1
        print("[build] compiling the Frontend...")
        if subprocess.run([npm, "run", "build"], cwd=str(FRONTEND)).returncode != 0:
            return 1
        print(f"[ok] serving http://127.0.0.1:{args.port}")
        if not args.no_browser:
            threading.Timer(1.5, webbrowser.open, [f"http://127.0.0.1:{args.port}"]).start()
        return subprocess.run(
            [sys.executable, "-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", str(args.port)],
            cwd=str(BASE_DIR),
        ).returncode

    api = start_api(args.port)
    ui = None
    try:
        if not args.api_only:
            if not npm:
                print("[warn] npm not found — running API only. Install Node.js for the UI, "
                      "or use --build once it is available.")
            elif ensure_node_modules(npm):
                ui = subprocess.Popen([npm, "run", "dev"], cwd=str(FRONTEND))
                if not args.no_browser:
                    threading.Timer(3.0, webbrowser.open, [f"http://localhost:{UI_PORT}"]).start()

        print(f"\n[ok] API   http://127.0.0.1:{args.port}")
        if ui:
            print(f"[ok] UI    http://localhost:{UI_PORT}")
        print("[info] Ctrl+C to stop.\n")

        while True:
            if api.poll() is not None:
                print("[error] API process exited.", file=sys.stderr)
                return api.returncode or 1
            if ui is not None and ui.poll() is not None:
                print("[error] Vite dev server exited.", file=sys.stderr)
                return ui.returncode or 1
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[info] shutting down...")
        return 0
    finally:
        for proc in (ui, api):
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=6)
                except subprocess.TimeoutExpired:
                    proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
