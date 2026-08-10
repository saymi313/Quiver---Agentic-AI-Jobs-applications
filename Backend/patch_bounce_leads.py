"""Patch CSV: CreditBook = verified contact; DBank/Marham/Shifa4U = careers@ not found (Failed)."""
import csv
from pathlib import Path

HERE = Path(__file__).parent
CSV_FILE = HERE / "companies_dataset.csv"

def main() -> None:
    with CSV_FILE.open(encoding="utf-8", newline="") as f:
        rdr = csv.DictReader(f)
        fns = list(rdr.fieldnames or [])
        rows = list(rdr)

    for r in rows:
        name = (r.get("Organization Name") or "").strip()
        if name == "CreditBook":
            r["Apply Email"] = "ali.hamdani@creditbook.pk"
            r["HR Email"] = ""
            r["Application Status"] = "Applied"
            n = (r.get("Notes") or "").strip()
            tag = "ali.hamdani@creditbook.pk"
            if tag not in n:
                r["Notes"] = (n + " Application contact: ali.hamdani@creditbook.pk (verified).").strip()
        elif name in ("DBank", "Marham", "Shifa4U"):
            r["Application Status"] = "Failed"
            r["Apply Email"] = ""
            r["HR Email"] = ""
            n = (r.get("Notes") or "").strip()
            tag = "careers@ not found / undeliverable"
            if tag not in n:
                r["Notes"] = (n + " " + tag + "; try info@, careers portal, or LinkedIn.").strip()

    with CSV_FILE.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fns)
        w.writeheader()
        w.writerows(rows)
    print("[OK] Updated CreditBook, DBank, Marham, Shifa4U in", CSV_FILE.name)

if __name__ == "__main__":
    main()
