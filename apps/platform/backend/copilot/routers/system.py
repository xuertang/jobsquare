from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Request

from .. import config, llm, referrals, repo
from ..deps import found, get_conn

router = APIRouter(tags=["system"])
RUNNABLE = ("daily", "fetch", "score", "digest", "refilter")


@router.get("/status")
def status(request: Request, conn=Depends(get_conn)):
    sched = request.app.state.scheduler
    companies = repo.list_companies(conn)
    queue = repo.list_applications(conn, submitted=False)
    return {
        "llm": {"available": llm.available(), "model": config.MODEL},
        "scheduler": {"enabled": sched is not None,
                      "next_run": sched.next_run() if sched else None},
        # The worker polls every few seconds; quiet for 20s means it is not running.
        "worker": {"running": time.time() - request.app.state.worker_seen < 20},
        "counts": {
            "matches": repo.match_counts(conn),
            "queue": len(queue),
            "paused": sum(1 for a in queue if a["state"] == "paused"),
            "submitted": len(repo.list_applications(conn, submitted=True)),
            "followups": len(referrals.followups(conn, draft_missing=False)),
            "contacts": repo.contact_total(conn),
            "companies": len(companies),
            "companies_attention": sum(
                1 for c in companies
                if c["active"] and c["last_status"] not in (None, "ok")),
        },
        "last_daily": repo.last_task(conn, "daily"),
        "running": [t for t in repo.list_tasks(conn, 40)
                    if t["state"] in ("queued", "running") and t["kind"] != "fill"],
    }


@router.post("/run/{kind}")
def run(kind: str, conn=Depends(get_conn)):
    if kind not in RUNNABLE:
        raise HTTPException(400, f"unknown task kind; expected one of {RUNNABLE}")
    task_id, created = repo.enqueue(conn, kind, dedupe_key=kind)
    return {"task": repo.get_task(conn, task_id), "created": created}


@router.get("/tasks")
def tasks(limit: int = 30, conn=Depends(get_conn)):
    return repo.list_tasks(conn, min(limit, 200))


@router.get("/tasks/{task_id}")
def task(task_id: int, conn=Depends(get_conn)):
    return found(repo.get_task(conn, task_id), "task")
