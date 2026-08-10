"""
One-time patch: mark bounces/invalid-hr@ rows as Failed and set public inboxes.
Re-run is optional; keep file for history.
"""
import csv
from pathlib import Path

HERE = Path(__file__).parent
CSV_FILE = HERE / "companies_dataset.csv"

# Public contacts (not guessed hr@). Sources: company contact/careers pages, Jazz group portal.
UPDATES: dict[str, dict] = {
    "SadaPay": {
        "Application Status": "Failed",
        "HR Email": "",
        "Apply Email": "hello@sadapay.pk",
        "Info Email": "info@sadapay.pk",
    },
    "JazzCash": {
        "Application Status": "Failed",
        "HR Email": "",
        "Apply Email": "careers@jazz.com.pk",
        "Info Email": "info@jazz.com.pk",
    },
    "Easypaisa": {
        "Application Status": "Failed",
        "HR Email": "",
        "Apply Email": "info@easypaisa.com.pk",
        "Info Email": "info@easypaisa.com.pk",
    },
    "Oraan": {
        "Application Status": "Failed",
        "HR Email": "",
        "Apply Email": "support@oraan.com",
        "Info Email": "support@oraan.com",
    },
}
NOTE = " [Prev. send: hr@ undeliverable. Status=Failed; Apply Email updated. Resend: set to Pending.]"
JAZZ_EXTRA = " For roles also use https://jobs.jazz.com.pk."
EP_EXTRA = " Many roles: easypaisa.com.pk/careers (portal)."


def main() -> None:
    with CSV_FILE.open(encoding="utf-8", newline="") as f:
        rdr = csv.DictReader(f)
        fieldnames = rdr.fieldnames
        if not fieldnames:
            raise SystemExit("empty csv")
        rows = list(rdr)
    for row in rows:
        name = (row.get("Organization Name") or "").strip()
        if name not in UPDATES:
            continue
        u = UPDATES[name]
        for k, v in u.items():
            if k in row:
                row[k] = v
        n = (row.get("Notes") or "").strip()
        tag = "Status=Failed; Apply Email updated"
        if tag not in n:
            extra = ""
            if name == "JazzCash":
                extra = JAZZ_EXTRA
            elif name == "Easypaisa":
                extra = EP_EXTRA
            row["Notes"] = (n + NOTE + extra).strip()
    with CSV_FILE.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"[OK] Patched {len(UPDATES)} rows in {CSV_FILE.name}")


if __name__ == "__main__":
    main()
