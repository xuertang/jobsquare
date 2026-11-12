"""Bridge to the existing scraper in apps/job-ops.

The scraper keeps its own fetchers, retry logic and notifier; this module is
the one place the platform touches them. Postings flow one way: scraper Job
objects are normalized and written to the app database through `repo`."""
from __future__ import annotations

import sys
from functools import lru_cache
from types import SimpleNamespace

from . import config


@lru_cache(maxsize=1)
def modules() -> SimpleNamespace:
    """Import fetchers/models/notify from the scraper directory. Appended to
    sys.path (not prepended) so its generic module names never shadow ours."""
    path = str(config.SCRAPER_DIR)
    if not (config.SCRAPER_DIR / "fetchers.py").exists():
        raise RuntimeError(
            f"scraper not found at {path}; set COPILOT_SCRAPER_DIR to apps/job-ops")
    if path not in sys.path:
        sys.path.append(path)
    import fetchers  # type: ignore
    import models  # type: ignore
    import notify  # type: ignore
    return SimpleNamespace(fetchers=fetchers, models=models, notify=notify)


def source_for(company: dict) -> dict:
    """Company row -> the source dict the scraper's fetchers expect."""
    cfg = {k: v for k, v in (company.get("board_config") or {}).items()
           if not k.startswith("_")}            # underscore keys are ours, not the scraper's
    if company["ats_type"] == "workday":
        return {"ats": "workday", "company": cfg.get("company") or company["name"], **cfg}
    return {**cfg, "ats": company["ats_type"], "company": company["board_token"]}


def company_from_source(src: dict) -> dict | None:
    """sources.yaml entry -> company fields, or None when the ATS is out of
    scope (LinkedIn and the bespoke career sites are never seeded)."""
    ats = src.get("ats")
    if ats not in config.ATS_TYPES:
        return None
    extras = {k: v for k, v in src.items() if k not in ("ats", "company")}
    if ats == "workday":
        if not all(src.get(k) for k in ("host", "tenant", "site")):
            return None
        label = src.get("company") or src["tenant"]
        token = f"https://{src['host']}/{src.get('locale', 'en-US')}/{src['site']}"
        return {"name": _pretty(label), "ats_type": ats, "board_token": token,
                "board_config": {**extras, "company": label}}
    if not src.get("company"):
        return None
    # The name is only a prettified slug ("janestreet" -> "Janestreet") until
    # the first fetch replaces it with the board's own display name.
    return {"name": _pretty(src["company"]), "ats_type": ats,
            "board_token": str(src["company"]),
            "board_config": {**extras, "_auto_name": True}}


def _pretty(slug: str) -> str:
    words = str(slug).replace("_", " ").replace("-", " ").split()
    return " ".join(w if any(c.isupper() for c in w) else w.capitalize() for w in words)
