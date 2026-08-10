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
import time
from pathlib import Path
from typing import Any, Callable

from api.config import DASHBOARD_OUT
from api import behuman

from . import llm, matcher, store

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
    (re.compile(r"\blocation|\bcity|where.*based|current.*residence", re.I), "location"),
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

SUBMIT_RE = re.compile(r"^\s*(submit|send|apply|submit application|apply now|"
                       r"send application|finish|complete)\s*$", re.I)

# Walls the agent cannot get past. Detected explicitly so the job is recorded as
# a failure with a reason the user can act on, rather than disappearing.
CAPTCHA_MARKERS = ("recaptcha", "hcaptcha", "turnstile", "captcha", "arkoselabs",
                   "funcaptcha", "geetest")
LOGIN_MARKERS = re.compile(
    r"\b(sign in to (?:apply|continue)|log ?in to (?:apply|continue)|"
    r"create an account to apply|please (?:sign|log) ?in|"
    r"you must be logged in|register to apply)\b", re.I)


def _visible_captcha(page) -> bool:
    """
    Is there a captcha the user would actually have to solve?

    Presence of a recaptcha script or frame is NOT enough: Ashby (and many
    Greenhouse boards) load an *invisible* reCAPTCHA badge on every form, and
    treating that as a wall rejects forms that fill and submit fine. Only a
    rendered challenge counts — the "I'm not a robot" checkbox widget or an
    hCaptcha/Turnstile box, which are sizeable visible elements. The invisible
    badge is ~60px and anchored off in a corner.
    """
    probes = (
        'iframe[src*="recaptcha"][src*="anchor"]',   # the checkbox widget frame
        'iframe[src*="hcaptcha"]',
        'iframe[src*="turnstile"]',
        ".h-captcha iframe", ".cf-turnstile iframe",
    )
    for sel in probes:
        try:
            loc = page.locator(sel)
            for i in range(min(loc.count(), 4)):
                el = loc.nth(i)
                if not el.is_visible():
                    continue
                box = el.bounding_box()
                # The invisible badge is ~60x60 and tucked at the viewport edge;
                # a real challenge widget is a ~300px-wide box in the form flow.
                if box and box["width"] >= 200 and box["height"] >= 60:
                    return True
        except Exception:
            continue
    try:
        challenge = page.get_by_text(re.compile(
            r"(verify (?:that )?you are (?:a )?human|i'?m not a robot|"
            r"complete the captcha)", re.I))
        if challenge.count() and challenge.first.is_visible():
            return True
    except Exception:
        pass
    return False


def diagnose_wall(page) -> str | None:
    """
    Why this form cannot be completed automatically, or None if it can.

    Checked before field collection: a rendered captcha challenge or a login
    gate means the fields on the page are not the application form at all.
    """
    if _visible_captcha(page):
        return "blocked by a captcha challenge — this form needs a human"

    try:
        text = (page.inner_text("body") or "")[:6000]
    except Exception:
        text = ""
    hit = LOGIN_MARKERS.search(text)
    if hit:
        return f"behind a login wall — the site asks you to {hit.group(0).lower()}"
    if re.search(r"/(login|signin|sign-in|auth)\b", (page.url or ""), re.I):
        return "redirected to a sign-in page — an account is required to apply"
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
            prompt,
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
    """Every visible, fillable control on the page with its best-guess label."""
    return page.evaluate(
        """() => {
          const out = [];
          const nodes = document.querySelectorAll('input, textarea, select');
          nodes.forEach((el, i) => {
            const type = (el.type || el.tagName).toLowerCase();
            if (['hidden','submit','button','image','reset'].includes(type)) return;
            const r = el.getBoundingClientRect();
            if (type !== 'file' && (r.width === 0 || r.height === 0)) return;

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
            if (!String(el.value || '').trim()) out.push({ label, type });
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
    """
    field = _handle(page, idx)
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
        # Accept a suggestion if the widget opened one.
        for selector in ("[role=option]", ".dropdown-item", "li[class*=suggestion]",
                         "[class*=autocomplete] li"):
            options = page.locator(selector)
            if options.count() and options.first.is_visible():
                options.first.click(timeout=4000)
                page.wait_for_timeout(400)
                break
        else:
            field.press("Enter", timeout=4000)
            page.wait_for_timeout(400)
        return bool((field.input_value(timeout=2000) or "").strip())
    except Exception:
        return False


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
            prompt, ANSWER_SCHEMA, default={"answers": []},
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
                result["error"] = wall
                log(f"[apply]   FAILED — {wall}")
                try:
                    shot = SHOT_DIR / f"job{job.get('id')}_blocked.png"
                    page.screenshot(path=str(shot), full_page=True)
                    result["screenshot"] = shot.name
                except Exception:
                    pass
                return result

            fields = _collect_fields(page)
            log(f"[apply]   {len(fields)} form field(s) detected")
            if not fields:
                result["error"] = ("no form fields found — the posting is closed, or the "
                                   "application lives on a site the agent cannot read")
                shot = SHOT_DIR / f"job{job.get('id')}_noform.png"
                page.screenshot(path=str(shot), full_page=True)
                result["screenshot"] = shot.name
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
                # A failure, not a skip. The user needs to see which question
                # stopped it so they can add the answer to their profile.
                result["status"] = "failed"
                result["error"] = ("unsupported form: required question(s) the profile cannot "
                                   "answer truthfully — "
                                   + "; ".join(f.get("label", "?")[:60] for f in blocking[:3]))
                log(f"[apply]   FAILED — {result['error']}")
                return result

            if dry_run:
                result["status"] = "filled"
                log(f"[apply]   DRY RUN — form complete, not submitted ({shot.name})")
                return result

            submitted = False
            for name in ("Submit application", "Submit Application", "Submit", "Send application", "Apply"):
                btn = page.get_by_role("button", name=re.compile(rf"^\s*{re.escape(name)}\s*$", re.I))
                if btn.count() and btn.first.is_enabled():
                    btn.first.click()
                    submitted = True
                    break
            if not submitted:
                inp = page.locator("input[type=submit]")
                if inp.count():
                    inp.first.click()
                    submitted = True

            if not submitted:
                result["status"] = "filled"
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
    elif status == "filled":
        # Dry run, or filled but no submit button. Either way it is not applied.
        store.set_job_status(job_id, "tracked" if dry_run else "failed")
        if not dry_run:
            store.mark_job_failed(job_id, result.get("error")
                                  or "form filled but no submit button was found")
    return status


def apply_to_ids(job_ids: list[int], *, dry_run: bool = False, headless: bool = True,
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
    counts = {"attempted": 0, "submitted": 0, "failed": 0, "filled": 0, "already": 0}
    log(f"[apply] {len(rows)} job(s) selected"
        + (" — DRY RUN, nothing will be submitted" if dry_run else ""))

    for job in rows:
        job_hash = job.get("dedupe_hash")
        if job.get("status") == "applied" or (job_hash and job_hash in already):
            counts["already"] += 1
            log(f"[apply] SKIP (already applied) {job.get('company_name')} — {job['title'][:48]}")
            continue

        counts["attempted"] += 1
        result = apply_to_job(job, dry_run=dry_run, headless=headless, log=log)
        status = _record(job, result, dry_run=dry_run, log=log)
        counts[status] = counts.get(status, 0) + 1
        if status == "submitted" and not dry_run and job_hash:
            already.add(job_hash)
        time.sleep(2)

    log(f"[apply] done — submitted={counts['submitted']} filled={counts.get('filled', 0)} "
        f"failed={counts['failed']} already-applied={counts['already']}")
    return counts


def run_applications(limit: int = 5, *, dry_run: bool = False, headless: bool = True,
                     max_age_days: int | None = None,
                     log: Callable[[str], None] = print) -> dict[str, Any]:
    targeting = store.get_setting("targeting", {}) or {}
    threshold = float(targeting.get("min_fit_score", 55))
    if max_age_days is None:
        max_age_days = targeting.get("max_age_days", 3)
    require_date = bool(targeting.get("require_posted_date", True))
    order = targeting.get("apply_order", "recent")

    queue = store.jobs_to_apply(limit=limit, min_score=threshold,
                                max_age_days=max_age_days,
                                require_posted_date=require_date, order=order)
    jobs, excluded = queue["jobs"], queue["excluded"]

    log(f"[apply] {excluded['considered']} matched role(s) considered · "
        f"skipped {excluded['stale']} older than {max_age_days}d, "
        f"{excluded['undated']} with no posting date, "
        f"{excluded['duplicate']} already applied to")

    if not jobs:
        log("[apply] nothing fresh to apply to. Run Research again for newer postings, "
            "widen the age window, or lower the fit threshold in Settings.")
        return {"attempted": 0, "submitted": 0, "skipped": 0, "failed": 0, **excluded}

    log(f"[apply] {len(jobs)} role(s) queued, "
        f"{'newest first' if order == 'recent' else 'best fit first'}"
        + (" — DRY RUN, nothing will be submitted" if dry_run else ""))

    counts = {"attempted": 0, "submitted": 0, "skipped": 0, "failed": 0, "filled": 0}
    seen_this_run: set[str] = set()

    for job in jobs:
        job_hash = job.get("dedupe_hash")
        # Re-check against the live table: a long run could have submitted this
        # same role under a different URL a few minutes ago.
        if job_hash and (job_hash in seen_this_run or job_hash in store.applied_hashes()):
            log(f"[apply] SKIP (already applied) {job.get('company_name')} — {job['title'][:50]}")
            store.set_job_status(job["id"], "duplicate")
            counts["skipped"] += 1
            continue

        age = job.get("age_days")
        log(f"[apply] fit {job.get('fit_score', 0):.0f} · posted "
            f"{'unknown' if age is None else f'{age:.1f}d ago'} · hash {job_hash or '—'}")

        counts["attempted"] += 1
        result = apply_to_job(job, dry_run=dry_run, headless=headless, log=log)
        status = _record(job, result, dry_run=dry_run, log=log)
        counts[status] = counts.get(status, 0) + 1
        if status in ("submitted", "filled") and not dry_run and job_hash:
            seen_this_run.add(job_hash)
        time.sleep(2)

    log(f"[apply] done — submitted={counts.get('submitted',0)} filled={counts.get('filled',0)} "
        f"skipped={counts.get('skipped',0)} failed={counts.get('failed',0)}")
    return {**counts, **excluded}
