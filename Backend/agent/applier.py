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
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from api.config import DASHBOARD_OUT
from api import behuman

from . import llm, matcher, portals, store

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
    (re.compile(r"sponsor|visa|work\s*permit", re.I), "requires_sponsorship"),
    (re.compile(r"authori[sz]ed|legally.*work|right\s*to\s*work|eligible.*work", re.I), "work_authorization"),
    (re.compile(r"relocat", re.I), "willing_to_relocate"),
    (re.compile(r"pronoun", re.I), "pronouns"),
    (re.compile(r"how.*(hear|find).*(us|role|position)|referral\s*source", re.I), "how_did_you_hear"),
    (re.compile(r"why.*(join|company|us|interested)|cover\s*letter|motivat", re.I), "_cover_letter"),
]

# Walls the agent cannot get past. Detected explicitly so the job is recorded as
# a failure with a reason the user can act on, rather than disappearing.
LOGIN_MARKERS = re.compile(
    r"\b(sign in to (?:apply|continue)|log ?in to (?:apply|continue)|"
    r"create an account to apply|please (?:sign|log) ?in|"
    r"you must be logged in|register to apply)\b", re.I)


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


# Yes/No toggle groups (Ashby renders required screening questions this way —
# as <button> pairs, not radio inputs, so input-based collection never sees
# them). The script tags each group's buttons so Python can click by group id.
CHOICE_GROUPS_JS = """() => {
  const yn = ['Yes', 'No'];
  const seen = new Set(); const out = []; let gi = 0;
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

    # Rules answer the common questions without a model call; the LLM handles
    # the rest with the same "only if the profile supports it" contract.
    need_llm = []
    answers: dict[int, str] = {}
    for g in pending:
        ans = _choice_rule_answer(g["question"], profile)
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
            btn = page.locator(f'button[data-agent-choice="{g["i"]}"]').filter(
                has_text=re.compile(rf"^\s*{ans}\s*$", re.I))
            btn.first.click(timeout=6000)
            filled[g["question"][:70]] = ans
            log(f"[apply]   {ans} -> {g['question'][:62]}")
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
    r"^\s*(apply(\s+(now|here|for this (job|role|position)|on .{0,30})?)?|"
    r"i'?m interested|submit application|go to application)\s*$", re.I)


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


def follow_apply_link(page, context, *, log: Callable[[str], None] = print):
    """
    Click through to the real application and return the page showing it.

    Handles the three shapes these links take: a same-tab navigation, a
    `target=_blank` popup, and an anchor whose href is the employer's site.
    Returns the original page unchanged when there is nothing to follow.
    """
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

    # Nothing clickable: fall back to the href of an apply-ish anchor.
    try:
        href = page.evaluate(
            """(pattern) => {
              const re = new RegExp(pattern, 'i');
              const a = Array.from(document.querySelectorAll('a[href]'))
                .find(x => re.test((x.innerText || '').trim()));
              return a ? a.href : '';
            }""", APPLY_LINK_TEXT.pattern)
    except Exception:
        href = ""
    if href and href != page.url:
        try:
            page.goto(href, wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(2000)
            log(f"[apply]   followed Apply link to {page.url[:90]}")
            return page
        except Exception:
            pass
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
                      .replace(/\\s+/g, ' ').trim();

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
        # intl-tel-input parses as it goes and drops what it cannot read.
        # "+92 301 8165385" loses its spaces or the whole entry; the compact
        # E.164 form is what it accepts, and the plus keeps the country right.
        digits = re.sub(r"[^\d+]", "", value or "")
        value = digits if digits else value

    if not must_type:
        try:
            field.fill(value, timeout=8000)
            if (field.input_value(timeout=2000) or "").strip():
                return True
        except Exception:
            pass

    try:
        field.click(timeout=5000)
        field.type(value, delay=35, timeout=15000)
        page.wait_for_timeout(1200)
        if picks_suggestion:
            if _pick_suggestion(page, field, value):
                return True
            # Enter accepts the highlighted option in a combobox. It is not
            # pressed on ordinary fields, where it would submit the form.
            field.press("Enter", timeout=4000)
            page.wait_for_timeout(400)
        if (field.input_value(timeout=2000) or "").strip():
            return True
        # A widget that stores its value out of sight (the phone box does)
        # reads back empty even when the form is perfectly happy. Ask the
        # form, not the input.
        return _field_satisfied(field)
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
    try:
        _handle(page, idx).select_option(label=opt, timeout=5000)
        return opt
    except Exception:
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


def apply_to_job(job: dict[str, Any], *, dry_run: bool = False, headless: bool = True,
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

    with sync_playwright() as p:
        # Anti-bot scorers (Ashby runs invisible reCAPTCHA on submit) rate a
        # stock headless browser as spam. Strip the obvious automation tells:
        # the AutomationControlled blink feature sets navigator.webdriver, and
        # a context with no languages/plugins reads as a script.
        browser = p.chromium.launch(headless=headless, args=[
            "--disable-blink-features=AutomationControlled",
        ])
        context = browser.new_context(
            viewport={"width": 1440, "height": 1000},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            locale="en-US",
            timezone_id="Asia/Karachi",
            accept_downloads=False,
        )
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            "window.chrome = window.chrome || {runtime: {}};"
            "Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});"
            "Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3]});"
        )
        page = context.new_page()
        page.set_default_timeout(timeout_ms)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(2500)

            # Greenhouse/Lever often gate the form behind an "Apply" button.
            for label in ("Apply for this job", "Apply now", "Apply", "I'm interested"):
                btn = page.get_by_role("button", name=re.compile(rf"^\s*{re.escape(label)}\s*$", re.I))
                if btn.count() and btn.first.is_visible():
                    btn.first.click()
                    page.wait_for_timeout(2000)
                    break

            # A captcha or login wall means the page in front of us is not the
            # application form. Recorded as a failure with the reason, never
            # skipped silently.
            wall = diagnose_wall(page)
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

            fields = _collect_fields(page)

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
                    fields = _collect_fields(page)

            log(f"[apply]   {len(fields)} form field(s) detected")
            if not fields or not looks_like_application(fields):
                result["error"] = (
                    "no application form found — this listing sends applicants to an "
                    "external site the agent could not reach. Open the link and apply "
                    "by hand." if fields else
                    "no form fields found — the posting is closed, or the application "
                    "lives on a site the agent cannot read")
                shot = SHOT_DIR / f"job{job.get('id')}_noform.png"
                page.screenshot(path=str(shot), full_page=True)
                result["screenshot"] = shot.name
                log(f"[apply]   FAILED — {result['error']}")
                return result

            filled: dict[str, str] = {}
            leftovers: list[dict[str, Any]] = []
            uploaded_labels: set[str] = set()

            # Pass 1 — rules
            file_fields = [f for f in fields if f["type"] == "file"]
            for f in fields:
                label = f["label"] or f["name"]
                key = _match_rule(label)
                if f["type"] == "file":
                    # The resume goes into the field that asks for one — or the
                    # only file field on the form. A second slot is usually the
                    # cover letter or "additional files", and stuffing the
                    # resume in there reads as carelessness to a recruiter.
                    wants_resume = bool(re.search(r"resume|résumé|\bcv\b", label or "", re.I))
                    if resume and resume.is_file() and (wants_resume or len(file_fields) == 1):
                        try:
                            _handle(page, f["idx"]).set_input_files(str(resume), timeout=15000)
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
                        chosen = _fill_select(page, f["idx"], value, f["options"])
                        if chosen:
                            filled[label] = chosen
                        else:
                            leftovers.append(f)
                    elif f["type"] in ("checkbox", "radio"):
                        leftovers.append(f)
                    elif _fill_text(page, f["idx"], value):
                        filled[label] = value[:120]
                    else:
                        leftovers.append(f)
                except Exception:
                    leftovers.append(f)

            log(f"[apply]   {len(filled)} field(s) from profile rules, {len(leftovers)} to reason about")

            # Pass 2 — LLM for whatever is left
            if leftovers:
                answers = _llm_answers(leftovers, {**job, "company_name": company},
                                       profile, letter, log)
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
                            chosen = _fill_select(page, f["idx"], value, f["options"])
                            if chosen:
                                filled[f["label"]] = chosen
                            else:
                                still.append({"label": f["label"], "required": f["required"],
                                              "type": f["type"], "reason": "no matching option"})
                        elif f["type"] == "checkbox":
                            if value.lower() in ("yes", "true", "on", "agree", "accept", "1"):
                                _handle(page, f["idx"]).check(timeout=6000)
                                filled[f["label"]] = "checked"
                        elif f["type"] == "radio":
                            _handle(page, f["idx"]).check(timeout=6000)
                            filled[f["label"]] = value[:80]
                        elif _fill_text(page, f["idx"], value):
                            filled[f["label"]] = value[:120]
                        else:
                            still.append({"label": f["label"], "required": f["required"],
                                          "type": f["type"], "reason": "value did not stick"})
                    except Exception:
                        still.append({"label": f["label"], "required": f["required"],
                                      "type": f["type"], "reason": "could not set value"})
                leftovers = still

            # Pass 3 — Yes/No button groups (screening questions that are not
            # <input> elements at all, so passes 1 and 2 cannot see them).
            group_filled, group_blocking = _answer_choice_groups(
                page, {**job, "company_name": company}, profile, log)
            filled.update(group_filled)

            result["fields_filled"] = filled

            page.wait_for_timeout(600)
            blocking = _unfilled_required(page) + group_blocking
            # React upload widgets (Ashby among them) read the file into their
            # own state and clear the <input>, so `el.files` is empty again even
            # though the upload took. If the page now shows our filename — the
            # chip these widgets render — the requirement is met.
            if blocking and uploaded_labels and resume:
                try:
                    body_text = (page.inner_text("body") or "")
                except Exception:
                    body_text = ""
                if resume.name in body_text:
                    blocking = [b for b in blocking if b.get("type") != "file"
                                or (b.get("label") or "").strip().lower() not in uploaded_labels]
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

            # Short timeouts on purpose. A wrong guess used to sit on the
            # default 45 seconds waiting for a hidden element to become
            # clickable; trying the next candidate is far more useful than
            # waiting, and every one of these is visible or it is not the
            # button. `:visible` matters — count() alone happily counts the
            # hidden submit input of a site search form.
            submitted = False
            for name in ("Submit application", "Submit Application", "Submit",
                         "Send application", "Apply"):
                btn = page.get_by_role(
                    "button", name=re.compile(rf"^\s*{re.escape(name)}\s*$", re.I))
                try:
                    if btn.count() and btn.first.is_visible() and btn.first.is_enabled():
                        btn.first.click(timeout=8000)
                        submitted = True
                        break
                except Exception as exc:
                    log(f"[apply]   '{name}' was not clickable ({type(exc).__name__}); "
                        f"trying the next candidate")
            if not submitted:
                inp = page.locator("input[type=submit]:visible")
                try:
                    if inp.count():
                        inp.first.click(timeout=8000)
                        submitted = True
                except Exception as exc:
                    log(f"[apply]   submit input was not clickable ({type(exc).__name__})")

            if not submitted:
                result["status"] = "needs_review"
                result["error"] = "Form filled but no submit button was found."
                log("[apply]   filled but could not find a submit button")
                return result

            # Poll rather than guess: file upload plus the invisible captcha
            # check can take well over ten seconds, during which the form sits
            # on screen with its fields disabled. Judging at a fixed six
            # seconds misread an in-flight submission as a failure.
            REJECTED = ("couldn't submit", "could not submit", "flagged as possible spam",
                        "flagged as spam", "submission was flagged", "failed to submit",
                        "error submitting", "please try again")
            ACCEPTED = ("thank you", "application received", "we have received",
                        "successfully submitted", "thanks for applying",
                        "application submitted", "your application has been")
            verdict = "pending"
            deadline = time.time() + 30
            while time.time() < deadline:
                page.wait_for_timeout(2500)
                body = (page.inner_text("body") or "").lower()
                if any(sig in body for sig in REJECTED):
                    verdict = "rejected"
                    break
                if any(sig in body for sig in ACCEPTED):
                    verdict = "accepted"
                    break
                if page.locator('input[type="email"], input[type="file"]').count() == 0:
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
            context.close()
            browser.close()


def _record(job: dict[str, Any], result: dict[str, Any], *, dry_run: bool,
            log: Callable[[str], None]) -> str:
    """Write one attempt to the applications log and update the job row."""
    job_id = int(job["id"])
    result["job_hash"] = job.get("dedupe_hash")
    store.record_application(result)

    status = result["status"]
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


def apply_to_ids(job_ids: list[int], *, dry_run: bool = False, headless: bool = True,
                 workers: int = 1,
                 log: Callable[[str], None] = print) -> dict[str, Any]:
    """
    Apply to exactly these jobs — the per-job and bulk-apply entry point.

    Nothing here picks jobs on its own: the user chose them. The only rows this
    refuses are ones already applied to, checked against the live applications
    table so a double click, a re-run or an overlapping bulk selection cannot
    produce a second application.
    """
    rows = store.jobs_by_ids([int(i) for i in job_ids])
    if not rows:
        log("[apply] none of those job ids exist.")
        return {"attempted": 0, "submitted": 0, "failed": 0, "already": 0}

    already = store.applied_hashes()
    counts = {"attempted": 0, "submitted": 0, "failed": 0, "needs_review": 0, "already": 0}
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

        result = apply_to_job(job, dry_run=dry_run, headless=headless, log=log)
        with guard:
            status = _record(job, result, dry_run=dry_run, log=log)
            counts[status] = counts.get(status, 0) + 1
            if status == "submitted" and not dry_run and job_hash:
                already.add(job_hash)

    if lanes == 1:
        for job in queue:
            attempt(job)
            time.sleep(2)
    else:
        with ThreadPoolExecutor(max_workers=lanes) as pool:
            for _ in pool.map(attempt, queue):
                pass

    log(f"[apply] done — submitted={counts['submitted']} "
        f"needs-review={counts.get('needs_review', 0)} "
        f"failed={counts['failed']} already-applied={counts['already']}")
    return counts
