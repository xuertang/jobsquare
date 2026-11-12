# Job Search Copilot

A single-user web app that finds matching job postings every day, prepares
referral outreach and applications, and leaves every outbound action to one
click from you. Built from the "Job Search Copilot" design doc (Nov 10, 2026).

**The rule the whole app is built around: nothing is sent or submitted without
you.** The app researches, drafts and fills forms. You send the messages and
press submit.

| Area      | What the app does                                               | What it never does                                   |
| --------- | --------------------------------------------------------------- | ---------------------------------------------------- |
| Fetch     | Daily pull from five ATS APIs, filtered and scored              | Scrape LinkedIn or any board that prohibits it       |
| Referrals | Suggest contacts per posting, draft messages, log what you send | Send a message or a connection request               |
| Apply     | Pre-fill application forms and stop for your review             | Click submit, solve a CAPTCHA, tick a consent box    |
| Tracking  | Matches, apply queue, applications, outreach history            | Multi-user accounts or hosting for others            |

## Layout

```
apps/platform/
  backend/
    copilot/            FastAPI app, SQLite (WAL), scheduler, LLM calls
      repo.py           every SQL statement (the repository layer)
      scraper.py        bridge to the existing fetchers in apps/job-ops
      pipeline.py       fetch -> normalize -> hard filter -> score -> store
      filters.py        hard filter (title, level, location, age, company)
      llm.py            Claude API: scoring, message drafts, custom answers
      referrals.py      contacts import, ranking, search links, drafts, follow-ups
      apply.py          field classification, answer planning, guardrails
      tasks.py          APScheduler plus the DB-backed task table
      routers/          HTTP API (dashboard and worker endpoints)
    worker/             apply worker: Playwright, visible browser, runs on the host
      page.js           in-page field reader (labels, options, values)
      form.py           filling, and the never-submit guard
      adapters/         greenhouse, lever, ashby, smartrecruiters
    tests/              142 tests, fixtures per ATS adapter
  frontend/             React + TypeScript + Vite + TanStack Query dashboard
  docker-compose.yml    API and dashboard in containers, on this machine, no login
  docker-compose.prod.yml   the same on a server: login required, Caddy for HTTPS
  deploy/               deploy.sh, set-password.sh, Caddyfile
  data/                 created on first run; gitignored (see "Your data")
```

## Run it

### Without Docker

```bash
cd apps/platform/backend
uv venv .venv --python 3.12 && uv pip install --python .venv/bin/python -r requirements-dev.txt
.venv/bin/python -m uvicorn copilot.main:app --host 127.0.0.1 --port 8000
```

```bash
cd apps/platform/frontend
npm install && npm run dev        # dashboard at http://localhost:5173
```

After `npm run build` the API serves the built dashboard itself, so
`http://127.0.0.1:8000` is enough and the second process is optional.

### With Docker Compose

```bash
cd apps/platform
docker compose up --build         # dashboard at http://localhost:5173
```

Both ports are published on 127.0.0.1 only. The app has no login by design:
do not expose it to a network.

### On a server

The local setup has no login, so it must never be exposed. For a server there
is a separate Compose file that requires one, and a script that sets it up:

```bash
cd apps/platform
deploy/deploy.sh me@your-server copilot.example.com --migrate-data
```

Before the first run, point the domain's DNS A record at the server and open
ports 80 and 443. The server needs Docker with the Compose plugin, and rsync.

The script syncs the code, writes the server's `.env` (random session secret
and worker token, generated on the server and never printed), asks you for a
dashboard password, optionally copies your local database and resumes up,
builds and starts the stack, waits for HTTPS, and confirms that an anonymous
request is refused. It stops the stack again if that last check fails. Run the
same command later to update; `--migrate-data` is only for the first time.

What changes on a server:

- **Login.** Every API route needs a session (the dashboard, after the
  password) or the worker token (the apply worker). Only a scrypt hash of the
  password is stored. Five wrong guesses from one address lock it out for ten
  minutes. Change the password with `deploy/set-password.sh me@your-server`.
- **HTTPS.** Caddy sits in front, gets and renews the certificate, and is the
  only container with published ports.
- **The worker stays on your machine.** The script writes `.worker.env` here
  with the server's URL and the worker token, and `python -m worker` picks it
  up. Delete that file to go back to a local API.
- **One copy fetches.** After migrating, stop the local stack
  (`docker compose down`), or both will fetch and score on their own schedule.

`deploy/deploy.sh --help` lists the options, including `--set KEY=VALUE` for
the digest channels and the time zone. The Claude API key is not copied
unless you say yes when the script asks; otherwise add `ANTHROPIC_API_KEY` to
`copilot/platform/.env` on the server and run the script again.

### The apply worker (always on the host)

The worker drives a visible browser, so it cannot live in a container.

```bash
cd apps/platform/backend
.venv/bin/python -m playwright install chromium      # once
.venv/bin/python -m worker                           # leave it running
```

It polls the API for fills you launched from the dashboard. Add
`--channel chrome` to use your installed Chrome, `--max-tabs N` to change how
many forms may be open for review at once (default 3). The browser profile is
kept in `data/browser-profile`, so anything you sign in to stays signed in.

### Claude API

Scoring, message drafts and custom-answer drafts call the Claude API. Export
`ANTHROPIC_API_KEY` in the shell that starts the API (or put it in
`apps/platform/.env` for Compose). The key is read from the environment and
never stored.

Without a key the app still works: matches stay unscored, messages are drafted
from templates, and custom questions are left for you.

## First run

1. **Settings, Profile.** Fill it in, or press "Import from job-ops apply
   profile" to copy what you already entered for the job-ops plugin.
2. **Settings, Resumes.** Upload at least one. Its text is what scoring reads.
3. **Settings, Search criteria.** Seeded from the scraper's keyword lists, with
   California plus US-remote geography. Adjust and save.
4. **Fetch now** (sidebar). The company list is seeded from
   `apps/job-ops/sources.yaml` for the five supported ATS platforms.
5. **Outreach, Import LinkedIn connections CSV.** The file comes from LinkedIn's
   own data export (Settings, Data privacy, Get a copy of your data,
   Connections).

After that the fetch runs daily at the time set in Settings (07:30 by default).

## How it works

### Daily fetch and matching

Only this part runs on a schedule.

1. **Fetch.** Greenhouse, Lever, Ashby, SmartRecruiters and Workday, through the
   existing fetchers in `apps/job-ops/fetchers.py`. One board failing never
   stops the rest.
2. **Normalize.** Title, company, location, remote flag, posted date, apply URL,
   ATS type, requisition id. Dedup is `UNIQUE(company, external_id)`.
3. **Hard filter.** Title keywords, level, location or remote, excluded
   companies, age. Cheap rules first, so the model only sees plausible matches.
   Descriptions are fetched only for postings that pass.
4. **Score.** Claude rates fit against your resume and preferences: 0 to 100 and
   a two-line rationale. A posting is scored once; the score is cached on its
   match row. A per-run cap (Settings) bounds the cost.
5. **Store and notify.** New matches go in the daily digest through the existing
   notifier in `apps/job-ops/notify.py`. Digest links open the dashboard.

A board that returns zero postings, or far fewer than last time, is flagged in
Settings rather than treated as "every role closed". Migrations, truncated
pagination and throttles all look like a quiet empty board.

### Referrals

Contacts come from the CSV you import. For a posting, the app lists your
first-degree connections at that company, strongest relationship first, and
generates LinkedIn people-search links (company plus your schools and past
employers) for finding second-degree targets. Those are plain links you open;
the app never requests them.

Drafts follow the contact type: former colleague (direct ask), alumni (shared
school), existing connection (short reintroduction), hiring team member (ask
about the role, no referral request). Each draft is checked against a character
limit; one that runs over is flagged, never silently cut. You copy, send on
LinkedIn, and press **Mark sent**, which sits next to **Copy**. Replies and
outcomes are logged the same way. A sent message with no reply logged after the
wait you set appears under follow-ups with a drafted nudge.

### Assisted apply

| ATS             | Handling                                              | Status in this build                          |
| --------------- | ----------------------------------------------------- | --------------------------------------------- |
| Greenhouse      | Dedicated adapter, embedded form endpoint             | Checked against a live form and a saved snapshot |
| Lever           | Dedicated adapter                                     | Checked against a live form and a saved snapshot |
| Ashby           | Dedicated adapter (React, no form element)            | Checked against a live form and a saved snapshot |
| SmartRecruiters | Adapter with shadow DOM support and multi-step re-scan | Synthetic fixture only (see "Known limits")   |
| Workday         | Manual queue with answers laid out to paste           | By design: per-company accounts and a wizard  |

The flow: approve a match, press **Launch fill**, and the worker opens the form
in its browser. It reads every field, asks the API what goes in each one, fills
them, and stops. The dashboard shows every question with its answer and its
source, and highlights anything drafted by Claude or reused with low
confidence. You correct anything in the browser and submit. The worker notices
the confirmation page, takes a screenshot, and records the answers as they
stood when you pressed submit. Answers you edited or typed are saved to the
answer bank, so the next form with that question is filled from your own words.

Guardrails, in the order they apply:

1. Government ids, passwords and payment fields are never filled.
2. Consent and acknowledgment boxes are never ticked.
3. Self-identification questions are filled only from defaults you saved
   explicitly. Blank means "leave it for me".
4. Factual fields come from the profile store, never from the model.
5. Choice questions with no profile or answer-bank match stay unfilled.
6. Claude drafts free text only, and every draft is flagged for review.
7. A duplicate check on company plus requisition id runs before a form opens.
8. The worker refuses to click anything that could submit, never presses Enter
   in a form, and a page-level guard blocks any submit while it is filling.

## Configuration

| Variable                | Default                    | Purpose                                              |
| ----------------------- | -------------------------- | ---------------------------------------------------- |
| `ANTHROPIC_API_KEY`     | unset                      | Enables scoring and drafting                         |
| `COPILOT_MODEL`         | `claude-opus-5-5`          | Model for all three LLM call sites                   |
| `COPILOT_FALLBACKS`     | `default`                  | Server-side refusal fallback; `off` to disable       |
| `COPILOT_LLM`           | `auto`                     | `off` disables LLM calls; `on` forces them           |
| `COPILOT_DATA_DIR`      | `apps/platform/data`       | Database, resumes, screenshots, browser profile      |
| `COPILOT_SCRAPER_DIR`   | `apps/job-ops`             | Where the existing fetchers and notifier live        |
| `COPILOT_DASHBOARD_URL` | `http://localhost:5173`    | Base URL for digest links                            |
| `COPILOT_SCHEDULER`     | `1`                        | `0` turns the in-process scheduler off               |
| `COPILOT_API`           | `http://127.0.0.1:8000`    | Where the worker finds the API                       |
| `COPILOT_WORKER_TOKEN`  | unset                      | Worker's bearer token for a deployed API             |
| `COPILOT_REQUIRE_AUTH`  | `0`                        | `1` refuses every request without a login (server)   |
| `COPILOT_PASSWORD_HASH` | unset                      | Output of `python -m copilot.auth hash`              |
| `COPILOT_SESSION_SECRET`| unset                      | Signs session cookies; changing it signs everyone out |

Digest channels use the notifier's own variables (`SLACK_WEBHOOK_URL`,
`WEBHOOK_URL`, `SMTP_HOST`, `EMAIL_TO`, and so on). With none set, the digest
prints to the API's console.

Everything else (criteria, fetch time, caps, character limits, follow-up wait)
is edited in the dashboard under Settings.

## Your data

Everything personal lives in `apps/platform/data`: the SQLite database, resume
files, confirmation screenshots and the worker's browser profile. The directory
is gitignored at the repo root and again here. No credentials are stored.

What leaves the machine: requests to the ATS job APIs, and, when a key is set,
Claude API calls. Those carry the posting, your preferences and your resume
text with email addresses and phone numbers stripped. Contacts' details are
limited to first name, title, company and the shared context you typed.

In Docker, only the API container opens the database. The worker talks to the
API over HTTP, so SQLite never has a second process across the bind mount.

On a server the same directory lives at `copilot/platform/data` there, owned
by your ssh user. Nothing backs it up: copy `copilot.db` off the server on
whatever schedule suits you (SQLite's `.backup` command is safe while the app
runs).

## Tests

```bash
cd apps/platform/backend
.venv/bin/python -m pytest
```

142 tests. None of them reaches the network or the Claude API (the LLM is
replaced by a fake that records each request). The browser tests need
`playwright install chromium` and skip themselves without it. They cover one
fixture per ATS adapter, the dropdown widgets, the never-submit guarantees, and
the full loop over real HTTP: approve, fill, pause, edit, submit, record.

Frontend: `npm run typecheck` and `npm run build` in `frontend/`.

## Decisions on the doc's open questions

- **Workday share.** 13 of the 159 seeded boards are Workday. They fetch and
  score like the rest and apply through the manual queue.
- **Scraper database.** Not reused. The app has its own database behind a
  repository layer (`copilot/repo.py`), and reads postings from the scraper's
  fetchers through `copilot/scraper.py`. The scraper and its `jobs.db` are
  untouched, and a later move to Postgres is confined to `repo.py` and `db.py`.
- **Resume variants.** Supported. A variant is picked when its keywords appear
  in the posting title; otherwise the default is used. You can change it per
  application.
- **Scoring.** Ranking only: a score and a two-line rationale. No resume tweak
  suggestions.
- **Recruiter email threads.** Not tracked.
- **Daily application cap.** A setting, off by default. When reached it blocks
  new fills for the day.

## Known limits

- **SmartRecruiters is unverified against the live site.** It returned HTTP 403
  to every headless request, so its form could not be captured. The adapter is
  tested against a hand-built page with the same shape (web components with
  open shadow roots, labels on host elements, a second step that appears
  later). If the live form differs, fields will show as unfilled rather than
  guessed, and a blocked page goes to the manual queue. Expect to adjust
  `worker/adapters/smartrecruiters.py` after the first real run.
- **The saved snapshots are static.** They test field discovery and native
  controls. Dropdown widgets are tested on a hand-written page that behaves
  like react-select, and were checked once against live Greenhouse and Lever
  forms.
- **LLM calls were not exercised against the live API** in this build (no key
  was available). Request shapes are asserted in tests against the installed
  SDK's signatures.
- **Answer matching is lexical.** The answer bank uses a feature-hashing
  embedder: identical and near-identical questions match well, loose
  paraphrases fall through to a Claude draft. `copilot/answers.py` keeps it
  behind an `Embedder` interface so a real embedding model can replace it.
- **Company names** start as the board slug and are replaced with the board's
  display name on the first fetch (Greenhouse, Lever, Ashby, SmartRecruiters).
  Workday names stay as seeded; rename them in Settings. Use the aliases field
  when a company goes by another name on LinkedIn.
