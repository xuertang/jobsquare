# jobsquare

The whole job search in one repo: find the roles, decide which are worth it,
tailor the CV, fill the application, prep the interview.

| Part | What it is | Stack |
|------|-----------|-------|
| [`apps/jobsquare/`](apps/job-ops/) | the watcher + Claude agent CLI — polls boards, dedups, ranks, drafts | Python |
| [`apps/gongzuo/`](apps/browser/) | Chrome extension that autofills job applications from a saved profile and tracks them | React + TS + Vite (MV3) |
| [`apps/prep/`](apps/prep/) | interview problems, one folder per problem, each with prompt + runnable solution | TS / Python |

Each part stands alone (own README, own deps); they share a repo because
they're the same workflow. `apps/gongzuo`'s tracker and the root agent's `apply`
mode cover the same step from two directions — extension for live forms, agent
for reasoning about them.

> **Note:** `apps/gongzuo`'s Chrome signing key (`dist.pem`) and packaged `.crx` are
> deliberately **not** in this repo — `.gitignore` blocks `*.pem`/`*.crx`. They
> stay in the original working copy. Anyone holding that key can publish
> updates as your extension.

## Quick start

```bash
# watcher: poll every board once (dry run)
python apps/job-ops/cli.py --dry-run

# agent: scan the new listings, rank, queue
python apps/job-ops/agent.py scan

# extension: build + load apps/browser/dist in chrome://extensions
cd apps/browser && pnpm install && pnpm build

# interview problems (./prep forwards to apps/prep, so no cd)
./prep new codesignal parking-lot   # scaffold a problem from a template
./prep pytest ledger -m level1      # pytest a Python problem (no name runs all)
./prep run wishlist                 # dev server for a frontend problem
./prep                              # list the commands
```

The frontend problems need `cd apps/prep && pnpm install` once before `./prep run`
works; `./prep new` and `./prep pytest` don't depend on it.

Docs per app: [apps/jobsquare/README.md](apps/job-ops/README.md) ·
[apps/gongzuo/README.md](apps/browser/README.md) ·
[apps/prep/README.md](apps/prep/README.md)

The `/jobsquare` Claude skill lives at `.claude/skills/jobsquare` (repo root —
that's where Claude Code discovers it) and drives the agent modes in
`apps/jobsquare/modes/`. The scheduled scrape is `.github/workflows/scrape.yaml`.
An OpenClaw plugin at [apps/job-ops/openclaw](apps/job-ops/openclaw/) exposes
the pipeline's Pending queue (list / report / prepare kit / mark applied) to an
OpenClaw assistant.
