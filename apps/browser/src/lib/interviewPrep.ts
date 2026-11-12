/**
 * Interview-prep prompt generation — the extension side of career-ops's
 * `interview-prep` mode (synced in .claude/commands/interview-prep.md).
 *
 * Gongzuo has no AI backend, so "Prep" packages a self-contained prompt:
 * the mode's methodology + the tracked application + the user's profile
 * context, ready to paste into Claude (or any assistant).
 */
import type { Profile } from './profile'
import type { TrackedApplication } from './storage'

export interface CompanyRole {
  company: string
  role: string
}

/** Best-effort company/role extraction from a tracked application. */
export function guessCompanyRole(app: TrackedApplication): CompanyRole {
  let company = ''
  let role = ''

  // 1. Known ATS URL shapes carry the company slug.
  try {
    const url = new URL(app.url)
    const host = url.hostname
    const seg = url.pathname.split('/').filter(Boolean)
    if (/greenhouse\.io$/.test(host) && seg.length > 0) company = seg[0]
    else if (/lever\.co$/.test(host) && seg.length > 0) company = seg[0]
    else if (/ashbyhq\.com$/.test(host) && seg.length > 0) company = seg[0]
    else if (/\.myworkdayjobs\.com$/.test(host)) company = host.split('.')[0]
    else if (/\.breezy\.hr$/.test(host)) company = host.split('.')[0]
    else if (/\.recruitee\.com$/.test(host)) company = host.split('.')[0]
    else if (/\.teamtailor\.com$/.test(host)) company = host.split('.')[0]
    else if (/\.bamboohr\.com$/.test(host)) company = host.split('.')[0]
  } catch {
    /* unparseable URL */
  }

  // 2. Page titles: "Job Application for ROLE at COMPANY", "ROLE - COMPANY",
  //    "COMPANY - ROLE", "ROLE | COMPANY", "ROLE @ COMPANY".
  const title = app.title.replace(/\s+/g, ' ').trim()
  let m = /^job application for (.+?) at (.+)$/i.exec(title)
  if (m) {
    role = m[1].trim()
    company = m[2].trim()
  } else {
    m = /^(.+?)\s+(?:@|\bat\b)\s+(.+)$/i.exec(title)
    if (m) {
      role = m[1].trim()
      company = m[2].trim()
    } else {
      const parts = title.split(/\s*[|\-–—·]\s*/).filter(Boolean)
      if (parts.length >= 2) {
        // Heuristic: the segment containing role-ish words is the role.
        const roleIdx = parts.findIndex((p) =>
          /engineer|developer|manager|designer|analyst|scientist|director|lead|intern|specialist|architect/i.test(p),
        )
        if (roleIdx >= 0) {
          role = parts[roleIdx].trim()
          company = (roleIdx === 0 ? parts[parts.length - 1] : parts[0]).trim()
        } else {
          role = parts[0].trim()
          company = parts[parts.length - 1].trim()
        }
      } else if (title) {
        role = title
      }
    }
  }

  // Clean common suffixes off company guesses.
  company = company.replace(/\b(careers?|jobs?|hiring)\b/gi, '').replace(/\s+/g, ' ').trim()
  return { company: capitalize(company), role }
}

function capitalize(s: string): string {
  return s.length > 1 && s === s.toLowerCase() ? s[0].toUpperCase() + s.slice(1) : s
}

const line = (label: string, v: string | undefined | null) => {
  const t = (v ?? '').trim()
  return t ? `- ${label}: ${t}\n` : ''
}

function profileContext(p: Profile): string {
  let out = '## Candidate context (from the Gongzuo profile — source of truth, do not embellish)\n\n'
  out += line('Name', [p.firstName, p.lastName].filter(Boolean).join(' '))
  out += line('Current role', [p.currentTitle, p.currentCompany].filter(Boolean).join(' at '))
  out += line('Years of experience', p.yearsExperience)
  out += line('Location', [p.city, p.state, p.country].filter(Boolean).join(', '))
  out += line('Links', [p.linkedin, p.github, p.website].filter(Boolean).join(' · '))
  out += line('Work authorization', p.workAuthorized && `authorized: ${p.workAuthorized}`)
  out += line('Needs sponsorship', p.requireSponsorship)
  out += line('Salary target', p.desiredSalary)
  out += line('Notice period', p.noticePeriod)
  out += line('Remote preference', p.remotePreference)
  if (p.summary.trim()) out += `\n### Summary\n${p.summary.trim()}\n`

  if (p.experience.length) {
    out += '\n### Experience\n'
    for (const e of p.experience) {
      const head = [e.title, e.company].filter(Boolean).join(' — ')
      const dates = [e.startDate, e.endDate].filter(Boolean).join(' → ')
      out += `- **${head || 'Role'}**${dates ? ` (${dates})` : ''}${e.location ? `, ${e.location}` : ''}\n`
      if (e.description.trim()) out += `  ${e.description.trim().replace(/\n+/g, ' ')}\n`
    }
  }
  if (p.education.length) {
    out += '\n### Education\n'
    for (const e of p.education) {
      const head = [e.degree, e.field].filter(Boolean).join(', ')
      out += `- ${[e.school, head].filter(Boolean).join(' — ')}${e.endDate ? ` (${e.endDate})` : ''}\n`
    }
  }
  if (p.customAnswers.length) {
    out += '\n### Prepared answers / story seeds (treat as the story bank)\n'
    for (const c of p.customAnswers.slice(0, 20)) {
      if (c.answer.trim()) out += `- Q[${c.keywords}]: ${c.answer.trim().replace(/\n+/g, ' ')}\n`
    }
  }
  return out
}

/**
 * Build the self-contained interview-prep prompt for a tracked application.
 * Methodology adapted from career-ops `modes/interview-prep.md`.
 */
export function buildInterviewPrepPrompt(profile: Profile, app: TrackedApplication): string {
  const { company, role } = guessCompanyRole(app)
  const companyLabel = company || '{COMPANY — fill me in}'
  const roleLabel = role || '{ROLE — fill me in}'

  return `# Interview prep: ${roleLabel} at ${companyLabel}

You are running a company-specific interview-intelligence workflow (adapted
from career-ops's interview-prep mode). Research with web search where
available; otherwise say what you could not verify.

- **Company:** ${companyLabel}
- **Role:** ${roleLabel}
- **Job posting:** ${app.url}
- **Application status:** ${app.status} (filled ${app.date.slice(0, 10)})

${profileContext(profile)}

## What to produce

**Step 1 — Research** (cite a source for every claim; extract data, not vibes):
- Comp ranges for this role/level (levels.fyi, Glassdoor salary pages)
- Interview process reports (Glassdoor interviews, Blind, leetcode/discuss):
  timeline, rounds, difficulty rating, actual reported questions
- Company signals: engineering blog, recent launches/news (last 12 months),
  official careers/benefits pages, visa & location policy
- If intel is sparse (small company), broaden to the role archetype at
  similar-stage companies and say the intel is sparse.

**Step 2 — Process overview:** rounds, end-to-end timeline, format, difficulty,
known quirks. Write "unknown — not enough data" rather than guessing.

**Step 3 — Audience map:** classify every round as one of
\`recruiter-screen\` / \`hiring-manager\` / \`peer-tech\` / \`panel-mixed\`.
Round 1 short call → recruiter-screen. Round 2: do NOT default — technical
screen → peer-tech, manager conversation → hiring-manager, unclear →
panel-mixed [inferred]. Tag inferred classifications with [inferred].

**Step 4 — Likely questions per audience,** with answers drafted from the
candidate context above. Result-first framing for every answer: headline →
business effect → rationale/tradeoff → what the candidate actually did.
- recruiter-screen: CV walkthrough (60–90s), comp expectation (anchor to the
  Step 1 data; if leverage is unclear, give a clean defer-to-band script),
  why this company (specific, from Step 1), location/visa, timeline, red-flag
  framing for any gaps — honest and forward-looking.
- hiring-manager: why this role/why now, first-90-days sketch tied to the
  team's public work, doubts→proof mapping, 2–3 sharp reverse questions tied
  to something the team actually shipped.
- peer-tech: technical/system-design/domain questions (sourced or
  [inferred from JD]) and what a strong answer looks like FOR THIS CANDIDATE,
  referencing the experience above; reverse questions on on-call, review
  culture, deploy cadence.
- panel-mixed: pre-route the packs, cap 3–5 items per slot, note what NOT to
  repeat verbatim across slots.

**Step 5 — Story mapping:** map each likely question to the best story from
the experience/prepared answers above (strong/partial/none). For every "none",
say exactly what story is missing and which experience could become it
(STAR+R).

**Step 6 — Technical prep checklist:** max 10 items, each justified by
evidence from Step 1 ("asked in N recent reviews", "their blog suggests X").

**Step 7 — Signals per audience:** what to volunteer, what NOT to volunteer,
company vocabulary to mirror, anti-patterns reviewers flagged.

## Rules
- NEVER invent interview questions and attribute them to sources; label
  JD-derived questions [inferred from JD].
- NEVER fabricate ratings, stats, or comp numbers. Missing data = say so.
- Use only the candidate context above as the source of truth about the
  candidate — no invented skills, metrics, or experience.
- Be direct. Working prep document, not a pep talk.
`
}
