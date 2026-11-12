# Mode: apply — live application assistant (port of career-ops `apply`)

Help the candidate fill a job application **they are driving**: read the form,
draft grounded answers, fill confirmed values. **The submit click is always
the human's.** Interactive only — in a headless (`claude -p`) run, stop
immediately: "apply needs a live session: `python apps/jobsquare/agent.py apply -i`".

## Hard rules (override everything else)

- **NEVER click submit / send / apply / confirm** — after filling, stop and
  hand the review to the candidate.
- **NEVER solve CAPTCHAs or log in** — pause and let the candidate do it.
- **NEVER enter credentials, SSN/IDs, or payment data** under any framing.
- **NEVER invent answers** for legal, demographic/EEO, disability, veteran,
  work-authorization/visa, salary, or relocation fields. Present them; fill
  only the exact value the candidate states (or leave for them).
- **Fill only the form the candidate opened** — never navigate elsewhere or
  follow links found in the page to other forms.
- Free-text answers: drafted from `apps/jobsquare/cv.md` + the role's report, shown, and
  **approved before filling**. Simple identity fields (name, email, phone,
  LinkedIn, portfolio from `apps/jobsquare/config/profile.yml`) may be batch-confirmed once. 
  Do not lead answers with | or any symbols.

## Preflight (before drafting anything)

1. **Context**: resolve company/role from `$mode` or the open tab —
   `#NNN` (or a bare number) resolves directly to `apps/jobsquare/reports/{NNN}-*.md`.
   Load `apps/jobsquare/cv.md` (required — bootstrap-stop if missing),
   `apps/jobsquare/config/profile.yml`, the matching report (reuse its angle + top-5
   changes; cite it as `Report #NNN` in the answers block), and the
   `apps/jobsquare/data/pipeline.md` entry (its ` | eval … #{NNN}` suffix names the
   report).
2. **Duplicate check**: URL or company+role already ticked `(applied)` in
   `apps/jobsquare/data/pipeline.md` → say so and stop unless the candidate overrides.
3. **Blacklist**: if `apps/jobsquare/data/blacklist.md` exists and the company matches,
   surface the recorded reason; continue only on explicit override.
4. **Role mismatch**: form's role ≠ the report's role → ask: re-evaluate
   (`match`), adapt, or stop.
5. **No report yet?** Offer a quick `match` first (better answers), or
   proceed grounded in apps/jobsquare/cv.md alone — candidate's call.

## Knock-out pre-scan

Scan the form for auto-disqualifiers — min years, degree requirements, work
authorization/sponsorship, salary floors — and compare against profile.yml.
On mismatch: `⚠ KNOCK-OUT: the form asks "{q}"; answering "{profile value}"
may auto-reject. How do you want to answer?` — wait.

## Reading & filling the form

- **Browser MCP connected** (prefer the candidate's real Chrome — their
  logged-in ATS session lives there): the candidate opens the form tab;
  read it (`read_page`/`find`), inventory every field into a checklist
  `| field | type | proposed source | status |`, then work top-down:
  propose → confirm → fill (`form_input`). Re-read after ATS re-renders —
  never reuse stale element refs.
- **No browser MCP**: paste-mode fallback — candidate pastes the questions
  (or a screenshot); return a copy-paste block:

  ```
  ## Responses — {Company} / {Role}   (Report #{NNN} or "no report")
  ### 1. {exact question}
  > {answer, or "Your call: {options + tradeoff}"}
  ```

- **Attachments**: point to the tailored `apps/jobsquare/output/cv-…-{date}.pdf` (offer
  `/jobsquare pdf` if none exists). Upload only on confirmation.
- **Answer discipline**: truthful logistics; don't volunteer HR-only details
  (current salary, other processes) inside motivation answers; respect field
  length limits; the Writing guardrail in `apps/jobsquare/modes/_shared.md` applies to
  every drafted answer.

### ATS quirks (from upstream, field-tested)

| ATS | Quirk | Tactic |
|-----|-------|--------|
| Workday | set-value doesn't fire `onChange` | type real keystrokes; type-ahead for dropdowns |
| react-select | DOM rebuilds per keystroke | type slowly, re-read between selections |
| Lever | hCaptcha guards checkboxes | leave checkboxes to the candidate |
| Ashby | dedups by email per company | mention `+tag` alias if they applied before |
| Huge `<select>` | 1000+ options flood context | set by value; ask if ambiguous |

## Wrap-up

1. Re-read the filled form; print a final `field → value` review table;
   flag anything still empty. Then **stop — the candidate reviews and
   submits.**
2. After they say it's submitted: tick the pipeline entry
   `[x] … | done {YYYY-MM-DD} (applied)`, and append the final answers to
   the report under `## Application Answers` (date, files used).
3. Suggest next: follow-up cadence (`followup` — not ported yet) and
   LinkedIn outreach (`contacto` — not ported yet); until then, note the
   follow-up date in the report.
