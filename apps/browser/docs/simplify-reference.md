# Simplify Copilot reference — teardown & Gongzuo roadmap

> Compiled 2026-07-17 from simplify.jobs, its Chrome/Firefox store listings, help
> docs, and hands-on third-party reviews; claims cross-checked adversarially.
> Marketing-only numbers (500k installs, 200M applications) are vendor self-report.

## 1. What Simplify Copilot is

A manual-trigger, human-in-the-loop autofill extension built on a **single
canonical profile** that also powers Job Matches, an AI Resume Builder, and a
Job Tracker. Only autofill + tracker are relevant to a local-first competitor.

**Autofill mechanics (high confidence):**
- User opens a supported application → clicks the in-page Simplify widget →
  Copilot maps fields to the profile → user reviews → user submits. No
  auto-apply, no auto-submit.
- Fields split into **Common Questions** (deterministic profile→field mapping)
  vs **Unique Questions** (custom/free-text; AI-answered on the paid tier).
- **Answer memory:** a saved/edited answer to a unique question is auto-reused
  when the same question appears again.
- **Granular per-field toggles**, incl. opt-outs for sensitive fields
  (Disability, Salary, Location), and a **"continuously autofill multipage
  forms"** switch for Workday-style multi-step flows.

**ATS coverage:** "100+ boards/portals"; officially named: Workday, Greenhouse,
iCIMS, Taleo, Avature, Lever, SmartRecruiters (Ashby via third-party reviews).
Real-world accuracy is inconsistent per-ATS; resume parsing has known bugs.
Reliable per-ATS mapping is the hard part, not the feature list.

**In-page UX (confirmed):** a floating Simplify icon/pill appears on detected
application forms; the toolbar icon lights up on supported sites; clicking the
pill triggers autofill with visual feedback; every submitted application is
auto-logged to the tracker (the retention flywheel).

**Privacy posture (their weakness, our differentiator):** cloud-first — the
profile, incl. EEO/demographic data, lives server-side; the extension requests
"read and change all your data on all websites"; AI answers/cover letters are
paywalled (Simplify+).

## 2. Gap analysis → what Gongzuo builds

| Capability | Simplify | Gongzuo action |
|---|---|---|
| Custom widgets (React-Select, ARIA combobox, Workday `data-automation-id`) | Yes | **P0.1** `src/lib/widgetFiller.ts` + async fill engine |
| In-page floating button + review panel | Signature UX | **P0.2** `src/content/overlay.ts` (Shadow DOM) |
| Cross-frame fill aggregation | n/a | **P0.3** top-frame `postMessage` coordination |
| Multi-page continuous fill (Workday) | Yes | **P1.1** `continuousFill` setting + re-run on DOM change |
| Education/experience section fill | Yes | **P1.2** section-aware specs (first entry v1) |
| Resume/cover file attach | Yes | **P1.3** `DataTransfer` + stored file → `input.files` |
| Answer memory | Yes (cloud) | **P1.4** save-answer in review panel → `customAnswers` (local) |
| Sensitive-field opt-outs | Yes | **P1.5** EEO / disability / salary toggles |
| Application tracker | Yes (cloud Kanban) | **P2.1** local tracker in options |
| AI answers, resume tailoring, job matching | Backend moat | **Out of scope** — local-first is the differentiator |

## 3. Positioning

Copy: single-profile spine, review-before-submit in-page UX, common/unique
question split, sensitive opt-outs, autofill→tracker loop, continuous fill.

Differentiate: **"your data never leaves your device"** (chrome.storage.local
only, no account, no paywall), portable JSON profile, and reliability on the
exact widgets where Simplify is reported inconsistent (Workday/React-Select).
