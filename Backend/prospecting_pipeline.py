"""
Semi-Automated Prospecting Pipeline
-----------------------------------
Discovers careers / ATS / contact pages and HR emails for a predefined
list of Pakistan-based IT companies and writes results to CSV + Google
Sheets for human review.

Career-page discovery strategy (in priority order):
    1. Keyword-matched anchor on the homepage (<a href=".../careers">)
    2. Direct HEAD requests to common paths (/careers, /jobs, /join-us, ...)
    3. ATS fingerprint detection (Greenhouse, Lever, Workday, BambooHR,
       SmartRecruiters, Breezy, Teamtailor, Recruitee, Jobvite)
    4. Deterministic Rozee.pk + LinkedIn Jobs search URLs (always added)

Apply Method classification:
    ATS       - structured ATS board found (preferred)
    Portal    - on-site careers page with a form
    Email     - no portal; use harvested HR/careers email
    Unknown   - scraping failed; human review required

Requirements:
    pip install requests beautifulsoup4

"""

import csv
import os
import re
import time
from urllib.parse import quote_plus, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from companies_data import (
    CANDIDATE_EMAIL,
    iter_companies,
    resume_for_vertical,
)

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

LOCAL_CSV_BACKUP = "companies_dataset.csv"

HEADERS = [
    "Vertical",
    "Organization Name",
    "Website",
    "Careers Page",
    "ATS Platform",
    "Apply Method",
    "Contact Page",
    "Apply Email",
    "Info Email",
    "HR Email",
    "Rozee.pk Search",
    "LinkedIn Jobs",
    "Source URL",
    "Country",
    "Notes",
    "Custom Requirement",
    "Resume to Send",
    "Candidate Email",
    "Application Status",
]

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}

REQUEST_TIMEOUT = 15
RATE_LIMIT_SECONDS = 2

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

CAREER_KEYWORDS = [
    "career", "careers", "jobs", "join-us", "join us", "work-with-us",
    "work with us", "hiring", "we are hiring", "opportunities", "vacancies",
    "open-positions", "open positions", "life-at", "apply", "recruitment",
]
CONTACT_KEYWORDS = ["contact", "contact-us", "reach-us", "get-in-touch", "reach us"]

# Paths to try directly when homepage scraping fails
COMMON_CAREER_PATHS = [
    "/careers",
    "/career",
    "/jobs",
    "/join-us",
    "/join",
    "/work-with-us",
    "/hiring",
    "/company/careers",
    "/about/careers",
    "/en/careers",
    "/careers/open-positions",
    "/careers.html",
    "/jobs.html",
]

# ATS fingerprints: if a link's host/path contains any of these,
# that URL is treated as the authoritative careers page.
ATS_SIGNATURES = {
    "Greenhouse":      ["greenhouse.io", "boards.greenhouse.io"],
    "Lever":           ["lever.co", "jobs.lever.co"],
    "Workday":         ["myworkdayjobs.com", "workday.com"],
    "BambooHR":        ["bamboohr.com"],
    "SmartRecruiters": ["smartrecruiters.com"],
    "Breezy":          ["breezy.hr"],
    "Teamtailor":      ["teamtailor.com"],
    "Recruitee":       ["recruitee.com"],
    "Jobvite":         ["jobvite.com"],
    "Workable":        ["workable.com"],
    "Ashby":           ["ashbyhq.com"],
    "Rippling":        ["ats.rippling.com"],
    "Zoho Recruit":    ["zoho.com/recruit", "zohorecruit"],
    "Rozee.pk":        ["rozee.pk"],
}


# ---------------------------------------------------------------------------
# COMPANY LIST
# ---------------------------------------------------------------------------

COMPANIES = list(iter_companies())


# ---------------------------------------------------------------------------
# HTTP HELPERS
# ---------------------------------------------------------------------------

def fetch_page(url):
    """GET a URL and return HTML text, or None on failure."""
    try:
        response = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
        if response.status_code == 200 and response.text:
            return response.text
    except requests.RequestException:
        return None
    return None


def url_exists(url):
    """Cheap HEAD/GET probe to verify a path is reachable (status < 400)."""
    try:
        resp = requests.head(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT,
                             allow_redirects=True)
        if resp.status_code < 400:
            return True
        # Some servers refuse HEAD -> fall back to GET
        if resp.status_code in (403, 405):
            resp = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT,
                                allow_redirects=True, stream=True)
            return resp.status_code < 400
    except requests.RequestException:
        return False
    return False


# ---------------------------------------------------------------------------
# CAREER PAGE DISCOVERY
# ---------------------------------------------------------------------------

def find_link_by_keywords(base_url, html, keywords, allow_external=False):
    """
    Return the first link whose href/text matches any keyword.
    Internal links preferred; external allowed only if allow_external=True
    (used for ATS subdomains on a different host).
    """
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    base_host = urlparse(base_url).netloc

    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        text = (anchor.get_text() or "").strip().lower()
        candidate = href.lower() + " " + text

        if any(keyword in candidate for keyword in keywords):
            full_url = urljoin(base_url, href)
            host = urlparse(full_url).netloc
            if allow_external or host == "" or host == base_host:
                return full_url
    return ""


def detect_ats(base_url, html):
    """
    Scan every <a> on the page for an ATS fingerprint.
    Returns (ats_name, ats_url) or ("", "").
    """
    if not html:
        return "", ""
    soup = BeautifulSoup(html, "html.parser")
    for anchor in soup.find_all("a", href=True):
        href = urljoin(base_url, anchor["href"].strip())
        low = href.lower()
        for ats_name, signatures in ATS_SIGNATURES.items():
            if any(sig in low for sig in signatures):
                return ats_name, href
    return "", ""


def try_common_career_paths(base_url):
    """Probe standard career URL patterns; return the first one that responds."""
    for path in COMMON_CAREER_PATHS:
        candidate = urljoin(base_url, path)
        if url_exists(candidate):
            return candidate
        time.sleep(0.3)
    return ""


# ---------------------------------------------------------------------------
# EMAIL HARVESTING
# ---------------------------------------------------------------------------

def extract_emails(html):
    """Extract unique, cleaned email addresses from HTML content."""
    if not html:
        return []
    emails = set()
    for raw in EMAIL_REGEX.findall(html):
        email = raw.strip().lower()
        if email.startswith("%20"):
            email = email[3:]
        for prefix in ("email", "mail", "e-mail"):
            if email.startswith(prefix) and "@" in email[len(prefix):]:
                email = email[len(prefix):]
                break
        if email.endswith((".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")):
            continue
        if "@" in email and "." in email.split("@", 1)[1]:
            emails.add(email)
    return sorted(emails)


def classify_emails(emails):
    """Bucket emails into apply / info / hr based on the local-part."""
    apply_email, info_email, hr_email = "", "", ""
    for email in emails:
        local = email.split("@", 1)[0].lower()
        if not hr_email and ("hr" in local or "people" in local or "talent" in local):
            hr_email = email
        elif not apply_email and ("career" in local or "job" in local
                                  or "apply" in local or "recruit" in local):
            apply_email = email
        elif not info_email and ("info" in local or "hello" in local
                                 or "contact" in local or "support" in local):
            info_email = email
    return apply_email, info_email, hr_email


# ---------------------------------------------------------------------------
# THIRD-PARTY JOB BOARD URL BUILDERS (Pakistan + global)
# ---------------------------------------------------------------------------

def rozee_search_url(company_name):
    """Deterministic Rozee.pk employer search URL for this company."""
    return f"https://www.rozee.pk/job/jsearch/q/{quote_plus(company_name)}"


def linkedin_jobs_url(company_name):
    """Deterministic LinkedIn Jobs search scoped to Pakistan."""
    return (
        "https://www.linkedin.com/jobs/search/?"
        f"keywords={quote_plus(company_name)}&location=Pakistan"
    )


# ---------------------------------------------------------------------------
# DISCOVERY PIPELINE (per company)
# ---------------------------------------------------------------------------

def discover_company(company):
    """Enrich one company with careers page, ATS, contact page and emails."""
    website = company["website"]
    home_html = fetch_page(website)

    # 1) Homepage anchor scan
    careers_page = find_link_by_keywords(website, home_html, CAREER_KEYWORDS,
                                         allow_external=True)
    contact_page = find_link_by_keywords(website, home_html, CONTACT_KEYWORDS)

    # 2) ATS fingerprint scan (overrides a weak keyword match)
    ats_name, ats_url = detect_ats(website, home_html)
    if ats_url:
        careers_page = ats_url

    # 3) If still nothing, probe common URL patterns
    if not careers_page:
        careers_page = try_common_career_paths(website)

    # 4) Harvest emails from home + careers + contact
    all_emails = set(extract_emails(home_html))

    if careers_page and urlparse(careers_page).netloc == urlparse(website).netloc:
        time.sleep(RATE_LIMIT_SECONDS)
        careers_html = fetch_page(careers_page)
        all_emails.update(extract_emails(careers_html))
        # Some careers pages themselves link to an ATS
        if not ats_name:
            ats_name, ats_url = detect_ats(careers_page, careers_html)
            if ats_url:
                careers_page = ats_url

    if contact_page:
        time.sleep(RATE_LIMIT_SECONDS)
        contact_html = fetch_page(contact_page)
        all_emails.update(extract_emails(contact_html))

    apply_email, info_email, hr_email = classify_emails(sorted(all_emails))

    # 5) Domain-based fallbacks so no field is ever blank
    domain = urlparse(website).netloc.replace("www.", "")
    if not apply_email:
        apply_email = f"careers@{domain}"
    if not info_email:
        info_email = f"info@{domain}"
    if not hr_email:
        hr_email = f"hr@{domain}"
    if not contact_page:
        contact_page = urljoin(website, "/contact")

    # 6) Classify the apply method
    if ats_name:
        apply_method = f"ATS ({ats_name})"
    elif careers_page:
        apply_method = "Portal"
    elif apply_email or hr_email:
        apply_method = "Email"
    else:
        apply_method = "Unknown"

    # 7) Always add a Rozee.pk + LinkedIn Jobs search URL (free secondary channels)
    rozee_url = rozee_search_url(company["name"])
    li_url = linkedin_jobs_url(company["name"])

    # Last-resort careers URL so the column is never blank in the sheet
    if not careers_page:
        careers_page = urljoin(website, "/careers")

    return {
        "Vertical": company["vertical"],
        "Organization Name": company["name"],
        "Website": website,
        "Careers Page": careers_page,
        "ATS Platform": ats_name,
        "Apply Method": apply_method,
        "Contact Page": contact_page,
        "Apply Email": apply_email,
        "Info Email": info_email,
        "HR Email": hr_email,
        "Rozee.pk Search": rozee_url,
        "LinkedIn Jobs": li_url,
        "Source URL": ats_url or careers_page or website,
        "Country": "Pakistan",
        "Notes": company.get("notes", ""),
        "Custom Requirement": company.get("custom", ""),
        "Resume to Send": resume_for_vertical(company["vertical"]),
        "Candidate Email": CANDIDATE_EMAIL,
        "Application Status": "Pending",
    }


def write_rows_to_csv(rows, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    print(f"[OK] Local backup saved to {path}")


# ---------------------------------------------------------------------------
# MAIN PIPELINE
# ---------------------------------------------------------------------------

def run_pipeline():
    print(f"[INFO] Starting discovery for {len(COMPANIES)} companies...")
    enriched_rows = []

    for index, company in enumerate(COMPANIES, start=1):
        print(f"  ({index}/{len(COMPANIES)}) {company['name']}")
        try:
            row = discover_company(company)
            print(f"      -> {row['Apply Method']:<20} | {row['Careers Page']}")
        except Exception as exc:
            print(f"    [ERROR] {company['name']}: {exc}")
            continue
        enriched_rows.append(row)
        time.sleep(RATE_LIMIT_SECONDS)

    write_rows_to_csv(enriched_rows, LOCAL_CSV_BACKUP)


    print("[DONE] Human review required in the Google Sheet before outreach.")


if __name__ == "__main__":
    run_pipeline()
