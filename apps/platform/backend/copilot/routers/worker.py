"""Endpoints for the apply worker. The worker runs on the host with a visible
browser and talks to the API over HTTP only: it never opens the database, so
SQLite has a single writer process even when the API runs in Docker."""
from __future__ import annotations

import json
import re
import time

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .. import apply, config, db, repo, seed
from ..deps import found, get_conn

router = APIRouter(prefix="/worker", tags=["worker"])


@router.post("/claim")
def claim(request: Request, conn=Depends(get_conn)):
    """Hand the next approved fill to the worker, or nothing."""
    request.app.state.worker_seen = time.time()      # the dashboard shows "worker running"
    while True:
        task = repo.claim_task(conn, ["fill"])
        if task is None:
            return {"task": None}
        app = repo.get_application(conn, task["payload"].get("application_id") or 0)
        if app is None or app["state"] == "submitted":
            repo.finish_task(conn, task["id"], state="cancelled")
            conn.commit()
            continue
        # Last duplicate check, immediately before a form is opened.
        posting = repo.get_posting(conn, app["posting_id"])
        dup = repo.find_duplicate(conn, posting)
        if dup and dup["state"] == "submitted":
            repo.finish_task(conn, task["id"], error="duplicate requisition")
            repo.update_application(conn, app["id"], {
                "state": "needs_manual",
                "manual_reason": "Not opened: you already applied to this requisition."})
            conn.commit()
            continue
        repo.update_application(conn, app["id"], {"state": "filling"})
        resume = repo.get_resume(conn, app["resume_id"]) if app["resume_id"] else None
        return {"task": {
            "id": task["id"], "application_id": app["id"],
            "posting": {"id": posting["id"], "title": posting["title"],
                        "company": posting["company"], "apply_url": posting["apply_url"],
                        "ats_type": posting["ats_type"]},
            "resume": ({"id": resume["id"], "filename": resume["filename"]}
                       if resume and resume["path"] else None)}}


@router.post("/tasks/{task_id}/heartbeat")
def heartbeat(task_id: int, request: Request, conn=Depends(get_conn)):
    request.app.state.worker_seen = time.time()
    task = found(repo.get_task(conn, task_id), "task")
    repo.heartbeat_task(conn, task_id)
    return {"state": task["state"]}     # 'cancelled' tells the worker to stop


class PlanIn(BaseModel):
    fields: list[dict]


@router.post("/applications/{application_id}/plan")
def plan(application_id: int, body: PlanIn, conn=Depends(get_conn)):
    """Decide a value (or a reason to skip) for each field the worker found."""
    app = found(repo.get_application(conn, application_id), "application")
    posting = repo.get_posting(conn, app["posting_id"])
    resumes = repo.list_resumes(conn)
    resume = next((r for r in resumes if r["id"] == app["resume_id"] and r["path"]), None) \
        or apply.select_resume(posting, resumes)
    text_source = resume or repo.default_resume(conn) or {}
    decisions = apply.plan(body.fields, profile=seed.load_profile(conn),
                           bank=repo.list_bank(conn), settings=seed.app_settings(conn),
                           posting=posting, resume=resume,
                           resume_text=text_source.get("text", ""))
    if resume and resume["id"] != app["resume_id"]:
        repo.update_application(conn, application_id, {"resume_id": resume["id"],
                                                       "resume_variant": resume["label"]})
    return {"decisions": decisions}


class FilledIn(BaseModel):
    decisions: list[dict]
    results: dict[str, dict]
    report: dict = {}


@router.post("/applications/{application_id}/filled")
def filled(application_id: int, body: FilledIn, conn=Depends(get_conn)):
    found(repo.get_application(conn, application_id), "application")
    return apply.record_fill(conn, application_id, body.decisions, body.results, body.report)


@router.post("/applications/{application_id}/snapshot")
def snapshot(application_id: int, values: dict[str, str] = Body(...),
             conn=Depends(get_conn)):
    found(repo.get_application(conn, application_id), "application")
    return {"changed": apply.record_snapshot(conn, application_id, values)}


@router.post("/applications/{application_id}/submitted")
async def submitted(application_id: int, values: str = Form("{}"),
                    screenshot: UploadFile | None = File(None), conn=Depends(get_conn)):
    """The worker saw the confirmation page after the user clicked submit."""
    found(repo.get_application(conn, application_id), "application")
    apply.record_snapshot(conn, application_id, json.loads(values or "{}"))
    rel = None
    if screenshot is not None:
        config.ensure_dirs()
        stamp = re.sub(r"[^0-9]", "", db.now())[:14]
        rel = f"screenshots/app-{application_id}-{stamp}.png"
        (config.DATA_DIR / rel).write_bytes(await screenshot.read())
    out = apply.finalize(conn, application_id, screenshot_path=rel)
    return {"bank_saved": out["bank_saved"]}


class Released(BaseModel):
    reason: str = ""
    needs_manual: bool = False
    task_id: int | None = None


@router.post("/applications/{application_id}/released")
def released(application_id: int, body: Released, conn=Depends(get_conn)):
    """The worker let go without a submission: the browser was closed, the
    form was blocked, or the fill failed."""
    app = found(repo.get_application(conn, application_id), "application")
    if body.task_id:
        repo.finish_task(conn, body.task_id, error=body.reason or None)
    if app["state"] == "submitted":
        return {"state": "submitted"}
    if body.needs_manual:
        repo.update_application(conn, application_id, {
            "state": "needs_manual", "manual_reason": body.reason})
        if not repo.list_answers(conn, application_id):
            apply.seed_manual_answers(conn, application_id)
    else:
        repo.update_application(conn, application_id, {
            "state": "waiting", "manual_reason": body.reason})
    return {"state": repo.get_application(conn, application_id)["state"]}


@router.get("/resumes/{resume_id}/file")
def resume_file(resume_id: int, conn=Depends(get_conn)):
    resume = found(repo.get_resume(conn, resume_id), "resume")
    path = (config.DATA_DIR / resume["path"]) if resume["path"] else None
    if not path or not path.is_file() or config.RESUME_DIR not in path.resolve().parents:
        raise HTTPException(404, "resume file is missing")
    return FileResponse(path, filename=resume["filename"])
