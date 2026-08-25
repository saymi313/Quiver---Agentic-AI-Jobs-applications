"""
Fetch a LaTeX engine so the Resume Tailor can produce real LaTeX PDFs.

Downloads Tectonic: one self-contained binary, no system-wide TeX install, no
admin rights. Run once from Backend/:

    python tools/install_tex.py

After this, api/latex_resume.py finds it automatically in Backend/tools/.
"""

from __future__ import annotations

import io
import json
import platform
import ssl
import sys
import urllib.request
import zipfile
from pathlib import Path

TOOLS = Path(__file__).parent
RELEASES = "https://api.github.com/repos/tectonic-typesetting/tectonic/releases/latest"


def asset_for_platform(assets: list[dict]) -> dict | None:
    system, machine = platform.system().lower(), platform.machine().lower()
    arch = "x86_64" if machine in ("amd64", "x86_64") else "aarch64"
    wanted = {"windows": f"{arch}-pc-windows-msvc",
              "darwin": f"{arch}-apple-darwin",
              "linux": f"{arch}-unknown-linux-gnu"}.get(system, "")
    for a in assets:
        n = a["name"]
        if wanted and wanted in n and n.endswith((".zip", ".tar.gz")):
            return a
    return None


def main() -> int:
    existing = list(TOOLS.glob("tectonic*"))
    if existing:
        print(f"[ok] already installed: {existing[0].name}")
        return 0

    print("[1/3] finding the latest Tectonic release...")
    req = urllib.request.Request(RELEASES, headers={"User-Agent": "jobenzy"})
    data = json.load(urllib.request.urlopen(req, timeout=60,
                                            context=ssl.create_default_context()))
    asset = asset_for_platform(data.get("assets", []))
    if not asset:
        print(f"[error] no Tectonic build for {platform.system()}/{platform.machine()}.",
              file=sys.stderr)
        print("        Install MiKTeX or TeX Live instead.", file=sys.stderr)
        return 1

    size_mb = asset["size"] // 1024 // 1024
    print(f"[2/3] downloading {asset['name']} ({size_mb} MB)...")
    req = urllib.request.Request(asset["browser_download_url"],
                                 headers={"User-Agent": "jobenzy"})
    blob = urllib.request.urlopen(req, timeout=600,
                                  context=ssl.create_default_context()).read()

    print("[3/3] extracting...")
    if asset["name"].endswith(".zip"):
        zipfile.ZipFile(io.BytesIO(blob)).extractall(TOOLS)
    else:
        import tarfile
        tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz").extractall(TOOLS)

    for f in TOOLS.glob("tectonic*"):
        if f.is_file():
            f.chmod(0o755)
            print(f"[ok] {f.name} ready. The Resume Tailor will now produce LaTeX PDFs.")
            return 0
    print("[error] archive did not contain a tectonic binary.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
