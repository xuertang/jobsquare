"""Daily digest through the scraper's existing notifier interface. Each line
links into the dashboard, not to the careers site."""
from __future__ import annotations

from . import config, db, repo, scraper, seed


def build(conn) -> tuple[list, list[int]]:
    """Unsent matches at or above the digest threshold, as scraper Job objects
    whose URL points at the posting's page in the dashboard."""
    Job = scraper.modules().models.Job
    settings = seed.app_settings(conn)
    jobs, ids = [], []
    for m in repo.digest_matches(conn, int(settings["digest_min_score"])):
        label = f"[{m['score']}] " if m["score"] is not None else ""
        jobs.append(Job(source=m["ats_type"], company=m["company"],
                        external_id=str(m["external_id"]), title=f"{label}{m['title']}",
                        url=f"{config.DASHBOARD_URL}/postings/{m['posting_id']}",
                        location=m["location"], salary_range=m["salary_range"]))
        ids.append(m["id"])
    return jobs, ids


def run_digest(db_path=None) -> dict:
    with db.session(db_path) as conn:
        jobs, ids = build(conn)
    if not jobs:
        return {"sent": 0}
    scraper.modules().notify.dispatch(jobs, [])
    with db.session(db_path) as conn:
        repo.mark_notified(conn, ids)
    return {"sent": len(jobs)}
