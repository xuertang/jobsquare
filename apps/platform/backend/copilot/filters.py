"""Hard filter: cheap rules that run before any LLM call, so the model only
sees plausible matches. Returns the first rule a posting fails."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from .repo import company_key

LEVELS = ("intern", "entry", "mid", "senior", "lead", "staff", "principal", "management")

_LEVEL_RULES = [
    ("intern", r"\b(intern|interns|internship|co-?op|apprentice(ship)?)\b"),
    ("management", r"\b(manager|director|head of|vp|vice president|chief|president)\b"),
    ("principal", r"\b(principal|distinguished|fellow)\b"),
    ("staff", r"\bstaff\b"),
    ("lead", r"\b(lead|tech lead|team lead)\b"),
    ("senior", r"\b(senior|sr\.?|iii|iv|l5|l6)\b"),
    ("entry", r"\b(new grad(uate)?|university grad(uate)?|early career|entry[- ]level|"
              r"junior|jr\.?|associate|graduate)\b"),
]


def level_of(title: str) -> str:
    """Seniority read off the title. Unmarked titles count as mid."""
    t = title.lower()
    for level, pattern in _LEVEL_RULES:
        if re.search(pattern, t):
            return level
    return "mid"


@lru_cache(maxsize=2048)
def _term(term: str) -> re.Pattern:
    """A term matches as a whole word or phrase, never inside another word,
    so 'US' does not match 'Austin' and 'intern' does not match 'internal'."""
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(term.strip())}(?![A-Za-z0-9])",
                      re.IGNORECASE)


def _any(terms, text: str) -> bool:
    return any(_term(t).search(text) for t in terms if t and t.strip())


_BARE_REMOTE = re.compile(r"\W*(fully\s+|100%\s+)?remote\W*", re.IGNORECASE)


def location_ok(location: str, remote: bool, criteria: dict) -> bool:
    places = criteria.get("locations") or []
    regions = criteria.get("remote_regions") or []
    loc = (location or "").strip()
    if not places and not regions:
        return True
    if _any(places, loc):
        return True
    if not criteria.get("remote_ok", True):
        return False
    if not loc:
        return True                      # unknown location: keep, do not guess
    # A location that is only a region ("United States") reads as remote-eligible.
    region_only = any(_term(r).fullmatch(loc) for r in regions if r.strip())
    if not (remote or region_only):
        return False
    return bool(_BARE_REMOTE.fullmatch(loc)) or _any(regions, loc)


def check(posting: dict, criteria: dict, *, now: datetime | None = None) -> tuple[bool, str]:
    """(passes, failed_rule). failed_rule is '' when the posting passes."""
    title = posting.get("title") or ""
    if company_key(posting.get("company") or "") in {
            company_key(c) for c in criteria.get("excluded_companies") or []}:
        return False, "company"
    include = criteria.get("title_include") or []
    if include and not _any(include, title):
        return False, "title"
    if _any(criteria.get("title_exclude") or [], title):
        return False, "title"
    levels = criteria.get("levels") or []
    if levels and level_of(title) not in levels:
        return False, "level"
    if not location_ok(posting.get("location") or "", bool(posting.get("remote")), criteria):
        return False, "location"
    max_age = criteria.get("max_age_days")
    if max_age and posting.get("posted_at"):
        try:
            posted = datetime.fromisoformat(str(posting["posted_at"]).replace("Z", "+00:00"))
            if posted.tzinfo is None:
                posted = posted.replace(tzinfo=timezone.utc)
            if posted < (now or datetime.now(timezone.utc)) - timedelta(days=float(max_age)):
                return False, "age"
        except ValueError:
            pass                          # unparseable date: keep the posting
    return True, ""
