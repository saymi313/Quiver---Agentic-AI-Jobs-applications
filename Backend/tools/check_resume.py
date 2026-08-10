"""
Audit a generated resume PDF against the house style — CLI wrapper.

The rules themselves live in api/resume_audit.py, where the tailor uses them
as a hard gate before recording any PDF. This script just prints the results.

    python tools/check_resume.py                       # every PDF in cv_data/
    python tools/check_resume.py cv_data/Some.pdf
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

from api.config import CV_DATA  # noqa: E402
from api.resume_audit import audit_pdf, page_count  # noqa: E402


def audit(pdf: Path) -> list[str]:
    fails = audit_pdf(pdf)
    pages = page_count(pdf)
    print(f"\n{'=' * 66}\n{pdf.name}  ({pages} page{'s' if pages != 1 else ''})\n{'=' * 66}")
    if fails:
        for f in fails:
            print(f"  FAIL  {f}")
    else:
        print("  PASS  every house style rule")
    return fails


def main() -> int:
    targets = ([Path(a) for a in sys.argv[1:]]
               or sorted(p for p in CV_DATA.glob("*.pdf")))
    if not targets:
        print("no PDFs found")
        return 1
    total = sum(len(audit(t)) for t in targets)
    print(f"\n{total} failure(s) across {len(targets)} file(s)")
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
