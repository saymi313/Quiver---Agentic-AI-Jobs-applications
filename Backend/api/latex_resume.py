"""
JD-tailored LaTeX resume.

Takes whatever the user uploaded (or cv_data/profile.yaml), scores every bullet
against the job description, rewrites the survivors through the LLM under the
BeHuman rules, and renders cv_data/template.tex.j2.

Output is always a `.tex` file. A PDF is produced too when a LaTeX engine is on
PATH; when there is none, the caller still gets the .tex plus the ReportLab PDF
so nothing is blocked on a MiKTeX install.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml
from jinja2 import Environment, FileSystemLoader

from . import behuman, resume_style
from .ats import _alias_pattern, _norm
from .config import CV_DATA
from .resume_parse import ParsedResume

TEMPLATE_NAME = "template.tex.j2"
PROFILE_PATH = CV_DATA / "profile.yaml"

# The house style requires 3 to 5 bullets under every Experience entry and
# 2 to 3 under every project. The fitter treats the lower bounds as floors it
# may not cross: a role reduced to one line reads as a job the candidate barely
# held, and a project with one bullet reads as filler.
#
# The document is a two pager. Projects are chosen by relevance to the posting:
# the tailor ranks them against the job description, drops the ones that score
# nothing when enough relevant ones remain, and the page fitter sheds the least
# relevant first — but the document always keeps at least MIN_PROJECTS.
#
# Defined here rather than beside the fitter because `tailor()` uses
# MAX_ROLE_BULLETS as a default argument, which Python evaluates at import.
MIN_ROLE_BULLETS = 3
MAX_ROLE_BULLETS = 5
MIN_PROJECT_BULLETS = 2
MAX_PROJECT_BULLETS = 3
MIN_PROJECTS = 2
# The profile carries every project the candidate has; the resume shows the
# few that fit this posting. Four keeps the section substantial without
# burying the relevant work under weak matches.
MAX_PROJECTS_SHOWN = 4
MAX_PAGES = 2

# Custom delimiters so LaTeX braces pass through Jinja untouched.
JINJA_KW = dict(
    block_start_string="[%", block_end_string="%]",
    variable_start_string="[[", variable_end_string="]]",
    comment_start_string="[#", comment_end_string="#]",
    trim_blocks=False, lstrip_blocks=False,
)

ENGINES = ("latexmk", "pdflatex", "xelatex", "tectonic")
# A LaTeX engine dropped in Backend/tools/ is used before anything on PATH, so
# `python tools/install_tex.py` gives working PDFs without a system-wide install.
LOCAL_TOOLS = CV_DATA.parent / "tools"


# --------------------------------------------------------------------------
# LaTeX escaping
# --------------------------------------------------------------------------

_TEX_MAP = {
    "\\": r"\textbackslash{}", "{": r"\{", "}": r"\}", "$": r"\$", "&": r"\&",
    "#": r"\#", "_": r"\_", "%": r"\%", "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def tex_escape(s: Any) -> str:
    """Escape text for LaTeX. Runs on every string that reaches the template."""
    if s is None:
        return ""
    text = str(s)
    # Normalise the punctuation PDF extraction leaves behind before escaping.
    text = (text.replace("’", "'").replace("‘", "'")
                .replace("“", '"').replace("”", '"')
                .replace("–", "--").replace("—", "---")
                .replace("•", "").replace("\xa0", " "))
    out = "".join(_TEX_MAP.get(ch, ch) for ch in text)
    return re.sub(r"\s{2,}", " ", out).strip()


def tex_url(url: str) -> str:
    return (url or "").replace("%", r"\%").replace("#", r"\#")


# --------------------------------------------------------------------------
# Content model
# --------------------------------------------------------------------------

@dataclass
class Bullet:
    text: str
    tags: list[str] = field(default_factory=list)
    score: float = 0.0


@dataclass
class Block:
    role: str = ""
    company: str = ""
    period: str = ""
    location: str = ""
    name: str = ""
    tech: str = ""
    bullets: list[Bullet] = field(default_factory=list)


@dataclass
class ResumeContent:
    name: str = ""
    title: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    links: list[dict[str, str]] = field(default_factory=list)
    summary: str = ""
    skills: list[str] = field(default_factory=list)
    experience: list[Block] = field(default_factory=list)
    projects: list[Block] = field(default_factory=list)
    # Structured education (institution / location / degree / period / courses)
    # renders in the reference layout; plain `education` lines are the fallback
    # for content parsed out of an uploaded file.
    education_entries: list[dict[str, str]] = field(default_factory=list)
    education: list[str] = field(default_factory=list)
    certifications: list[str] = field(default_factory=list)
    # Retitled to "Certifications and Awards" when the fitter folds the two
    # sections together to reclaim a heading.
    certifications_title: str = "Certifications"
    awards: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    source: str = ""


# --------------------------------------------------------------------------
# Loading content
# --------------------------------------------------------------------------

def from_profile(path: Path | None = None) -> ResumeContent:
    """Load cv_data/profile.yaml — the curated, fully tagged source."""
    data = yaml.safe_load((path or PROFILE_PATH).read_text(encoding="utf-8"))
    c = data.get("candidate") or {}

    content = ResumeContent(
        name=c.get("name", ""), title=c.get("title", ""), email=c.get("email", ""),
        phone=c.get("phone", ""), location=c.get("location", ""),
        links=list(c.get("links") or []),
        summary=(c.get("summary") or "").strip(),
        source="profile.yaml",
    )
    content.skills = [s["line"] for s in (data.get("skills") or []) if s.get("line")]
    for e in data.get("education") or []:
        if e.get("institution") or e.get("degree"):
            content.education_entries.append({
                "institution": e.get("institution", ""), "location": e.get("location", ""),
                "degree": e.get("degree", ""), "period": e.get("period", ""),
                "courses": e.get("courses", "")})
        elif e.get("line"):
            content.education.append(e["line"])
    content.awards = [a["line"] for a in (data.get("awards") or []) if a.get("line")]
    content.certifications = [x["line"] for x in (data.get("certifications") or [])
                              if x.get("line")]
    content.languages = [l["line"] for l in (data.get("languages") or []) if l.get("line")]

    for exp in data.get("experience") or []:
        role_tags = [str(t).lower() for t in (exp.get("tags") or [])]
        content.experience.append(Block(
            role=exp.get("role", ""), company=exp.get("company", ""),
            period=exp.get("period", ""), location=exp.get("location", ""),
            bullets=[Bullet(b.get("text", ""),
                            list(dict.fromkeys([str(t).lower() for t in (b.get("tags") or [])] + role_tags)))
                     for b in (exp.get("bullets") or []) if b.get("text")]))

    for proj in data.get("projects") or []:
        ptags = [str(t).lower() for t in (proj.get("tags") or [])]
        content.projects.append(Block(
            name=proj.get("name", ""), tech=proj.get("tech", ""),
            bullets=[Bullet(b.get("text", ""),
                            list(dict.fromkeys([str(t).lower() for t in (b.get("tags") or [])] + ptags)))
                     for b in (proj.get("bullets") or []) if b.get("text")]))

    content._raw = data  # type: ignore[attr-defined]
    return content


def from_parsed(parsed: ParsedResume) -> ResumeContent:
    """Build the same model from an uploaded PDF/DOCX, so any file can be tailored."""
    c = parsed.contact
    links: list[dict[str, str]] = []
    for label, key, hidden in (("LinkedIn", "linkedin", "linkedinHidden"),
                               ("GitHub", "github", "githubHidden"),
                               ("Portfolio", "website", "websiteHidden")):
        url = c.get(key) or c.get(hidden)
        if url:
            links.append({"label": label, "url": url})

    content = ResumeContent(
        name=parsed.name or "Your Name", title=parsed.headline or "",
        email=c.get("email", ""), phone=c.get("phone", ""), location=c.get("location", ""),
        links=links,
        summary=re.sub(r"\s+", " ", " ".join(parsed.sections.get("summary", []))).strip(),
        source=f"uploaded .{parsed.source}",
    )
    content.skills = [re.sub(r"^[•\-\*·]\s*", "", s).strip()
                      for s in parsed.sections.get("skills", []) if s.strip()]
    content.education = [re.sub(r"^[•\-\*·]\s*", "", s).strip()
                         for s in parsed.sections.get("education", []) if s.strip()]
    content.awards = [re.sub(r"^[•\-\*·]\s*", "", s).strip()
                      for s in parsed.sections.get("awards", []) if s.strip()]
    content.certifications = [re.sub(r"^[•\-\*·]\s*", "", s).strip()
                              for s in parsed.sections.get("certifications", []) if s.strip()]
    content.languages = [s.strip() for s in parsed.sections.get("languages", []) if s.strip()]

    for e in parsed.experience:
        content.experience.append(Block(
            role=e.title or e.header, company=e.organization, period=e.period,
            location=e.location, bullets=[Bullet(b) for b in e.bullets]))
    for p in parsed.projects:
        content.projects.append(Block(
            name=p.title or p.header, tech=p.organization,
            bullets=[Bullet(b) for b in p.bullets]))
    return content


# --------------------------------------------------------------------------
# Tailoring
# --------------------------------------------------------------------------

def score_bullet(bullet: Bullet, jd: dict[str, Any], hint_tags: set[str]) -> float:
    """Relevance of one bullet to this posting."""
    norm = _norm(bullet.text)
    score = 0.0
    for kw in jd.get("keywords", []):
        for alias in kw.get("aliases", [kw["term"]]):
            if _alias_pattern(alias).search(norm):
                score += kw["weight"]
                break
    score += 1.2 * len(hint_tags.intersection(bullet.tags))
    if re.search(r"\d", bullet.text):
        score += 0.6                      # a measured bullet beats an unmeasured one
    return round(score, 2)


def active_tags(jd_text: str, raw_profile: dict[str, Any] | None) -> set[str]:
    """Which profile tag_hints this job description triggers."""
    if not raw_profile:
        return set()
    jd_norm = _norm(jd_text)
    hits: set[str] = set()
    for tag, phrases in (raw_profile.get("tag_hints") or {}).items():
        for phrase in phrases or []:
            p = str(phrase).lower().strip()
            if len(p) > 1 and p in jd_norm:
                hits.add(str(tag).lower())
                break
    return hits


def select_projects(projects: list[Block],
                    max_projects: int | None = None) -> list[Block]:
    """
    Which projects this resume shows, in relevance order.

    Ranked by their bullets' scores against the posting, capped at the
    MAX_PROJECTS_SHOWN best. A project that scores nothing is dropped —
    showing a trading platform to a design studio dilutes the relevant work —
    but only when at least MIN_PROJECTS relevant ones remain. A generic
    posting that triggers nothing keeps the profile's order, because a zero
    signal is not evidence of irrelevance.
    """
    ranked = sorted([p for p in projects if p.bullets],
                    key=lambda p: -sum(b.score for b in p.bullets))
    relevant = [p for p in ranked if sum(b.score for b in p.bullets) > 0]
    picked = relevant if len(relevant) >= MIN_PROJECTS else ranked
    return picked[:max_projects if max_projects is not None else MAX_PROJECTS_SHOWN]


def pick_summary(content: ResumeContent, jd_text: str,
                 raw_profile: dict[str, Any] | None) -> str:
    """Swap in an alternate summary when the posting leans AI or design."""
    if not raw_profile:
        return content.summary
    jd_norm = _norm(jd_text)
    modes = raw_profile.get("modes") or {}
    for mode, triggers in (raw_profile.get("modes_triggers") or {}).items():
        if any(str(t).lower() in jd_norm for t in (triggers or [])) and modes.get(mode):
            return str(modes[mode]).strip()
    return content.summary


REWRITE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "bullets": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "original": {"type": "string"},
                    "revised": {"type": "string"},
                },
                "required": ["original", "revised"],
            },
        },
    },
    "required": ["summary", "bullets"],
}

REWRITE_SYSTEM = """You tailor an engineer's resume to one specific job posting.

Hard constraints:
- Only restate facts already present in the bullets you are given. Never invent an employer,
  technology, metric, date, or credential.
- Preserve every number exactly as written. If a bullet has no number, do not add one.
- Keep each bullet to one line, roughly 15 to 28 words.
- Open each bullet with a past-tense action verb (or present tense for a current role).
- Use the posting's own vocabulary only where the underlying work genuinely matches.
- The summary must fit two lines: 220 characters at most.

Return only bullets you actually improved. `original` must be a byte-exact copy of the input.
""" + """
House style, enforced on every line you return:
- Never use a hyphen or dash. Write compounds open ("full stack", "real time", "end to end")
  and date ranges with the word "to" ("August 2023 to Present").
- Never use first person. No "I", "we", "my", "our".
- Never open a bullet with "Responsible for", "Worked on", "Helped", "Assisted" or
  "Involved in". Open with the verb itself.
- No emoji. No unevidenced soft claims ("strong communicator", "proven track record").
- Shape each bullet as: action verb, what was built, the method, then the measurable
  outcome. Keep the outcome only if a real number is already present.
""" + "\n" + behuman.RULES


def tailor(content: ResumeContent, jd_text: str, jd: dict[str, Any], *,
           use_llm: bool = True, max_bullets: int = MAX_ROLE_BULLETS,
           max_projects: int | None = None,
           log: Callable[[str], None] = print) -> dict[str, Any]:
    """Select, order and (optionally) rewrite content for this posting."""
    raw = getattr(content, "_raw", None)
    hint_tags = active_tags(jd_text, raw)
    if hint_tags:
        log(f"[latex] job triggers profile tags: {', '.join(sorted(hint_tags))}")

    content.summary = pick_summary(content, jd_text, raw)

    for block in content.experience:
        for b in block.bullets:
            b.score = score_bullet(b, jd, hint_tags)
        block.bullets.sort(key=lambda b: -b.score)
        block.bullets = block.bullets[:max_bullets]

    # Projects are the tailored part of the document: scored against the
    # posting, ordered most relevant first, and the irrelevant ones dropped.
    for block in content.projects:
        for b in block.bullets:
            b.score = score_bullet(b, jd, hint_tags)
        block.bullets.sort(key=lambda b: -b.score)
        block.bullets = block.bullets[:MAX_PROJECT_BULLETS]
        # The tech line is relevance evidence too: "React, Node.js, MongoDB"
        # should pull a project up for a Node role even when its bullets talk
        # about the product rather than the stack.
        if block.tech and block.bullets:
            block.bullets[0].score += 0.5 * score_bullet(Bullet(block.tech), jd, hint_tags)
    content.projects = select_projects(content.projects, max_projects)

    if content.skills and hint_tags and raw:
        tagged = {s["line"]: [str(t).lower() for t in (s.get("tags") or [])]
                  for s in (raw.get("skills") or []) if s.get("line")}
        content.skills.sort(key=lambda l: -len(hint_tags.intersection(tagged.get(l, []))))

    result: dict[str, Any] = {"llm": None, "rewritten": 0, "lint": []}

    if use_llm:
        result.update(_llm_rewrite(content, jd_text, log=log))

    # Final safety net regardless of who wrote the text.
    for block in content.experience + content.projects:
        for b in block.bullets:
            b.text = behuman.scrub(b.text)
    content.summary = behuman.scrub(content.summary)

    all_text = " ".join([content.summary] +
                        [b.text for blk in content.experience + content.projects for b in blk.bullets])
    result["lint"] = behuman.lint(all_text)
    if result["lint"]:
        log(f"[latex] BeHuman check: {behuman.report(all_text)}")
    else:
        log("[latex] BeHuman check: clean")
    return result


def _llm_rewrite(content: ResumeContent, jd_text: str, *,
                 log: Callable[[str], None]) -> dict[str, Any]:
    try:
        from agent import llm as provider
    except ImportError:
        return {"llm": {"ok": False, "error": "agent package unavailable"}}

    ok, why = provider.available()
    if not ok:
        log(f"[latex] LLM pass skipped: {why}")
        return {"llm": {"ok": False, "error": why}}

    bullets = [b.text for blk in content.experience + content.projects for b in blk.bullets]
    if not bullets:
        return {"llm": {"ok": False, "error": "no bullets to rewrite"}}

    prompt = (
        f"JOB POSTING:\n{jd_text.strip()[:9000]}\n\n"
        f"CANDIDATE SUMMARY:\n{content.summary}\n\n"
        f"BULLETS (rewrite only what you can genuinely improve):\n"
        + "\n".join(f"- {b}" for b in bullets[:24])
        + "\n\nRewrite the summary for this posting and improve the bullets."
    )
    try:
        data = provider.complete_json(prompt, REWRITE_SCHEMA, system=REWRITE_SYSTEM,
                                      default={"summary": "", "bullets": []},
                                      purpose="tailor")
    except Exception as exc:
        log(f"[latex] LLM pass failed: {type(exc).__name__}: {exc}")
        return {"llm": {"ok": False, "error": str(exc)[:200]}}

    mapping = {_norm(x.get("original", "")): (x.get("revised") or "").strip()
               for x in (data.get("bullets") or []) if x.get("original") and x.get("revised")}

    # A rewrite is only accepted if it passes the house style. `enforce()` fixes
    # hyphens and dates mechanically at render time, but it cannot fix voice —
    # a model that returns "Responsible for the frontend" or "I led the team"
    # has produced a worse line than the one it replaced, so keep the original.
    changed = rejected = 0
    for block in content.experience + content.projects:
        for b in block.bullets:
            revised = mapping.get(_norm(b.text))
            if not revised or revised == b.text:
                continue
            problems = resume_style.lint(resume_style.enforce(revised))
            if problems:
                rejected += 1
                log(f"[latex] kept the original bullet — rewrite broke house style "
                    f"({problems[0]})")
                continue
            b.text = revised
            changed += 1

    # The house style caps the summary at two rendered lines (~230 chars in
    # 10.5pt Times across 7.5in). A longer rewrite is rejected outright: the
    # curated summary already fits, and the audit gate would bounce the PDF.
    new_summary = (data.get("summary") or "").strip()
    if (40 < len(new_summary) <= 230
            and not resume_style.lint(resume_style.enforce(new_summary))):
        content.summary = new_summary

    log(f"[latex] LLM rewrote {changed} bullet(s) and the summary "
        f"({provider.config().get('model')})"
        + (f"; {rejected} rejected on house style" if rejected else ""))
    return {"llm": {"ok": True, "model": provider.config().get("model")},
            "rewritten": changed, "rejected": rejected}


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

def _styled(s: Any) -> str:
    """House style, then LaTeX escaping. Every piece of prose goes through here."""
    return tex_escape(resume_style.enforce(s))



def render_tex(content: ResumeContent) -> str:
    env = Environment(loader=FileSystemLoader(str(CV_DATA)), autoescape=False, **JINJA_KW)
    env.filters["tex"] = tex_escape
    template = env.get_template(TEMPLATE_NAME)

    # Contact ordering comes from the shared helper so this renderer and the
    # DOCX/TXT one cannot drift; only the LaTeX escaping and the hyperlink
    # wrapping are format-specific. URLs get \href on top of the visible text.
    url_by_text = {re.sub(r"^https?://(www\.)?", "", (l.get("url") or "")).rstrip("/"): l["url"]
                   for l in (content.links or []) if l.get("url")}
    shown = [
        rf"\href{{{tex_url(url_by_text[part])}}}{{{tex_escape(part)}}}"
        if part in url_by_text else tex_escape(part)
        for part in resume_style.contact_parts(content)
    ]
    contact_line = r" \textbar{} ".join(shown)

    # The reference merges awards, certifications and languages into one
    # bulleted section: each award is its own bullet, all certifications share
    # one "Certifications:" bullet, languages share one "Languages:" bullet.
    achievements: list[str] = [_styled(a) for a in content.awards if a]
    if content.certifications:
        achievements.append(r"\textbf{Certifications:} "
                            + ", ".join(_styled(c) for c in content.certifications if c))
    if content.languages:
        achievements.append(r"\textbf{Languages:} "
                            + ", ".join(_styled(l) for l in content.languages if l))

    ctx = {
        "name": tex_escape(content.name),
        "title": _styled(content.title),
        "contact_line": contact_line,
        "summary": _styled(content.summary),
        "skills": resume_style.skill_rows(content.skills),
        "education": [_styled(e) for e in content.education if e],
        "education_entries": [{
            "institution": _styled(e.get("institution")), "location": _styled(e.get("location")),
            "degree": _styled(e.get("degree")), "period": _styled(e.get("period")),
            "courses": _styled(e.get("courses")),
        } for e in content.education_entries],
        "achievements": achievements,
        "experience": [{
            "role": _styled(b.role), "company": _styled(b.company),
            "period": _styled(b.period), "location": _styled(b.location),
            "bullets": [_styled(x.text) for x in b.bullets],
        } for b in content.experience],
        "projects": [{
            "name": _styled(b.name), "tech": _styled(b.tech),
            "bullets": [_styled(x.text) for x in b.bullets],
        } for b in content.projects],
    }
    return template.render(ctx)


def find_engine() -> str | None:
    for name in ENGINES:
        for candidate in (LOCAL_TOOLS / f"{name}.exe", LOCAL_TOOLS / name):
            if candidate.is_file():
                return str(candidate)
        found = shutil.which(name)
        if found:
            return found
    return None


def engine_name(engine: str | None) -> str:
    return Path(engine).stem if engine else ""


def compile_pdf(tex_path: Path, *, log: Callable[[str], None] = print) -> tuple[Path | None, str]:
    """Compile to PDF if a LaTeX engine exists. Returns (pdf_path, message)."""
    engine = find_engine()
    if not engine:
        return None, ("No LaTeX engine found. Run `python tools/install_tex.py` from Backend/ "
                      "to fetch Tectonic (one 20 MB binary, no system install), or install "
                      "MiKTeX / TeX Live. The .tex file is ready to compile or paste into "
                      "Overleaf either way.")

    name = engine_name(engine)
    # cwd is the output directory, so the engine's own output flag must be an
    # absolute path — a relative one would resolve against cwd a second time.
    out_dir = tex_path.parent.resolve()
    if name == "latexmk":
        cmd = [engine, "-pdf", "-interaction=nonstopmode", f"-outdir={out_dir}", tex_path.name]
    elif name == "tectonic":
        cmd = [engine, "--outdir", str(out_dir), tex_path.name]
    else:
        cmd = [engine, "-interaction=nonstopmode", "-halt-on-error",
               "-output-directory", str(out_dir), tex_path.name]

    passes = 1 if name in ("latexmk", "tectonic") else 2
    for i in range(passes):
        proc = subprocess.run(cmd, cwd=str(out_dir), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=180)
        if proc.returncode != 0:
            tail = ((proc.stdout or "") + (proc.stderr or ""))[-1200:]
            log(f"[latex] {name} failed on pass {i + 1}")
            return None, f"{name} failed: {tail[-500:]}"

    pdf = out_dir / f"{tex_path.stem}.pdf"
    if not pdf.is_file():
        return None, f"{name} reported success but produced no PDF."
    log(f"[latex] compiled with {name}: {pdf.name}")
    return pdf, f"Compiled with {name}."


def clamp_role_bullets(content: ResumeContent, *, log: Callable[[str], None] = print) -> None:
    """Cap every Experience entry at the house maximum, keeping the best lines."""
    for blk in content.experience:
        if len(blk.bullets) > MAX_ROLE_BULLETS:
            blk.bullets[:] = blk.bullets[:MAX_ROLE_BULLETS]
    thin = [b.role or b.company for b in content.experience
            if len(b.bullets) < MIN_ROLE_BULLETS]
    if thin:
        log(f"[latex] below the {MIN_ROLE_BULLETS}-bullet floor: {', '.join(thin)} "
            f"— add bullets in profile.yaml")


def trim_to_budget(content: ResumeContent, *,
                   max_awards: int = 4, log: Callable[[str], None] = print) -> None:
    """
    Pre-trim obviously surplus content before the measured fitting loop runs.

    Experience bullets are not touched here: they are the substance of the
    document and the floor is enforced. Project selection already happened in
    `tailor()`; here only their bullet counts are clamped to the cap.
    """
    clamp_role_bullets(content, log=log)
    content.awards = content.awards[:max_awards]
    for proj in content.projects:
        if len(proj.bullets) > MAX_PROJECT_BULLETS:
            proj.bullets[:] = proj.bullets[:MAX_PROJECT_BULLETS]
    thin = [p.name for p in content.projects if len(p.bullets) < MIN_PROJECT_BULLETS]
    if thin:
        log(f"[latex] project(s) below the {MIN_PROJECT_BULLETS}-bullet floor: "
            f"{', '.join(thin)} — add bullets in profile.yaml")


def _drop_weakest(content: ResumeContent) -> bool:
    """
    Remove the single least valuable element. Returns False when nothing is left.

    Order matters more than it looks. Cutting an Experience bullet costs real
    evidence, so everything cheaper goes first: languages, then surplus project
    bullets, then surplus credentials, then whole low-relevance projects.
    Floors are absolute: no role below MIN_ROLE_BULLETS, no project below
    MIN_PROJECT_BULLETS, never fewer than MIN_PROJECTS projects. A resume that
    cannot fit the page budget with everything at its floor stays long, and
    the log says so.
    """
    # Cheap lines first: the languages bullet, then the coursework line.
    if content.languages:
        content.languages = []
        return True
    for entry in content.education_entries:
        if entry.get("courses"):
            entry["courses"] = ""
            return True
    if len(content.education) > 1:
        content.education.pop()
        return True

    # Projects give up bullets down to their floor, weakest project first.
    # The project itself always survives.
    for proj in sorted(content.projects, key=lambda p: sum(b.score for b in p.bullets)):
        if len(proj.bullets) > MIN_PROJECT_BULLETS:
            proj.bullets.remove(min(proj.bullets[1:], key=lambda b: b.score))
            return True

    # Surplus credentials, weakest (stored last) first.
    if len(content.awards) > 2:
        content.awards.pop()
        return True
    if len(content.certifications) > 2:
        content.certifications.pop()
        return True

    # Whole projects go least-relevant first, but never below MIN_PROJECTS:
    # a still-overflowing page sheds the trading platform before it sheds a
    # line of real work experience.
    if len(content.projects) > MIN_PROJECTS:
        content.projects.remove(
            min(content.projects, key=lambda p: sum(b.score for b in p.bullets)))
        return True

    # Only roles above the floor can give a bullet up, weakest line first.
    candidates = [(blk, b) for blk in content.experience
                  if len(blk.bullets) > MIN_ROLE_BULLETS for b in blk.bullets[1:]]
    if candidates:
        blk, bullet = min(candidates, key=lambda pair: pair[1].score)
        blk.bullets.remove(bullet)
        return True

    # Last resorts, in increasing order of pain.
    if content.awards:
        content.awards.pop()
        return True
    if content.certifications:
        content.certifications.pop()
        return True
    return False


def build(content: ResumeContent, out_dir: Path, stem: str = "resume", *,
          max_pages: int = MAX_PAGES, max_passes: int = 24,
          log: Callable[[str], None] = print) -> dict[str, Any]:
    """
    Render the .tex and compile it.

    The real page count from the compiled PDF drives trimming: render, compile,
    and if it spilled past `max_pages` drop the lowest-scoring line and try
    again. Measuring beats guessing a bullet budget, because how much fits
    depends on how long the lines actually are. The default budget is two
    pages — enough for every role and every project at healthy bullet counts.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    trim_to_budget(content, log=log)

    tex_path = out_dir / f"{stem}.tex"
    tex_source = render_tex(content)
    tex_path.write_text(tex_source, encoding="utf-8")

    pdf, message = compile_pdf(tex_path, log=log)
    pages = _page_count(pdf) if pdf else None

    if pdf and pages and pages > max_pages:
        for _ in range(max_passes):
            if not _drop_weakest(content):
                break
            tex_source = render_tex(content)
            tex_path.write_text(tex_source, encoding="utf-8")
            pdf, message = compile_pdf(tex_path, log=lambda _: None)
            pages = _page_count(pdf) if pdf else pages
            if pages <= max_pages:
                break
        if pages and pages <= max_pages:
            log(f"[latex] trimmed to fit: {pages} page(s)")
        else:
            log(f"[latex] {pages} pages against a budget of {max_pages}, with every "
                f"role and project at its bullet floor — the house style keeps the "
                f"content rather than cutting further. Shorten skills or education "
                f"in profile.yaml to recover space.")

    log(f"[latex] {tex_path.name} ({len(tex_source)} chars)"
        + (f", {pages} page(s)" if pages else ""))
    return {
        "tex": tex_path,
        "texSource": tex_source,
        "pdf": pdf,
        "pages": pages,
        "engine": engine_name(find_engine()),
        "message": message,
    }


def _page_count(pdf: Path) -> int | None:
    try:
        import fitz

        with fitz.open(str(pdf)) as doc:
            return doc.page_count
    except Exception:
        return None
