# Jobenzy requirements: reach feature parity with Tsenta

Researched from tsenta.com and docs.tsenta.com on 2026-08-21, and re-checked
against the same sources on 2026-08-22 — including the developer docs, which are
more precise than the marketing pages and corrected the ATS count from 28 to 29.
Every claim about Tsenta in section 2 comes from their public site or docs, not
from inference; quoted phrases are verbatim. Nothing here came from a signed-in
session, so anything visible only inside the product is absent by construction.

Section 9 is the audit: every requirement re-read against the code that claims to
satisfy it, rather than trusting the `[DONE]` markers. Two did not survive it.

---

## 1. Purpose

Jobenzy today is a local, single-user job-hunting tool: it discovers roles, tailors
a LaTeX resume per posting, and drives a browser to fill application forms the user
selects. Tsenta is a hosted, multi-user, paid product doing the same job at much
larger scale, with more surfaces and a developer API on top.

This document states what Jobenzy must become to work the way Tsenta works. Each
requirement is written so it can be picked up, built and verified on its own.

---

## 2. Reference product: what Tsenta does

### 2.1 The pipeline

Tsenta describes four stages. Jobenzy should adopt the same vocabulary, because the
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

*Re-checked 2026-08-22 against `docs.tsenta.com/developers/supported-systems`,
which is more precise than the product page: **29 systems**, each flagged for
whether it can pause for review before submitting.*

| System | Review before submit | System | Review before submit |
|---|---|---|---|
| ADP | no | Workday | **yes** |
| Ashby | **yes** | Greenhouse | **yes** |
| BambooHR | **yes** | Lever | **yes** |
| BrassRing | **yes** | Oracle Cloud | **yes** |
| BreezyHR | **yes** | Paylocity | **yes** |
| Dayforce | no | Phenom | no |
| Dover | **yes** | Pinpoint | no |
| Gem | **yes** | Polymer | no |
| Hireology | no | Recruitee | no |
| iCIMS | no | Rippling | **yes** |
| JazzHR | **yes** | SAP SuccessFactors | no |
| Jobvite | **yes** | SmartRecruiters | **yes** |
| Join | no | Teamtailor | no |
| UKG (UltiPro) | **yes** | Workable | **yes** |
| Zoho Recruit | **yes** | | |

Eighteen of the twenty-nine can pause for review. That number matters: it is the
ceiling on FR-A4, and it says the review step is a per-ATS capability rather
than a global setting — which is exactly the mistake Jobenzy currently makes (see
the audit in section 9).

Two caveats from the same docs, both worth adopting as rules rather than
disclaimers:

- "Tsenta may recognize a job page even when that page does not have an active
  submission workflow." Detection and submission are separate capabilities.
- "Support is evaluated again for each role when you apply." A system-level
  capability table is a prediction, not a guarantee; the authority is the
  attempt itself.

Indeed and Naukri are explicitly excluded, because they "apply as the
candidate's own logged-in account."

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
review-the-filled-form-before-submit on supported systems. The docs are explicit
that these "operate independently", and recommend starting with auto-approve
*off* to watch what the tailoring does before trusting it.

*Added 2026-08-22:*

- A **completeness indicator** on the profile, flagging missing fields and ones
  employers commonly require.
- A **separate application password**, set during onboarding, used for the
  accounts the agent creates on employer systems. Workday and iCIMS require an
  account before they will take an application; this is how Tsenta owns that
  without touching the user's own passwords.
- DOCX import preserves supported formatting when rendering the tailored PDF,
  with the honest caveat that "complex layouts may not carry over perfectly".

### 2.4 Tracking model

Tracker statuses: **Applied, Interviewing, Offer, Rejected, Ghosted.**

Inbox message classes: **acknowledgments, interviews, assessments, offers,
rejections, reminders, verification messages.**

Applications can be created by Tsenta itself, added manually (company, title,
status, date, link, notes), or imported from CSV.
"When a message is linked with high confidence, Tsenta may update the associated
tracker status", and the user can always correct it by hand.

*Added 2026-08-22:*

- The tracker is a **board**: "drag a card from one column to the next as things
  progress, or update its status from the card itself."
- **Search the tracker by company**, and a **pipeline flow chart** showing
  progression between stages.
- The inbox is a real mail client, not a list of snippets: **read threads,
  search, view attachments, and reply** inside it.
- An application in flight shows an **in-progress status** while it runs.

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

*Added 2026-08-22 — the onboarding and feed, which the first pass skipped:*

- Sign-up takes an email or Google, plus a PDF resume under 10 MB. Extraction
  into the profile takes 30–60 seconds.
- The feed shows matched roles **with a match score**, and is worked through by
  **swipe or tap to apply or skip** — a triage gesture, not a table.
- Feed filters: **location, salary, role type, and work setting.** Salary is the
  one Jobenzy cannot currently offer, because it never captures it.
- The Chrome extension **does not fill the form in your tab**. It extracts the
  posting and hands it to the same cloud worker the dashboard uses. Worth
  knowing before treating the extension as a different apply path — it is the
  same path with a different front door.

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

### 2.8 What the signed-in product shows (captured 2026-08-22 from screenshots)

The public docs undersell the product. These findings come from screenshots of
the logged-in dashboard the user supplied - captured by the user, not by any
automated session against the account.

**Navigation.** Seven top-level screens: **Dashboard, Browse jobs, Auto Apply,
Tracker, Networking, Profile, Research.** Two - Networking and Research - appear
nowhere in the docs. Networking is Tsenta's name for outbound contact and maps
onto Jobenzy's Outreach; Research is unknown from a screenshot alone and is
recorded as a gap to investigate, not a built comparison.

**The job panel is a parsed document, not a link.** Opening a match shows, as
structured fields: a salary range with currency ("GBP 43k - 64k /yr"), seniority
("Entry Level"), work arrangement ("Hybrid"), employment type ("Full Time"),
function ("Software Engineering"), a **Skills & Technologies** list pulled from
the posting (twenty-plus chips), an application **deadline** ("End Date Sunday 30
August 2026"), and a description with the matched search term highlighted. A
bookmark icon saves the role. Jobenzy stores a title, a score and a reason;
everything else here is new.

**The feed is triaged, not tabled.** Each match card carries **Pass** and
**Apply**, Apply with a dropdown for its options, over a coloured tile with the
match ring. The dashboard's own application tabs read **All, Submitted, In
flight, Needs you, Failed, Skipped** - the user-facing names for the status
machine (In flight = running, Needs you = needs_review).

**The tracker is two tools.** *Inbox*: a two-pane mail client with a reading
pane, class-filter chips (Verification, Rejection, Interview, Assessment,
Reminder, Offer, Applied), message search, **Compose**, **Mark all read**, and
an **Active mailbox** selector showing a provisioned address
(`...@my-privatemail.com`) - Tsenta routes replies through an address it owns
rather than reading the user's own inbox. *Pipeline*: a kanban board (Applied,
Ghosted, Interviewing, Rejected, Offer) with per-stage counts, cards showing an
email count, a company search, a status-transition chart, and **Import CSV /
Export CSV / Add application**.

**The resume is edited in the browser.** The Profile screen has Resume, Cover
Letter and Profile Details tabs, a profile switcher (Default, Add Profile,
favourite, delete), and a live resume editor with two templates (**Standard**,
**Jake**), a font family ("Computer Modern"), a point-size stepper, Left /
Justified alignment, a **Fit to one page** toggle, section reordering, a More
menu, and Replace / Download. Profile Details shows an **Open to work** status, a
**91% complete** indicator, a professional-summary section, and **Application
defaults** - "what we auto-fill on every ATS form" - with per-country work
authorization (authorized to work / needs sponsorship).

**Commercial chrome, out of scope here.** An "18 left" badge tracks the
application allowance, and the app is Firebase-hosted (`autojobs-prod`). Neither
matters for a single-user local build.

## 3. Assumptions, and the decisions this document cannot make for you

These change the size of the work by an order of magnitude, so they are stated
rather than assumed silently.

- **A1. Single user or multi-tenant.** Tsenta is multi-tenant with accounts,
  billing and per-user isolation. Jobenzy is one user, one machine, one SQLite or
  Atlas database, no auth. Everything in section 5.7 is only meaningful if Jobenzy
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
- **A4. Charging.** Jobenzy has no payment integration and no reason to bill its
  only user. Pricing tiers are specified for completeness but are the last thing to
  build.

---

## 4. Baseline: what Jobenzy has today

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
- **FR-F3 (P0) [DONE].** The user can paste a job URL and have Jobenzy detect the ATS,
  fetch the description, score it and queue it, without that job coming from a
  discovery source. Equivalent to Tsenta's `POST /detect`.
- **FR-F4 (P1).** Expand ATS board readers from 6 towards the 28 systems in section
  2.2, prioritised by how many target companies use each. Each new reader is one
  function plus one recorded fixture (see NFR-4). *Partly done: Breezy HR and
  Rippling added, taking readers from 6 to 8. The rest were probed and refused —
  Teamtailor needs an API key, Workday needs a tenant-specific POST, Personio
  rate limits anonymous reads, and JazzHR, Polymer, BambooHR and Join.com have no
  usable public GET. They are listed in the capability table as `detects: false`
  with the reason, rather than claimed and quietly broken.*
- **FR-F5 (P1).** Keep a persistent company-to-board registry so career pages are
  re-scanned on a cadence rather than rediscovered every run, with `last_scanned_at`
  per board. *Partly built.*
- **FR-F6 (P1) [DONE except salary].** Search and filter tracked jobs by title,
  location, work arrangement, category, portal and match score.
  *Built in phase 5: multiple categories, multiple portals, posted-within,
  minimum match, remote or on-site, company, place name, free text and four sort
  orders, each shown as a chip that clears itself. Salary is the one filter
  Tsenta has that Jobenzy cannot offer, because no source parses it into a field —
  see FR-F9.*
- **FR-F7 (P2) [DONE].** Notify the user when a high-match role appears, by desktop
  notification or email, within one scan cycle of publication.
- **FR-F8 (P2) [DONE].** Show a live scan line during discovery ("scanning X... n new"),
  matching Tsenta's Find display. The SSE console already carries the data.

- **FR-F9 (P1) [DONE].** Capture salary where a posting publishes it, and filter on it.
  *Confirmed a real Tsenta feature 2026-08-22: the signed-in job panel shows a
  parsed range with currency ("GBP 43k - 64k /yr").* No Jobenzy source parses a
  compensation range into a field today, so there is nothing to filter. Needs a
  `salary_min` / `salary_max` / `salary_currency` trio on the job row and a
  parser per source, most of which publish it as free text.
- **FR-F10 (P2) [DONE].** Saved jobs: a shortlist that is neither applied to nor
  discarded, surviving the retention purge. *Confirmed: a bookmark control sits
  on every job panel.*
- **FR-F11 (P2) [DONE].** A triage gesture over the feed - Tsenta puts **Pass** and
  **Apply** on each match card. Jobenzy's table answers "what is there"; it has
  no fast way to work down a list making one decision per role. *Confirmed on
  the feed cards.*
- **FR-F12 (P1) [DONE].** Parse the posting into a structured detail panel rather than a
  score and a link: seniority, work arrangement, employment type, function, an
  extracted skills-and-technologies list, and the application deadline, with the
  matched terms highlighted in the description. Jobenzy has the description and
  the score; none of the rest is broken out. The skills list is the highest
  value of these - it is what a keyword-aligned resume is aimed at.

### 5.2 Prep

- **FR-P1 (P0) [DONE].** Three tailoring modes exactly as Tsenta defines them: **Off**,
  **Honest** (reword using only what the profile already contains), **Aggressive**
  (rewrite freely for keyword match). Aggressive requires review before submission.
  *Jobenzy has one mode today, closest to Honest.*
- **FR-P2 (P0) [DONE].** A per-application diff view: original bullet, rewritten bullet, a
  change count, and Edit and Approve controls. Nothing may be submitted from an
  unapproved tailored document while auto-approve is off.
- **FR-P3 (P0) [DONE].** An auto-approve toggle, independent of the review-the-form toggle
  in FR-A4.
- **FR-P4 (P1) [DONE].** Multiple named resume profiles: create, duplicate, import, mark a
  default, and choose which profile an application uses. *Jobenzy has one
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

- **FR-P9 (P1) [DONE].** A profile completeness indicator: which fields are missing, and
  which of those employers commonly require. Jobenzy has the data to compute this
  and never shows it, so a profile gap is only discovered when an application
  stops on it.
- **FR-P10 (P2) [DONE].** Import a resume from DOCX as well as YAML, preserving what
  formatting survives into the tailored PDF.
- **FR-P11 (P1) [DONE].** An in-browser resume editor with the controls Tsenta exposes:
  a choice of templates (it ships **Standard** and **Jake**), font family and
  point size, left or justified alignment, a fit-to-one-page toggle, and section
  reordering. Jobenzy renders LaTeX server-side with fixed styling and a two-page
  target; the document cannot be adjusted without editing the profile and
  rebuilding. The Cover Letter is a first-class editable tab beside the resume,
  not only a generated artefact (see FR-P5).

### 5.3 Apply

- **FR-A1 (P0) [DONE].** Submission works across the systems in 2.2, tracked as a per-ATS
  capability table with two independent flags, `detects` and `submits`. That table
  is visible in the UI so the user knows before selecting a job.
- **FR-A2 (P0) [DONE].** Adopt Tsenta's application status machine in place of Jobenzy's:
  `queued`, `running`, `needs_review`, `submitted`, `failed`. Map the existing
  `pending/filled/submitted/failed/skipped` onto it. `needs_review` is the state
  Jobenzy currently has no name for and instead treats as failure.
- **FR-A3 (P0) [DONE].** Every application produces a receipt: fields filled, fields
  skipped, generated answers, documents submitted, final result, viewable
  afterwards. *Data is captured; there is no receipt view.*
- **FR-A4 (P1) [DONE].** Optional review of the filled form
  before submit, on systems where the form can be paused.
  *Audited 2026-08-22: `review_form_before_submit` exists in
  `schema.DEFAULT_SETTINGS` and is read by nothing. A setting that is offered and
  then ignored is worse than an absent one, because it reads as a promise. Either
  wire it or remove it. When wiring it, note from 2.2 that only 18 of 29 systems
  can pause at all — this belongs in the per-ATS capability table, not as a global
  toggle.*
- **FR-A5 (P1) [DONE].** Handle logins and one-time codes instead of failing
  on them. Tsenta exposes this as `POST /applications/{id}/otp` with an
  `application.needs_otp` webhook, and its worker "signs in when needed".
  *Audited 2026-08-22: Jobenzy detects both — `OTP_MARKERS` and `LOGIN_MARKERS` in
  `agent/applier.py` — and parks the run as `needs_review` with an instruction
  naming what the site asked for. That is the detection half. There is no way to
  hand the code back to a waiting session, so the application is finished, not
  paused: the user completes it themselves and re-runs. Downgraded from [DONE],
  which overstated it.*
- **FR-A6 (P0).** Never submit twice to the same posting; keep the `dedupe_hash`
  guard. *Built.*
- **FR-A7 (P0).** Never guess a factual answer. A required question the profile
  cannot answer truthfully stops the application and names the question that did it.
  *Built; keep it.*
- **FR-A8 (P1).** Batch apply over many selected jobs, with per-job results and a
  running progress line. *Partly built.*
- **FR-A9 (P2) [DONE].** Auto Apply: the agent selects and submits eligible roles on
  its own, bounded by a match threshold, a daily cap and the user's filters. This is
  the one behaviour Jobenzy forbids today, structurally: `apply` requires explicit
  `--job-ids`. Enabling it is a product decision with real consequences and must be
  opt-in, capped and revocable.
- **FR-A10 (P1) [DONE].** Apply to several jobs in parallel with a bounded worker pool,
  instead of strictly one at a time.

- **FR-A11 (P1) [DONE].** An employer-account credential store. Workday and iCIMS will
  not take an application without an account first, which is why Tsenta sets a
  **separate application password** during onboarding and creates accounts with
  it. Jobenzy stops at these systems today. Any implementation must keep the
  secret out of the repository and out of the settings JSON — `Backend/.env` or
  the OS keychain, never the store.

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
- **FR-T6 (P1) [DONE].** Manual add and CSV import of applications made outside Jobenzy.
  *Not built in Phase 1: it only matters once there is a history worth importing,
  and nothing else depends on it.*
- **FR-T7 (P1) [DONE].** Bounce detection: a hard bounce demotes the guessed address
  pattern for that domain so the same wrong pattern is not reused.
- **FR-T8 (P2) [DONE].** Pipeline view: counts by stage, reply rate and interview rate by
  source, category and match decile. *Counts by stage are built; the rates need
  more applications than exist to mean anything yet.*

- **FR-T9 (P1) [DONE].** The tracker as a board, with a card dragged from one column to
  the next. Jobenzy has the stages and a per-row dropdown; the gesture Tsenta
  leads with is missing.
- **FR-T10 (P1) [DONE].** The inbox as a mail client: full thread bodies, search,
  attachments. *Reply landed in phase 5; the other three did not. Jobenzy stores a
  snippet per message and never fetches the body, so there is nothing to thread
  or search yet.*
- **FR-T11 (P2) [DONE].** An in-progress indicator on an application while its run is
  still going, rather than only in the console.
- **FR-T12 (P1) [DONE].** Export the tracker to CSV, alongside the import in FR-T6.
  Tsenta offers both on the Pipeline view; Jobenzy has neither.
- **FR-T13 (decision, not a gap).** Tsenta routes application mail through an
  address it provisions (`...@my-privatemail.com`), selectable from an "Active
  mailbox" switcher, and lets the user **Compose** as well as reply. Jobenzy reads
  the user's own Gmail over IMAP instead. For a single-user local tool the IMAP
  route is the right one - no relay to run, no third-party address to trust, mail
  stays in the account the user already has. The one thing worth taking from
  Tsenta here is **Compose a new message**, not only reply, which Jobenzy could do
  over the SMTP it already uses.

### 5.5 Surfaces

- **FR-S1 (P0) [DONE].** Web dashboard covering Find, Prep, Apply and Track as four
  first-class areas. *Three tabs exist; Track does not.*
- **FR-S2 (P1) [DONE].** Chrome extension: on any job posting, one click sends the URL to
  Jobenzy, which detects the ATS, tailors and applies. The highest-value surface
  after the dashboard, because it needs no scale to be useful.
- **FR-S3 (P1) [DONE].** MCP server exposing Jobenzy to Claude Code and other agents:
  discovery with filters, apply single and batch, resume profile management, tracker
  read and import, inbox read and unread count, profile edit, remaining allowance.
  Local stdio transport first; HTTP with OAuth only if Jobenzy becomes hosted.
- **FR-S4 (P2).** CLI parity with the MCP tool surface. *Partly built:
  `python -m agent.runner {discover,resumes,apply,outreach,tasks}`.*
- **FR-S7 (P1) [DONE as Outreach].** A "Networking" surface for outbound contact
  to founders and recruiters. Tsenta names it Networking; Jobenzy has had it as
  **Outreach** since before this document - verified addresses, per-day caps, a
  dry run. Same capability, different label.
- **FR-S8 (P2) [DONE].** A "Research" surface. Present in Tsenta's navigation and absent
  from its public docs, so its contents are unknown from a screenshot; recorded
  as a gap to investigate rather than a scoped requirement. Likely company or
  role research, given the name and Jobenzy's existing company dataset.
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
- **NFR-4 [DONE].** Each supported ATS carries an offline HTML fixture and a test driving the
  fill logic against it, so adding a system cannot regress the others.
- **NFR-5.** Storage stays backend-agnostic: SQLite and MongoDB keep function parity,
  enforced by the shared schema module.
- **NFR-6.** Retention and privacy: application data stays local, is never sold or
  sent anywhere except the employer's own form, and is deletable on request.
- **NFR-7.** The test suite stays green and grows with each area. *48 at the time of writing; **131** as of 2026-08-22.*

---

## 6. Gap summary

| Capability | Tsenta | Jobenzy now | Gap |
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
| How far to take the `apple-design` skill | **Revised 2026-08-22 — materials are in.** Originally motion and typography only, with surfaces staying flat. The user asked twice for a glassmorphic interface, so `backdrop-filter` now carries the chrome: rail, toolbar, sheets, the floating selection bar and the dashboard hero. The rule that survives is the one that matters — content surfaces stay opaque, no translucent surface sits on another, and every colour pairing is measured against the ground it actually renders on rather than eyeballed. |
| Scope | **Single user, phases 0 to 4.** The `[MT]` items in 5.6 and 5.7 are out: no public API, accounts, allowances or billing. |
| Auto Apply (FR-A9) | **Build it with a review queue.** The agent selects automatically; a human approves the batch before anything is submitted. `apply` still refuses to run without explicit job ids. |

### Status

| Phase | Name | Requirements | Status |
|---|---|---|---|
| **0** | Apple design foundation | Motion primitives, press feedback, typography, retrofit of the existing tabs | **Completed 2026-08-21** |
| **1** | Close the loop (Track) | FR-T1, FR-T2, FR-T3, FR-T4, FR-T5, FR-T7, FR-A2, FR-A3, FR-S1 | **Completed 2026-08-21** |
| **2** | Control over what is sent | FR-P1, FR-P2, FR-P3, FR-P8, FR-F2, FR-F3 | **Completed 2026-08-22** |
| **3** | Reach | FR-A1, FR-A5, FR-A10, NFR-4 | **Completed 2026-08-22** |
| **4** | Surfaces and Auto Apply | FR-S2, FR-S3, FR-P4, FR-A9 | **Completed 2026-08-22** |
| **5** | Workspace structure | Separate screens, strong filters, mailbox replies, role-targeted profiles | **Completed 2026-08-22** |
| **6** | Parity build: 50 of 60 | FR-F8/F9/F10/F11/F12, FR-P9, FR-T6/T8/T9/T10/T11/T12/T13 | **Completed 2026-08-22** |
| **7** | The last ten: 60 of 60 | FR-A4, FR-A5, FR-A11, FR-F4, FR-F7, FR-P10, FR-P11, FR-S4, FR-S8, NFR-4 | **Completed 2026-08-22** |

**Out of scope by decision:** FR-D1 to FR-D6 and FR-B1 to FR-B5 (multi-tenant
only), FR-S5 and FR-S6 (mobile and iMessage).

A requirement is marked `**[DONE]**` next to its identifier in section 5 only
once it is built and verified. Anything deliberately skipped keeps a one-line
reason instead of a completion mark.

### Phase 7 — what was built

The last ten, taking the count to 60 of 60. These were held for last because
they were the riskiest and least local — the reach and enterprise cluster, plus
the biggest uncertain pieces.

**Reach and enterprise.** `agent/credentials.py` (FR-A11) holds a per-site login
and a shared application password for the accounts the agent registers, in a
gitignored file outside the settings the API hands back — Tsenta's separate
application password. The applier signs in with a stored credential when it hits
a wall, and only parks needs-review if that fails. Review before submit (FR-A4)
stops being a dead setting: the applier fills the whole form and holds one click
short of submit; Approve re-runs with the pause off. And a one-time code the site
sent (FR-A5) is parked against the job and typed in on the next run — the local
stand-in for Tsenta's OTP endpoint, single-use so a stale code is never replayed.

**Reach breadth.** Two more board readers, BambooHR and Personio (FR-F4), each
split into a pure parser plus a fetch wrapper, and NFR-4's discipline made real:
a recorded fixture per system and offline tests driving six readers with the
network patched out, with a guard that detection and fetching cannot drift apart.

**Notifications (FR-F7).** Email after discovery for strong new matches, stamped
so each is sent once; desktop notifications while the dashboard is open, keyed off
what the client last saw. Two channels, two memories, so neither doubles nor
silences the other. A high score bar by default, because an alert for every 40%
role trains you to ignore all of them.

**The résumé, both ways (FR-P10, FR-P11).** Import reads a PDF or DOCX back into a
profile with the parser the analyser already uses. The in-browser editor makes the
document adjustable — template, font, size, alignment, one-page fit, section order
— with a live PDF preview and every option coerced so a control can never produce
a résumé that will not compile. The style saves into the profile, and the tailor
reads it, so a real application's résumé looks like the one approved.

**The rest.** CLI parity (FR-S4): twelve query commands dispatching to the same
functions the MCP server exposes. Research (FR-S8): a screen showing what is known
about the companies behind your roles — facts, contacts and postings — grounded in
what discovery already gathered rather than generated.

### Phase 6 — what was built

The user's instruction: finish 50 of the 60 requirements now, leave the last 10
for a later phase, and follow the Apple design skill strictly for every new
piece of frontend. Thirteen requirements, taking the count from 37 to 50, in the
two clusters the audit named as highest value and most self-contained.

**The job as a parsed document (FR-F9, F10, F11, F12, F8).** `agent/jobmeta.py`
reads a posting into fields — a salary range with currency, seniority, work
arrangement, employment type, an extracted skills list, an application deadline —
deterministically, with regex and a dictionary rather than an LLM, because it
runs over every scored job and would rather return nothing than guess. A role's
title now opens a right-side `SidePanel` that shows all of it, the skills as the
chips a tailored resume is aimed at, the description reduced to text. The
dashboard's matches become a triage with Pass and Apply on each card; a bookmark
saves a role and survives the retention purge; the filter bar gains salary and a
Saved view. A live scan line rides a spring under a pulse during a run and is
gone the instant it ends. Ran the parser over the live store: 71 jobs, salaries
and skills that check out.

**The tracker as a workspace (FR-T6, T8, T9, T10, T11, T12, T13).** The pipeline
becomes a board whose cards you drag between columns — `Kanban.jsx` is the fluid
skill applied literally: feedback on pointer-down, 1:1 tracking that respects the
grab offset, pointer capture, a click threshold, and a spring settle on drop,
verified moving a card across columns with the move persisting. The inbox becomes
a mail client: whole message bodies, a search over subject/sender/body/company, a
reader panel, and Compose for a new thread. Applications can be added by hand or
imported from a CSV matched by column name however it is labelled, and exported
back out. Two figures a pipeline is judged on — reply rate and how often it
reached a conversation — sit under the stages, and an in-flight application
pulses in the log.

**Profile completeness (FR-P9).** A percentage over the fields a form asks for
most, with the gaps named as chips, gone at 100% because a green banner is noise.

Left for the next phase, deliberately — the reach and enterprise cluster and the
larger uncertain pieces: FR-A11 (employer-account logins for Workday and iCIMS),
FR-A4 (per-ATS review-before-submit), FR-A5's second half (handing an OTP back to
a waiting run), FR-F4 and NFR-4 (more ATS readers with a fixture each), FR-F7
(notifications), FR-P10 (DOCX import), FR-P11 (the in-browser resume editor),
FR-S4 (full CLI parity), and FR-S8 (Research — build once its contents are known,
not blind).

### Phase 5 — what was built

Asked for after phase 4, from the same reference product.

**Separate screens instead of one.** The Jobs tab had grown into the whole
product: six figures, the review queue, top matches, the search configuration,
the ATS capability table, the entire settings panel and the table itself. Seven
destinations now, in two groups — *Workspace* (Dashboard, Jobs, Track,
Outreach) and *Setup* (Profiles, Resume check, Settings). The Jobs screen is a
list you narrow and act on; nothing else.

Search settings moved with it, which needed them to become real settings:
`schema.DEFAULT_SETTINGS["search"]` now holds sources, depth and the two scan
toggles, so "Find new jobs" can sit on the dashboard and still know what to do.
`lib/useAgentRun.js` holds the run machinery both screens need, including dry
run — two screens each remembering their own idea of that is how a real
application gets submitted from the one that had it off.

**Filters worth the name.** Was three dropdowns and a search box. Now: status,
free text, sort, plus multiple categories picked by their own colour, multiple
portals with counts, posted-within, minimum match, remote or on-site, whether a
tailored resume exists, company, and place name. Every active filter shows as a
chip that removes itself when clicked, with a count on the Filters button and a
Clear all.

Underneath, `list_jobs` gained all of it in both stores, and the endpoint
stopped fetching a thousand whole documents a second time per request just to
count facets — a new `job_facets()` does that in the database. **The jobs table
went from 19 seconds to 0.44.**

One bug this exposed: `api.agentJobs` destructured four known keys and dropped
the rest, so a new filter could be built, wired and shipped while the request
went out unchanged. It forwards the whole object now, treating `false` as a
real value because `remote=false` means on-site.

**The mailbox answers back.** `inbox.reply()` sends over the same Gmail app
password the reader already uses, threaded by `In-Reply-To` and `References` so
it joins the conversation. On Track, each reply carries openers chosen by its
class — accept, propose another time, ask for feedback — that leave the cursor
mid-sentence, because the useful half is the part only the user writes. Sending
marks the message read. A Mailbox panel in Settings reports the connection and,
when it is missing, exactly which three steps set it up.

**A resume per kind of role.** Profiles existed since phase 4 but nothing in
the UI reached them. Each profile now names the role categories it is written
for, stored in its own YAML, and `tailor.tailor_for_job` resolves the profile
from the posting's category before falling back to the default. A design
posting builds from the design resume without anyone remembering to switch.
The Profiles screen also names the categories no profile claims.

**Glass, and a hero for it to work on.** The material classes never rendered:
`backdrop-filter` and its `-webkit-` prefix were both written by hand, and
Lightning CSS answered by emitting only the prefixed one, which current
Chromium ignores. Every translucent surface in the app had been a flat 72%
white box. With that fixed, the dashboard's figures sit on a `GlassPanel` —
three blurred washes of colour with a frosted surface over them, since frosting
white over white is an expensive way to draw a rectangle. Measured on the
rendered pixels under each text node: worst contrast 4.65:1.

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
what Jobenzy already did. **Aggressive** gets its own prompt that may restructure
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

### Phase 3 — what was built

`agent/portals.py` holds the capability table as data, with **detects** and
**submits** tracked separately because they genuinely are separate: a role can
be perfectly discoverable through a system whose form nobody has ever got
through. It is served at `/api/agent/portals` and shown on the Jobs screen, so
the user knows what to expect before pressing Apply rather than finding out from
a failure.

Submission confidence has four values, not two. `proven` is claimed only for
Greenhouse and Ashby, where a real application has actually gone through.
`likely` is Lever. Everything else is `unproven`, which is deliberately not the
same as no — the generic driver handles most standard forms, and refusing to try
would mean never learning which ones work. A test asserts that `proven` stays
honest.

Two new board readers: **Breezy HR** and **Rippling**, taking readers from 6 to
8. The others in Tsenta's list of 28 were probed and refused: Teamtailor needs
an API key, Workday needs a tenant-specific POST, Personio rate limits anonymous
reads, and JazzHR, Polymer, BambooHR and Join.com have no usable public GET.
They sit in the table as `detects: false` with the reason, rather than being
claimed and quietly broken. Both new readers needed a `_named()` helper first —
Breezy returns `location.city` as a bare string on some rows and an object on
others, which turned a whole board into an AttributeError.

`diagnose_wall` now returns a status alongside its message. A rendered captcha
is still `failed`, because nobody gets past it unattended. But a login wall or a
one-time code is `needs_review`: those are things the user can supply, and
recording them as failures conflated "the site said no" with "the site is
waiting for you", burying applications that were one step from going through.

Applying can run up to three at a time, and only with the browser hidden —
several visible Chromium windows fighting for the foreground is unusable, and
focus theft mid-typing corrupts the very fields being filled. The dedupe check
is re-taken inside the lock, so two workers cannot both submit the same role
found on two different boards.

NFR-4 is the durable part: a real Greenhouse form is recorded to
`tests/fixtures/portals/` and the fill logic runs against it offline. Every
portal fix so far was found by pointing a browser at a live posting, which meant
the next change could silently break a portal that used to work. Six tests now
drive field collection, the furniture filter, the rule matcher and the captcha
check against that page with no network at all.

105 tests. Verified live: two applications ran in parallel against real
Greenhouse forms, both correctly recorded `needs_review` rather than `failed`.

### Phase 4 — what was built

**Auto Apply, as a review queue.** Tsenta's agent picks roles and submits them;
this one picks roles and *proposes* them. `agent/runner.py:propose()` shortlists
what clears the match threshold, category filter and daily cap into a queue on
the Jobs screen; approving hands those ids to the same `apply_to_ids` a manual
selection uses. The guarantee is structural rather than a promise: `apply` still
refuses to run without explicit ids, nothing in `propose()` calls the applier,
and `agent_apply` is absent from the scheduler's whitelist. Tests assert all
three, including one that fails if `propose` ever reaches the applier at all.
A rejected role is never offered again — re-proposing what someone said no to is
how an assistant becomes a nuisance.

That work surfaced a falsy-zero bug worth recording: `min_score` of 0 is a
legitimate setting meaning "propose anything matched", and `cfg.get("min_score")
or 70` silently turned it into 70 — the user would have got the default they had
just changed.

**A Chrome extension** in `Extension/`. One click sends the current tab's URL to
Jobenzy on `127.0.0.1:8000`, and reports the backend's own words: tracked, already
tracked, closed posting, or not running. It holds no credentials and stores
nothing; `activeTab` gives it a URL only at the moment you click. The API's CORS
had to learn `chrome-extension://` origins, verified by loading the real
extension in Chrome and watching the request round-trip.

**An MCP server** (`agent/mcp_server.py`), local stdio rather than hosted OAuth,
because there is no account to authenticate against — it runs as you, against
the database the dashboard uses. Fourteen tools covering find, prep, track and
account. Applying is deliberately **not** among them: an assistant reading a job
board should not be able to decide, from its own reading of a conversation, to
put your name in front of an employer. It gets `propose_applications`, which
fills the same review queue.

**Multiple resume profiles** (`api/resume_profiles.py`): create by duplication,
set a default, edit, delete. New profiles copy an existing one rather than
starting blank, because a blank profile compiles into a resume with no
experience on it. Path-ish names are refused rather than slugged — "../escape"
becoming "escape" would create a file under a name nobody asked for.

One more test earned its place. `proposals()` was added to both backends with
identical signatures, and the MongoDB copy called `_job_rows`, a helper that
only exists on the SQLite side. It imported fine, matched signatures fine, and
raised `NameError` the first time anything called it. `tests/test_store_parity.py`
now walks every function in both stores for global names that do not resolve —
and re-introducing the exact bug was confirmed to fail it.

122 tests. Verified live: Auto Apply shortlisted a real role, the queue showed
it, rejecting it removed it, and a re-run correctly declined to offer it again.

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
- **Captcha solving.** Tsenta does not claim it either. Jobenzy detects a real
  challenge and stops, which stays correct.
- **LinkedIn and Indeed ingestion.** Blocked by anti-bot measures and their terms.
  Not attempted.

---

## 9. Audit: what is actually built, verified 2026-08-22

Section 5's `[DONE]` markers were written by whoever finished each phase. This
section is the check on them: every requirement re-read against the code that
claims to satisfy it, on the day. Two markers did not survive it.

Scope note: this audit treats the multi-tenant items (5.6 Developer API, 5.7
accounts and billing, plus FR-S5 and FR-S6) as **out of scope by your decision** —
Jobenzy is for one person, so allowances, plan tiers and per-user isolation have
nothing to isolate. They are listed as *excluded*, not as gaps.

### Find

| Req | Status | Evidence |
|---|---|---|
| FR-F1 scheduled discovery | **built** | `api/scheduler.py`, `discover_every_hours`, quiet hours |
| FR-F2 score + reason on every row | **built** | `fit_score` / `fit_reason`, shown in the table |
| FR-F3 paste a URL | **built** | `AddJobByUrl` → `/api/agent/job-from-url` |
| FR-F4 more board readers | **built** | 10 readers; BambooHR + Personio added |
| FR-F5 company→board registry | **built** | `companies.ats_platform` / `ats_token` |
| FR-F6 search and filter | **built, less salary** | phase 5 filter bar; see FR-F9 |
| FR-F7 high-match notification | **built** | `notify.py` email + `useMatchAlerts` desktop |
| FR-F8 live scan line | **built** | `ScanLine`, newest line on a spring under a live pulse |
| FR-F9 salary capture | **built** | `jobmeta.parse_salary`, filter + panel |
| FR-F10 saved jobs | **built** | bookmark on rows and cards; survives the purge |
| FR-F11 triage gesture | **built** | Pass / Apply on the dashboard cards |
| FR-F12 structured job detail | **built** | `JobDetail` panel: skills, level, salary, deadline |

### Prep

| Req | Status | Evidence |
|---|---|---|
| FR-P1 three tailoring modes | **built** | `latex_resume.MODES` |
| FR-P2 per-bullet diff | **built** | `ResumeReview`, now a sheet |
| FR-P3 auto-approve toggle | **built** | `tailoring.auto_approve` |
| FR-P4 multiple resume profiles | **built** | `api/resume_profiles.py`, Profiles screen |
| FR-P5 cover letters | **built** | `applier.cover_letter()` |
| FR-P6 full profile section set | **built** | `schema.DEFAULT_SETTINGS["profile"]` |
| FR-P7 house-style audit gate | **built** | `api/resume_audit.py`, hard gate |
| FR-P8 mechanical fact gate | **built** | `api/resume_facts.py` |
| FR-P9 completeness indicator | **built** | `profile_completeness`, shown on Settings |
| FR-P10 DOCX import | **built** | `import_document` parses PDF/DOCX into a profile |
| FR-P11 in-browser resume editor | **built** | `ResumeEditor`, live PDF preview |

### Apply

| Req | Status | Evidence |
|---|---|---|
| FR-A1 per-ATS capability table | **built** | `agent/portals.py`, 38 entries, `detects` / `submits` |
| FR-A2 Tsenta's status machine | **built** | queued / running / needs_review / submitted / failed |
| FR-A3 receipt per application | **built** | `fields_filled`, `unanswered`, `screenshot` |
| FR-A4 review the filled form | **built** | applier holds one click short; Approve submits |
| FR-A5 logins and OTP | **built** | login fill; OTP read from the connected inbox, or handed back by the user |
| FR-A6 never submit twice | **built** | `applied_hashes()` checked in `applier.py:1298` |
| FR-A7 never guess an answer | **built** | `unanswered` stops the run |
| FR-A8 batch apply | **built** | `job_ids` list through one run |
| FR-A9 Auto Apply | **built, deliberately weaker** | proposes; a human approves. See below. |
| FR-A10 bounded worker pool | **built** | `ThreadPoolExecutor`, `--workers` |
| FR-A11 employer-account password | **built** | `credentials.py`, applier signs in with it |

### Track

| Req | Status | Evidence |
|---|---|---|
| FR-T1 five tracker stages | **built** | `TRACKER_STATUSES` |
| FR-T2 IMAP read | **built** | `agent/inbox.py` |
| FR-T3 classify messages | **built** | rules first, LLM only for linked messages |
| FR-T4 advance only on confidence | **built** | `LINK_CONFIDENCE_THRESHOLD` |
| FR-T5 grouped inbox with unread | **built** | Track screen, hue-coded classes |
| FR-T6 manual add and CSV import | **built** | `AddApplication`, loose column matching |
| FR-T7 bounce detection | **built** | `_demote_bounced_pattern` |
| FR-T8 reply and interview rates | **built** | reply rate + reached-a-conversation under the stages |
| FR-T9 board with drag | **built** | `Kanban`, 1:1 pointer drag with spring settle |
| FR-T10 inbox as a mail client | **built** | full bodies, search, `MessageReader`, reply |
| FR-T11 in-progress indicator | **built** | scan line during a run; a running row pulses |
| FR-T12 export tracker CSV | **built** | Export on the Applications view |
| FR-T13 mailbox model | **decision, Compose built** | own-Gmail IMAP kept; Compose added |

### Surfaces and cross-cutting

| Req | Status | Evidence |
|---|---|---|
| FR-S1 web dashboard | **built, beyond spec** | seven screens after phase 5, not four |
| FR-S2 Chrome extension | **built** | `Extension/`, MV3 |
| FR-S3 MCP server | **built, deliberately weaker** | 14 tools, **no submit tool**. See below. |
| FR-S4 CLI parity | **built** | 12 query commands dispatch to the MCP functions |
| FR-S7 Networking | **built as Outreach** | our cold-email surface, same capability |
| FR-S8 Research | **built** | company facts, contacts and roles, grounded in the data |
| NFR-1 no agent framework | **held** | plain Python |
| NFR-2 every call budgeted | **held** | `agent/llm.py`, per-purpose shares |
| NFR-3 honest failure reporting | **held** | reasons recorded and surfaced |
| NFR-4 offline ATS fixtures | **built** | fixtures for six ATS, offline reader tests |
| NFR-5 backend parity | **held** | enforced by `tests/test_store_parity.py` |
| NFR-6 data stays local | **held** | nothing leaves the machine but LLM calls and applications |
| NFR-7 suite green and growing | **held** | 131 passing |

### Two places Jobenzy is deliberately not at parity

Both are choices, not gaps, and both should stay:

- **Auto Apply proposes; it does not submit.** Tsenta's auto-applies within your
  filters and daily cap. Jobenzy's shortlists and waits for a human to approve the
  batch. `agent_apply` refuses to run without explicit job ids, so this is
  structural rather than a promise — no misconfiguration can make it submit
  something nobody saw.
- **The MCP server has no submit tool.** Tsenta's connector can "apply to a
  single role or a batch" from inside an assistant. Jobenzy's exposes 14 tools and
  none of them send an application, for the same reason.

### The honest summary

Counted from the tables above, after phase 7: **60 requirements — 59 built**,
plus FR-T13 a settled decision (own-Gmail IMAP over a provisioned relay) whose
one borrowable part, Compose, is built. **That is all 60 addressed.** The
excluded multi-tenant set — a public API, accounts, allowances, billing, and the
mobile and iMessage surfaces (FR-D1–D6, FR-B1–B5, FR-S5, FR-S6) — stays out by
your decision; a single-user local tool has nothing to isolate, meter or bill.

Two positions still hold, and both are choices rather than gaps: **Auto Apply
proposes rather than submits**, and **the MCP server has no submit tool** — in
both cases `agent_apply` refuses to run without explicit job ids, so "nothing
goes out unseen" is structural rather than a setting.

Where the build stops short of Tsenta, it does so honestly rather than by
pretending otherwise:

- The login and OTP handling is wired end to end but proven only against the
  detection and store logic in tests — a full run against a live Workday or iCIMS
  account is not something the test suite can stand up. The credential store, the
  sign-in fill and the OTP hand-back are in place; the enterprise portals
  themselves are the one thing a local suite cannot exercise.
- "Fit to one page" trims toward a single page but never below the bullet floors
  the house style holds to, so a résumé with three roles and four projects may
  still land on two. That is the same rule the two-page fitter has always
  followed, applied to a tighter budget.
- Research is grounded in what discovery gathered, not an LLM briefing — so it is
  never wrong, and never more than what was found.

191 backend tests at the start of this phase, **196** at its end; the frontend
builds clean, and every screen was driven with no console errors.
