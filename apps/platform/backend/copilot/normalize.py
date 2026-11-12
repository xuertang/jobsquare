"""Scraper Job -> posting row, plus the per-ATS description fetch that runs
only for postings that pass the hard filter."""
from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from urllib.parse import quote

import httpx

_REMOTE = re.compile(r"\bremote\b", re.IGNORECASE)


def is_remote(job) -> bool:
    raw = job.raw or {}
    if job.source == "ashby":
        # isRemote is set on plenty of hybrid roles; workplaceType is the
        # reliable field, so it wins whenever the board sends it.
        workplace = str(raw.get("workplaceType") or "").lower()
        if workplace:
            return workplace == "remote"
        if raw.get("isRemote"):
            return True
    if job.source == "lever" and str(raw.get("workplaceType", "")).lower() == "remote":
        return True
    if job.source == "smartrecruiters" and (raw.get("location") or {}).get("remote"):
        return True
    return bool(_REMOTE.search(f"{job.location} {job.title}"))


def location_of(job) -> str:
    raw = job.raw or {}
    parts = [job.location]
    if job.source == "ashby":
        parts += [(s or {}).get("location", "") for s in raw.get("secondaryLocations") or []]
    seen: list[str] = []
    for p in parts:
        p = (p or "").strip()
        if p and p not in seen:
            seen.append(p)
    return "; ".join(seen)


def apply_url(job) -> str:
    """Where the application form lives, per ATS."""
    raw, url = job.raw or {}, job.url
    if job.source == "greenhouse":
        # absolute_url is often the employer's own careers page, and the
        # hosted board redirects there too (Stripe, Jane Street). The embed
        # endpoint always serves the standard Greenhouse form.
        return ("https://job-boards.greenhouse.io/embed/job_app"
                f"?for={quote(job.company)}&token={job.external_id}")
    if job.source == "lever":
        return raw.get("applyUrl") or (url.rstrip("/") + "/apply")
    if job.source == "ashby":
        return raw.get("applyUrl") or (url.rstrip("/") + "/application")
    if job.source == "smartrecruiters" and raw.get("uuid"):
        ident = (raw.get("company") or {}).get("identifier") or job.company
        return (f"https://jobs.smartrecruiters.com/oneclick-ui/company/{quote(ident)}"
                f"/publication/{raw['uuid']}?dcr_ci={quote(ident)}")
    return url


def requisition_id(job) -> str:
    raw = job.raw or {}
    if job.source == "greenhouse":
        value = str(raw.get("requisition_id") or "").strip()
    elif job.source == "smartrecruiters":
        value = str(raw.get("refNumber") or "").strip()
    elif job.source == "workday":
        value = job.external_id
    else:
        value = ""
    # Some boards put a placeholder in the field ("See Opening ID" on every
    # Stripe posting). A real requisition id has a digit in it.
    return value if any(ch.isdigit() for ch in value) else ""


def description_from_raw(job) -> str | None:
    """Lever and Ashby ship the description in the list payload."""
    raw = job.raw or {}
    if job.source == "lever":
        parts = [raw.get("descriptionPlain") or html_to_text(raw.get("description") or "")]
        for lst in raw.get("lists") or []:
            parts.append(f"{lst.get('text', '')}\n{html_to_text(lst.get('content', ''))}")
        parts.append(raw.get("additionalPlain") or "")
        text = "\n\n".join(p.strip() for p in parts if p and p.strip())
        return text or None
    if job.source == "ashby":
        text = raw.get("descriptionPlain") or html_to_text(raw.get("descriptionHtml") or "")
        return text.strip() or None
    return None


def normalize(job) -> dict:
    dt = job.posted_dt
    return {
        "external_id": job.external_id,
        "requisition_id": requisition_id(job),
        "title": job.title.strip(),
        "location": location_of(job),
        "remote": int(is_remote(job)),
        "department": job.department,
        "employment_type": job.employment_type,
        "salary_range": job.salary_range,
        "url": job.url,
        "apply_url": apply_url(job),
        "ats_type": job.source,
        "posted_at": dt.isoformat(timespec="seconds") if dt else "",
        "description": description_from_raw(job),
    }


# ------------------------------------------------------- description fetch ---
async def fetch_description(client: httpx.AsyncClient, posting: dict) -> str:
    """Fetch the full description for one posting. Raises on HTTP errors so
    the caller can tell a failed fetch from an empty description."""
    ats, token = posting["ats_type"], posting["board_token"]
    cfg = posting.get("board_config") or {}
    if ats == "greenhouse":
        r = await client.get(f"https://boards-api.greenhouse.io/v1/boards/{quote(token)}"
                             f"/jobs/{posting['external_id']}")
        r.raise_for_status()
        return html_to_text(html.unescape(r.json().get("content") or ""))
    if ats == "smartrecruiters":
        r = await client.get(f"https://api.smartrecruiters.com/v1/companies/{quote(token)}"
                             f"/postings/{posting['external_id']}")
        r.raise_for_status()
        sections = ((r.json().get("jobAd") or {}).get("sections") or {})
        parts = [f"{s.get('title', '')}\n{html_to_text(s.get('text', ''))}"
                 for s in sections.values() if isinstance(s, dict) and s.get("text")]
        return "\n\n".join(parts)
    if ats == "workday":
        host, tenant, site = cfg.get("host"), cfg.get("tenant"), cfg.get("site")
        marker = f"/{site}/"
        path = posting["url"].split(marker, 1)[-1] if marker in posting["url"] else ""
        if not (host and tenant and site and path):
            return ""
        r = await client.get(f"https://{host}/wday/cxs/{tenant}/{site}/{path}",
                             headers={"Accept": "application/json"})
        r.raise_for_status()
        info = r.json().get("jobPostingInfo") or {}
        return html_to_text(info.get("jobDescription") or "")
    return ""   # lever and ashby arrive with the list payload


class _Text(HTMLParser):
    BLOCK = {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "tr", "section"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag == "li":
            self.out.append("\n- ")
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        elif tag in self.BLOCK and tag != "li":
            self.out.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def html_to_text(markup: str) -> str:
    if not markup:
        return ""
    p = _Text()
    p.feed(markup)
    text = "".join(p.out).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()
