"""Paths and environment. Everything personal lives under DATA_DIR, which is
gitignored; nothing here reads or stores a credential."""
from __future__ import annotations

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
PLATFORM_DIR = BACKEND_DIR.parent
APPS_DIR = PLATFORM_DIR.parent


def _path(env: str, default: Path) -> Path:
    raw = os.getenv(env)
    return Path(raw).expanduser().resolve() if raw else default


DATA_DIR = _path("COPILOT_DATA_DIR", PLATFORM_DIR / "data")
DB_PATH = _path("COPILOT_DB", DATA_DIR / "copilot.db")
RESUME_DIR = DATA_DIR / "resumes"
SCREENSHOT_DIR = DATA_DIR / "screenshots"
BROWSER_PROFILE_DIR = DATA_DIR / "browser-profile"

# The existing scraper (apps/job-ops): fetchers, models, notify, sources.yaml.
SCRAPER_DIR = _path("COPILOT_SCRAPER_DIR", APPS_DIR / "job-ops")

# The five ATS platforms the design doc puts in scope. Anything else in
# sources.yaml (LinkedIn and the bespoke career sites) is not seeded.
ATS_TYPES = ("greenhouse", "lever", "ashby", "smartrecruiters", "workday")

DASHBOARD_URL = os.getenv("COPILOT_DASHBOARD_URL", "http://localhost:5173").rstrip("/")
MODEL = os.getenv("COPILOT_MODEL", "claude-opus-5-5")
SCHEDULER_ENABLED = os.getenv("COPILOT_SCHEDULER", "1") not in ("0", "false", "no")
CORS_ORIGINS = [o.strip() for o in os.getenv(
    "COPILOT_CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]


def ensure_dirs() -> None:
    for d in (DATA_DIR, RESUME_DIR, SCREENSHOT_DIR):
        d.mkdir(parents=True, exist_ok=True)
