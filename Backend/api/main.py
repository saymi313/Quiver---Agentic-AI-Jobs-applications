"""
FastAPI backend for Quiver.

Run from the Backend/ folder:

    python -m uvicorn api.main:app --reload --port 8000

Two surfaces:
  /api/ats/*   resume + job-description tailoring
  /api/auto/*  drive the existing prospecting / sending pipeline
"""

from __future__ import annotations

import asyncio
import json
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import resume_style, state
from .ats import analyze
from .config import (
    ALLOWED_RESUME_EXT,
    DASHBOARD_OUT,
    DIST_DIR,
    MAX_UPLOAD_BYTES,
    RUNNABLE,
    UPLOADS_DIR,
)
from .jobs import manager
from .resume_build import build_resume, render_docx, render_pdf, render_txt
from .resume_parse import parse_resume

app = FastAPI(title="Quiver", version="1.0.0")


@app.on_event("startup")
def _start_scheduler() -> None:
    # The daemon thread that fires scheduled discovery and retry drains. It
    # does nothing until schedule.enabled is turned on in Settings, and it can
    # only ever dispatch the tasks in scheduler.SCHEDULABLE — never applying.
    from . import scheduler
    scheduler.start()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:4173", "http://127.0.0.1:4173",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# sessionId -> analysis context. In-process only; this is a local single-user tool.
SESSIONS: dict[str, dict[str, Any]] = {}
SESSION_TTL = 60 * 60 * 6


def _gc_sessions() -> None:
    now = time.time()
    for sid in [s for s, v in SESSIONS.items() if now - v["created"] > SESSION_TTL]:
        ctx = SESSIONS.pop(sid, None)
        if ctx:
            shutil.rmtree(ctx["dir"], ignore_errors=True)
    while len(SESSIONS) > 24:
        oldest = min(SESSIONS, key=lambda s: SESSIONS[s]["created"])
        ctx = SESSIONS.pop(oldest)
        shutil.rmtree(ctx["dir"], ignore_errors=True)


# --------------------------------------------------------------------------
# Health / meta
# --------------------------------------------------------------------------

@app.get("/api/health")
def health() -> dict[str, Any]:
    """
    `ai` reports the provider that actually does the writing.

    The agent's provider (Gemini by default, configured in the Agent tab) is the
    one used for LaTeX tailoring, cover letters and cold emails. The optional
    Anthropic path is reported separately so the UI never claims "AI off" while
    Gemini is happily rewriting bullets.
    """
    try:
        from agent import llm as agent_llm

        agent_ok, agent_why = agent_llm.available()
        agent_model = agent_llm.config().get("model", "")
        provider = agent_llm.config().get("provider", "")
        budget = agent_llm.budget_status()
    except Exception as exc:
        agent_ok, agent_why, agent_model, provider = False, f"agent unavailable: {exc}", "", ""
        budget = {}

    return {
        "ok": True,
        "time": datetime.now(timezone.utc).isoformat(),
        "ai": {
            "available": agent_ok,
            "reason": agent_why,
            "model": agent_model,
            "provider": provider,
            "budget": budget,
        },
        "latex": {"engine": _latex_engine()},
    }


def _latex_engine() -> str:
    from .latex_resume import engine_name, find_engine

    return engine_name(find_engine())


# --------------------------------------------------------------------------
# ATS: analyze
# --------------------------------------------------------------------------

@app.post("/api/ats/analyze")
async def ats_analyze(
    resume: UploadFile = File(...),
    jd_text: str = Form(""),
    jd_file: UploadFile | None = File(None),
) -> JSONResponse:
    _gc_sessions()

    ext = Path(resume.filename or "").suffix.lower()
    if ext not in ALLOWED_RESUME_EXT:
        raise HTTPException(400, f"Unsupported resume type '{ext or 'unknown'}'. "
                                 f"Upload {', '.join(sorted(ALLOWED_RESUME_EXT))}.")

    payload = await resume.read()
    if not payload:
        raise HTTPException(400, "The uploaded resume is empty.")
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"Resume exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")

    jd = (jd_text or "").strip()
    if jd_file is not None and getattr(jd_file, "filename", ""):
        jd_ext = Path(jd_file.filename).suffix.lower()
        jd_bytes = await jd_file.read()
        if len(jd_bytes) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "Job description file is too large.")
        if jd_ext in (".txt", ".md", ""):
            jd = jd_bytes.decode("utf-8", errors="replace").strip() or jd
        else:
            tmp = UPLOADS_DIR / f"jd_{uuid.uuid4().hex[:8]}{jd_ext}"
            tmp.write_bytes(jd_bytes)
            try:
                jd = parse_resume(tmp).raw_text.strip() or jd
            except Exception as exc:
                raise HTTPException(400, f"Could not read the job description file: {exc}")
            finally:
                tmp.unlink(missing_ok=True)

    if len(jd) < 60:
        raise HTTPException(400, "Paste the full job description — at least a few sentences of "
                                 "requirements are needed to match against.")

    session_id = uuid.uuid4().hex[:16]
    session_dir = DASHBOARD_OUT / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    resume_path = session_dir / f"original{ext}"
    resume_path.write_bytes(payload)

    try:
        parsed = parse_resume(resume_path)
    except Exception as exc:
        shutil.rmtree(session_dir, ignore_errors=True)
        raise HTTPException(400, f"Could not read that resume: {exc}")

    if len(parsed.raw_text.strip()) < 40:
        shutil.rmtree(session_dir, ignore_errors=True)
        raise HTTPException(
            400,
            "Almost no text could be extracted — the file is probably a scan or an image-only "
            "export. Re-export it as a text-based PDF or DOCX.",
        )

    result = analyze(parsed, jd)
    jd_analysis = result.pop("_jd")

    SESSIONS[session_id] = {
        "created": time.time(),
        "dir": session_dir,
        "parsed": parsed,
        "jd_text": jd,
        "jd": jd_analysis,
        "analysis": result,
        "files": {},
        "filename": resume.filename,
    }

    return JSONResponse({
        "sessionId": session_id,
        "originalFilename": resume.filename,
        **result,
    })


# --------------------------------------------------------------------------
# ATS: build
# --------------------------------------------------------------------------

class BuildRequest(BaseModel):
    sessionId: str
    reorderBullets: bool = True
    useAi: bool = False
    formats: list[str] = Field(default_factory=lambda: ["pdf", "docx", "txt"])
    # LaTeX is the primary output: a real .tex plus a compiled PDF.
    useLatex: bool = True
    contentSource: str = "upload"      # upload | profile
    # The house standard is a two pager with every project on it. Turning this
    # on squeezes to one page instead.
    onePage: bool = False


@app.post("/api/ats/build")
def ats_build(req: BuildRequest) -> dict[str, Any]:
    ctx = SESSIONS.get(req.sessionId)
    if ctx is None:
        raise HTTPException(404, "That analysis session expired. Re-upload the resume.")

    parsed = ctx["parsed"]
    jd = ctx["jd"]
    analysis = ctx["analysis"]

    # The AI rewrite happens inside the LaTeX tailor (agent.llm / Gemini).
    ai_result: dict[str, Any] | None = None

    built = build_resume(
        parsed, jd, analysis["match"],
        reorder_bullets=req.reorderBullets,
        llm=ai_result if (ai_result and ai_result.get("ok")) else None,
    )

    session_dir: Path = ctx["dir"]
    # House naming: Usairam_Saeed_CompanyName_Role. The JD title often reads
    # "Frontend Engineer at SpaceX"; file_stem splits company out of it.
    stem = resume_style.file_stem(parsed.name or "Resume", "", jd.get("title") or "")
    text = render_txt(built)

    files: dict[str, str] = {}
    errors: dict[str, str] = {}

    txt_path = session_dir / f"{stem}.txt"
    txt_path.write_text(text, encoding="utf-8")
    files["txt"] = txt_path.name

    def render_plain_fallback() -> None:
        """The ReportLab/python-docx renderers over the parsed upload.

        Only runs when LaTeX is off or its build failed. With LaTeX on, these
        files would be overwritten by the tailored versions moments later —
        the old flow really did render every document twice per build.
        """
        if "docx" in req.formats:
            try:
                render_docx(built, session_dir / f"{stem}.docx")
                files["docx"] = f"{stem}.docx"
            except Exception as exc:
                errors["docx"] = str(exc)
        if "pdf" in req.formats:
            try:
                render_pdf(built, session_dir / f"{stem}.pdf")
                files["pdf"] = f"{stem}.pdf"
            except Exception as exc:
                errors["pdf"] = str(exc)

    if not req.useLatex:
        render_plain_fallback()

    # ---- LaTeX build -----------------------------------------------------
    latex_info: dict[str, Any] | None = None
    latex_out: dict[str, Any] = {}
    if req.useLatex:
        from . import latex_resume

        try:
            if req.contentSource == "profile" and latex_resume.PROFILE_PATH.is_file():
                content = latex_resume.from_profile()
            else:
                content = latex_resume.from_parsed(parsed)

            tailor_notes: list[str] = []
            tailored = latex_resume.tailor(
                content, ctx["jd_text"], jd, use_llm=req.useAi,
                log=lambda m: tailor_notes.append(m))
            latex_out = latex_resume.build(
                content, session_dir, stem,
                max_pages=1 if req.onePage else latex_resume.MAX_PAGES,
                log=lambda m: tailor_notes.append(m))

            files["tex"] = latex_out["tex"].name

            # The tailored content is the document. Re-render the DOCX and TXT
            # from it and let the compiled PDF *be* the PDF download, so all
            # four files are one resume in four containers. Before this, "PDF"
            # served a plain rebuild of the upload while ".TEX" served the
            # tailored profile — two different documents from one button row.
            from . import resume_docx

            try:
                docx_path = session_dir / f"{stem}.docx"
                resume_docx.render_docx(content, docx_path)
                files["docx"] = docx_path.name
                errors.pop("docx", None)
            except Exception as exc:
                errors["docx"] = f"tailored DOCX failed: {exc}"

            try:
                text = resume_docx.render_txt(content)
                txt_path.write_text(text, encoding="utf-8")
            except Exception as exc:
                errors["txt"] = f"tailored TXT failed: {exc}"

            if latex_out["pdf"]:
                # One PDF button, not two. `latex_info.engine` tells the UI
                # which engine produced it.
                files["pdf"] = latex_out["pdf"].name
                errors.pop("pdf", None)

            # The same hard audit the agent applies before recording a resume.
            # Here the files still download — this is an interactive tool and
            # the user may be iterating — but the failures are front and centre.
            audit_fails: list[str] = []
            if latex_out.get("pdf"):
                from . import resume_audit

                try:
                    audit_fails = resume_audit.audit_pdf(latex_out["pdf"])
                except Exception as exc:
                    audit_fails = [f"audit could not run: {type(exc).__name__}"]
                if audit_fails:
                    tailor_notes.append(
                        "[audit] FAILED house style: " + "; ".join(audit_fails[:4]))
                else:
                    tailor_notes.append("[audit] passes every house style rule")

            latex_info = {
                "engine": latex_out["engine"],
                "pages": latex_out["pages"],
                "message": latex_out["message"],
                "source": content.source,
                "texSource": latex_out["texSource"],
                "llm": tailored.get("llm"),
                "rewritten": tailored.get("rewritten", 0),
                "lint": tailored.get("lint", []),
                "audit": audit_fails,
                "log": tailor_notes,
            }
        except Exception as exc:
            latex_info = {"error": f"{type(exc).__name__}: {exc}"}
            errors["tex"] = str(exc)[:300]
            # LaTeX path died before producing files — fall back to the plain
            # renderers so the user still gets a PDF and DOCX.
            render_plain_fallback()

        if not latex_out.get("pdf") and "pdf" not in files:
            # Compiled but produced no PDF (no engine installed): plain PDF
            # fallback, tailored TXT/DOCX from above still stand.
            render_plain_fallback()

    ctx["files"] = files

    # Honest "after" score: re-parse the generated plain text through the same pipeline.
    latex_pdf = (latex_out["pdf"] if (req.useLatex and latex_info
                                      and not latex_info.get("error")
                                      and latex_out.get("pdf")) else None)
    rescore_path = session_dir / "_rescore.txt"
    rescore_path.write_text(text, encoding="utf-8")
    try:
        # Score the compiled LaTeX PDF when there is one — that is the file the
        # employer actually receives, so it is the honest thing to measure.
        rebuilt_parsed = parse_resume(latex_pdf if latex_pdf and latex_pdf.is_file()
                                      else rescore_path)
        after = analyze(rebuilt_parsed, ctx["jd_text"])
        after.pop("_jd", None)
        after_score = after["score"]
        after_match = after["match"]
    except Exception:
        after_score = None
        after_match = None
    finally:
        rescore_path.unlink(missing_ok=True)

    return {
        "sessionId": req.sessionId,
        "resume": built.to_dict(),
        "preview": text,
        "downloads": {
            fmt: f"/api/ats/download/{req.sessionId}/{fmt}" for fmt in files
        },
        "fileNames": files,
        "renderErrors": errors,
        "before": {
            "score": analysis["score"]["total"],
            "coverage": analysis["match"]["coverage"],
            "matched": len(analysis["match"]["matched"]),
        },
        "after": {
            "score": after_score["total"] if after_score else None,
            "band": after_score["band"] if after_score else None,
            "components": after_score["components"] if after_score else [],
            "coverage": after_match["coverage"] if after_match else None,
            "matched": len(after_match["matched"]) if after_match else None,
            "stillMissing": [m["term"] for m in (after_match["missing"] if after_match else [])][:12],
        },
        "ai": ai_result,
        "latex": latex_info,
        # House style verdict on the document that was actually produced, so a
        # violation shows up in the browser rather than only in check_resume.py.
        # Linted after enforcement, so this reports what the delivered document
        # actually contains rather than what the source happened to say.
        "style": resume_style.report({
            "summary": resume_style.enforce(built.summary),
            "skills": [resume_style.enforce(s) for s in built.skills],
            "bullet": [resume_style.enforce(b)
                       for e in built.experience + built.projects for b in e["bullets"]],
        }),
    }


@app.get("/api/ats/download/{session_id}/{fmt}")
def ats_download(session_id: str, fmt: str):
    ctx = SESSIONS.get(session_id)
    if ctx is None:
        raise HTTPException(404, "Session expired.")
    name = ctx["files"].get(fmt)
    if not name:
        raise HTTPException(404, f"No {fmt} file was generated for this session.")
    path: Path = ctx["dir"] / name
    if not path.is_file():
        raise HTTPException(404, "File is missing on disk.")
    media = {
        "pdf": "application/pdf",
        "latexpdf": "application/pdf",
        "tex": "application/x-tex",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "txt": "text/plain; charset=utf-8",
    }.get(fmt, "application/octet-stream")
    return FileResponse(str(path), media_type=media, filename=name)


# --------------------------------------------------------------------------
# Auto mode
# --------------------------------------------------------------------------

@app.get("/api/auto/overview")
def auto_overview() -> dict[str, Any]:
    running = manager.active()
    return {
        "stats": state.pipeline_stats(),
        "environment": state.environment(),
        "verticals": state.verticals(),
        # Agent tasks are driven from the Agent tab, not this one.
        "tasks": [
            {"key": k, "label": v["label"], "script": v["script"],
             "description": v["description"], "flags": v["flags"]}
            for k, v in RUNNABLE.items() if "script" in v
        ],
        "activeJob": running.summary() if running else None,
        "jobs": manager.recent(),
    }


@app.get("/api/auto/activity")
def auto_activity() -> dict[str, Any]:
    return {
        "sends": state.send_log(40),
    }


class RunRequest(BaseModel):
    key: str
    dry_run: bool = False
    to_self: bool = False
    limit: int | None = None
    delay: int | None = None
    vertical: str | None = None
    # agent-only switches
    sources: list[str] | None = None
    no_people: bool = False
    no_ats: bool = False
    no_attach: bool = False
    headed: bool = False
    # The jobs the user selected. Apply never runs without this.
    job_ids: list[int] | None = None


@app.post("/api/auto/run")
def auto_run(req: RunRequest) -> dict[str, Any]:
    try:
        job = manager.start(req.key, req.model_dump())
    except KeyError as exc:
        raise HTTPException(400, str(exc))
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc))
    except RuntimeError as exc:
        raise HTTPException(409, str(exc))
    except Exception as exc:
        raise HTTPException(500, f"Could not start the task: {exc}")
    return job.summary()


@app.post("/api/auto/stop/{job_id}")
def auto_stop(job_id: str) -> dict[str, Any]:
    ok = manager.stop(job_id)
    if not ok:
        raise HTTPException(409, "That job is not running.")
    return {"ok": True}


@app.get("/api/auto/jobs/{job_id}")
def auto_job(job_id: str, cursor: int = 0) -> dict[str, Any]:
    job = manager.get(job_id)
    if job is None:
        raise HTTPException(404, "Unknown job.")
    lines, next_cursor = manager.slice_lines(job, cursor)
    return {**job.summary(), "lines": lines, "cursor": next_cursor}


@app.get("/api/auto/jobs/{job_id}/stream")
async def auto_stream(job_id: str, cursor: int = 0):
    job = manager.get(job_id)
    if job is None:
        raise HTTPException(404, "Unknown job.")

    async def events():
        pos = cursor
        idle = 0
        while True:
            lines, pos = manager.slice_lines(job, pos)
            if lines:
                idle = 0
                yield f"data: {json.dumps({'type': 'lines', 'lines': lines, 'cursor': pos})}\n\n"
            else:
                idle += 1
                if idle % 20 == 0:
                    yield ": keepalive\n\n"
            if job.status not in ("running", "stopping"):
                # drain anything written between the last read and exit
                lines, pos = manager.slice_lines(job, pos)
                if lines:
                    yield f"data: {json.dumps({'type': 'lines', 'lines': lines, 'cursor': pos})}\n\n"
                yield f"data: {json.dumps({'type': 'end', 'job': job.summary()})}\n\n"
                return
            await asyncio.sleep(0.35)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# --------------------------------------------------------------------------
# Agent
# --------------------------------------------------------------------------

@app.get("/api/agent/overview")
def agent_overview() -> dict[str, Any]:
    from agent import llm as agent_llm, matcher, store as agent_store
    from . import scheduler

    agent_store.init()
    ok, reason = agent_llm.available()
    resume = matcher.resume_path()
    running = manager.active()
    return {
        "stats": agent_store.stats(),
        "schedule": scheduler.status(),
        "queue": agent_store.task_stats(),
        "settings": agent_store.all_settings(),
        "store": agent_store.backend_status(),
        "llm": {"available": ok, "reason": reason, **agent_llm.config(), "api_key": ""},
        "resume": {"path": str(resume) if resume else None, "name": resume.name if resume else None},
        "tasks": [
            {"key": k, "label": v["label"], "description": v["description"], "flags": v["flags"]}
            for k, v in RUNNABLE.items() if "module" in v
        ],
        "runs": agent_store.list_runs(10),
        "activeJob": running.summary() if running else None,
    }


@app.get("/api/agent/data")
def agent_data(kind: str = "jobs", limit: int = 100, status: str | None = None) -> dict[str, Any]:
    from agent import store as agent_store

    agent_store.init()
    limit = max(1, min(limit, 500))
    table = {
        "jobs": lambda: agent_store.list_jobs(limit, status),
        "companies": lambda: agent_store.list_companies(limit),
        "people": lambda: agent_store.list_people(limit, status),
        "applications": lambda: agent_store.list_applications(limit),
        "outreach": lambda: agent_store.list_outreach(limit),
    }.get(kind)
    if table is None:
        raise HTTPException(400, f"Unknown kind '{kind}'.")
    return {"kind": kind, "rows": table()}


@app.get("/api/agent/jobs")
def agent_jobs(limit: int = 200, status: str | None = None,
               category: str | None = None, source: str | None = None,
               q: str | None = None) -> dict[str, Any]:
    """
    The tracked jobs table.

    Returns the rows plus the facet values actually present in the data, so the
    filter dropdowns only ever offer categories and portals that exist.
    """
    from agent import categories, store as agent_store

    agent_store.init()
    rows = agent_store.list_jobs(max(1, min(limit, 1000)), status,
                                 category=category, source=source, q=q)

    # Failed rows link to the screenshot the applier saved — the evidence of
    # what the form looked like when it stopped. The applications log holds
    # the filename; newest attempt wins.
    shots: dict[int, str] = {}
    for app_row in agent_store.list_applications(300):
        if app_row.get("screenshot") and app_row.get("job_id") is not None:
            shots.setdefault(int(app_row["job_id"]), app_row["screenshot"])
    for r in rows:
        if r.get("status") == "failed":
            r["screenshot"] = shots.get(int(r["id"]))

    everything = agent_store.list_jobs(1000)

    def tally(key: str) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in everything:
            value = r.get(key)
            if value:
                out[str(value)] = out.get(str(value), 0) + 1
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))

    return {
        "rows": rows,
        "total": len(everything),
        "categories": [{"slug": s, "label": categories.CATEGORIES[s],
                        "count": tally("role_category").get(s, 0)}
                       for s in categories.ALL],
        "sources": tally("source"),
        "statuses": tally("status"),
    }


@app.get("/api/agent/resume/{job_id}")
def agent_resume(job_id: int, fmt: str = "pdf", download: bool = False):
    """Serve the resume tailored for one job."""
    from agent import store as agent_store, tailor

    agent_store.init()
    job = agent_store.job(job_id)
    if not job:
        raise HTTPException(404, f"No job with id {job_id}.")

    pdf = tailor.existing(job)
    if not pdf:
        raise HTTPException(404, "No tailored resume has been generated for this job yet.")
    path = pdf.with_suffix(".tex") if fmt == "tex" else pdf
    if not path.is_file():
        raise HTTPException(404, f"The .{fmt} for this job is not on disk.")

    media = "application/pdf" if fmt == "pdf" else "text/plain; charset=utf-8"
    return FileResponse(
        path, media_type=media,
        filename=path.name if download else None,
        headers={} if download else {"Content-Disposition": f'inline; filename="{path.name}"'})


class SettingsPatch(BaseModel):
    profile: dict[str, Any] | None = None
    targeting: dict[str, Any] | None = None
    limits: dict[str, Any] | None = None
    llm: dict[str, Any] | None = None
    schedule: dict[str, Any] | None = None
    tailoring: dict[str, Any] | None = None


@app.post("/api/agent/settings")
def agent_settings(patch: SettingsPatch) -> dict[str, Any]:
    from agent import store as agent_store

    agent_store.init()
    for key, value in patch.model_dump(exclude_none=True).items():
        current = agent_store.get_setting(key, {}) or {}
        merged = {**current, **value}
        # An empty api_key in the payload means "leave it alone", not "clear it".
        if key == "llm" and not (value.get("api_key") or "").strip():
            merged["api_key"] = current.get("api_key", "")
        agent_store.set_setting(key, merged)
    return {"ok": True, "settings": agent_store.all_settings()}


@app.post("/api/agent/llm-test")
def agent_llm_test() -> dict[str, Any]:
    from agent import llm as agent_llm

    ok, reason = agent_llm.available()
    if not ok:
        return {"ok": False, "error": reason}
    try:
        reply = agent_llm.complete("Reply with exactly: READY", purpose="test",
                                   system="You follow instructions literally.")
        return {"ok": True, "reply": (reply or "").strip()[:120], "model": agent_llm.config().get("model")}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:400]}


@app.get("/api/agent/screenshot/{name}")
def agent_screenshot(name: str):
    safe = Path(name).name
    path = DASHBOARD_OUT / "applications" / safe
    if not path.is_file():
        raise HTTPException(404, "Screenshot not found.")
    return FileResponse(str(path), media_type="image/png")


# --------------------------------------------------------------------------
# Prep: tailoring modes, the change review, and adding a job by URL
# --------------------------------------------------------------------------

class AddJobRequest(BaseModel):
    url: str


@app.post("/api/agent/job-from-url")
def agent_job_from_url(req: AddJobRequest) -> dict[str, Any]:
    """
    Track one job from its URL, without waiting for discovery to find it.

    Detects the portal, fetches the description, classifies the role and scores
    it against the profile — the same pipeline a discovered job goes through,
    entered at the point where the URL is already known.
    """
    from agent import categories, jobdesc, matcher, sources, store as agent_store

    agent_store.init()
    url = (req.url or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        raise HTTPException(400, "That does not look like a job URL.")

    existing = agent_store.job_by_url(url)
    if existing:
        return {"ok": True, "id": existing["id"], "created": False,
                "title": existing.get("title"), "status": existing.get("status"),
                "message": "Already tracked."}

    portal, _token = sources.portal_from_url(url)
    row: dict[str, Any] = {"url": url, "apply_url": url,
                           "source": portal or "manual", "title": "", "description": ""}

    text, origin = jobdesc.fetch_description(row, log=lambda _: None)
    if origin == "closed":
        raise HTTPException(
            410, "That posting is closed — the board says it is no longer open. "
                 "Nothing was added.")
    if not text:
        raise HTTPException(
            422, "Could not read that page. It may need a login, or the posting may be "
                 "closed. Paste the description into the Resume screen instead.")
    # Reaching here with a board index means the posting was not found: the id
    # is stale, or the link points at the board itself. Storing it would put a
    # row in the table whose description is the company blurb and whose title
    # is whichever vacancy happened to be listed first.
    if jobdesc.LOOKS_LIKE_A_BOARD.search(text[:600]):
        raise HTTPException(
            422, "That link opens a job board rather than a single posting — the role "
                 "may have been taken down. Open the board and paste the link to the "
                 "specific job.")

    row["description"] = text
    row["description_source"] = origin
    # The page's own heading beats scanning the body text, which on a board
    # page picks up whichever vacancy happens to be listed first.
    title = jobdesc.fetch_page_title(url)
    if not title or jobdesc.LOOKS_LIKE_A_BOARD.search(title):
        title = jobdesc.guess_title(text, url)
    row["title"] = title or "Untitled role"

    company_name = sources.company_from_url(url) or "Unknown"
    company_id = agent_store.upsert_company({"name": company_name, "source": "manual",
                                             "domain": sources.domain_of(url)})
    row["company_id"] = company_id
    row["role_category"] = categories.classify(row["title"], text)
    row["dedupe_hash"] = sources.dedupe_hash(company_name, row["title"], "", url=url)

    job_id = agent_store.upsert_job(row, company_name=company_name)
    if not job_id:
        raise HTTPException(500, "Could not store that job.")
    scored = matcher.score_pending(limit=5, log=lambda _: None)
    fresh = agent_store.job(int(job_id)) or {}
    return {"ok": True, "id": int(job_id), "created": True,
            "title": fresh.get("title"), "company": company_name,
            "category": fresh.get("role_category"),
            "fitScore": fresh.get("fit_score"), "fitReason": fresh.get("fit_reason"),
            "status": fresh.get("status"), "scored": scored.get("matched", 0)}


@app.get("/api/agent/resume/{job_id}/changes")
def agent_resume_changes(job_id: int) -> dict[str, Any]:
    """What the rewrite changed, for the review screen."""
    from agent import store as agent_store

    agent_store.init()
    row = agent_store.job(job_id)
    if not row:
        raise HTTPException(404, "No such job.")

    raw = row.get("resume_changes")
    changes: list[dict[str, Any]] = []
    if isinstance(raw, str) and raw.strip():
        try:
            changes = json.loads(raw)
        except json.JSONDecodeError:
            changes = []
    elif isinstance(raw, list):
        changes = raw

    return {
        "id": job_id,
        "title": row.get("title"),
        "company": row.get("company_name"),
        "mode": row.get("resume_mode"),
        "approved": row.get("resume_approved"),
        "hasResume": bool(row.get("resume_path")),
        "version": row.get("resume_version"),
        "changes": changes,
    }


class ApproveRequest(BaseModel):
    # Present only when the user edited a line before approving.
    changes: list[dict[str, Any]] | None = None


@app.post("/api/agent/resume/{job_id}/approve")
def agent_approve_resume(job_id: int, req: ApproveRequest) -> dict[str, Any]:
    """
    Sign off a tailored resume so it can be sent.

    When the user edited a line, the resume is rebuilt from the edited text
    rather than approved as-is — approving text that differs from the compiled
    PDF would ship the version nobody read.
    """
    from agent import store as agent_store, tailor

    agent_store.init()
    row = agent_store.job(job_id)
    if not row:
        raise HTTPException(404, "No such job.")

    edits = req.changes or []
    edited = [c for c in edits if (c.get("edited") or "").strip()
              and c.get("edited") != c.get("revised")]
    if edited:
        rebuilt = tailor.rebuild_with_edits(row, edits, log=lambda _: None)
        if not rebuilt["ok"]:
            raise HTTPException(422, rebuilt.get("reason") or "Could not rebuild the resume.")

    agent_store.approve_job_resume(job_id, edits or None)
    return {"ok": True, "id": job_id, "approved": True, "rebuilt": bool(edited)}


# --------------------------------------------------------------------------
# Track: the pipeline and the reply inbox
# --------------------------------------------------------------------------

@app.get("/api/agent/tracker")
def agent_tracker(limit: int = 300) -> dict[str, Any]:
    """Every application that reached an employer, with its pipeline stage."""
    from agent import inbox, store as agent_store
    from agent.schema import MESSAGE_CLASSES, TRACKER_STATUSES

    agent_store.init()
    ok, reason = inbox.available()
    return {
        "rows": agent_store.tracked_applications(max(1, min(limit, 1000))),
        "counts": agent_store.tracker_counts(),
        "messageCounts": agent_store.message_counts(),
        "unread": agent_store.unread_count(),
        "stages": list(TRACKER_STATUSES),
        "classes": list(MESSAGE_CLASSES),
        "mailbox": {"available": ok, "reason": reason},
    }


@app.get("/api/agent/inbox")
def agent_inbox(limit: int = 100, klass: str | None = None,
                unread: bool = False) -> dict[str, Any]:
    from agent import store as agent_store

    agent_store.init()
    return {
        "rows": agent_store.list_messages(max(1, min(limit, 500)),
                                          klass=klass, unread_only=unread),
        "unread": agent_store.unread_count(),
        "counts": agent_store.message_counts(),
    }


class TrackerPatch(BaseModel):
    status: str


@app.patch("/api/agent/application/{app_id}/status")
def agent_set_tracker(app_id: int, patch: TrackerPatch) -> dict[str, Any]:
    """Move an application by hand. The agent never overrides this."""
    from agent import store as agent_store
    from agent.schema import TRACKER_STATUSES

    agent_store.init()
    if not agent_store.set_tracker_status(app_id, patch.status):
        raise HTTPException(400, f"Status must be one of {', '.join(TRACKER_STATUSES)}.")
    return {"ok": True, "id": app_id, "status": patch.status}


@app.post("/api/agent/message/{message_id}/read")
def agent_mark_read(message_id: int, read: bool = True) -> dict[str, Any]:
    from agent import store as agent_store

    agent_store.init()
    agent_store.mark_message_read(message_id, read)
    return {"ok": True, "unread": agent_store.unread_count()}


@app.get("/api/agent/receipt/{app_id}")
def agent_receipt(app_id: int) -> dict[str, Any]:
    """
    What was actually submitted, after the fact.

    The applier has always captured this; until now there was nowhere to read
    it. An application you cannot inspect is one you have to take on trust.
    """
    from agent import store as agent_store
    from agent.schema import APPLICATION_STATUS_HELP

    agent_store.init()
    row = agent_store.application(app_id)
    if not row:
        raise HTTPException(404, "No such application.")

    def _parsed(value: Any) -> Any:
        if isinstance(value, str) and value.strip().startswith(("{", "[")):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return value

    filled = _parsed(row.get("fields_filled")) or {}
    unanswered = _parsed(row.get("unanswered")) or []
    return {
        "id": row.get("id"),
        "status": row.get("status"),
        "statusHelp": APPLICATION_STATUS_HELP.get(row.get("status") or "", ""),
        "trackerStatus": row.get("tracker_status"),
        "title": row.get("title"),
        "company": row.get("company_name"),
        "url": row.get("url"),
        "submittedAt": row.get("submitted_at"),
        "dryRun": bool(row.get("dry_run")),
        "resume": Path(row["resume_path"]).name if row.get("resume_path") else None,
        "coverLetter": row.get("cover_letter") or "",
        "error": row.get("error"),
        "screenshot": row.get("screenshot"),
        "fields": filled if isinstance(filled, dict) else {},
        "unanswered": unanswered if isinstance(unanswered, list) else [],
        "counts": {
            "filled": len(filled) if isinstance(filled, dict) else 0,
            "skipped": len(unanswered) if isinstance(unanswered, list) else 0,
        },
    }


# --------------------------------------------------------------------------
# Static build (production: `npm run build` inside ../Frontend)
# --------------------------------------------------------------------------

if DIST_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(DIST_DIR), html=True), name="dashboard")
else:
    @app.get("/")
    def root() -> dict[str, str]:
        return {
            "message": "API is running. Start the UI with `npm run dev` in ../Frontend "
                       "(http://localhost:5173), or build it with `npm run build` to have it "
                       "served from here.",
        }
