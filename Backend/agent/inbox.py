"""
The reply half of the loop.

Applications used to go out and nothing came back: the agent knew what it had
submitted and never learned what happened next. This module reads the mailbox
the outreach path already sends from, links each message to the application it
belongs to, works out what the message *is*, and moves the pipeline on.

Three deliberate positions:

  * **Linking is ranked, not guessed.** A threaded reply is near-certain; a
    match on the sender's domain is strong; a company name in the subject is
    weak. Each carries its confidence forward, and only a high-confidence link
    is allowed to move anything. A message that cannot be placed is still
    stored, so it shows up to be read rather than vanishing.

  * **Classification is rules first.** A phrase table answers the large
    majority for nothing at all, which matters when the whole LLM budget is
    about sixty calls a day. The model is asked only about what the rules
    genuinely cannot place, and the answer is cached.

  * **The user's own edit always wins.** The agent advances a stage; it never
    contradicts a stage a human set by hand.

Credentials are the ones already in Backend/.env for sending: no new secret,
no OAuth dance. Gmail requires an app password for IMAP exactly as it does for
SMTP.
"""

from __future__ import annotations

import email
import imaplib
import re
from email.header import decode_header, make_header
from email.utils import getaddresses, parsedate_to_datetime
from typing import Any, Callable

from . import env, store
from .schema import CLASS_TO_TRACKER, LINK_CONFIDENCE_THRESHOLD

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993
SOCKET_TIMEOUT_S = 45

# How much of the body is worth reading. Recruiting mail says what it is in the
# first paragraph; the rest is signatures, legal boilerplate and quoted history.
BODY_CHARS = 4000
SNIPPET_CHARS = 400

# How many messages one scan may put to the model. The rules answer nearly
# everything; this bounds the tail so a single run cannot spend the day.
LLM_BUDGET_PER_RUN = 8


# --------------------------------------------------------------------------
# Classification
# --------------------------------------------------------------------------
#
# Ordered most specific first, and checked in order: a rejection that mentions
# an interview ("we will not be moving forward after your interview") is a
# rejection, so `rejection` is tested before `interview`.

RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("bounce", re.compile(
        r"\b(delivery status notification|undeliverable|mail delivery (failed|subsystem)|"
        r"address not found|recipient address rejected|550[- ]5\.1\.1|"
        r"user unknown|mailbox (is )?(full|unavailable))\b", re.I)),

    ("rejection", re.compile(
        r"\b(not (be )?(moving|progressing) forward|will not be moving ahead|"
        r"decided (not to (move|proceed)|to move forward with other)|"
        r"unfortunately[^.]{0,60}(not|unable|other candidates)|"
        r"we (have )?(decided|chosen|selected) (an)?other|"
        r"no longer (being )?consider|not (been )?(selected|shortlisted|successful)|"
        r"pursue other candidates|position has been filled|"
        r"keep your (resume|details|cv) on file)\b", re.I)),

    ("offer", re.compile(
        r"\b(offer of employment|pleased to offer|we would like to offer|"
        r"formal offer|offer letter|extend(ing)? (you )?an offer|"
        r"your compensation package)\b", re.I)),

    ("interview", re.compile(
        r"\b(schedule (a|an|your)? ?(call|chat|interview|conversation)|"
        r"invite you to (an?|the) ?(interview|call|conversation)|"
        r"would like to (set up|arrange|schedule)|"
        r"book a time|pick a time|select a time|availability (for|to)|"
        r"phone screen|technical (interview|round)|hiring manager (call|chat)|"
        r"next (round|step)s? (is|will be) an? (call|interview)|"
        # Subject-line shapes. Recruiting mail routinely says the whole thing
        # in the subject and puts only logistics in the body, so a pattern that
        # only reads prose misses the clearest signal on the message.
        r"interview (invitation|request|scheduling)|invitation to interview|"
        r"schedule your interview|"
        r"calendly\.com|savvycal\.com|meetings\.hubspot)\b", re.I)),

    ("assessment", re.compile(
        r"\b(coding (challenge|assessment|exercise|test)|take[- ]home|"
        r"online assessment|technical (assessment|challenge|screen)|"
        r"hackerrank|codility|codesignal|karat|woven|"
        r"complete (the|this) (assessment|challenge|test))\b", re.I)),

    ("verification", re.compile(
        r"\b(verify your (email|account|address)|confirm your (email|account)|"
        r"activate your account|one[- ]time (code|password)|"
        r"security code|\bOTP\b|reset your password)\b", re.I)),

    ("reminder", re.compile(
        r"\b(reminder|don'?t forget|action required|complete your (application|profile)|"
        r"your application is incomplete|finish (your )?application|"
        r"awaiting your (response|action))\b", re.I)),

    ("acknowledgment", re.compile(
        r"\b(thank you for (your interest|applying|your application)|"
        r"we (have )?received your application|application (has been )?received|"
        r"we'?re reviewing your application|thanks for applying|"
        r"your application (to|for)|application confirmation)\b", re.I)),
)

# Automated senders whose mail is never about one application's progress.
NOISE_SENDERS = re.compile(
    r"(no-?reply@(linkedin|indeed|glassdoor|ziprecruiter)|"
    r"jobalerts?@|digest@|newsletter@|notifications?@(linkedin|glassdoor))", re.I)

# The domains applicant tracking systems send from.
#
# This matters more than it looks. Almost no recruiting mail arrives from the
# employer's own domain: the Interfere rejection came from no-reply@ashbyhq.com,
# so matching the sender against `interfere.com` failed and the company name in
# the subject was the only signal left. Treating that as weak meant a genuine
# rejection sat below the threshold and moved nothing.
#
# An ATS mailer only writes to you about applications you actually made, so
# "known ATS mailer + this company named in the subject" is a strong link, not
# a guess.
ATS_MAILERS = re.compile(
    r"\b(ashbyhq|greenhouse(-mail)?|greenhouse\.io|lever\.co|hire\.lever|"
    r"myworkday|workday(suite)?|icims|smartrecruiters|jobvite|workable|"
    r"bamboohr|breezy\.hr|teamtailor|recruitee|jazzhr|applytojob|"
    r"successfactors|taleo|dayforce|paylocity|rippling|gem\.com|dover\.com|"
    r"phenompeople|pinpointhq|join\.com|hireology|zohorecruit)\b", re.I)


def is_ats_mailer(domain: str) -> bool:
    return bool(domain and ATS_MAILERS.search(domain))


def classify_rules(subject: str, body: str) -> tuple[str | None, float]:
    """(class, confidence) from the phrase table, or (None, 0) if unsure."""
    blob = f"{subject}\n{body}"
    for klass, pattern in RULES:
        hit = pattern.search(blob)
        if not hit:
            continue
        # A phrase in the subject line is a much stronger signal than the same
        # phrase buried in a body that may be quoting an earlier message.
        in_subject = bool(pattern.search(subject))
        return klass, 0.95 if in_subject else 0.85
    return None, 0.0


CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "klass": {"type": "string", "enum": ["acknowledgment", "interview", "assessment",
                                             "offer", "rejection", "reminder",
                                             "verification", "other"]},
        "confidence": {"type": "number"},
    },
    "required": ["klass"],
}

CLASSIFY_SYSTEM = (
    "You label one email from an employer to a job applicant. Reply with exactly one "
    "class:\n"
    "  acknowledgment  the application was received, nothing more\n"
    "  interview       an interview or call is being scheduled or offered\n"
    "  assessment      a coding test, take home or online assessment\n"
    "  offer           an offer of employment\n"
    "  rejection       the candidate is not going forward\n"
    "  reminder        the candidate must finish or act on something\n"
    "  verification    verify an email, confirm an account, or a one time code\n"
    "  other           none of the above, or not about a job application\n\n"
    "Judge what the sender is telling the candidate. A rejection that mentions an "
    "interview is still a rejection."
)


def classify(subject: str, body: str, *, use_llm: bool = True,
             log: Callable[[str], None] = print) -> tuple[str, float, str]:
    """(class, confidence, how). Rules answer first; the model is the fallback."""
    klass, confidence = classify_rules(subject, body)
    if klass:
        return klass, confidence, "rules"
    if not use_llm:
        return "other", 0.3, "default"

    from . import llm

    try:
        data = llm.complete_json(
            f"SUBJECT: {subject}\n\nBODY:\n{body[:1500]}",
            CLASSIFY_SCHEMA, system=CLASSIFY_SYSTEM,
            default={"klass": "other", "confidence": 0.3},
            purpose="classify", cacheable=True)
    except Exception as exc:
        log(f"[inbox] classifier unavailable ({type(exc).__name__}); leaving as other")
        return "other", 0.3, "default"

    guess = (data.get("klass") or "other").strip()
    score = float(data.get("confidence") or 0.6)
    return (guess if guess in dict(RULES) or guess == "other" else "other"), score, "llm"


# --------------------------------------------------------------------------
# Linking
# --------------------------------------------------------------------------

def _norm_company(name: str) -> str:
    """Company names for comparison, with the corporate suffixes removed."""
    text = re.sub(r"[^a-z0-9 ]+", " ", (name or "").lower())
    text = re.sub(r"\b(inc|llc|ltd|limited|gmbh|bv|ab|as|oy|plc|corp|corporation|"
                  r"co|company|technologies|technology|labs|group|holdings|sa|srl)\b",
                  " ", text)
    return re.sub(r"\s+", " ", text).strip()


def link_message(msg: dict[str, Any], applications: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Which application does this message belong to?

    Returns {application_id, job_id, company_id, confidence, linked_by}. The
    signals are ranked, and the first that fires wins, because a weaker signal
    agreeing adds nothing and a weaker signal disagreeing should not be able to
    drag a certain match away.
    """
    miss = {"application_id": None, "job_id": None, "company_id": None,
            "confidence": 0.0, "linked_by": "none"}

    # 1. The message is a reply in a thread we started. Near certain.
    refs = {r for r in (msg.get("references") or []) if r}
    if msg.get("in_reply_to"):
        refs.add(msg["in_reply_to"])
    if refs:
        for app in applications:
            if app.get("message_id") and app["message_id"] in refs:
                return {"application_id": int(app["id"]), "job_id": app.get("job_id"),
                        "company_id": app.get("company_id"),
                        "confidence": 0.98, "linked_by": "thread"}

    domain = (msg.get("from_domain") or "").lower()
    subject_norm = _norm_company(msg.get("subject") or "")

    # 2. The sender's domain is the company's. Strong, and stronger still when
    #    only one application went to that company.
    if domain:
        matches = [a for a in applications
                   if (a.get("domain") or "").lower() == domain
                   or _norm_company(a.get("company_name") or "") == _norm_company(
                       domain.rsplit(".", 1)[0])]
        if len(matches) == 1:
            app = matches[0]
            return {"application_id": int(app["id"]), "job_id": app.get("job_id"),
                    "company_id": app.get("company_id"),
                    "confidence": 0.9, "linked_by": "domain"}
        if len(matches) > 1:
            # Several roles at one employer. The job title in the subject
            # decides; without it, the newest application is the best guess and
            # the confidence says so.
            titled = [a for a in matches
                      if a.get("title") and _norm_company(a["title"]) in subject_norm]
            app = titled[0] if len(titled) == 1 else max(
                matches, key=lambda a: a.get("submitted_at") or "")
            return {"application_id": int(app["id"]), "job_id": app.get("job_id"),
                    "company_id": app.get("company_id"),
                    "confidence": 0.85 if len(titled) == 1 else 0.6,
                    "linked_by": "domain"}

    # 3. The company's name in the subject.
    #
    #    Weak in general — anyone can put a company name in a subject line —
    #    but strong when the sender is a known ATS mailer, because an ATS only
    #    writes to you about applications you actually submitted. That case is
    #    also the common one: most recruiting mail never comes from the
    #    employer's own domain.
    if subject_norm:
        named = [a for a in applications
                 if _norm_company(a.get("company_name") or "")
                 and _norm_company(a["company_name"]) in subject_norm]
        if len(named) == 1:
            app = named[0]
            return {"application_id": int(app["id"]), "job_id": app.get("job_id"),
                    "company_id": app.get("company_id"),
                    "confidence": 0.9 if is_ats_mailer(domain) else 0.65,
                    "linked_by": "ats" if is_ats_mailer(domain) else "company"}

    return miss


# --------------------------------------------------------------------------
# IMAP
# --------------------------------------------------------------------------

def _decode(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return str(value)


def _body_text(message: email.message.Message) -> str:
    """Plain text of the message, preferring text/plain over stripped HTML."""
    html = ""
    if message.is_multipart():
        for part in message.walk():
            ctype = part.get_content_type()
            if part.get_filename():
                continue
            try:
                payload = part.get_payload(decode=True)
            except Exception:
                continue
            if not payload:
                continue
            text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
            if ctype == "text/plain":
                return text[:BODY_CHARS]
            if ctype == "text/html" and not html:
                html = text
    else:
        try:
            payload = message.get_payload(decode=True)
            text = (payload or b"").decode(
                message.get_content_charset() or "utf-8", errors="replace")
        except Exception:
            text = ""
        if message.get_content_type() == "text/html":
            html = text
        else:
            return text[:BODY_CHARS]

    stripped = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    stripped = re.sub(r"<[^>]+>", " ", stripped)
    return re.sub(r"\s+", " ", stripped)[:BODY_CHARS]


def credentials() -> tuple[str, str]:
    env.load()
    import os

    return (os.environ.get("GMAIL_ADDRESS", "").strip(),
            os.environ.get("GMAIL_APP_PASS", "").replace(" ", "").strip())


def available() -> tuple[bool, str]:
    address, password = credentials()
    if not address or not password:
        return False, ("GMAIL_ADDRESS and GMAIL_APP_PASS are not both set in Backend/.env. "
                       "The inbox uses the same app password the outreach sender does.")
    return True, f"Reading {address} over IMAP."


def fetch(days: int = 30, limit: int = 200, *,
          log: Callable[[str], None] = print) -> list[dict[str, Any]]:
    """Recent messages as plain dicts. Never raises; returns [] and says why."""
    address, password = credentials()
    ok, why = available()
    if not ok:
        log(f"[inbox] {why}")
        return []

    from datetime import datetime, timedelta, timezone

    since = (datetime.now(timezone.utc) - timedelta(days=max(1, days))).strftime("%d-%b-%Y")
    out: list[dict[str, Any]] = []
    try:
        # A timeout matters more than it looks: Gmail throttles IMAP after
        # repeated logins, and a throttled connection accepts the socket and
        # then simply never answers. Without this the scheduler's inbox run
        # would hang forever and block every other scheduled task behind it.
        conn = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, timeout=SOCKET_TIMEOUT_S)
        conn.login(address, password)
        conn.select("INBOX", readonly=True)      # readonly: never touch the mailbox
        status, data = conn.search(None, f'(SINCE {since})')
        if status != "OK":
            log(f"[inbox] search failed: {status}")
            conn.logout()
            return []
        ids = (data[0] or b"").split()
        seen = store.known_message_ids()
        log(f"[inbox] {len(ids)} message(s) since {since}")

        # Two passes, because bodies are the expensive part. Headers come back
        # in one batched round trip; only messages that survive the "already
        # stored" and "automated noise" filters cost a body fetch. Fetching
        # every full message one at a time made a routine sync take minutes.
        recent = ids[-max(limit, 1) * 4:]
        if not recent:
            conn.logout()
            return []

        headers: dict[bytes, email.message.Message] = {}
        for start in range(0, len(recent), 100):
            batch = b",".join(recent[start:start + 100])
            status, payload = conn.fetch(
                batch, "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID IN-REPLY-TO REFERENCES "
                       "FROM SUBJECT DATE)])")
            if status != "OK":
                continue
            index = 0
            for item in payload or []:
                if not isinstance(item, tuple):
                    continue
                # The server returns results in request order; pair them up by
                # position rather than parsing the sequence number back out.
                if index < len(recent[start:start + 100]):
                    headers[recent[start:start + 100][index]] = \
                        email.message_from_bytes(item[1])
                    index += 1

        wanted: list[tuple[bytes, email.message.Message]] = []
        for raw_id in reversed(recent):
            head = headers.get(raw_id)
            if head is None:
                continue
            message_id = (head.get("Message-ID") or "").strip()
            if message_id and message_id in seen:
                continue
            if NOISE_SENDERS.search(head.get("From", "") or ""):
                continue
            wanted.append((raw_id, head))
            if len(wanted) >= limit:
                break

        log(f"[inbox] {len(wanted)} new message(s) to read")
        for raw_id, head in wanted:
            addresses = getaddresses([head.get("From", "")])
            from_addr = (addresses[0][1] if addresses else "").lower()
            received = None
            try:
                received = parsedate_to_datetime(head.get("Date", "")).isoformat()
            except Exception:
                pass

            # RFC822 rather than BODY.PEEK[]: Gmail answers the latter with a
            # bare "System Error" on some messages. Nothing gets marked read
            # either way — the mailbox was selected readonly.
            # One unreadable message must not end the run, so this is guarded.
            body = ""
            try:
                status, payload = conn.fetch(raw_id, "(RFC822)")
                if status == "OK" and payload and isinstance(payload[0], tuple):
                    body = _body_text(email.message_from_bytes(payload[0][1]))
            except Exception as exc:
                log(f"[inbox] could not read one message body ({type(exc).__name__}); "
                    f"classifying from the subject alone")

            out.append({
                "message_id": (head.get("Message-ID") or "").strip() or None,
                "in_reply_to": (head.get("In-Reply-To") or "").strip() or None,
                "references": (head.get("References") or "").split(),
                "from_addr": from_addr,
                "from_domain": from_addr.rsplit("@", 1)[-1] if "@" in from_addr else "",
                "subject": _decode(head.get("Subject")),
                "body": body,
                "snippet": body[:SNIPPET_CHARS],
                "received_at": received,
            })
        conn.logout()
    except imaplib.IMAP4.error as exc:
        detail = str(exc)
        # Distinguish the two, because they need opposite responses: a refused
        # login is a credentials problem the user must fix, a mid-session
        # command error is not, and telling them to check their app password
        # when the password is fine sends them the wrong way.
        if "AUTHENTICATIONFAILED" in detail or "Invalid credentials" in detail:
            log(f"[inbox] Gmail refused the login: {detail}. It needs an app password, "
                f"with IMAP enabled under Settings > Forwarding and POP/IMAP.")
        else:
            log(f"[inbox] the mailbox stopped responding partway through: {detail}. "
                f"Keeping the {len(out)} message(s) read so far.")
        return out
    except Exception as exc:
        log(f"[inbox] could not read the mailbox: {type(exc).__name__}: {exc}")
        return out
    return out


# --------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------

def backfill_stages(*, log: Callable[[str], None] = print) -> int:
    """Applications submitted before the tracker existed start at `applied`.

    Without this they are invisible to the pipeline: submitted, real, and
    sitting in no stage at all."""
    fixed = 0
    for row in store.applications_for_linking():
        if not row.get("tracker_status"):
            store.set_tracker_status(int(row["id"]), "applied")
            fixed += 1
    if fixed:
        log(f"[inbox] placed {fixed} earlier application(s) at the 'applied' stage")
    return fixed


def sync(days: int = 30, limit: int = 200, *, use_llm: bool = True,
         log: Callable[[str], None] = print) -> dict[str, Any]:
    """Read, link, classify and advance. The whole Track loop, one call."""
    counts = {"scanned": 0, "stored": 0, "linked": 0, "advanced": 0, "bounced": 0}
    backfill_stages(log=log)
    messages = fetch(days=days, limit=limit, log=log)
    counts["scanned"] = len(messages)
    if not messages:
        return counts

    applications = store.applications_for_linking()
    log(f"[inbox] matching against {len(applications)} submitted application(s)")

    # The model is asked only about messages that could plausibly be about an
    # application: ones that linked to something. An unlinked message whose
    # phrasing matched no rule is almost never recruiting mail — it is the
    # ordinary contents of a mailbox — and asking about each one turned a
    # seven-second scan into a four-minute one while draining a daily budget
    # of about sixty calls. `LLM_BUDGET_PER_RUN` caps even the plausible ones,
    # so one busy morning cannot spend the whole day's allowance.
    asked = 0

    for msg in messages:
        link = link_message(msg, applications)

        klass, confidence = classify_rules(msg["subject"], msg["body"])
        how = "rules"
        if not klass:
            worth_asking = (use_llm and link["application_id"] is not None
                            and asked < LLM_BUDGET_PER_RUN)
            if worth_asking:
                klass, confidence, how = classify(msg["subject"], msg["body"],
                                                  use_llm=True, log=log)
                asked += 1
            else:
                klass, confidence, how = "other", 0.3, "default"

        row_id = store.record_message({
            **{k: msg.get(k) for k in
               ("message_id", "from_addr", "from_domain", "subject", "snippet",
                "body", "received_at")},
            "application_id": link["application_id"],
            "job_id": link["job_id"],
            "company_id": link["company_id"],
            "thread_id": msg.get("in_reply_to"),
            "klass": klass,
            "confidence": link["confidence"],
            "linked_by": link["linked_by"],
        })
        if row_id is None:
            continue                    # already stored on an earlier run
        counts["stored"] += 1
        if link["application_id"]:
            counts["linked"] += 1

        if klass == "bounce":
            counts["bounced"] += 1
            _demote_bounced_pattern(msg, log=log)
            continue

        # Only a confident link may move the pipeline, and only for a class
        # whose meaning is unambiguous.
        stage = CLASS_TO_TRACKER.get(klass)
        if (stage and link["application_id"]
                and link["confidence"] >= LINK_CONFIDENCE_THRESHOLD):
            if _advance(int(link["application_id"]), stage, log=log):
                counts["advanced"] += 1

    log(f"[inbox] stored={counts['stored']} linked={counts['linked']} "
        f"advanced={counts['advanced']} bounced={counts['bounced']}"
        + (f" · {asked} classified by the model" if asked else " · rules only"))
    counts["llm_calls"] = asked
    return counts


# A stage only ever moves forward, and never past a terminal one. Without this
# an automated "thanks for applying" arriving after a rejection would drag the
# application back to square one.
STAGE_ORDER = {"applied": 0, "interviewing": 1, "offer": 2, "rejected": 3, "ghosted": 3}


def _advance(application_id: int, stage: str, *,
             log: Callable[[str], None] = print) -> bool:
    row = store.application(application_id)
    if not row:
        return False
    current = row.get("tracker_status") or "applied"
    if current in ("rejected", "offer"):
        return False                    # terminal: only the user reopens these
    if STAGE_ORDER.get(stage, 0) <= STAGE_ORDER.get(current, 0):
        return False
    store.set_tracker_status(application_id, stage)
    log(f"[inbox] {row.get('company_name') or 'application'} "
        f"{row.get('title') or ''}: {current} -> {stage}")
    return True


def _demote_bounced_pattern(msg: dict[str, Any], *,
                            log: Callable[[str], None] = print) -> None:
    """A hard bounce means the address was wrong; stop trusting that guess.

    Marking it invalid is the honest substitute for the port-25 probe most
    ISPs block: the mailbox itself has now told us."""
    found = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", msg.get("body") or "")
    if not found:
        return
    address = found.group(0).lower()
    if address == (msg.get("from_addr") or ""):
        return
    try:
        store.upsert_person({
            "email": address, "email_status": "invalid", "email_score": 0.0,
            "verify_detail": "hard bounce received from the mail server",
        })
        log(f"[inbox] {address} bounced; marked invalid so it is not reused")
    except Exception:
        pass


# --------------------------------------------------------------------------
# Replying
# --------------------------------------------------------------------------

def reply(message_id: int, body: str, *, subject: str | None = None,
          log: Callable[[str], None] = print) -> dict[str, Any]:
    """
    Answer one message from the mailbox Quiver already reads.

    A recruiter's "can you do Tuesday at 3?" wants a one-line answer within the
    hour, and the whole point of reading the mailbox here is to know it arrived.
    Making the user leave for Gmail to type that line is where the loop breaks.

    The reply is threaded properly — `In-Reply-To` and `References` carry the
    original `Message-ID` — so it lands in the same conversation rather than
    arriving as an unrelated mail with a "Re:" subject. It goes out over the
    same SMTP credentials the outreach sender uses; there is no second account
    and no OAuth.
    """
    text = (body or "").strip()
    if not text:
        return {"ok": False, "error": "The reply is empty."}

    row = store.get_message(message_id)
    if not row:
        return {"ok": False, "error": f"No message {message_id}."}

    to = (row.get("from_addr") or "").strip()
    if not to:
        return {"ok": False, "error": "That message has no reply address."}

    address, password = credentials()
    if not address or not password:
        return {"ok": False, "error": ("GMAIL_ADDRESS and GMAIL_APP_PASS are not set in "
                                       "Backend/.env, so nothing can be sent.")}

    original = (row.get("subject") or "").strip()
    if subject:
        line = subject.strip()
    elif original.lower().startswith("re:"):
        line = original
    else:
        line = f"Re: {original}" if original else "Re:"

    # The RFC value, not our row id — threading is done by Message-ID.
    ref = (row.get("message_id") or "").strip()

    import smtplib
    import ssl
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["From"] = address
    msg["To"] = to
    msg["Subject"] = line
    if ref:
        msg["In-Reply-To"] = ref
        msg["References"] = ref
    msg.set_content(text)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465,
                              context=ssl.create_default_context(), timeout=30) as server:
            server.login(address, password)
            server.send_message(msg)
    except Exception as exc:
        log(f"[inbox] reply to {to} failed: {exc}")
        return {"ok": False, "error": str(exc)}

    # Answering a message is the clearest possible signal that it has been
    # read, so the user never has to say so twice.
    try:
        store.mark_message_read(message_id, True)
    except Exception:
        pass

    log(f"[inbox] replied to {to}")
    return {"ok": True, "to": to, "subject": line, "threaded": bool(ref)}


def compose(to: str, subject: str, body: str, *,
            log: Callable[[str], None] = print) -> dict[str, Any]:
    """
    Send a new message — a follow-up, a nudge, a thank-you — not a reply.

    The inbox is where the user already reads recruiter mail, so composing from
    the same place, over the same credentials, is one less context switch than
    opening Gmail to send a single line. It starts a fresh thread; `reply()`
    remains the way to answer an existing one.
    """
    to = (to or "").strip()
    text = (body or "").strip()
    if "@" not in to:
        return {"ok": False, "error": "That is not an email address."}
    if not text:
        return {"ok": False, "error": "The message is empty."}

    address, password = credentials()
    if not address or not password:
        return {"ok": False, "error": ("GMAIL_ADDRESS and GMAIL_APP_PASS are not set in "
                                       "Backend/.env, so nothing can be sent.")}

    import smtplib
    import ssl
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["From"] = address
    msg["To"] = to
    msg["Subject"] = (subject or "").strip() or "(no subject)"
    msg.set_content(text)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465,
                              context=ssl.create_default_context(), timeout=30) as server:
            server.login(address, password)
            server.send_message(msg)
    except Exception as exc:
        log(f"[inbox] compose to {to} failed: {exc}")
        return {"ok": False, "error": str(exc)}

    log(f"[inbox] sent a message to {to}")
    return {"ok": True, "to": to, "subject": msg["Subject"]}
