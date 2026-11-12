from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from .. import db, referrals, repo
from ..deps import found, get_conn

router = APIRouter(tags=["outreach"])
OUTCOMES = ("referred", "declined", "no_response", "replied")


@router.get("/outreach")
def outreach(conn=Depends(get_conn)):
    """Contacts per company for every company with an active match, plus
    follow-ups due and the sent log."""
    active = repo.list_matches(conn, state="new") + repo.list_matches(conn, state="approved")
    by_company: dict[int, dict] = {}
    for m in active:
        entry = by_company.setdefault(m["company_id"], {
            "company_id": m["company_id"], "company": m["company"], "postings": []})
        entry["postings"].append({"id": m["posting_id"], "title": m["title"],
                                  "score": m["score"], "state": m["state"],
                                  "location": m["location"]})
    groups = []
    for entry in by_company.values():
        company = repo.get_company(conn, entry["company_id"])
        contacts = referrals.contacts_for_company(conn, company)
        if not contacts:
            continue
        for c in contacts:
            referrals.decorate(conn, c["messages"])
        entry["contacts"] = contacts
        # Roles already in the apply queue first, then best fit first.
        entry["postings"].sort(key=lambda p: (p["state"] != "approved", -(p["score"] or -1)))
        entry["best_score"] = max((p["score"] or 0) for p in entry["postings"])
        groups.append(entry)
    groups.sort(key=lambda g: (-g["best_score"], g["company"].lower()))
    return {"companies": groups, "followups": referrals.followups(conn),
            "log": referrals.decorate(conn, repo.message_log(conn)),
            "contact_total": repo.contact_total(conn)}


@router.get("/contacts")
def contacts(q: str = "", conn=Depends(get_conn)):
    return repo.search_contacts(conn, q.strip())


class ContactIn(BaseModel):
    name: str
    company: str = ""
    title: str = ""
    profile_url: str = ""
    relationship_type: str = "connection"
    shared_context: str = ""
    notes: str = ""


@router.post("/contacts")
def add_contact(body: ContactIn, conn=Depends(get_conn)):
    """Add a contact by hand, for example a second-degree target found
    through a search link: paste their profile URL and name."""
    if not body.name.strip():
        raise HTTPException(400, "name is required")
    if body.relationship_type not in referrals.RELATIONSHIPS:
        raise HTTPException(400, "unknown relationship type")
    contact_id, _ = repo.upsert_contact(conn, {**body.model_dump(), "source": "manual"})
    repo.update_contact(conn, contact_id, body.model_dump(include={
        "relationship_type", "shared_context", "notes"}))
    return repo.get_contact(conn, contact_id)


class ContactPatch(BaseModel):
    name: str | None = None
    company: str | None = None
    title: str | None = None
    profile_url: str | None = None
    relationship_type: str | None = None
    shared_context: str | None = None
    notes: str | None = None


@router.patch("/contacts/{contact_id}")
def patch_contact(contact_id: int, body: ContactPatch, conn=Depends(get_conn)):
    found(repo.get_contact(conn, contact_id), "contact")
    fields = body.model_dump(exclude_none=True)
    if fields.get("relationship_type") and fields["relationship_type"] not in referrals.RELATIONSHIPS:
        raise HTTPException(400, "unknown relationship type")
    repo.update_contact(conn, contact_id, fields)
    return repo.get_contact(conn, contact_id)


@router.delete("/contacts/{contact_id}")
def delete_contact(contact_id: int, conn=Depends(get_conn)):
    repo.delete_contact(conn, contact_id)
    return {"ok": True}


@router.post("/contacts/import")
async def import_contacts(file: UploadFile = File(...), conn=Depends(get_conn)):
    data = await file.read()
    try:
        return referrals.import_contacts(conn, data)
    except ValueError as e:
        raise HTTPException(400, str(e))


class DraftIn(BaseModel):
    contact_id: int
    posting_id: int | None = None
    kind: str = "initial"
    regenerate: bool = False


@router.post("/messages/draft")
def draft(body: DraftIn, conn=Depends(get_conn)):
    if body.kind not in ("initial", "followup"):
        raise HTTPException(400, "kind must be initial or followup")
    try:
        return referrals.draft_message(conn, body.contact_id, body.posting_id, body.kind,
                                       body.regenerate)
    except KeyError:
        raise HTTPException(404, "contact not found")


class MessagePatch(BaseModel):
    body: str


@router.patch("/messages/{message_id}")
def edit_message(message_id: int, body: MessagePatch, conn=Depends(get_conn)):
    message = found(repo.get_message(conn, message_id), "message")
    if message["sent_at"] and message["direction"] == "out":
        raise HTTPException(409, "this message is logged as sent; unmark it to edit")
    repo.update_message(conn, message_id, {"body": body.body, "source": "manual"})
    return referrals.decorate(conn, [repo.get_message(conn, message_id)])[0]


@router.post("/messages/{message_id}/sent")
def mark_sent(message_id: int, conn=Depends(get_conn)):
    """One click after pasting the message into LinkedIn: log it as sent."""
    found(repo.get_message(conn, message_id), "message")
    repo.update_message(conn, message_id, {"sent_at": db.now()})
    return repo.get_message(conn, message_id)


@router.post("/messages/{message_id}/unsent")
def mark_unsent(message_id: int, conn=Depends(get_conn)):
    found(repo.get_message(conn, message_id), "message")
    repo.update_message(conn, message_id, {"sent_at": None})
    return repo.get_message(conn, message_id)


@router.delete("/messages/{message_id}")
def delete_message(message_id: int, conn=Depends(get_conn)):
    repo.delete_message(conn, message_id)
    return {"ok": True}


class ReplyIn(BaseModel):
    posting_id: int | None = None
    body: str = ""
    outcome: str = "replied"


@router.post("/contacts/{contact_id}/reply")
def log_reply(contact_id: int, body: ReplyIn, conn=Depends(get_conn)):
    """Log a reply or an outcome (referred, declined, no response)."""
    found(repo.get_contact(conn, contact_id), "contact")
    if body.outcome not in OUTCOMES:
        raise HTTPException(400, f"outcome must be one of {OUTCOMES}")
    outcome = None if body.outcome == "replied" else body.outcome
    message_id = repo.add_message(
        conn, contact_id=contact_id, posting_id=body.posting_id, body=body.body.strip(),
        direction="in", kind="reply", source="manual", outcome=outcome, sent=True)
    return repo.get_message(conn, message_id)


@router.get("/followups")
def followups(conn=Depends(get_conn)):
    return referrals.followups(conn)
