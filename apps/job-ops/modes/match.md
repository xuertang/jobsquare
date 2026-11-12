# Mode: match — score a JD against apps/jobsquare/cv.md (port of career-ops `oferta`)

Answer one question with evidence: **should the candidate apply, and with what
angle?** Everything is grounded in `apps/jobsquare/cv.md` — no invented experience, no
flattery. Alias: `oferta`.

## Required inputs

Same resolution as `pdf` mode:
- **`apps/jobsquare/cv.md`** (repo root) — missing → stop with the bootstrap instructions
  from `apps/jobsquare/modes/pdf.md`.
- **A JD**: pasted text | URL (WebFetch it) | company/keyword matching a
  `## Pending` entry in `apps/jobsquare/data/pipeline.md` | nothing → ask.
- `apps/jobsquare/config/profile.yml` — North Star targets + comp floor; fall back to
  `apps/jobsquare/sources.yaml` filters when absent.

## Pre-gates

1. **Liveness** (URL inputs): the WebFetch doubles as the check — 404 /
   "no longer accepting" / empty JD body → report the dead link, offer to
   tick the pipeline.md entry `[x] … | done {date} (expired)`, and stop.
2. **Research budget**: max 3 WebSearch queries total (comp + legitimacy).
   Single-pass lookups; no subagents.

## Scoring rubric (1–5 each; jobsquare weights)

| Dim | Weight | Measures | 5 looks like |
|-----|--------|----------|--------------|
| A: CV match | 35% | requirements covered by apps/jobsquare/cv.md evidence | every must-have has direct proof |
| B: North Star | 20% | fit vs `apps/jobsquare/config/profile.yml` targets (titles, seniority, locations) | bull's-eye on title + level + location |
| C: Comp | 15% | listing/JD salary (verbatim) vs `comp.floor_usd`; market check only if unstated | at/above floor with stated numbers |
| D: Culture/stability | 15% | size, growth, remote policy, hiring signals | growing, stable, policy fits |
| E: Red flags | 15% | 5 = clean; deduct per flag (vague scope, buzzword density, contractor phrasing, ghost-job signals) | nothing detected |

**F: Global** = weighted average, one decimal.
**Culture cap:** a contradicted hard requirement from profile.yml (e.g.
onsite-only vs remote-required) caps D at 2/5 and must be called out.
**Comp rule:** advertised figures are quoted verbatim; researched estimates
are labeled as estimates, never presented as the listing's numbers.

| F | Verdict |
|---|---------|
| ≥ 4.5 | Strong match — apply immediately |
| 4.0–4.4 | Good match — apply |
| 3.5–3.9 | Decent — apply only with a specific reason (name it) |
| < 3.5 | Recommend against — say the one thing that would change it |

## Block G: posting legitimacy (separate from F)

Tier **High Confidence / Proceed with Caution / Suspicious** from: posting
age, description specificity (real tech vs buzzwords), reposting pattern,
hiring-freeze/layoff signals, contractor-classification phrasing (1099/
invoice + no benefits/PTO), scope-vs-team-size mismatch. Two or more negative
signals → drop a tier.

## Workflow

1. Pre-gates → read apps/jobsquare/cv.md + profile → extract JD requirements
   (must-have vs nice-to-have).
2. **CV↔JD mapping table** — the heart of the mode:
   `| JD requirement | apps/jobsquare/cv.md evidence (cite the line) | strong / partial / GAP | mitigation |`
   Gaps are hard-blocker or mitigable — never silently reframed.
3. Seniority calibration: JD's real level (from scope, not title) vs the
   candidate's; one line on pitching up/down without lying.
4. Score A–E → compute F → Block G tier.
5. **If F ≥ 3.5:** list the top-5 CV changes for this role. **F ≥ 4.0** →
   close with "run `/jobsquare pdf {company}` to apply them"; 3.5–3.9 →
   frame them as "if you decide to apply" (PDF stays a manual call).
6. Claim an id — `python apps/jobsquare/agent.py report-num` (do this right before writing,
   not earlier) — then write the report to
   `apps/jobsquare/reports/{NNN}-{company-kebab}-{role-kebab}.md`.
7. If the JD came from `apps/jobsquare/data/pipeline.md`: append
   ` | eval {F}/5 {YYYY-MM-DD} #{NNN}` to that entry (keep it unticked —
   ticking means applied/closed).
8. Print the report body (minus the machine block) to the terminal.

## Report template

````markdown
# {Company} — {Role}
**Report:** #{NNN}
**URL:** {url}
**Evaluated:** {YYYY-MM-DD} · **Global: {F}/5 — {verdict}** · **Legitimacy: {tier}**

## Scores
| A CV | B North Star | C Comp | D Culture | E Red flags | F Global |
|------|--------------|--------|-----------|-------------|----------|

## TL;DR
{2 sentences: fit + the deciding factor}

## CV ↔ JD mapping
{the table from step 2}

## Comp
{verbatim advertised figures or "not stated"; floor comparison; estimates labeled}

## Red flags & legitimacy
{bullets with evidence, or "none detected"}

## If applying
{top-5 CV changes → /jobsquare pdf; suggested angle in one line}

## Machine summary
```json
{"report_id": 0, "company": "…", "role": "…", "url": "…", "date": "…",
 "scores": {"a": 0, "b": 0, "c": 0, "d": 0, "e": 0, "f": 0.0},
 "legitimacy": "high|caution|suspicious",
 "advertised_comp": "verbatim or null"}
```
````

The machine-summary block is load-bearing: the future `patterns` mode
aggregates these, so keys and casing are fixed.
