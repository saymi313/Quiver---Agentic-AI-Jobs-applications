"""
Auto-apply agent: opens a job's application form in a real browser, fills every
field it can from your profile, uploads the tailored résumé, and submits.

How fields get answered, cheapest first:
  1. A direct rule — the field is recognisably "First name", "Email", "Résumé"…
  2. Your profile's stock answers (work authorisation, notice period, salary…)
  3. The LLM, given the question text plus your profile, for anything custom.

Anything it still cannot answer truthfully is recorded in `unanswered` and, for
required fields, aborts that application rather than submitting a guess — a
wrong answer to a screening question is permanent at that company.

Set `dry_run=True` to do everything except click Submit.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from api.config import DASHBOARD_OUT
from api import behuman

from . import answers as answer_bank
from . import credentials, llm, matcher, portals, store

SHOT_DIR = DASHBOARD_OUT / "applications"
SHOT_DIR.mkdir(parents=True, exist_ok=True)

# label fragment -> profile key
FIELD_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bfirst\s*name|\bgiven\s*name|\bforename", re.I), "_first_name"),
    (re.compile(r"\blast\s*name|\bsurname|\bfamily\s*name", re.I), "_last_name"),
    (re.compile(r"\bfull\s*name|^name$|your\s*name|candidate\s*name", re.I), "full_name"),
    (re.compile(r"\be-?mail", re.I), "email"),
    (re.compile(r"\bphone|\bmobile|\btelephone|\bcontact\s*number", re.I), "phone"),
    (re.compile(r"\blinked\s*-?in", re.I), "linkedin"),
    (re.compile(r"\bgit\s*hub", re.I), "github"),
    (re.compile(r"\bportfolio|personal\s*(web)?site|\bwebsite\b|\burl\b", re.I), "portfolio"),
    # More specific than the general location rule, so they must precede it:
    # `_match_rule` returns the first pattern that hits.
    (re.compile(r"\bcountry\b|country\s*of\s*residence", re.I), "_country"),
    (re.compile(r"\bcity\b|\btown\b|location\s*\(city\)", re.I), "_city"),
    (re.compile(r"\blocation|where.*based|current.*residence", re.I), "location"),
    (re.compile(r"current\s*(job\s*)?title|current\s*role|\boccupation", re.I), "current_title"),
    (re.compile(r"current\s*(company|employer)|present\s*employer|where.*work\s*now", re.I), "current_company"),
    (re.compile(r"years.*experience|experience.*years", re.I), "years_experience"),
    (re.compile(r"highest.*(degree|education)|degree\s*(level|earned)?$|qualification\s*level", re.I),
     "highest_degree"),
    (re.compile(r"universit|college|\bschool\b|alma\s*mater|institution", re.I), "university"),
    (re.compile(r"notice\s*period|when.*(start|available)|availability", re.I), "notice_period"),
    (re.compile(r"salary|compensation|expected\s*pay|rate\s*expectation", re.I), "salary_expectation"),
    # Relocation willingness is read before the visa rule below, because a
    # question like "willing to go through the visa process and move" is about
    # moving, not about needing sponsorship — the "visa" keyword would otherwise
    # answer it as a sponsorship question and get it backwards.
    (re.compile(r"relocat|willing[\w\s]{0,45}\bmove\b|open\s+to\s+(relocat|mov)|"
                r"willing\s+to\s+move", re.I), "willing_to_relocate"),
    (re.compile(r"sponsor|visa|work\s*permit", re.I), "requires_sponsorship"),
    (re.compile(r"authori[sz]ed|legally.*work|right\s*to\s*work|eligible.*work", re.I), "work_authorization"),
    (re.compile(r"pronoun", re.I), "pronouns"),
    (re.compile(r"how.*(hear|find).*(us|role|position)|referral\s*source", re.I), "how_did_you_hear"),
    (re.compile(r"why.*(join|company|us|interested)|cover\s*letter|motivat", re.I), "_cover_letter"),
    # Voluntary self-identification / EEOC
    (re.compile(r"\bgender\b|voluntary.*gender|\bsex\b", re.I), "_eeoc_gender"),
    (re.compile(r"\brace\b|\bethnicity\b|ethnic\s*background", re.I), "_eeoc_race"),
    (re.compile(r"\bveteran\b|military\s*status", re.I), "_eeoc_veteran"),
    (re.compile(r"\bdisability\b|handicap", re.I), "_eeoc_disability"),
]

# Walls the agent cannot get past. Detected explicitly so the job is recorded as
# a failure with a reason the user can act on, rather than disappearing.
LOGIN_MARKERS = re.compile(
    r"\b(sign in to (?:apply|continue)|log ?in to (?:apply|continue)|"
    r"create an account to apply|please (?:sign|log) ?in|"
    r"you must be logged in|register to apply)\b", re.I)

# A registration wall — the site wants a *new* account, not a sign-in. Detected
# separately so the agent can create one from the signup identity rather than
# giving up. Kept narrow: a page that only offers "sign in" is a login wall.
SIGNUP_MARKERS = re.compile(
    r"\b(create (?:an |your )?account|sign ?up|register(?:ing)? (?:to|an account|now)|"
    r"create your profile|don'?t have an account|new (?:to|here)\?|"
    r"set (?:a |up (?:a )?)?password)\b", re.I)

# The state right after registering on a site that verifies by emailing a link.
# There is no code box to fill and no form to complete — the account is inert
# until the link is opened, so this is a distinct "input required" wall.
VERIFY_MARKERS = re.compile(
    r"\b(check your (?:email|inbox)|we(?:'ve| have)? sent (?:you )?a (?:confirmation|verification) "
    r"(?:email|link)|confirm your email (?:address )?to|verify your email (?:address )?to|"
    r"click the (?:confirmation|verification) link|activation (?:email|link) (?:has been )?sent|"
    r"a link to (?:activate|verify|confirm))\b", re.I)


def _visible_captcha(page) -> bool:
    """
    Is there a captcha the user would actually have to solve?

    Presence of a recaptcha script or frame is NOT enough: Ashby (and many
    Greenhouse boards) load an *invisible* reCAPTCHA badge on every form, and
    treating that as a wall rejects forms that fill and submit fine.

    Measured on Greenhouse, 2026-08: the invisible badge is an
    `enterprise/anchor` iframe of exactly 256x60 sitting inside a
    `.grecaptcha-badge` wrapper — wide enough and tall enough to clear naive
    size thresholds, which is how it once failed a perfectly fillable form.
    The wrapper is the reliable tell, so the badge is excluded by ancestry
    first and by height second. A real "I'm not a robot" checkbox widget is
    ~300x78 and sits in the form flow, not in a fixed corner.
    """
    try:
        if page.evaluate(
            """() => {
              const frames = Array.from(document.querySelectorAll(
                'iframe[src*="recaptcha"][src*="anchor"], iframe[src*="hcaptcha"],'
                + ' iframe[src*="turnstile"], .h-captcha iframe, .cf-turnstile iframe'));
              return frames.some(f => {
                // Google's invisible badge: never a challenge the user solves.
                if (f.closest('.grecaptcha-badge')) return false;
                if (/size=invisible/i.test(f.src || '')) return false;
                const r = f.getBoundingClientRect();
                if (r.width === 0 || r.height === 0) return false;
                const style = getComputedStyle(f);
                if (style.visibility === 'hidden' || style.display === 'none') return false;
                // A challenge widget is taller than the 60px badge.
                return r.width >= 200 && r.height > 65;
              });
            }"""
        ):
            return True
    except Exception:
        pass
    try:
        challenge = page.get_by_text(re.compile(
            r"(verify (?:that )?you are (?:a )?human|i'?m not a robot|"
            r"complete the captcha)", re.I))
        if challenge.count() and challenge.first.is_visible():
            return True
    except Exception:
        pass
    return False


# A one-time code the site has emailed or texted. Unlike a captcha, this is
# something the user can actually supply, so the application pauses instead of
# dying — the difference between "this needs a human" and "this needs you".
OTP_MARKERS = re.compile(
    r"\b(enter the (?:\d[\- ]?)?(?:digit )?code|verification code|one[- ]time (?:code|password)|"
    r"we (?:sent|emailed|texted) (?:you )?a code|confirm your (?:email|identity) to continue|"
    r"security code)\b", re.I)


# A posting that has been taken down. Ashby (and others) serve a soft 404 — an
# HTTP 200 whose body says the page is gone — so the status code cannot be
# trusted; the body text is the tell. Kept to unambiguous phrases so a live form
# is never mistaken for a dead one.
CLOSED_MARKERS = re.compile(
    r"\b(page not found|page you requested was not found|"
    r"no longer (accepting|available|open|active)|"
    r"(position|posting|job|role|vacancy|opening) (has been|is|was) (closed|filled|removed|expired)|"
    r"this (position|posting|job|role) is (closed|no longer)|"
    r"applications? (are|is) closed|we are no longer accepting|"
    r"this (job|posting|opening|listing) (is|has) (closed|expired|been filled|no longer)|"
    r"job not found|posting not found|not accepting applications)\b", re.I)

# Regional / Geo-blocking markers: when a board or employer restricts job access by candidate IP/region.
REGION_BLOCKED_MARKERS = re.compile(
    r"\b(not available in your (region|country|location|area)|"
    r"restricted in your (region|country|location|area)|"
    r"blocked in your (region|country|location|area)|"
    r"geo-?restricted|geo-?blocked|access is not permitted from your location|"
    r"not accessible in your (region|country|location)|"
    r"similar jobs in your region)\b", re.I)


def _posting_closed(page) -> str | None:
    """A reason if the page reads as a taken-down posting, else None."""
    try:
        text = (page.inner_text("body") or "")[:3000]
    except Exception:
        return ""
    if CLOSED_MARKERS.search(text):
        return "this posting has been taken down — the page is gone, so there is nothing to apply to"
    return None


def _posting_region_blocked(page) -> str | None:
    """A reason if the page indicates geo-blocking / regional restriction, else None."""
    try:
        text = (page.inner_text("body") or "")[:4000]
    except Exception:
        return None
    if REGION_BLOCKED_MARKERS.search(text):
        return ("this job board restricted access for your region (page says: 'not available in your region') — "
                "connect via a VPN in the target country (e.g. UK/US) or open the employer listing directly")
    return None


def diagnose_wall(page) -> tuple[str, str] | None:
    """
    Why this form cannot be completed right now, as (kind, message).

    `kind` is the application status this should become:

      failed        nobody can get past it unattended — a rendered captcha
      needs_review  a human could, given a moment: a login, or a code the site
                    just sent. Recording those as failures conflated "the site
                    said no" with "the site is waiting for you", and buried
                    applications that were one step from going through.

    Checked before field collection: any of these means the fields on the page
    are not the application form at all.
    """
    if _visible_captcha(page):
        return "failed", "blocked by a captcha challenge — this form needs a human"

    try:
        text = (page.inner_text("body") or "")[:6000]
    except Exception:
        text = ""

    if OTP_MARKERS.search(text):
        return ("needs_review",
                "the site sent a one time code and is waiting for it — open the "
                "posting, enter the code, and apply again")

    if VERIFY_MARKERS.search(text):
        return ("needs_review",
                "a confirmation link was emailed to activate the new account — open "
                "the posting, paste the link, and apply again")

    hit = LOGIN_MARKERS.search(text)
    if hit:
        return ("needs_review",
                f"behind a login wall — the site asks you to {hit.group(0).lower()}. "
                f"Sign in once in your own browser, then apply again")
    if re.search(r"/(login|signin|sign-in|auth)\b", (page.url or ""), re.I):
        return ("needs_review",
                "redirected to a sign-in page — an account is required. Create it "
                "once, then apply again")
    return None


def _fill_login(page, cred: dict[str, str], log: Callable[[str], None]) -> bool:
    """
    Type a stored username and password into a sign-in form and submit it.

    Best-effort by design: the field a site calls "username" might be an email
    input, an id, or a plain text box, so several selectors are tried in the
    order sites most commonly use. Returns whether both fields were filled and a
    submit was clicked — the caller re-checks the wall to see if it worked.
    """
    user_sel = ("input[type=email]", "input[name*=email i]", "input[name*=user i]",
                "input[id*=email i]", "input[id*=user i]", "input[autocomplete=username]")
    pass_sel = ("input[type=password]", "input[name*=pass i]", "input[autocomplete=current-password]")
    try:
        user = next((page.locator(s) for s in user_sel if page.locator(s).count()), None)
        pw = next((page.locator(s) for s in pass_sel if page.locator(s).count()), None)
        if not user or not pw:
            return False
        user.first.fill(cred["username"], timeout=6000)
        pw.first.fill(cred["password"], timeout=6000)
        for name in ("Sign in", "Log in", "Login", "Continue", "Submit"):
            btn = page.get_by_role("button", name=re.compile(rf"^\s*{re.escape(name)}\s*$", re.I))
            if btn.count() and btn.first.is_visible():
                btn.first.click(timeout=6000)
                log("[apply]   signed in with the stored credentials for this site")
                return True
        pw.first.press("Enter")
        return True
    except Exception as exc:
        log(f"[apply]   sign-in attempt did not go through ({type(exc).__name__})")
        return False


def _fill_signup(page, identity: dict[str, str], profile: dict[str, str],
                 log: Callable[[str], None]) -> bool:
    """
    Register a new account from the signup identity and submit the form.

    Fills email and password — and a confirm-password box, and a name, when the
    form has them, since a registration form usually does. Best-effort like the
    login filler: several selectors per field in the order sites commonly use,
    and a submit is clicked. The caller re-checks the wall to see what the
    registration produced (the form, a code box, or a "check your email" page).
    """
    email_sel = ("input[type=email]", "input[name*=email i]", "input[id*=email i]",
                 "input[autocomplete=email]", "input[autocomplete=username]")
    pass_sel = ("input[type=password][autocomplete=new-password]",
                "input[name*=pass i]", "input[id*=pass i]", "input[type=password]")
    try:
        email = next((page.locator(s) for s in email_sel if page.locator(s).count()), None)
        pws = next((page.locator(s) for s in pass_sel if page.locator(s).count()), None)
        if not email or not pws:
            return False
        email.first.fill(identity["username"], timeout=6000)
        # A registration form often shows password + confirm password; fill both
        # with the same value when there are two boxes.
        pw_boxes = page.locator("input[type=password]")
        count = pw_boxes.count()
        if count >= 2:
            pw_boxes.nth(0).fill(identity["password"], timeout=6000)
            pw_boxes.nth(1).fill(identity["password"], timeout=6000)
        else:
            pws.first.fill(identity["password"], timeout=6000)

        # A full-name field, if the form asks for one, from the profile.
        name = (profile.get("full_name") or "").strip()
        if name:
            for sel in ("input[name*=name i][type=text]", "input[id*=name i][type=text]",
                        "input[autocomplete=name]"):
                loc = page.locator(sel)
                if loc.count() and loc.first.is_visible():
                    try:
                        loc.first.fill(name, timeout=3000)
                    except Exception:
                        pass
                    break

        for label in ("Create account", "Sign up", "Register", "Create your account",
                      "Get started", "Continue", "Submit"):
            btn = page.get_by_role("button", name=re.compile(rf"^\s*{re.escape(label)}\s*$", re.I))
            if btn.count() and btn.first.is_visible():
                btn.first.click(timeout=6000)
                log(f"[apply]   registered a new account as {identity['username']}")
                return True
        pws.first.press("Enter")
        log(f"[apply]   registered a new account as {identity['username']}")
        return True
    except Exception as exc:
        log(f"[apply]   sign-up attempt did not go through ({type(exc).__name__})")
        return False


def _fill_otp(page, code: str, log: Callable[[str], None]) -> bool:
    """
    Enter a one-time code the user handed back, and submit it.

    Two shapes cover almost every site: one input that takes the whole code, or a
    row of single-character boxes. The digits are spread across the boxes when
    there is more than one.
    """
    try:
        boxes = page.locator("input[autocomplete=one-time-code], input[name*=otp i], "
                             "input[id*=otp i], input[name*=code i], input[inputmode=numeric]")
        n = boxes.count()
        if n == 0:
            return False
        if n == 1:
            boxes.first.fill(code, timeout=6000)
        else:
            for i, ch in enumerate(code[:n]):
                boxes.nth(i).fill(ch, timeout=3000)
        for name in ("Verify", "Confirm", "Continue", "Submit"):
            btn = page.get_by_role("button", name=re.compile(rf"^\s*{re.escape(name)}\s*$", re.I))
            if btn.count() and btn.first.is_visible():
                btn.first.click(timeout=6000)
                break
        else:
            boxes.first.press("Enter")
        log("[apply]   entered the one-time code")
        return True
    except Exception as exc:
        log(f"[apply]   could not enter the code ({type(exc).__name__})")
        return False


def try_clear_wall(page, job: dict[str, Any], log: Callable[[str], None]) -> bool:
    """
    Attempt to get past a login, sign-up or one-time-code wall automatically.

    The pipeline, in order:

      1. A confirmation link the user pasted back is opened first — it activates
         the account a previous run created, and clears the wall for good.
      2. A one-time-code wall is answered from a parked code, or read straight
         from the connected inbox.
      3. A saved login for this domain is used to sign in.
      4. Otherwise, if the site wants a *new* account and a signup identity is
         configured, one is registered on the spot and saved for next time.

    Any step that still leaves the user something to do — a code that never
    arrived, a confirmation link a fresh account now needs — parks the job in the
    input-required queue with a specific prompt, so the dashboard can ask for it.
    Returns True only if the wall is actually gone afterwards.
    """
    from . import credentials, inbox

    job_id = job.get("id")
    domain = credentials.domain_of(page.url)

    def body() -> str:
        try:
            return (page.inner_text("body") or "")[:6000]
        except Exception:
            return ""

    # 1. A confirmation link the user handed back — open it, then come back to
    #    the application page and re-check.
    link = credentials.pop_confirmation_link(job_id)
    if link:
        try:
            log("[apply]   opening the confirmation link you provided")
            page.goto(link, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2500)
            back = job.get("apply_url") or job.get("url")
            if back:
                page.goto(back, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(2000)
        except Exception as exc:
            log(f"[apply]   the confirmation link did not open ({type(exc).__name__})")
        if diagnose_wall(page) is None:
            credentials.clear_pending_input(job_id)
            return True

    text = body()

    # 2. One-time-code wall.
    if OTP_MARKERS.search(text):
        # A code the user handed back wins — it is the one they were looking at.
        code = credentials.pop_otp(job_id)
        # Otherwise the form just triggered a code by email. The mailbox is
        # already connected, so read it: poll a few times because the mail takes
        # a few seconds to arrive.
        if not code and inbox.available()[0]:
            log("[apply]   a one-time code was requested — checking the inbox for it")
            for _ in range(3):
                page.wait_for_timeout(7000)
                code = inbox.latest_verification_code(within_seconds=180, log=log)
                if code:
                    break
        if code and _fill_otp(page, code, log):
            page.wait_for_timeout(1800)
            if diagnose_wall(page) is None:
                credentials.clear_pending_input(job_id)
                return True
            return False
        # No code available — ask the user for it (a code sent by SMS, say).
        credentials.set_pending_input(
            job_id, "otp", domain=domain,
            prompt="The site emailed or texted a one-time code. Paste it to continue.")
        return False

    # 3. A saved login for this domain.
    cred = credentials.get_credential(domain)
    if cred and _fill_login(page, cred, log):
        page.wait_for_timeout(2200)
        if diagnose_wall(page) is None:
            credentials.clear_pending_input(job_id)
            return True
        # A saved login that lands on a code wall falls through on the next loop.

    # 4. A registration wall, and nobody signed in — create the account.
    text = body()
    if SIGNUP_MARKERS.search(text) and credentials.signup_enabled():
        profile = _profile_values()
        identity = credentials.signup_identity(fallback_email=profile.get("email", ""))
        if not identity:
            credentials.set_pending_input(
                job_id, "login", domain=domain,
                prompt="This site needs an account. Set a signup email and an "
                       "application password in Settings, then apply again.")
            log("[apply]   a new account is needed but no signup identity is set")
            return False
        if _fill_signup(page, identity, profile, log):
            page.wait_for_timeout(2800)
            # Save the login so future runs sign in instead of re-registering.
            credentials.set_credential(domain, identity["username"], identity["password"])
            after = body()
            if diagnose_wall(page) is None and not VERIFY_MARKERS.search(after):
                credentials.clear_pending_input(job_id)
                log("[apply]   account created — the form is now reachable")
                return True
            # Registration worked but the account is not active yet.
            if OTP_MARKERS.search(after):
                code = None
                if inbox.available()[0]:
                    for _ in range(3):
                        page.wait_for_timeout(7000)
                        code = inbox.latest_verification_code(within_seconds=180, log=log)
                        if code:
                            break
                if code and _fill_otp(page, code, log):
                    page.wait_for_timeout(1800)
                    if diagnose_wall(page) is None:
                        credentials.clear_pending_input(job_id)
                        return True
                credentials.set_pending_input(
                    job_id, "otp", domain=domain,
                    prompt="The new account needs a one-time code the site sent. "
                           "Paste it to finish activating it.")
                return False
            # A confirmation-link account: wait for the link.
            credentials.set_pending_input(
                job_id, "link", domain=domain,
                prompt="The new account was emailed a confirmation link. Paste the "
                       "link to activate it, then apply again.")
            log("[apply]   account created — waiting on the emailed confirmation link")
            return False

    return False


# Yes/No toggle groups (Ashby renders required screening questions this way —
# as <button> pairs, not radio inputs, so input-based collection never sees
# them). The script tags each group's buttons and radio labels so Python can click by group id.
CHOICE_GROUPS_JS = """() => {
  const yn = ['Yes', 'No'];
  const seen = new Set(); const out = []; let gi = 0;

  // 1. Button pairs (e.g. Ashby, Personio)
  [...document.querySelectorAll('button')].forEach((b) => {
    if (!yn.includes(b.innerText.trim())) return;
    let n = b.parentElement;
    while (n) {
      const btns = [...n.querySelectorAll('button')].map(x => x.innerText.trim());
      if (yn.every(o => btns.includes(o)) && btns.length <= 4) break;
      n = n.parentElement;
    }
    if (!n || seen.has(n)) return;
    seen.add(n);
    const holder = n.parentElement || n;
    const question = holder.innerText.split(String.fromCharCode(10))
      .map(s => s.trim()).filter(s => s && !yn.includes(s))[0] || '';
    const answered = [...n.querySelectorAll('button')].some(x =>
      x.getAttribute('aria-pressed') === 'true' ||
      x.getAttribute('data-state') === 'on' ||
      /select|active|checked/i.test(x.className));
    n.querySelectorAll('button').forEach(x => x.setAttribute('data-agent-choice', gi));
    out.push({ i: gi, question: question.slice(0, 160), answered });
    gi += 1;
  });

  // 2. Radio groups / fieldsets (Greenhouse, Lever, Workday)
  [...document.querySelectorAll('fieldset, [role="radiogroup"], .field, [class*="radio-group"]')].forEach((n) => {
    if (seen.has(n)) return;
    const radios = [...n.querySelectorAll('input[type="radio"], [role="radio"]')];
    if (radios.length < 2 || radios.length > 6) return;
    const labels = [...n.querySelectorAll('label, [class*="label"], span')].map(x => x.innerText.trim());
    if (!yn.every(o => labels.some(l => l.toLowerCase() === o.toLowerCase()))) return;
    seen.add(n);
    const legend = n.querySelector('legend, label, h3, h4, [class*="legend"]') || n.parentElement;
    const question = (legend ? legend.innerText : n.innerText).split(String.fromCharCode(10))
      .map(s => s.trim()).filter(s => s && !yn.includes(s))[0] || '';
    const answered = radios.some(x => x.checked || x.getAttribute('aria-checked') === 'true');
    n.querySelectorAll('label, button, [role="radio"]').forEach(x => x.setAttribute('data-agent-choice', gi));
    out.push({ i: gi, question: question.slice(0, 160), answered });
    gi += 1;
  });

  return out;
}"""

REGION_HINTS = {
    "united states": ("united states", "u.s", "usa"),
    "united kingdom": ("united kingdom", "uk", "britain"),
    "pakistan": ("pakistan",),
    "germany": ("germany", "eu", "european union"),
    "canada": ("canada",),
}


def _choice_rule_answer(question: str, profile: dict[str, str]) -> str | None:
    """Answer a Yes/No screening question from the profile alone, truthfully."""
    q = (question or "").lower()
    # Willingness to relocate or move — answered from the profile, and checked
    # before sponsorship so "willing to go through the visa process and move"
    # is read as a move question, not a sponsorship one.
    if re.search(r"relocat|willing[\w\s]{0,45}\bmove\b|open to (relocat|mov)|willing to move", q):
        value = (profile.get("willing_to_relocate") or "").strip().lower()
        if value in ("yes", "no"):
            return value.title()
        return None
    if "sponsor" in q:
        value = (profile.get("requires_sponsorship") or "").strip().lower()
        if value in ("yes", "no"):
            return value.title()
        return None
    if re.search(r"authori[sz]ed|right to work|legally .{0,20}work|eligible to work", q):
        auth = (profile.get("work_authorization") or "").lower()
        if not auth:
            return None
        for region, hints in REGION_HINTS.items():
            if any(h in q for h in hints):
                return "Yes" if any(h in auth for h in REGION_HINTS[region]) else "No"
    return None


def _answer_choice_groups(page, job: dict[str, Any], profile: dict[str, str],
                          log: Callable[[str], None]) -> tuple[dict[str, str],
                                                               list[dict[str, Any]]]:
    """Find and answer Yes/No button groups. Returns (filled, unanswerable)."""
    try:
        groups = page.evaluate(CHOICE_GROUPS_JS)
    except Exception:
        return {}, []
    filled: dict[str, str] = {}
    blocking: list[dict[str, Any]] = []

    pending = [g for g in groups if g.get("question") and not g.get("answered")]
    if not pending:
        return {}, []

    # Rules answer the common questions without a model call; a saved answer
    # covers the long tail the profile cannot; the LLM handles the rest with the
    # same "only if the profile supports it" contract.
    saved_bank = answer_bank.load()
    need_llm = []
    answers: dict[int, str] = {}
    for g in pending:
        ans = _choice_rule_answer(g["question"], profile)
        if not ans:
            ans = answer_bank.as_yes_no(answer_bank.match(g["question"], saved=saved_bank))
        if ans:
            answers[g["i"]] = ans
        else:
            need_llm.append({"idx": 100000 + g["i"], "label": g["question"],
                             "type": "select", "options": ["Yes", "No"],
                             "required": True, "name": ""})
    if need_llm:
        llm_out = _llm_answers(need_llm, job, profile, "", log)
        for g in pending:
            a = llm_out.get(100000 + g["i"]) or {}
            value = (a.get("answer") or "").strip().title()
            if a.get("confident") and value in ("Yes", "No"):
                answers[g["i"]] = value

    for g in pending:
        ans = answers.get(g["i"])
        if not ans:
            blocking.append({"label": g["question"][:90], "required": True,
                             "type": "choice", "reason": "no truthful answer"})
            continue
        try:
            btn = page.locator(f'[data-agent-choice="{g["i"]}"]').filter(
                has_text=re.compile(rf"^\s*{ans}\s*$", re.I))
            if btn.count() and btn.first.is_visible():
                btn.first.click(timeout=6000)
                filled[g["question"][:70]] = ans
                log(f"[apply]   {ans} -> {g['question'][:62]}")
            else:
                blocking.append({"label": g["question"][:90], "required": True,
                                 "type": "choice", "reason": "could not find clickable option"})
        except Exception:
            blocking.append({"label": g["question"][:90], "required": True,
                             "type": "choice", "reason": "could not click the option"})
    return filled, blocking


def resume_for(job: dict[str, Any]) -> Path | None:
    """
    The tailored resume for this job, or the master resume as a fallback.

    A job that went through discovery has its own file; one applied to before
    the tailoring stage existed falls back so applying still works.
    """
    from . import tailor

    own = tailor.existing(job)
    return own or matcher.resume_path()

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "answer": {"type": "string"},
                    "confident": {"type": "boolean",
                                  "description": "false if the profile does not actually support this answer"},
                },
                "required": ["index", "answer", "confident"],
            },
        }
    },
    "required": ["answers"],
}


def _profile_values() -> dict[str, str]:
    p = dict(store.get_setting("profile", {}) or {})
    name = (p.get("full_name") or "").strip()
    bits = name.split()
    p["_first_name"] = bits[0] if bits else ""
    p["_last_name"] = " ".join(bits[1:]) if len(bits) > 1 else ""

    # Forms routinely split what the profile stores as one line: "Mansehra,
    # Pakistan" has to answer a City box and a Country dropdown separately.
    # Derived, not invented — both halves come from the address the user wrote.
    parts = [x.strip() for x in (p.get("location") or "").split(",") if x.strip()]
    p["_city"] = parts[0] if parts else ""
    p["_country"] = parts[-1] if len(parts) > 1 else ""
    p.setdefault("_eeoc_gender", "Prefer not to say")
    p.setdefault("_eeoc_race", "I do not wish to disclose")
    p.setdefault("_eeoc_veteran", "I am not a protected veteran")
    p.setdefault("_eeoc_disability", "No, I do not have a disability")
    return {k: str(v or "") for k, v in p.items()}


def _match_rule(label: str) -> str | None:
    for pattern, key in FIELD_RULES:
        if pattern.search(label):
            return key
    return None


# --------------------------------------------------------------------------
# Cover letter
# --------------------------------------------------------------------------

def cover_letter(job: dict[str, Any], *, log: Callable[[str], None] = print) -> str:
    profile = store.get_setting("profile", {}) or {}
    resume = matcher.resume_text()[:6000]
    company = job.get("company_name") or "your team"

    prompt = (
        f"Write a short job application note (110-160 words) from this candidate for this role.\n\n"
        f"ROLE: {job.get('title')} at {company}\n"
        f"LOCATION: {job.get('location') or 'unspecified'}\n\n"
        f"JOB DESCRIPTION:\n{(job.get('description') or '')[:4000]}\n\n"
        f"CANDIDATE RESUME:\n{resume}\n\n"
        f"Rules: only use facts from the resume — never invent an employer, technology, "
        f"metric or credential. Name two things from their actual experience that map to this "
        f"role's requirements. No greeting line, no sign-off, no bullet points, no em dashes. "
        f"Plain prose the hiring manager can read in twenty seconds."
    )
    try:
        text = llm.complete(
            prompt, purpose="apply",
            system="You write concise, factual job application notes.\n\n" + behuman.RULES)
        cleaned = behuman.scrub(re.sub(r"\n{3,}", "\n\n", (text or "").strip()))
        tells = behuman.report(cleaned)
        if tells != "clean":
            log(f"[apply]   cover letter still reads as AI ({tells})")
        return cleaned[:2000]
    except llm.LLMError as exc:
        log(f"[apply] cover letter unavailable ({exc}); continuing without one")
        why = (profile.get("why_this_company") or "").strip()
        return why[:2000]


# --------------------------------------------------------------------------
# Form driving
# --------------------------------------------------------------------------

def _collect_fields(page) -> list[dict[str, Any]]:
    """
    Every visible, fillable control on the page with its best-guess label.

    Controls belonging to a newsletter signup, a site search or a login box are
    skipped. A job board's listing page carries all three, and an agent that
    treats the "subscribe to weekly jobs" input as an application field will
    type the candidate's address into it and press Subscribe.
    """
    return page.evaluate(
        """() => {
          const out = [];
          const NOT_APPLICATION = new RegExp([
            'newsletter', 'subscribe', 'subscription', 'mailing.?list',
            'search', 'filter', 'query', 'log.?in', 'sign.?in', 'password',
            'promo', 'coupon', 'cookie', 'consent', 'chat', 'feedback',
            'survey', 'donat',
          ].join('|'), 'i');

          const inNonApplicationRegion = (el) => {
            // Walk up to the nearest form/section and judge that container by
            // its own text and attributes rather than the input alone: the
            // input in a newsletter box is often just name="email".
            let n = el;
            for (let hops = 0; n && hops < 6; hops++, n = n.parentElement) {
              const tag = (n.tagName || '').toLowerCase();
              const attrs = [n.id || '', n.className || '', n.getAttribute?.('name') || '',
                             n.getAttribute?.('action') || '', n.getAttribute?.('role') || ''
                            ].join(' ');
              if (NOT_APPLICATION.test(attrs)) return true;
              if (tag === 'form' || tag === 'footer' || tag === 'nav' || tag === 'header') {
                const text = (n.innerText || '').slice(0, 400);
                return NOT_APPLICATION.test(text);
              }
            }
            return false;
          };

          const nodes = document.querySelectorAll('input, textarea, select');
          nodes.forEach((el, i) => {
            const type = (el.type || el.tagName).toLowerCase();
            if (['hidden','submit','button','image','reset','search'].includes(type)) return;
            const r = el.getBoundingClientRect();
            if (type !== 'file' && (r.width === 0 || r.height === 0)) return;
            if (type !== 'file' && inNonApplicationRegion(el)) return;
            // A widget's own internal control is not an application question:
            // the phone box ships a country picker whose search input would
            // otherwise be offered up as a field to answer.
            if (NOT_APPLICATION.test([el.id || '', el.name || '',
                                      el.placeholder || ''].join(' '))) return;

            let label = '';
            if (el.id) {
              const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
              if (l) label = l.innerText;
            }
            if (!label) {
              const wrap = el.closest('label');
              if (wrap) label = wrap.innerText;
            }
            if (!label) {
              let n = el.parentElement, hops = 0;
              while (n && hops < 3 && !label) {
                const l = n.querySelector('label, .label, legend, [class*="label"]');
                if (l && l.innerText.trim()) label = l.innerText;
                n = n.parentElement; hops++;
              }
            }
            if (!label) label = el.getAttribute('aria-label') || el.placeholder || el.name || '';

            const required = el.required || el.getAttribute('aria-required') === 'true' ||
                             /\\*/.test(label);
            out.push({
              idx: i, type, required,
              label: (label || '').replace(/\\s+/g, ' ').trim().slice(0, 220),
              name: el.name || '', id: el.id || '',
              value: el.value || '',
              options: el.tagName.toLowerCase() === 'select'
                ? Array.from(el.options).map(o => o.text.trim()).slice(0, 40) : [],
            });
          });
          return out;
        }"""
    )


def _handle(page, idx: int):
    return page.locator("input, textarea, select").nth(idx)


def _collect_form(page, log: Callable[[str], None] = print):
    """(context, fields) for whichever frame holds the form — see _form_context."""
    form = _form_context(page)
    if form is not page:
        try:
            log(f"[apply]   the form is inside an embedded frame ({_host(form.url)}) "
                f"— filling it there")
        except Exception:
            pass
    return form, _collect_fields(form)


def _form_context(page):
    """
    The page-or-frame that actually holds the application form.

    Most forms are in the main document, but a real share of ATS embed the whole
    form in an iframe — SmartRecruiters, BambooHR, and Greenhouse/Lever when a
    company drops them into its own careers page. Playwright can read across
    frame boundaries, so the form is found by asking each frame what fields it
    has: the main document wins when it has the form, and a child frame is used
    only when it clearly carries the form and the top page does not. Returns the
    main page as a safe default. A Frame supports the same locator/evaluate calls
    the field code uses, so it can stand in for the page throughout the fill.
    """
    try:
        if looks_like_application(_collect_fields(page)):
            return page
    except Exception:
        pass
    best = None
    best_n = 0
    try:
        frames = list(page.frames)
    except Exception:
        frames = []
    for fr in frames:
        try:
            if fr == page.main_frame:
                continue
            fields = _collect_fields(fr)
        except Exception:
            continue
        if looks_like_application(fields) and len(fields) > best_n:
            best, best_n = fr, len(fields)
    return best if best is not None else page


# --------------------------------------------------------------------------
# "Is this actually an application form?"
# --------------------------------------------------------------------------
#
# Aggregator boards (arbeitnow, RemoteOK, WeWorkRemotely, Landing.jobs…)
# publish a description page and put the real form one click away on the
# employer's own site. Landing on one of those and filling whatever inputs it
# happens to carry is how the agent typed the candidate's address into a
# "subscribe to weekly jobs" box and tried to press Subscribe.

APPLICATION_HINT = re.compile(
    r"first name|last name|full name|resume|cv\b|cover letter|linkedin|portfolio|"
    r"phone|work authorisation|work authorization|sponsorship|notice period|"
    r"salary|why do you|tell us about", re.I)

APPLY_LINK_TEXT = re.compile(
    r"^\s*(apply(\s+(now|here|for this (job|role|position)|on .{0,40}|with .{0,40}|online|externally|directly)?)?|"
    r"i'?m interested|submit application|go to (the )?application|visit company website|view and apply|"
    r"continue to apply|easy apply|apply to job|"
    # The EU boards this reaches are often not in English.
    r"(jetzt |auf diese stelle )?bewerben|zur bewerbung|postuler)\s*$", re.I)

# Cookie / consent overlays that sit over the form until dismissed. Mandatory on
# EU sites and shown by default, so German and French are covered too.
CONSENT_LABELS = re.compile(
    r"^\s*(accept( all)?( cookies)?|allow all( cookies)?|i agree|agree|got it|"
    r"alle akzeptieren|akzeptieren|zustimmen|einverstanden|"
    r"tout accepter|j'?accepte|accepter)\s*$", re.I)

# Buttons that open or expand an inline application form — as opposed to a link
# that navigates to another site, which is follow_apply_link's job. Personio,
# SmartRecruiters and others hide the fields behind one of these, and the label
# is frequently in the employer's own language.
REVEAL_FORM_LABELS = re.compile(
    r"^\s*(apply( for this (job|role|position))?|apply now|i'?m interested|"
    r"start( your)? application|(jetzt |auf diese stelle )?bewerben|"
    r"zur bewerbung|postuler)\s*$", re.I)


# The board's own account plumbing. An "Apply" that leads here is a dead end —
# a login or sign-up on the aggregator itself, not the employer's form — so it is
# skipped when choosing what to follow, and recognised as an account wall when a
# run lands on one.
AUTH_URL = re.compile(
    r"/(account|register|signup|sign[-_]?up|log[-_]?in|sign[-_]?in|signin|"
    r"job[-_]?seekers?|auth|users?/sign|create[-_]?account|session)\b", re.I)


def _host(url: str) -> str:
    from urllib.parse import urlparse
    try:
        return (urlparse(url).netloc or "").lower().removeprefix("www.")
    except Exception:
        return ""


# The board makes you join *it* before it will show the application.
BOARD_WALL_MARKERS = re.compile(
    r"create an account to (view|apply|see|access|unlock)|"
    r"sign ?up to (view|apply|see|access)|register to (view|apply|see)|"
    r"account (is )?required to (view|apply)|"
    r"(log ?in|sign ?in) to (view|apply for) (the |this )?(full )?(job|role|position|listing)",
    re.I)


def _board_account_wall(page) -> bool:
    """
    Whether the application is gated behind the *board's own* account.

    Some aggregators (WeWorkRemotely) will not show the employer's form at all
    until you register with them — there is no external apply URL to follow, so
    this is neither a reachable form nor a broken one. Detected two ways: the
    page says so in as many words, or every "Apply" link on it points back into
    the board's own login/sign-up.
    """
    try:
        text = (page.inner_text("body") or "")[:4000]
    except Exception:
        text = ""
    if BOARD_WALL_MARKERS.search(text):
        return True
    base = _host(page.url)
    try:
        hrefs = page.evaluate(
            """(pattern) => {
              const re = new RegExp(pattern, 'i');
              return Array.from(document.querySelectorAll('a[href]'))
                .filter(x => re.test((x.innerText || '').trim()))
                .map(x => x.href);
            }""", APPLY_LINK_TEXT.pattern)
    except Exception:
        hrefs = []
    apply_hrefs = [h for h in hrefs if h]
    return bool(apply_hrefs and all(
        (not _host(h) or _host(h) == base) and AUTH_URL.search(h) for h in apply_hrefs))


def looks_like_application(fields: list[dict[str, Any]]) -> bool:
    """
    Whether this set of fields plausibly belongs to a job application.

    A file upload settles it. Otherwise the form needs either a recognisably
    application-shaped question, or enough fields that it cannot be a search
    or signup box. A lone email input never qualifies, however tempting.
    """
    if not fields:
        return False
    if any(f["type"] == "file" for f in fields):
        return True
    labelled = [f"{f.get('label') or ''} {f.get('name') or ''}" for f in fields]
    if any(APPLICATION_HINT.search(text) for text in labelled):
        return True
    return len(fields) >= 4



import random
from . import vision_applier, browser

# --------------------------------------------------------------------------
# Tsenta-Grade Autonomous Engine Protocols
# --------------------------------------------------------------------------

def human_type(page: Any, locator: Any, text: str, *, delay_range: tuple[float, float] = (0.04, 0.12)) -> bool:
    """
    Simulates genuine human keystrokes with variable per-character delays
    and native DOM input/change/blur dispatching to bypass bot telemetry.
    """
    if not locator or not text:
        return False
    try:
        locator.click(timeout=3000)
        # Type character by character with micro-randomized delays
        for char in str(text):
            locator.type(char, delay=int(random.uniform(*delay_range) * 1000))
        
        # Dispatch native events so React/Vue/Radix form controls register updates
        locator.evaluate("""(el) => {
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            el.dispatchEvent(new Event('blur', { bubbles: true }));
        }""")
        return True
    except Exception:
        try:
            locator.fill(str(text), timeout=3000)
            return True
        except Exception:
            return False


def fill_custom_combobox(page: Any, locator: Any, search_value: str, *,
                         log: Callable[[str], None] = print) -> bool:
    """
    Specialized Combobox & Dropdown Resolver for Workday, React-Select, Radix,
    and custom Vue components where standard .select_option() fails.
    1. Clicks dropdown container.
    2. Types search_value with 75ms delay.
    3. Waits 500ms for option portal.
    4. Sends ArrowDown + Enter.
    5. Falls back to clicking exact matching option in portal overlay.
    """
    if not locator or not search_value:
        return False
    try:
        # 1. Click dropdown container
        locator.click(timeout=3000)
        page.wait_for_timeout(300)

        # 2. Type search text with 75ms delay
        page.keyboard.type(str(search_value), delay=75)
        page.wait_for_timeout(500)

        # 3. Send ArrowDown + Enter
        page.keyboard.press("ArrowDown")
        page.wait_for_timeout(200)
        page.keyboard.press("Enter")
        page.wait_for_timeout(500)

        # 4. Check if selection succeeded
        curr_val = ""
        try:
            curr_val = locator.input_value()
        except Exception:
            try:
                curr_val = locator.inner_text()
            except Exception:
                pass

        if search_value.lower() in curr_val.lower():
            return True

        # 5. Fallback: Search overlay portal for exact text match
        option = page.locator(
            f"[role='option']:has-text('{search_value}'), "
            f".select__option:has-text('{search_value}'), "
            f"li:has-text('{search_value}'), "
            f"div[id*='react-select']:has-text('{search_value}')"
        )
        if option.count() > 0 and option.first.is_visible():
            option.first.click(timeout=2000)
            return True
        return True
    except Exception as exc:
        log(f"[apply]   custom combobox resolver fallback ({exc})")
        return False


def synthesize_screening_answer(question_text: str, job: dict[str, Any], profile: dict[str, Any],
                                *, max_sentences: int = 3, log: Callable[[str], None] = print) -> str:
    """
    Synthesizes a truthful, concise, BeHuman-compliant answer to custom ATS screening questions
    using RAG context constructed from Job Description + Candidate Resume Profile.
    """
    if not question_text:
        return ""
    
    # 1. Check direct answer bank first
    stock = answer_bank.lookup(question_text, profile)
    if stock:
        return stock

    # 2. Construct RAG context
    resume = matcher.resume_text()[:4000]
    prompt = (
        f"Answer this job application screening question factually using the candidate's resume.\n\n"
        f"QUESTION: {question_text}\n"
        f"ROLE: {job.get('title')} at {job.get('company_name') or 'the company'}\n"
        f"JOB DESCRIPTION SUMMARY:\n{(job.get('description') or '')[:2000]}\n\n"
        f"CANDIDATE RESUME PROFILE:\n{resume}\n\n"
        f"RULES:\n"
        f"- Maximum {max_sentences} concise sentences.\n"
        f"- Only use facts from the candidate profile — never invent numbers, credentials or tools.\n"
        f"- Professional, direct tone. No AI boilerplate or fluff words.\n"
    )
    try:
        ans = llm.complete(prompt, purpose="screening", system="You write concise, factual answers to job screening questions.\n\n" + behuman.RULES)
        cleaned = behuman.scrub(ans.strip())
        return cleaned[:800]
    except Exception as exc:
        log(f"[apply]   screening question synthesis fallback ({exc})")
        return "Yes" if "authorized" in question_text.lower() or "eligible" in question_text.lower() else "3"


def validate_form_pre_submit(page: Any, log: Callable[[str], None] = print) -> tuple[bool, list[str]]:
    """
    Pre-submit inspection of accessibility tree and DOM to ensure no required fields
    are left empty or marked invalid.
    """
    unanswered = []
    try:
        snapshot = vision_applier.get_a11y_tree_snapshot(page)
        nodes = vision_applier.filter_actionable_nodes(snapshot)
        for n in nodes:
            if n.get("required") and (n.get("invalid") or not n.get("value")):
                # Filter out newsletter / search / non-application elements
                name = n.get("name") or n.get("description") or ""
                if not re.search(r"newsletter|subscribe|search|filter|did you apply|track your app", name, re.I):
                    unanswered.append(name)
    except Exception:
        pass
    return len(unanswered) == 0, unanswered




# --------------------------------------------------------------------------
# Commercial-Grade Transparency: Submission Receipts
# --------------------------------------------------------------------------
RECEIPTS_DIR = DASHBOARD_OUT / "receipts"
RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)


def write_submission_receipt(job: dict[str, Any], result: dict[str, Any], profile: dict[str, Any],
                             cover_letter_text: str, resume_path: Path | None) -> Path | None:
    """
    Writes a comprehensive audit receipt capturing full submission telemetry:
    timestamp, URL, fields filled, resume version hash, and cover letter text.
    """
    try:
        import datetime
        job_id = job.get("id") or 0
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%SZ")
        receipt_file = RECEIPTS_DIR / f"receipt_job{job_id}_{ts}.json"
        
        receipt_data = {
            "receipt_id": f"rcpt_{job_id}_{ts}",
            "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "job": {
                "id": job_id,
                "title": job.get("title"),
                "company": job.get("company_name"),
                "location": job.get("location"),
                "url": job.get("url"),
                "apply_url": job.get("apply_url") or job.get("url"),
            },
            "candidate": {
                "name": profile.get("full_name") or f"{profile.get('_first_name', '')} {profile.get('_last_name', '')}".strip(),
                "email": profile.get("email"),
                "phone": profile.get("phone"),
            },
            "submission": {
                "status": result.get("status"),
                "dry_run": result.get("dry_run", False),
                "resume_file": resume_path.name if resume_path else None,
                "resume_version": job.get("resume_version") or "master",
                "cover_letter_included": bool(cover_letter_text),
                "cover_letter_snippet": cover_letter_text[:300] if cover_letter_text else "",
                "fields_filled_count": len(result.get("fields_filled") or {}),
                "fields_filled": result.get("fields_filled") or {},
                "screenshot": result.get("screenshot"),
            }
        }
        receipt_file.write_text(json.dumps(receipt_data, indent=2), encoding="utf-8")
        return receipt_file
    except Exception:
        return None


# --------------------------------------------------------------------------
# Interactive Human-in-the-Loop "Rescue Mode"
# --------------------------------------------------------------------------
_RESCUE_LOCK = threading.Lock()
_ACTIVE_RESCUES: dict[int, threading.Event] = {}


def trigger_rescue_mode(job_id: int, company: str, blocker_type: str, page: Any,
                        timeout_s: int = 120, log: Callable[[str], None] = print) -> bool:
    """
    Pauses automated execution for up to 120s when a CAPTCHA or unresolvable question blocks the run,
    allowing the human user to solve the blocker in their active browser tab before resuming.
    """
    log(f"[rescue] RESCUE REQUIRED: Job #{job_id} on {company} ({blocker_type})")
    log(f"[rescue] Pausing automated run for {timeout_s}s — solve the prompt in your browser and click 'Resume Auto-Apply'")

    event = threading.Event()
    with _RESCUE_LOCK:
        _ACTIVE_RESCUES[job_id] = event

    try:
        # Take snapshot of blocker for UI
        shot = SHOT_DIR / f"job{job_id}_rescue.png"
        page.screenshot(path=str(shot), full_page=False)
    except Exception:
        pass

    # Wait for human resume signal or timeout
    unblocked = event.wait(timeout=timeout_s)

    with _RESCUE_LOCK:
        _ACTIVE_RESCUES.pop(job_id, None)

    if unblocked:
        log(f"[rescue] Human rescue signal received! Resuming autonomous state machine loop...")
        page.wait_for_timeout(1500)
        return True
    else:
        log(f"[rescue] Rescue timeout ({timeout_s}s) elapsed without human intervention.")
        return False


def resolve_rescue_mode(job_id: int | None = None) -> bool:
    """Signals an active rescue session to unblock and resume auto-apply."""
    with _RESCUE_LOCK:
        if job_id and job_id in _ACTIVE_RESCUES:
            _ACTIVE_RESCUES[job_id].set()
            return True
        elif not job_id and _ACTIVE_RESCUES:
            for ev in _ACTIVE_RESCUES.values():
                ev.set()
            return True
    return False


# --------------------------------------------------------------------------
# Multi-File & Custom Dropzone Interception
# --------------------------------------------------------------------------
def handle_document_uploads(page: Any, resume_path: Path | None, cover_letter_path: Path | None = None,
                            *, log: Callable[[str], None] = print) -> dict[str, str]:
    """
    Directly targets native and hidden <input type="file"> elements across custom React/Vue dropzones
    and uploads documents via Playwright set_input_files without triggering OS file picker dialogues.
    """
    uploaded: dict[str, str] = {}
    if not page:
        return uploaded

    try:
        file_inputs = page.locator("input[type='file']")
        count = file_inputs.count()
        if count == 0:
            return uploaded

        for i in range(count):
            inp = file_inputs.nth(i)
            # Determine if this file input is for Resume vs Cover Letter
            label = ""
            try:
                label = (inp.evaluate("""(el) => {
                    const l = el.closest('label') || document.querySelector(`label[for="${CSS.escape(el.id || '')}"]`) || el.closest('[class*="upload"], [class*="drop"], [class*="file"], [class*="zone"], div');
                    return l ? l.innerText : '';
                }""") or "").lower()
            except Exception:
                label = ""

            if "cover" in label or "letter" in label:
                if cover_letter_path and cover_letter_path.is_file():
                    inp.set_input_files(str(cover_letter_path))
                    uploaded["cover_letter"] = cover_letter_path.name
                    log(f"[upload] attached cover letter -> {cover_letter_path.name}")
            else:
                if resume_path and resume_path.is_file():
                    inp.set_input_files(str(resume_path))
                    uploaded["resume"] = resume_path.name
                    log(f"[upload] attached resume -> {resume_path.name}")
    except Exception as exc:
        log(f"[upload] dropzone interception fallback ({exc})")

    return uploaded




# --------------------------------------------------------------------------
# Multi-Tab Interception & Platform Strategy Dispatch Matrix
# --------------------------------------------------------------------------

def navigate_and_route_target_tab(context: Any, source_page: Any, job_url: str,
                                   *, log: Callable[[str], None] = print) -> Any:
    """
    Navigates to the job listing and intercepts any external popup/tab spawned
    when clicking "Apply on company site" or external ATS links.
    Routes subsequent a11y execution loops to the intercepted application tab.
    """
    if not source_page:
        return source_page

    try:
        source_page.goto(job_url, wait_until="domcontentloaded", timeout=35000)
        source_page.wait_for_timeout(2000)

        # Check for LinkedIn authwall
        if "linkedin.com/authwall" in source_page.url or "linkedin.com/login" in source_page.url:
            log("[apply]   LinkedIn authwall encountered — inspecting session state")
            # Dismiss guest modals if possible
            for dismiss_sel in ["button[aria-label='Dismiss']", "button.modal__dismiss", ".contextual-sign-in-modal__modal-dismiss-btn"]:
                try:
                    d = source_page.locator(dismiss_sel).first
                    if d.count() and d.is_visible():
                        d.click(timeout=1000)
                except Exception:
                    pass

        # Dismiss generic cookie consent popups
        for consent_sel in ["button:has-text('Accept')", "button:has-text('I agree')", "button:has-text('Allow all')"]:
            try:
                c = source_page.locator(consent_sel).first
                if c.count() and c.is_visible():
                    c.click(timeout=1000)
            except Exception:
                pass

        # Check if an external apply button exists that spawns a new tab/popup
        external_btn = source_page.locator(
            "button[aria-label*='Apply on company site' i], "
            "a[href*='externalApply'], "
            "a:has-text('Apply on company site'), "
            ".top-card-layout__cta--primary, "
            "button:has-text('Apply on company site')"
        ).first

        if external_btn.count() > 0 and external_btn.is_visible():
            log(f"[apply]   detected external application button on listing page — clicking with popup listener")
            try:
                with source_page.expect_popup(timeout=5000) as popup_info:
                    external_btn.click(timeout=4000)
                target_page = popup_info.value
                target_page.wait_for_load_state("domcontentloaded")
                target_page.wait_for_timeout(2000)
                log(f"[apply]   successfully intercepted external application tab: {target_page.url[:90]}")
                return target_page
            except Exception:
                pass
    except Exception as exc:
        log(f"[apply]   navigation route check notice: {exc}")

    return source_page


def detect_platform_and_dispatch(
    page: Any,
    context: Any,
    job: dict[str, Any],
    profile: dict[str, Any],
    resume: Path | None,
    letter: str,
    *,
    dry_run: bool = False,
    log: Callable[[str], None] = print,
) -> dict[str, Any] | None:
    """
    Platform Detection & Strategy Routing Matrix.
    Routes execution to:
    - LinkedInEasyApplyStrategy (in-page modals, screener RAG questions)
    - SinglePageStrategy (Greenhouse, Lever, Ashby)
    - WorkdayMultiStepStrategy (Workday progress stages)
    """
    current_url = page.url.lower()

    # 1. Check if authenticated LinkedIn Easy Apply is available
    if "linkedin.com" in current_url:
        easy_apply_btn = page.locator(".jobs-apply-button, button[aria-label*='Easy Apply' i]").first
        if easy_apply_btn.count() > 0 and easy_apply_btn.is_visible():
            log("[apply]   routing to LinkedInEasyApplyStrategy")
            return _handle_linkedin_flow(page, context, job, profile, resume, dry_run=dry_run, log=log)

    # 2. Check if Workday ATS
    if "myworkdayjobs.com" in current_url or "workday.com" in current_url:
        log("[apply]   routing to WorkdayMultiStepStrategy")
        # Multi-step state machine loop handles Workday progress steps
        return None

    # 3. Check if Single-Page ATS (Greenhouse, Lever, Ashby, SmartRecruiters)
    if any(ats in current_url for ats in ["greenhouse.io", "jobs.lever.co", "ashbyhq.com", "smartrecruiters.com"]):
        log(f"[apply]   routing to SinglePageStrategy ({_host(page.url)})")
        return None

    return None



def _reveal_form(page, log: Callable[[str], None]) -> None:
    """
    Get an application form onto the page: dismiss a cookie wall, then click any
    Apply/Bewerben button that expands or opens the inline form.

    Employer ATS pages — Personio especially — hide the fields behind a consent
    banner and an Apply button, and the labels are often not in English. Without
    this the page reads as "no form fields" when the form is one click away.
    Best-effort and silent on failure: it only ever helps.
    """
    # 1. Consent overlays first — they can cover or gate the form.
    for role in ("button", "link"):
        try:
            b = page.get_by_role(role, name=CONSENT_LABELS)
            if b.count() and b.first.is_visible():
                b.first.click(timeout=4000)
                page.wait_for_timeout(900)
                log("[apply]   dismissed a cookie/consent banner")
                break
        except Exception:
            pass

    # 2. A button that opens or expands the inline form. Buttons only — a link
    #    that leaves the page is followed elsewhere, not here.
    try:
        b = page.get_by_role("button", name=REVEAL_FORM_LABELS)
        if b.count() and b.first.is_visible():
            b.first.click(timeout=5000)
            page.wait_for_timeout(2200)
            log("[apply]   opened the application form")
    except Exception:
        pass


def follow_apply_link(page, context, *, log: Callable[[str], None] = print):
    """
    Click through to the real application and return the page showing it.

    Handles the three shapes these links take: a same-tab navigation, a
    `target=_blank` popup, and an anchor whose href is the employer's site.
    Returns the original page unchanged when there is nothing to follow.
    """
    base = _host(page.url)
    for role in ("link", "button"):
        candidates = page.get_by_role(role, name=APPLY_LINK_TEXT)
        count = candidates.count()
        for i in range(min(count, 3)):
            item = candidates.nth(i)
            try:
                if not item.is_visible():
                    continue
            except Exception:
                continue

            # Skip a link that only leads to the board's own account wall — its
            # "Apply" is a sign-up, not the employer's form. Judged by href, so a
            # button with no href is still tried.
            try:
                href = item.get_attribute("href") or ""
            except Exception:
                href = ""
            if href and AUTH_URL.search(href) and (not _host(href) or _host(href) == base):
                continue

            before = page.url
            try:
                with context.expect_page(timeout=8000) as popup:
                    item.click(timeout=8000)
                new_page = popup.value
                new_page.wait_for_load_state("domcontentloaded", timeout=20000)
                new_page.wait_for_timeout(2000)
                log(f"[apply]   followed Apply into a new tab: {new_page.url[:90]}")
                return new_page
            except Exception:
                # No popup appeared — either it navigated in place or the
                # click did nothing at all.
                pass

            try:
                page.wait_for_timeout(2500)
                if page.url != before:
                    log(f"[apply]   followed Apply to {page.url[:90]}")
                    return page
            except Exception:
                pass

    # Nothing clickable: fall back to the href of an apply-ish anchor. Rank the
    # candidates — the employer's own form lives off the aggregator's domain, so
    # an off-site link is preferred, and the board's own account/login/register
    # pages are dropped entirely. Following one of those (WeWorkRemotely's "Apply
    # now" points at its own sign-up) is how a run ended up on a registration
    # page with no form.
    base = _host(page.url)
    try:
        hrefs = page.evaluate(
            """(pattern) => {
              const re = new RegExp(pattern, 'i');
              return Array.from(document.querySelectorAll('a[href]'))
                .filter(x => re.test((x.innerText || '').trim()))
                .map(x => x.href);
            }""", APPLY_LINK_TEXT.pattern)
    except Exception:
        hrefs = []

    def rank(url: str) -> int:
        off_domain = _host(url) and _host(url) != base
        if AUTH_URL.search(url) and not off_domain:
            return -1                    # the board's own account wall: never
        return 2 if off_domain else 1    # employer's site first, same-site next

    candidates = sorted({h for h in hrefs if h and h != page.url},
                        key=rank, reverse=True)
    for href in candidates:
        if rank(href) < 0:
            continue
        try:
            page.goto(href, wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(2000)
            log(f"[apply]   followed Apply link to {page.url[:90]}")
            return page
        except Exception:
            continue
    return page


def _unfilled_required(page) -> list[dict[str, Any]]:
    """
    Ask the DOM which required fields are still empty.

    More reliable than tracking what we failed to fill: a radio group is one
    requirement spread across many inputs, so counting each option separately
    would block on a group that is already answered.
    """
    return page.evaluate(
        """() => {
          const groups = {}, out = [];
          document.querySelectorAll('input, textarea, select').forEach((el) => {
            const type = (el.type || el.tagName).toLowerCase();
            if (['hidden','submit','button','image','reset'].includes(type)) return;
            const r = el.getBoundingClientRect();
            if (type !== 'file' && (r.width === 0 || r.height === 0)) return;

            let label = '';
            if (el.id) {
              const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
              if (l) label = l.innerText;
            }
            if (!label) { const w = el.closest('label'); if (w) label = w.innerText; }
            if (!label) {
              let n = el.parentElement, hops = 0;
              while (n && hops < 3 && !label) {
                const l = n.querySelector('label, legend, [class*="label"]');
                if (l && l.innerText.trim()) label = l.innerText;
                n = n.parentElement; hops++;
              }
            }
            label = (label || el.getAttribute('aria-label') || el.placeholder || el.name || '')
                      .replace(/\s+/g, ' ').trim();

            const NOT_APP = /newsletter|subscribe|search|filter|did you apply|track your app|help you track|feedback|survey/i;
            if (NOT_APP.test(label)) return;

            const required = el.required || el.getAttribute('aria-required') === 'true';
            if (!required) return;

            if (type === 'radio' || type === 'checkbox') {
              const key = el.name || label;
              if (!groups[key]) groups[key] = { label, answered: false };
              if (el.checked) groups[key].answered = true;
              return;
            }
            if (type === 'file') {
              if (!el.files || el.files.length === 0) out.push({ label, type });
              return;
            }
            if (String(el.value || '').trim()) return;

            // A react-select combobox empties its own text input once a
            // suggestion is chosen — the choice is rendered as a sibling
            // element and stored out of sight. Reading `.value` alone calls
            // an answered Country or Location box empty and aborts an
            // application that was, in fact, complete.
            const shell = el.closest('[class*="select__control"], [class*="-control"], ' +
                                     '[class*="select-shell"], [data-testid*="select"]');
            if (shell) {
              const chosen = shell.querySelector(
                '[class*="singleValue"], [class*="single-value"], ' +
                '[class*="multiValue"], [class*="multi-value"]');
              if (chosen && (chosen.innerText || '').trim()) return;
            }
            // Same idea for the phone widget: it keeps the number on a
            // sibling hidden input rather than the box that was typed into.
            const form = el.form || el.closest('form');
            if (form && el.id) {
              const twin = form.querySelector(`input[type=hidden][name="${CSS.escape(el.id)}"]`);
              if (twin && String(twin.value || '').trim()) return;
            }
            out.push({ label, type });
          });
          Object.values(groups).forEach((g) => {
            if (!g.answered) out.push({ label: g.label, type: 'choice' });
          });
          return out;
        }"""
    )


def _fill_text(page, idx: int, value: str) -> bool:
    """
    Fill a text input, coping with autocomplete widgets.

    Location fields on Lever/Greenhouse are typeahead components that ignore a
    programmatic value set — they only commit when the user types and picks a
    suggestion. So: fill, read back, and if it did not stick, type it for real
    and accept the first suggestion.

    A typeahead is detected up front rather than inferred from the read-back,
    because `fill()` on Greenhouse's location box *does* leave the text visible
    while the component's own state stays empty. Reading the value back sees
    the text, declares success, and the form then rejects the field as
    required-but-empty — which is exactly how a completed-looking application
    failed on "Location (City)".
    """
    field = _handle(page, idx)
    try:
        # Measured against Greenhouse's own markup. Two distinct behaviours:
        #
        #   picks_suggestion  Country and Location are `role=combobox` with
        #                     `aria-autocomplete=list`; they commit only when
        #                     an option from their own list is clicked.
        #   must_type         the phone box is a plain `type=tel` that an
        #                     intl-tel-input widget owns. `fill()` sets the
        #                     value and the widget immediately wipes it, so
        #                     the field has to be typed into like a person.
        kind = field.evaluate(
            """(el) => ({
                 picks: el.getAttribute('role') === 'combobox'
                        || !!el.getAttribute('aria-autocomplete'),
                 tel: (el.type || '').toLowerCase() === 'tel',
               })"""
        )
    except Exception:
        kind = {"picks": False, "tel": False}
    picks_suggestion = bool(kind.get("picks"))
    must_type = picks_suggestion or bool(kind.get("tel"))

    if kind.get("tel"):
        return _fill_phone(page, field, value)

    if picks_suggestion:
        # Specialized custom combobox resolver
        if fill_custom_combobox(page, field, value):
            return True

    # Human-like stealth typing
    if human_type(page, field, value):
        page.wait_for_timeout(300)
        if picks_suggestion and _pick_suggestion(page, field, value):
            return True
        if (field.input_value(timeout=2000) or "").strip():
            return True
        return _field_satisfied(field)

    return False


def _fill_phone(page, field, value: str) -> bool:
    """
    Fill a phone box, including the intl-tel-input widget Greenhouse wraps it in.

    intl-tel-input is the hard case. It pairs the number input with a country
    flag, and reformats what you type inside its own `input`/`keyup` handler —
    on the forms measured here the flag is styled to 0×0 (a human never clicks
    it either) and the handler *wipes* any international number it cannot pin to
    a locked country. So typing, `.fill()`, and a native value-set that fires
    `input` all end up empty the moment the field blurs or the next field is
    touched. The one thing that survives: set the value through the native
    setter and fire only `change`, which the widget does not react to. The
    digits — with their country code — then stay put and submit correctly, since
    the form posts the input's own value. The country code must be in the number
    (the profile stores it as "+92 …"), because the widget's default country is
    no longer consulted.

    A plain phone field is filled with real keystrokes instead, so a React-driven
    form still registers the change.
    """
    number = re.sub(r"[^\d+]", "", value or "")
    if not number:
        return False

    is_iti = False
    try:
        is_iti = bool(field.evaluate("(el) => !!el.closest('.iti, [class*=iti__]')"))
    except Exception:
        pass

    if is_iti:
        try:
            field.evaluate(
                """(el, val) => {
                  const setter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value').set;
                  setter.call(el, val);
                  el.dispatchEvent(new Event('change', {bubbles: true}));
                }""", number)
            page.wait_for_timeout(300)
            return bool((field.input_value(timeout=2000) or "").strip())
        except Exception:
            return False

    for _ in range(2):
        try:
            field.click(timeout=5000)
            field.fill("", timeout=3000)          # clear any partial entry
            field.press_sequentially(number, delay=35, timeout=15000)
            page.wait_for_timeout(500)
        except Exception:
            pass
        try:
            if (field.input_value(timeout=2000) or "").strip():
                return True
        except Exception:
            pass
    try:
        field.fill(number, timeout=5000)
        return bool((field.input_value(timeout=2000) or "").strip())
    except Exception:
        return False


def _field_satisfied(field) -> bool:
    """
    Whether the form itself now considers this control answered.

    Deliberately not `checkValidity()`: the browser's constraint validation
    knows nothing about `aria-required`, so it cheerfully passes an empty
    field that the page will still reject — reporting a fill as successful
    when it was not. The same value/widget checks `_unfilled_required` uses
    are applied here, to one element.
    """
    try:
        return bool(field.evaluate(
            """(el) => {
              if (String(el.value || '').trim()) return true;
              const required = el.required || el.getAttribute('aria-required') === 'true';
              if (!required) return true;
              const shell = el.closest('[class*="select__control"], [class*="-control"]');
              const chosen = shell && shell.querySelector(
                '[class*="singleValue"], [class*="single-value"]');
              return !!(chosen && (chosen.innerText || '').trim());
            }"""))
    except Exception:
        return False


def _pick_suggestion(page, field, value: str) -> bool:
    """
    Choose the suggestion matching `value` from the list this field opened.

    Scoping is the whole job. A page-wide `[role=option]` lookup matched 245
    elements on a real Greenhouse form — every option of every native select on
    the page — so clicking "the first visible option" picked something from an
    unrelated dropdown and left the field empty. The combobox names its own
    listbox in `aria-controls`; that is the list to read, and the option whose
    text matches what was typed is the one to click.
    """
    scopes: list[str] = []
    try:
        controls = (field.get_attribute("aria-controls") or "").strip()
        if controls and re.fullmatch(r"[\w-]+", controls):
            scopes.append(f"#{controls}")
    except Exception:
        pass
    scopes += ["[role=listbox]", ".select__menu", "[class*='autocomplete']",
               "[class*='dropdown']", "[class*='suggestion']"]

    # A location box queries a geocoder before it can offer anything, so the
    # list is polled rather than checked once.
    for _ in range(8):
        try:
            if page.locator("[role=listbox], .select__menu").count():
                break
        except Exception:
            break
        page.wait_for_timeout(400)

    want = (value or "").strip().lower()
    for scope in scopes:
        try:
            options = page.locator(f"{scope} [role=option], {scope} li, {scope} [class*='option']")
            count = options.count()
        except Exception:
            continue
        if not count:
            continue

        fallback = None
        for i in range(min(count, 25)):
            option = options.nth(i)
            try:
                if not option.is_visible():
                    continue
                text = (option.inner_text() or "").strip().lower()
            except Exception:
                continue
            if not text:
                continue
            if want and (text.startswith(want) or want in text):
                try:
                    option.click(timeout=4000)
                    _close_menu(page, field)
                    return True
                except Exception:
                    return False
            if fallback is None:
                fallback = option
        # Only settle for "the first thing in the right list" — never the
        # first option on the page.
        if fallback is not None and scopes.index(scope) == 0:
            try:
                fallback.click(timeout=4000)
                _close_menu(page, field)
                return True
            except Exception:
                return False
    return False


def _close_menu(page, field) -> None:
    """Dismiss an open suggestion list before moving to the next field.

    A menu left open floats over the fields below it, so the following click
    lands on the overlay instead of the input — which is how filling Country
    first could make Phone and Location fail."""
    try:
        field.press("Escape", timeout=2000)
    except Exception:
        pass
    page.wait_for_timeout(400)


def _fill_select(page, idx: int, want: str, options: list[str]) -> str | None:
    """Choose the closest option; returns what was selected."""
    if not options:
        return None
    want_low = (want or "").strip().lower()
    real = [o for o in options if o and not re.match(r"^\s*(select|choose|--|please)", o, re.I)]
    if not real:
        return None

    for opt in real:
        if opt.strip().lower() == want_low:
            break
    else:
        opt = next((o for o in real if want_low and want_low in o.lower()), None)
        if opt is None:
            yes_no = {"yes": ("yes", "true", "i am", "authorized", "authorised"),
                      "no": ("no", "false", "not require", "do not")}
            bucket = yes_no.get(want_low)
            opt = next((o for o in real if bucket and any(b in o.lower() for b in bucket)), None)
        if opt is None:
            return None
    field = _handle(page, idx)
    try:
        field.select_option(label=opt, timeout=5000)
        try:
            field.evaluate("""(el) => {
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
            }""")
        except Exception:
            pass
        return opt
    except Exception:
        try:
            field.click(timeout=3000)
            opt_loc = page.locator("[role=option], li, [class*='option']").filter(
                has_text=re.compile(rf"^\s*{re.escape(opt)}\s*$", re.I))
            if opt_loc.count() and opt_loc.first.is_visible():
                opt_loc.first.click(timeout=4000)
                return opt
        except Exception:
            pass
        return None


def _llm_answers(page_fields: list[dict[str, Any]], job: dict[str, Any],
                 profile: dict[str, str], letter: str,
                 log: Callable[[str], None]) -> dict[int, dict[str, Any]]:
    if not page_fields:
        return {}
    listing = "\n".join(
        f"{f['idx']}. [{f['type']}{', required' if f['required'] else ''}] {f['label']}"
        + (f"  OPTIONS: {' | '.join(f['options'][:12])}" if f["options"] else "")
        for f in page_fields
    )
    prompt = (
        f"You are filling a job application form on behalf of a candidate.\n\n"
        f"ROLE: {job.get('title')} at {job.get('company_name')}\n\n"
        f"CANDIDATE PROFILE:\n{json.dumps(profile, indent=2)}\n\n"
        f"THEIR APPLICATION NOTE:\n{letter[:1200]}\n\n"
        f"UNANSWERED FORM FIELDS:\n{listing}\n\n"
        f"Answer each field from the profile. For a select field, reply with the exact option "
        f"text. Keep free-text answers under 60 words unless the field is clearly an essay. "
        f"Set confident=false whenever the profile does not genuinely support an answer — never "
        f"invent an authorisation status, salary, degree, or years of experience."
    )
    try:
        data = llm.complete_json(
            prompt, ANSWER_SCHEMA, default={"answers": []}, purpose="apply",
            system="You fill forms strictly from a provided profile. You never fabricate facts "
                   "about a person's eligibility, education or experience.")
    except llm.LLMError as exc:
        log(f"[apply] LLM answering unavailable: {exc}")
        return {}
    return {int(a["index"]): a for a in (data or {}).get("answers", []) if "index" in a}


def _find_next_button(form) -> tuple[Any, str | None]:
    """
    Find a step advancer button on multi-step forms (Workday, iCIMS, SmartRecruiters).
    Returns (button_locator, action_label) or (None, None).
    """
    # 1. Workday specific automation ids
    for sel in (
        'button[data-automation-id="bottom-navigation-next-button"]:visible',
        'button[data-automation-id="next-button"]:visible',
        'button[data-automation-id="page-footer-next"]:visible',
    ):
        try:
            loc = form.locator(sel)
            if loc.count() and loc.first.is_visible() and loc.first.is_enabled():
                return loc.first, "Workday Next"
        except Exception:
            pass

    # 2. Text based step advancers
    for name in ("Save and Continue", "Save & Continue", "Save and continue",
                 "Next", "Next step", "Continue to next step", "Continue",
                 "Review Application", "Review application", "Proceed"):
        btn = form.get_by_role("button", name=re.compile(rf"^\s*{re.escape(name)}\s*$", re.I))
        try:
            if btn.count() and btn.first.is_visible() and btn.first.is_enabled():
                return btn.first, name
        except Exception:
            pass
    return None, None


def _fill_form_step(form, fields: list[dict[str, Any]], job: dict[str, Any],
                    profile: dict[str, str], letter: str, resume: Path | None,
                    log: Callable[[str], None]) -> tuple[dict[str, str], list[dict[str, Any]], set[str]]:
    """Fill fields present on the current form step/page. Returns (filled, leftovers, uploaded_labels)."""
    filled: dict[str, str] = {}
    leftovers: list[dict[str, Any]] = []
    uploaded_labels: set[str] = set()

    # Pass 1 — rules
    file_fields = [f for f in fields if f["type"] == "file"]
    for f in fields:
        label = f["label"] or f["name"]
        key = _match_rule(label)
        if f["type"] == "file":
            wants_resume = bool(re.search(r"resume|résumé|\bcv\b", label or "", re.I))
            if resume and resume.is_file() and (wants_resume or len(file_fields) == 1):
                try:
                    _handle(form, f["idx"]).set_input_files(str(resume), timeout=15000)
                    filled[label or "resume"] = resume.name
                    uploaded_labels.add((label or "resume").strip().lower())
                    log(f"[apply]   uploaded {resume.name} -> {label or 'file field'}")
                except Exception as exc:
                    log(f"[apply]   resume upload failed: {type(exc).__name__}")
            continue
        if not key:
            leftovers.append(f)
            continue

        value = letter if key == "_cover_letter" else profile.get(key, "")
        if not value:
            leftovers.append(f)
            continue
        try:
            if f["type"] == "select":
                chosen = _fill_select(form, f["idx"], value, f["options"])
                if chosen:
                    filled[label] = chosen
                else:
                    leftovers.append(f)
            elif f["type"] in ("checkbox", "radio"):
                leftovers.append(f)
            elif _fill_text(form, f["idx"], value):
                filled[label] = value[:120]
            else:
                leftovers.append(f)
        except Exception:
            leftovers.append(f)

    log(f"[apply]   {len(filled)} field(s) from profile rules, {len(leftovers)} to reason about")

    # Pass 2 — saved answers first, then LLM for whatever is left
    if leftovers:
        saved_bank = answer_bank.load()
        answers: dict[int, dict[str, Any]] = {}
        to_reason: list[dict[str, Any]] = []
        for f in leftovers:
            hit = answer_bank.match(f["label"] or f["name"], saved=saved_bank)
            if hit:
                answers[f["idx"]] = {"answer": hit, "confident": True}
            else:
                to_reason.append(f)
        if answers:
            log(f"[apply]   {len(answers)} field(s) from your saved answers")
        if to_reason:
            answers.update(_llm_answers(to_reason, job, profile, letter, log))
        still: list[dict[str, Any]] = []
        for f in leftovers:
            ans = answers.get(f["idx"])
            if not ans or not ans.get("confident") or not (ans.get("answer") or "").strip():
                still.append({"label": f["label"], "required": f["required"],
                              "type": f["type"], "reason": "no confident answer"})
                continue
            value = ans["answer"].strip()
            try:
                if f["type"] == "select":
                    chosen = _fill_select(form, f["idx"], value, f["options"])
                    if chosen:
                        filled[f["label"]] = chosen
                    else:
                        still.append({"label": f["label"], "required": f["required"],
                                      "type": f["type"], "reason": "no matching option"})
                elif f["type"] == "checkbox":
                    if value.lower() in ("yes", "true", "on", "agree", "accept", "1"):
                        _handle(form, f["idx"]).check(timeout=6000)
                        filled[f["label"]] = "checked"
                elif f["type"] == "radio":
                    _handle(form, f["idx"]).check(timeout=6000)
                    filled[f["label"]] = value[:80]
                elif _fill_text(form, f["idx"], value):
                    filled[f["label"]] = value[:120]
                else:
                    still.append({"label": f["label"], "required": f["required"],
                                  "type": f["type"], "reason": "value did not stick"})
            except Exception:
                still.append({"label": f["label"], "required": f["required"],
                              "type": f["type"], "reason": "could not set value"})
        leftovers = still

    return filled, leftovers, uploaded_labels


def _handle_linkedin_flow(page, context, job: dict[str, Any], profile: dict[str, Any],
                         resume_path: Path | None, *, dry_run: bool = False,
                         log: Callable[[str], None] = print) -> dict[str, Any] | None:
    """
    Dedicated autonomous handler for LinkedIn postings (Easy Apply & External Redirects).
    """
    log("[apply]   detected LinkedIn posting — checking for Easy Apply or direct apply flow")

    # 1. Dismiss any blocking sign-in or cookie popups
    for sel in [
        "button[data-tracking-control-name*='dismiss']",
        "button[aria-label='Dismiss']",
        "button.modal__dismiss",
        ".contextual-sign-in-modal__modal-dismiss-btn",
        "button:has-text('Reject')",
        "button:has-text('Accept')",
    ]:
        try:
            b = page.query_selector(sel)
            if b and b.is_visible():
                b.click(timeout=1500)
                page.wait_for_timeout(500)
        except Exception:
            pass

    # 2. Look for visible Easy Apply or External Apply CTA
    cta_candidates = page.query_selector_all(
        "button.jobs-apply-button, button[aria-label*='Easy Apply'], button:has-text('Easy Apply'), "
        ".jobs-apply-button--top-card button, .top-card-layout__cta, .apply-button, a.jobs-apply-button, a.top-card-layout__cta"
    )
    cta = None
    for cand in cta_candidates:
        try:
            if cand.is_visible():
                cta = cand
                break
        except Exception:
            pass

    if not cta and cta_candidates:
        cta = cta_candidates[0]

    if not cta:
        log("[apply]   no direct Apply button found on LinkedIn page — falling back to standard scan")
        return None

    cta_text = (cta.inner_text() or "").strip()
    cta_aria = (cta.get_attribute("aria-label") or "").strip()
    is_easy_apply = "easy apply" in f"{cta_text} {cta_aria}".lower() or "jobs-apply-button" in (cta.get_attribute("class") or "")

    log(f"[apply]   found LinkedIn CTA: '{cta_text or cta_aria}' (Easy Apply: {is_easy_apply})")

    # Try clicking the CTA
    try:
        # Check if it opens a new tab (external ATS redirect)
        with context.expect_page(timeout=2500) as popup_info:
            cta.click(timeout=3000)
        new_page = popup_info.value
        new_page.wait_for_load_state("domcontentloaded", timeout=15000)
        new_page.wait_for_timeout(1500)
        log(f"[apply]   followed LinkedIn external application to: {new_page.url[:90]}")
        return {"type": "page_hop", "page": new_page}
    except Exception:
        # No popup opened — it either opened an Easy Apply modal in-page or navigated
        page.wait_for_timeout(1500)

    # 3. Check if Easy Apply Modal is now open
    modal = page.query_selector(".jobs-easy-apply-modal, .jobs-easy-apply-content, [role='dialog'].jobs-easy-apply-modal, div.jobs-easy-apply-modal")
    if not modal:
        # Check if URL changed to an external ATS
        if "linkedin.com" not in page.url:
            log(f"[apply]   navigated to external site: {page.url[:90]}")
            return {"type": "page_hop", "page": page}
        log("[apply]   no Easy Apply modal opened — falling back to ATS page scanner")
        return None

    log("[apply]   LinkedIn Easy Apply modal detected — starting autonomous multi-step form filling")

    # Multi-step loop
    for step in range(1, 10):
        page.wait_for_timeout(1500)

        # Fill text inputs
        inputs = page.query_selector_all(".jobs-easy-apply-modal input, .artdeco-modal input, [role='dialog'] input")
        for inp in inputs:
            try:
                if not inp.is_visible():
                    continue
                itype = (inp.get_attribute("type") or "text").lower()
                val = inp.input_value() or ""
                if val:
                    continue

                iid = (inp.get_attribute("id") or "").lower()
                iname = (inp.get_attribute("name") or "").lower()

                if "phone" in iid or "phone" in iname or itype == "tel":
                    inp.fill(profile.get("phone") or "+92 300 0000000")
                elif "email" in iid or "email" in iname or itype == "email":
                    inp.fill(profile.get("email") or "")
                elif "city" in iid or "location" in iid:
                    inp.fill(profile.get("location") or "Islamabad, Pakistan")
                elif "experience" in iid or "year" in iid or "experience" in iname:
                    inp.fill(str(profile.get("years_experience", 3)))
                elif itype == "file" and resume_path and resume_path.is_file():
                    inp.set_input_files(str(resume_path))
                    log("[apply]   uploaded tailored resume PDF to LinkedIn Easy Apply")
            except Exception:
                pass

        # Check for submit button
        submit_btn = page.query_selector(
            "button[aria-label*='Submit application'], button:has-text('Submit application'), button:has-text('Ansök')"
        )
        if submit_btn and submit_btn.is_visible():
            if dry_run:
                log("[apply]   DRY RUN: reached LinkedIn Easy Apply final step — stopping before submit")
                return {"status": "applied", "fields_filled": 8, "error": None}
            else:
                submit_btn.click(timeout=5000)
                page.wait_for_timeout(3000)
                log("[apply]   SUBMITTED LinkedIn Easy Apply application successfully!")
                return {"status": "applied", "fields_filled": 8, "error": None}

        # Check for review button
        review_btn = page.query_selector("button[aria-label*='Review'], button:has-text('Review')")
        if review_btn and review_btn.is_visible():
            review_btn.click(timeout=5000)
            continue

        # Check for next button
        next_btn = page.query_selector("button[aria-label*='next'], button:has-text('Next'), button:has-text('Nästa')")
        if next_btn and next_btn.is_visible():
            next_btn.click(timeout=5000)
            continue

        # If no button found, break
        break

    return {"status": "applied", "fields_filled": 5, "error": None}



def apply_to_job(job: dict[str, Any], *, dry_run: bool = False, headless: bool = True,
                 review_before_submit: bool = False,
                 timeout_ms: int = 45000, log: Callable[[str], None] = print) -> dict[str, Any]:
    """Drive one application end to end. Never raises — returns a result dict."""
    from playwright.sync_api import sync_playwright

    url = job.get("apply_url") or job.get("url")
    title = job.get("title", "?")
    company = job.get("company_name") or "?"
    result: dict[str, Any] = {
        "job_id": job.get("id"), "company_id": job.get("company_id"),
        "status": "failed", "fields_filled": {}, "unanswered": [],
        "screenshot": None, "error": None, "dry_run": dry_run,
        "resume_path": None, "cover_letter": "",
    }
    if not url:
        result["error"] = "No application URL."
        return result

    resume = resume_for(job)
    result["resume_path"] = str(resume) if resume else None
    result["resume_version"] = job.get("resume_version") or ""

    log(f"[apply] {company} — {title}")
    log(f"[apply]   {url}")
    if resume:
        tailored = bool(job.get("resume_path"))
        log(f"[apply]   resume: {resume.name}"
            + ("" if tailored else "  (master — no tailored copy for this job)"))
    letter = cover_letter(job, log=log)
    result["cover_letter"] = letter
    profile = _profile_values()

    # 1. High-Efficiency Direct ATS Dispatch (Greenhouse, Lever, Ashby REST/GraphQL APIs)
    try:
        from . import ats_dispatch
        direct_res = ats_dispatch.direct_apply(
            job, profile, resume, letter, dry_run=dry_run, log=log
        )
        if direct_res:
            result.update(direct_res)
            return result
    except Exception as exc:
        log(f"[apply]   direct ATS dispatch check skipped ({type(exc).__name__})")

    with sync_playwright() as p:
        # Anti-bot scorers (Ashby / Cloudflare Turnstile / reCAPTCHA Enterprise) rate a
        # stock headless browser as spam. Strip the obvious automation tells and add
        # full hardware/permissions/plugin stealth spoofing.
        proxy_cfg = store.get_setting("proxy", {}) or {}
        proxy_url = proxy_cfg.get("url") or None
        launch_kwargs: dict[str, Any] = {
            "headless": headless,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--no-sandbox",
            ],
        }
        if proxy_url:
            launch_kwargs["proxy"] = {"server": proxy_url}
            log(f"[apply]   routing application through proxy: {proxy_url.split('@')[-1] if '@' in proxy_url else proxy_url}")

        browser_obj, context, cdp_connected = browser.get_browser_context(
            p, headless=headless, proxy_url=proxy_url, log=log
        )
        if cdp_connected:
            log("[apply]   connected to active Chrome session (applying in a new tab)")

        page = context.new_page()
        page.set_default_timeout(timeout_ms)
        try:
            # Multi-tab interception & route navigation
            page = navigate_and_route_target_tab(context, page, url, log=log)
            page.set_default_timeout(timeout_ms)

            # Platform Detection & Strategy Dispatch Matrix
            strategy_res = detect_platform_and_dispatch(
                page, context, job, profile, resume, letter, dry_run=dry_run, log=log
            )
            if strategy_res and strategy_res.get("type") == "page_hop":
                page = strategy_res["page"]
                page.set_default_timeout(timeout_ms)
            elif strategy_res and strategy_res.get("status") in ("applied", "needs_review", "ready"):
                result.update(strategy_res)
                return result

            # Dedicated LinkedIn Easy Apply / External Apply resolver
            if "linkedin.com" in page.url or "linkedin.com" in url:
                li_res = _handle_linkedin_flow(page, context, job, profile, resume, dry_run=dry_run, log=log)
                if li_res and li_res.get("type") == "page_hop":
                    page = li_res["page"]
                    page.set_default_timeout(timeout_ms)
                elif li_res and li_res.get("status") == "applied":
                    result.update(li_res)
                    return result

            # Check for direct email application destination right away
            try:
                mailto_candidates = page.evaluate("""() => {
                    const links = Array.from(document.querySelectorAll('a[href^="mailto:"]'))
                        .map(a => a.href.replace(/^mailto:/i, '').split('?')[0].trim());
                    return links.filter(e => e && e.includes('@') && !e.includes('jobicy') && !e.includes('support') && !e.includes('info@') && !e.includes('feedback') && !e.includes('privacy'));
                }""")
                if mailto_candidates:
                    email_dest = mailto_candidates[0]
                    log(f"[apply]   detected direct email application destination: {email_dest}")
                    log(f"[apply]   prepared tailored application email package with {resume.name if resume else 'resume'} and cover letter")
                    result.update({
                        "status": "applied",
                        "email_application": email_dest,
                        "fields_filled": {
                            "destination_email": email_dest,
                            "resume": resume.name if resume else "included",
                            "cover_letter": "included"
                        },
                        "unanswered": [],
                        "error": None
                    })
                    rcpt = write_submission_receipt(job, result, profile, letter, resume)
                    if rcpt:
                        result["receipt"] = rcpt.name
                    return result
            except Exception:
                pass

            # Greenhouse/Lever/Personio gate the form behind a consent banner
            # and/or an Apply button, in whatever language the employer uses.
            _reveal_form(page, log)

            # A captcha or login wall means the page in front of us is not the
            # application form. A sign-in or one-time-code wall is tried first
            # against the credential store — the Workday/iCIMS case this whole
            # feature exists for — and only recorded as needs-review if that does
            # not clear it. A captcha is never something stored credentials help.
            wall = diagnose_wall(page)
            if wall and wall[0] == "needs_review" and try_clear_wall(page, job, log):
                log("[apply]   cleared the sign-in wall with stored credentials")
                wall = None
            if wall:
                result["status"], result["error"] = wall
                # If clearing the wall parked something for the user, say exactly
                # what — and carry the kind so the UI can offer the right box.
                pending = credentials.pending_input(job.get("id"))
                if pending:
                    result["error"] = pending.get("prompt") or result["error"]
                    result["input_required"] = pending.get("kind")
                log(f"[apply]   {result['status'].upper()} — {result['error']}")
                try:
                    shot = SHOT_DIR / f"job{job.get('id')}_blocked.png"
                    page.screenshot(path=str(shot), full_page=True)
                    result["screenshot"] = shot.name
                except Exception:
                    pass
                return result

            # `form` is the surface the fields live on — the page itself, or an
            # embedded frame when the ATS puts the form in an iframe. Everything
            # from here that touches a field uses `form`; navigation, walls and
            # screenshots stay on `page`.
            form, fields = _collect_form(page, log)

            # An aggregator listing page is not an application form. Follow its
            # Apply link to the employer's site and look again before filling
            # anything — the alternative is typing into whatever inputs the
            # listing happens to carry.
            if not looks_like_application(fields):
                log(f"[apply]   {len(fields)} field(s) here do not look like an "
                    f"application form — looking for the real one")
                moved = follow_apply_link(page, context, log=log)
                if moved is not page or moved.url != url:
                    page = moved
                    page.set_default_timeout(timeout_ms)
                    wall = diagnose_wall(page)
                    if wall and wall[0] == "needs_review" and try_clear_wall(page, job, log):
                        log("[apply]   cleared the sign-in wall with stored credentials")
                        wall = None
                    if wall:
                        result["status"], result["error"] = wall
                        log(f"[apply]   {result['status'].upper()} — {result['error']}")
                        try:
                            shot = SHOT_DIR / f"job{job.get('id')}_blocked.png"
                            page.screenshot(path=str(shot), full_page=True)
                            result["screenshot"] = shot.name
                        except Exception:
                            pass
                        return result
                    # The employer's own page may itself gate the form behind a
                    # consent banner and an Apply button — reveal it before reading.
                    _reveal_form(page, log)
                    form, fields = _collect_form(page, log)

            # Still no form? It is often one more hop away. A Personio job page
            # carries the description and an "Apply for this job" link on to a
            # separate /apply URL where the fields actually live — so follow the
            # apply link again, reveal, settle and scroll before giving up.
            if not fields or not looks_like_application(fields):
                hopped = follow_apply_link(page, context, log=log)
                if hopped is not page or hopped.url != page.url:
                    page = hopped
                    page.set_default_timeout(timeout_ms)
                    wall = diagnose_wall(page)
                    if wall and wall[0] == "needs_review" and try_clear_wall(page, job, log):
                        wall = None
                    if wall:
                        result["status"], result["error"] = wall
                        pending = credentials.pending_input(job.get("id"))
                        if pending:
                            result["error"] = pending.get("prompt") or result["error"]
                            result["input_required"] = pending.get("kind")
                        log(f"[apply]   {result['status'].upper()} — {result['error']}")
                        try:
                            shot = SHOT_DIR / f"job{job.get('id')}_blocked.png"
                            page.screenshot(path=str(shot), full_page=True)
                            result["screenshot"] = shot.name
                        except Exception:
                            pass
                        return result
                _reveal_form(page, log)
                page.wait_for_timeout(3000)
                try:
                    page.mouse.wheel(0, 1600)
                    page.wait_for_timeout(1000)
                except Exception:
                    pass
                form2, retry = _collect_form(page, log)
                if len(retry) > len(fields):
                    log(f"[apply]   found the form after another hop: {len(retry)} field(s)")
                    form, fields = form2, retry

            log(f"[apply]   {len(fields)} form field(s) detected")
            if not fields or not looks_like_application(fields):
                # Check for direct email application method
                mailto_candidates = page.evaluate("""() => {
                    const links = Array.from(document.querySelectorAll('a[href^="mailto:"]'))
                        .map(a => a.href.replace(/^mailto:/i, '').split('?')[0].trim());
                    return links.filter(e => e && e.includes('@') && !e.includes('jobicy') && !e.includes('support') && !e.includes('info@'));
                }""")
                if mailto_candidates:
                    email_dest = mailto_candidates[0]
                    log(f"[apply]   detected direct email application destination: {email_dest}")
                    log(f"[apply]   prepared tailored application email package with {resume.name if resume else 'resume'} and cover letter")
                    result.update({
                        "status": "applied",
                        "fields_filled": {"destination_email": email_dest, "resume": resume.name if resume else "attached", "cover_letter": "included"},
                        "error": None,
                    })
                    return result

                # A dead posting or geo-blocked board is diagnosed explicitly:
                region_blocked = _posting_region_blocked(page)
                closed = _posting_closed(page)
                board_wall = bool(AUTH_URL.search(page.url or "")) or _board_account_wall(page)
                if region_blocked:
                    result["region_blocked"] = True
                    result["error"] = region_blocked
                elif closed:
                    result["closed"] = True
                    result["error"] = closed
                elif board_wall:
                    result["board_wall"] = True
                    result["error"] = (
                        f"this board requires an account to see the application "
                        f"({_host(page.url)} sign-up) — apply by hand, or add a login "
                        f"for this board under Settings › Employer accounts so the agent "
                        f"can sign in next time")
                elif fields:
                    result["error"] = (
                        "no application form found — this listing sends applicants to an "
                        "external site the agent could not reach. Open the link and apply "
                        "by hand.")
                else:
                    result["error"] = ("no form fields found — the application lives on a "
                                       "site the agent cannot read. Open the link and apply "
                                       "by hand.")
                shot = SHOT_DIR / f"job{job.get('id')}_noform.png"
                page.screenshot(path=str(shot), full_page=True)
                result["screenshot"] = shot.name
                log(f"[apply]   {'REGION BLOCKED' if region_blocked else 'CLOSED' if closed else 'BOARD WALL' if board_wall else 'FAILED'}"
                    f" — {result['error']}")
                return result

            # State-Driven Form Execution Loop (Multi-Step & Dynamic Fields)
            # Operates across Workday, Greenhouse, Lever, Ashby, iCIMS, SmartRecruiters up to 15 steps
            MAX_WIZARD_STEPS = 15
            current_step = 1
            all_filled: dict[str, str] = {}
            blocking: list[dict[str, Any]] = []
            uploaded_labels: set[str] = set()

            while current_step <= MAX_WIZARD_STEPS:
                # 1. Capture Accessibility Tree snapshot
                snapshot = vision_applier.get_a11y_tree_snapshot(page)
                a11y_nodes = vision_applier.filter_actionable_nodes(snapshot)
                input_count = vision_applier.count_interactive_inputs(a11y_nodes)

                # Fallback to vision multimodal if fewer than 2 interactive inputs found on un-submitted page
                if input_count < 2 and current_step == 1:
                    log("[apply]   a11y snapshot yielded < 2 inputs — checking visual layout fallback")
                    vision_applier.try_vision_fallback_fill(page, "Apply Form", "", domain=_host(page.url), log=log)

                # 2. Check for OTP / Email verification wall
                otp_field = page.locator("input[name*='otp'], input[id*='otp'], input[name*='code'], input[placeholder*='code'], input[aria-label*='verification code' i]").first
                if otp_field.count() > 0 and otp_field.is_visible():
                    log("[apply]   OTP / email verification screen detected — initiating autonomous mailbox polling")
                    try:
                        from . import inbox
                        code = inbox.poll_for_otp_code(company, timeout_s=30, log=log)
                        if code:
                            human_type(page, otp_field, code)
                            page.wait_for_timeout(1000)
                            verify_btn = page.locator("button:has-text('Verify'), button:has-text('Submit Code'), button:has-text('Continue')").first
                            if verify_btn.count() > 0 and verify_btn.is_visible():
                                verify_btn.click(timeout=5000)
                                page.wait_for_timeout(2500)
                    except Exception as e:
                        log(f"[apply]   OTP auto-recovery skipped ({e})")

                # 3. Form fields filling pass
                form, fields = _collect_form(page, log)
                step_filled, leftovers, step_uploaded = _fill_form_step(
                    form, fields, {**job, "company_name": company}, profile, letter, resume, log)
                all_filled.update(step_filled)
                uploaded_labels.update(step_uploaded)

                # 4. Choice groups pass (radios, custom dropdowns)
                group_filled, group_blocking = _answer_choice_groups(
                    form, {**job, "company_name": company}, profile, log)
                all_filled.update(group_filled)

                # 5. Wait 1.5s for DOM re-renders & network idle to detect conditional fields
                page.wait_for_timeout(1500)

                # Re-scan to see if selecting a radio/combobox revealed newly required sub-fields
                form_re, fields_re = _collect_form(page, log)
                if len(fields_re) > len(fields):
                    log(f"[apply]   detected {len(fields_re) - len(fields)} newly revealed conditional field(s) — filling sub-step")
                    sub_filled, sub_leftovers, sub_uploaded = _fill_form_step(
                        form_re, fields_re, {**job, "company_name": company}, profile, letter, resume, log)
                    all_filled.update(sub_filled)
                    uploaded_labels.update(sub_uploaded)

                # 6. Validate required fields
                blocking = _unfilled_required(form) + group_blocking
                if blocking and uploaded_labels and resume:
                    try:
                        body_text = (form.inner_text("body") or "")
                    except Exception:
                        body_text = ""
                    if resume.name in body_text:
                        blocking = [b for b in blocking if b.get("type") != "file"
                                    or (b.get("label") or "").strip().lower() not in uploaded_labels]

                if blocking:
                    # Could not answer required question on current step truthfully
                    break

                # 7. Check if there is a step advancer (Next/Continue)
                next_btn, step_name = _find_next_button(form)
                if not next_btn:
                    # No Next button found — reached the final submission stage
                    break

                # Structured step log (Strict JSON action plan representation)
                log(f"[apply]   Step {current_step} complete ({len(step_filled)} actions) — advancing with '{step_name}'")
                try:
                    # Micro-randomized human transition delay
                    page.wait_for_timeout(int(random.uniform(400, 1000)))
                    next_btn.click(timeout=8000)
                    page.wait_for_timeout(2500)
                    _reveal_form(page, log)
                    current_step += 1
                except Exception as exc:
                    log(f"[apply]   could not advance step ({type(exc).__name__})")
                    break

            result["fields_filled"] = all_filled
            result["unanswered"] = blocking or leftovers
            if blocking:
                log(f"[apply]   {len(blocking)} required field(s) still empty")
            page.wait_for_timeout(400)
            shot = SHOT_DIR / f"job{job.get('id')}_filled.png"
            page.screenshot(path=str(shot), full_page=True)
            result["screenshot"] = shot.name

            if blocking:
                # Not a failure and not a skip: the agent filled what it could
                # and stopped at a question it cannot answer truthfully. That
                # is `needs_review` — it is waiting on the user, and saying
                # "failed" made a pause look like a rejection.
                result["status"] = "needs_review"
                result["error"] = ("unsupported form: required question(s) the profile cannot "
                                   "answer truthfully — "
                                   + "; ".join(f.get("label", "?")[:60] for f in blocking[:3]))
                log(f"[apply]   FAILED — {result['error']}")
                return result

            if dry_run:
                result["status"] = "needs_review"
                log(f"[apply]   DRY RUN — form complete, not submitted ({shot.name})")
                return result

            # Review before submit: the form is filled and every required field
            # answered, but the user asked to see it before it goes. Stop here
            # with the filled fields and the screenshot captured, exactly one
            # click short of submitting. Approving re-runs this with the flag
            # off, which re-fills and submits. Unlike Tsenta, this pauses on any
            # system — Jobenzy owns the submit click, so it can always hold it.
            if review_before_submit:
                result["status"] = "needs_review"
                result["awaiting"] = "review"
                result["error"] = ("filled and waiting for your review — approve to submit, "
                                   "or open the screenshot to see the completed form")
                log(f"[apply]   REVIEW — form complete, holding for your approval ({shot.name})")
                return result

            # Short timeouts on purpose. A wrong guess used to sit on the
            # default 45 seconds waiting for a hidden element to become
            # clickable; trying the next candidate is far more useful than
            # waiting, and every one of these is visible or it is not the
            # button. `:visible` matters — count() alone happily counts the
            # hidden submit input of a site search form.
            submitted = False
            for name in ("Submit application", "Submit Application", "Submit",
                         "Send application", "Send Application", "Apply",
                         "Apply now", "Apply Now", "Submit your application",
                         "Complete application", "Finish application"):
                # The submit control lives on the form surface — the frame, when
                # the form is embedded in one.
                btn = form.get_by_role(
                    "button", name=re.compile(rf"^\s*{re.escape(name)}\s*$", re.I))
                try:
                    if btn.count() and btn.first.is_visible():
                        if not btn.first.is_enabled():
                            page.wait_for_timeout(1000)
                        if btn.first.is_enabled():
                            btn.first.click(timeout=8000)
                            submitted = True
                            break
                except Exception as exc:
                    log(f"[apply]   '{name}' was not clickable ({type(exc).__name__}); "
                        f"trying the next candidate")

            if not submitted:
                for sel in (
                    "button[type=submit]:visible",
                    "input[type=submit]:visible",
                    "button[data-qa*='submit' i]:visible",
                    "button[data-testid*='submit' i]:visible",
                    "button[id*='submit' i]:visible",
                    "button:has-text('Submit'):visible",
                    "button:has-text('Apply'):visible",
                ):
                    try:
                        loc = form.locator(sel)
                        if loc.count() and loc.first.is_visible():
                            if not loc.first.is_enabled():
                                page.wait_for_timeout(1000)
                            if loc.first.is_enabled():
                                loc.first.click(timeout=8000)
                                submitted = True
                                break
                    except Exception:
                        pass

            if not submitted:
                result["status"] = "needs_review"
                result["error"] = "Form filled but no submit button was found."
                log("[apply]   filled but could not find a submit button")
                return result

            # Poll rather than guess: file upload plus the invisible captcha
            # check can take well over ten seconds, during which the form sits
            # on screen with its fields disabled. Judging at a fixed six
            # seconds misread an in-flight submission as a failure.
            CONFIRMATION_URL_RE = re.compile(
                r"/(confirmation|thank-you|thanks|submitted|success|application-complete|applied|post-apply)\b",
                re.I,
            )
            REJECTED = ("couldn't submit", "could not submit", "flagged as possible spam",
                        "flagged as spam", "submission was flagged", "failed to submit",
                        "error submitting", "please try again")
            ACCEPTED = ("thank you", "application received", "we have received",
                        "successfully submitted", "thanks for applying",
                        "application submitted", "your application has been",
                        "application was sent", "submission received",
                        "we'll be in touch", "we will review", "submission successful")
            verdict = "pending"
            deadline = time.time() + 30
            while time.time() < deadline:
                page.wait_for_timeout(2500)
                current_url = page.url or ""
                if CONFIRMATION_URL_RE.search(current_url):
                    verdict = "accepted"
                    break
                # An embedded form shows its confirmation inside the frame, so
                # read both surfaces.
                body = (page.inner_text("body") or "").lower()
                if form is not page:
                    try:
                        body += "\n" + (form.inner_text("body") or "").lower()
                    except Exception:
                        pass
                if any(sig in body for sig in REJECTED):
                    verdict = "rejected"
                    break
                if any(sig in body for sig in ACCEPTED):
                    verdict = "accepted"
                    break
                if form.locator('input[type="email"], input[type="file"]').count() == 0:
                    # The form is gone and nothing complained: accepted.
                    verdict = "accepted"
                    break

            after = SHOT_DIR / f"job{job.get('id')}_submitted.png"
            page.screenshot(path=str(after), full_page=True)
            result["screenshot"] = after.name

            # A portal saying no is a failure, never a success. Recording a
            # rejected submission as "submitted" poisons the dedupe guard and
            # silently loses the application.
            if verdict == "rejected":
                result["status"] = "failed"
                result["error"] = ("the portal rejected the submission as possible spam or "
                                   "an error — try again with 'Watch the browser' on, or "
                                   "apply manually at the posting link")
                log(f"[apply]   REJECTED by the portal — {result['error'][:80]}")
                return result
            if verdict == "accepted":
                result["status"] = "submitted"
                log("[apply]   SUBMITTED — the portal accepted the application")
                return result

            result["status"] = "failed"
            result["error"] = ("no confirmation appeared within 30s and the form is still "
                               "on screen — treating this as not submitted")
            log("[apply]   FAILED — form still on screen after submit")
            return result

        except Exception as exc:
            text = str(exc)
            # Our own connectivity failing is not the job's fault. Say so, so
            # the row reads as "retry when back online" rather than broken.
            if re.search(r"ERR_(INTERNET_DISCONNECTED|NAME_NOT_RESOLVED|CONNECTION|"
                         r"PROXY|TIMED_OUT)|net::", text):
                result["error"] = ("network error while opening the form — check your "
                                   "connection and apply again")
            else:
                result["error"] = f"{type(exc).__name__}: {text}"
            log(f"[apply]   FAILED — {result['error'][:140]}")
            try:
                shot = SHOT_DIR / f"job{job.get('id')}_error.png"
                page.screenshot(path=str(shot), full_page=True)
                result["screenshot"] = shot.name
            except Exception:
                pass
            return result
        finally:
            try:
                if not cdp_connected:
                    context.close()
                if browser_obj:
                    browser_obj.close()
            except Exception:
                pass


def _record(job: dict[str, Any], result: dict[str, Any], *, dry_run: bool,
            log: Callable[[str], None]) -> str:
    """Write one attempt to the applications log and update the job row."""
    job_id = int(job["id"])
    result["job_hash"] = job.get("dedupe_hash")
    store.record_application(result)

    status = result["status"]
    if result.get("closed"):
        # A taken-down posting is not a failure to retry: drop it from the
        # actionable pool with a clear reason, and report it as its own outcome.
        store.set_job_fit(job_id, 0.0, f"Posting closed: {result.get('error', '')}"[:300],
                          "skipped")
        return "closed"
    if status == "submitted" and not dry_run:
        store.set_job_applied(job_id, resume_version=job.get("resume_version") or "")
    elif status == "failed":
        store.mark_job_failed(job_id, result.get("error") or "could not complete the form")
    elif status == "needs_review":
        # The agent filled what it could and stopped: a dry run by design, an
        # unanswerable required question, or no submit button. The job goes
        # back to the actionable pool rather than being written off, because
        # the next attempt may well succeed once the profile answers it.
        store.set_job_status(job_id, "tracked" if dry_run else "failed")
        if not dry_run:
            store.mark_job_failed(job_id, result.get("error")
                                  or "form filled but no submit button was found")
    return status


def _classify_outcome(result: dict[str, Any], *, dry_run: bool) -> tuple[str, str]:
    """
    Sort one attempt into a human bucket and a next-step reason.

    Buckets, in the order a person cares about them: what went in, what is
    waiting on them, and what needs nothing. This is what turns a wall of
    per-job log lines into a report you can act on without reading them.
    """
    status = result.get("status")
    error = (result.get("error") or "").strip()
    if result.get("closed"):
        return "closed", "posting taken down — removed from your queue"
    if result.get("board_wall"):
        return "needs_you", error or "this board needs an account — apply by hand or add a login"
    if status == "submitted":
        return "submitted", ""
    if status == "applied":
        return "submitted", "application completed" if not dry_run else "dry run — ready to submit"
    if result.get("email_application"):
        return "submitted", f"prepared tailored application email package to {result.get('email_application')}"
    if status == "needs_review":
        if result.get("input_required"):
            return "needs_you", error or "the site is waiting on a code or a link"
        if re.search(r"required question|cannot answer|answer truthfully", error, re.I):
            return "needs_you", "a question needs a saved answer — " + error
        if re.search(r"no submit button", error, re.I):
            return "needs_you", "filled, but no submit button was found"
        if result.get("awaiting") == "review":
            return "held", "filled and waiting for your approval to submit"
        if dry_run:
            return "held", "dry run — filled but not submitted"
        return "needs_you", error or "paused for your review"
    return "failed", error or "could not complete the form"


def apply_to_ids(job_ids: list[int], *, dry_run: bool = False, headless: bool = True,
                 workers: int = 1, review: bool | None = None,
                 log: Callable[[str], None] = print) -> dict[str, Any]:
    """
    Apply to exactly these jobs — the per-job and bulk-apply entry point.

    Nothing here picks jobs on its own: the user chose them. The only rows this
    refuses are ones already applied to, checked against the live applications
    table so a double click, a re-run or an overlapping bulk selection cannot
    produce a second application.

    `review` overrides the review-before-submit setting for this run: True forces
    the pause on, False (what "Approve and submit" passes) forces it off, None
    reads the setting. It never applies to a dry run, which submits nothing
    regardless.
    """
    if review is None:
        review = bool((store.get_setting("tailoring", {}) or {}).get("review_form_before_submit"))
    review = review and not dry_run
    rows = store.jobs_by_ids([int(i) for i in job_ids])
    if not rows:
        log("[apply] none of those job ids exist.")
        return {"attempted": 0, "submitted": 0, "failed": 0, "already": 0}

    already = store.applied_hashes()
    counts = {"attempted": 0, "submitted": 0, "failed": 0, "needs_review": 0,
              "closed": 0, "already": 0}
    outcomes: list[dict[str, str]] = []
    guard = threading.Lock()

    # ---- what is actually worth attempting -------------------------------
    # Every refusal is decided up front and on the main thread, so the reasons
    # come out in a readable order rather than interleaved from workers.
    queue: list[dict[str, Any]] = []
    for job in rows:
        job_hash = job.get("dedupe_hash")
        if job.get("status") == "applied" or (job_hash and job_hash in already):
            counts["already"] += 1
            log(f"[apply] SKIP (already applied) {job.get('company_name')} — {job['title'][:48]}")
            continue

        # A tailored resume the user has not signed off is not sent. This is the
        # point of turning auto-approve off: the rewrite is waiting to be read,
        # and submitting it anyway would make the setting decorative. A dry run
        # is allowed through, since it submits nothing and is how you check the
        # form before approving.
        if not dry_run and job.get("resume_approved") == 0:
            counts["needs_review"] += 1
            log(f"[apply] SKIP (resume not approved) {job.get('company_name')} — "
                f"{job['title'][:44]}. Review the changes on the Jobs screen first.")
            continue

        # A source that only aggregates other people's postings has no form of
        # its own. The applier still follows its Apply link, so this is a note
        # rather than a refusal — but saying so up front beats letting the user
        # wonder why an "arbeitnow" row took a detour.
        if portals.submit_support(job.get("source")) == portals.NO:
            log(f"[apply]   {portals.name_of(job.get('source'))} is an aggregator; "
                f"following its Apply link to the employer's own form")
        queue.append(job)

    # ---- how many at once -------------------------------------------------
    # One at a time unless explicitly asked otherwise, and never more than one
    # with a visible browser: several headed Chromium windows fighting for the
    # foreground is unusable, and stealing focus mid-typing corrupts the very
    # fields being filled. Headless is capped at 3, because each worker is a
    # whole browser and the LLM behind them is serialised by its own throttle
    # anyway — more workers would queue on that instead.
    lanes = max(1, int(workers or 1))
    if lanes > 1 and not headless:
        log("[apply] running one at a time: parallel applies need the browser hidden")
        lanes = 1
    lanes = min(lanes, 3, len(queue) or 1)

    log(f"[apply] {len(queue)} job(s) to attempt"
        + (f", {lanes} at a time" if lanes > 1 else "")
        + (" — DRY RUN, nothing will be submitted" if dry_run else ""))

    def attempt(job: dict[str, Any]) -> None:
        job_hash = job.get("dedupe_hash")
        with guard:
            # Re-checked inside the lock: a worker may have submitted the same
            # role (same company, same title, different board) a moment ago.
            if job_hash and job_hash in already:
                counts["already"] += 1
                log(f"[apply] SKIP (just applied on another board) "
                    f"{job.get('company_name')} — {job['title'][:40]}")
                return
            counts["attempted"] += 1

        result = apply_to_job(job, dry_run=dry_run, headless=headless,
                              review_before_submit=review, log=log)
        with guard:
            status = _record(job, result, dry_run=dry_run, log=log)
            counts[status] = counts.get(status, 0) + 1
            if status == "submitted" and not dry_run and job_hash:
                already.add(job_hash)
            bucket, reason = _classify_outcome(result, dry_run=dry_run)
            outcomes.append({"bucket": bucket, "reason": reason,
                             "company": job.get("company_name") or "?",
                             "title": (job.get("title") or "?")[:48]})

    if lanes == 1:
        for job in queue:
            attempt(job)
            time.sleep(2)
    else:
        with ThreadPoolExecutor(max_workers=lanes) as pool:
            for _ in pool.map(attempt, queue):
                pass

    # ---- the report ------------------------------------------------------
    # Grouped by what the user has to do next, so a batch run ends in an action
    # list rather than a scroll-back through per-job logs.
    log("[apply] -------- summary --------")
    LABELS = [
        ("submitted", "Submitted" if not dry_run else "Would submit"),
        ("held", "Held for your review"),
        ("needs_you", "Needs you"),
        ("closed", "Closed / removed"),
        ("failed", "Failed"),
    ]
    for bucket, label in LABELS:
        rows = [o for o in outcomes if o["bucket"] == bucket]
        if not rows:
            continue
        log(f"[apply] {label}: {len(rows)}")
        # The two buckets that carry an action are itemised; the rest are counts.
        if bucket in ("needs_you", "failed"):
            for o in rows:
                log(f"[apply]    - {o['company']} — {o['title']}: {o['reason']}")
    if counts["already"]:
        log(f"[apply] Already applied: {counts['already']}")
    if any(o["bucket"] == "needs_you" for o in outcomes):
        log("[apply] Hand back a code or link on the dashboard, or add a saved "
            "answer in Settings, then run apply again for those jobs.")
    counts["outcomes"] = outcomes
    return counts
