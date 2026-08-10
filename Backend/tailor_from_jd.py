"""
Build a JD-tailored resume: selects/reorders bullets by tag overlap with the
job description, optionally switches the AI profile summary, writes PDF, logs
to applications.jsonl, and can patch companies_dataset.csv with
'Generated Resume' (relative path) for send_applications.py.

  python tailor_from_jd.py --jd jd_sadapay.txt --company "SadaPay" --update-csv
  python tailor_from_jd.py --jd jd.txt --slug sadapay
  python tailor_from_jd.py --jd jd.txt --slug sadapay --tex-only
"""

import argparse
import csv
import json
import os
import sys
from pathlib import Path

from cv_engine import BASE_DIR, run_build

CSV_NAME = "companies_dataset.csv"
GEN_COL = "Generated Resume"
REQUIRED_CSV_EXTRAS = [GEN_COL, "Job Description Hash"]


def _ensure_columns(fieldnames: list, rows: list[dict], extras: list[str]) -> list[str]:
    fn = list(fieldnames)
    for c in extras:
        if c not in fn:
            fn.append(c)
    for r in rows:
        for c in fn:
            r.setdefault(c, "")
    return fn


def _find_row_index(rows: list[dict], org_name: str) -> int:
    o = (org_name or "").strip().lower()
    for i, r in enumerate(rows):
        if (r.get("Organization Name") or "").strip().lower() == o:
            return i
    return -1


def main() -> int:
    ap = argparse.ArgumentParser(description="Tailor resume from job description")
    ap.add_argument("--jd", type=Path, help="Text file with job description (required for tailor)")
    ap.add_argument("--profile", type=Path, default=None, help="Override profile.yaml")
    ap.add_argument(
        "--slug",
        type=str,
        default="",
        help="Folder name segment (e.g. sadapay). Default: 'job' if omitted.",
    )
    ap.add_argument("--tex-only", action="store_true", help="Only write .tex, skip PDF build")
    ap.add_argument(
        "--company",
        type=str,
        default="",
        help="If set with --update-csv, match this Organization Name exactly",
    )
    ap.add_argument(
        "--update-csv",
        action="store_true",
        help=f"Set '{GEN_COL}' and JD hash for the matched company row in {CSV_NAME}",
    )
    args = ap.parse_args()

    if not args.jd or not args.jd.is_file():
        print("[ERROR] Provide an existing file: --jd path/to/jd.txt", file=sys.stderr)
        return 1

    try:
        meta = run_build(
            profile_path=args.profile,
            jd_path=args.jd,
            static=False,
            out_slug=args.slug or "job",
            tex_only=args.tex_only,
        )
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    print(json.dumps(meta, indent=2))
    if meta.get("pdf"):
        print(f"\n[OK] PDF: {meta['pdf']}")
    else:
        print(f"\n[OK] TeX: {meta['tex']}")

    if args.update_csv:
        csv_path = BASE_DIR / CSV_NAME
        if not csv_path.is_file():
            print(f"[WARN] {CSV_NAME} not found; skipped CSV update.", file=sys.stderr)
            return 0
        if not args.company:
            print("[ERROR] --update-csv requires --company \"Organization Name\"", file=sys.stderr)
            return 1
        with open(csv_path, encoding="utf-8", newline="") as f:
            rdr = csv.DictReader(f)
            fieldnames = list(rdr.fieldnames or [])
            rows = list(rdr)
        fieldnames = _ensure_columns(fieldnames, rows, REQUIRED_CSV_EXTRAS)
        idx = _find_row_index(rows, args.company)
        if idx < 0:
            print(
                f"[ERROR] No row with Organization Name = {args.company!r}",
                file=sys.stderr,
            )
            return 1
        rel = ""
        if meta.get("pdf"):
            rel = os.path.relpath(meta["pdf"], BASE_DIR).replace(os.sep, "/")
            rows[idx][GEN_COL] = rel
        rows[idx]["Job Description Hash"] = meta.get("jd_hash") or ""
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(rows)
        print(f"\n[OK] Updated row for {args.company!r}: {GEN_COL}={rel or '(tex-only)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
