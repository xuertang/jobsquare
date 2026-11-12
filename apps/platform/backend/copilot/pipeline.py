"""The daily job: fetch -> normalize -> hard filter -> score -> store, notify.
This is the only part of the app that runs on a schedule."""
from __future__ import annotations

import asyncio
import html
import re
from collections import Counter
from urllib.parse import quote

import httpx

from . import db, filters, llm, normalize, repo, scoring, scraper, seed

FETCH_CONCURRENCY = 8
DESCRIPTION_CONCURRENCY = 6


# ------------------------------------------------------------------ fetch ---
async def _fetch_boards(companies: list[dict]) -> list[tuple[dict, list, str]]:
    """Fetch every board. One board failing never stops the rest; its error is
    returned so Settings can show which companies need attention."""
    mods = scraper.modules()
    sem = asyncio.Semaphore(FETCH_CONCURRENCY)

    async def one(client, company):
        async with sem:
            try:
                jobs = await mods.fetchers.fetch_source(client, scraper.source_for(company))
                return company, jobs, ""
            except Exception as e:  # noqa: BLE001 - recorded per company
                return company, [], f"{type(e).__name__}: {e}"

    async with httpx.AsyncClient(headers={"User-Agent": mods.fetchers.UA},
                                 timeout=mods.fetchers.TIMEOUT,
                                 follow_redirects=True) as client:
        return await asyncio.gather(*(one(client, c) for c in companies))


_TITLE = re.compile(r"<title[^>]*>([^<]{2,80})</title>", re.I)
_NOT_A_NAME = {"jobs", "careers", "not found", "404", "ashby", "lever", "error"}


async def _display_name(client: httpx.AsyncClient, company: dict) -> str | None:
    """The board's own name for the company. Drafted messages say "the role
    at <name>", so a slug like "Janestreet" is not good enough."""
    ats, token = company["ats_type"], quote(company["board_token"], safe="")
    if ats == "greenhouse":
        r = await client.get(f"https://boards-api.greenhouse.io/v1/boards/{token}")
        name = (r.json().get("name") or "") if r.status_code == 200 else ""
    elif ats in ("ashby", "lever"):
        host = "jobs.ashbyhq.com" if ats == "ashby" else "jobs.lever.co"
        r = await client.get(f"https://{host}/{token}")
        m = _TITLE.search(r.text) if r.status_code == 200 else None
        name = re.sub(r"\s+(jobs|careers)\s*$", "", html.unescape(m.group(1)).strip(),
                      flags=re.I) if m else ""
    else:
        return None
    name = name.strip()
    return name if 2 <= len(name) <= 60 and name.lower() not in _NOT_A_NAME else None


async def _resolve_names(companies: list[dict]) -> dict[int, str]:
    mods = scraper.modules()
    sem = asyncio.Semaphore(FETCH_CONCURRENCY)

    async def one(client, c):
        async with sem:
            try:
                return c["id"], await _display_name(client, c)
            except Exception:  # noqa: BLE001 - cosmetic; retried on the next fetch
                return c["id"], None

    async with httpx.AsyncClient(headers={"User-Agent": mods.fetchers.UA},
                                 timeout=mods.fetchers.TIMEOUT,
                                 follow_redirects=True) as client:
        return {cid: name for cid, name in
                await asyncio.gather(*(one(client, c) for c in companies)) if name}


def resolve_names(db_path, companies: list[dict]) -> int:
    """Replace slug-derived names with real ones, once per company. A name
    edited in Settings is never touched: only auto-named rows are candidates."""
    todo = [c for c in companies if c["board_config"].get("_auto_name")
            and c["ats_type"] in ("greenhouse", "ashby", "lever")]
    if not todo:
        return 0
    names = asyncio.run(_resolve_names(todo))
    with db.session(db_path) as conn:
        for c in todo:
            if c["id"] in names:
                cfg = {k: v for k, v in c["board_config"].items() if k != "_auto_name"}
                repo.update_company(conn, c["id"], {"name": names[c["id"]], "board_config": cfg})
                c["name"], c["board_config"] = names[c["id"]], cfg
    return len(names)


def store_fetch(conn, company: dict, jobs: list, error: str) -> dict:
    """Write one board's result. A board that comes back empty, or far smaller
    than last time, is treated as suspect rather than as 'every role closed':
    migrations, truncated pagination and throttles all look like that."""
    if error:
        repo.record_fetch(conn, company["id"], status="failed", error=error)
        return {"status": "failed", "new": 0, "closed": 0}
    rows = {}
    for job in jobs:
        if job.external_id and job.title:
            rows[job.external_id] = normalize.normalize(job)
    count = len(rows)
    if company["board_config"].get("_auto_name") and jobs:
        # SmartRecruiters carries the display name on every posting.
        name = ((jobs[0].raw or {}).get("company") or {}).get("name")
        if isinstance(name, str) and name.strip():
            cfg = {k: v for k, v in company["board_config"].items() if k != "_auto_name"}
            repo.update_company(conn, company["id"], {"name": name.strip(), "board_config": cfg})
    open_before = conn.execute(
        "SELECT COUNT(*) FROM postings WHERE company_id = ? AND closed = 0",
        (company["id"],)).fetchone()[0]
    if count == 0:
        note = ("board returned 0 postings; it had listings before, so it may have "
                "moved" if (company.get("best_count") or 0) > 0 else
                "board returned 0 postings; check the board token")
        repo.record_fetch(conn, company["id"], status="empty", count=0, error=note)
        return {"status": "empty", "new": 0, "closed": 0}
    new_ids = repo.upsert_postings(conn, company["id"], list(rows.values()))
    shrunk = open_before >= 10 and count < 0.4 * open_before
    if shrunk and (company.get("failures") or 0) == 0:
        # First time it looks truncated: keep old postings open and flag it.
        # If the next fetch agrees, the smaller board is accepted.
        repo.record_fetch(conn, company["id"], status="suspect", count=count,
                          error=f"board shrank from {open_before} to {count} postings; "
                                "closures deferred until the next fetch confirms it")
        return {"status": "suspect", "new": len(new_ids), "closed": 0}
    closed = repo.close_missing(conn, company["id"], set(rows))
    repo.record_fetch(conn, company["id"], status="ok", count=count)
    return {"status": "ok", "new": len(new_ids), "closed": closed}


def refilter(conn) -> dict:
    """Apply the hard filter to every open posting and sync match rows."""
    criteria = seed.search_criteria(conn)
    stats: Counter = Counter()
    created = 0
    for posting in repo.open_postings(conn):
        passes, rule = filters.check(posting, criteria)
        stats["passed" if passes else f"rejected_{rule}"] += 1
        created += int(repo.sync_match(conn, posting["id"], passes))
    return {"open_postings": sum(stats.values()), "new_matches": created, **stats}


async def _fetch_descriptions(postings: list[dict]) -> list[tuple[int, str | None, str]]:
    mods = scraper.modules()
    sem = asyncio.Semaphore(DESCRIPTION_CONCURRENCY)

    async def one(client, p):
        async with sem:
            try:
                return p["id"], await normalize.fetch_description(client, p), ""
            except Exception as e:  # noqa: BLE001
                return p["id"], None, f"{type(e).__name__}: {e}"

    async with httpx.AsyncClient(headers={"User-Agent": mods.fetchers.UA},
                                 timeout=mods.fetchers.TIMEOUT,
                                 follow_redirects=True) as client:
        return await asyncio.gather(*(one(client, p) for p in postings))


def fill_descriptions(db_path=None, posting_ids: list[int] | None = None) -> dict:
    """Fetch descriptions for matched postings that lack one. Runs after the
    hard filter, so only plausible matches cost a request."""
    with db.session(db_path) as conn:
        sql = (repo.POSTING_SELECT + " JOIN matches m ON m.posting_id = p.id "
               "WHERE p.description IS NULL AND p.closed = 0 AND m.passes_filter = 1 "
               "AND m.state IN ('new','approved')")
        todo = [repo._posting(dict(r)) for r in conn.execute(sql)]
    if posting_ids is not None:
        todo = [p for p in todo if p["id"] in set(posting_ids)]
    if not todo:
        return {"fetched": 0, "failed": 0}
    results = asyncio.run(_fetch_descriptions(todo))
    fetched = failed = 0
    with db.session(db_path) as conn:
        for pid, text, err in results:
            if err or text is None:
                failed += 1
            else:
                repo.set_description(conn, pid, text)
                fetched += 1
    return {"fetched": fetched, "failed": failed}


def run_fetch(db_path=None, company_ids: list[int] | None = None) -> dict:
    with db.session(db_path) as conn:
        companies = repo.list_companies(conn, active_only=True)
    if company_ids is not None:
        companies = [c for c in companies if c["id"] in set(company_ids)]
    renamed = resolve_names(db_path, companies)
    results = asyncio.run(_fetch_boards(companies)) if companies else []
    totals: Counter = Counter()
    totals["names_resolved"] = renamed
    with db.session(db_path) as conn:
        for company, jobs, error in results:
            out = store_fetch(conn, company, jobs, error)
            totals[out["status"]] += 1
            totals["new_postings"] += out["new"]
            totals["closed_postings"] += out["closed"]
        repo.wake_snoozed(conn)
        filtered = refilter(conn)
    descriptions = fill_descriptions(db_path)
    return {"companies": len(companies), **totals, "filter": filtered,
            "descriptions": descriptions}


# ------------------------------------------------------------------ score ---
def run_score(db_path=None, limit: int | None = None,
              match_ids: list[int] | None = None) -> dict:
    """Score matches that have no score yet, up to the per-run cap."""
    if not llm.available():
        return {"scored": 0, "skipped": "no Claude API credentials; matches stay unscored"}
    with db.session(db_path) as conn:
        settings = seed.app_settings(conn)
        cap = limit or int(settings["max_scores_per_run"])
        todo = repo.unscored_matches(conn, 10_000)
        if match_ids is not None:
            todo = [p for p in todo if p["match_id"] in set(match_ids)]
        remaining = max(0, len(todo) - cap)
        todo = todo[:cap]
        resume = repo.default_resume(conn)
        ctx = scoring.context(seed.load_profile(conn), seed.search_criteria(conn),
                              (resume or {}).get("text", ""))
    if not todo:
        return {"scored": 0, "remaining": 0}
    fill_descriptions(db_path, [p["id"] for p in todo if p.get("description") is None])
    with db.session(db_path) as conn:
        for p in todo:
            fresh = repo.get_posting(conn, p["id"])
            p["description"] = fresh["description"] if fresh else p.get("description")
    try:
        results = scoring.score_many(todo, ctx, int(settings["description_chars"]))
    except llm.LLMUnavailable as e:
        return {"scored": 0, "error": str(e)}
    scored = failed = 0
    from . import config
    with db.session(db_path) as conn:
        for posting, score, error in results:
            if score is None:
                repo.set_score_error(conn, posting["match_id"], error)
                failed += 1
            else:
                repo.set_score(conn, posting["match_id"], score.score, score.rationale,
                               config.MODEL)
                scored += 1
    return {"scored": scored, "failed": failed, "remaining": remaining}
