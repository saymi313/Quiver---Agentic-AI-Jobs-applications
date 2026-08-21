# Quiver requirements: reach feature parity with Tsenta

Researched from tsenta.com and docs.tsenta.com on 2026-08-21. Every claim about
Tsenta in section 2 comes from their marketing site or public documentation, not
from inference. Quoted phrases are verbatim.

---

## 1. Purpose

Quiver today is a local, single-user job-hunting tool: it discovers roles, tailors
a LaTeX resume per posting, and drives a browser to fill application forms the user
selects. Tsenta is a hosted, multi-user, paid product doing the same job at much
larger scale, with more surfaces and a developer API on top.

This document states what Quiver must become to work the way Tsenta works. Each
requirement is written so it can be picked up, built and verified on its own.

---

## 2. Reference product: what Tsenta does

### 2.1 The pipeline

Tsenta describes four stages. Quiver should adopt the same vocabulary, because the
stages map cleanly onto code that already exists.

| Stage | Tsenta's headline | What it means |
|---|---|---|
| **01 Find** | "Be the first qualified applicant on the job." | Watches 50,000+ company career pages continuously; alerts within seconds of a matching role appearing; shows a match percentage and the reasoning behind it. |
| **02 Prep** | "A resume and cover letter, rewritten per role." | Keyword-aligned resume and cover letter generated from the actual job description; every change shown before anything is sent. |
| **03 Apply** | "Tsenta opens the form. Tsenta hits submit." | Fills every field across 19+ ATS platforms in the product (28 listed in the docs), writes open-ended answers in the user's voice, uploads documents, handles login, submits, and returns a receipt. |
| **04 Track** | "Replies, interviews, rejections, auto-routed." | Recruiter email is matched back to the application it belongs to; status advances on its own; the inbox is grouped by what each message is. |

Supporting detail worth copying:

- Find shows a live scan line ("scanning supabase.com/careers... 0 new") and a
  time-to-apply comparison against other channels.
- Prep shows a before/after diff per bullet and a counter: "4 changes, nothing
  sent yet", with Edit and Approve.
- Apply returns a receipt: "6 of 6 fields, 0 skipped, 0 generic answers".
- Track shows "Zero manual filings, 47 routed automatically".

### 2.2 Supported application systems

Tsenta's docs list **28 supported application-system types**:

Workday, Greenhouse, Lever, Ashby, ADP, iCIMS, SmartRecruiters, Oracle Recruiting,
Workable, Rippling, Paylocity, JazzHR, BambooHR, Jobvite, Breezy HR, UltiPro/UKG,
Zoho Recruit, Dover, Gem, SuccessFactors, Dayforce, Phenom, Teamtailor, Recruitee,
Pinpoint, Polymer, Hireology, Join.com.

Their caveat is worth adopting as a rule rather than a disclaimer: "Tsenta may
recognize a job page even when that page does not have an active submission
workflow." Detection and submission are tracked as separate capabilities.

### 2.3 Profile and tailoring model

Profile sections: contact and personal info, experience, education, skills,
projects and certifications, application defaults (work authorization, work
preferences, reused background answers), plus user-defined custom sections.

Resumes: preview, upload, download. PDF under 10 MB at onboarding, DOCX after.
Multiple named resume profiles, creatable by duplication or import, one marked
default. Cover letters are generated "on demand in supported application workflows
that accept or require one".

Three tailoring modes:

- **Off**: submit the resume unchanged.
- **Honest**: "Reword for the role using only what's already on your resume."
- **Aggressive**: "Rewrite more freely to maximize keyword match."

Two independent review gates: auto-approve tailored materials on or off, and
review-the-filled-form-before-submit on supported systems.

### 2.4 Tracking model

Tracker statuses: **Applied, Interviewing, Offer, Rejected, Ghosted.**

Inbox message classes: **acknowledgments, interviews, assessments, offers,
rejections, reminders, verification messages.**

Applications can be created by Tsenta itself, added manually, or imported from CSV.
"When a message is linked with high confidence, Tsenta may update the associated
tracker status", and the user can always correct it by hand.

### 2.5 Surfaces

Web dashboard, iOS app, Android app, iMessage and WhatsApp texting, a Chrome
extension for one-click apply from any job posting, and an MCP server plus CLI for
agents.

MCP server: `https://api.autojobs.me/api/v1/mcp`, HTTP transport, OAuth with
short-lived auto-refreshing tokens. Installed with:

    claude mcp add --transport http tsenta https://api.autojobs.me/api/v1/mcp

MCP capabilities: role discovery with filters, single and batch application
submission, resume profile management, application tracking and import, inbox
reading and unread count, profile editing, remaining-allowance check.

### 2.6 Developer API

Base URL `https://api.autojobs.me/v1`, bearer API key. Priced at **$0.09 per
application, charged only on success**. Rate limit **100 applications per minute
per account**.

Endpoints:

    GET  /ats
    POST /detect
    POST /candidates
    POST /profiles
    GET  /profiles
    GET  /profiles/{id}
    POST /applications
    GET  /applications
    GET  /applications/{id}
    POST /applications/{id}/review
    POST /applications/{id}/otp
    GET  /usage

Application object: `id`, `candidate_id`, `candidate_name`, `candidate_email`,
`profile_id`, `ats`, `url`, `status`, `failure_reason`, `price_usd`, `review`,
`created_at`, `updated_at`.

Application status machine:

| Status | Meaning (verbatim) |
|---|---|
| `queued` | "Accepted, not started. Credit is held." |
| `running` | "In progress." |
| `needs_review` | "Paused. Answers are waiting on your decision." |
| `submitted` | "Terminal, success. This is what you are charged for." |
| `failed` | "Terminal. Not charged." |

Webhooks: `application.running`, `application.needs_review`,
`application.needs_otp`, `application.submitted`, `application.failed`.

Errors: `unauthorized`, `invalid_request`, `not_found`, `insufficient_credit`,
`rate_limited`, `duplicate_application`, `invalid_state`, `internal_error`.

### 2.7 Commercial model

| Tier | Price | Applications per 30 days |
|---|---|---|
| Starter | $19/mo | 600 |
| Pro | $39/mo | 1,500 |
| Power | $99/mo | 4,500 |

Free trial of 25 successful applications, no card. Features are identical across
tiers; only volume differs. "Successful submission uses one application; failed or
skipped attempts do not." A referral gives both parties 200 free applications.
Auto Apply, where the agent picks and submits within your filters subject to a
match threshold and a daily cap, is a Pro and Power feature rather than Starter.

---

## 3. Assumptions, and the decisions this document cannot make for you

These change the size of the work by an order of magnitude, so they are stated
rather than assumed silently.

- **A1. Single user or multi-tenant.** Tsenta is multi-tenant with accounts,
  billing and per-user isolation. Quiver is one user, one machine, one SQLite or
  Atlas database, no auth. Everything in section 5.7 is only meaningful if Quiver
  becomes multi-tenant. This document specifies both and marks multi-tenant items
  `[MT]`.
- **A2. Hosting.** "50,000 pages watched" and "100 applications per minute" need
  always-on servers and a browser farm. A laptop running uvicorn cannot do this.
  Parity on **behaviour** is achievable now; parity on **scale** needs paid
  infrastructure. Requirements are written so scale becomes a deployment change
  rather than a rewrite.
- **A3. Free-tier LLM.** The current Gemini free tier gives 20 requests per day per
  model, roughly 60 per day across the fallback rotation. Tsenta's volumes assume
  paid inference. Any per-application LLM work must stay inside the existing budget
  manager, or the tier has to change.
- **A4. Charging.** Quiver has no payment integration and no reason to bill its
  only user. Pricing tiers are specified for completeness but are the last thing to
  build.

---

## 4. Baseline: what Quiver has today

| Area | Present | Where |
|---|---|---|
| Discovery sources | Y Combinator, HN "Who is hiring", remote boards (RemoteOK, Remotive, WeWorkRemotely, WorkingNomads, Landing.jobs, The Muse, arbeitnow), hidden portals | `agent/sources.py` |
| ATS board readers | 6: Greenhouse, Lever, Ashby, SmartRecruiters, Workable, Recruitee | `fetch_ats_jobs` |
| ATS submission | Verified on Greenhouse and Ashby; a generic driver attempts others | `agent/applier.py` |
| Matching | Keyword and alias scoring, fit score 0-100, 10 role categories, 1-3 year experience gate | `agent/matcher.py`, `agent/categories.py` |
| Resume tailoring | LaTeX, two pages, relevance-ranked projects, house-style audit as a hard gate | `api/latex_resume.py`, `api/resume_audit.py` |
| Cover letters | Generated per job, BeHuman-scrubbed | `applier.cover_letter` |
| Apply | User-selected job ids only, dry run, headed browser, receipt data, screenshots, post-submit verdict polling | `applier.apply_to_ids` |
| Job statuses | `new, matched, skipped, queued, applied, failed, closed, stale, duplicate` | `agent/sqlite_store.py` |
| Application statuses | `pending, filled, submitted, failed, skipped` | `agent/sqlite_store.py` |
| Retry queue | `jd_fetch`, `resume_build`, `verify_email_greylist`, with backoff and dead-lettering | `agent/schema.py` |
| Scheduler | In-process, quiet hours, whitelist of `agent_discover` and `agent_tasks` | `api/scheduler.py` |
| LLM | Gemini free tier, per-model day-quota rotation, daily budget with per-purpose shares, response cache | `agent/llm.py` |
| Outreach | Cold email to verified founders and recruiters over Gmail SMTP | `agent/outreach.py` |
| Surfaces | Web dashboard only: Jobs, Resume, Outreach | `Frontend/src/tabs` |
| Reply tracking | None | |
| Public API | None | |
| Accounts and billing | None | |

---

## 5. Requirements

Priority: **P0** parity-critical, **P1** important, **P2** desirable.

### 5.1 Find

- **FR-F1 (P0).** Discovery runs on a schedule without the user present, recording
  per-source counts and duration for every run. *Partly built: the scheduler
  exists, per-source telemetry does not.*
- **FR-F2 (P0) [DONE].** Every tracked job carries a match score and a readable reason for
  that score, both visible in the jobs table. *Score exists; `fit_reason` is stored
  but only surfaced on skipped rows.*
- **FR-F3 (P0) [DONE].** The user can paste a job URL and have Quiver detect the ATS,
  fetch the description, score it and queue it, without that job coming from a
  discovery source. Equivalent to Tsenta's `POST /detect`.
- **FR-F4 (P1).** Expand ATS board readers from 6 towards the 28 systems in section
  2.2, prioritised by how many target companies use each. Each new reader is one
  function plus one recorded fixture (see NFR-4).
- **FR-F5 (P1).** Keep a persistent company-to-board registry so career pages are
  re-scanned on a cadence rather than rediscovered every run, with `last_scanned_at`
  per board. *Partly built.*
- **FR-F6 (P1).** Search and filter tracked jobs by title, location, salary where
  published, work arrangement, category, portal and match score. *Partly built:
  category, portal, status and free text exist.*
- **FR-F7 (P2).** Notify the user when a high-match role appears, by desktop
  notification or email, within one scan cycle of publication.
- **FR-F8 (P2).** Show a live scan line during discovery ("scanning X... n new"),
  matching Tsenta's Find display. The SSE console already carries the data.

### 5.2 Prep

- **FR-P1 (P0) [DONE].** Three tailoring modes exactly as Tsenta defines them: **Off**,
  **Honest** (reword using only what the profile already contains), **Aggressive**
  (rewrite freely for keyword match). Aggressive requires review before submission.
  *Quiver has one mode today, closest to Honest.*
- **FR-P2 (P0) [DONE].** A per-application diff view: original bullet, rewritten bullet, a
  change count, and Edit and Approve controls. Nothing may be submitted from an
  unapproved tailored document while auto-approve is off.
- **FR-P3 (P0) [DONE].** An auto-approve toggle, independent of the review-the-form toggle
  in FR-A4.
- **FR-P4 (P1).** Multiple named resume profiles: create, duplicate, import, mark a
  default, and choose which profile an application uses. *Quiver has one
  `profile.yaml` and three built variants.*
- **FR-P5 (P1).** Cover letters generated only where the form accepts or requires
  one, and attached as a file when a file is wanted rather than pasted into a text
  box. *Currently generated for every application.*
- **FR-P6 (P1).** The profile carries the full section set from 2.3, including
  application defaults reused across forms and user-defined custom sections. *Most
  exist; custom sections do not.*
- **FR-P7 (P0).** Every tailored document must pass the house-style audit before it
  can be attached to an application. *Built; keep it.*
- **FR-P8 (P0) [DONE].** No tailoring mode, Aggressive included, may introduce an employer,
  technology, metric, date or credential absent from the profile. This is a
  mechanical gate, not a prompt instruction.

### 5.3 Apply

- **FR-A1 (P0).** Submission works across the systems in 2.2, tracked as a per-ATS
  capability table with two independent flags, `detects` and `submits`. That table
  is visible in the UI so the user knows before selecting a job.
- **FR-A2 (P0) [DONE].** Adopt Tsenta's application status machine in place of Quiver's:
  `queued`, `running`, `needs_review`, `submitted`, `failed`. Map the existing
  `pending/filled/submitted/failed/skipped` onto it. `needs_review` is the state
  Quiver currently has no name for and instead treats as failure.
- **FR-A3 (P0) [DONE].** Every application produces a receipt: fields filled, fields
  skipped, generated answers, documents submitted, final result, viewable
  afterwards. *Data is captured; there is no receipt view.*
- **FR-A4 (P1).** Optional review of the filled form before submit, on systems where
  the form can be paused.
- **FR-A5 (P1).** Handle logins and one-time codes instead of failing on them.
  Tsenta exposes this as `POST /applications/{id}/otp` with an
  `application.needs_otp` webhook. Quiver records a login wall as a terminal failure
  today.
- **FR-A6 (P0).** Never submit twice to the same posting; keep the `dedupe_hash`
  guard. *Built.*
- **FR-A7 (P0).** Never guess a factual answer. A required question the profile
  cannot answer truthfully stops the application and names the question that did it.
  *Built; keep it.*
- **FR-A8 (P1).** Batch apply over many selected jobs, with per-job results and a
  running progress line. *Partly built.*
- **FR-A9 (P2) [MT].** Auto Apply: the agent selects and submits eligible roles on
  its own, bounded by a match threshold, a daily cap and the user's filters. This is
  the one behaviour Quiver forbids today, structurally: `apply` requires explicit
  `--job-ids`. Enabling it is a product decision with real consequences and must be
  opt-in, capped and revocable.
- **FR-A10 (P1).** Apply to several jobs in parallel with a bounded worker pool,
  instead of strictly one at a time.

### 5.4 Track

- **FR-T1 (P0) [DONE].** Tracker statuses **Applied, Interviewing, Offer, Rejected,
  Ghosted**, editable by hand at any time. *Not built.*
- **FR-T2 (P0) [DONE].** Read the user's mailbox over IMAP with the existing Gmail app
  password and link each incoming message to the application it belongs to, by
  `Message-ID`, thread, sender domain and company name.
- **FR-T3 (P0) [DONE].** Classify each linked message as one of: acknowledgment, interview,
  assessment, offer, rejection, reminder, verification. Rule-first with the LLM as
  fallback, to stay inside the daily budget.
- **FR-T4 (P0) [DONE].** Advance tracker status automatically only on a high-confidence
  link. Otherwise leave the status alone and mark the message for review.
- **FR-T5 (P1) [DONE].** An application inbox grouped by the classes in FR-T3, with an
  unread count.
- **FR-T6 (P1).** Manual add and CSV import of applications made outside Quiver.
  *Not built in Phase 1: it only matters once there is a history worth importing,
  and nothing else depends on it.*
- **FR-T7 (P1) [DONE].** Bounce detection: a hard bounce demotes the guessed address
  pattern for that domain so the same wrong pattern is not reused.
- **FR-T8 (P2).** Pipeline view: counts by stage, reply rate and interview rate by
  source, category and match decile. *Counts by stage are built; the rates need
  more applications than exist to mean anything yet.*

### 5.5 Surfaces

- **FR-S1 (P0) [DONE].** Web dashboard covering Find, Prep, Apply and Track as four
  first-class areas. *Three tabs exist; Track does not.*
- **FR-S2 (P1).** Chrome extension: on any job posting, one click sends the URL to
  Quiver, which detects the ATS, tailors and applies. The highest-value surface
  after the dashboard, because it needs no scale to be useful.
- **FR-S3 (P1).** MCP server exposing Quiver to Claude Code and other agents:
  discovery with filters, apply single and batch, resume profile management, tracker
  read and import, inbox read and unread count, profile edit, remaining allowance.
  Local stdio transport first; HTTP with OAuth only if Quiver becomes hosted.
- **FR-S4 (P2).** CLI parity with the MCP tool surface. *Partly built:
  `python -m agent.runner {discover,resumes,apply,outreach,tasks}`.*
- **FR-S5 (P2) [MT].** iOS and Android apps.
- **FR-S6 (P2) [MT].** A text-message surface over WhatsApp or iMessage for matching
  and approval.

### 5.6 Developer API [MT]

- **FR-D1 (P1).** A versioned HTTP API under `/v1` with bearer-token auth, mirroring
  the endpoint set in 2.6. Reuse Tsenta's shapes where there is no reason to differ;
  a familiar API is easier to write clients against.
- **FR-D2 (P1).** Application lifecycle exposed exactly as FR-A2, with the same
  terminal guarantee: an application ends `submitted` or `failed` and nothing else.
- **FR-D3 (P1).** Webhooks for `application.running`, `application.needs_review`,
  `application.needs_otp`, `application.submitted`, `application.failed`.
- **FR-D4 (P1).** `GET /ats` returns the live capability table from FR-A1, so clients
  read supported systems rather than hard-coding them.
- **FR-D5 (P1).** The error vocabulary from 2.6, returned as a stable machine-readable
  code plus a human message.
- **FR-D6 (P2).** Per-key rate limiting, with `rate_limited` as the refusal.

### 5.7 Account, allowance and billing [MT]

- **FR-B1 (P2).** Accounts with isolated data per user.
- **FR-B2 (P2).** An application allowance counted per 30 days, decremented **only on
  successful submission**. Failed and skipped attempts must not consume it.
- **FR-B3 (P2).** Plan tiers differing in volume only, never in features.
- **FR-B4 (P2).** A free allowance for a new account with no card.
- **FR-B5 (P2).** `GET /usage` reporting remaining allowance, and the same figure in
  the dashboard header.

### 5.8 Non-functional

- **NFR-1.** No LangChain, LangGraph or comparable agent framework. Plain Python on
  the existing runner, subprocess and SSE pattern.
- **NFR-2.** Every LLM call goes through the budget manager with a declared purpose.
  Live application answering is never starved before bulk work is.
- **NFR-3.** Honest reporting throughout: a failure is recorded with its reason and a
  screenshot, nothing is silently skipped, and a submitted application means the form
  was accepted, verified by the post-submit verdict check.
- **NFR-4.** Each supported ATS carries an offline HTML fixture and a test driving the
  fill logic against it, so adding a system cannot regress the others.
- **NFR-5.** Storage stays backend-agnostic: SQLite and MongoDB keep function parity,
  enforced by the shared schema module.
- **NFR-6.** Retention and privacy: application data stays local, is never sold or
  sent anywhere except the employer's own form, and is deletable on request.
- **NFR-7.** The test suite stays green and grows with each area. Current count: 48.

---

## 6. Gap summary

| Capability | Tsenta | Quiver now | Gap |
|---|---|---|---|
| Scheduled discovery | Continuous, 50k pages | Scheduled, ~9 sources | Scale, not behaviour |
| ATS detection | 28 systems | 6 board readers | 22 systems |
| ATS submission | 19+ in product | 2 verified | Large |
| Paste a URL and apply | `POST /detect` | Absent | Build |
| Tailoring modes | Off / Honest / Aggressive | One mode | Build 2 modes plus gate |
| Review before send | Diff and Approve | Absent | Build |
| Multiple resume profiles | Yes | One profile, 3 variants | Build |
| Receipts | Per application | Data captured, no view | Build view |
| `needs_review` state | Yes | Treated as failure | Build |
| Login and OTP handling | Yes | Terminal failure | Build |
| Reply tracking | IMAP and classification | Absent | Build |
| Tracker statuses | 5 stages | Job statuses only | Build |
| Inbox classification | 7 classes | Absent | Build |
| Chrome extension | Yes | Absent | Build |
| MCP server | Hosted, OAuth | Absent | Build, local first |
| Mobile and iMessage | Yes | Absent | Out of scope for now |
| Public API | Full | Absent | Build if multi-tenant |
| Accounts and billing | Full | Absent | Build if multi-tenant |
| Auto Apply | Pro and Power feature | Forbidden by design | Product decision |

---

## 7. Delivery phases

Scope decisions taken on 2026-08-21:

| Question | Answer |
|---|---|
| How far to take the `apple-design` skill | **Motion and typography; surfaces stay flat.** Springs, pointer-down feedback, interruptible transitions, size-specific tracking and leading, and the eight principles. No `backdrop-filter`, no gradients, no glow: the opaque-surface rule in `index.css` stands. |
| Scope | **Single user, phases 0 to 4.** The `[MT]` items in 5.6 and 5.7 are out: no public API, accounts, allowances or billing. |
| Auto Apply (FR-A9) | **Build it with a review queue.** The agent selects automatically; a human approves the batch before anything is submitted. `apply` still refuses to run without explicit job ids. |

### Status

| Phase | Name | Requirements | Status |
|---|---|---|---|
| **0** | Apple design foundation | Motion primitives, press feedback, typography, retrofit of the existing tabs | **Completed 2026-08-21** |
| **1** | Close the loop (Track) | FR-T1, FR-T2, FR-T3, FR-T4, FR-T5, FR-T7, FR-A2, FR-A3, FR-S1 | **Completed 2026-08-21** |
| **2** | Control over what is sent | FR-P1, FR-P2, FR-P3, FR-P8, FR-F2, FR-F3 | **Completed 2026-08-22** |
| **3** | Reach | FR-A1, FR-F4, FR-A5, FR-A10, NFR-4 | Not started |
| **4** | Surfaces and Auto Apply | FR-S2, FR-S3, FR-P4, FR-A9 | Not started |

**Out of scope by decision:** FR-D1 to FR-D6 and FR-B1 to FR-B5 (multi-tenant
only), FR-S5 and FR-S6 (mobile and iMessage).

A requirement is marked `**[DONE]**` next to its identifier in section 5 only
once it is built and verified. Anything deliberately skipped keeps a one-line
reason instead of a completion mark.

### Phase 0 — what was built

`Frontend/src/lib/motion.js` holds the whole motion vocabulary: two springs
(`ui`, damping 1.0 / response 0.35 for anything that simply appears;
`momentum`, damping 0.8 / response 0.3 reserved for gesture-driven motion),
Apple's momentum `project()` and a `rubberband()` for boundaries.
`springFor()` downgrades to a cross-fade under `prefers-reduced-motion`.

`Frontend/src/lib/usePress.js` puts feedback on pointer-down instead of click,
with pointer capture and 10px hysteresis so a press cancels when you drag away
and re-arms when you come back. A `.press` CSS class gives every other control
the same instant response through `:active`.

Typography is now size-specific: headings carry negative tracking down to
`-0.02em` at 26px, micro text carries `+0.01em`, and leading tightens as size
grows. Sizes moved from px to rem so the browser's own text setting scales the
layout with the text.

`Disclosure` and the tab bar were converted from CSS transitions to springs,
because a transition always plays out to its target before accepting a new one.
Verified by interrupting a Disclosure 90ms into opening: it reverses from 172px
rather than completing first. Reduced motion verified separately — the press
transform disappears, the opacity feedback stays.

### Phase 1 — what was built

A fourth screen, **Track**, and the machinery behind it. `agent/inbox.py` reads
the mailbox over IMAP using the Gmail app password the outreach sender already
uses, links each message to the application it belongs to, classifies it, and
advances the pipeline. `python -m agent.runner inbox` runs it; the scheduler
fires it every 20 minutes, ahead of the retry queue, because an interview
invitation is time-sensitive in a way a failed JD fetch is not. The IMAP
connection is opened read-only, which is why it was safe to make schedulable.

Linking is ranked rather than guessed: a threaded reply scores 0.98, a matching
sender domain 0.9, and a company name in the subject only 0.65 — too low to move
anything. Only a link at or above 0.75 may advance a stage, and only for a class
whose meaning is unambiguous; an acknowledgment or a reminder moves nothing.
Stages never run backwards, and a stage set by hand is never overruled.

Two things were found by running it against the real mailbox rather than
fixtures. First, classifying every message through the model turned a
seven-second scan into a four-minute one and would have drained a day's LLM
budget on ordinary mail, so the model is now asked only about messages that
already linked to an application, capped at eight per run. Second, and more
important: almost no recruiting mail arrives from the employer's own domain.
The real Interfere rejection came from `no-reply@ashbyhq.com`, scored 0.65 as a
mere subject match, and moved nothing. Known ATS mailer domains are now
recognised, because an ATS only writes to you about applications you actually
made — with that fixed, the same message correctly moved the Interfere
application to **rejected**.

The application state machine moved to Tsenta's (`queued`, `running`,
`needs_review`, `submitted`, `failed`). `needs_review` is the state that
previously had no name: a form the agent filled but stopped on, which was being
recorded as `failed` and so made a pause look like a rejection.
`/api/agent/receipt/{id}` finally exposes what was actually submitted — the
applier had been capturing it all along with nowhere to read it.

Verified end to end against the live mailbox: 16 messages read in 19 seconds,
2 linked, the Interfere rejection detected and the stage moved. 75 tests, with
25 new ones covering the linker, the rule classifier and the ATS-mailer case.

### Phase 2 — what was built

Three tailoring modes exactly as Tsenta defines them, in
`settings.tailoring.mode`. **Off** makes no model call at all. **Honest** is
what Quiver already did. **Aggressive** gets its own prompt that may restructure
a bullet and reach for the posting's vocabulary, and always requires review.

The important part is what the modes do *not* change. `api/resume_facts.py` is a
mechanical gate applied identically in every mode: a rewritten bullet may not
contain a number, employer or technology that the profile does not carry. "Never
invent a metric" has been in the rewrite prompt since the beginning and models
mostly obey it, but a resume goes to a real employer with the user's name on it,
and "mostly" is the wrong standard. A rewrite that fails the gate is discarded
and the original kept.

Getting that gate right took three passes, and each failure is worth recording.
Exact token matching rejected "European clients" becoming "clients across
Europe", which is ordinary rewording and would have made the gate something you
switch off. Relaxing it to stem matching then let sentence-initial verbs read as
proper nouns, so "Mentored 10 developers" was flagged. Skipping the first word
fixed that and opened a hole in the one position nobody checks: "Stripe payments
were integrated" sailed through. The first word is now skipped only when it is
actually verb-shaped. Numbers stay matched exactly, because 4M and 4.2M are
different claims.

`auto_approve` off means a rewritten resume is recorded unapproved and
`apply_to_ids` refuses to send it — otherwise the setting would be decorative.
The Jobs table shows a **review** link on any resume that is waiting, opening a
per-bullet before/after where each line can be edited. Approving after an edit
rebuilds the PDF rather than approving as-is: the file on disk still carries the
model's wording until it does, and approving text that differs from the compiled
document would ship the version nobody read.

`POST /api/agent/job-from-url` tracks a job from a pasted link, running the same
pipeline a discovered job goes through. Testing it against real postings found
two things worth having. Greenhouse's `job-boards` host renders client side, so a
plain GET returns the board's *index* — long enough to pass the length check, so
the first attempt stored the company blurb as the description and a neighbouring
vacancy's title as the job. Content that reads as a board index now goes to the
renderer however long it is. And a posting that has been taken down is now told
apart from a page that could not be read: the first returns 410 and stores
nothing, the second suggests pasting the description by hand.

`fit_reason` is now shown on every row rather than only on filtered-out ones — a
score with no reasoning behind it is not something anyone can act on. And the
`Field` component wires each label to its control automatically; before this the
labels were decoration, focusing nothing when clicked and leaving every input
unnamed to a screen reader.

91 tests. Both storage backends still expose 59 identically-signed functions.

---

## 8. What cannot be matched on the current footing

Stated plainly so nobody plans around it.

- **Continuous monitoring of 50,000 career pages.** Needs always-on hosting and a
  crawl budget. A scheduled scan of a few hundred boards is the honest local
  equivalent.
- **100 applications per minute.** Needs a browser farm. One machine running headed
  Chromium manages a few per minute at best.
- **Per-application LLM work at volume.** The current free tier allows roughly 60
  model calls per day in total. Tailoring, answering and classifying at Tsenta's
  volumes needs paid inference.
- **iOS and Android apps, and iMessage.** Each is a separate product with its own
  store, review process and push infrastructure.
- **Captcha solving.** Tsenta does not claim it either. Quiver detects a real
  challenge and stops, which stays correct.
- **LinkedIn and Indeed ingestion.** Blocked by anti-bot measures and their terms.
  Not attempted.
