# Mode: pdf — ATS-optimized CV tailored to one JD

Produce a recruiter-scannable, ATS-parseable PDF CV tailored to a single job
description. Everything on it must be sourced from `apps/jobsquare/cv.md` — tailoring means
*selecting and reframing*, never inventing.

## Required inputs

- **`apps/jobsquare/cv.md`** (repo root) — the candidate's master CV, source of truth.
  Missing → **stop** and tell the user to create it with sections:
  `# Name / contact`, `## Summary`, `## Experience` (company, role, dates,
  bullets), `## Projects`, `## Education`, `## Skills`. Offer to draft it
  interactively from their answers; never fabricate one.
- **A JD**, resolved from `$mode`'s remainder:
  1. pasted text → use directly;
  2. URL → WebFetch it;
  3. company name / keyword → match a `## Pending` entry in
     `apps/jobsquare/data/pipeline.md`, WebFetch its URL;
  4. nothing → ask which pending entry to target.
- `apps/jobsquare/config/profile.yml` (optional) — contact block, language, comp context.

## Workflow

1. **Extract 15–20 JD keywords** (skills, tools, domain nouns, seniority).
2. **Language**: match the JD's language; default English.
3. **Paper**: `letter` for US/Canada roles, else `a4`.
4. **Summary**: rewrite 3–4 lines for this role — target title in sentence
   one, top-5 keywords woven honestly, one quantified proof point from apps/jobsquare/cv.md.
5. **Competencies**: 6–8 short phrases mirroring JD vocabulary that apps/jobsquare/cv.md
   actually supports.
6. **Experience**: reverse-chronological; within each role, reorder bullets
   by JD relevance; reframe wording to exact JD vocabulary when truthful
   (apps/jobsquare/cv.md "LLM workflows with retrieval" + JD "RAG pipelines" → "RAG
   pipeline design"). A JD skill absent from apps/jobsquare/cv.md **never** appears.
7. **Projects**: keep the 3–4 most relevant; drop the section if none.
8. **One page, hard limit.** The CV must fit a single page — never spill to
   a second. The top third must make target role, fit, and proof obvious.
   If it overflows (step 10 tells you), tighten in this order: drop the
   least-JD-relevant bullets, then the oldest role's bullets, then the
   Projects section, then trim the summary to 3 lines and competencies to 6.
   Cut content — never shrink the template's fonts/margins.
9. **Build HTML (transient)**: copy `apps/jobsquare/templates/cv-template.html`, replace
   every `data-slot` element's content, delete empty optional sections, leave
   CSS untouched. Write it to a **temp** path — `apps/jobsquare/output/.cv-{name-kebab}-{company-kebab}.html`
   (leading dot). This file is scaffolding, not a deliverable; step 10 deletes it.
10. **Render to PDF** (the only artifact):
    `python apps/jobsquare/agent.py pdf-render apps/jobsquare/output/.cv-{…}.html apps/jobsquare/output/cv-{name-kebab}-{company-kebab}-{YYYY-MM-DD}.pdf --format {letter|a4} --max-pages 1 --clean`
    The helper ATS-normalizes text (smart quotes, dashes, bullets → ASCII),
    prints via headless Chrome, and on success `--clean` removes the temp HTML
    so **only the PDF remains**. **Exit 3** = more than one page: go back to
    step 8, cut content, and re-render (the temp HTML is kept for editing).
    Any other non-zero exit → report the error, don't improvise a renderer.
    Never leave an `.html` in `apps/jobsquare/output/`.
11. **Report** (terminal):

    ```
    CV PDF — {company} / {role}
    File: apps/jobsquare/output/cv-…-{date}.pdf ({size}, 1 page)
    Emphasized: {3-5 bullets of what was surfaced/reordered and why}
    Keyword coverage: {matched}/{extracted} — missing: {honest gaps}
    {if content was cut to fit one page: what was dropped}
    ```

    List gaps honestly — a keyword apps/jobsquare/cv.md can't support is a gap, not a
    rewrite target. Tracker registration: not ported yet; if the JD came
    from `apps/jobsquare/data/pipeline.md`, mention the entry so the user can annotate it.

## ATS rules (non-negotiable)

- Single column; no tables, images, sidebars, headers/footers.
- Standard section names exactly as in the template.
- Selectable text only; no keyword stuffing, no hidden text.
- Keywords distributed: top-5 in summary, first bullet of each role, skills.
- Prose follows the **Writing guardrail** in `apps/jobsquare/modes/_shared.md` (voice
  sources, banned clichés, specifics over abstractions).
