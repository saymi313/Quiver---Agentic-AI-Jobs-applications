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

# The house style requires 3 to 5 bullets under every Experience entry. The
# fitter treats the lower bound as a floor it may not cross: a role reduced to
# one line reads as a job the candidate barely held. If the page still overflows
# with every role at its floor, the resume runs to two pages instead.
#
# Defined here rather than beside the fitter because `tailor()` uses
# MAX_ROLE_BULLETS as a default argument, which Python evaluates at import.
MIN_ROLE_BULLETS = 3
MAX_ROLE_BULLETS = 5

# Same delimiters cv_engine.py uses, so one template serves both paths.
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
           use_llm: bool = True, max_bullets: int = MAX_ROLE_BULLETS, max_projects: int = 3,
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

    for block in content.projects:
        for b in block.bullets:
            b.score = score_bullet(b, jd, hint_tags)
        block.bullets.sort(key=lambda b: -b.score)
        block.bullets = block.bullets[:2]
    content.projects.sort(
        key=lambda p: -sum(b.score for b in p.bullets))
    content.projects = [p for p in content.projects if p.bullets][:max_projects]

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
                                      default={"summary": "", "bullets": []})
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

    new_summary = (data.get("summary") or "").strip()
    if len(new_summary) > 40 and not resume_style.lint(resume_style.enforce(new_summary)):
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


def _skill_rows(lines: list[str]) -> list[dict[str, str]]:
    """
    Split `Languages: JavaScript, C++` into a bold category and its list.

    The house style wants categorised bullets rather than a paragraph, so a
    line with no colon still becomes a row — it just gets a generic label
    rather than being silently dropped.
    """
    rows: list[dict[str, str]] = []
    for line in lines:
        if not line or not line.strip():
            continue
        label, sep, items = line.partition(":")
        if not sep or len(label) > 40:
            rows.append({"label": "Also", "value": _styled(line)})
        else:
            rows.append({"label": _styled(label), "value": _styled(items)})
    return rows


def render_tex(content: ResumeContent) -> str:
    env = Environment(loader=FileSystemLoader(str(CV_DATA)), autoescape=False, **JINJA_KW)
    env.filters["tex"] = tex_escape
    template = env.get_template(TEMPLATE_NAME)

    # Contact line in the reference layout: location, phone, email, then the
    # full URLs spelled out. It wraps to a second centred line rather than
    # abbreviating — a text parser reads the whole address, and the reference
    # resume does exactly this. Nothing here is style-enforced: a hyphen inside
    # linkedin.com/in/usairam-saeed-148044285 is part of the address.
    parts: list[str] = []
    if content.location:
        parts.append(_styled(content.location))
    if content.phone:
        parts.append(tex_escape(resume_style.phone(content.phone)))
    if content.email:
        parts.append(tex_escape(content.email))
    for link in content.links:
        url = link.get("url", "")
        if not url:
            continue
        shown = re.sub(r"^https?://(www\.)?", "", url).rstrip("/")
        parts.append(rf"\href{{{tex_url(url)}}}{{{tex_escape(shown)}}}")
    contact_line = r" \textbar{} ".join(p for p in parts if p)

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
        "skills": _skill_rows(content.skills),
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


def trim_to_budget(content: ResumeContent, *, max_bullets: int = 18,
                   max_awards: int = 4, log: Callable[[str], None] = print) -> None:
    """
    Pre-trim obviously surplus content before the measured fitting loop runs.

    Experience bullets are not touched here: they are the substance of the
    document and the floor is enforced. Projects are the flexible part, and are
    not in the house section order at all, so they absorb the cut first.
    """
    clamp_role_bullets(content, log=log)
    content.awards = content.awards[:max_awards]

    total = sum(len(b.bullets) for b in content.experience + content.projects)
    dropped = 0
    while total > max_bullets and content.projects:
        weakest = min(content.projects, key=lambda p: sum(b.score for b in p.bullets))
        total -= len(weakest.bullets)
        content.projects.remove(weakest)
        dropped += 1
    if dropped:
        log(f"[latex] dropped {dropped} project(s) to make room for the experience bullets")


def _drop_weakest(content: ResumeContent) -> bool:
    """
    Remove the single least valuable element. Returns False when nothing is left.

    Order matters more than it looks. Cutting an Experience bullet costs real
    evidence, so everything cheaper goes first: languages, then projects, then
    surplus awards and certifications. Only after all of that are bullets
    touched, and never below MIN_ROLE_BULLETS. Getting this order backwards
    strips a resume to one bullet per role to save a two-line Languages block.
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

    # Projects slim down before any disappears: every project drops to its
    # single strongest bullet first. Whole projects then go weakest-first, but
    # the best one is protected until almost nothing else remains — the
    # reference layout has a Projects section, and the old order deleted all of
    # them while a coursework line survived.
    for proj in sorted(content.projects, key=lambda p: sum(b.score for b in p.bullets)):
        if len(proj.bullets) > 1:
            proj.bullets.remove(min(proj.bullets[1:], key=lambda b: b.score))
            return True
    if len(content.projects) > 1:
        content.projects.remove(min(content.projects,
                                    key=lambda p: sum(b.score for b in p.bullets)))
        return True

    # Surplus credentials, weakest (stored last) first.
    if len(content.awards) > 2:
        content.awards.pop()
        return True
    if len(content.certifications) > 2:
        content.certifications.pop()
        return True

    # Only roles above the floor can give a bullet up, weakest line first.
    candidates = [(blk, b) for blk in content.experience
                  if len(blk.bullets) > MIN_ROLE_BULLETS for b in blk.bullets[1:]]
    if candidates:
        blk, bullet = min(candidates, key=lambda pair: pair[1].score)
        blk.bullets.remove(bullet)
        return True

    # Last resorts, in increasing order of pain.
    if content.projects:
        content.projects.clear()
        return True
    if content.awards:
        content.awards.pop()
        return True
    if content.certifications:
        content.certifications.pop()
        return True
    return False


def build(content: ResumeContent, out_dir: Path, stem: str = "resume", *,
          one_page: bool = True, max_passes: int = 24,
          log: Callable[[str], None] = print) -> dict[str, Any]:
    """
    Render the .tex and compile it.

    With `one_page`, the real page count from the compiled PDF drives trimming:
    render, compile, and if it spilled onto a second page drop the lowest-scoring
    line and try again. Measuring beats guessing a bullet budget, because how much
    fits depends on how long the lines actually are.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    if one_page:
        trim_to_budget(content, log=log)

    tex_path = out_dir / f"{stem}.tex"
    tex_source = render_tex(content)
    tex_path.write_text(tex_source, encoding="utf-8")

    pdf, message = compile_pdf(tex_path, log=log)
    pages = _page_count(pdf) if pdf else None

    if one_page and pdf and pages and pages > 1:
        for _ in range(max_passes):
            if not _drop_weakest(content):
                break
            tex_source = render_tex(content)
            tex_path.write_text(tex_source, encoding="utf-8")
            pdf, message = compile_pdf(tex_path, log=lambda _: None)
            pages = _page_count(pdf) if pdf else pages
            if pages == 1:
                break
        if pages == 1:
            log("[latex] trimmed to fit: 1 page")
        else:
            log(f"[latex] {pages} pages, and every role is at the {MIN_ROLE_BULLETS}-bullet "
                f"floor — the house style keeps the bullets rather than cutting to one "
                f"page. Shorten skills or education in profile.yaml to recover a page.")

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
