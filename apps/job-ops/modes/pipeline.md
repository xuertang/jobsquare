# Mode: pipeline — batch-process pending inbox entries (port of career-ops `pipeline`)

Drain `apps/jobsquare/data/pipeline.md`: evaluate every selected pending entry with the
`match` rubric, annotate results, close dead links. Autonomous — no
mid-run questions; defaults over asks.

## Selection (from `$mode` remainder)

| Arg | Processes |
|-----|-----------|
| (none) | 10 oldest pending |
| `{N}` | N oldest pending |
| `{company}` | all pending for that company |
| `all` | every pending entry (state the count before starting) |
| `pdf` (combinable, e.g. `pipeline 5 pdf`) | additionally generate a CV PDF for every entry scoring F ≥ 4.0 (the "apply" verdict band) |

**Pending** = checkbox with no `x`. Treat any bracket containing `x` —
`[x]`, `[x ]`, `[ x]`, `[X]` — as closed. **Hygiene pass first:** normalize
malformed ticked brackets to `[x]` (report the count; touch nothing else on
those lines). Entries already carrying ` | eval` are skipped unless the arg
names their company explicitly.

`apps/jobsquare/cv.md` missing → stop with the bootstrap instructions from `apps/jobsquare/modes/pdf.md`.

## Per-entry workflow (single pass, no retries)

1. **Fetch JD** (WebFetch the URL) — doubles as liveness: 404 / "no longer
   accepting" / empty body → status `expired`, no evaluation.
2. **Pre-screen gate** — scan mode already screened at queue time, so only
   hard contradictions count: a `deal_breakers` hit from `apps/jobsquare/config/profile.yml`
   in the fetched JD (not just the title) → status `skipped` with reason.
3. **Evaluate** with the full `apps/jobsquare/modes/match.md` rubric (A–E → F, legitimacy
   tier, CV↔JD mapping). **Batch web budget: max 1 WebSearch per entry** —
   spend it on comp only when the JD states none and F would land near a
   verdict boundary.
4. **Write the report**: claim an id with `python apps/jobsquare/agent.py report-num`
   (atomic — safe from parallel workers), then write
   `apps/jobsquare/reports/{NNN}-{company-kebab}-{role-kebab}.md` (match-mode template,
   machine-summary block included).
5. `pdf` flag and F ≥ 4.0 → fill `apps/jobsquare/templates/cv-template.html` per
   `apps/jobsquare/modes/pdf.md`, render via `python apps/jobsquare/agent.py pdf-render`. (Below 4.0 the
   human can still run `/jobsquare pdf` manually — the gate only limits
   automatic generation.)

## Parallelization — single-writer rule

**Scratchpad isolation (mandatory).** Any temp file a worker writes — curl
output, extracted hydration JSON — must live at a path unique to that worker:
`mktemp -d`, or a name containing the job id plus `$$-$RANDOM`. Generic names
(`page.html`, `hydration.json`) in a shared directory get clobbered by a
sibling worker, and the victim then evaluates **someone else's JD at HTTP 200
with no error**. After extracting, assert the JD's own id/title matches the
assigned entry, against the same bytes just extracted — a guard that passed
before the clobber does not hold. Observed 2026-07-15 and again 2026-08-13.

- **3+ selected entries:** launch one worker subagent per entry (≤ 5
  concurrent), prompt = output-language directive + `apps/jobsquare/modes/_shared.md` +
  `apps/jobsquare/modes/_custom.md` (if exists) + `apps/jobsquare/modes/match.md` + the worker protocol
  below + the entry line. Fewer than 3: process inline.
- **Workers never edit `apps/jobsquare/data/pipeline.md`** — concurrent edits corrupt it.
  Workers fetch, evaluate, and write only their own `apps/jobsquare/reports/` (and
  `apps/jobsquare/output/`) files, then return one JSON object as their final message:

  ```json
  {"id": "NNN or null", "url": "…", "company": "…", "role": "…",
   "status": "evaluated|expired|skipped|error",
   "f": 0.0, "legitimacy": "high|caution|suspicious",
   "report": "apps/job-ops/reports/….md", "pdf": "apps/job-ops/output/….pdf or null", "reason": "for non-evaluated"}
  ```

- The **main loop alone** applies results to `apps/jobsquare/data/pipeline.md` after all
  workers return:
  - `evaluated` → append ` | eval {F}/5 {YYYY-MM-DD} #{NNN}` (stays unticked)
  - `expired`  → tick `[x]` + ` | done {YYYY-MM-DD} (expired)`
  - `skipped`  → tick `[x]` + ` | done {YYYY-MM-DD} (pre-screen: {reason})`
  - `error`    → leave the line untouched; list in the summary
  - `expired` + `skipped` also get a line in `apps/jobsquare/data/discard.log`:
    `{ISO-8601}\t{url}\t{reason}` (create the file if missing).

## Summary (terminal, after all edits applied)

```
Pipeline — {n} processed ({remaining} still pending)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
| # | Company | Role | F | Legit | PDF | Next action |
|…  (# = report id; sorted by F desc; next action: "apply now" ≥4.5,
    "apply" ≥4.0, "apply if {reason}" ≥3.5, "skip" <3.5, or
    "expired"/"skipped") |

Reports: apps/jobsquare/reports/ · Discards logged: apps/jobsquare/data/discard.log
→ Top scorer: /jobsquare pdf {company}   (already generated if `pdf` flag was set)
```

One failing entry never aborts the run; it surfaces as `error` in the
summary with its cause.
