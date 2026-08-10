"""
Build the master resumes from cv_data/profile.yaml.

These are the untailored baselines — the file you send when there is no specific
job description to aim at, and the source the agent uploads to application forms.
Per-job tailoring happens in the Resume Tailor tab, which starts from the same
profile and reorders against the posting.

    python tools/build_resumes.py            # all variants
    python tools/build_resumes.py --variant fullstack

Variants map to the alternate summaries in profile.yaml (`modes`).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api import behuman, latex_resume as L  # noqa: E402
from api.config import CV_DATA  # noqa: E402

VARIANTS = {
    "fullstack": {
        "file": "Usairam_Saeed_Resume",
        "mode": None,
        "title": "Software Developer",
        "drop_tags": set(),
    },
    "ai": {
        "file": "Usairam_Saeed_AI_Engineer_Resume",
        "mode": "ai_summary",
        "title": "AI Software Engineer",
        "drop_tags": set(),
    },
    "uiux": {
        "file": "Usairam_Saeed_UIUX_Resume",
        "mode": "ux_summary",
        "title": "UI/UX Designer & Frontend Developer",
        "drop_tags": set(),
    },
}

# Which tags each variant leads with, so the same profile produces three
# genuinely different documents instead of three identical ones.
PRIORITY = {
    "fullstack": {"react", "node", "mongo", "api", "payments", "saas"},
    "ai": {"ai", "cv", "trading", "node"},
    "uiux": {"ux", "react", "performance"},
}


def build(variant: str, *, log=print) -> dict:
    spec = VARIANTS[variant]
    content = L.from_profile()
    raw = getattr(content, "_raw", {}) or {}

    if spec["mode"]:
        alt = (raw.get("modes") or {}).get(spec["mode"])
        if alt:
            content.summary = str(alt).strip()
    content.title = spec["title"]

    # No job description here, so rank by the variant's own emphasis.
    focus = PRIORITY[variant]
    for block in content.experience + content.projects:
        for b in block.bullets:
            b.score = 10.0 * len(focus.intersection(b.tags)) + (1.0 if any(
                ch.isdigit() for ch in b.text) else 0.0)
        block.bullets.sort(key=lambda b: -b.score)
    content.projects.sort(key=lambda p: -sum(b.score for b in p.bullets))

    if content.skills:
        tagged = {s["line"]: [str(t).lower() for t in (s.get("tags") or [])]
                  for s in (raw.get("skills") or []) if s.get("line")}
        content.skills.sort(key=lambda l: -len(focus.intersection(tagged.get(l, []))))

    out = L.build(content, CV_DATA, spec["file"], log=log)
    text = " ".join([content.summary] +
                    [b.text for blk in content.experience + content.projects for b in blk.bullets])
    out["behuman"] = behuman.report(text)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Build master resumes from profile.yaml")
    ap.add_argument("--variant", choices=list(VARIANTS) + ["all"], default="all")
    args = ap.parse_args()

    engine = L.engine_name(L.find_engine())
    if not engine:
        print("[warn] no LaTeX engine found — .tex will be written, PDFs will not.")
        print("       run: python tools/install_tex.py")
    else:
        print(f"[ok] LaTeX engine: {engine}\n")

    wanted = list(VARIANTS) if args.variant == "all" else [args.variant]
    for variant in wanted:
        print(f"--- {variant} " + "-" * (46 - len(variant)))
        out = build(variant, log=lambda m: print("   " + m))
        pdf = out["pdf"].name if out["pdf"] else "(none)"
        print(f"   tex      {out['tex'].name}")
        print(f"   pdf      {pdf}  ({out['pages']} page(s))" if out["pdf"] else f"   pdf      {pdf}")
        print(f"   behuman  {out['behuman']}")
        print()

    print(f"[done] written to {CV_DATA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
