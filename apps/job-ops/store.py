"""SQLite-backed dedup. The store is the source of truth for what's 'fresh'."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from models import Job

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    key           TEXT PRIMARY KEY,
    source        TEXT NOT NULL,
    company       TEXT NOT NULL,
    external_id   TEXT NOT NULL,
    title         TEXT,
    url           TEXT,
    location      TEXT,
    department    TEXT,
    employment_type TEXT,
    posted_at     TEXT,
    salary_range  TEXT,
    content_hash  TEXT,
    first_seen    TEXT NOT NULL,
    last_seen     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company);
CREATE TABLE IF NOT EXISTS meta (
    k TEXT PRIMARY KEY,
    v TEXT NOT NULL
);
"""


class Store:
    def __init__(self, path: str | Path = "jobs.db"):
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        """Additive migrations for DBs created before a column existed."""
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(jobs)")}
        if "salary_range" not in cols:
            self.conn.execute("ALTER TABLE jobs ADD COLUMN salary_range TEXT")

    def close(self) -> None:
        self.conn.close()

    def __enter__(self): return self
    def __exit__(self, *exc): self.close()

    def diff(self, jobs: list[Job]) -> tuple[list[Job], list[Job]]:
        """Return (new_jobs, changed_jobs) and upsert everything seen this run."""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        new, changed = [], []
        cur = self.conn.cursor()
        for job in jobs:
            row = cur.execute("SELECT content_hash FROM jobs WHERE key = ?",
                              (job.key,)).fetchone()
            if row is None:
                new.append(job)
                self._insert(cur, job, now)
            else:
                if row["content_hash"] != job.content_hash:
                    changed.append(job)
                    self._update(cur, job, now)
                else:
                    cur.execute("UPDATE jobs SET last_seen=? WHERE key=?",
                                (now, job.key))
        self.conn.commit()
        return new, changed

    def _insert(self, cur, job: Job, now: str) -> None:
        r = job.to_row()
        cur.execute(
            """INSERT INTO jobs (key, source, company, external_id, title, url,
                 location, department, employment_type, posted_at, salary_range,
                 content_hash, first_seen, last_seen)
               VALUES (:key,:source,:company,:external_id,:title,:url,:location,
                 :department,:employment_type,:posted_at,:salary_range,
                 :content_hash,:now,:now)""",
            {**r, "now": now},
        )

    def _update(self, cur, job: Job, now: str) -> None:
        r = job.to_row()
        cur.execute(
            """UPDATE jobs SET title=:title, url=:url, location=:location,
                 department=:department, employment_type=:employment_type,
                 posted_at=:posted_at, salary_range=:salary_range,
                 content_hash=:content_hash, last_seen=:now
               WHERE key=:key""",
            {**r, "now": now},
        )

    # --- agent-scan support (see agent.py / modes/scan.md) ----------------
    def get_meta(self, key: str) -> str | None:
        row = self.conn.execute("SELECT v FROM meta WHERE k = ?", (key,)).fetchone()
        return row["v"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta (k, v) VALUES (?, ?) "
            "ON CONFLICT(k) DO UPDATE SET v = excluded.v",
            (key, value))
        self.conn.commit()

    def next_seq(self, key: str) -> int:
        """Atomically increment and return the integer counter stored at `key`.

        BEGIN IMMEDIATE takes the write lock before the read, so concurrent
        claimers (parallel pipeline workers) serialize instead of racing.
        """
        cur = self.conn.cursor()
        cur.execute("BEGIN IMMEDIATE")
        row = cur.execute("SELECT v FROM meta WHERE k = ?", (key,)).fetchone()
        n = (int(row["v"]) if row else 0) + 1
        cur.execute("INSERT INTO meta (k, v) VALUES (?, ?) "
                    "ON CONFLICT(k) DO UPDATE SET v = excluded.v",
                    (key, str(n)))
        self.conn.commit()
        return n

    def added_since(self, ts: str) -> list[sqlite3.Row]:
        """Rows first seen strictly after `ts` (ISO UTC), oldest first.

        Plain string comparison is sound: every first_seen is written by
        Store.diff with the same isoformat(timespec="seconds") UTC shape.
        """
        return self.conn.execute(
            "SELECT * FROM jobs WHERE first_seen > ? "
            "ORDER BY first_seen, company, title", (ts,)).fetchall()

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]