# Mode: scan — new listings since the last scan (SQLite-backed)

The Python pipeline scrapes portals on its own schedule; **this mode never hits
a job board.** Scan = dump what's new in `apps/jobsquare/jobs.db` since the marker, judge it
against the candidate's preferences, queue the promising ones, advance the
marker.

## Arguments (from `$mode` remainder)

- A posted-at window: `3d`, `7d`, `posted 3`, or "last N days" →
  `--posted-days N` on the dump. Only listings **posted** within the window
  survive; listings with no parseable date are still kept (many sources never
  emit dates) and reported separately.
- `dated-only` → additionally pass `--dated-only` (drop undated listings too).
- No time argument → no posted-at filtering (marker semantics only).

## Workflow

1. **Dump** — run `python apps/jobsquare/agent.py db-new [--posted-days N] [--dated-only]`
   and parse the JSON.
   - `count == 0` → report `No new listings since {since}.` (mention
     `dropped_old`/`undated_dropped` if the window filtered everything) and
     **stop** — leave the marker untouched.
   - `first_run: true` → note in the summary that this covers the last 7 days,
     not "since last scan".
2. **Preferences** — read `apps/jobsquare/config/profile.yml` if present (titles, seniority,
   locations, comp floor, deal-breakers); otherwise derive the preference
   signal from `apps/jobsquare/sources.yaml` `filters:`.
3. **Dedup** — read `apps/jobsquare/data/pipeline.md`; drop any dumped job whose URL already
   appears anywhere in the file.
4. **Judge** the remainder into tiers, using only fields present in the dump —
   do not fetch JD pages here:
   - **STRONG** — title + location + seniority all fit; salary (when known) at
     or above the floor.
   - **MAYBE** — partial fit; state what's off in ≤ 10 words.
   - **SKIP** — fails a hard preference; group by one-phrase reason.
5. **Queue** — append STRONG + MAYBE entries to `## Pending` in
   `apps/jobsquare/data/pipeline.md` per the _shared.md contract (create the file from the
   skeleton if missing). Never introduce a duplicate URL.
6. **Advance the marker** — `python apps/jobsquare/agent.py db-mark "{watermark}"` with the
   exact watermark from step 1, **only after** step 5 succeeded. If anything
   failed, leave the marker so the next scan retries the same window
   (re-runs are safe: step 3 dedupes by URL).
7. `truncated: true` → add `{total_new - count} more queued for the next scan —
   run /jobsquare scan again.`

## Output summary (print after marking)

```
Scan — {YYYY-MM-DD HH:MM} UTC
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Window: {since} → {watermark}{"  (first run: last 7 days)" if first_run}
{if posted_within_days: "Posted window: last {N} days — {dropped_old} older
 dropped, {undated_kept} undated kept{, {undated_dropped} undated dropped}"}
New in DB: {total_new}   Queued: {strong+maybe}   Skipped: {skipped}

STRONG ({n})
  + {company} — {title} [{location}]{ · {salary_range}}
    {url}

MAYBE ({n})
  ~ {company} — {title} [{location}] — {why}
    {url}

SKIPPED ({n}): {reason} ×{count}, {reason} ×{count}, …

→ Queued entries live in apps/jobsquare/data/pipeline.md (pipeline mode is not ported yet —
  open them from there).
```
