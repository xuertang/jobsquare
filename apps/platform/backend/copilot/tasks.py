"""Task runner and scheduler.

APScheduler runs in-process and does two things only: enqueue the daily job at
the configured time, and tick a runner that drains the task table. Every run
is a row in `tasks`, so a restart can see what was interrupted and resume it.
'fill' tasks are not run here: the apply worker on the host claims those."""
from __future__ import annotations

import logging
import threading
import traceback

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from . import db, digest, pipeline, repo, seed

log = logging.getLogger("copilot.tasks")

IN_PROCESS = ("daily", "fetch", "score", "digest", "refilter")
FILL_STALE_SECONDS = 180


def _daily(db_path, payload: dict) -> dict:
    out = {"fetch": pipeline.run_fetch(db_path)}
    out["score"] = pipeline.run_score(db_path)
    out["digest"] = digest.run_digest(db_path)
    return out


def _refilter(db_path, payload: dict) -> dict:
    with db.session(db_path) as conn:
        out = pipeline.refilter(conn)
    out["descriptions"] = pipeline.fill_descriptions(db_path)
    return out


HANDLERS = {
    "daily": _daily,
    "fetch": lambda p, payload: pipeline.run_fetch(p, payload.get("company_ids")),
    "score": lambda p, payload: pipeline.run_score(p, payload.get("limit"),
                                                   payload.get("match_ids")),
    "digest": lambda p, payload: digest.run_digest(p),
    "refilter": _refilter,
}

_run_lock = threading.Lock()


def run_pending(db_path=None) -> int:
    """Drain queued in-process tasks, one at a time. Safe to call from the
    scheduler tick and from tests; overlapping calls return immediately."""
    if not _run_lock.acquire(blocking=False):
        return 0
    done = 0
    try:
        while True:
            conn = db.connect(db_path)
            try:
                task = repo.claim_task(conn, IN_PROCESS)
            finally:
                conn.close()
            if task is None:
                return done
            try:
                result = HANDLERS[task["kind"]](db_path, task["payload"])
                error = None
            except Exception as e:  # noqa: BLE001 - recorded on the task row
                log.error("task %s (%s) failed\n%s", task["id"], task["kind"],
                          traceback.format_exc())
                result, error = None, f"{type(e).__name__}: {e}"
            with db.session(db_path) as conn:
                repo.finish_task(conn, task["id"], result=result, error=error)
            done += 1
    finally:
        _run_lock.release()


def release_stale_fills(db_path=None) -> int:
    """A fill task whose worker stopped heartbeating goes back to 'waiting' so
    the application is not stuck in 'filling' forever."""
    released = 0
    with db.session(db_path) as conn:
        for task in repo.stale_tasks(conn, "fill", FILL_STALE_SECONDS):
            repo.finish_task(conn, task["id"], error="worker stopped responding")
            app_id = task["payload"].get("application_id")
            app = repo.get_application(conn, app_id) if app_id else None
            if app and app["state"] == "filling":
                repo.update_application(conn, app_id, {
                    "state": "waiting",
                    "manual_reason": "The apply worker stopped before the form was filled."})
            released += 1
    return released


class Scheduler:
    def __init__(self, db_path=None) -> None:
        self.db_path = db_path
        self.sched = BackgroundScheduler(job_defaults={"coalesce": True, "max_instances": 1,
                                                       "misfire_grace_time": 3600})

    def start(self) -> None:
        with db.session(self.db_path) as conn:
            recovered = repo.recover_tasks(conn, IN_PROCESS)
        if recovered:
            log.info("re-queued %d task(s) interrupted by the last shutdown", recovered)
        self.sched.add_job(lambda: run_pending(self.db_path), "interval", seconds=3,
                           id="runner")
        self.sched.add_job(lambda: release_stale_fills(self.db_path), "interval",
                           seconds=60, id="stale-fills")
        self.reschedule()
        self.sched.start()

    def reschedule(self) -> None:
        """(Re)install the daily trigger from the current settings."""
        with db.session(self.db_path) as conn:
            s = seed.app_settings(conn)
        self.sched.add_job(self.enqueue_daily, CronTrigger(
            hour=int(s["fetch_hour"]), minute=int(s["fetch_minute"])),
            id="daily", replace_existing=True)

    def enqueue_daily(self) -> None:
        with db.session(self.db_path) as conn:
            repo.enqueue(conn, "daily", dedupe_key="daily")

    def next_run(self) -> str | None:
        job = self.sched.get_job("daily") if self.sched.running else None
        return job.next_run_time.isoformat() if job and job.next_run_time else None

    def shutdown(self) -> None:
        if self.sched.running:
            self.sched.shutdown(wait=False)
