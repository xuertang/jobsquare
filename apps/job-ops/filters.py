"""Filtering: keep only jobs that match your interests."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Iterable

from models import Job


def _compile(words: Iterable[str]) -> list[re.Pattern]:
    return [re.compile(rf"\b{re.escape(w)}\b", re.IGNORECASE) for w in words if w]


def match(job: Job, *, include: list[str] | None = None,
          exclude: list[str] | None = None,
          locations: list[str] | None = None,
          cutoff: datetime | None = None) -> bool:
    haystack = " ".join((job.title, job.department, job.location))

    if exclude:
        if any(p.search(haystack) for p in _compile(exclude)):
            return False

    if include:
        if not any(p.search(haystack) for p in _compile(include)):
            return False

    if locations:
        loc = job.location.lower()
        if not any(l.lower() in loc for l in locations):
            return False

    if cutoff is not None:
        dt = job.posted_dt
        # Drop only when we can confirm it's older than the cutoff; keep
        # postings whose timestamp we couldn't parse rather than nuke them.
        if dt is not None and dt < cutoff:
            return False

    return True


def filter_jobs(jobs: list[Job], rules: dict) -> list[Job]:
    cutoff = None
    max_age = rules.get("max_age_days")
    if max_age:
        cutoff = datetime.now(timezone.utc) - timedelta(days=float(max_age))
    return [j for j in jobs if match(
        j,
        include=rules.get("include_keywords"),
        exclude=rules.get("exclude_keywords"),
        locations=rules.get("locations"),
        cutoff=cutoff,
    )]