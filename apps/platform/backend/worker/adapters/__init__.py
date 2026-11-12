"""Adapter registry. Workday is deliberately absent: it needs a per-company
account and a multi-step wizard, so the API routes it to the manual queue
and the worker is never handed a Workday posting."""
from __future__ import annotations

from .ashby import Ashby
from .base import Adapter
from .greenhouse import Greenhouse
from .lever import Lever
from .smartrecruiters import SmartRecruiters

ADAPTERS: dict[str, Adapter] = {a.name: a for a in
                                (Greenhouse(), Lever(), Ashby(), SmartRecruiters())}


def adapter_for(ats_type: str) -> Adapter | None:
    return ADAPTERS.get(ats_type)
