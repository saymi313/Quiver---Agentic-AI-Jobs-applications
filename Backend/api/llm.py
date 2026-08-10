"""
Optional AI polish pass (Claude).

Everything in the dashboard works without this module. When an Anthropic
credential is available, this rewrites bullets and the summary so the resume
reads for the specific job — under a hard constraint that it may only reuse
facts already present in the uploaded resume.

Enable by installing the SDK and providing a credential:
    pip install anthropic
    setx ANTHROPIC_API_KEY sk-ant-...     (or run `ant auth login`)
"""

from __future__ import annotations

import json
import os
from typing import Any

from . import behuman

MODEL = "claude-opus-5"

OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "2-3 sentence professional summary tailored to the job description.",
        },
        "bullets": {
            "type": "array",
            "description": "Rewritten bullets. Only include bullets you actually changed.",
            "items": {
                "type": "object",
                "properties": {
                    "original": {"type": "string", "description": "The bullet text exactly as given."},
                    "revised": {"type": "string", "description": "The rewritten bullet."},
                    "reason": {"type": "string", "description": "One short clause on what changed and why."},
                },
                "required": ["original", "revised", "reason"],
                "additionalProperties": False,
            },
        },
        "skillsToAdd": {
            "type": "array",
            "description": "Job-description skills the resume already evidences but never names explicitly.",
            "items": {"type": "string"},
        },
        "gaps": {
            "type": "array",
            "description": "Required skills the resume gives no evidence for. State them plainly; do not invent them.",
            "items": {"type": "string"},
        },
        "warnings": {
            "type": "array",
            "description": "Anything the user must verify before sending.",
            "items": {"type": "string"},
        },
    },
    "required": ["summary", "bullets", "skillsToAdd", "gaps", "warnings"],
    "additionalProperties": False,
}

SYSTEM = """You tailor resumes for applicant tracking systems and the recruiters reading behind them.

Absolute rule: you may only restate facts that appear in the resume you are given. Never invent an
employer, a technology, a date, a credential, or a metric. If a bullet has no number, do not add one —
rewrite for clarity and keyword alignment instead. If the job requires something the resume gives no
evidence for, put it in `gaps`; never write it into a bullet.

For each bullet you rewrite:
- open with a strong past-tense action verb
- keep it to one line, roughly 15-28 words
- surface the job description's own vocabulary where the underlying work genuinely matches
- preserve every real metric already present, unchanged
- drop filler ("responsible for", "worked on", "various tasks")

Return only bullets you meaningfully improved. `original` must be a byte-exact copy of the input bullet
so it can be matched back.

The summary is 2-3 sentences, third person with no pronouns, naming the candidate's actual stack and the
most relevant job-description terms they can back up.
""" + "\n\n" + behuman.RULES


def available() -> tuple[bool, str]:
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False, "The `anthropic` package is not installed (pip install anthropic)."
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return True, "Ready."
    if (os.environ.get("ANTHROPIC_PROFILE")
            or os.path.isdir(os.path.expanduser("~/.config/anthropic"))
            or os.path.isdir(os.path.join(os.environ.get("APPDATA", ""), "Anthropic"))):
        return True, "Using the stored Anthropic CLI profile."
    return False, "No Anthropic credential found (set ANTHROPIC_API_KEY or run `ant auth login`)."


def _build_prompt(resume_text: str, jd_text: str, analysis: dict[str, Any]) -> str:
    missing = [m["term"] for m in analysis["match"]["missing"][:16]]
    matched = [m["term"] for m in analysis["match"]["matched"][:20]]
    bullets: list[str] = []
    for entry in analysis["resume"]["experience"] + analysis["resume"]["projects"]:
        bullets.extend(entry["bullets"])

    return f"""<job_description>
{jd_text.strip()[:14000]}
</job_description>

<resume_full_text>
{resume_text.strip()[:16000]}
</resume_full_text>

<bullets_to_consider>
{json.dumps(bullets[:40], indent=2)}
</bullets_to_consider>

<deterministic_analysis>
Job title detected: {analysis['jd']['title'] or 'unknown'}
ATS score: {analysis['score']['total']}/100 ({analysis['score']['band']})
Job keywords already present: {', '.join(matched) or 'none'}
Job keywords absent: {', '.join(missing) or 'none'}
</deterministic_analysis>

Rewrite the resume for this job. Work only from the bullets listed above."""


def enhance(resume_text: str, jd_text: str, analysis: dict[str, Any]) -> dict[str, Any]:
    """Returns {"ok": bool, "error": str|None, ...schema fields}."""
    ok, reason = available()
    if not ok:
        return {"ok": False, "error": reason}

    import anthropic

    client = anthropic.Anthropic()
    prompt = _build_prompt(resume_text, jd_text, analysis)
    kwargs: dict[str, Any] = {
        "model": MODEL,
        "max_tokens": 24000,
        "system": SYSTEM,
        "thinking": {"type": "adaptive"},
        "output_config": {
            "effort": "high",
            "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA},
        },
        "messages": [{"role": "user", "content": prompt}],
    }

    try:
        try:
            # Server-side fallback keeps the request alive if a safety classifier declines.
            with client.beta.messages.stream(
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                **kwargs,
            ) as stream:
                message = stream.get_final_message()
        except (TypeError, anthropic.BadRequestError):
            with client.messages.stream(**kwargs) as stream:
                message = stream.get_final_message()
    except anthropic.AuthenticationError:
        return {"ok": False, "error": "Anthropic credential was rejected. Check ANTHROPIC_API_KEY."}
    except anthropic.RateLimitError:
        return {"ok": False, "error": "Rate limited by the Anthropic API. Try again shortly."}
    except anthropic.APIStatusError as exc:
        return {"ok": False, "error": f"Anthropic API error {exc.status_code}: {exc.message}"}
    except anthropic.APIConnectionError:
        return {"ok": False, "error": "Could not reach the Anthropic API. Check your connection."}
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "error": f"AI pass failed: {exc}"}

    if message.stop_reason == "refusal":
        return {"ok": False, "error": "The model declined this request."}

    text = next((b.text for b in message.content if b.type == "text"), "")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {"ok": False, "error": "The model returned malformed JSON."}

    usage = getattr(message, "usage", None)
    return {
        "ok": True,
        "error": None,
        "model": message.model,
        "summary": data.get("summary", ""),
        "bullets": data.get("bullets", []),
        "skillsToAdd": data.get("skillsToAdd", []),
        "gaps": data.get("gaps", []),
        "warnings": data.get("warnings", []),
        "usage": {
            "inputTokens": getattr(usage, "input_tokens", None),
            "outputTokens": getattr(usage, "output_tokens", None),
        } if usage else None,
    }
