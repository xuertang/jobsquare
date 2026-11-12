# Mode: interview-prep — company-specific interview intel (port of career-ops `interview-prep`)

Turn a role into a prep document: how their loop actually runs, the questions
each interviewer is likely to ask, and which of the candidate's real stories
answer them. Grounded in `apps/jobsquare/cv.md` and the role's evaluation; researched, never
invented. Alias: `interview/prep`.

## Required inputs

- **`apps/jobsquare/cv.md`** (repo root) — proof points. Missing → bootstrap-stop (see `pdf`).
- **A target**, resolved like `apply`: `#NNN` or a bare number → `apps/jobsquare/reports/{NNN}-*`;
  a company/keyword → the matching `apps/jobsquare/reports/*.md` or `apps/jobsquare/data/pipeline.md` entry;
  a URL → WebFetch it; nothing → ask which role.
- **The evaluation report** if one exists — reuse its archetype, legitimacy
  tier, CV↔JD gaps, and comp read instead of re-deriving them.
- `apps/jobsquare/config/profile.yml`, `apps/jobsquare/modes/_profile.md` (if present) — targets, voice.
- `apps/jobsquare/interview-prep/story-bank.md` (if present) — the candidate's STAR stories.

## Research (bounded)

**≤ 6 WebSearch queries total**, across three lenses. Extract structured facts
with a source per claim:
- **recruiter** — comp range (levels.fyi/Glassdoor), process timeline, screen.
- **hiring manager** — eng blog, recent launches, roadmap, tech priorities.
- **peer/tech** — reported questions & round structure (Glassdoor, Blind,
  LeetCode discuss), difficulty.

Cite every fact or tag it `[inferred from JD]`. **Never fabricate a Glassdoor
stat or a question** — thin data is stated as thin, not filled in.

## Output document — `apps/jobsquare/interview-prep/{company-kebab}-{role-kebab}.md`

```markdown
# Interview Intel: {Company} — {Role}
**URL:** {url}   **Report:** {#NNN or N/A}   **Legitimacy:** {tier or unknown}
**Researched:** {YYYY-MM-DD}   **Sources:** {N Glassdoor, N Blind, N other}

## Process
Rounds, duration, format, difficulty, known quirks — each with a source.

## Audience map
Classify each round into exactly one (mark guesses `[inferred]`):
- **recruiter-screen** (15–30m) — fit gate
- **hiring-manager** (30–45m) — motivation + scope
- **peer-tech** (coding / system design / take-home) — depth
- **panel-mixed** (onsite loop) — cross-cuts all three

## Round-by-round
Per round: who runs it, evaluation criteria, reported questions (sourced),
prep actions.

## Likely questions by audience
- **recruiter-screen** — CV walk-through, comp expectation (the concrete range
  from research), why-this-company (2–3 sentences tied to a public signal),
  location/visa fit, red-flag framing.
- **hiring-manager** — why this role + why now (tie to a named team challenge),
  a 90-day plan, how the report's gaps get covered, 2–3 sharp reverse questions.
- **peer-tech** — technical topics (source + a strong-answer sketch), JD-mapped
  role questions, reverse questions on how they actually build/operate.
- **panel-mixed** — a panel table (name, role, what they'll probe), and don't
  repeat the same proof point identically across interviewers.

## Story bank mapping
| Audience | Question / topic | Best story (apps/jobsquare/cv.md line) | Fit | Gap? |
Same story maps differently per audience. Flag gaps explicitly:
"No story for {X} — closest apps/jobsquare/cv.md experience: {Y}."

## Technical prep checklist  (≤ 10, by frequency × relevance)
- [ ] {topic} — why: {evidence}

## Company signals
What to volunteer, what to hold back, their vocabulary, red flags they screen.
```

## Rules

- Candidate-voiced text (the why-company answer, reverse questions, STAR
  phrasing) follows the **Writing guardrail** in `apps/jobsquare/modes/_shared.md`.
- Reported questions: **paraphrase**; if quoting verbatim, ≤ 15 words with the
  source named. Never reproduce large blocks of a source.
- Be direct — this is a briefing, not a pep talk. No fabricated confidence.

## After delivery

1. List the story gaps; offer to draft the missing STARs and append them to
   `apps/jobsquare/interview-prep/story-bank.md` (create it if absent).
2. If an interview date is known, note it in the doc's header for follow-up.
3. If research came back thin, say so and name what's still unknown.
