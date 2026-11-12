# openclaw-plugin-jobops

OpenClaw tool plugin that lets your assistant work the jobsquare application
queue — `apps/job-ops/data/pipeline.md`'s **Pending** section — from any
OpenClaw channel (WhatsApp, Telegram, TUI, …).

| Tool | What it does |
|------|--------------|
| `jobops_pending` | List waiting positions, best eval score first (`min_score`, `company`, `limit`, `include_done`) |
| `jobops_report` | Read the eval report behind an entry's `#NNN` (rubric, gaps, verdict) |
| `jobops_prepare` | Run the repo's headless agent for one entry: `pdf` (tailored one-page CV), `match`, or `interview-prep`. Slow — drives a full Claude session. Marked `optional`, so allowlist it explicitly. |
| `jobops_fill` | Open the posting in a **visible managed Chrome** and fill the application form from your local apply profile — the browser extension's engine (`apps/browser/src/lib`), injected per-frame over CDP. Fills and stops; the window stays open for you. Also `optional`. |
| `jobops_mark` | Tick an entry and append `\| applied {date}` / `\| skipped {date}` / `\| done {date}` after **you** handled it |

**Boundary:** `jobops_fill` fills and STOPS — nothing here clicks submit,
solves CAPTCHAs, logs in, or invents answers to legal/EEO questions the
profile leaves blank. The loop is: assistant surfaces the queue → prepares the
kit → fills the form → you review + submit in the open window → tell the
assistant → `jobops_mark applied`.

## Apply profile (for `jobops_fill`)

Fill values come from `apps/job-ops/config/apply-profile.json` (gitignored;
same shape as the extension's profile — see
[apply-profile.example.json](apply-profile.example.json)). `resumePath` /
`coverLetterPath` point at local PDFs that get attached to upload fields.
Empty fields are simply not filled — leave work-authorization, EEO, and salary
blank unless you want them auto-answered.

Fills run in a dedicated Chrome profile (`~/.openclaw/jobops-chrome`, never
your main one). ATSes that need an account (Workday…): log in once in that
window; the session persists for future fills.

## Install

```bash
cd apps/job-ops/openclaw
npm install
npm run plugin:build          # tsc + regenerate openclaw.plugin.json
openclaw plugins install --link .
```

`--link` keeps the plugin running from this checkout, so it self-locates the
repo (no config needed). If you install a *copy* instead, set the checkout
path in the plugin config:

```jsonc
// ~/.openclaw/openclaw.json → plugins.entries.jobops.config
{ "repoRoot": "/absolute/path/to/jobsquare" }
```

Optional config: `python` (default `{repoRoot}/.venv/bin/python`, falling back
to `python3`) and `prepareTimeoutMs` (default 900000). `jobops_prepare` spawns
`agent.py`, which runs the `claude` CLI — the gateway's PATH must include it.

## Notes

- `jobops_mark` edits are line-anchored, Pending-scoped, idempotent per
  action, and written atomically (tmp + rename). It never touches the Done
  archive. Avoid marking while a `/jobsquare scan` is mid-rewrite.
- Rebuild after changing `src/`: `npm run plugin:build`, then restart the
  gateway. `dist/` is gitignored — built output lives only on the machine.
- Tests (`npm test`) cover the pipeline.md parser and marking round-trips
  with fixture lines matching the real entry contract.
