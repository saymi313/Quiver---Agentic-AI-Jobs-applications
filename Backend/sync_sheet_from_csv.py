"""
Replace the Google Sheet "Leads" tab with the current companies_dataset.csv.

Requires:
  - pip install gspread google-auth
  - credentials.json (service account) in this folder, sheet shared with that email

Usage:
  python sync_sheet_from_csv.py
"""
from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
CSV_FILE = BASE_DIR / "companies_dataset.csv"
CREDENTIALS_FILE = BASE_DIR / "credentials.json"

# Reuse the same column order as prospecting_pipeline (sheet header row)
from prospecting_pipeline import HEADERS, SHEET_NAME, WORKSHEET_NAME, get_worksheet  # noqa: E402


def load_csv_rows() -> list[dict]:
    if not CSV_FILE.is_file():
        print(f"[ERROR] {CSV_FILE} not found.", file=sys.stderr)
        sys.exit(1)
    with CSV_FILE.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main() -> int:
    if not os.path.exists(CREDENTIALS_FILE):
        print(
            f"[ERROR] {CREDENTIALS_FILE} not found. Add a Google service account JSON "
            "and share the spreadsheet with the service account email.",
            file=sys.stderr,
        )
        return 1

    rows = load_csv_rows()
    values: list[list[str]] = [list(HEADERS)]
    for r in rows:
        values.append([str(r.get(col, "") or "") for col in HEADERS])

    ws = get_worksheet()
    if ws is None:
        print(
            "[ERROR] Could not open worksheet (install gspread, add credentials, share sheet).",
            file=sys.stderr,
        )
        return 1

    # Full replace: clear then write header + data
    try:
        ws.clear()
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] clear() failed (continuing): {exc}")

    # Resize if needed
    nrows = len(values)
    ncols = len(HEADERS)
    try:
        ws.resize(rows=nrows, cols=ncols)
    except Exception:
        pass

    try:
        ws.update("A1", values, value_input_option="USER_ENTERED")
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    print(f"[OK] Google Sheet '{SHEET_NAME}' / '{WORKSHEET_NAME}': {len(rows)} data rows + header.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
