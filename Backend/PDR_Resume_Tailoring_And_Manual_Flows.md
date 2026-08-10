# PDR: Resume Tailoring (LaTeX) + Job-Description–Driven Output & Manual Application Flows

**Document type:** Project / Product Design & Requirements (PDR)  
**Status:** Draft for improving the existing Job Script (`prospecting_pipeline.py`, `companies_data.py`, `email_templates.py`, `send_applications.py`)  
**Author:** Aligned to current codebase (April 2026)

---

## 1. Executive summary

**Goal:** Evolve the pipeline from “one of two static PDFs per company vertical” to **per-application tailored PDFs** generated from a **single source LaTeX template**, driven by the **target job description (JD)** and your **core resume facts** (achievements, stack, products). Where employers require **manual portal applications** (Workday, Greenhouse, bespoke forms), the system should **not pretend to be fully automatic**; it should **generate artifacts** (tailored PDF, cover text, form-field cheat sheet) and support **assisted** manual steps with clear audit trails.

**Principle:** *Automate what is safe and repetitive; never automate bypass of CAPTCHAs, terms of service, or “apply as human” deceptions.*

---

## 2. Problem statement

### 2.1 Current behavior

- Resumes: **Two fixed files** — general PDF vs AI-focused Europass, chosen by `vertical` (`resume_for_vertical` in `companies_data.py`).
- Outreach: `send_applications.py` picks an **email template** by vertical, fills placeholders, attaches the **static** `Resume to Send` from CSV.
- Discovery: `prospecting_pipeline.py` finds careers pages, emails, and optional ATS hints.

**Gap:** No linkage to a **specific role** or its **JD**. No **LaTeX-driven** rebuild. No support for “**manual apply**” as a first-class state with generated assets per attempt.

### 2.2 Desired behavior

1. For each **target application** (company + job URL or JD text):
   - Ingest **JD** (text).
   - Extract **must-have skills**, **tools**, and **responsibility themes** (keyword + optional semantic).
   - Map them to your **evidence** (which project proves X).
   - **Render a LaTeX file** (from a template) with reordered/selected bullets and optional one-line “role line” or summary tuned to the JD.
   - **Compile to PDF** (one PDF per application, named and versioned).
2. For **email** path: attach **that** PDF, not a generic one; email body can reference 2–3 matched phrases from the JD.
3. For **manual portal** path: do **not** auto-submit; provide **ready-to-paste** fields + **upload the generated PDF** + track status in the same `Application Status` model.

---

## 3. Goals and non-goals

### 3.1 Goals (must-have in later phases)

| ID | Goal |
|----|------|
| G1 | **Single source of truth** for resume content in **LaTeX** (or LaTeX + small YAML/JSON for structured data). |
| G2 | **Per-JD** generation of a PDF: inputs = JD + your structured profile + policy constraints (max length, no fabrication). |
| G3 | **Traceability:** store which JD hash/version produced which PDF and which cover letter. |
| G4 | **Channel-aware packaging:** same core PDF can feed email attachment, “upload resume” on portal, and optional short “message to hiring manager” text. |
| G5 | **Manual apply workflow** as explicit states, checklists, and generated helper text (not hidden automation). |

### 3.2 Non-goals (out of scope or forbidden)

- **Full unattended submission** to Workday / LinkedIn / government portals.
- **Scraping** that violates site ToS (e.g., mass LinkedIn job scraping without API/compliance).
- **Fabricated** experience: automated text must be constrained to **user-approved facts** or clearly marked **drafts** for human edit.

---

## 4. Stakeholder view: “How it applies for you”

### 4.1 Email + attachment (high automation)

**You run:** `discover` → `tailor` → `send` (or review then send).

- System produces `outputs/applications/{company}_{job_slug}/resume.pdf` + `cover_snippet.txt`.
- `send_applications.py` (extended) attaches **path from row**, not a global filename.

**Value:** One command after review; consistent naming and logging.

### 4.2 Manual portal (partial automation)

**The system does not click “Submit” for you in a way that fools the employer.** Instead it:

1. **Generates** the tailored **PDF** and a **form cheat sheet** (plain text or JSON):
   - *Paste into “Why this company?”* — 2–3 sentences derived from `Notes` + JD overlap.
   - *Paste into “Describe a project”* — one paragraph from your structured projects table.
2. **Opens** a **human checklist** in the same folder (`CHECKLIST.md` or a small local HTML) with:
   - [ ] Log in (you)
   - [ ] Upload `resume.pdf`
   - [ ] Copy fields from `form_fields.txt`
   - [ ] Confirm submission screenshot / confirmation ID
3. **Optional assisted browser:** [Playwright](https://playwright.dev/python) script in “**pilot mode**” — opens the apply URL, pre-fills **non-sensitive** fields from JSON, then **pauses** for you to solve CAPTCHA and press Submit (or only fills after you type password). This is **not** in v1; document as phase 3.

**Value:** You still “apply as yourself,” but **resume quality and field text are pre-baked** and **deduplication** (same company, different roles) is tracked in CSV/JSONL.

### 4.3 “No URL, only email” employers

- Tailoring can use **vertical + `Notes` + `Custom Requirement`** from `companies_data.py` as a **proxy** for JD when no job posting exists (cold email mode).
- PDF variant: “**prospecting**” template section order vs “**role-specific**” when JD exists.

---

## 5. Proposed architecture (logical)

```
┌──────────────────┐     ┌───────────────────┐     ┌──────────────────┐
│ Job description  │     │ Profiling + match │     │ LaTeX generator  │
│ (URL or paste)   │───▶│ (keywords +      │───▶│ (Jinja2 /       │
│ + metadata       │     │  project mapping)  │     │  python replace)  │
└──────────────────┘     └───────────────────┘     └─────────┬────────┘
                                                          │
                    ┌────────────────────────────────────┼────────────────┐
                    ▼                                    ▼                ▼
            ┌──────────────┐                    ┌────────────┐   ┌──────────────┐
            │ PDF (pdflatex│                    │ Email body │   │ Form helper  │
            │  or tectonic)│                    │ snippet    │   │ (pasteable)  │
            └──────────────┘                    └────────────┘   └──────────────┘
                    │                                    │                │
                    └────────────────────┬───────────────┴────────────────┘
                                         ▼
                              ┌──────────────────────┐
                              │ applications.db or   │
                              │ applications.jsonl  │
                              │ + updated CSV         │
                              └──────────────────────┘
```

**Integration points with the existing project:**

- Replace or extend `Resume to Send` with **`Generated Resume Path`** or **`Resume Variant`** (`static_ai`, `static_general`, `tailored_{id}`).
- `send_applications.py`: `EmailMessage` attachment from **per-row path**.
- `prospecting_pipeline.py` row: add optional `Job URL`, `JD Text File`, `JD Hash` after you implement ingestion.

---

## 6. Data model (recommended)

### 6.1 New entity: `Application` (one row can represent one job, not one company)

| Field | Type | Description |
|-------|------|-------------|
| `application_id` | ULID/UUID | Stable id |
| `company_name` | str | From CSV |
| `vertical` | str | From CSV |
| `channel` | enum | `email` \| `portal` \| `unknown` |
| `job_url` | url | optional |
| `job_title` | str | optional, parsed or manual |
| `jd_source` | enum | `url` \| `paste` \| `file` \| `inferred` |
| `jd_text` | text | full JD (stored locally, not committed) |
| `jd_hash` | str | sha256 of normalized JD |
| `match_report` | json | keywords found, selected bullets, score |
| `latex_source_path` | path | generated `.tex` |
| `pdf_path` | path | final PDF |
| `status` | enum | `draft` \| `ready` \| `sent_email` \| `applied_manual` \| `rejected` |
| `created_at` / `updated_at` | ISO8601 | audit |

**Privacy:** Store JD text under `outputs/applications/.../jd.txt` in `.gitignore`.

---

## 7. LaTeX pipeline (technical design)

### 7.1 Source structure

- `resume/`  
  - `base.tex` — document class, packages, layout  
  - `sections/experience.tex` — with **named macros** or **Jinja2** blocks, e.g. `{{ bullet_scholarslee_payments | maybe_show }}`  
  - `data/profile.yaml` (optional) — companies, dates, technologies, **metrics** (numbers are sacred; never let LLM invent)

### 7.2 Templating options

| Approach | Pros | Cons |
|----------|------|------|
| **Jinja2 → .tex** | Familiar, clear conditionals | Must escape `{%` in LaTeX carefully |
| **Python string** `.format()` / **replace** | Simple | Gets messy for many sections |
| **Pandoc** markdown → PDF | Fast drafts | Less control than raw LaTeX for CV layout |

**Recommendation:** Jinja2 on `.tex.j2` files + a **pre-flight escape** for LaTeX special characters in free text (or restrict free text to a fixed “summary” block).

### 7.3 Compilation

- **Engine:** `pdflatex` or `latexmk` (recommended for multi-pass) or `tectonic` (self-contained, good for CI).
- **Output:** `outputs/.../resume.pdf` with deterministic naming: `{date}_{company_slug}_{short_hash}.pdf`.

### 7.4 Tailoring algorithm (v1, rule-based; v2, optional LLM)

**v1 – Rule-based (no API cost, predictable)**

1. Normalize JD: lowercase, remove punctuation, tokenize, remove stopwords.
2. **Keyword buckets:** map tokens to *sections/bullets* in profile YAML (e.g. token `stripe` → `bullet_scholarslee_payments`).
3. **Scoring:** count hits per bullet; take top *N* bullets per experience block (ceiling, e.g. 4 per role).
4. **Order:** show highest-match bullets first within each job.

**v2 – LLM assist (optional, human review)**

- Input: profile YAML + JD + “do not add facts; only rephrase and select.”
- Output: **ordered bullet ids** + short professional summary (2 lines).
- **Human gate:** diff shown in CLI or file; you approve before `pdflatex`.

---

## 8. Job description ingestion

| Method | When to use | Implementation sketch |
|--------|------------|------------------------|
| **Paste** | Quickest | CLI `python tailor_resume.py --jd-file jd.txt` |
| **URL fetch** | Public posting page | `requests` + trafilatura/readability; fail → manual paste |
| **Job board API** | If you add JobSpy, Greenhouse public API, etc. | Returns structured title + description |
| **Inferred (no JD)** | Cold email only | Use `Custom Requirement` + `Notes` as pseudo-JD for keyword pass |

**ATS note:** If `prospecting_pipeline` already identified Greenhouse, you can use **public job list JSON** in a later phase to get real JDs per role without scraping pages bluntly.

---

## 9. Channel-specific packaging

### 9.1 Email (existing `send_applications.py`)

- Extend CSV row: `Tailored PDF Path` (or compute path from `application_id`).
- Email template: add optional **first paragraph** that mirrors top 2 JD keywords (templated, not long).

### 9.2 Manual portal

Generate alongside PDF:

- `cover_200_words.txt` — for “message to hiring team”
- `screening_answers.md` — STAR answers **template** with blanks filled only from your approved YAML facts
- `CHECKLIST.md` — user steps
- `metadata.json` — job URL, time, version

**“Apply for me” here means:** the repository of artifacts **+ status tracking**, not headless form submission in v1.

### 9.3 Optional assisted browser (phase 3)

- **Playwright:** open `job_url`, optional fill of text fields from `metadata.json`, **you** upload PDF and click submit.
- Log **screenshot path** to `Application Status: applied_manual` with `confirmation_ref` in notes.

---

## 10. Phased roadmap (concrete)

| Phase | Duration (indicative) | Deliverable |
|-------|------------------------|------------|
| **P0** | 0.5 w | `profile.yaml` + one static LaTeX → PDF script (`build_resume.py`), `.gitignore` for `outputs/`. |
| **P1** | 1 w | JD from file + rule-based selection + Jinja2 render + `pdf_path` in a new `applications.jsonl`. |
| **P2** | 1 w | Wire `send_applications.py` to attach `pdf_path`; CSV column `Application Id` or path. |
| **P3** | 1–2 w | Optional LLM re-rank; manual approval CLI `tailor --approve`. |
| **P4** | 1–2 w | Playwright “open and assist” (no blind submit) + checklist generation for Workday-style pages. |
| **P5** | ongoing | Greenhouse/Lever public APIs for “real JD” where applicable. |

---

## 11. Security, compliance, and reputation

- **Gmail / SMTP:** current sender already throttles; **tailored** volume should follow same rules (20–40/day, warm-up).
- **ToS:** Do not automate sites that prohibit bots; prefer official APIs and **manual** upload of PDFs.
- **Data:** JDs and generated PDFs may contain personal/company text — keep out of public repos.

---

## 12. Success metrics (for you, as user)

- **Time per application** (first time vs repeat to same company).
- **Interviews / positive replies** per 100 tailored vs untailored (A/B on subject line optional).
- **Error rate** (failed PDF build, missing fields).
- **Traceability** — 100% of sent emails have a matching `pdf_path` and `jd_hash` logged.

---

## 13. Open decisions

- LaTeX distribution on Windows: **MiKTeX** vs WSL; or **tectonic** single binary.
- Whether one **Europass** LaTeX variant vs a single template with a toggle `AI_mode` that shows/hides the AI-heavy projects page.
- Whether to use **LLM** at all in v1 (recommend: **no**, until rule-based is stable).

---

## 14. Appendix: Mapping to current files (implementation hints)

| Current | Change |
|---------|--------|
| `companies_data.py` | Keep `resume_for_vertical` as **fallback** when `pdf_path` empty. |
| `send_applications.py` | If `tailored_pdf` column set, attach it; else existing behavior. |
| `prospecting_pipeline.py` | Optional: add `last_known_job_listing_url` in future, not required for P0–P1. |
| New | `build_resume.py`, `tailor_from_jd.py`, `profile.yaml`, `resume/template.tex.j2` |

---

**End of PDR**
