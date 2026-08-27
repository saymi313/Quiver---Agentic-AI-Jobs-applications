"""
Several resumes, one engine.

A designer applying to design roles and to frontend roles wants two different
documents, not one that tries to be both. Each profile is a `profile.yaml` in
its own right, so everything downstream — the tailor, the fitter, the house
style audit — works on it unchanged; only which file gets loaded differs.

Layout:

    cv_data/profile.yaml            the original, always present, named "main"
    cv_data/profiles/design.yaml    anything else

The original stays where it is rather than moving into the folder. It is
referenced by name in half a dozen places and by muscle memory in more, and a
tidier layout is not worth breaking either.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

import yaml

from .config import CV_DATA

PROFILES_DIR = CV_DATA / "profiles"
MAIN = "main"
MAIN_PATH = CV_DATA / "profile.yaml"

# A profile name is a filename. Keep it to something that cannot escape the
# directory or collide with the shell.
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,38}$")


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9_-]+", "-", (name or "").strip().lower()).strip("-")[:39]


def valid(name: str) -> bool:
    return bool(NAME_RE.match(name or ""))


def path_for(name: str | None) -> Path:
    """The file behind a profile name. Unknown names fall back to the main one."""
    slug = _slug(name or MAIN)
    if not slug or slug == MAIN:
        return MAIN_PATH
    candidate = PROFILES_DIR / f"{slug}.yaml"
    return candidate if candidate.is_file() else MAIN_PATH


def exists(name: str) -> bool:
    slug = _slug(name)
    return slug == MAIN and MAIN_PATH.is_file() or (PROFILES_DIR / f"{slug}.yaml").is_file()


def _describe(path: Path, name: str) -> dict[str, Any]:
    """Enough to tell two profiles apart in a dropdown, without parsing deeply."""
    info: dict[str, Any] = {"name": name, "file": path.name, "exists": path.is_file()}
    if not path.is_file():
        return info
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        info["error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
        return info
    candidate = data.get("candidate") or {}
    target = data.get("target") or {}
    info.update({
        "title": candidate.get("title") or "",
        "summary": (candidate.get("summary") or "").strip()[:160],
        "experience": len(data.get("experience") or []),
        "projects": len(data.get("projects") or []),
        "skills": len(data.get("skills") or []),
        # Which role categories this profile is meant for. A designer's resume
        # and an engineer's are different documents, and the point of having
        # both is that the right one is picked without being asked.
        "categories": [str(c) for c in (target.get("categories") or [])],
        # The saved editor style, so the editor opens on it rather than the
        # defaults.
        "render": data.get("render") if isinstance(data.get("render"), dict) else None,
        "data": data,
    })
    return info


def listing() -> list[dict[str, Any]]:
    """Every profile, main first."""
    out = [_describe(MAIN_PATH, MAIN)]
    if PROFILES_DIR.is_dir():
        for path in sorted(PROFILES_DIR.glob("*.yaml")):
            out.append(_describe(path, path.stem))
    return out


def default_name() -> str:
    """Which profile the agent uses when nothing else is specified."""
    from agent import store

    try:
        name = (store.get_setting("tailoring", {}) or {}).get("profile") or MAIN
    except Exception:
        return MAIN
    return name if exists(name) else MAIN


def set_default(name: str) -> bool:
    from agent import store

    slug = _slug(name)
    if not exists(slug):
        return False
    current = dict(store.get_setting("tailoring", {}) or {})
    current["profile"] = slug
    store.set_setting("tailoring", current)
    return True


def create(name: str, *, copy_from: str = MAIN) -> dict[str, Any]:
    """
    A new profile, copied from an existing one.

    Duplicating rather than starting empty is deliberate: a blank profile.yaml
    produces a resume with no experience on it, and the tailor would happily
    compile that. Starting from a real document means the first edit is a
    change rather than a rebuild.
    """
    # "My Design CV" becoming "my-design-cv" is helpful. "../escape" becoming
    # "escape" is not: slugging it away would create a file under a name the
    # user never asked for and quietly hide that they typed something odd.
    # Path characters are refused rather than cleaned.
    if re.search(r"[\\/.]|^\s*$", name or ""):
        return {"ok": False,
                "error": "A profile name cannot contain slashes or dots."}

    slug = _slug(name)
    if not valid(slug):
        return {"ok": False, "error": "Use letters, numbers, dashes and underscores."}
    if slug == MAIN or exists(slug):
        return {"ok": False, "error": f"A profile called '{slug}' already exists."}

    source = path_for(copy_from)
    if not source.is_file():
        return {"ok": False, "error": f"Nothing to copy from ('{copy_from}')."}

    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    target = PROFILES_DIR / f"{slug}.yaml"
    shutil.copyfile(source, target)
    return {"ok": True, "name": slug, "file": target.name, "copiedFrom": copy_from}


def _parsed_to_profile(parsed: Any) -> dict[str, Any]:
    """
    Map a parsed resume onto the profile YAML shape.

    Only what the document actually carried, kept in the structure the tailor
    and the LaTeX builder already understand — so an imported DOCX produces the
    same kind of profile a hand-written one does. Bullets keep their text; no
    tags are invented, because a tag the document did not carry would be a
    guess, and the tailor treats an untagged bullet as available to any role.
    """
    contact = getattr(parsed, "contact", {}) or {}
    links = []
    for label, key in (("LinkedIn", "linkedin"), ("GitHub", "github"), ("Portfolio", "website")):
        if contact.get(key):
            links.append({"label": label, "url": contact[key]})

    def entries(items):
        out = []
        for e in items or []:
            row = {
                "company": getattr(e, "organization", "") or "",
                "role": getattr(e, "title", "") or getattr(e, "header", "") or "",
                "period": getattr(e, "period", "") or "",
                "bullets": [{"text": b} for b in (getattr(e, "bullets", []) or []) if b.strip()],
            }
            if row["role"] or row["bullets"]:
                out.append(row)
        return out

    sections = getattr(parsed, "sections", {}) or {}
    skills = [{"line": line} for line in sections.get("skills", []) if line.strip()]
    education = []
    for line in sections.get("education", []):
        if line.strip():
            education.append({"institution": line.strip()})

    summary = " ".join(sections.get("summary", []) or sections.get("about", [])).strip()

    return {
        "candidate": {
            "name": getattr(parsed, "name", "") or "",
            "title": getattr(parsed, "headline", "") or "",
            "email": contact.get("email", ""),
            "phone": contact.get("phone", ""),
            "location": contact.get("location", ""),
            "links": links,
            "summary": summary,
        },
        "experience": entries(getattr(parsed, "experience", [])),
        "projects": entries(getattr(parsed, "projects", [])),
        "education": education,
        "skills": skills,
    }


def import_document(name: str, path: Path) -> dict[str, Any]:
    """
    Create a profile from an uploaded resume — DOCX as well as PDF.

    The document is parsed into the same structure a hand-written profile has:
    contact, experience with its bullets, projects, education and skills. What
    survives the parse survives into the tailored PDF; a complex two-column
    layout may not carry perfectly, which is the honest limit of reading a
    finished document back into fields.
    """
    if re.search(r"[\\/.]|^\s*$", name or ""):
        return {"ok": False, "error": "A profile name cannot contain slashes or dots."}
    slug = _slug(name)
    if not valid(slug):
        return {"ok": False, "error": "Use letters, numbers, dashes and underscores."}
    if slug == MAIN or exists(slug):
        return {"ok": False, "error": f"A profile called '{slug}' already exists."}

    from .resume_parse import parse_resume

    try:
        parsed = parse_resume(path)
    except Exception as exc:
        return {"ok": False, "error": f"Could not read that document: {exc}"}

    profile = _parsed_to_profile(parsed)
    if not profile["experience"] and not profile["skills"]:
        return {"ok": False, "error": ("Almost nothing could be read out of that file — it may be "
                                       "a scan or an image-only export. Try a text-based PDF or DOCX.")}

    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    target = PROFILES_DIR / f"{slug}.yaml"
    header = ("# Imported from an uploaded resume. Every line here came from that\n"
              "# document; edit freely, but keep the rule the rest of the profiles hold\n"
              "# to — add facts, never invent a metric that was not on the page.\n\n")
    try:
        target.write_text(header + yaml.safe_dump(profile, sort_keys=False, allow_unicode=True),
                          encoding="utf-8")
    except Exception as exc:
        return {"ok": False, "error": f"Could not write the profile: {exc}"}

    described = _describe(target, slug)
    return {"ok": True, "name": slug,
            "counts": {"experience": len(profile["experience"]),
                       "projects": len(profile["projects"]),
                       "skills": len(profile["skills"])},
            **described}


def render_options(name: str | None) -> dict[str, Any]:
    """The saved editor style for a profile, or {} — read from its `render:` block."""
    path = path_for(name)
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    render = data.get("render")
    return render if isinstance(render, dict) else {}


def set_render_options(name: str, options: dict[str, Any]) -> dict[str, Any]:
    """
    Persist the editor's choices into the profile so every resume built from it
    uses them — the tailored ones for real applications included.
    """
    from .latex_resume import RenderOptions

    path = path_for(name)
    if not path.is_file():
        return {"ok": False, "error": f"No profile named '{name}'."}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:120]}"}

    # Round-trip through RenderOptions so only valid, complete options are stored.
    opts = RenderOptions.coerce(options)
    data["render"] = {
        "template": opts.template, "font": opts.font, "font_size": opts.font_size,
        "align": opts.align, "fit_one_page": opts.fit_one_page, "sections": list(opts.sections),
    }
    try:
        path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    except Exception as exc:
        return {"ok": False, "error": f"could not write the profile: {exc}"}
    return {"ok": True, "render": data["render"]}


def delete(name: str) -> dict[str, Any]:
    """Remove a profile. The main one cannot be deleted — it is the fallback."""
    slug = _slug(name)
    if slug == MAIN:
        return {"ok": False, "error": "The main profile is the fallback and cannot be deleted."}
    target = PROFILES_DIR / f"{slug}.yaml"
    if not target.is_file():
        return {"ok": False, "error": f"No profile called '{slug}'."}
    target.unlink()
    if default_name() == slug:
        set_default(MAIN)
    return {"ok": True, "name": slug}


def read(name: str) -> str:
    path = path_for(name)
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def read_dict(name: str) -> dict[str, Any]:
    """Return full structured profile dictionary."""
    path = path_for(name)
    if not path.is_file():
        return {}
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def write_dict(name: str, data: dict[str, Any]) -> dict[str, Any]:
    """Save structured profile data directly to YAML."""
    if not isinstance(data, dict) or not data.get("candidate"):
        return {"ok": False, "error": "A profile needs a candidate section."}
    path = path_for(name)
    if _slug(name) != MAIN and not path.is_file():
        return {"ok": False, "error": f"No profile called '{name}'."}
    try:
        text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
        path.write_text(text, encoding="utf-8")
    except Exception as exc:
        return {"ok": False, "error": f"Could not save profile: {exc}"}
    return {"ok": True, "name": _slug(name) or MAIN}


def write(name: str, text: str) -> dict[str, Any]:
    """
    Save an edited profile, after checking it still parses.

    Writing YAML that does not load would break every future build with a
    parse error a long way from the edit that caused it.
    """
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return {"ok": False, "error": f"That is not valid YAML: {str(exc)[:200]}"}
    if not isinstance(data, dict) or not data.get("candidate"):
        return {"ok": False, "error": "A profile needs a top level `candidate:` section."}

    path = path_for(name)
    if _slug(name) != MAIN and not path.is_file():
        return {"ok": False, "error": f"No profile called '{name}'."}
    path.write_text(text, encoding="utf-8")
    return {"ok": True, "name": _slug(name) or MAIN}


def set_categories(name: str, categories: list[str]) -> dict[str, Any]:
    """
    Point a profile at the role categories it is written for.

    Stored in the profile's own YAML rather than in settings, because it is a
    fact about that document — copy the file somewhere else and it stays true.
    """
    path = path_for(name)
    if not path.is_file():
        return {"ok": False, "error": f"No profile named '{name}'."}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:120]}"}

    target = dict(data.get("target") or {})
    target["categories"] = [str(c).strip() for c in (categories or []) if str(c).strip()]
    data["target"] = target
    try:
        path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
                        encoding="utf-8")
    except Exception as exc:
        return {"ok": False, "error": f"could not write the profile: {exc}"}
    return {"ok": True, **_describe(path, name)}


def for_category(slug: str | None) -> str:
    """
    Which profile to build a resume from for a role in this category.

    A profile that names the category wins; otherwise the configured default.
    Two profiles claiming the same category is not an error — the first by name
    wins, deterministically, rather than the choice depending on disk order.
    """
    if not slug:
        return default_name()
    for row in listing():
        if slug in (row.get("categories") or []):
            return row["name"]
    return default_name()
