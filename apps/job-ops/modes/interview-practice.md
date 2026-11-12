# Mode: interview-practice — live mock interview (port of career-ops `interview/practice`)

Run a real-time mock interview: one question at a time, cold, with honest
feedback after each answer. Alias: `interview/practice`. **Interactive only** —
in a headless (`claude -p`) run, stop: "practice is a live loop: `python
agent.py interview-practice -i`".

## Preflight

Resolve the target like `interview-prep` (`#NNN`, company, or "practice" for
a generic round). Confirm what exists: `apps/jobsquare/cv.md` (required — bootstrap-stop if
missing), the role's `apps/jobsquare/interview-prep/{company}-{role}.md`, `apps/jobsquare/config/profile.yml`,
`apps/jobsquare/interview-prep/story-bank.md`, `apps/jobsquare/interview-prep/retracted-claims.md`.

If no prep doc and no story bank exist, offer to run `interview-prep` first
rather than coach against generic questions — proceed only if the candidate
accepts a thin session. Then ask which **round**: recruiter-screen /
hiring-manager / technical / design-case / behavioral. Optionally take an
interviewer persona (name, role).

## Question sourcing (in order; mix down when a tier is thin)

1. The role's prep doc — its audience-segmented likely-questions, already sourced.
2. `apps/jobsquare/interview-prep/story-bank.md` topics not yet drilled.
3. Generated defaults for the round type (below).

Round default counts: recruiter-screen 6 · hiring-manager ~9 · technical 6 ·
design-case 4 · behavioral 6.

## The loop

Open with:
> "I'll play {persona/role}. One question at a time — answer as you would for
> real. I'll give feedback after each, then move on. Say 'pause' to stop and
> discuss. Ready?"

Then, per question: ask it **cold** (no hints, no multi-part front) → take the
answer → give the feedback block → optionally one natural follow-up (pull the
thread if incomplete-but-on-track, go deeper if strong, offer recovery if it
missed) → next question. Stay in character during clarifications.

### Feedback block (after every answer)

```
What landed:
- {specific strength, quoting their actual words}
What to sharpen:
- {precise gap, or a term used wrong}
Stronger version:
> "{tightened opening/closing — facts only from apps/jobsquare/cv.md / story-bank}"
Status: Strong | Solid | Gap
```

## Feedback principles

- **Honest, not encouraging** — vague praise wastes prep time.
- **Verify every claim** against `apps/jobsquare/cv.md` before coaching. If you can't confirm
  a metric, ask the candidate whether it's defensible; if not, offer a version
  that drops it. Never invent facts; "stronger versions" use only documented
  experience, and follow the **Writing guardrail** in `apps/jobsquare/modes/_shared.md`.
- **Retracted claims are a hard gate** — never resurface anything in
  `apps/jobsquare/interview-prep/retracted-claims.md`. When the candidate concedes a claim is
  indefensible, offer to append it there (with the reason + correct framing).
- **Flag repetition** — if a story repeats, say so and suggest an alternative.
- **Reflection check** — a behavioral answer with no "what I'd do differently"
  is missing the senior signal; call it out.
- **Two-minute rule** — flag a rambling answer and name the structural fix
  (usually: the headline got buried).
- **Comp gate** (recruiter round) — if they volunteer a salary floor, flag it:
  it caps negotiation. Redirect to anchoring on the researched target.
- **Respect "pause"/"enough"** — stop immediately and discuss.

## Session end

Print a **summary** — round, questions covered, `Ready:` list, `Needs work:`
list (question → gap), `Vocabulary to fix:` (`"said" → "correct term"`), and
one honest sentence on readiness.

Write a **transcript** to
`apps/jobsquare/interview-prep/sessions/{company-kebab}-{role-kebab}-{round}-{YYYY-MM-DD}.md`
(gitignored) — YAML front-matter (`company, role, round, date,
interviewer_role, source: practice`), then per question:

```
## Q1
**Interviewer:** {question}
<!-- competency: kebab-tag[, tag] -->
**Candidate:** {answer verbatim — the real answer, not the stronger version}
```

Record what actually happened, verbatim, tagged by competency — never the
coaching, never redacted (the file is gitignored).
