"""Async fetchers for common ATS platforms.

Each fetcher hits a public JSON endpoint and normalizes the payload into
`Job` objects. Add a new platform by writing a `parse_*` function and
registering it in `FETCHERS`.

The HTTP client is injectable so the parsing logic is unit-testable against
mocked transports without touching the network.
"""
from __future__ import annotations

import asyncio
import json
import random
import re
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from html import unescape
from typing import Awaitable, Callable, Iterable

import httpx

from models import Job

UA = "jobscraper/1.0 (+personal job-listing watcher)"
TIMEOUT = httpx.Timeout(20.0, connect=10.0)


# --------------------------------------------------------------------------
# retry wrapper: exponential backoff + jitter, retries transient failures
# --------------------------------------------------------------------------
async def _request(client: httpx.AsyncClient, url: str, *, retries: int = 4,
                   method: str = "GET", **kw) -> httpx.Response:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            r = await client.request(method, url, **kw)
            if r.status_code in (429, 500, 502, 503, 504):
                raise httpx.HTTPStatusError("retryable", request=r.request, response=r)
            r.raise_for_status()
            return r
        except (httpx.TransportError, httpx.HTTPStatusError) as e:
            last = e
            if attempt == retries - 1:
                break
            sleep = min(2 ** attempt + random.uniform(0, 0.5), 30)
            await asyncio.sleep(sleep)
    raise RuntimeError(f"failed to fetch {url}: {last}")


async def _get_json(client: httpx.AsyncClient, url: str, **kw) -> dict | list:
    return (await _request(client, url, **kw)).json()


async def _get_text(client: httpx.AsyncClient, url: str, **kw) -> str:
    return (await _request(client, url, **kw)).text


def _balanced_json(text: str, start: int) -> str | None:
    """Slice a balanced, string-aware {...} literal starting at text[start]."""
    depth, i, in_str, esc = 0, start, False, False
    while i < len(text):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        i += 1
    return None


# --------------------------------------------------------------------------
# normalizers — one per ATS. They take (company, payload) -> list[Job]
# --------------------------------------------------------------------------
def parse_greenhouse(company: str, data: dict) -> list[Job]:
    out = []
    for j in data.get("jobs", []):
        out.append(Job(
            source="greenhouse", company=company,
            external_id=str(j["id"]),
            title=j.get("title", ""),
            url=j.get("absolute_url", ""),
            location=(j.get("location") or {}).get("name", ""),
            department=", ".join(d.get("name", "") for d in j.get("departments", [])),
            posted_at=j.get("updated_at", ""),
            raw=j,
        ))
    return out


def parse_lever(company: str, data: list) -> list[Job]:
    out = []
    for j in data:
        cats = j.get("categories") or {}
        out.append(Job(
            source="lever", company=company,
            external_id=str(j["id"]),
            title=j.get("text", ""),
            url=j.get("hostedUrl", ""),
            location=cats.get("location", ""),
            department=cats.get("team", ""),
            employment_type=cats.get("commitment", ""),
            posted_at=str(j.get("createdAt", "")),
            salary_range=_lever_salary(j),
            raw=j,
        ))
    return out


def _lever_salary(j: dict) -> str:
    sr = j.get("salaryRange") or {}
    lo, hi, cur = sr.get("min"), sr.get("max"), sr.get("currency", "")
    if lo and hi:
        fmt = lambda v: f"{v:,}" if isinstance(v, (int, float)) else str(v)
        return f"{cur} {fmt(lo)}–{fmt(hi)}".strip()
    return j.get("salaryDescriptionPlain") or ""


def parse_ashby(company: str, data: dict) -> list[Job]:
    out = []
    for j in data.get("jobs", []):
        if j.get("isListed") is False:
            continue
        out.append(Job(
            source="ashby", company=company,
            external_id=str(j.get("id") or j.get("jobId")),
            title=j.get("title", ""),
            url=j.get("jobUrl") or j.get("applyUrl", ""),
            location=j.get("location", ""),
            department=j.get("department") or j.get("team", ""),
            employment_type=j.get("employmentType", ""),
            posted_at=j.get("publishedAt", ""),
            salary_range=_ashby_salary(j),
            raw=j,
        ))
    return out


def _ashby_salary(j: dict) -> str:
    comp = j.get("compensation") or {}
    return (comp.get("compensationTierSummary")
            or comp.get("scrapeableCompensationSalarySummary") or "")


def parse_ashby_page(company: str, postings: list) -> list[Job]:
    """Postings embedded in jobs.ashbyhq.com/{company} (window.__appData) —
    the fallback for orgs that disabled the posting-api (e.g. whatnot)."""
    out = []
    slug = urllib.parse.quote(company, safe="")
    for j in postings:
        if j.get("isListed") is False:
            continue
        pid = str(j.get("id"))
        out.append(Job(
            source="ashby", company=company,
            external_id=pid,
            title=j.get("title", ""),
            url=f"https://jobs.ashbyhq.com/{slug}/{pid}",
            location=j.get("locationName", ""),
            department=j.get("departmentName") or j.get("teamName", ""),
            employment_type=j.get("employmentType", ""),
            posted_at=j.get("publishedDate", ""),
            salary_range=j.get("compensationTierSummary") or "",
            raw=j,
        ))
    return out


async def fetch_ashby(client: httpx.AsyncClient, source: dict) -> list[Job]:
    """Ashby: posting-api first; a 404 means the org disabled it, so fall
    back to the hosted board page, which embeds postings in __appData."""
    company = source["company"]
    slug = urllib.parse.quote(company, safe="")   # boards like "Superhuman Platform Inc"
    r = await client.get("https://api.ashbyhq.com/posting-api/job-board/"
                         f"{slug}?includeCompensation=true")
    if r.status_code == 200:
        return parse_ashby(company, r.json())
    if r.status_code != 404:
        r.raise_for_status()
    html = await _get_text(client, f"https://jobs.ashbyhq.com/{slug}")
    m = re.search(r"window\.__appData\s*=", html)
    blob = _balanced_json(html, html.find("{", m.end())) if m else None
    if not blob:
        raise RuntimeError(f"ashby: no posting-api and no __appData for {company}")
    postings = ((json.loads(blob).get("jobBoard") or {}).get("jobPostings")) or []
    return parse_ashby_page(company, postings)


def parse_smartrecruiters(company: str, data: dict) -> list[Job]:
    out = []
    for j in data.get("content", []):
        loc = j.get("location") or {}
        loc_str = ", ".join(filter(None, (loc.get("city"), loc.get("region"),
                                          loc.get("country"))))
        out.append(Job(
            source="smartrecruiters", company=company,
            external_id=str(j["id"]),
            title=j.get("name", ""),
            url=f"https://jobs.smartrecruiters.com/{company}/{j['id']}",
            location=loc_str,
            department=(j.get("department") or {}).get("label", ""),
            posted_at=j.get("releasedDate", ""),
            raw=j,
        ))
    return out


def parse_recruitee(company: str, data: dict) -> list[Job]:
    out = []
    for j in data.get("offers", []):
        # location can be a flat string or assembled from city/country
        loc = j.get("location") or ", ".join(
            filter(None, (j.get("city"), j.get("country"))))
        out.append(Job(
            source="recruitee", company=company,
            external_id=str(j["id"]),
            title=j.get("title", ""),
            url=j.get("careers_url") or j.get("careers_apply_url", ""),
            location=loc,
            department=j.get("department", ""),
            employment_type=j.get("employment_type_code") or j.get("kind", ""),
            posted_at=j.get("published_at") or j.get("created_at", ""),
            raw=j,
        ))
    return out


def parse_workable(company: str, data: dict) -> list[Job]:
    out = []
    for j in data.get("jobs", []):
        loc = j.get("location")
        if isinstance(loc, dict):
            loc_str = loc.get("location_str") or ", ".join(filter(None, (
                loc.get("city"), loc.get("region"), loc.get("country"))))
        else:
            loc_str = ", ".join(filter(None, (j.get("city"), j.get("state"),
                                              j.get("country"))))
        out.append(Job(
            source="workable", company=company,
            external_id=str(j.get("shortcode") or j.get("id")),
            title=j.get("title", ""),
            url=j.get("url") or j.get("shortlink") or j.get("application_url", ""),
            location=loc_str,
            department=j.get("department") or "",
            employment_type=j.get("employment_type") or "",
            posted_at=j.get("published_on") or j.get("created_at") or "",
            raw=j,
        ))
    return out


# --------------------------------------------------------------------------
# Google Careers — bespoke, no documented JSON API.
#
# The public results page server-renders each page of listings inline as
#   AF_initDataCallback({key: 'ds:1', ..., data:[[<job>, ...]], sideChannel:{}})
# where each <job> is a positional array. We paginate that page and parse the
# blob. Field indices are positional and undocumented, so every access is
# defensive — a layout shift degrades to skipped fields, not a crash.
# --------------------------------------------------------------------------
def _extract_ds1(html: str) -> list:
    """Return the list of raw job arrays embedded in a careers results page."""
    m = re.search(r"key: 'ds:1'.*?data:(\[.*?\])\s*,\s*sideChannel", html, re.S)
    if not m:  # fallback if the trailing sideChannel key ever moves/disappears
        m = re.search(r"key: 'ds:1'.*?data:(\[.*\])\s*\}\s*\)\s*;", html, re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return []
    return data[0] if data and isinstance(data[0], list) else []


def _ds1_posted_at(job: list) -> str:
    """First available [seconds, nanos] timestamp -> ISO-8601 UTC string.

    Prefers create-time (index 12) over update-time so a re-publish doesn't
    reset the age the recency filter sees.
    """
    for idx in (12, 13, 14):
        cell = job[idx] if len(job) > idx else None
        if cell and isinstance(cell, list) and cell[0]:
            return datetime.fromtimestamp(cell[0], timezone.utc).isoformat(
                timespec="seconds")
    return ""


def parse_google(company: str, jobs_raw: list) -> list[Job]:
    out = []
    for j in jobs_raw:
        if not j or not j[0]:
            continue
        jid = str(j[0])
        locs = "; ".join(
            loc[0] for loc in (j[9] if len(j) > 9 and j[9] else []) if loc and loc[0])
        out.append(Job(
            source="google", company=company,
            external_id=jid,
            title=(j[1] if len(j) > 1 else "") or "",
            url=f"https://www.google.com/about/careers/applications/jobs/results/{jid}",
            location=locs,
            posted_at=_ds1_posted_at(j),
            # ds:1 entries embed full HTML descriptions; keep only a light ref.
            raw={"id": jid, "brand": j[7] if len(j) > 7 else None},
        ))
    return out


# --------------------------------------------------------------------------
# D. E. Shaw — bespoke, no JSON API. The careers page server-renders every open
# position as a card carrying data-job-id + a `.job-display-name` title and a
# `.location`. We parse those cards. All roles render on one page (no paging).
# --------------------------------------------------------------------------
def parse_deshaw(company: str, page: str) -> list[Job]:
    out: list[Job] = []
    seen: set[str] = set()
    for ch in re.split(r'(?=data-job-id=")', page):
        mid = re.search(r'data-job-id="(\d+)"', ch)
        mtitle = re.search(r'class="job-display-name">([^<]+)<', ch)
        if not (mid and mtitle) or mid.group(1) in seen:
            continue
        seen.add(mid.group(1))
        mloc = re.search(r'class="location"[^>]*>([^<]+)<', ch)
        mhref = re.search(r'href="(/careers/[a-z0-9-]+-\d+)"', ch)
        out.append(Job(
            source="deshaw", company=company,
            external_id=mid.group(1),
            title=unescape(mtitle.group(1)).strip(),
            url="https://www.deshaw.com" + (
                mhref.group(1) if mhref else f"/careers/{mid.group(1)}"),
            location=unescape(mloc.group(1)).strip() if mloc else "",
            raw={"id": mid.group(1)},
        ))
    return out


async def fetch_deshaw(client: httpx.AsyncClient, source: dict) -> list[Job]:
    """D. E. Shaw careers. Config: company (label, default "deshaw")."""
    company = source.get("company", "deshaw")
    page = await _get_text(client, "https://www.deshaw.com/careers")
    return parse_deshaw(company, page)


# --------------------------------------------------------------------------
# Atlassian — left Lever (api.lever.co/v0/postings/atlassian now 404s) for
# iCIMS, spread across several regional portals (globalcareers-, careers-
# americas, careers-apac-). atlassian.com/company/careers/all-jobs is an SPA
# shell, but it is backed by one unauthenticated JSON feed that returns the
# WHOLE board in a single GET:
#
#     https://www.atlassian.com/endpoint/careers/listings
#
# It ignores every query param tried (page/limit/offset/category), so there is
# no pagination to drive — one request is the complete list. Sibling endpoints
# (/careers/teams, /locations, /search) all 401.
#
# Per item: id, title, category, locations[], applyUrl, and portalJobPost
# {portalUrl, updatedDate}. Two caveats:
#   * `updatedDate` is a *modified* stamp, not first-published, and it carries
#     no timezone ("2026-07-30 01:00 PM"). Treated as UTC. Recency filtering on
#     Atlassian rows is therefore softer than on sources with a real posted_at.
#   * `compensation` is boilerplate prose with no figures (verified: 0 of 83
#     items carrying the field contain a "$"), so salary_range stays empty.
# --------------------------------------------------------------------------
_ATLASSIAN_LISTINGS = "https://www.atlassian.com/endpoint/careers/listings"


def _atlassian_location(raw: str) -> str:
    """Flatten one verbose iCIMS location string into something readable.

    'San Francisco - United States -   San Francisco, California 94104 United States'
        -> 'San Francisco, California, United States'
    'Remote - Japan - Remote' -> 'Remote - Japan'      'Remote - Remote' -> 'Remote'
    """
    parts = [" ".join(p.split()) for p in str(raw).split(" - ")]
    parts = [p for p in parts if p]
    if not parts:
        return ""
    detail = parts[2] if len(parts) >= 3 else ""
    if detail and detail.lower() != "remote":
        # drop postal codes, then collapse the comma/space soup iCIMS emits
        detail = re.sub(r"\b[A-Z]?\d[\dA-Z-]{2,}\b", " ", detail)
        bits = [b.strip() for b in re.split(r"[,\s]{2,}|,", detail) if b.strip()]
        return ", ".join(dict.fromkeys(bits))
    if parts[0].lower() == "remote":
        region = parts[1] if len(parts) >= 2 else ""
        return f"Remote - {region}" if region and region.lower() != "remote" else "Remote"
    return parts[0]


def _atlassian_posted_at(value: str) -> str:
    """'2026-07-30 01:00 PM' -> ISO-8601 UTC. Empty string if unparseable."""
    v = " ".join(str(value or "").split())
    for fmt in ("%Y-%m-%d %I:%M %p", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(v, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        return dt.isoformat(timespec="seconds")
    return ""


def parse_atlassian(company: str, items: list) -> list[Job]:
    out: list[Job] = []
    seen: set[str] = set()
    for j in items:
        if not isinstance(j, dict):
            continue
        ext = str(j.get("id") or "")
        if not ext or ext in seen:
            continue
        seen.add(ext)
        post = j.get("portalJobPost") or {}
        locs = [_atlassian_location(l) for l in (j.get("locations") or [])]
        out.append(Job(
            source="atlassian", company=company,
            external_id=ext,
            title=(j.get("title") or "").strip(),
            url=post.get("portalUrl") or j.get("applyUrl", ""),
            location="; ".join(dict.fromkeys(l for l in locs if l)),
            department=j.get("category", ""),
            posted_at=_atlassian_posted_at(post.get("updatedDate", "")),
            raw=j,
        ))
    return out


async def fetch_atlassian(client: httpx.AsyncClient, source: dict) -> list[Job]:
    """Atlassian careers feed. Config: company (label, default "atlassian")."""
    company = source.get("company", "atlassian")
    data = await _get_json(client, _ATLASSIAN_LISTINGS,
                           headers={"Accept": "application/json"})
    if not isinstance(data, list):
        raise RuntimeError(
            f"atlassian: expected a JSON list from {_ATLASSIAN_LISTINGS}, "
            f"got {type(data).__name__}")
    return parse_atlassian(company, data)


# --------------------------------------------------------------------------
# Two Sigma — bespoke Avature portal, no JSON API. /careers/OpenRoles server-
# renders job cards and paginates via a `jobOffset` query param (10 per page).
# Each card: a JobDetail anchor (title + id) followed by a `.paragraph_inner-span`
# location inside `.article__header__content__text`.
# --------------------------------------------------------------------------
def parse_twosigma(company: str, page: str) -> list[Job]:
    out: list[Job] = []
    seen: set[str] = set()
    anchors = list(re.finditer(
        r'href="(https://careers\.twosigma\.com/careers/JobDetail/[^"]+/(\d+))">'
        r'\s*([^<]+?)\s*</a>', page))
    for i, m in enumerate(anchors):
        jid = m.group(2)
        if jid in seen:                       # each role renders 3x (layout variants)
            continue
        seen.add(jid)
        # bound the location lookup to this card (up to the next anchor)
        end = anchors[i + 1].start() if i + 1 < len(anchors) else m.end() + 800
        mloc = re.search(
            r'article__header__content__text">\s*<span[^>]*>\s*([^<]+?)\s*</span>',
            page[m.end():end])
        out.append(Job(
            source="twosigma", company=company,
            external_id=jid,
            title=unescape(m.group(3)).strip(),
            url=m.group(1),
            location=unescape(mloc.group(1)).strip() if mloc else "",
            raw={"id": jid},
        ))
    return out


async def fetch_twosigma(client: httpx.AsyncClient, source: dict) -> list[Job]:
    """Two Sigma careers (Avature). Config: company (label, default "twosigma");
    max_pages (pagination cap, default 30; 10 roles per page)."""
    company = source.get("company", "twosigma")
    base = "https://careers.twosigma.com/careers/OpenRoles"
    max_pages = int(source.get("max_pages", 30))

    jobs: list[Job] = []
    seen: set[str] = set()
    for page_n in range(max_pages):
        html = await _get_text(client, base, params={"jobOffset": page_n * 10})
        fresh = [j for j in parse_twosigma(company, html) if j.external_id not in seen]
        if not fresh:
            break
        seen.update(j.external_id for j in fresh)
        jobs.extend(fresh)
    return jobs


# --------------------------------------------------------------------------
# Optiver — bespoke Optimizely/EPiServer site, but it exposes a clean JSON API
# at /en/api/v1/jobs paginated by from/size (server caps size at 16). Each item:
# title, location, domain (department), href. No posted_at or salary.
# --------------------------------------------------------------------------
def parse_optiver(company: str, items: list) -> list[Job]:
    out: list[Job] = []
    for j in items:
        href = j.get("href", "")
        # stable id = the unique slug path (domain/office/title) under /jobs/
        ext = href.strip("/").removeprefix("join-us/jobs/") or href
        out.append(Job(
            source="optiver", company=company,
            external_id=ext,
            title=j.get("title", ""),
            url=("https://www.optiver.com" + href) if href.startswith("/") else href,
            location=j.get("location", ""),
            department=j.get("domain", ""),
            raw=j,
        ))
    return out


async def fetch_optiver(client: httpx.AsyncClient, source: dict) -> list[Job]:
    """Optiver careers JSON API. Config: company (label, default "optiver");
    max_pages (pagination cap, default 40; 16 roles per page)."""
    company = source.get("company", "optiver")
    base = "https://www.optiver.com/en/api/v1/jobs"
    max_pages = int(source.get("max_pages", 40))

    jobs: list[Job] = []
    seen: set[str] = set()
    for page_n in range(max_pages):
        data = await _get_json(client, base, params={"from": page_n * 16, "size": 16},
                               headers={"Accept": "application/json"})
        items = data.get("items") if isinstance(data, dict) else None
        if not items:
            break
        fresh = [j for j in parse_optiver(company, items) if j.external_id not in seen]
        if not fresh:
            break
        seen.update(j.external_id for j in fresh)
        jobs.extend(fresh)
    return jobs


# --------------------------------------------------------------------------
# Apple — bespoke. jobs.apple.com server-renders search results into
# window.__staticRouterHydrationData = JSON.parse("...") (React Router loader
# data), paginated via ?page=N (20/page). Sorted newest-first; postDateInGMT
# gives a real (nanosecond) timestamp. Board is ~6400 roles — cap pages.
# --------------------------------------------------------------------------
def _apple_hydration(html: str) -> dict | None:
    """Decode the JSON.parse("...") hydration blob into a dict, or None."""
    i = html.find("window.__staticRouterHydrationData")
    if i == -1:
        return None
    i = html.find('JSON.parse("', i)
    if i == -1:
        return None
    start = i + len("JSON.parse(")          # at the opening quote
    j = start + 1
    esc = False
    while j < len(html):                     # scan to the closing unescaped quote
        ch = html[j]
        if esc:
            esc = False
        elif ch == "\\":
            esc = True
        elif ch == '"':
            break
        j += 1
    try:
        return json.loads(json.loads(html[start:j + 1]))  # JS-string, then JSON
    except (ValueError, json.JSONDecodeError):
        return None


def _apple_posted_at(value: str) -> str:
    """Apple's postDateInGMT is nanosecond-precision (e.g. ...:03.812668311Z),
    which datetime.fromisoformat rejects. Trim to microseconds + explicit UTC."""
    m = re.match(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(\.\d+)?Z?", value or "")
    return m.group(1) + (m.group(2) or "")[:7] + "+00:00" if m else ""


def parse_apple(company: str, results: list) -> list[Job]:
    out: list[Job] = []
    for j in results:
        pid = str(j.get("positionId") or "")
        # City alone ("Cupertino") won't match country-level location filters —
        # append state/country when present: "Cupertino, United States of America".
        locs = "; ".join(dict.fromkeys(filter(None, (
            ", ".join(p for p in (loc.get("name") or loc.get("city"),
                                  loc.get("stateProvince"),
                                  loc.get("countryName")) if p)
            for loc in (j.get("locations") or [])))))
        out.append(Job(
            source="apple", company=company,
            # `id` is unique per role×location (e.g. "200658020-0836"); a single
            # req posted to N locations yields N results, one per location.
            external_id=str(j.get("id") or pid),
            title=j.get("postingTitle", ""),
            url=(f"https://jobs.apple.com/en-us/details/{pid}/"
                 f"{j.get('transformedPostingTitle', '')}") if pid else "",
            location=locs,
            department=(j.get("team") or {}).get("teamName", ""),
            posted_at=_apple_posted_at(j.get("postDateInGMT", "")),
            raw={"id": j.get("id"), "positionId": pid},
        ))
    return out


async def fetch_apple(client: httpx.AsyncClient, source: dict) -> list[Job]:
    """Apple Jobs. No JSON API — parse the server-rendered hydration blob,
    paginated newest-first via ?page=N. Config: company (label, default "apple");
    query (optional keyword search); location (optional slug, e.g.
    "united-states-USA"); max_pages (default 10; 20 roles per page)."""
    company = source.get("company", "apple")
    base = "https://jobs.apple.com/en-us/search"
    params = {"sort": "newest"}
    if source.get("query"):
        params["search"] = source["query"]
    if source.get("location"):
        params["location"] = source["location"]
    max_pages = int(source.get("max_pages", 10))

    jobs: list[Job] = []
    seen: set[str] = set()
    for page in range(1, max_pages + 1):
        html = await _get_text(client, base, params={**params, "page": page})
        data = _apple_hydration(html) or {}
        results = (((data.get("loaderData") or {}).get("search") or {})
                   .get("searchResults") or [])
        fresh = [j for j in parse_apple(company, results) if j.external_id not in seen]
        if not fresh:
            break
        seen.update(j.external_id for j in fresh)
        jobs.extend(fresh)
    return jobs


# --------------------------------------------------------------------------
# Eightfold (generic) — the platform behind Netflix's board, for any other
# tenant (e.g. Millennium: mlp.eightfold.ai / mlp.com). Real post dates via
# t_create/t_update (unix seconds). Netflix keeps its dedicated fetcher.
# --------------------------------------------------------------------------
def parse_eightfold(company: str, host: str, positions: list) -> list[Job]:
    out: list[Job] = []
    for p in positions:
        pid = str(p.get("id") or "")
        loc = p.get("location") or "; ".join(
            l.replace(",", ", ") for l in (p.get("locations") or []))
        out.append(Job(
            source="eightfold", company=company, external_id=pid,
            title=p.get("name", ""),
            url=p.get("canonicalPositionUrl") or f"https://{host}/careers/job/{pid}",
            location=loc,
            department=p.get("department", ""),
            posted_at=str(p.get("t_update") or p.get("t_create") or ""),
        ))
    return out


async def fetch_eightfold(client: httpx.AsyncClient, source: dict) -> list[Job]:
    """Generic Eightfold tenant. Config: host (mlp.eightfold.ai), domain
    (mlp.com), company (label), query/location (optional), max_pages."""
    host, domain = source["host"], source["domain"]
    company = source.get("company") or host.split(".")[0]
    params = {"domain": domain, "num": 10}
    if source.get("query"):
        params["query"] = source["query"]
    if source.get("location"):
        params["location"] = source["location"]
    max_pages = int(source.get("max_pages", 40))

    jobs: list[Job] = []
    seen: set[str] = set()
    for page in range(max_pages):
        data = await _get_json(client, f"https://{host}/api/apply/v2/jobs",
                               params={**params, "start": page * 10})
        positions = data.get("positions") if isinstance(data, dict) else None
        fresh = [j for j in parse_eightfold(company, host, positions or [])
                 if j.external_id not in seen]
        if not fresh:
            break
        seen.update(j.external_id for j in fresh)
        jobs.extend(fresh)
    return jobs


# --------------------------------------------------------------------------
# ByteDance / TikTok — shared "supplier" search API behind their Next.js
# portals (joinbytedance.com / lifeattiktok.com). POST JSON; the body schema
# is STRICT — any unknown key -> 400 "invalid request" — and ByteDance
# additionally requires the `website-path: en` header. No post dates.
# Recipe recovered via browser network capture (fetch interceptor).
# --------------------------------------------------------------------------
_BD_SITES = {
    "bytedance": {
        "api": "https://jobs.bytedance.com/api/v1/public/supplier/search/job/posts",
        "origin": "https://joinbytedance.com",
        "headers": {"website-path": "en", "accept-language": "en-US"},
        "body": {},
        "job_url": "https://joinbytedance.com/search/{id}",
    },
    "tiktok": {
        "api": "https://api.lifeattiktok.com/api/v1/public/supplier/search/job/posts",
        "origin": "https://lifeattiktok.com",
        "headers": {"portal-channel": "tiktok", "portal-platform": "pc",
                    "website-path": "tiktok"},
        "body": {"portal_type": 4, "tag_id_list": [], "job_function_id_list": [],
                 "storefront_id_list": []},
        "job_url": "https://lifeattiktok.com/search/{id}",
    },
}


def _bd_location(city_info: dict | None) -> str:
    """Walk the city_info parent chain: city -> state -> country."""
    parts: list[str] = []
    node = city_info
    while isinstance(node, dict):
        name = node.get("en_name") or node.get("name")
        if name:
            parts.append(name)
        node = node.get("parent")
    return ", ".join(parts)


def parse_bytedance(company: str, items: list, job_url: str) -> list[Job]:
    return [Job(
        source=company, company=company,
        external_id=str(j.get("id") or ""),
        title=j.get("title", ""),
        url=job_url.format(id=j.get("id")),
        location=_bd_location(j.get("city_info")),
        department=(j.get("job_category") or {}).get("en_name", ""),
        employment_type=(j.get("recruit_type") or {}).get("en_name", ""),
    ) for j in items]


async def fetch_bytedance(client: httpx.AsyncClient, source: dict) -> list[Job]:
    """ByteDance & TikTok portals (ats: bytedance | tiktok). Config: query
    (optional), max_pages (default 25; 20 roles/page). Listings are dateless."""
    ats = source.get("ats", "bytedance")
    site = _BD_SITES[ats]
    company = source.get("company", ats)
    limit = 20
    max_pages = int(source.get("max_pages", 25))
    headers = {**site["headers"], "Origin": site["origin"],
               "Referer": site["origin"] + "/"}

    jobs: list[Job] = []
    seen: set[str] = set()
    for page in range(max_pages):
        body = {"recruitment_id_list": [], "job_category_id_list": [],
                "subject_id_list": [], "location_code_list": [],
                "keyword": source.get("query", ""), "limit": limit,
                "offset": page * limit, **site["body"]}
        r = await _request(client, site["api"], method="POST",
                           json=body, headers=headers)
        payload = r.json()
        data = payload.get("data") or {}
        items = data.get("job_post_list") or []
        fresh = [j for j in parse_bytedance(company, items, site["job_url"])
                 if j.external_id not in seen]
        if not fresh:
            break
        seen.update(j.external_id for j in fresh)
        jobs.extend(fresh)
        if len(jobs) >= int(data.get("count") or 0):
            break
    return jobs


# --------------------------------------------------------------------------
# Phenom (generic) — the POST /widgets "refineSearch" API behind
# careers.cisco.com and many other enterprise career sites. Real post dates.
# Config: company (label), host (e.g. careers.cisco.com), locale (default
# en_global), query, max_pages. NOTE: some Phenom tenants front a Workday
# instance — applyUrl often deep-links there.
# --------------------------------------------------------------------------
def parse_phenom(company: str, items: list) -> list[Job]:
    return [Job(
        source="phenom", company=company,
        external_id=str(j.get("jobId") or j.get("jobSeqNo")),
        title=j.get("title", ""),
        url=j.get("applyUrl") or j.get("jobUrl", ""),
        location=j.get("cityStateCountry") or ", ".join(
            filter(None, (j.get("city"), j.get("state"), j.get("country")))),
        department=j.get("category", ""),
        posted_at=j.get("postedDate") or j.get("dateCreated", ""),
        raw={"jobId": j.get("jobId")},
    ) for j in items]


async def fetch_phenom(client: httpx.AsyncClient, source: dict) -> list[Job]:
    host = source["host"]
    company = source.get("company") or host.split(".")[-2]
    locale = source.get("locale", "en_global")
    size = 10
    max_pages = int(source.get("max_pages", 40))

    jobs: list[Job] = []
    seen: set[str] = set()
    for page in range(max_pages):
        body = {"lang": locale, "deviceType": "desktop", "country": "global",
                "pageName": "search-results", "ddoKey": "refineSearch",
                "sortBy": "Most recent", "subsearch": "", "from": page * size,
                "jobs": True, "counts": True,
                "all_fields": ["category", "country", "state", "city"],
                "size": size, "clearAll": False, "jdsource": "facets",
                "isSliderEnable": False, "pageId": "page10",
                "siteType": "external", "keywords": source.get("query", ""),
                "global": True, "selected_fields": {}, "locationData": {}}
        r = await _request(client, f"https://{host}/widgets", method="POST",
                           json=body, headers={"Origin": f"https://{host}",
                                               "Referer": f"https://{host}/"})
        rs = r.json().get("refineSearch") or {}
        total = int(rs.get("totalHits") or 0)
        items = (rs.get("data") or {}).get("jobs") or []
        fresh = [j for j in parse_phenom(company, items) if j.external_id not in seen]
        if not fresh:
            break
        seen.update(j.external_id for j in fresh)
        jobs.extend(fresh)
        if len(jobs) >= total:
            break
    return jobs


# --------------------------------------------------------------------------
# endpoint builders + registry
# --------------------------------------------------------------------------
def _greenhouse_url(c: str) -> tuple[str, str]:
    return "GET", f"https://boards-api.greenhouse.io/v1/boards/{c}/jobs?content=false"

def _lever_url(c: str) -> tuple[str, str]:
    return "GET", f"https://api.lever.co/v0/postings/{c}?mode=json"

# (ashby is fetched by fetch_ashby above — posting-api with hosted-page fallback)

def _smartrecruiters_url(c: str) -> tuple[str, str]:
    return "GET", f"https://api.smartrecruiters.com/v1/companies/{c}/postings?limit=100"


async def fetch_smartrecruiters(client: httpx.AsyncClient, source: dict) -> list[Job]:
    """SmartRecruiters postings API, paginated via `offset` (100/page). The API
    caps a page at 100 and reports the true size in `totalFound`, so a
    single-page fetch silently truncates big boards (ServiceNow ~500).
    Config: company (the slug in jobs.smartrecruiters.com/<company>);
    max_pages (default 20 => 2000 postings)."""
    company = source["company"]
    max_pages = int(source.get("max_pages", 20))
    base = f"https://api.smartrecruiters.com/v1/companies/{company}/postings"

    jobs: list[Job] = []
    seen: set[str] = set()
    for pg in range(max_pages):
        data = await _get_json(client, base,
                               params={"limit": 100, "offset": pg * 100})
        fresh = [j for j in parse_smartrecruiters(company, data or {})
                 if j.external_id not in seen]
        if not fresh:
            break
        seen.update(j.external_id for j in fresh)
        jobs.extend(fresh)
        total = (data or {}).get("totalFound")
        if isinstance(total, int) and len(jobs) >= total:
            break
    return jobs

def _recruitee_url(c: str) -> tuple[str, str]:
    return "GET", f"https://{c}.recruitee.com/api/offers/"

def _workable_url(c: str) -> tuple[str, str]:
    return "GET", f"https://apply.workable.com/api/v1/widget/accounts/{c}"


# Unified fetcher signature: async (client, source_dict) -> list[Job].
# Simple single-request platforms share `_simple`; Workday brings its own.
SourceFetcher = Callable[[httpx.AsyncClient, dict], Awaitable[list[Job]]]


def _simple(url_builder: Callable[[str], tuple[str, str]],
            parser: Callable[[str, object], list[Job]]) -> SourceFetcher:
    async def _fetch(client: httpx.AsyncClient, source: dict) -> list[Job]:
        company = source["company"]
        method, url = url_builder(company)
        payload = await _get_json(client, url, method=method)
        return parser(company, payload)
    return _fetch


def _workday_posted_at(text: str) -> str:
    """Workday's list payload only exposes display text ("Posted Today",
    "Posted 9 Days Ago"). Convert the unambiguous forms to an ISO date so the
    max-age filter and scan --posted-days can see them; "Posted 30+ Days Ago"
    and anything unrecognized stay raw (treated as undated downstream)."""
    t = text.strip().lower()
    if not t.startswith("posted"):
        return text
    rest = t[len("posted"):].strip()
    today = datetime.now(timezone.utc).date()
    if rest == "today":
        return today.isoformat()
    if rest == "yesterday":
        return (today - timedelta(days=1)).isoformat()
    m = re.fullmatch(r"(\d+)\s+days?\s+ago", rest)
    if m:
        return (today - timedelta(days=int(m.group(1)))).isoformat()
    return text


async def fetch_workday(client: httpx.AsyncClient, source: dict) -> list[Job]:
    """Workday (CXS). Paginated POST to a per-tenant endpoint.

    Required config keys: host, tenant, site. Optional: company (label),
    locale (default en-US), page_size (default 20).

    Derive these from the public career URL, e.g.
      https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite
        host   = nvidia.wd5.myworkdayjobs.com
        tenant = nvidia                      (leftmost host label; CXS path tenant)
        locale = en-US
        site   = NVIDIAExternalCareerSite
    If tenant != leftmost host label for a given employer, set `tenant`
    explicitly (check DevTools > Network for the POST to /wday/cxs/.../jobs).
    """
    host = source["host"]
    tenant = source["tenant"]
    site = source["site"]
    locale = source.get("locale", "en-US")
    company = source.get("company", tenant)
    page_size = int(source.get("page_size", 20))

    cxs = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
    jobs: list[Job] = []
    offset = 0
    total: int | None = None
    while True:
        body = {"appliedFacets": {}, "limit": page_size,
                "offset": offset, "searchText": source.get("query", "")}
        data = await _get_json(client, cxs, method="POST", json=body,
                               headers={"Accept": "application/json"})
        postings = data.get("jobPostings", []) if isinstance(data, dict) else []
        for p in postings:
            ext_path = p.get("externalPath", "")
            # bulletFields[0] is typically the requisition id (stable); fall back to path
            req_id = next(iter(p.get("bulletFields") or []), ext_path)
            jobs.append(Job(
                source="workday", company=company,
                external_id=str(req_id),
                title=p.get("title", ""),
                url=f"https://{host}/{locale}/{site}{ext_path}",
                location=p.get("locationsText", ""),
                posted_at=_workday_posted_at(p.get("postedOn", "")),
                raw=p,
            ))
        # `total` is only populated on the FIRST page by some tenants
        # (salesforce reports 584 then 0); a later 0 must never be read as
        # "we're done" or every board silently truncates at one page.
        reported = data.get("total") if isinstance(data, dict) else None
        if isinstance(reported, int) and reported > 0 and total is None:
            total = reported
        offset += page_size
        if not postings or (total is not None and offset >= total) or offset > 5000:
            break
    return jobs


async def fetch_google(client: httpx.AsyncClient, source: dict) -> list[Job]:
    """Google Careers. No documented JSON API — paginate the public results
    page and parse its server-rendered `ds:1` blob.

    Config: company (label, default "google"). Optional:
      query     server-side search text, e.g. "software engineer". Strongly
                recommended — the global board is thousands of roles.
      location  server-side location filter, e.g. "United States".
      max_pages pagination safety cap (default 20; ~20 roles per page).
    """
    company = source.get("company", "google")
    base = "https://www.google.com/about/careers/applications/jobs/results/"
    params = {}
    if source.get("query"):
        params["q"] = source["query"]
    if source.get("location"):
        params["location"] = source["location"]
    max_pages = int(source.get("max_pages", 20))

    jobs: list[Job] = []
    seen: set[str] = set()
    for page in range(1, max_pages + 1):
        html = await _get_text(client, base, params={**params, "page": page})
        batch = parse_google(company, _extract_ds1(html))
        # Out-of-range pages render empty; stop on the first page with nothing new.
        fresh = [j for j in batch if j.external_id not in seen]
        if not fresh:
            break
        seen.update(j.external_id for j in fresh)
        jobs.extend(fresh)
    return jobs


# --------------------------------------------------------------------------
# Meta — bespoke GraphQL (metacareers.com). A single persisted-query POST
# returns the entire public board (~500 roles, no pagination). The /graphql
# endpoint needs an `lsd` token + `__spin_*` build params scraped from the
# careers page. NOTE: Meta rotates the persisted-query doc_id on redeploys —
# if this fetcher starts returning a graphql error, re-capture the doc_id for
# CareersJobSearchResultsV2DataQuery from the live site's network panel.
# --------------------------------------------------------------------------
_META_DOC_ID = "27129360303422352"  # CareersJobSearchResultsV2DataQuery


def parse_meta(company: str, results: list) -> list[Job]:
    out: list[Job] = []
    seen: set[str] = set()
    for j in results:
        jid = str(j.get("id") or "")
        if not jid or jid in seen:
            continue
        seen.add(jid)
        out.append(Job(
            source="meta", company=company,
            external_id=jid,
            title=j.get("title", ""),
            url=f"https://www.metacareers.com/jobs/{jid}/",
            location="; ".join(j.get("locations") or []),
            department="; ".join(j.get("teams") or []),
            raw={"id": jid},
        ))
    return out


async def fetch_meta(client: httpx.AsyncClient, source: dict) -> list[Job]:
    """Meta Careers GraphQL. One POST returns the whole board. Config: company
    (label, default "meta"); query (optional keyword search); remote_only (bool).
    Scrapes lsd + __spin_* tokens from the careers page each run."""
    company = source.get("company", "meta")
    page = await _get_text(client, "https://www.metacareers.com/jobs")
    tok = lambda p: (re.search(p, page) or [None, ""])[1] if re.search(p, page) else ""
    lsd = tok(r'\["LSD",\[\],\{"token":"([^"]+)"')
    rev = tok(r'"__spin_r":(\d+)')

    variables = {
        "search_input": {
            "q": source.get("query"), "divisions": [], "offices": [], "roles": [],
            "leadership_levels": [], "saved_jobs": [], "saved_searches": [],
            "sub_teams": [], "teams": [], "is_leadership": False,
            "is_remote_only": bool(source.get("remote_only", False)),
            "sort_by_new": True, "results_per_page": None,
        },
        "viewasUserID": None, "isLoggedIn": False,
    }
    body = {
        "lsd": lsd, "doc_id": _META_DOC_ID,
        "fb_api_req_friendly_name": "CareersJobSearchResultsV2DataQuery",
        "variables": json.dumps(variables), "__a": "1", "__comet_req": "1",
        "__rev": rev, "__spin_r": rev,
        "__spin_b": tok(r'"__spin_b":"([^"]+)"'), "__spin_t": tok(r'"__spin_t":(\d+)'),
    }
    text = await _get_text(client, "https://www.metacareers.com/graphql",
                           method="POST", data=body,
                           headers={"X-FB-LSD": lsd,
                                    "content-type": "application/x-www-form-urlencoded"})
    if text.startswith("for (;;);"):
        text = text[9:]
    data = json.loads(text)
    if data.get("errors"):  # surfaces a rotated doc_id as a logged failure
        raise RuntimeError(f"meta graphql: {data['errors'][0].get('message', '?')[:80]}")
    node = (data.get("data") or {}).get("job_search_with_featured_jobs_v2") or {}
    return parse_meta(company, node.get("all_jobs") or [])


# --------------------------------------------------------------------------
# Microsoft — bespoke, but a clean JSON API (Phenom "pcsx" platform). Paginated
# via `start` (10/page). `postedTs` is a real unix-seconds timestamp, so the
# recency filter engages. No tokens/cookies needed.
# --------------------------------------------------------------------------
def parse_microsoft(company: str, positions: list) -> list[Job]:
    out: list[Job] = []
    for j in positions:
        jid = str(j.get("id") or "")
        locs = j.get("standardizedLocations") or j.get("locations") or []
        ts = j.get("postedTs")
        out.append(Job(
            source="microsoft", company=company,
            external_id=jid,
            title=j.get("name", ""),
            # jobs.careers.microsoft.com 301s to the bare site root and drops the
            # id — every such link resolves to an unrelated job. Only this host
            # serves a real job page.
            url=f"https://apply.careers.microsoft.com/careers/job/{jid}" if jid else "",
            location="; ".join(locs),
            department=j.get("department", ""),
            posted_at=(datetime.fromtimestamp(ts, timezone.utc).isoformat()
                       if ts else ""),
            raw={"id": jid, "displayJobId": j.get("displayJobId")},
        ))
    return out


async def fetch_microsoft(client: httpx.AsyncClient, source: dict) -> list[Job]:
    """Microsoft Careers (Phenom pcsx JSON API), sorted newest-first and
    paginated via `start` (10/page). Config: company (label, default
    "microsoft"); query (optional keyword); location (optional); max_pages
    (default 40 — the board is thousands of roles)."""
    company = source.get("company", "microsoft")
    url = "https://apply.careers.microsoft.com/api/pcsx/search"
    base = {"domain": "microsoft.com", "query": source.get("query", ""),
            "location": source.get("location", ""), "sort_by": "timestamp"}
    max_pages = int(source.get("max_pages", 40))

    jobs: list[Job] = []
    seen: set[str] = set()
    for pg in range(max_pages):
        data = await _get_json(client, url, params={**base, "start": pg * 10},
                               headers={"Accept": "application/json"})
        positions = ((data or {}).get("data") or {}).get("positions") or []
        fresh = [j for j in parse_microsoft(company, positions)
                 if j.external_id not in seen]
        if not fresh:
            break
        seen.update(j.external_id for j in fresh)
        jobs.extend(fresh)
    return jobs


# --------------------------------------------------------------------------
# Netflix — bespoke. jobs.netflix.com is just a Contentful marketing site; the
# real ATS is Eightfold at explore.jobs.netflix.net, with a clean JSON API at
# /api/apply/v2/jobs paginated via `start` (server-capped at 10/page). `t_create`
# is a real unix-seconds timestamp, so the recency filter engages.
# --------------------------------------------------------------------------
def parse_netflix(company: str, positions: list) -> list[Job]:
    out: list[Job] = []
    for j in positions:
        jid = str(j.get("id") or "")
        locs = j.get("locations") or ([j["location"]] if j.get("location") else [])
        ts = j.get("t_create") or j.get("t_update")
        out.append(Job(
            source="netflix", company=company,
            external_id=jid,
            title=j.get("name", ""),
            url=f"https://explore.jobs.netflix.net/careers/job/{jid}" if jid else "",
            # raw locations are comma-packed ("City,State,Country") — space them out
            location="; ".join(l.replace(",", ", ") for l in locs),
            department=j.get("department", ""),
            posted_at=(datetime.fromtimestamp(ts, timezone.utc).isoformat()
                       if ts else ""),
            raw={"id": jid, "display_job_id": j.get("display_job_id")},
        ))
    return out


async def fetch_netflix(client: httpx.AsyncClient, source: dict) -> list[Job]:
    """Netflix Careers (Eightfold JSON API). Paginated via start (10/page).
    Config: company (label, default "netflix"); query (optional keyword);
    location (optional); max_pages (default 30)."""
    company = source.get("company", "netflix")
    url = "https://explore.jobs.netflix.net/api/apply/v2/jobs"
    base = {"domain": "netflix.com", "query": source.get("query", ""),
            "location": source.get("location", "")}
    max_pages = int(source.get("max_pages", 30))

    jobs: list[Job] = []
    seen: set[str] = set()
    for pg in range(max_pages):
        data = await _get_json(client, url, params={**base, "start": pg * 10, "num": 10},
                               headers={"Accept": "application/json"})
        positions = (data or {}).get("positions") or []
        fresh = [j for j in parse_netflix(company, positions)
                 if j.external_id not in seen]
        if not fresh:
            break
        seen.update(j.external_id for j in fresh)
        jobs.extend(fresh)
    return jobs


# --------------------------------------------------------------------------
# Amazon — a clean, long-standing public JSON API (amazon.jobs/en/search.json),
# paginated via `offset` (10/page). posted_date is a US-format string
# ("June 26, 2026"), so we normalize it to ISO for the recency filter.
# --------------------------------------------------------------------------
_AMZ_MONTHS = {m: i for i, m in enumerate(
    ("January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"), 1)}


def _amazon_posted_at(value: str) -> str:
    """'June 26, 2026' -> '2026-06-26T00:00:00+00:00' (locale-independent)."""
    try:
        mon, day, year = value.replace(",", "").split()
        return f"{int(year):04d}-{_AMZ_MONTHS[mon]:02d}-{int(day):02d}T00:00:00+00:00"
    except (ValueError, KeyError):
        return ""


def parse_amazon(company: str, jobs_raw: list) -> list[Job]:
    out: list[Job] = []
    for j in jobs_raw:
        jid = str(j.get("id") or j.get("id_icims") or "")
        path = j.get("job_path", "")
        out.append(Job(
            source="amazon", company=company,
            external_id=jid,
            title=(j.get("title") or "").strip(),
            url=("https://www.amazon.jobs" + path) if path else "",
            location=j.get("normalized_location") or j.get("location", ""),
            department=j.get("job_category") or j.get("business_category", ""),
            employment_type=j.get("job_schedule_type", ""),
            posted_at=_amazon_posted_at(j.get("posted_date", "")),
            raw={"id": jid, "id_icims": j.get("id_icims")},
        ))
    return out


async def fetch_amazon(client: httpx.AsyncClient, source: dict) -> list[Job]:
    """Amazon Jobs public JSON API, sorted newest-first, paginated via `offset`
    (10/page). Config: company (label, default "amazon"); query (optional
    base_query); max_pages (default 40 — the board is thousands of roles)."""
    company = source.get("company", "amazon")
    url = "https://www.amazon.jobs/en/search.json"
    base = {"base_query": source.get("query", ""), "sort": "recent", "result_limit": 10}
    max_pages = int(source.get("max_pages", 40))

    jobs: list[Job] = []
    seen: set[str] = set()
    for pg in range(max_pages):
        data = await _get_json(client, url, params={**base, "offset": pg * 10},
                               headers={"Accept": "application/json"})
        jobs_raw = (data or {}).get("jobs") or []
        fresh = [j for j in parse_amazon(company, jobs_raw) if j.external_id not in seen]
        if not fresh:
            break
        seen.update(j.external_id for j in fresh)
        jobs.extend(fresh)
    return jobs


# --------------------------------------------------------------------------
# LinkedIn jobs-guest — the public no-auth endpoint behind linkedin.com's
# "see more jobs" scroll. Returns server-rendered HTML cards, 25/page via
# `start`, scoped to ONE employer with f_C={numeric LinkedIn company id}
# (LinkedIn itself = 1337, Tesla = 15564). Real posted dates in
# time[datetime]. Aggressively rate-limited (429/999 under load): browser UA,
# small max_pages, 1s between pages, and a mid-run 429 keeps partial results
# instead of failing the poll.
# --------------------------------------------------------------------------
_LI_GUEST = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
# The guest endpoint rate-limits per-IP, hard, and the budget is shared by
# EVERY linkedin source in a run. So the throttle state is global too:
#   _LI_LOCK           one request at a time, never `concurrency` in parallel
#   _LI_SPACING        gap between consecutive hits
#   _LI_COOLDOWN_UNTIL a 429 pauses the whole group, not just the source that
#                      hit it — otherwise each remaining source marches into
#                      its own 429 and the back half of the run returns nothing
_LI_LOCK = asyncio.Lock()
_LI_SPACING = 2.5
_LI_BACKOFFS = (20.0, 60.0, 150.0)
_LI_COOLDOWN_UNTIL = 0.0


async def _li_get(client: httpx.AsyncClient, params: dict, attempt: int) -> httpx.Response:
    """One serialized, cooldown-aware GET against the guest endpoint.

    Holding the lock across the wait is deliberate: the point is to stop the
    whole group while the limit recovers. A poll runs every 12h, so minutes of
    patience here are free compared with losing a source's data for the cycle.
    """
    global _LI_COOLDOWN_UNTIL
    async with _LI_LOCK:
        wait = _LI_COOLDOWN_UNTIL - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        r = await client.get(_LI_GUEST, params=params,
                             headers={"User-Agent": _BROWSER_UA,
                                      "Accept-Language": "en-US,en;q=0.9"},
                             timeout=30)
        if r.status_code in (429, 999):
            base = _LI_BACKOFFS[min(attempt, len(_LI_BACKOFFS) - 1)]
            _LI_COOLDOWN_UNTIL = time.monotonic() + base * (1 + random.uniform(0, 0.3))
        else:
            await asyncio.sleep(_LI_SPACING)
        return r
_BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
               "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def parse_linkedin(company: str, page: str) -> list[Job]:
    out: list[Job] = []
    seen: set[str] = set()
    anchors = list(re.finditer(
        r'href="(https://www\.linkedin\.com/jobs/view/[^"?]+?-(\d{6,}))[^"]*"', page))
    for i, m in enumerate(anchors):
        jid = m.group(2)
        if jid in seen:
            continue
        seen.add(jid)
        # bound field lookups to this card (up to the next card's anchor)
        end = anchors[i + 1].start() if i + 1 < len(anchors) else len(page)
        window = page[m.end():end]
        title_m = re.search(r'base-search-card__title[^>]*>\s*([^<]+?)\s*<', window)
        loc_m = re.search(r'job-search-card__location[^>]*>\s*([^<]+?)\s*<', window)
        date_m = re.search(r'datetime="(\d{4}-\d{2}-\d{2})"', window)
        out.append(Job(
            source="linkedin", company=company,
            external_id=jid,
            title=unescape(title_m.group(1)) if title_m else "",
            url=m.group(1),
            location=unescape(loc_m.group(1)) if loc_m else "",
            posted_at=date_m.group(1) if date_m else "",
        ))
    return out


async def fetch_linkedin(client: httpx.AsyncClient, source: dict) -> list[Job]:
    """LinkedIn jobs-guest scoped to a company id. Config: company (label),
    company_id (REQUIRED, the numeric id in linkedin.com/company URLs/f_C),
    query (keywords), max_pages (default 3 => ~30 newest roles). Pages hold 10
    cards (observed 2026-07-31; the endpoint has served 25 in the past — stride
    must match what a page actually returns, so it uses the running count).
    The default is deliberately small: every page spends shared rate-limit
    budget, and the max_age filter discards most of a deep crawl anyway."""
    company = source.get("company", "linkedin")
    cid = source.get("company_id")
    if not cid:
        raise RuntimeError("linkedin: company_id (numeric LinkedIn company id) is required")
    max_pages = int(source.get("max_pages", 3))

    jobs: list[Job] = []
    seen: set[str] = set()
    for pg in range(max_pages):
        params = {"f_C": str(cid), "start": str(len(jobs))}
        if source.get("query"):
            params["keywords"] = source["query"]
        # Retry a throttled page a few times, each attempt waiting out (and
        # extending) the group-wide cooldown. 400 is a real bad request, so it
        # is never retried.
        r = await _li_get(client, params, 0)
        for attempt in range(1, len(_LI_BACKOFFS) + 1):
            if r.status_code not in (429, 999):
                break
            r = await _li_get(client, params, attempt)
        if r.status_code in (400, 429, 999):
            # Rate-limited (the guest endpoint answers 429 with a ~24KB notice
            # page, no job cards). Partial results are kept so a mid-run
            # throttle loses nothing — the next run re-reads the same window.
            # But a source throttled from its FIRST page would otherwise return
            # an empty list, which is indistinguishable from a board with no
            # matching roles; that silent zero is worse than a logged failure,
            # so say so out loud.
            if not jobs:
                raise RuntimeError(
                    f"linkedin: rate-limited (HTTP {r.status_code}) before any "
                    f"results for {company} (f_C={cid}); no data this run")
            break
        r.raise_for_status()
        fresh = [j for j in parse_linkedin(company, r.text) if j.external_id not in seen]
        if not fresh:
            break
        seen.update(j.external_id for j in fresh)
        jobs.extend(fresh)
    return jobs


# --------------------------------------------------------------------------
# Radancy (TMP) attraction sites — jobs.intuit.com and friends. GET
# /search-jobs/results returns JSON whose `results` field is server-rendered
# HTML: <a href="/job/{city}/{slug}/{site}/{posting_id}" data-job-id=...>
# with an <h2> title and a .job-location span per card. First page embeds
# data-total-pages. No post dates anywhere (undated jobs are kept by the
# max_age filter and flagged by scan's --dated-only).
# --------------------------------------------------------------------------
def parse_radancy(company: str, host: str, chunk: str) -> list[Job]:
    out: list[Job] = []
    seen: set[str] = set()
    # Radancy sites may or may not carry a locale prefix on job links:
    # jobs.intuit.com uses /job/..., www.disneycareers.com uses /en/job/... .
    anchors = list(re.finditer(
        r'<a[^>]*href="((?:/[a-z]{2}(?:-[A-Za-z]{2})?)?/job/[^"]+?/(\d+))"', chunk))
    for i, m in enumerate(anchors):
        jid = m.group(2)
        if jid in seen:                # cards can repeat across page modules
            continue
        seen.add(jid)
        end = anchors[i + 1].start() if i + 1 < len(anchors) else len(chunk)
        window = chunk[m.end():end]
        title_m = re.search(r'<h2[^>]*>\s*([^<]+?)\s*</h2>', window)
        loc_m = re.search(r'job-location[^>]*>\s*([^<]+?)\s*<', window)
        out.append(Job(
            source="radancy", company=company,
            external_id=jid,
            title=unescape(title_m.group(1)) if title_m else "",
            url=f"https://{host}{m.group(1)}",
            location=unescape(loc_m.group(1)) if loc_m else "",
        ))
    return out


async def fetch_radancy(client: httpx.AsyncClient, source: dict) -> list[Job]:
    """Radancy search. Config: company (label), host (e.g. jobs.intuit.com),
    query (keywords), max_pages (default 5 => 75 roles). Page 2+ requires the
    full module-name param set AND IsPagination=True or the site returns an
    empty shell."""
    company = source["company"]
    host = source["host"]
    max_pages = int(source.get("max_pages", 5))

    jobs: list[Job] = []
    total_pages = 1
    for pg in range(1, max_pages + 1):
        if pg > total_pages:
            break
        params = {
            "ActiveFacetID": "0", "CurrentPage": str(pg), "RecordsPerPage": "15",
            "Distance": "50", "RadiusUnitType": "0",
            "Keywords": source.get("query", ""), "Location": "",
            "ShowRadius": "False",
            "IsPagination": "True" if pg > 1 else "False",
            "FacetType": "0",
            "SearchResultsModuleName": "Search Results",
            "SearchFiltersModuleName": "Search Filters",
            "SortCriteria": "0", "SortDirection": "1",
            "SearchType": "5", "PostalCode": "", "ResultsType": "0",
        }
        data = await _get_json(client, f"https://{host}/search-jobs/results",
                               params=params,
                               headers={"User-Agent": _BROWSER_UA,
                                        "X-Requested-With": "XMLHttpRequest"})
        chunk = (data or {}).get("results") or ""
        if pg == 1:
            tp = re.search(r'data-total-pages="(\d+)"', chunk)
            total_pages = int(tp.group(1)) if tp else 1
        fresh = [j for j in parse_radancy(company, host, chunk)
                 if j.external_id not in {x.external_id for x in jobs}]
        if not fresh:
            break
        jobs.extend(fresh)
    return jobs


FETCHERS: dict[str, SourceFetcher] = {
    "google":          fetch_google,
    "apple":           fetch_apple,
    "meta":            fetch_meta,
    "microsoft":       fetch_microsoft,
    "netflix":         fetch_netflix,
    "amazon":          fetch_amazon,
    "bytedance":       fetch_bytedance,
    "tiktok":          fetch_bytedance,
    "eightfold":       fetch_eightfold,
    "deshaw":          fetch_deshaw,
    "twosigma":        fetch_twosigma,
    "optiver":         fetch_optiver,
    "atlassian":       fetch_atlassian,
    "greenhouse":      _simple(_greenhouse_url, parse_greenhouse),
    "lever":           _simple(_lever_url, parse_lever),
    "linkedin":        fetch_linkedin,
    "radancy":         fetch_radancy,
    "ashby":           fetch_ashby,
    "phenom":          fetch_phenom,
    "smartrecruiters": fetch_smartrecruiters,
    "recruitee":       _simple(_recruitee_url, parse_recruitee),
    "workable":        _simple(_workable_url, parse_workable),
    "workday":         fetch_workday,
}


async def fetch_source(client: httpx.AsyncClient, source: dict) -> list[Job]:
    ats = source["ats"]
    if ats not in FETCHERS:
        raise ValueError(f"unknown ATS '{ats}'. Known: {sorted(FETCHERS)}")
    return await FETCHERS[ats](client, source)


async def fetch_all(sources: Iterable[dict], *, concurrency: int = 8,
                    client: httpx.AsyncClient | None = None) -> list[Job]:
    """Fetch every configured source concurrently; failures are logged, not fatal."""
    owns_client = client is None
    client = client or httpx.AsyncClient(headers={"User-Agent": UA}, timeout=TIMEOUT,
                                         follow_redirects=True)
    sem = asyncio.Semaphore(concurrency)

    async def one(src: dict) -> list[Job]:
        async with sem:
            try:
                return await fetch_source(client, src)
            except Exception as e:  # noqa: BLE001 - keep the run alive
                print(f"  ! {src['ats']}:{src.get('company', src.get('tenant'))} failed: {e}")
                return []

    try:
        results = await asyncio.gather(*(one(s) for s in sources))
    finally:
        if owns_client:
            await client.aclose()
    return [job for batch in results for job in batch]