"""Canonical job representation shared across all sources."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_posted_at(value: str) -> datetime | None:
    """Best-effort parse of a source's `posted_at` into an aware UTC datetime.

    Sources disagree on format: Lever sends a unix epoch in *milliseconds*
    (e.g. 1643241332430), others send ISO-8601, and Workday sends prose like
    "Posted 3 Days Ago". Returns None when the value is empty or unparseable.
    """
    if not value:
        return None
    s = str(value).strip()

    # Numeric epoch. Lever uses milliseconds (13 digits); also accept seconds.
    if s.lstrip("-").isdigit():
        n = int(s)
        if abs(n) >= 1_000_000_000_000:   # >= 1e12 -> milliseconds
            n /= 1000
        return datetime.fromtimestamp(n, tz=timezone.utc)

    # ISO-8601. Normalize a trailing "Z" that fromisoformat rejected pre-3.11.
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@dataclass(slots=True)
class Job:
    source: str                # ats type, e.g. "greenhouse"
    company: str               # board/company slug
    external_id: str           # stable id from the source
    title: str
    url: str
    location: str = ""
    department: str = ""
    employment_type: str = ""
    posted_at: str = ""        # source-provided timestamp, best-effort
    salary_range: str = ""     # source-provided comp, best-effort (often blank)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    _STR_FIELDS = ("source", "company", "external_id", "title", "url", "location",
                   "department", "employment_type", "posted_at", "salary_range")

    def __post_init__(self) -> None:
        """Coerce None to "" on every text field.

        ATS payloads routinely carry explicit nulls (`"department": null`), and
        `payload.get("department", "")` yields None for those — the default only
        applies when the KEY is absent. Normalizing here instead of in each
        parser means one null field can never again crash a whole poll:
        filters.match joins these into a haystack, and a single None used to
        abort the run and discard every listing fetched that cycle.
        """
        for f in self._STR_FIELDS:
            if getattr(self, f) is None:
                object.__setattr__(self, f, "")

    # --- identity -------------------------------------------------------
    @property
    def key(self) -> str:
        """Stable primary key used for dedup. Survives title/location edits."""
        return f"{self.source}:{self.company}:{self.external_id}"

    @property
    def posted_dt(self) -> datetime | None:
        """Source `posted_at` as an aware UTC datetime, or None if unparseable."""
        return parse_posted_at(self.posted_at)

    @property
    def content_hash(self) -> str:
        """Detects *material* changes to an existing posting (title/loc/url)."""
        blob = "|".join((self.title, self.location, self.url, self.department))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]

    def to_row(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("raw", None)
        d["key"] = self.key
        d["content_hash"] = self.content_hash
        return d