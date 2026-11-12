-- Job Search Copilot schema. Eight domain tables from the design doc, the two
-- config tables (criteria, profile), plus resumes and the task table.

CREATE TABLE IF NOT EXISTS companies (
  id            INTEGER PRIMARY KEY,
  name          TEXT NOT NULL,
  ats_type      TEXT NOT NULL CHECK (ats_type IN
                  ('greenhouse','lever','ashby','smartrecruiters','workday')),
  board_token   TEXT NOT NULL,              -- board slug, or the Workday site URL
  board_config  TEXT NOT NULL DEFAULT '{}', -- JSON extras (workday host/tenant/site/query)
  aliases       TEXT NOT NULL DEFAULT '',   -- comma separated, for contact matching
  active        INTEGER NOT NULL DEFAULT 1,
  last_fetch_at TEXT,
  last_status   TEXT,                       -- ok | empty | failed
  last_error    TEXT,
  last_count    INTEGER,
  best_count    INTEGER NOT NULL DEFAULT 0, -- most postings ever seen in one fetch
  failures      INTEGER NOT NULL DEFAULT 0, -- consecutive failed or suspicious fetches
  created_at    TEXT NOT NULL,
  UNIQUE (ats_type, board_token)
);

CREATE TABLE IF NOT EXISTS postings (
  id              INTEGER PRIMARY KEY,
  company_id      INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  external_id     TEXT NOT NULL,
  requisition_id  TEXT NOT NULL DEFAULT '',
  title           TEXT NOT NULL,
  location        TEXT NOT NULL DEFAULT '',
  remote          INTEGER NOT NULL DEFAULT 0,
  department      TEXT NOT NULL DEFAULT '',
  employment_type TEXT NOT NULL DEFAULT '',
  salary_range    TEXT NOT NULL DEFAULT '',
  description     TEXT,                     -- NULL until fetched (after the hard filter)
  url             TEXT NOT NULL DEFAULT '', -- public posting page
  apply_url       TEXT NOT NULL DEFAULT '',
  ats_type        TEXT NOT NULL,
  posted_at       TEXT,
  first_seen      TEXT NOT NULL,
  last_seen       TEXT NOT NULL,
  closed          INTEGER NOT NULL DEFAULT 0,
  closed_at       TEXT,
  UNIQUE (company_id, external_id)
);
CREATE INDEX IF NOT EXISTS postings_company ON postings(company_id, closed);

CREATE TABLE IF NOT EXISTS matches (
  id            INTEGER PRIMARY KEY,
  posting_id    INTEGER NOT NULL UNIQUE REFERENCES postings(id) ON DELETE CASCADE,
  score         INTEGER,                    -- 0-100, NULL until scored
  rationale     TEXT,
  score_model   TEXT,
  scored_at     TEXT,
  score_error   TEXT,
  state         TEXT NOT NULL DEFAULT 'new'
                  CHECK (state IN ('new','approved','dismissed','snoozed')),
  snoozed_until TEXT,
  passes_filter INTEGER NOT NULL DEFAULT 1, -- 0 hides it; the cached score stays
  notified_at   TEXT,
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS matches_state ON matches(state, passes_filter);

CREATE TABLE IF NOT EXISTS resumes (
  id         INTEGER PRIMARY KEY,
  label      TEXT NOT NULL,
  filename   TEXT NOT NULL DEFAULT '',
  path       TEXT NOT NULL DEFAULT '',      -- relative to the data dir
  keywords   TEXT NOT NULL DEFAULT '',      -- comma separated; picks the variant
  text       TEXT NOT NULL DEFAULT '',      -- plain text used for scoring and drafts
  is_default INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS applications (
  id              INTEGER PRIMARY KEY,
  posting_id      INTEGER NOT NULL UNIQUE REFERENCES postings(id) ON DELETE CASCADE,
  state           TEXT NOT NULL DEFAULT 'waiting'
                    CHECK (state IN ('waiting','filling','paused','submitted','needs_manual')),
  status          TEXT NOT NULL DEFAULT 'applied'
                    CHECK (status IN ('applied','screen','onsite','offer','rejected','withdrawn')),
  resume_id       INTEGER REFERENCES resumes(id) ON DELETE SET NULL,
  resume_variant  TEXT NOT NULL DEFAULT '',
  submitted_at    TEXT,
  screenshot_path TEXT,
  notes           TEXT NOT NULL DEFAULT '',
  manual_reason   TEXT NOT NULL DEFAULT '',
  fill_report     TEXT NOT NULL DEFAULT '{}', -- JSON: warnings, captcha, unfilled count
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS application_answers (
  id             INTEGER PRIMARY KEY,
  application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
  field_key      TEXT NOT NULL DEFAULT '',
  question       TEXT NOT NULL,
  answer         TEXT NOT NULL DEFAULT '',
  source         TEXT NOT NULL DEFAULT 'manual'
                   CHECK (source IN ('profile','bank','llm','manual')),
  edited         INTEGER NOT NULL DEFAULT 0,
  flagged        INTEGER NOT NULL DEFAULT 0,  -- LLM drafted or low confidence
  confidence     REAL,
  field_type     TEXT NOT NULL DEFAULT 'text',
  category       TEXT NOT NULL DEFAULT 'custom', -- standard|custom|demographic|consent
  status         TEXT NOT NULL DEFAULT 'filled', -- filled|unfilled|failed
  note           TEXT NOT NULL DEFAULT '',
  options        TEXT NOT NULL DEFAULT '[]',
  position       INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS answers_app ON application_answers(application_id, position);

CREATE TABLE IF NOT EXISTS answer_bank (
  id         INTEGER PRIMARY KEY,
  question   TEXT NOT NULL,                 -- canonical question text
  answer     TEXT NOT NULL,
  embedding  TEXT NOT NULL DEFAULT '[]',    -- JSON vector
  uses       INTEGER NOT NULL DEFAULT 0,
  last_used  TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS contacts (
  id                INTEGER PRIMARY KEY,
  name              TEXT NOT NULL,
  company           TEXT NOT NULL DEFAULT '',
  company_key       TEXT NOT NULL DEFAULT '', -- normalized, for matching
  title             TEXT NOT NULL DEFAULT '',
  profile_url       TEXT NOT NULL DEFAULT '',
  relationship_type TEXT NOT NULL DEFAULT 'connection'
                      CHECK (relationship_type IN
                        ('former_colleague','alumni','connection','hiring_team')),
  source            TEXT NOT NULL DEFAULT 'manual' CHECK (source IN ('export','manual')),
  connected_on      TEXT,
  shared_context    TEXT NOT NULL DEFAULT '',  -- what you share; feeds the draft
  notes             TEXT NOT NULL DEFAULT '',
  created_at        TEXT NOT NULL,
  updated_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS contacts_company ON contacts(company_key);

CREATE TABLE IF NOT EXISTS messages (
  id         INTEGER PRIMARY KEY,
  contact_id INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
  posting_id INTEGER REFERENCES postings(id) ON DELETE SET NULL,
  direction  TEXT NOT NULL DEFAULT 'out' CHECK (direction IN ('out','in')),
  kind       TEXT NOT NULL DEFAULT 'initial' CHECK (kind IN ('initial','followup','reply')),
  body       TEXT NOT NULL DEFAULT '',
  source     TEXT NOT NULL DEFAULT 'manual' CHECK (source IN ('llm','template','manual')),
  outcome    TEXT CHECK (outcome IN ('referred','declined','no_response','replied')),
  channel    TEXT NOT NULL DEFAULT 'linkedin',
  drafted_at TEXT NOT NULL,
  sent_at    TEXT
);
CREATE INDEX IF NOT EXISTS messages_contact ON messages(contact_id, drafted_at);

-- Config tables: one JSON document per key, editable from the dashboard.
CREATE TABLE IF NOT EXISTS criteria (
  key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS profile (
  key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL
);

-- DB-backed task table. APScheduler only enqueues; rows here are the record
-- of what ran, and what a restart has to resume.
CREATE TABLE IF NOT EXISTS tasks (
  id          INTEGER PRIMARY KEY,
  kind        TEXT NOT NULL,                -- fetch|score|digest|followups|fill
  payload     TEXT NOT NULL DEFAULT '{}',
  state       TEXT NOT NULL DEFAULT 'queued'
                CHECK (state IN ('queued','running','done','failed','cancelled')),
  dedupe_key  TEXT,
  attempts    INTEGER NOT NULL DEFAULT 0,
  created_at  TEXT NOT NULL,
  started_at  TEXT,
  finished_at TEXT,
  heartbeat   TEXT,
  error       TEXT,
  result      TEXT
);
CREATE INDEX IF NOT EXISTS tasks_state ON tasks(state, kind, id);
