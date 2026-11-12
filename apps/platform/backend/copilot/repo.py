"""Repository layer. Every SQL statement in the app lives here, so the store
can move from SQLite to Postgres without touching the callers."""
from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from .db import now, today

Row = dict[str, Any]
Conn = sqlite3.Connection


def _rows(cur: sqlite3.Cursor) -> list[Row]:
    return [dict(r) for r in cur.fetchall()]


def _one(conn: Conn, sql: str, args: Iterable = ()) -> Row | None:
    r = conn.execute(sql, tuple(args)).fetchone()
    return dict(r) if r else None


def _all(conn: Conn, sql: str, args: Iterable = ()) -> list[Row]:
    return _rows(conn.execute(sql, tuple(args)))


def _update(conn: Conn, table: str, row_id: int, fields: dict, allowed: set[str]) -> None:
    cols = {k: v for k, v in fields.items() if k in allowed}
    if not cols:
        return
    sets = ", ".join(f"{k} = ?" for k in cols)
    conn.execute(f"UPDATE {table} SET {sets} WHERE id = ?", (*cols.values(), row_id))


# ---------------------------------------------------------------- config ---
def get_config(conn: Conn, table: str, key: str, default: Any = None) -> Any:
    assert table in ("criteria", "profile")
    r = conn.execute(f"SELECT value FROM {table} WHERE key = ?", (key,)).fetchone()
    return json.loads(r["value"]) if r else default


def set_config(conn: Conn, table: str, key: str, value: Any) -> None:
    assert table in ("criteria", "profile")
    conn.execute(
        f"INSERT INTO {table}(key, value, updated_at) VALUES (?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
        "updated_at = excluded.updated_at", (key, json.dumps(value), now()))


def all_config(conn: Conn, table: str) -> dict[str, Any]:
    assert table in ("criteria", "profile")
    return {r["key"]: json.loads(r["value"])
            for r in conn.execute(f"SELECT key, value FROM {table}")}


# ------------------------------------------------------------- companies ---
_SUFFIXES = {"inc", "incorporated", "llc", "ltd", "limited", "corp", "corporation",
             "co", "company", "gmbh", "plc", "lp", "llp", "holdings", "group",
             "technologies", "technology"}


def company_key(name: str) -> str:
    """Normalize a company name for matching contacts to postings:
    'Stripe, Inc.' and 'stripe' both become 'stripe'."""
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    words = re.findall(r"[a-z0-9]+", s.lower())
    while len(words) > 1 and words[-1] in _SUFFIXES:
        words.pop()
    return "".join(words)


def company_keys(company: Row) -> set[str]:
    keys = {company_key(company["name"])}
    token = company.get("board_token") or ""
    if token and "/" not in token:
        keys.add(company_key(token))
    for alias in (company.get("aliases") or "").split(","):
        if alias.strip():
            keys.add(company_key(alias))
    keys.discard("")
    return keys


def _company(row: Row | None) -> Row | None:
    if row:
        row["board_config"] = json.loads(row.get("board_config") or "{}")
        row["active"] = bool(row["active"])
    return row


def list_companies(conn: Conn, active_only: bool = False) -> list[Row]:
    sql = ("SELECT c.*, (SELECT COUNT(*) FROM postings p WHERE p.company_id = c.id "
           "AND p.closed = 0) AS open_postings FROM companies c")
    if active_only:
        sql += " WHERE c.active = 1"
    return [_company(r) for r in _all(conn, sql + " ORDER BY c.name COLLATE NOCASE")]


def get_company(conn: Conn, company_id: int) -> Row | None:
    return _company(_one(conn, "SELECT * FROM companies WHERE id = ?", (company_id,)))


def upsert_company(conn: Conn, *, name: str, ats_type: str, board_token: str,
                   board_config: dict | None = None, active: bool = True,
                   aliases: str = "") -> tuple[int, bool]:
    """Insert, or leave an existing (ats_type, board_token) row alone.
    Returns (id, created)."""
    existing = conn.execute(
        "SELECT id FROM companies WHERE ats_type = ? AND board_token = ?",
        (ats_type, board_token)).fetchone()
    if existing:
        return existing["id"], False
    cur = conn.execute(
        "INSERT INTO companies(name, ats_type, board_token, board_config, aliases, "
        "active, created_at) VALUES (?,?,?,?,?,?,?)",
        (name, ats_type, board_token, json.dumps(board_config or {}), aliases,
         int(active), now()))
    return cur.lastrowid, True


def update_company(conn: Conn, company_id: int, fields: dict) -> None:
    fields = dict(fields)
    if "board_config" in fields:
        fields["board_config"] = json.dumps(fields["board_config"] or {})
    if "active" in fields:
        fields["active"] = int(bool(fields["active"]))
    _update(conn, "companies", company_id, fields,
            {"name", "ats_type", "board_token", "board_config", "aliases", "active"})


def delete_company(conn: Conn, company_id: int) -> None:
    conn.execute("DELETE FROM companies WHERE id = ?", (company_id,))


def record_fetch(conn: Conn, company_id: int, *, status: str, count: int = 0,
                 error: str = "") -> None:
    ok = status == "ok"
    conn.execute(
        "UPDATE companies SET last_fetch_at = ?, last_status = ?, last_error = ?, "
        "last_count = ?, best_count = MAX(best_count, ?), "
        "failures = CASE WHEN ? THEN 0 ELSE failures + 1 END WHERE id = ?",
        (now(), status, error[:500], count, count, ok, company_id))


# -------------------------------------------------------------- postings ---
POSTING_COLS = ("external_id", "requisition_id", "title", "location", "remote",
                "department", "employment_type", "salary_range", "url", "apply_url",
                "ats_type", "posted_at")


def upsert_postings(conn: Conn, company_id: int, rows: list[Row]) -> list[int]:
    """Insert new postings and refresh the ones already known. Dedup is the
    UNIQUE(company_id, external_id) key. Returns ids of newly seen postings."""
    stamp = now()
    known = {r["external_id"]: r["id"] for r in conn.execute(
        "SELECT id, external_id FROM postings WHERE company_id = ?", (company_id,))}
    new_ids: list[int] = []
    for row in rows:
        vals = [row.get(c, "") for c in POSTING_COLS]
        if row["external_id"] in known:
            conn.execute(
                "UPDATE postings SET requisition_id=?, title=?, location=?, remote=?, "
                "department=?, employment_type=?, salary_range=?, url=?, apply_url=?, "
                "ats_type=?, posted_at=COALESCE(NULLIF(?, ''), posted_at), last_seen=?, "
                "closed=0, closed_at=NULL, "
                "description=COALESCE(description, ?) WHERE id=?",
                (*vals[1:], stamp, row.get("description"), known[row["external_id"]]))
        else:
            cur = conn.execute(
                "INSERT INTO postings(company_id, external_id, requisition_id, title, "
                "location, remote, department, employment_type, salary_range, url, "
                "apply_url, ats_type, posted_at, description, first_seen, last_seen) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (company_id, *vals, row.get("description"), stamp, stamp))
            known[row["external_id"]] = cur.lastrowid
            new_ids.append(cur.lastrowid)
    return new_ids


def close_missing(conn: Conn, company_id: int, seen_external_ids: set[str]) -> int:
    """Mark postings that left the board as closed. Callers only do this after
    a fetch they trust (see pipeline.fetch_company)."""
    open_rows = conn.execute(
        "SELECT id, external_id FROM postings WHERE company_id = ? AND closed = 0",
        (company_id,)).fetchall()
    gone = [r["id"] for r in open_rows if r["external_id"] not in seen_external_ids]
    stamp = now()
    for pid in gone:
        conn.execute("UPDATE postings SET closed = 1, closed_at = ? WHERE id = ?",
                     (stamp, pid))
    return len(gone)


POSTING_SELECT = ("SELECT p.*, c.name AS company, c.board_token, c.board_config, "
                  "c.aliases FROM postings p JOIN companies c ON c.id = p.company_id")


def _posting(row: Row | None) -> Row | None:
    if row:
        row["board_config"] = json.loads(row.get("board_config") or "{}")
        row["remote"] = bool(row["remote"])
        row["closed"] = bool(row["closed"])
    return row


def get_posting(conn: Conn, posting_id: int) -> Row | None:
    return _posting(_one(conn, POSTING_SELECT + " WHERE p.id = ?", (posting_id,)))


def open_postings(conn: Conn) -> list[Row]:
    return [_posting(r) for r in _all(
        conn, POSTING_SELECT + " WHERE p.closed = 0 AND c.active = 1")]


def set_description(conn: Conn, posting_id: int, text: str) -> None:
    conn.execute("UPDATE postings SET description = ? WHERE id = ?", (text, posting_id))


# --------------------------------------------------------------- matches ---
def sync_match(conn: Conn, posting_id: int, passes: bool) -> bool:
    """Create the match row for a posting that passes the hard filter, or flip
    passes_filter on an existing one. Returns True when a row was created."""
    row = conn.execute("SELECT id, passes_filter FROM matches WHERE posting_id = ?",
                       (posting_id,)).fetchone()
    stamp = now()
    if row is None:
        if not passes:
            return False
        conn.execute("INSERT INTO matches(posting_id, created_at, updated_at) "
                     "VALUES (?,?,?)", (posting_id, stamp, stamp))
        return True
    if bool(row["passes_filter"]) != passes:
        conn.execute("UPDATE matches SET passes_filter = ?, updated_at = ? WHERE id = ?",
                     (int(passes), stamp, row["id"]))
    return False


MATCH_SELECT = (
    "SELECT m.id, m.posting_id, m.score, m.rationale, m.score_model, m.scored_at, "
    "m.score_error, m.state, m.snoozed_until, m.passes_filter, m.created_at, "
    "p.title, p.location, p.remote, p.department, p.salary_range, p.url, p.apply_url, "
    "p.ats_type, p.posted_at, p.first_seen, p.closed, p.company_id, p.external_id, "
    "p.requisition_id, (p.description IS NOT NULL) AS has_description, "
    "c.name AS company, c.board_token, c.aliases, "
    "a.id AS application_id, a.state AS application_state "
    "FROM matches m JOIN postings p ON p.id = m.posting_id "
    "JOIN companies c ON c.id = p.company_id "
    "LEFT JOIN applications a ON a.posting_id = p.id")


def _match(row: Row | None) -> Row | None:
    if row:
        for k in ("remote", "closed", "passes_filter", "has_description"):
            row[k] = bool(row[k])
    return row


def list_matches(conn: Conn, *, state: str = "new", query: str = "",
                 min_score: int | None = None, include_closed: bool = False,
                 limit: int = 500) -> list[Row]:
    sql = MATCH_SELECT + " WHERE m.state = ? AND m.passes_filter = 1"
    args: list[Any] = [state]
    if not include_closed:
        sql += " AND p.closed = 0"
    if query:
        sql += " AND (p.title LIKE ? OR c.name LIKE ? OR p.location LIKE ?)"
        args += [f"%{query}%"] * 3
    if min_score is not None:
        sql += " AND m.score >= ?"
        args.append(min_score)
    sql += (" ORDER BY (m.score IS NULL), m.score DESC, "
            "COALESCE(p.posted_at, p.first_seen) DESC LIMIT ?")
    args.append(limit)
    return [_match(r) for r in _all(conn, sql, args)]


def get_match(conn: Conn, match_id: int) -> Row | None:
    return _match(_one(conn, MATCH_SELECT + " WHERE m.id = ?", (match_id,)))


def match_for_posting(conn: Conn, posting_id: int) -> Row | None:
    return _match(_one(conn, MATCH_SELECT + " WHERE m.posting_id = ?", (posting_id,)))


def match_counts(conn: Conn) -> dict[str, int]:
    out = {"new": 0, "approved": 0, "dismissed": 0, "snoozed": 0, "unscored": 0}
    for r in conn.execute(
            "SELECT m.state, COUNT(*) n FROM matches m JOIN postings p ON p.id = "
            "m.posting_id WHERE m.passes_filter = 1 AND p.closed = 0 GROUP BY m.state"):
        out[r["state"]] = r["n"]
    out["unscored"] = conn.execute(
        "SELECT COUNT(*) FROM matches m JOIN postings p ON p.id = m.posting_id "
        "WHERE m.passes_filter = 1 AND p.closed = 0 AND m.state = 'new' "
        "AND m.score IS NULL").fetchone()[0]
    return out


def set_match_state(conn: Conn, match_id: int, state: str,
                    snoozed_until: str | None = None) -> None:
    conn.execute("UPDATE matches SET state = ?, snoozed_until = ?, updated_at = ? "
                 "WHERE id = ?", (state, snoozed_until, now(), match_id))


def wake_snoozed(conn: Conn) -> int:
    cur = conn.execute(
        "UPDATE matches SET state = 'new', snoozed_until = NULL, updated_at = ? "
        "WHERE state = 'snoozed' AND snoozed_until IS NOT NULL AND snoozed_until <= ?",
        (now(), today()))
    return cur.rowcount


def unscored_matches(conn: Conn, limit: int) -> list[Row]:
    """Matches still owed a score. One row per posting, so a posting is scored
    at most once; rescoring is an explicit action."""
    return [_posting(r) for r in _all(
        conn,
        "SELECT m.id AS match_id, p.*, c.name AS company, c.board_token, "
        "c.board_config, c.aliases FROM matches m JOIN postings p ON p.id = m.posting_id "
        "JOIN companies c ON c.id = p.company_id WHERE m.score IS NULL "
        "AND m.passes_filter = 1 AND m.state = 'new' AND p.closed = 0 "
        "ORDER BY COALESCE(p.posted_at, p.first_seen) DESC LIMIT ?", (limit,))]


def set_score(conn: Conn, match_id: int, score: int, rationale: str, model: str) -> None:
    conn.execute(
        "UPDATE matches SET score = ?, rationale = ?, score_model = ?, scored_at = ?, "
        "score_error = NULL, updated_at = ? WHERE id = ?",
        (score, rationale, model, now(), now(), match_id))


def set_score_error(conn: Conn, match_id: int, error: str) -> None:
    conn.execute("UPDATE matches SET score_error = ?, updated_at = ? WHERE id = ?",
                 (error[:500], now(), match_id))


def clear_score(conn: Conn, match_id: int) -> None:
    conn.execute("UPDATE matches SET score = NULL, rationale = NULL, scored_at = NULL, "
                 "score_error = NULL, updated_at = ? WHERE id = ?", (now(), match_id))


def digest_matches(conn: Conn, min_score: int) -> list[Row]:
    return [_match(r) for r in _all(
        conn, MATCH_SELECT + " WHERE m.state = 'new' AND m.passes_filter = 1 "
        "AND p.closed = 0 AND m.notified_at IS NULL "
        "AND (m.score IS NULL OR m.score >= ?) "
        "ORDER BY (m.score IS NULL), m.score DESC", (min_score,))]


def mark_notified(conn: Conn, match_ids: list[int]) -> None:
    stamp = now()
    conn.executemany("UPDATE matches SET notified_at = ? WHERE id = ?",
                     [(stamp, i) for i in match_ids])


# --------------------------------------------------------------- resumes ---
def list_resumes(conn: Conn) -> list[Row]:
    rows = _all(conn, "SELECT * FROM resumes ORDER BY is_default DESC, label")
    for r in rows:
        r["is_default"] = bool(r["is_default"])
    return rows


def get_resume(conn: Conn, resume_id: int) -> Row | None:
    return _one(conn, "SELECT * FROM resumes WHERE id = ?", (resume_id,))


def add_resume(conn: Conn, *, label: str, filename: str = "", path: str = "",
               keywords: str = "", text: str = "", is_default: bool = False) -> int:
    first = conn.execute("SELECT COUNT(*) FROM resumes").fetchone()[0] == 0
    cur = conn.execute(
        "INSERT INTO resumes(label, filename, path, keywords, text, is_default, "
        "created_at) VALUES (?,?,?,?,?,0,?)",
        (label, filename, path, keywords, text, now()))
    if is_default or first:
        set_default_resume(conn, cur.lastrowid)
    return cur.lastrowid


def update_resume(conn: Conn, resume_id: int, fields: dict) -> None:
    _update(conn, "resumes", resume_id, fields,
            {"label", "keywords", "text", "filename", "path"})
    if fields.get("is_default"):
        set_default_resume(conn, resume_id)


def set_default_resume(conn: Conn, resume_id: int) -> None:
    conn.execute("UPDATE resumes SET is_default = (id = ?)", (resume_id,))


def delete_resume(conn: Conn, resume_id: int) -> None:
    conn.execute("DELETE FROM resumes WHERE id = ?", (resume_id,))
    if not conn.execute("SELECT 1 FROM resumes WHERE is_default = 1").fetchone():
        conn.execute("UPDATE resumes SET is_default = 1 WHERE id = "
                     "(SELECT MIN(id) FROM resumes)")


def default_resume(conn: Conn) -> Row | None:
    return _one(conn, "SELECT * FROM resumes ORDER BY is_default DESC, id LIMIT 1")


# ---------------------------------------------------------- applications ---
APP_SELECT = (
    "SELECT a.*, p.title, p.location, p.remote, p.url, p.apply_url, p.ats_type, "
    "p.external_id, p.requisition_id, p.company_id, p.closed, p.posted_at, "
    "c.name AS company, m.score, m.id AS match_id "
    "FROM applications a JOIN postings p ON p.id = a.posting_id "
    "JOIN companies c ON c.id = p.company_id "
    "LEFT JOIN matches m ON m.posting_id = p.id")


def _application(row: Row | None) -> Row | None:
    if row:
        row["fill_report"] = json.loads(row.get("fill_report") or "{}")
        row["remote"] = bool(row["remote"])
        row["closed"] = bool(row["closed"])
    return row


def create_application(conn: Conn, posting_id: int, *, state: str = "waiting",
                       manual_reason: str = "", resume: Row | None = None) -> int:
    stamp = now()
    cur = conn.execute(
        "INSERT INTO applications(posting_id, state, manual_reason, resume_id, "
        "resume_variant, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
        (posting_id, state, manual_reason, resume["id"] if resume else None,
         resume["label"] if resume else "", stamp, stamp))
    return cur.lastrowid


def get_application(conn: Conn, application_id: int) -> Row | None:
    return _application(_one(conn, APP_SELECT + " WHERE a.id = ?", (application_id,)))


def application_for_posting(conn: Conn, posting_id: int) -> Row | None:
    return _application(_one(conn, APP_SELECT + " WHERE a.posting_id = ?", (posting_id,)))


def list_applications(conn: Conn, *, submitted: bool) -> list[Row]:
    if submitted:
        sql = APP_SELECT + " WHERE a.state = 'submitted' ORDER BY a.submitted_at DESC"
    else:
        sql = (APP_SELECT + " WHERE a.state != 'submitted' ORDER BY CASE a.state "
               "WHEN 'paused' THEN 0 WHEN 'filling' THEN 1 WHEN 'waiting' THEN 2 "
               "ELSE 3 END, m.score DESC, a.created_at")
    return [_application(r) for r in _all(conn, sql)]


def update_application(conn: Conn, application_id: int, fields: dict) -> None:
    fields = dict(fields)
    if "fill_report" in fields:
        fields["fill_report"] = json.dumps(fields["fill_report"] or {})
    fields["updated_at"] = now()
    _update(conn, "applications", application_id, fields,
            {"state", "status", "resume_id", "resume_variant", "submitted_at",
             "screenshot_path", "notes", "manual_reason", "fill_report", "updated_at"})


def delete_application(conn: Conn, application_id: int) -> None:
    conn.execute("DELETE FROM applications WHERE id = ?", (application_id,))


def find_duplicate(conn: Conn, posting: Row) -> Row | None:
    """Another application at the same company for the same requisition. A
    repost under a new posting id keeps its requisition id, so both are checked."""
    req = posting.get("requisition_id") or ""
    if req:
        # An id shared by many postings is a placeholder, not a requisition.
        shared = conn.execute(
            "SELECT COUNT(*) FROM postings WHERE company_id = ? AND requisition_id = ?",
            (posting["company_id"], req)).fetchone()[0]
        if shared > 4:
            req = ""
    return _application(_one(
        conn,
        APP_SELECT + " WHERE p.company_id = ? AND p.id != ? AND "
        "(p.external_id = ? OR (? != '' AND p.requisition_id = ?)) "
        "ORDER BY (a.state = 'submitted') DESC LIMIT 1",
        (posting["company_id"], posting["id"], posting["external_id"], req, req)))


def submitted_on(conn: Conn, day: str) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM applications WHERE state = 'submitted' "
        "AND date(submitted_at, 'localtime') = ?", (day,)).fetchone()[0]


def _answer(row: Row) -> Row:
    row["options"] = json.loads(row.get("options") or "[]")
    row["edited"] = bool(row["edited"])
    row["flagged"] = bool(row["flagged"])
    return row


def list_answers(conn: Conn, application_id: int) -> list[Row]:
    return [_answer(r) for r in _all(
        conn, "SELECT * FROM application_answers WHERE application_id = ? "
        "ORDER BY position, id", (application_id,))]


def get_answer(conn: Conn, answer_id: int) -> Row | None:
    r = _one(conn, "SELECT * FROM application_answers WHERE id = ?", (answer_id,))
    return _answer(r) if r else None


ANSWER_COLS = ("field_key", "question", "answer", "source", "edited", "flagged",
               "confidence", "field_type", "category", "status", "note", "options",
               "position")


def add_answer(conn: Conn, application_id: int, a: Row) -> int:
    vals = dict(field_key="", answer="", source="manual", edited=0, flagged=0,
                confidence=None, field_type="text", category="custom",
                status="filled", note="", options=[], position=0)
    vals.update({k: v for k, v in a.items() if k in ANSWER_COLS})
    vals["options"] = json.dumps(vals["options"] or [])
    vals["edited"], vals["flagged"] = int(bool(vals["edited"])), int(bool(vals["flagged"]))
    cur = conn.execute(
        f"INSERT INTO application_answers(application_id, {', '.join(ANSWER_COLS)}) "
        f"VALUES (?{', ?' * len(ANSWER_COLS)})",
        (application_id, *[vals[c] for c in ANSWER_COLS]))
    return cur.lastrowid


def upsert_answer(conn: Conn, application_id: int, a: Row) -> int:
    """Keyed on field_key so a re-scan of the same form updates in place."""
    existing = None
    if a.get("field_key"):
        existing = conn.execute(
            "SELECT id FROM application_answers WHERE application_id = ? "
            "AND field_key = ?", (application_id, a["field_key"])).fetchone()
    if not existing:
        return add_answer(conn, application_id, a)
    update_answer(conn, existing["id"], a)
    return existing["id"]


def update_answer(conn: Conn, answer_id: int, fields: dict) -> None:
    fields = dict(fields)
    if "options" in fields:
        fields["options"] = json.dumps(fields["options"] or [])
    for k in ("edited", "flagged"):
        if k in fields:
            fields[k] = int(bool(fields[k]))
    _update(conn, "application_answers", answer_id, fields, set(ANSWER_COLS))


def delete_answer(conn: Conn, answer_id: int) -> None:
    conn.execute("DELETE FROM application_answers WHERE id = ?", (answer_id,))


# ----------------------------------------------------------- answer bank ---
def _bank(row: Row) -> Row:
    row["embedding"] = json.loads(row.get("embedding") or "[]")
    return row


def list_bank(conn: Conn) -> list[Row]:
    return [_bank(r) for r in _all(
        conn, "SELECT * FROM answer_bank ORDER BY COALESCE(last_used, created_at) DESC")]


def get_bank(conn: Conn, bank_id: int) -> Row | None:
    r = _one(conn, "SELECT * FROM answer_bank WHERE id = ?", (bank_id,))
    return _bank(r) if r else None


def add_bank(conn: Conn, question: str, answer: str, embedding: list[float]) -> int:
    stamp = now()
    cur = conn.execute(
        "INSERT INTO answer_bank(question, answer, embedding, created_at, updated_at) "
        "VALUES (?,?,?,?,?)", (question, answer, json.dumps(embedding), stamp, stamp))
    return cur.lastrowid


def update_bank(conn: Conn, bank_id: int, *, question: str | None = None,
                answer: str | None = None, embedding: list[float] | None = None) -> None:
    fields: dict[str, Any] = {"updated_at": now()}
    if question is not None:
        fields["question"] = question
    if answer is not None:
        fields["answer"] = answer
    if embedding is not None:
        fields["embedding"] = json.dumps(embedding)
    _update(conn, "answer_bank", bank_id, fields,
            {"question", "answer", "embedding", "updated_at"})


def touch_bank(conn: Conn, bank_id: int) -> None:
    conn.execute("UPDATE answer_bank SET uses = uses + 1, last_used = ? WHERE id = ?",
                 (now(), bank_id))


def delete_bank(conn: Conn, bank_id: int) -> None:
    conn.execute("DELETE FROM answer_bank WHERE id = ?", (bank_id,))


# -------------------------------------------------------------- contacts ---
CONTACT_FIELDS = {"name", "company", "title", "profile_url", "relationship_type",
                  "connected_on", "shared_context", "notes"}


def upsert_contact(conn: Conn, c: Row) -> tuple[int, bool]:
    """Dedupe on profile URL when there is one, else on name plus company.
    A re-import refreshes company and title but keeps what you set by hand
    (relationship type, shared context, notes). Returns (id, created)."""
    url = (c.get("profile_url") or "").strip().rstrip("/")
    name = (c.get("name") or "").strip()
    key = company_key(c.get("company") or "")
    row = None
    if url:
        row = conn.execute("SELECT id FROM contacts WHERE profile_url = ?", (url,)).fetchone()
    if row is None:
        row = conn.execute(
            "SELECT id FROM contacts WHERE name = ? COLLATE NOCASE AND company_key = ? "
            "AND (profile_url = '' OR ? = '')", (name, key, url)).fetchone()
    stamp = now()
    if row:
        conn.execute(
            "UPDATE contacts SET company = ?, company_key = ?, title = ?, "
            "profile_url = CASE WHEN ? != '' THEN ? ELSE profile_url END, "
            "connected_on = COALESCE(?, connected_on), updated_at = ? WHERE id = ?",
            (c.get("company") or "", key, c.get("title") or "", url, url,
             c.get("connected_on"), stamp, row["id"]))
        return row["id"], False
    cur = conn.execute(
        "INSERT INTO contacts(name, company, company_key, title, profile_url, "
        "relationship_type, source, connected_on, shared_context, notes, created_at, "
        "updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (name, c.get("company") or "", key, c.get("title") or "", url,
         c.get("relationship_type") or "connection", c.get("source") or "manual",
         c.get("connected_on"), c.get("shared_context") or "", c.get("notes") or "",
         stamp, stamp))
    return cur.lastrowid, True


def get_contact(conn: Conn, contact_id: int) -> Row | None:
    return _one(conn, "SELECT * FROM contacts WHERE id = ?", (contact_id,))


def update_contact(conn: Conn, contact_id: int, fields: dict) -> None:
    fields = {k: v for k, v in fields.items() if k in CONTACT_FIELDS}
    if "company" in fields:
        fields["company_key"] = company_key(fields["company"])
    if "profile_url" in fields:
        fields["profile_url"] = (fields["profile_url"] or "").strip().rstrip("/")
    fields["updated_at"] = now()
    _update(conn, "contacts", contact_id, fields,
            CONTACT_FIELDS | {"company_key", "updated_at"})


def delete_contact(conn: Conn, contact_id: int) -> None:
    conn.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))


def contacts_for_keys(conn: Conn, keys: set[str]) -> list[Row]:
    if not keys:
        return []
    marks = ",".join("?" * len(keys))
    return _all(conn, f"SELECT * FROM contacts WHERE company_key IN ({marks})",
                sorted(keys))


def search_contacts(conn: Conn, query: str = "", limit: int = 200) -> list[Row]:
    if query:
        like = f"%{query}%"
        return _all(conn, "SELECT * FROM contacts WHERE name LIKE ? OR company LIKE ? "
                    "OR title LIKE ? ORDER BY name LIMIT ?", (like, like, like, limit))
    return _all(conn, "SELECT * FROM contacts ORDER BY name LIMIT ?", (limit,))


def contact_counts(conn: Conn) -> dict[str, int]:
    return {r["company_key"]: r["n"] for r in conn.execute(
        "SELECT company_key, COUNT(*) n FROM contacts WHERE company_key != '' "
        "GROUP BY company_key")}


def contact_total(conn: Conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]


# -------------------------------------------------------------- messages ---
MESSAGE_SELECT = (
    "SELECT g.*, k.name AS contact_name, k.company AS contact_company, "
    "k.title AS contact_title, k.profile_url, k.relationship_type, "
    "p.title AS posting_title, pc.name AS posting_company "
    "FROM messages g JOIN contacts k ON k.id = g.contact_id "
    "LEFT JOIN postings p ON p.id = g.posting_id "
    "LEFT JOIN companies pc ON pc.id = p.company_id")


def add_message(conn: Conn, *, contact_id: int, posting_id: int | None, body: str,
                direction: str = "out", kind: str = "initial", source: str = "manual",
                outcome: str | None = None, sent: bool = False) -> int:
    stamp = now()
    cur = conn.execute(
        "INSERT INTO messages(contact_id, posting_id, direction, kind, body, source, "
        "outcome, drafted_at, sent_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (contact_id, posting_id, direction, kind, body, source, outcome, stamp,
         stamp if sent else None))
    return cur.lastrowid


def get_message(conn: Conn, message_id: int) -> Row | None:
    return _one(conn, MESSAGE_SELECT + " WHERE g.id = ?", (message_id,))


def update_message(conn: Conn, message_id: int, fields: dict) -> None:
    _update(conn, "messages", message_id, fields,
            {"body", "source", "sent_at", "outcome"})


def delete_message(conn: Conn, message_id: int) -> None:
    conn.execute("DELETE FROM messages WHERE id = ?", (message_id,))


def messages_for_contacts(conn: Conn, contact_ids: list[int]) -> list[Row]:
    if not contact_ids:
        return []
    marks = ",".join("?" * len(contact_ids))
    return _all(conn, MESSAGE_SELECT + f" WHERE g.contact_id IN ({marks}) "
                "ORDER BY g.drafted_at, g.id", contact_ids)


def message_log(conn: Conn, limit: int = 300) -> list[Row]:
    return _all(conn, MESSAGE_SELECT + " ORDER BY COALESCE(g.sent_at, g.drafted_at) DESC, "
                "g.id DESC LIMIT ?", (limit,))


def open_draft(conn: Conn, contact_id: int, posting_id: int | None, kind: str) -> Row | None:
    return _one(conn, MESSAGE_SELECT + " WHERE g.contact_id = ? AND g.posting_id IS ? "
                "AND g.kind = ? AND g.direction = 'out' AND g.sent_at IS NULL "
                "ORDER BY g.id DESC LIMIT 1", (contact_id, posting_id, kind))


def followup_candidates(conn: Conn, days: int, max_followups: int) -> list[Row]:
    """Contacts whose last sent message is older than `days`, with no reply or
    outcome logged since, and follow-ups still left to send."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    return _all(conn, """
        SELECT k.*, last.id AS last_message_id, last.posting_id, last.sent_at AS last_sent_at,
               last.body AS last_body, p.title AS posting_title, pc.name AS posting_company,
               (SELECT COUNT(*) FROM messages f WHERE f.contact_id = k.id
                  AND f.kind = 'followup' AND f.sent_at IS NOT NULL
                  AND f.posting_id IS last.posting_id) AS followups_sent
        FROM contacts k
        JOIN messages last ON last.id = (
            SELECT id FROM messages s WHERE s.contact_id = k.id AND s.direction = 'out'
              AND s.sent_at IS NOT NULL ORDER BY s.sent_at DESC, s.id DESC LIMIT 1)
        LEFT JOIN postings p ON p.id = last.posting_id
        LEFT JOIN companies pc ON pc.id = p.company_id
        WHERE last.sent_at <= ?
          AND NOT EXISTS (SELECT 1 FROM messages r WHERE r.contact_id = k.id
                            AND r.direction = 'in' AND r.drafted_at >= last.sent_at)
          AND NOT EXISTS (SELECT 1 FROM messages o WHERE o.contact_id = k.id
                            AND o.outcome IS NOT NULL)
          AND (SELECT COUNT(*) FROM messages f WHERE f.contact_id = k.id
                 AND f.kind = 'followup' AND f.sent_at IS NOT NULL
                 AND f.posting_id IS last.posting_id) < ?
        ORDER BY last.sent_at""", (cutoff, max_followups))


# ----------------------------------------------------------------- tasks ---
def _task(row: Row | None) -> Row | None:
    if row:
        row["payload"] = json.loads(row.get("payload") or "{}")
        row["result"] = json.loads(row["result"]) if row.get("result") else None
    return row


def enqueue(conn: Conn, kind: str, payload: dict | None = None,
            dedupe_key: str | None = None) -> tuple[int, bool]:
    """Queue a task. With a dedupe key, an identical task that is still queued
    or running is returned instead of a second copy. Returns (id, created)."""
    if dedupe_key:
        row = conn.execute(
            "SELECT id FROM tasks WHERE dedupe_key = ? AND state IN ('queued','running')",
            (dedupe_key,)).fetchone()
        if row:
            return row["id"], False
    cur = conn.execute(
        "INSERT INTO tasks(kind, payload, dedupe_key, created_at) VALUES (?,?,?,?)",
        (kind, json.dumps(payload or {}), dedupe_key, now()))
    return cur.lastrowid, True


def claim_task(conn: Conn, kinds: Iterable[str]) -> Row | None:
    """Atomically take the oldest queued task of the given kinds. A single
    UPDATE ... RETURNING, so two claimers can never get the same row."""
    kinds = list(kinds)
    marks = ",".join("?" * len(kinds))
    stamp = now()
    row = conn.execute(
        "UPDATE tasks SET state = 'running', started_at = ?, heartbeat = ?, "
        "attempts = attempts + 1 WHERE id = (SELECT id FROM tasks WHERE "
        f"state = 'queued' AND kind IN ({marks}) ORDER BY id LIMIT 1) RETURNING id",
        (stamp, stamp, *kinds)).fetchone()
    conn.commit()
    return get_task(conn, row["id"]) if row else None


def get_task(conn: Conn, task_id: int) -> Row | None:
    return _task(_one(conn, "SELECT * FROM tasks WHERE id = ?", (task_id,)))


def finish_task(conn: Conn, task_id: int, result: Any = None, error: str | None = None,
                state: str | None = None) -> None:
    conn.execute(
        "UPDATE tasks SET state = ?, finished_at = ?, error = ?, result = ? WHERE id = ?",
        (state or ("failed" if error else "done"), now(), error,
         json.dumps(result) if result is not None else None, task_id))


def heartbeat_task(conn: Conn, task_id: int) -> None:
    conn.execute("UPDATE tasks SET heartbeat = ? WHERE id = ?", (now(), task_id))


def active_task(conn: Conn, dedupe_key: str) -> Row | None:
    return _task(_one(conn, "SELECT * FROM tasks WHERE dedupe_key = ? AND state IN "
                      "('queued','running') ORDER BY id DESC LIMIT 1", (dedupe_key,)))


def cancel_tasks(conn: Conn, dedupe_key: str) -> None:
    conn.execute("UPDATE tasks SET state = 'cancelled', finished_at = ? WHERE "
                 "dedupe_key = ? AND state IN ('queued','running')", (now(), dedupe_key))


def recover_tasks(conn: Conn, kinds: Iterable[str]) -> int:
    """After a restart: in-process tasks left 'running' go back on the queue."""
    kinds = list(kinds)
    marks = ",".join("?" * len(kinds))
    cur = conn.execute(f"UPDATE tasks SET state = 'queued', started_at = NULL WHERE "
                       f"state = 'running' AND kind IN ({marks})", kinds)
    return cur.rowcount


def stale_tasks(conn: Conn, kind: str, seconds: int) -> list[Row]:
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat(timespec="seconds")
    return [_task(r) for r in _all(
        conn, "SELECT * FROM tasks WHERE kind = ? AND state = 'running' AND "
        "COALESCE(heartbeat, started_at) < ?", (kind, cutoff))]


def list_tasks(conn: Conn, limit: int = 30) -> list[Row]:
    return [_task(r) for r in _all(
        conn, "SELECT * FROM tasks ORDER BY id DESC LIMIT ?", (limit,))]


def last_task(conn: Conn, kind: str) -> Row | None:
    return _task(_one(conn, "SELECT * FROM tasks WHERE kind = ? AND state IN "
                      "('done','failed') ORDER BY id DESC LIMIT 1", (kind,)))
