"""
Build a static LaTeX resume from cv_data/profile.yaml (all bullets) and
compile to PDF. Requires pdflatex or latexmk on PATH (MiKTeX / TeX Live).

  python build_resume.py
  python build_resume.py --tex-only
  python build_resume.py --profile path/to/custom_profile.yaml
"""

import argparse
import json
import sys
from pathlib import Path

from cv_engine import PROFILE_PATH, run_build


def main() -> int:
    ap = argparse.ArgumentParser(description="Build static PDF resume from profile.yaml")
    ap.add_argument("--profile", type=Path, default=None, help="Override profile YAML")
    ap.add_argument(
        "--tex-only",
        action="store_true",
        help="Write resume.tex only; do not require LaTeX (useful to inspect output).",
    )
    args = ap.parse_args()

    try:
        meta = run_build(
            profile_path=args.profile,
            static=True,
            tex_only=args.tex_only,
        )
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    print(json.dumps(meta, indent=2))
    print(f"\n[OK] Wrote: {meta.get('tex')}")
    if meta.get("pdf"):
        print(f"     PDF:  {meta['pdf']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
