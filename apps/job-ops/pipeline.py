"""Orchestration: load config -> fetch -> filter -> dedup -> notify."""
from __future__ import annotations

import asyncio
from pathlib import Path

import yaml

from fetchers import fetch_all
from filters import filter_jobs
from notify import dispatch
from store import Store


def load_config(path: str | Path) -> dict:
    with open(path) as f:
        cfg = yaml.safe_load(f)
    cfg.setdefault("sources", [])
    cfg.setdefault("filters", {})
    cfg.setdefault("db", "jobs.db")
    cfg.setdefault("concurrency", 8)
    # A relative db path means "next to the config file", not "under whatever
    # cwd this ran from" — keeps repo-root invocations working post-monorepo.
    db = Path(cfg["db"])
    if not db.is_absolute():
        cfg["db"] = str(Path(path).resolve().parent / db)
    return cfg


async def run(config_path: str | Path, *, dry_run: bool = False) -> dict:
    cfg = load_config(config_path)
    sources = cfg["sources"]
    print(f"Fetching {len(sources)} source(s)...")

    jobs = await fetch_all(sources, concurrency=cfg["concurrency"])
    print(f"Fetched {len(jobs)} listing(s) total.")

    jobs = filter_jobs(jobs, cfg["filters"])
    print(f"{len(jobs)} match your filters.")

    if dry_run:
        # show what we'd surface without persisting dedup state
        for j in jobs:
            print(f"  • {j.title} [{j.location}] — {j.company}")
        return {"matched": len(jobs), "new": 0, "changed": 0}

    with Store(cfg["db"]) as store:
        new, changed = store.diff(jobs)
        dispatch(new, changed)
        total = store.count()

    print(f"\nDone. {len(new)} new, {len(changed)} updated. "
          f"{total} tracked overall.")
    return {"matched": len(jobs), "new": len(new), "changed": len(changed)}


def run_sync(config_path: str | Path, *, dry_run: bool = False) -> dict:
    return asyncio.run(run(config_path, dry_run=dry_run))