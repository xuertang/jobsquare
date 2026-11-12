from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from .. import answers, config, db, filters, repo, seed
from ..deps import found, get_conn

router = APIRouter(prefix="/settings", tags=["settings"])
RESUME_TYPES = {".pdf", ".doc", ".docx", ".txt", ".md", ".rtf"}


# ---------------------------------------------------------------- criteria ---
@router.get("/criteria")
def get_criteria(conn=Depends(get_conn)):
    return {"search": seed.search_criteria(conn), "app": seed.app_settings(conn),
            "levels": list(filters.LEVELS)}


@router.put("/criteria")
def put_criteria(request: Request, body: dict = Body(...), conn=Depends(get_conn)):
    """Save search criteria and app settings. Matches are re-filtered in the
    background, and the daily trigger moves if the fetch time changed."""
    if "search" in body:
        search = {**seed.search_criteria(conn), **body["search"]}
        bad = set(search.get("levels") or []) - set(filters.LEVELS)
        if bad:
            raise HTTPException(400, f"unknown level(s): {sorted(bad)}")
        repo.set_config(conn, "criteria", "search", search)
        repo.enqueue(conn, "refilter", dedupe_key="refilter")
    if "app" in body:
        app = {**seed.app_settings(conn), **body["app"]}
        for key, default in seed.DEFAULT_APP.items():
            try:
                app[key] = type(default)(app[key])
            except (TypeError, ValueError):
                raise HTTPException(400, f"{key} must be a number")
        if not (0 <= app["fetch_hour"] <= 23 and 0 <= app["fetch_minute"] <= 59):
            raise HTTPException(400, "fetch time is out of range")
        repo.set_config(conn, "criteria", "app", app)
        conn.commit()
        if request.app.state.scheduler:
            request.app.state.scheduler.reschedule()
    return get_criteria(conn)


# ----------------------------------------------------------------- profile ---
@router.get("/profile")
def get_profile(conn=Depends(get_conn)):
    return seed.load_profile(conn)


@router.put("/profile")
def put_profile(body: dict = Body(...), conn=Depends(get_conn)):
    for key, value in body.items():
        if key not in seed.DEFAULT_PROFILE:
            raise HTTPException(400, f"unknown profile section: {key}")
        if type(value) is not type(seed.DEFAULT_PROFILE[key]):
            raise HTTPException(400, f"profile section {key} has the wrong shape")
        repo.set_config(conn, "profile", key, value)
    return seed.load_profile(conn)


@router.post("/profile/import-job-ops")
def import_job_ops(conn=Depends(get_conn)):
    """Copy the apply profile already filled in for the job-ops plugin."""
    path = config.SCRAPER_DIR / "config" / "apply-profile.json"
    if not path.is_file():
        raise HTTPException(404, f"no apply profile at {path}")
    changed = seed.import_job_ops_profile(conn, json.loads(path.read_text()))
    return {"updated": changed, "profile": seed.load_profile(conn)}


# ----------------------------------------------------------------- resumes ---
def _resume_text(filename: str, data: bytes) -> str:
    """Best-effort text for scoring and drafts. Editable afterwards."""
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in (".txt", ".md"):
        return data.decode("utf-8", errors="replace")
    if ext == ".pdf":
        try:
            import io

            from pypdf import PdfReader
            pages = PdfReader(io.BytesIO(data)).pages
            return "\n".join((p.extract_text() or "") for p in pages).strip()
        except Exception:  # noqa: BLE001 - an unreadable PDF is not fatal
            return ""
    return ""


def _public_resume(r: dict) -> dict:
    return {**{k: v for k, v in r.items() if k != "path"}, "has_file": bool(r["path"])}


@router.get("/resumes")
def list_resumes(conn=Depends(get_conn)):
    return [_public_resume(r) for r in repo.list_resumes(conn)]


@router.post("/resumes")
async def add_resume(label: str = Form(...), keywords: str = Form(""), text: str = Form(""),
                     file: UploadFile | None = File(None), conn=Depends(get_conn)):
    if not label.strip():
        raise HTTPException(400, "label is required")
    filename, rel, data = "", "", b""
    if file is not None and file.filename:
        filename = re.sub(r"[^A-Za-z0-9._ -]+", "_", file.filename).strip() or "resume"
        ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in RESUME_TYPES:
            raise HTTPException(400, f"unsupported file type {ext or '(none)'}")
        data = await file.read()
        if len(data) > 10 * 1024 * 1024:
            raise HTTPException(400, "file is larger than 10 MB")
    resume_id = repo.add_resume(conn, label=label.strip(), filename=filename,
                                keywords=keywords.strip(),
                                text=text.strip() or _resume_text(filename, data))
    if data:
        config.ensure_dirs()
        rel = f"resumes/{resume_id}-{filename}"
        (config.DATA_DIR / rel).write_bytes(data)
        repo.update_resume(conn, resume_id, {"path": rel})
    return _public_resume(repo.get_resume(conn, resume_id))


class ResumePatch(BaseModel):
    label: str | None = None
    keywords: str | None = None
    text: str | None = None
    is_default: bool | None = None


@router.patch("/resumes/{resume_id}")
def patch_resume(resume_id: int, body: ResumePatch, conn=Depends(get_conn)):
    found(repo.get_resume(conn, resume_id), "resume")
    repo.update_resume(conn, resume_id, body.model_dump(exclude_none=True))
    return _public_resume(repo.get_resume(conn, resume_id))


@router.delete("/resumes/{resume_id}")
def delete_resume(resume_id: int, conn=Depends(get_conn)):
    resume = found(repo.get_resume(conn, resume_id), "resume")
    if resume["path"]:
        path = config.DATA_DIR / resume["path"]
        if path.is_file() and config.RESUME_DIR in path.resolve().parents:
            path.unlink()
    repo.delete_resume(conn, resume_id)
    return {"ok": True}


# ------------------------------------------------------------- answer bank ---
def _public_bank(e: dict) -> dict:
    return {k: v for k, v in e.items() if k != "embedding"}


class BankIn(BaseModel):
    question: str
    answer: str


@router.get("/answers")
def list_bank(conn=Depends(get_conn)):
    return [_public_bank(e) for e in repo.list_bank(conn)]


@router.post("/answers")
def add_bank(body: BankIn, conn=Depends(get_conn)):
    if not body.question.strip() or not body.answer.strip():
        raise HTTPException(400, "question and answer are both required")
    bank_id = answers.save(conn, body.question, body.answer)
    return _public_bank(repo.get_bank(conn, bank_id))


@router.patch("/answers/{bank_id}")
def patch_bank(bank_id: int, body: BankIn, conn=Depends(get_conn)):
    found(repo.get_bank(conn, bank_id), "answer")
    repo.update_bank(conn, bank_id, question=body.question.strip(),
                     answer=body.answer.strip(),
                     embedding=answers.embedder.embed(answers.canonical(body.question)))
    return _public_bank(repo.get_bank(conn, bank_id))


@router.delete("/answers/{bank_id}")
def delete_bank(bank_id: int, conn=Depends(get_conn)):
    repo.delete_bank(conn, bank_id)
    return {"ok": True}


# --------------------------------------------------------------- companies ---
class CompanyIn(BaseModel):
    name: str
    ats_type: str
    board_token: str
    board_config: dict[str, Any] = {}
    aliases: str = ""
    active: bool = True


class CompanyPatch(BaseModel):
    name: str | None = None
    board_token: str | None = None
    board_config: dict[str, Any] | None = None
    aliases: str | None = None
    active: bool | None = None


def _check_company(ats_type: str, token: str, cfg: dict) -> None:
    if ats_type not in config.ATS_TYPES:
        raise HTTPException(400, f"ATS must be one of {config.ATS_TYPES}")
    if not token.strip():
        raise HTTPException(400, "board token is required")
    if ats_type == "workday" and not all(cfg.get(k) for k in ("host", "tenant", "site")):
        raise HTTPException(400, "Workday needs host, tenant and site in the board config")


@router.get("/companies")
def list_companies(conn=Depends(get_conn)):
    return repo.list_companies(conn)


@router.post("/companies")
def add_company(body: CompanyIn, conn=Depends(get_conn)):
    _check_company(body.ats_type, body.board_token, body.board_config)
    company_id, created = repo.upsert_company(
        conn, name=body.name.strip() or body.board_token, ats_type=body.ats_type,
        board_token=body.board_token.strip(), board_config=body.board_config,
        active=body.active, aliases=body.aliases)
    if not created:
        raise HTTPException(409, "that board is already in the company list")
    return repo.get_company(conn, company_id)


@router.patch("/companies/{company_id}")
def patch_company(company_id: int, body: CompanyPatch, conn=Depends(get_conn)):
    company = found(repo.get_company(conn, company_id), "company")
    fields = body.model_dump(exclude_none=True)
    _check_company(company["ats_type"], fields.get("board_token", company["board_token"]),
                   fields.get("board_config", company["board_config"]))
    repo.update_company(conn, company_id, fields)
    return repo.get_company(conn, company_id)


@router.delete("/companies/{company_id}")
def delete_company(company_id: int, conn=Depends(get_conn)):
    found(repo.get_company(conn, company_id), "company")
    applied = conn.execute(
        "SELECT COUNT(*) FROM applications a JOIN postings p ON p.id = a.posting_id "
        "WHERE p.company_id = ?", (company_id,)).fetchone()[0]
    if applied:
        raise HTTPException(409, "this company has applications on record; "
                                 "deactivate it instead of deleting it")
    repo.delete_company(conn, company_id)
    return {"ok": True}


@router.post("/companies/sync")
def sync_companies(conn=Depends(get_conn)):
    """Add any boards from the scraper's sources.yaml that are missing here."""
    return seed.sync_companies(conn)


@router.post("/companies/{company_id}/fetch")
def fetch_company(company_id: int, conn=Depends(get_conn)):
    found(repo.get_company(conn, company_id), "company")
    task_id, _ = repo.enqueue(conn, "fetch", {"company_ids": [company_id]},
                              dedupe_key=f"fetch:{company_id}")
    return {"task": repo.get_task(conn, task_id)}


# ------------------------------------------------------------ import/export ---
@router.get("/export")
def export(conn=Depends(get_conn)):
    """Everything configured by hand, as one JSON document. Resume files and
    the browser profile are not included."""
    return {
        "exported_at": db.now(),
        "criteria": {"search": seed.search_criteria(conn), "app": seed.app_settings(conn)},
        "profile": seed.load_profile(conn),
        "answer_bank": [{"question": e["question"], "answer": e["answer"]}
                        for e in repo.list_bank(conn)],
        "companies": [{k: c[k] for k in ("name", "ats_type", "board_token", "board_config",
                                         "aliases", "active")}
                      for c in repo.list_companies(conn)],
        "contacts": [{k: c[k] for k in ("name", "company", "title", "profile_url",
                                        "relationship_type", "source", "connected_on",
                                        "shared_context", "notes")}
                     for c in repo.search_contacts(conn, limit=100000)],
    }


@router.post("/import")
def import_settings(body: dict = Body(...), conn=Depends(get_conn)):
    """Merge an export back in. Existing rows are kept; nothing is deleted."""
    out = {"criteria": 0, "profile": 0, "answer_bank": 0, "companies": 0, "contacts": 0}
    for key in ("search", "app"):
        if isinstance((body.get("criteria") or {}).get(key), dict):
            repo.set_config(conn, "criteria", key, body["criteria"][key])
            out["criteria"] += 1
    for key, value in (body.get("profile") or {}).items():
        if key in seed.DEFAULT_PROFILE and type(value) is type(seed.DEFAULT_PROFILE[key]):
            repo.set_config(conn, "profile", key, value)
            out["profile"] += 1
    for entry in body.get("answer_bank") or []:
        if entry.get("question") and entry.get("answer"):
            out["answer_bank"] += int(bool(answers.save(conn, entry["question"],
                                                        entry["answer"])))
    for c in body.get("companies") or []:
        if c.get("ats_type") in config.ATS_TYPES and c.get("board_token"):
            _, created = repo.upsert_company(
                conn, name=c.get("name") or c["board_token"], ats_type=c["ats_type"],
                board_token=c["board_token"], board_config=c.get("board_config") or {},
                active=bool(c.get("active", True)), aliases=c.get("aliases") or "")
            out["companies"] += int(created)
    for c in body.get("contacts") or []:
        if c.get("name"):
            _, created = repo.upsert_contact(conn, c)
            out["contacts"] += int(created)
    return out
