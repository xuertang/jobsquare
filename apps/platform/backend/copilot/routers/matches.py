from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import apply, llm, referrals, repo, seed
from ..deps import found, get_conn

router = APIRouter(tags=["matches"])


def _with_contacts(conn, matches: list[dict]) -> list[dict]:
    """Attach how many known contacts each match's company has."""
    counts = repo.contact_counts(conn)
    for m in matches:
        keys = repo.company_keys({"name": m["company"], "board_token": m["board_token"],
                                  "aliases": m["aliases"]})
        m["contacts"] = sum(counts.get(k, 0) for k in keys)
    return matches


@router.get("/matches")
def list_matches(state: str = "new", q: str = "", min_score: int | None = None,
                 conn=Depends(get_conn)):
    if state not in ("new", "approved", "dismissed", "snoozed"):
        raise HTTPException(400, "unknown state")
    repo.wake_snoozed(conn)
    rows = repo.list_matches(conn, state=state, query=q.strip(), min_score=min_score)
    return {"matches": _with_contacts(conn, rows), "counts": repo.match_counts(conn)}


@router.post("/matches/{match_id}/approve")
def approve(match_id: int, conn=Depends(get_conn)):
    try:
        return apply.approve(conn, match_id)
    except KeyError:
        raise HTTPException(404, "match not found")
    except apply.ApplyError as e:
        raise HTTPException(409, str(e))


@router.post("/matches/{match_id}/dismiss")
def dismiss(match_id: int, conn=Depends(get_conn)):
    found(repo.get_match(conn, match_id), "match")
    repo.set_match_state(conn, match_id, "dismissed")
    return repo.get_match(conn, match_id)


class Snooze(BaseModel):
    days: int = 7


@router.post("/matches/{match_id}/snooze")
def snooze(match_id: int, body: Snooze, conn=Depends(get_conn)):
    found(repo.get_match(conn, match_id), "match")
    until = (date.today() + timedelta(days=max(1, min(body.days, 365)))).isoformat()
    repo.set_match_state(conn, match_id, "snoozed", snoozed_until=until)
    return repo.get_match(conn, match_id)


@router.post("/matches/{match_id}/restore")
def restore(match_id: int, conn=Depends(get_conn)):
    match = found(repo.get_match(conn, match_id), "match")
    if match["application_state"] == "submitted":
        raise HTTPException(409, "already applied to this posting")
    repo.set_match_state(conn, match_id, "new")
    return repo.get_match(conn, match_id)


@router.post("/matches/{match_id}/rescore")
def rescore(match_id: int, conn=Depends(get_conn)):
    found(repo.get_match(conn, match_id), "match")
    if not llm.available():
        raise HTTPException(409, "No Claude API credentials: scoring is unavailable.")
    repo.clear_score(conn, match_id)
    task_id, _ = repo.enqueue(conn, "score", {"match_ids": [match_id]},
                              dedupe_key=f"score:{match_id}")
    return {"task": repo.get_task(conn, task_id)}


@router.get("/postings/{posting_id}")
def posting_detail(posting_id: int, conn=Depends(get_conn)):
    """Everything about one posting: description, score, application state,
    and every contact and message for that company."""
    posting = found(repo.get_posting(conn, posting_id), "posting")
    company = found(repo.get_company(conn, posting["company_id"]), "company")
    application = repo.application_for_posting(conn, posting_id)
    if application:
        application["answers"] = repo.list_answers(conn, application["id"])
    contacts = referrals.contacts_for_company(conn, company, posting)
    for c in contacts:
        referrals.decorate(conn, c["messages"])
    duplicate = repo.find_duplicate(conn, posting)
    return {
        "posting": posting,
        "match": repo.match_for_posting(conn, posting_id),
        "application": application,
        "contacts": contacts,
        "search_links": referrals.search_links(posting, seed.load_profile(conn)),
        "duplicate": ({"id": duplicate["id"], "posting_id": duplicate["posting_id"],
                       "title": duplicate["title"], "state": duplicate["state"]}
                      if duplicate else None),
    }
