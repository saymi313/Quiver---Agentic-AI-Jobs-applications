"""
Load cv_data/profile.yaml, select bullets (all or JD-tailored), render Jinja2
LaTeX, compile to PDF with pdflatex/latexmk if available.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

BASE_DIR = Path(__file__).parent
CV_DATA = BASE_DIR / "cv_data"
PROFILE_PATH = CV_DATA / "profile.yaml"
TEMPLATE_NAME = "template.tex.j2"
OUTPUTS_DIR = BASE_DIR / "outputs"
APP_LOG = BASE_DIR / "applications.jsonl"

# Jinja2 delimiters: avoid clashing with LaTeX { }
JINJA_KW = dict(
    block_start_string="[%",
    block_end_string="%]",
    variable_start_string="[[",
    variable_end_string="]]",
    comment_start_string="[#",
    comment_end_string="#]",
)


def tex_escape(s: str) -> str:
    if not s:
        return ""
    out: list[str] = []
    for c in s:
        if c == "\\":
            out.append(r"\textbackslash{}")
        elif c == "{":
            out.append(r"\{")
        elif c == "}":
            out.append(r"\}")
        elif c == "$":
            out.append(r"\$")
        elif c == "&":
            out.append(r"\&")
        elif c == "#":
            out.append(r"\#")
        elif c == "_":
            out.append(r"\_")
        elif c == "%":
            out.append(r"\%")
        elif c == "~":
            out.append(r"\textasciitilde{}")
        elif c == "^":
            out.append(r"\textasciicircum{}")
        else:
            out.append(c)
    return "".join(out)


def href_url_escape(url: str) -> str:
    """Minimal fixes for common URL chars inside hyperref first argument."""
    if not url:
        return ""
    return url.replace("%", r"\%").replace("#", r"\#")


def build_link_line(links: list[dict]) -> str:
    parts: list[str] = []
    for item in (links or []):
        if not item:
            continue
        label = item.get("label", "")
        url = item.get("url", "")
        if not url:
            continue
        parts.append(
            r"\href{"
            + href_url_escape(url)
            + "}{"
            + tex_escape(label)
            + "}"
        )
    if not parts:
        return ""
    return r" | \quad ".join(parts)


def load_profile(path: Path | None = None) -> dict[str, Any]:
    p = path or PROFILE_PATH
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f)


def normalize_jd(text: str) -> str:
    t = text.lower()
    t = re.sub(r"https?://\S+", " ", t)
    t = re.sub(r"[^a-z0-9\s\-+/]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def jd_hash(text: str) -> str:
    n = normalize_jd(text)
    return hashlib.sha256(n.encode("utf-8")).hexdigest()[:16]


def score_tags_against_jd(tags: list[str], jd_norm: str) -> float:
    """Higher is better. Tags are short keywords (e.g. react, stripe)."""
    if not tags:
        return 0.0
    score = 0.0
    jd = jd_norm
    for t in tags:
        if not t:
            continue
        t = t.lower().strip()
        if len(t) <= 1:
            continue
        if t in jd:
            score += 2.0
    return score


def apply_tag_hints(profile: dict, jd_norm: str) -> None:
    """Use optional tag_hints: boost when JD contains hint phrases."""
    hints: dict = profile.get("tag_hints") or {}
    extra: dict[str, float] = {}
    for key, phrase_list in hints.items():
        for phrase in phrase_list or []:
            p = (phrase or "").lower().strip()
            if len(p) > 1 and p in jd_norm:
                extra[key] = extra.get(key, 0.0) + 0.5
    profile["_hint_boosts"] = extra


def score_bullet(bullet: dict, jd_norm: str, hint_boosts: dict) -> float:
    tags = [str(x).lower() for x in (bullet.get("tags") or [])]
    s = score_tags_against_jd(tags, jd_norm)
    for k, boost in (hint_boosts or {}).items():
        if k in tags or any(k in t for t in tags):
            s += boost
    return s


def pick_top_bullets(
    items: list[dict],
    jd_norm: str,
    max_n: int,
    hint_boosts: dict,
) -> list[str]:
    scored: list[tuple[float, int, str]] = []
    for i, b in enumerate(items or []):
        sc = score_bullet(b, jd_norm, hint_boosts)
        text = (b.get("text") or "").strip()
        if not text:
            continue
        scored.append((sc, -i, text))
    # Stable: prefer higher score, then original order
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [t for _, __, t in scored[:max_n]]


def use_ai_summary(profile: dict, jd_norm: str) -> bool:
    if not jd_norm:
        return False
    keys = [
        " ai ", "machine learning", "ml ", " nlp", "llm", "data science",
        "deep learning", " computer vision", "pytorch", "tensorflow",
    ]
    s = f" {jd_norm} "
    return any(k.strip() in s for k in keys) or s.strip().startswith("ai ")


def build_experience_blocks(
    profile: dict, jd_text: str | None, static: bool
) -> list[dict[str, Any]]:
    defaults = profile.get("defaults") or {}
    max_b = int(defaults.get("max_bullets_per_role", 4))
    jd_norm = normalize_jd(jd_text) if jd_text else ""
    if jd_norm:
        apply_tag_hints(profile, jd_norm)
    hint_boosts = profile.get("_hint_boosts") or {}

    blocks: list[dict[str, Any]] = []
    for exp in profile.get("experience") or []:
        bullets_src = exp.get("bullets") or []
        role_tags = [str(t).lower() for t in (exp.get("tags") or [])]
        enriched: list[dict] = []
        for b in bullets_src:
            bt = [str(t).lower() for t in (b.get("tags") or [])]
            merged = {**b, "tags": list(dict.fromkeys(bt + role_tags))}
            enriched.append(merged)
        if static or not jd_norm:
            texts = [b.get("text", "").strip() for b in enriched if b.get("text")]
            if not static:
                texts = texts[:max_b]
        else:
            texts = pick_top_bullets(enriched, jd_norm, max_b, hint_boosts)
        if not texts:
            continue
        blocks.append(
            {
                "company": tex_escape(str(exp.get("company", ""))),
                "role": tex_escape(str(exp.get("role", ""))),
                "period": tex_escape(str(exp.get("period", ""))),
                "location": tex_escape(str(exp.get("location", ""))),
                "bullets": [tex_escape(t) for t in texts],
            }
        )
    return blocks


def build_project_blocks(
    profile: dict, jd_text: str | None, static: bool
) -> list[dict[str, Any]]:
    defaults = profile.get("defaults") or {}
    max_b = int(defaults.get("max_bullets_per_project", 3))
    jd_norm = normalize_jd(jd_text) if jd_text else ""
    if jd_norm:
        apply_tag_hints(profile, jd_norm)
    hint_boosts = profile.get("_hint_boosts") or {}

    out: list[dict[str, Any]] = []
    for proj in profile.get("projects") or []:
        name = proj.get("name", "")
        tech = proj.get("tech", "")
        bullets_src = proj.get("bullets") or []
        ptags = [str(t).lower() for t in (proj.get("tags") or [])]
        enriched = []
        for b in bullets_src:
            bt = [str(t).lower() for t in (b.get("tags") or [])]
            enriched.append({**b, "tags": list(dict.fromkeys(bt + ptags))})
        if static or not jd_norm:
            texts = [b.get("text", "").strip() for b in enriched if b.get("text")]
            if not static:
                texts = texts[:max_b]
        else:
            texts = pick_top_bullets(enriched, jd_norm, max_b, hint_boosts)
        if not texts:
            continue
        out.append(
            {
                "name": tex_escape(str(name)),
                "tech": tex_escape(str(tech)) if tech else "",
                "bullets": [tex_escape(t) for t in texts],
            }
        )
    return out


def build_summary(
    profile: dict, jd_text: str | None, static: bool
) -> str:
    c = profile.get("candidate") or {}
    jd_norm = normalize_jd(jd_text) if jd_text else ""
    if static or not jd_norm:
        return tex_escape(str(c.get("summary", "")).strip())
    modes = profile.get("modes") or {}
    if use_ai_summary(profile, jd_norm) and modes.get("ai_summary"):
        return tex_escape(str(modes["ai_summary"]).strip())
    return tex_escape(str(c.get("summary", "")).strip())


def jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(CV_DATA)),
        autoescape=select_autoescape(enabled_extensions=()),
        **JINJA_KW,
    )


def build_render_context(profile: dict, jd_text: str | None, static: bool) -> dict[str, Any]:
    c = profile.get("candidate") or {}
    link_line = build_link_line(c.get("links") or [])
    return {
        "name": tex_escape(str(c.get("name", ""))),
        "title": tex_escape(str(c.get("title", ""))),
        "email_href": href_url_escape(str(c.get("email", ""))),
        "email_show": tex_escape(str(c.get("email", ""))),
        "phone": tex_escape(str(c.get("phone", ""))),
        "location": tex_escape(str(c.get("location", ""))),
        "link_line": link_line,
        "summary": build_summary(profile, jd_text, static=static),
        "experience": build_experience_blocks(profile, jd_text, static=static),
        "projects": build_project_blocks(profile, jd_text, static=static),
        "education": [tex_escape(str(x.get("line", ""))) for x in (profile.get("education") or []) if x.get("line")],
        "skills": [tex_escape(str(x.get("line", ""))) for x in (profile.get("skills") or []) if x.get("line")],
    }


def render_tex(context: dict[str, Any], out_tex: Path) -> None:
    env = jinja_env()
    template = env.get_template(TEMPLATE_NAME)
    out_tex.write_text(template.render(context), encoding="utf-8")


def find_latex_engine() -> str | None:
    for cmd in ("latexmk", "pdflatex"):
        if shutil.which(cmd):
            return cmd
    return None


def compile_tex(tex_path: Path) -> Path:
    """
    Run pdflatex/latexmk in the .tex file's directory; return path to the PDF.
    """
    out_dir = tex_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    engine = find_latex_engine()
    if not engine:
        raise RuntimeError(
            "No LaTeX engine found. Install MiKTeX (Windows) or TeX Live, "
            "and ensure 'pdflatex' or 'latexmk' is on PATH."
        )
    work = str(out_dir)
    if engine == "latexmk":
        args = [
            "latexmk",
            "-pdf",
            "-interaction=nonstopmode",
            f"-outdir={work}",
            tex_path.name,
        ]
    else:
        args = [
            "pdflatex",
            "-interaction=nonstopmode",
            "-halt-on-error",
            "-file-line-error",
            "-output-directory",
            work,
            tex_path.name,
        ]
    for pass_num in range(2):
        r = subprocess.run(
            args,
            cwd=work,
            capture_output=True,
            text=True,
            timeout=180,
        )
        if r.returncode != 0:
            tail = (r.stdout or "") + (r.stderr or "")
            tail = tail[-4000:]
            raise RuntimeError(
                f"LaTeX failed (engine={engine}, pass {pass_num + 1}): {tail}"
            )
    pdf = out_dir / f"{tex_path.stem}.pdf"
    if not pdf.is_file():
        raise FileNotFoundError(f"Expected PDF at {pdf}")
    return pdf


def slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s or "application"


def append_application_log(entry: dict[str, Any]) -> None:
    with open(APP_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def run_build(
    *,
    profile_path: Path | None = None,
    jd_path: Path | None = None,
    jd_text: str | None = None,
    static: bool = True,
    out_slug: str | None = None,
    tex_only: bool = False,
) -> dict[str, Any]:
    """
    Build PDF (or .tex only). Returns metadata dict with paths, jd_hash, mode.
    """
    profile = load_profile(profile_path)
    jd_src = jd_text
    if jd_path and jd_path.is_file():
        jd_src = jd_path.read_text(encoding="utf-8", errors="replace")

    base_name = (out_slug or ("" if static else "job")).strip()
    h = jd_hash(jd_src) if jd_src else "nojd"
    if static:
        out_root = OUTPUTS_DIR / "static"
    else:
        if not jd_src or not str(jd_src).strip():
            raise ValueError("Tailored build requires a job description (file or --jd inline).")
        safe = slugify(base_name) if base_name else "job"
        out_root = OUTPUTS_DIR / "tailored" / f"{safe}_{h}"
    out_root.mkdir(parents=True, exist_ok=True)

    ctx = build_render_context(profile, jd_text=jd_src, static=static)
    tex_path = out_root / "resume.tex"
    render_tex(ctx, tex_path)

    if not static:
        checklist = (
            "# Manual application (portal)\n\n"
            "This resume was tailored to a job description. For Workday / Greenhouse / company sites:\n\n"
            "1. Open the job posting URL (add it to your tracker row).\n"
            f"2. Upload **{tex_path.parent.name}/resume.pdf** when the form asks for a CV.\n"
            "3. Paste your answers from memory or from `cv_data/profile.yaml` facts only.\n"
            "4. Solve CAPTCHA and submit yourself (do not use unattended bots).\n"
            f"5. JD hash (for audit): `{h}`\n"
        )
        (out_root / "MANUAL_APPLY.md").write_text(checklist, encoding="utf-8")

    meta: dict[str, Any] = {
        "mode": "static" if static else "tailored",
        "profile": str((profile_path or PROFILE_PATH).resolve()),
        "tex": str(tex_path.resolve()),
        "jd_hash": h if jd_src else None,
        "static": static,
    }

    if tex_only:
        meta["pdf"] = None
        append_application_log(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                **{k: v for k, v in meta.items() if k in ("mode", "tex", "jd_hash", "static")},
            }
        )
        return meta

    pdf = compile_tex(tex_path)
    meta["pdf"] = str(pdf.resolve())
    append_application_log(
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            **{k: v for k, v in meta.items()},
        }
    )
    return meta
