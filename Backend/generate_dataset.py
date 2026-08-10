"""
Generate companies_dataset.csv from companies_data.py.

Derives standard careers/contact URLs and apply/info/hr emails from
the website of each company, and attaches the correct resume and
candidate email per vertical.
"""

import csv
from pathlib import Path
from urllib.parse import urljoin, urlparse

from companies_data import CANDIDATE_EMAIL, iter_companies, resume_for_vertical

BASE_DIR = Path(__file__).parent
CSV_FILE = BASE_DIR / "companies_dataset.csv"

HEADERS = [
    "Vertical",
    "Organization Name",
    "Website",
    "Careers Page",
    "Contact Page",
    "Apply Email",
    "Info Email",
    "HR Email",
    "Source URL",
    "Country",
    "Notes",
    "Custom Requirement",
    "Resume to Send",
    "Candidate Email",
    "Application Status",
]


def domain_of(website: str) -> str:
    """Return bare domain (without www.) for email construction."""
    host = urlparse(website).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def build_row(company: dict) -> dict:
    website = company["website"]
    careers = urljoin(website, "/careers")
    contact = urljoin(website, "/contact")
    host = domain_of(website)

    return {
        "Vertical": company["vertical"],
        "Organization Name": company["name"],
        "Website": website,
        "Careers Page": careers,
        "Contact Page": contact,
        "Apply Email": f"careers@{host}",
        "Info Email": f"info@{host}",
        "HR Email": f"hr@{host}",
        "Source URL": careers,
        "Country": "Pakistan",
        "Notes": company["notes"],
        "Custom Requirement": company["custom"],
        "Resume to Send": resume_for_vertical(company["vertical"]),
        "Candidate Email": CANDIDATE_EMAIL,
        "Application Status": "Pending",
    }


def main():
    rows = [build_row(c) for c in iter_companies()]

    with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"[OK] Wrote {len(rows)} companies to {CSV_FILE}")


if __name__ == "__main__":
    main()
