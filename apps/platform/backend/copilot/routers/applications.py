from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .. import apply, config, repo
from ..deps import found, get_conn

router = APIRouter(tags=["applications"])
STATUSES = ("applied", "screen", "onsite", "offer", "rejected", "withdrawn")


def _detail(conn, application_id: int) -> dict:
    app = found(repo.get_application(conn, application_id), "application")
    app["answers"] = repo.list_answers(conn, application_id)
    task = repo.active_task(conn, f"fill:{application_id}")
    app["fill_task"] = {"id": task["id"], "state": task["state"]} if task else None
    return app


@router.get("/applications")
def list_applications(scope: str = "queue", conn=Depends(get_conn)):
    apps = repo.list_applications(conn, submitted=(scope == "submitted"))
    for a in apps:
        answers = repo.list_answers(conn, a["id"])
        a["answer_count"] = len(answers)
        a["flagged_count"] = sum(1 for x in answers if x["flagged"])
        a["unfilled_count"] = sum(1 for x in answers if x["status"] != "filled")
        task = repo.active_task(conn, f"fill:{a['id']}")
        a["fill_task"] = {"id": task["id"], "state": task["state"]} if task else None
    return apps


@router.get("/applications/{application_id}")
def get_application(application_id: int, conn=Depends(get_conn)):
    return _detail(conn, application_id)


@router.post("/applications/{application_id}/launch")
def launch(application_id: int, conn=Depends(get_conn)):
    try:
        apply.launch(conn, application_id)
    except KeyError:
        raise HTTPException(404, "application not found")
    except apply.ApplyError as e:
        raise HTTPException(409, str(e))
    return _detail(conn, application_id)


@router.post("/applications/{application_id}/cancel-fill")
def cancel_fill(application_id: int, conn=Depends(get_conn)):
    app = found(repo.get_application(conn, application_id), "application")
    repo.cancel_tasks(conn, f"fill:{application_id}")
    if app["state"] == "filling":
        repo.update_application(conn, application_id, {"state": "waiting"})
    return _detail(conn, application_id)


@router.post("/applications/{application_id}/submitted")
def mark_submitted(application_id: int, conn=Depends(get_conn)):
    """I submitted this one myself: record it with the answers on file."""
    found(repo.get_application(conn, application_id), "application")
    apply.finalize(conn, application_id)
    return _detail(conn, application_id)


class Manual(BaseModel):
    reason: str = "Moved to the manual queue."


@router.post("/applications/{application_id}/manual")
def needs_manual(application_id: int, body: Manual, conn=Depends(get_conn)):
    app = found(repo.get_application(conn, application_id), "application")
    if app["state"] == "submitted":
        raise HTTPException(409, "already submitted")
    repo.cancel_tasks(conn, f"fill:{application_id}")
    repo.update_application(conn, application_id, {"state": "needs_manual",
                                                   "manual_reason": body.reason})
    if not repo.list_answers(conn, application_id):
        apply.seed_manual_answers(conn, application_id)
    return _detail(conn, application_id)


class Patch(BaseModel):
    status: str | None = None
    notes: str | None = None
    resume_id: int | None = None


@router.patch("/applications/{application_id}")
def patch(application_id: int, body: Patch, conn=Depends(get_conn)):
    found(repo.get_application(conn, application_id), "application")
    fields: dict = {}
    if body.status is not None:
        if body.status not in STATUSES:
            raise HTTPException(400, f"status must be one of {STATUSES}")
        fields["status"] = body.status
    if body.notes is not None:
        fields["notes"] = body.notes
    if body.resume_id is not None:
        resume = found(repo.get_resume(conn, body.resume_id), "resume")
        fields.update(resume_id=resume["id"], resume_variant=resume["label"])
    repo.update_application(conn, application_id, fields)
    return _detail(conn, application_id)


@router.delete("/applications/{application_id}")
def withdraw(application_id: int, conn=Depends(get_conn)):
    """Take a posting back out of the apply queue; its match returns to New."""
    app = found(repo.get_application(conn, application_id), "application")
    if app["state"] == "submitted":
        raise HTTPException(409, "a submitted application cannot be removed; "
                                 "set its status to withdrawn instead")
    repo.cancel_tasks(conn, f"fill:{application_id}")
    repo.delete_application(conn, application_id)
    if app["match_id"]:
        repo.set_match_state(conn, app["match_id"], "new")
    return {"ok": True}


class AnswerEdit(BaseModel):
    answer: str


@router.patch("/applications/{application_id}/answers/{answer_id}")
def edit_answer(application_id: int, answer_id: int, body: AnswerEdit,
                conn=Depends(get_conn)):
    answer = found(repo.get_answer(conn, answer_id), "answer")
    if answer["application_id"] != application_id:
        raise HTTPException(404, "answer not found")
    text = body.answer.strip()
    repo.update_answer(conn, answer_id, {
        "answer": text, "edited": True, "flagged": False,
        "status": "filled" if text else "unfilled",
        "source": answer["source"] if answer["status"] == "filled" else "manual"})
    return repo.get_answer(conn, answer_id)


class Question(BaseModel):
    question: str


@router.post("/applications/{application_id}/answers")
def draft_answer(application_id: int, body: Question, conn=Depends(get_conn)):
    """Manual queue: paste a question from the form, get the saved answer or
    a flagged draft to paste back."""
    if not body.question.strip():
        raise HTTPException(400, "question is empty")
    try:
        return apply.draft_manual_answer(conn, application_id, body.question.strip())
    except KeyError:
        raise HTTPException(404, "application not found")


@router.delete("/applications/{application_id}/answers/{answer_id}")
def delete_answer(application_id: int, answer_id: int, conn=Depends(get_conn)):
    answer = found(repo.get_answer(conn, answer_id), "answer")
    if answer["application_id"] != application_id:
        raise HTTPException(404, "answer not found")
    repo.delete_answer(conn, answer_id)
    return {"ok": True}


@router.get("/applications/{application_id}/screenshot")
def screenshot(application_id: int, conn=Depends(get_conn)):
    app = found(repo.get_application(conn, application_id), "application")
    path = (config.DATA_DIR / app["screenshot_path"]) if app["screenshot_path"] else None
    if not path or not path.is_file() or config.DATA_DIR not in path.resolve().parents:
        raise HTTPException(404, "no confirmation screenshot")
    return FileResponse(path, media_type="image/png")
