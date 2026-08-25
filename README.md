# Jobenzy

**One resume per target, drawn and ready.**

A local-first job-hunting system. Three screens, one dataset, zero recurring cost.

1. **Jobs** — searches public job boards across ten role categories, tracks every role it finds
   in a database you can filter, writes a resume tailored to each one, finds and *verifies*
   recruiter emails, and fills and submits application forms in a real browser **when you tell it
   to** — per job or in bulk.
2. **Resume** — upload your résumé plus a job description, see exactly what an applicant
   tracking system reads, and generate an ATS-safe rewrite as PDF, DOCX and TXT.
3. **Outreach** — cold email from two lists: founders and recruiters the agent verified, and your
   own company dataset, both with live console output.

Everything runs on your machine. Nothing leaves it except the emails you explicitly send and the
LLM calls you enable.

## Built entirely on free tiers

| Layer | What it uses | Cost |
| --- | --- | --- |
| Agent brain | Google Gemini (~1,500 req/day), Groq, OpenRouter, or Ollama locally | Free |
| LaTeX engine | Tectonic via `python tools/install_tex.py`, or MiKTeX / TeX Live | Free |
| Startup discovery | Y Combinator directory (6,100+ companies), HN "Who is hiring" | Free |
| Job ingestion | Greenhouse, Lever, Ashby, SmartRecruiters, Workable, Recruitee public APIs | Free |
| Remote/EU boards | Arbeitnow, Remotive, RemoteOK, Himalayas | Free |
| Hidden job market | The Muse, Jobicy, Working Nomads, WeWorkRemotely, Jobspresso, Landing.jobs | Free |
| Email discovery | Site crawl + published HN addresses + pattern generation | Free |
| Email verification | DNS MX lookup + SMTP `RCPT TO` probe | Free |
| Browser automation | Playwright + Chromium | Free |
| Sending | Your existing Gmail SMTP | Free |
| Database | MongoDB Atlas free tier (512 MB), or local SQLite | Free |

LinkedIn and Indeed are deliberately absent — they block automation, so relying on them would make
the agent fragile and get accounts limited.

---

## Project structure

```
jobenzy/
├── .gitignore
├── README.md                      ← you are here
│
├── Backend/                       Python: agent + pipeline + dashboard API
│   ├── run_dashboard.py           launcher (starts API + UI)
│   ├── requirements.txt
│   ├── .env                       Gmail credentials (git-ignored)
│   ├── .env.example
│   ├── credentials.json           Google Sheets service account (git-ignored)
│   ├── agent_data.sqlite3         local fallback database (git-ignored)
│   │
│   ├── agent/                     the agentic layer
│   │   ├── runner.py              discover / resumes / apply / outreach / full
│   │   ├── categories.py          the ten role categories + title classifier
│   │   ├── jobdesc.py             full description from the listing page
│   │   ├── tailor.py              per-job resume, via the Tab 2 engine
│   │   ├── experience.py          1-3 year gate: level, title, parsed years
│   │   ├── sources.py             YC, HN, ATS boards, remote & EU job APIs
│   │   ├── people.py              founder/recruiter discovery + email verification
│   │   ├── matcher.py             scores each role against your résumé
│   │   ├── applier.py             Playwright form filling and submission
│   │   ├── outreach.py            research → personalised email → send
│   │   ├── llm.py                 Gemini / Groq / OpenRouter / Ollama provider layer
│   │   ├── store.py               backend-selecting facade (Mongo, else SQLite)
│   │   ├── mongo_store.py         MongoDB backend
│   │   ├── sqlite_store.py        SQLite backend
│   │   └── schema.py              field lists and defaults shared by both
│   │
│   ├── api/                       FastAPI dashboard backend
│   │   ├── main.py                routes: /api/ats/*, /api/auto/*
│   │   ├── config.py              paths + the whitelist of runnable scripts
│   │   ├── resume_parse.py        PDF/DOCX/TXT → text, sections, roles, layout warnings
│   │   ├── ats.py                 JD keyword extraction, matching, scoring
│   │   ├── resume_build.py        ATS-safe document assembly + PDF/DOCX/TXT rendering
│   │   ├── resume_style.py        house style: fonts, hyphens, voice, bullet floor
│   │   ├── jobs.py                child-process runner with SSE log streaming
│   │   └── state.py               read-only views over the CSV / logs / .env
│   │
│   ├── prospecting_pipeline.py    crawl company sites → companies_dataset.csv
│   ├── send_applications.py       send personalised cold emails via Gmail SMTP
│   ├── email_templates.py         10 templates + vertical→template routing
│   ├── companies_data.py          curated company list
│   ├── cv_data/
│   │   ├── profile.yaml           source of truth for every resume
│   │   ├── template.tex.j2        Jinja2 LaTeX template
│   │   └── Usairam_Saeed_*.pdf    master resumes, built by tools/build_resumes.py
│   │
│   ├── tools/
│   │   ├── build_resumes.py       rebuild the master resumes from profile.yaml
│   │   ├── check_resume.py        audit any PDF against the house style
│   │   └── install_tex.py         fetch Tectonic, no admin rights needed
│   │
│   ├── companies_dataset.csv      the pipeline's working dataset
│   ├── send_log.jsonl             append-only audit of every send attempt
│   └── outputs/                   generated resumes (git-ignored)
│       └── agent_resumes/         one tailored resume per tracked job
│
└── Frontend/                      React 19 + Vite 7 + Tailwind 4
    ├── package.json
    ├── vite.config.js             dev server + /api proxy to :8000
    ├── index.html
    └── src/
        ├── index.css              design tokens: primitive → semantic → component
        ├── App.jsx                shell, nav, health
        ├── lib/api.js             typed fetch wrappers
        ├── components/
        │   ├── ui.jsx             the design kit — every visual decision lives here
        │   ├── Settings.jsx       model, application answers, targeting
        │   ├── TrackedJobs.jsx    the jobs table: filters, selection, apply
        │   └── Console.jsx        live run log
        └── tabs/
            ├── JobsTab.jsx        find, review, apply
            ├── ResumeTab.jsx      score and generate
            └── OutreachTab.jsx    both email lists
```

---

## Quick start

```bash
cd Backend
pip install -r requirements.txt
python -m playwright install chromium     # one-time, for the auto-apply agent
python run_dashboard.py
```

That starts the API on `:8000`, the Vite dev server on `:5173`, installs the Frontend's npm
packages on first run, and opens **http://localhost:5173**. Ctrl+C stops both.

Then, on the **Jobs** screen → **Settings**:

1. Paste a free [Gemini API key](https://aistudio.google.com/apikey) and hit **Test**.
2. Fill in the profile fields — these go straight into application forms.
3. Set the titles, locations and keywords you actually want.

**Requirements:** Python 3.10+ and Node 18+. For LaTeX PDFs run
`python tools/install_tex.py` once (fetches Tectonic, no admin rights); without an engine the
dashboard falls back to ReportLab PDFs.

### Ways to run it

| Command (from `Backend/`) | What happens | Open |
| --- | --- | --- |
| `python run_dashboard.py` | API + Vite dev server with hot reload | `http://localhost:5173` |
| `python run_dashboard.py --build` | Compiles the UI once, serves it from FastAPI. No Node process. | `http://localhost:8000` |
| `python run_dashboard.py --api-only` | Backend only | — |

Or run the two halves in separate terminals:

```bash
# Terminal 1
cd Backend
python -m uvicorn api.main:app --reload --port 8000

# Terminal 2
cd Frontend
npm run dev
```

Then open `http://localhost:5173`. Vite proxies every `/api/*` call to `:8000`, so you only ever
visit the 5173 URL in dev.

> **Run the backend from `Backend/`.** `api.main:app` is a package import — `cd Backend/api` first
> and you get `ModuleNotFoundError`.

> **Which URL?** `5173` in dev, `8000` after `--build`. Opening `:8000` while in dev mode serves the
> last *built* copy, not your live edits — that's the usual cause of "my change isn't showing up".

The chip in the dashboard's top-right reads **connected** when the two halves are talking and
**API offline** when they aren't.

---

## Jobs

A tracked pipeline you drive. The agent searches, classifies, scores and writes a tailored resume
for every role it finds — then stops. **Applications are only ever submitted when you press Apply**,
on a single row or a selection, from the Tracked jobs table.

### Role categories

The search is scoped to ten categories. A posting that maps to none of them is never stored, so
the table stays actionable instead of filling with SRE, data and sales roles.

```
Backend · Frontend · Full stack · Software engineer · AI engineer
AI software engineer · Product design · UI UX designer · UI designer · UX designer
```

Classification is rules-first (`agent/categories.py`), checked most specific first so the
overlapping names resolve correctly: *AI Software Engineer* beats *AI Engineer* beats *Software
Engineer*; *UI/UX Designer* beats *UI Designer* and *UX Designer*. Titles that differ from the
category name still land right — *Software Development Engineer*, *SDE II* and *Product Engineer*
all map to Software engineer, *Product Designer* to Product design. An LLM fallback exists for
titles no rule matched but is **off by default**, so a discovery run spends no model calls here.

### Tracked jobs

The table is the centre of the tab. Per job it records:

| | |
| --- | --- |
| Title, company, portal, link | where it came from |
| Role category | one of the ten above |
| Recruiter or founder email | **blank unless a real address verified** — never guessed |
| Discovered date | when the agent first saw it |
| Status | not applied · applied · failed to apply |
| Applied date | once applied |
| Resume version | which tailored file was uploaded, e.g. `job123_spacex_…-2f2e1836` |

Filter by category, status or portal, or search the text. Select rows to **apply in bulk** or
**generate resumes in bulk**; each row also has its own Apply button and a link to view or download
its resume.

Roles the experience gate or fit threshold ruled out stay visible under **Filtered out** with the
reason on hover, but their checkboxes are disabled — "select all" can never sweep up a Staff
Engineer posting the agent already rejected.

### Each run is incremental

Before anything expensive happens, every discovered job is checked against the hashes already in
the database. A job seen on a previous run is skipped without re-fetching its description,
re-scoring it or rebuilding its resume. A run reports exactly this:

```
[track] 47 job(s) already tracked · 10 categories enabled
[discover] 0 new · 22 already tracked · 23 outside the ten categories
```

### Tailored resume per job

For every job that clears the gates, the agent fetches the **full description from the listing
page** (not the board's summary snippet) and builds a resume aimed at it, through the same engine
and the same house style as Tab 2 — `agent/tailor.py` calls `latex_resume.build()` directly, so
nothing about the format is relaxed for this path. Files land in `Backend/outputs/agent_resumes/`
as a `.pdf` and a `.tex`.

Building one costs an LLM call plus a LaTeX compile, so a run only builds them for jobs above your
fit threshold, capped by `limits.max_resumes_per_run` (default 10). Everything else gets a
**Generate resume** button in the table.

Verify them the same way as any other output:

```bash
python tools/check_resume.py outputs/agent_resumes/*.pdf
```

### Research

Pulls from every source you enable, then scores what it finds:

- **Y Combinator** — 6,100+ companies, ~1,500 currently hiring, newest batches first.
- **HN "Who is hiring"** — the current monthly thread. Roughly a third of posts contain a direct
  founder email, which makes this the single best source for outreach.
- **Remote & EU boards** — Arbeitnow, Remotive, RemoteOK, Himalayas.
- **Hidden job market** — The Muse, Jobicy, Working Nomads, WeWorkRemotely, Jobspresso and
  Landing.jobs. These matter because competition scales with reach: a role on LinkedIn collects
  hundreds of applicants, the same role on Jobicy collects a handful. The Muse and Jobicy also
  publish an explicit experience level, which feeds the filter below.
- **Career portals** — for each company it detects Greenhouse / Lever / Ashby / Workable /
  Recruitee / SmartRecruiters from the site, then pulls that board's live openings with full
  descriptions.

Then it finds the humans: crawls `/about`, `/team` and `/contact`, extracts published addresses,
asks the model to name founders and recruiters, and generates likely address patterns for them.

**Every address is verified before it is ever used** — DNS MX lookup, then an SMTP `RCPT TO` probe
against the real mail server, plus a random control probe to detect catch-all domains:

| Status | Meaning |
| --- | --- |
| `valid` | The mail server accepted this mailbox and rejected a random control address. |
| `risky` | Catch-all domain, or a shared inbox like `careers@`. Deliverable but unproven. |
| `invalid` | The server rejected it, or the domain has no MX record. Never emailed. |
| `unknown` | The probe could not run — your ISP blocks port 25, or the server greylisted us. |

Guessed pattern addresses are dropped unless they verify as `valid`, so the agent never emails
an address it invented.

### Experience filter

Roles outside your experience window are dropped **before** scoring — a posting demanding eight
years is not a candidate however well the keywords line up. Three signals, most trusted first:

1. The board's own level field (The Muse and Jobicy publish one).
2. The job title — Senior, Staff, Principal, Lead, Head of, Director are unambiguous.
3. A years requirement parsed from the description: `3+ years`, `2-4 years`, `at least two years`.

Silence is not disqualifying — plenty of good postings never state a number, and rejecting those
would discard most of the market. The parser also ignores decoys: *"Founded 10 years ago. You bring
3 years of Node.js"* reads as 3, not 10.

Set the window in **Agent setup → What to go after**. Default is 1–3 years, internships off.

Finally every role is scored 0–100 against your résumé using the same ATS engine as Tab 2:
title match (30), keyword coverage (45), location fit (15), seniority fit (10). Anything below
your threshold is never applied to.

### Applying

**Applying is user-triggered only.** There is no autonomous apply mode and "Research and outreach"
never submits anything — the runner refuses to apply without explicit `--job-ids`.

**Freshness gate.** Only roles posted within `max_age_days` (default **3**) are ever applied to —
a week-old posting has usually already collected hundreds of applicants. Every board reports dates
differently (Lever sends epoch milliseconds, Arbeitnow epoch seconds, Greenhouse an ISO string with
an offset), so each one is normalised to a UTC timestamp at ingest. Within the window, the queue is
ordered **newest first** by default; switch to best-fit-first in Settings.

Boards that publish no date at all can't be proven fresh, so they're skipped by default — toggle
**Skip roles with no posting date** off to let them through at the back of the queue. The run log
always says how many were dropped and why:

```
[apply] 16 matched role(s) considered · skipped 14 older than 3d, 0 with no posting date, 2 already applied to
```

**Never applies twice.** Every role gets a content hash of company + title + location, normalised so
formatting differences don't matter. The hash is stored on each application, and the queue excludes
anything already submitted. Because it's derived from content rather than the URL, it also catches
the same job re-posted under a new ID, listed on two boards at once, or carrying tracking
parameters — a re-post with a fresh date and a higher fit score is still blocked.

Opens each selected role's form in a real Chromium browser and fills it three ways, cheapest first:
direct field rules → your profile's stock answers → the model, given the question text and your
profile.

It uploads **that job's own tailored resume** (falling back to the master resume only if none was
generated), writes a per-role cover letter grounded in your actual experience, and submits.

**A form it cannot complete is recorded as failed with the reason, never skipped silently.** Three
walls are detected explicitly and written to `failure_reason`, visible inline on the row:

| Wall | What it looks like |
| --- | --- |
| Captcha | reCAPTCHA / hCaptcha / Turnstile in a frame or the DOM |
| Login | "sign in to apply", or a redirect to `/login` |
| Unsupported form | no fillable fields, or a required question your profile cannot answer truthfully |

That last one matters: after filling, it re-reads the DOM for genuinely empty required fields
(treating a radio group as one question, not one per option). If any remain the application is
failed rather than guessed — a wrong answer on work authorisation or salary is permanent at that
company, and the row tells you which question stopped it so you can add the answer.

Every attempt is screenshotted; the screenshots are viewable from the Applications table.

Start with **Dry run** on: it fills everything and screenshots the completed form without clicking
Submit.

### Cold email

For each verified contact, it researches the company, writes an email grounded in what they
actually do, attaches your résumé, and sends via your Gmail with a configurable delay. If the model
is unavailable it falls back to a plain template rather than shipping generic filler.

Safety ladder, same as Auto Mode: **Dry run** → **Send to yourself** → live.

### From the command line

```bash
cd Backend
python -m agent.runner discover --sources yc,hn,remote,hidden --limit 40
python -m agent.runner resumes  --job-ids 12,15
python -m agent.runner apply    --job-ids 12,15 --dry-run --headed
python -m agent.runner outreach --limit 10 --delay 90 --dry-run
python -m agent.runner full     --limit 25      # research + outreach, never applies
```

### Known limits

- Some location fields (Lever uses a Google-Places typeahead) resist automated entry. The agent
  detects this and skips rather than submitting an incomplete form.
- Companies with a custom careers SPA rather than an embedded ATS form (Stripe, for example) yield
  no fillable fields; those get logged as `failed` with a screenshot.
- SMTP verification cannot be certain on catch-all domains — those are marked `risky`, never
  `valid`.
- If your ISP blocks outbound port 25, verification degrades to MX-only and everything is marked
  `unknown` rather than being falsely promoted.

## Resume

### House style

Every resume this project generates — LaTeX or not — is held to one written specification,
compiled into `api/resume_style.py` and enforced on both output paths.

| Rule | Where it is enforced |
|---|---|
| Times New Roman throughout | `template.tex.j2` (newtx) and `resume_build.py` (Times-Roman) |
| FAANG-template layout: large small-caps name, small-caps section headings over a rule | all three renderers |
| Pure black, no shading, no colour | `hidelinks` plus explicit `#000000`; only a 0.4pt hairline under headings |
| 0.5in margins, name 20 to 22pt small caps, headings 12pt bold small caps over a hairline, body 11pt | both renderers |
| No hyphen or dash anywhere | `resume_style.enforce()` — compounds open up, dates become "August 2023 to Present" |
| No word broken across a line | hyphenation penalties at 10000 |
| 3 to 5 bullets under every role | `MIN_ROLE_BULLETS` / `MAX_ROLE_BULLETS`, respected by the one-page fitter |
| Categorised Skills, two-line Summary | `_skill_rows()` and `profile.yaml` |
| No first person, no "Responsible for", no emoji | `resume_style.lint()`, which also gates LLM rewrites |

Two rules exist because of how PDFs actually extract, not because of how they look:

- **Interword space is widened to 0.36em.** A PDF stores no space characters — a space is a
  positioning offset. Times' natural space at 11pt draws a 2.49pt gap, and pdfminer-based
  parsers (including a good share of real ATS software) only split words above ~3pt. Left
  alone, the resume extracts as `SoftwareDeveloperandFrontendTeamLead`.
- **`\raggedright` everywhere.** Justification shrinks interword space, which pushes it back
  under that threshold on exactly the lines that are most full.

**Checking a build:**

```bash
cd Backend
python tools/check_resume.py                    # every PDF in cv_data/
python tools/check_resume.py path/to/one.pdf
```

It audits the *extracted text* and the PDF's own drawing operators rather than the LaTeX
source, because the source can be correct while the file a parser sees is not. The Resume
Tailor also returns a `style` block per build, so violations surface in the browser.

**When it will not fit on one page.** The fitter drops content in a fixed order — languages,
projects, the "Relevant coursework" line, then it folds Awards into Certifications to reclaim a
heading, and only then trims bullets. It never takes a role below three bullets: if everything
is at the floor and the page is still full, you get two pages rather than a hollowed-out
Experience section.

### LaTeX output

Tailoring produces a real **`.tex`** file and compiles it to PDF. The pipeline:

1. Load content from `cv_data/profile.yaml` (curated and tagged, best results) or from the
   resume you just uploaded.
2. Score every bullet against the posting, using the same keyword engine as the ATS analysis
   plus `tag_hints` triggered by the job text.
3. Swap in an alternate summary when the posting leans AI or design (`modes` in profile.yaml).
4. Rewrite the surviving bullets through the LLM under the BeHuman rules — facts only, every
   existing number preserved, no invented metrics.
5. Render `cv_data/template.tex.j2`, compile, **measure the real page count**, and drop the
   lowest-scoring lines until it fits on one page.

The template is engine-portable (pdflatex, xelatex, lualatex, tectonic) and ATS-safe: single
column, no tables, standard headings, links written as visible text, and `\pdfgentounicode`
under pdfTeX so extraction returns characters instead of `(cid:NNN)`.

**Getting a LaTeX engine.** If none is installed:

```bash
cd Backend
python tools/install_tex.py     # fetches Tectonic, one binary, no admin rights
```

Anything in `Backend/tools/` is used before PATH. Without an engine you still get the `.tex`
(ready for Overleaf) plus the plain-builder PDF, DOCX and TXT.

**One document, four containers.** With LaTeX on, the PDF is the compiled `.tex`, and the WORD and
TXT files are rendered from the *same tailored content* by `api/resume_docx.py` — Times New Roman,
pure black, 0.55in margins, native tab stops for the dates, no tables. Downloads: **PDF**, **WORD**,
**TXT**, **`.TEX`**.

This used to be wrong in a way that was easy to miss. `resume_build.py` rebuilds whatever file you
uploaded, while `latex_resume.py` scores, reorders and rewrites your curated `profile.yaml` against
the posting — so "PDF" served a plain rebuild of your upload while ".TEX" served the tailored
document. Two different resumes from one button row. Both now come from the tailored content.

With LaTeX off, the ReportLab and python-docx path in `resume_build.py` takes over, under the same
house style. The before/after score is measured by re-parsing the compiled LaTeX PDF — the actual
file an employer receives.

### BeHuman

`Backend/.skills/behuman` is installed as a project skill and its rules are compiled into
`api/behuman.py`, which every writing path imports: resume bullets and summaries, cover letters,
and cold emails.

- `RULES` is appended to each system prompt — banned vocabulary, no negative parallelism, no
  significance tails, no em dashes, no chatbot residue.
- `lint()` checks the output afterwards, because models comply unevenly.
- `scrub()` fixes only what is safe to fix. A trailing clause containing a number is kept, since
  "ensuring reliability for 500+ users" is a result, not decoration.

The Resume Tailor shows the verdict after each build ("BeHuman check: clean", or the specific
tells it found).



Upload a resume (PDF, DOCX, TXT or MD) and paste the job description. The dashboard reads the
document the way a parser does, scores it, and rebuilds it.

### The score

100 points across six components, each shown with the evidence behind it:

| Component | Max | What it measures |
| --- | --- | --- |
| **Keyword match** | 35 | Weighted coverage of terms extracted from the posting. Terms in the requirements section and the job title carry more weight than body text; "nice to have" terms carry less. |
| **Section structure** | 15 | Whether SUMMARY / SKILLS / EXPERIENCE / EDUCATION exist under headings a parser recognises. |
| **Parseability** | 20 | Tables, multi-column layouts, images, header/footer content, hyperlink-only URLs, missing text layer. Each trap deducts by severity. |
| **Contact details** | 10 | Email, phone, LinkedIn and location readable as plain text **in the document body**. |
| **Bullet quality** | 10 | Share of bullets carrying a number, share opening on a strong action verb, average bullet length. |
| **Format hygiene** | 10 | Word count, first-person pronoun density, file type, parseable date range on every role. |

Below the score, **"What a parser actually sees"** shows the reconstructed contact block, the
sections it found (and the exact heading text that matched), every role with its dates and bullet
count, and the layout traps. A low score is always traceable to a specific parsing failure rather
than being a black-box number.

### Keyword extraction

The job description is split into must-have and nice-to-have regions, then mined two ways:

- a curated lexicon of ~180 skill families with aliases, so `node`, `node.js` and `nodejs` all
  resolve to one term, and `ci/cd` matches `github actions` or `jenkins`;
- n-gram harvesting for anything the lexicon doesn't know, with clause-boundary splitting so
  phrases never span a comma or full stop, connector-word filtering, and substring de-duplication
  (`hubspot marketing automation` wins over `hubspot marketing`).

If the lexicon harvest comes back thin — a non-technical role, or a domain it hasn't seen — the
thresholds relax and the whole posting is mined. It works on marketing, finance and ops postings,
not just engineering ones.

### The rebuild

The generated resume is single-column with standard headings and contains no tables, images, text
boxes or header/footer content. It also:

- **reorders bullets inside each role** so the most job-relevant work reads first — nothing is
  deleted, only resequenced;
- **adds a `Job-Matched Skills:` line** built *only* from terms your resume already evidences;
- **restores hyperlink-only links** — a hyperlinked word "LinkedIn" is invisible to a text parser,
  so the URL is written out as visible characters;
- **re-joins hyphenated line breaks** that PDF extraction splits (`de-` / `livering`);
- outputs **PDF, DOCX and TXT**, then **re-scores the generated document** through the same pipeline
  so the before/after delta is measured, not asserted.

Keywords you have no evidence for stay in a "still not covered" list. The tool will not write
experience you do not have — a term with no work behind it fails at the interview instead of the
filter.

### Optional AI pass

The rewrite pass runs on the agent's configured provider (Gemini by default — the free key you set
in Jobs → Settings). It reorders and rewrites bullets for the specific posting, constrained to
facts already in your resume, and rejected rewrites fall back to the original line.

### Safety model

- Only the scripts declared in [`Backend/api/config.py`](Backend/api/config.py) can be launched.
- Flags are rebuilt server-side from typed, range-clamped values — the browser never supplies a
  command line.
- One task runs at a time, since these scripts share `companies_dataset.csv`. Starting a second
  returns `409` with an explanation rather than corrupting the file.
- Rows already `Applied` / `Interview` / `Offer` / `Failed` are skipped automatically, so every run
  is rerun-safe.

### Recommended rollout

```
dry run  →  --to-self  →  --limit 20 --delay 90  →  scale up
```

Gmail allows roughly 500 messages per rolling 24h on a free account (2,000 on Workspace). Start at
20–40/day with 60–90s spacing for the first two or three weeks to build sender reputation.

---

## Data storage

The agent stores everything in **MongoDB** when `MONGODB_URI` is set, and in a local
**SQLite** file otherwise. Both backends implement the same interface, so nothing else in the
codebase knows which is live.

```
Backend/.env
  MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/?appName=Cluster0
  MONGODB_DB=jobscript      # keeps its original name: renaming it points at an empty database
```

Collections: `companies`, `jobs`, `people`, `applications`, `outreach`, `runs`, `settings`,
plus `counters` for id sequences.

Two design choices worth knowing:

- **Ids stay integers.** A `counters` collection issues sequences rather than using ObjectIds,
  so `job.company_id` and `outreach.person_id` keep working and the API shape is identical
  across backends.
- **Unreachable means degraded, not broken.** If the cluster is paused, DNS fails, or you are
  offline, the agent falls back to local SQLite and the dashboard shows an amber banner. Push
  the local data up afterwards with the migration tool.

### Moving existing data into MongoDB

```bash
cd Backend
python tools/migrate_to_mongo.py --dry-run   # report what would move
python tools/migrate_to_mongo.py             # copy it
python tools/migrate_to_mongo.py --wipe      # clear the target first
```

Ids are preserved so foreign keys stay intact, id sequences are advanced past the imported rows,
and re-running is safe — companies, jobs and people match on their natural keys and update
rather than duplicate. The SQLite file is never modified, so it stays as a backup.

To pin the local backend regardless of configuration:

```bash
JOBSCRIPT_FORCE_SQLITE=1 python run_dashboard.py
```

The Agent tab shows the active backend as a chip beside the Refresh button.

## Configuration

### `Backend/.env`

```ini
GMAIL_ADDRESS=you@gmail.com
GMAIL_APP_PASS=xxxx xxxx xxxx xxxx
```

The app password is **not** your account password — create one at
<https://myaccount.google.com/apppasswords> with 2FA enabled. Copy `.env.example` to `.env` to start.
The dashboard shows an amber banner while this is unset; dry runs still work.

### `Backend/cv_data/profile.yaml`

Source of truth for every generated resume. The dashboard's
Resume Tailor does not use it — that works from whatever file you upload.

### `Backend/credentials.json`

Google service-account key. No longer used by any live path; safe to delete.

---

## Command line (without the dashboard)

Every step still runs standalone from `Backend/`:

```bash
python prospecting_pipeline.py                      # discover careers/ATS/emails → CSV
python send_applications.py --dry-run               # preview, no network
python send_applications.py --limit 3 --to-self     # safe deliverability test
python send_applications.py --limit 30 --delay 60   # real run

python -m agent.runner discover --sources yc,hn,remote,hidden --limit 40
python -m agent.runner resumes  --job-ids 12,15
python -m agent.runner apply    --job-ids 12,15 --dry-run
python -m agent.runner outreach --limit 10 --delay 90 --dry-run

python tools/build_resumes.py                       # rebuild the master resumes
python tools/check_resume.py                        # audit any PDF against the house style
```

## HTTP API

Useful if you want to script against the backend directly.

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Liveness plus whether the AI pass is available. |
| `POST` | `/api/ats/analyze` | multipart: `resume` file, `jd_text` and/or `jd_file`. Returns the full analysis and a `sessionId`. |
| `POST` | `/api/ats/build` | `{sessionId, reorderBullets, useAi, formats}`. Returns the rebuilt resume, download URLs and the re-scored result. |
| `GET` | `/api/ats/download/{sessionId}/{pdf\|docx\|txt}` | Fetch a generated file. |
| `GET` | `/api/auto/overview` | Dataset stats, environment check, task list, active job. |
| `GET` | `/api/auto/activity` | Recent sends and resume builds. |
| `POST` | `/api/auto/run` | `{key, dry_run, to_self, limit, delay, vertical}`. Starts a task. |
| `GET` | `/api/auto/jobs/{id}/stream` | SSE log stream. |
| `GET` | `/api/auto/jobs/{id}?cursor=N` | Polling fallback for the same log. |
| `POST` | `/api/auto/stop/{id}` | Terminate a running task. |
| `GET` | `/api/agent/overview` | Agent stats, settings, LLM status, task list. |
| `GET` | `/api/agent/data?kind=` | `jobs` / `companies` / `people` / `applications` / `outreach`. |
| `POST` | `/api/agent/settings` | Patch profile, targeting, limits or LLM config. |
| `POST` | `/api/agent/llm-test` | Check the configured provider responds. |
| `GET` | `/api/agent/screenshot/{name}` | A saved application-form screenshot. |

Analysis sessions live in memory and are garbage-collected after 6 hours or 24 sessions.

---

## Dataset columns

`companies_dataset.csv`:

```
Vertical, Organization Name, Website, Careers Page, ATS Platform, Apply Method,
Contact Page, Apply Email, Info Email, HR Email, Rozee.pk Search, LinkedIn Jobs,
Source URL, Country, Notes, Custom Requirement, Resume to Send, Candidate Email,
Application Status, Generated Resume, Job Description Hash
```

Discovery detects Greenhouse, Lever, Workday, BambooHR, SmartRecruiters, Breezy, Teamtailor,
Recruitee, Jobvite, Workable, Ashby, Rippling, Zoho Recruit and Rozee.pk.

---

## Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| Header reads **API offline** | Backend isn't running, or you started it from the wrong folder. `cd Backend` first. |
| `ModuleNotFoundError: api` | You ran uvicorn from inside `Backend/api/`. Run it from `Backend/`. |
| UI changes don't appear | You're on `:8000` (the built copy) instead of `:5173` (dev). Or re-run `--build`. |
| "Almost no text could be extracted" | The PDF is a scan or an image-only export. An ATS sees the same nothing — re-export as a text-based PDF. |
| Sends fail at SMTP login | `GMAIL_APP_PASS` missing or still the placeholder. Regular account passwords are rejected. |
| A task won't start (`409`) | Another task is already running; stop it first. They share the CSV. |
| Port already in use | `python run_dashboard.py --port 8010`, or kill the stale process. |
| AI toggle is greyed out | Set a Gemini key in Jobs → Settings and press Test. |
