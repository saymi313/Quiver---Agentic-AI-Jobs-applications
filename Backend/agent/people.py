"""
Find the human behind a startup, then prove the address is real.

Three ways in, best first:

  1. An email published in the company's HN "Who is hiring" post — the founder
     wrote it themselves, so it is both correct and welcoming.
  2. An address on the site (mailto: links, team and contact pages).
  3. A generated pattern (first@, first.last@) for a named founder, kept only
     if verification agrees the mailbox exists.

Verification is MX lookup + an SMTP RCPT probe. Two honest caveats, both handled
explicitly rather than papered over:

  * Many ISPs block outbound port 25. When that happens the probe cannot run at
    all, so addresses are scored on provenance alone and marked `unknown` —
    never silently promoted to `valid`.
  * Catch-all domains accept every address. Those are detected with a random
    control probe and marked `risky`, not `valid`.
"""

from __future__ import annotations

import random
import re
import smtplib
import socket
import string
from typing import Any, Callable, Iterable

from . import llm, sources
from .sources import EMAIL_RE, domain_of, strip_html

try:
    import dns.resolver
    HAVE_DNS = True
except ImportError:  # pragma: no cover
    HAVE_DNS = False

MAILTO_RE = re.compile(r"mailto:([^\"'?>\s]+)", re.I)

ROLE_PREFIXES = {
    "info", "hello", "hi", "contact", "support", "help", "sales", "admin",
    "office", "team", "press", "media", "legal", "privacy", "security",
    "billing", "accounts", "noreply", "no-reply", "donotreply", "notifications",
    "marketing", "partnerships", "bd", "enquiries", "inquiries", "general",
}
HIRING_PREFIXES = {"jobs", "careers", "hiring", "recruiting", "recruitment", "talent", "apply", "work"}
FOUNDER_PREFIXES = {"founders", "founder", "ceo", "cto"}

JUNK_DOMAINS = {
    "example.com", "sentry.io", "wixpress.com", "gmail.com", "googlemail.com",
    "yahoo.com", "hotmail.com", "outlook.com", "protonmail.com", "icloud.com",
    "domain.com", "email.com", "yourcompany.com", "squarespace.com", "wordpress.com",
}
JUNK_LOCAL_HINTS = ("sentry", "wixpress", "cloudflare", "godaddy", "@2x", "png", "jpg", "svg")

PEOPLE_SCHEMA = {
    "type": "object",
    "properties": {
        "people": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "full_name": {"type": "string"},
                    "title": {"type": "string"},
                    "role": {"type": "string",
                             "description": "one of: founder, recruiter, engineer, other"},
                    "email": {"type": "string", "description": "empty string if not stated on the page"},
                },
                "required": ["full_name", "title", "role", "email"],
            },
        }
    },
    "required": ["people"],
}


# --------------------------------------------------------------------------
# Extraction
# --------------------------------------------------------------------------

def _clean_email(raw: str) -> str:
    email = raw.strip().strip("<>\"'.,;:()").lower()
    email = email.split("?")[0]
    return email if EMAIL_RE.fullmatch(email) else ""


def _plausible(email: str, company_domain: str = "") -> bool:
    if not email or email.count("@") != 1:
        return False
    local, _, dom = email.partition("@")
    if not local or len(local) > 64 or len(dom) < 4:
        return False
    if dom in JUNK_DOMAINS and dom != company_domain:
        return False
    blob = email.lower()
    if any(j in blob for j in JUNK_LOCAL_HINTS):
        return False
    if re.fullmatch(r"[0-9a-f]{16,}", local):        # tracking hashes
        return False
    return True


def classify_role(email: str, hint: str = "") -> str:
    local = email.split("@")[0].lower()
    blob = f"{local} {hint}".lower()
    if local in FOUNDER_PREFIXES or any(w in blob for w in ("founder", "ceo", "cto", "co-founder")):
        return "founder"
    if local in HIRING_PREFIXES or any(w in blob for w in ("recruit", "talent", "people ops", "hr")):
        return "recruiter"
    if local in ROLE_PREFIXES:
        return "generic"
    return "unknown"


def emails_from_pages(pages: dict[str, str], company_domain: str = "") -> list[dict[str, Any]]:
    """Pull mailto: links and visible addresses out of crawled HTML."""
    found: dict[str, dict[str, Any]] = {}
    for url, html_text in pages.items():
        for raw in MAILTO_RE.findall(html_text):
            email = _clean_email(raw)
            if email and _plausible(email, company_domain):
                found.setdefault(email, {"email": email, "email_source": "site", "context": url})
        text = strip_html(html_text)
        for raw in EMAIL_RE.findall(text):
            email = _clean_email(raw)
            if email and _plausible(email, company_domain):
                idx = text.lower().find(email)
                context = text[max(0, idx - 120): idx + 60].replace("\n", " ") if idx >= 0 else url
                found.setdefault(email, {"email": email, "email_source": "site", "context": context})
    return list(found.values())


def people_from_llm(company: dict[str, Any], pages: dict[str, str], *,
                    log: Callable[[str], None] = lambda _: None) -> list[dict[str, Any]]:
    """Ask the model to read the team/about pages and name the humans."""
    if not pages:
        return []
    blob = ""
    for url, html_text in list(pages.items())[:4]:
        blob += f"\n--- {url} ---\n{strip_html(html_text)[:5000]}\n"
    if len(blob.strip()) < 200:
        return []

    prompt = (
        f"Company: {company.get('name')}\n"
        f"Website: {company.get('website')}\n"
        f"What they do: {company.get('description', '')[:400]}\n\n"
        f"Below are pages from their website. List the real named people you can find — "
        f"prioritise founders, then anyone in recruiting or hiring, then engineering leads. "
        f"Only include a person if their name actually appears on the page. Set email to an "
        f"empty string unless the page states it. Do not guess an address.\n{blob[:16000]}"
    )
    try:
        data = llm.complete_json(prompt, PEOPLE_SCHEMA, default={"people": []},
                                 purpose="extract", cacheable=True,
                                 system="You extract structured facts from web pages. "
                                        "You never invent names or email addresses.")
    except llm.LLMError as exc:
        log(f"[people] LLM extraction unavailable: {exc}")
        return []

    out: list[dict[str, Any]] = []
    for p in (data or {}).get("people", [])[:8]:
        name = (p.get("full_name") or "").strip()
        if not name or len(name) < 3 or len(name.split()) > 5:
            continue
        email = _clean_email(p.get("email") or "")
        out.append({
            "full_name": name,
            "title": (p.get("title") or "").strip()[:120],
            "role": (p.get("role") or "unknown").strip().lower(),
            "email": email if email and _plausible(email, company.get("domain", "")) else "",
        })
    if out:
        log(f"[people] model named {len(out)} person(s) at {company.get('name')}")
    return out


def email_patterns(full_name: str, domain: str) -> list[str]:
    """Common corporate address shapes, most likely first."""
    if not full_name or not domain:
        return []
    parts = [re.sub(r"[^a-z]", "", p.lower()) for p in full_name.split()]
    parts = [p for p in parts if p]
    if not parts:
        return []
    first = parts[0]
    last = parts[-1] if len(parts) > 1 else ""
    fi, li = first[:1], last[:1] if last else ""

    shapes = [first]
    if last:
        shapes += [f"{first}.{last}", f"{fi}{last}", f"{first}{last}", f"{first}_{last}",
                   f"{first}-{last}", f"{last}", f"{fi}.{last}", f"{first}{li}"]
    return [f"{s}@{domain}" for s in dict.fromkeys(shapes) if s]


# --------------------------------------------------------------------------
# Verification
# --------------------------------------------------------------------------

_PORT25_BLOCKED: bool | None = None


def mx_hosts(domain: str) -> list[str]:
    if not HAVE_DNS or not domain:
        return []
    try:
        answers = dns.resolver.resolve(domain, "MX", lifetime=8)
        ranked = sorted(answers, key=lambda r: r.preference)
        return [str(r.exchange).rstrip(".") for r in ranked][:3]
    except Exception:
        return []


def _smtp_probe(mx: str, address: str, sender: str, timeout: int = 12) -> tuple[int, str]:
    """Return (code, message) for RCPT TO. Code 0 means the probe could not run."""
    try:
        server = smtplib.SMTP(timeout=timeout)
        server.connect(mx, 25)
        server.ehlo_or_helo_if_needed()
        server.mail(sender)
        code, msg = server.rcpt(address)
        try:
            server.quit()
        except Exception:
            pass
        return code, msg.decode("utf-8", "replace") if isinstance(msg, bytes) else str(msg)
    except (socket.timeout, TimeoutError, ConnectionRefusedError, OSError) as exc:
        return 0, f"{type(exc).__name__}: {exc}"
    except smtplib.SMTPException as exc:
        return 0, f"SMTPException: {exc}"


def verify_email(email: str, *, sender: str = "verify@example.com",
                 log: Callable[[str], None] = lambda _: None) -> dict[str, Any]:
    """
    Returns {status, score, detail}.

      valid    mailbox accepted by the mail server
      risky    domain is catch-all, or a generic role inbox — deliverable but unproven
      invalid  server rejected the mailbox, or the domain has no MX
      unknown  probe could not run (port 25 blocked, greylisted, timeout)
    """
    global _PORT25_BLOCKED

    email = (email or "").strip().lower()
    if not EMAIL_RE.fullmatch(email):
        return {"status": "invalid", "score": 0.0, "detail": "Malformed address."}

    domain = email.split("@")[1]
    hosts = mx_hosts(domain)
    if not hosts:
        if not HAVE_DNS:
            return {"status": "unknown", "score": 0.3, "detail": "dnspython not installed; no MX check."}
        return {"status": "invalid", "score": 0.0, "detail": f"No MX record for {domain}."}

    is_role = email.split("@")[0] in (ROLE_PREFIXES | HIRING_PREFIXES | FOUNDER_PREFIXES)

    if _PORT25_BLOCKED:
        return {"status": "risky" if is_role else "unknown",
                "score": 0.5 if is_role else 0.4,
                "detail": f"MX present ({hosts[0]}); SMTP probe unavailable (port 25 blocked here)."}

    mx = hosts[0]
    code, msg = _smtp_probe(mx, email, sender)

    if code == 0:
        if _PORT25_BLOCKED is None:
            _PORT25_BLOCKED = True
            log("[verify] outbound port 25 appears blocked — falling back to MX-only scoring "
                "for the rest of this run.")
        return {"status": "risky" if is_role else "unknown",
                "score": 0.5 if is_role else 0.4,
                "detail": f"MX present ({mx}); SMTP probe failed: {msg[:90]}"}

    _PORT25_BLOCKED = False

    if code in (550, 551, 553, 554, 501):
        return {"status": "invalid", "score": 0.0, "detail": f"{mx} rejected the mailbox ({code})."}
    if code in (450, 451, 452, 421):
        return {"status": "unknown", "score": 0.4,
                "detail": f"{mx} greylisted the probe ({code}); retry later."}
    if code not in (250, 251):
        return {"status": "unknown", "score": 0.4, "detail": f"{mx} replied {code}: {msg[:80]}"}

    # Accepted — but does it accept anything?
    control = "".join(random.choices(string.ascii_lowercase, k=14)) + f"@{domain}"
    c_code, _ = _smtp_probe(mx, control, sender)
    if c_code in (250, 251):
        return {"status": "risky", "score": 0.55,
                "detail": f"{domain} is catch-all — accepts any address, so delivery is likely "
                          f"but the mailbox is unproven."}
    if is_role:
        return {"status": "valid", "score": 0.8,
                "detail": f"{mx} accepted this shared inbox; catch-all ruled out."}
    return {"status": "valid", "score": 0.95,
            "detail": f"{mx} accepted the mailbox and rejected a random control address."}


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

def discover_people(company: dict[str, Any], *, hn_emails: Iterable[str] = (),
                    use_llm: bool = True, max_patterns: int = 3,
                    sender: str = "verify@example.com",
                    log: Callable[[str], None] = print) -> list[dict[str, Any]]:
    """Everything above, in priority order, for one company."""
    name = company.get("name") or "?"
    domain = company.get("domain") or domain_of(company.get("website"))
    candidates: dict[str, dict[str, Any]] = {}

    def add(email: str, *, source: str, full_name: str = "", title: str = "",
            role: str = "", score_hint: float = 0.0) -> None:
        email = _clean_email(email)
        if not email or not _plausible(email, domain):
            return
        existing = candidates.get(email)
        if existing:
            existing["full_name"] = existing.get("full_name") or full_name
            existing["title"] = existing.get("title") or title
            return
        candidates[email] = {
            "email": email,
            "email_source": source,
            "full_name": full_name,
            "title": title,
            "role": role or classify_role(email, f"{full_name} {title}"),
            "_hint": score_hint,
        }

    # 1. Emails the founder published on HN
    for email in hn_emails:
        add(email, source="hn", role=classify_role(email, "founder"), score_hint=0.25)
    if candidates:
        log(f"[people] {name}: {len(candidates)} address(es) straight from the HN post")

    # 2. The company's own site
    pages = sources.crawl_company_pages(company.get("website") or "", log=log)
    for hit in emails_from_pages(pages, domain):
        add(hit["email"], source="site", title=hit.get("context", "")[:100])

    # 3. Named humans, then generated patterns for them
    named: list[dict[str, Any]] = []
    if use_llm and pages:
        named = people_from_llm(company, pages, log=log)
        for person in named:
            if person["email"]:
                add(person["email"], source="site", full_name=person["full_name"],
                    title=person["title"], role=person["role"], score_hint=0.1)

    if domain:
        pattern_budget = max_patterns
        for person in named:
            if pattern_budget <= 0:
                break
            if person["email"] or person["role"] not in ("founder", "recruiter"):
                continue
            for guess in email_patterns(person["full_name"], domain)[:2]:
                if guess in candidates or pattern_budget <= 0:
                    continue
                add(guess, source="pattern", full_name=person["full_name"],
                    title=person["title"], role=person["role"], score_hint=-0.15)
                pattern_budget -= 1

    if not candidates:
        log(f"[people] {name}: nothing found")
        return []

    # 4. Verify, best-provenance first
    order = {"hn": 0, "site": 1, "pattern": 2}
    ranked = sorted(candidates.values(), key=lambda c: (order.get(c["email_source"], 3), c["email"]))

    results: list[dict[str, Any]] = []
    for cand in ranked[:8]:
        check = verify_email(cand["email"], sender=sender, log=log)
        score = max(0.0, min(1.0, check["score"] + cand.pop("_hint", 0.0)))
        if cand["email_source"] == "pattern" and check["status"] != "valid":
            log(f"[people]   drop {cand['email']} (guessed, {check['status']})")
            continue
        results.append({
            **cand,
            "company_id": company.get("id"),
            "email_status": check["status"],
            "email_score": round(score, 2),
            "verify_detail": check["detail"],
        })
        log(f"[people]   {cand['email']:<36} {check['status']:<8} {score:.2f}  ({cand['email_source']})")

    return results
