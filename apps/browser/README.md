# Gongzuo — Job Application Autofill

A Chrome (Manifest V3) extension that fills job applications from a profile you
save once. Built with **React + TypeScript + Vite** (via `@crxjs/vite-plugin`).

It reads each form field's labels, `aria-*`, `placeholder`, `name`/`id`,
`autocomplete` attribute and nearby text, matches them to your profile with
keyword heuristics, and writes values in a way that works on React-controlled
forms (Greenhouse, Lever, Workday, Ashby, and most company career pages).

## Features

- **In-page autofill button** (Simplify-style): a floating pill appears on
  pages with fillable forms and opens a **review panel** — see every field
  that will be filled, untick any you want to skip, then fill in one click.
- **Profile tab** in the popup: your whole profile as click-to-copy blocks
  (contact lines, each education/experience entry line, bullet descriptions,
  summary, cover letter, saved answers) — for referencing while answering
  questions Gongzuo can't fill.
- **Custom-widget engine**: fills ARIA comboboxes, React-Select typeaheads,
  and Workday `data-automation-id` dropdowns — not just native inputs. Also
  handles contenteditable rich-text editors, `date`/`month` inputs (with
  free-form date parsing), and shadow DOM.
- **Resume auto-attach**: store your resume/cover letter locally and Gongzuo
  attaches them to matching upload fields (including hidden file inputs).
- **Answer memory**: unmatched questions show up in the review panel — save an
  answer once and it's reused whenever a similar question appears. All local.
- **Alternative values**: any profile value or saved answer can list
  alternatives with `|` — e.g. `BSc | Bachelor of Science` or
  `LinkedIn | Job board`. Dropdowns, radios, and custom widgets try each in
  order until one matches the form's options (typeaheads retype each
  candidate); text inputs use the first; date inputs use the first parseable
  one (`ASAP | 2026-08`). Long prose containing `|` is never split.
  On top of that, enumerable answers carry built-in synonyms: a stored
  `Male` also matches a dropdown that says `Man`, `On-site` matches
  `In office`, `No` matches the full federal veteran/disability phrasings,
  and any decline-to-answer wording matches every ATS's variant of it.
- **Application tracker**: every filled application is logged locally with a
  status you can update (Filled → Applied → Interviewing → Offer/Rejected).
- **Interview prep** (synced from [career-ops](docs/modes/recruiter-side.md)'s
  interview-prep mode): every tracked application has a **Prep** button that
  copies a self-contained, company-specific interview-intelligence prompt —
  your profile/experience/prepared answers plus the application's company,
  role, and posting URL — ready to paste into Claude or any assistant. The
  full modes are also available as repo commands:
  `.claude/commands/interview-prep.md` (company intel for a tracked
  application) and `.claude/commands/interview.md` (interactive profile
  enrichment that round-trips through `gongzuo-profile.json`).
- **Repeating sections**: Education and Work Experience blocks fill row by
  row — the form's 2nd School field reads your 2nd education entry — and when
  your profile has more entries than the form shows, Gongzuo clicks the
  section's **"Add another"** control (inert links/buttons only), waits for
  the new row, and fills it too.
- **Cross-frame filling**: embedded ATS iframes (Greenhouse/Lever) are filled
  and counted via background-mediated frame aggregation — never
  `window.postMessage`, which pages could forge to harvest profile data.
- **Continuous multi-page fill** (opt-in): keeps filling as Workday-style
  wizards reveal new steps.
- **Sensitive-field opt-outs**: separate toggles for EEO/demographics,
  disability status, and salary questions.
- **Smart field matching** — labels, `aria-*`, placeholders, `autocomplete`
  tokens, section headings (so "Start date" under *Education* fills from your
  education history, not your availability), education/experience specs, and
  radio/`<select>`/option matching including yes/no questions.
- **Privacy-first** — everything is stored locally in `chrome.storage.local`.
  No network calls, no analytics, no accounts. See
  [docs/simplify-reference.md](docs/simplify-reference.md) for the competitive
  teardown this design is based on.
- Autosave, JSON import/export, highlight-on-fill, and an
  "only fill blanks vs. overwrite" toggle.

## Develop

```bash
npm install
npm run icons     # generate PNG icons (also runs fine without; committed)
npm run dev       # Vite dev server with HMR for the extension
```

Then load the dev build into Chrome:

1. Visit `chrome://extensions`, enable **Developer mode**.
2. **Load unpacked** → select the `dist/` folder.

## Build a distributable

```bash
npm run build     # type-checks, then outputs the extension to dist/
```

Load `dist/` via **Load unpacked**, or zip it for the Chrome Web Store.

## Try it

Open [`examples/sample-application.html`](examples/sample-application.html) in
Chrome (with the extension loaded), set up your profile from the options page
(or click **Load sample data**), then click the Gongzuo icon → **Fill this
page**.

## Test the matching engine

```bash
npm test          # runs the field-matcher unit tests (no browser needed)
```

## Project layout

```
manifest.config.ts        MV3 manifest (typed, via crxjs defineManifest)
vite.config.ts            Vite + React + crxjs
index.html                Popup entry
src/
  popup/                  Popup UI (Fill button, counts, status)
  options/                Profile, settings, documents & application tracker
  content/
    content.ts            Field detection + fill orchestration (content script)
    overlay.ts            In-page floating button + review panel (shadow DOM)
  background/background.ts Service worker (badge, cross-frame fill aggregator)
  lib/
    profile.ts            Profile types + defaults (incl. stored documents)
    storage.ts            chrome.storage wrappers + application tracker
    fieldMatcher.ts       Heuristic field → profile-value matching (section-aware)
    filler.ts             React-compatible DOM value setting + file attach
    widgetFiller.ts       Async custom-dropdown/combobox fill engine
    dates.ts              Free-form → ISO date parsing for date/month inputs
    dom.ts                Shadow-DOM-piercing queries
    messages.ts           Typed message protocol (+ untrusted-input sanitizers)
scripts/
  generate-icons.mjs      Dependency-free PNG icon generator
  test-matcher.ts         Matcher/date/file-slot unit tests
examples/
  sample-application.html A realistic native form to test against
  custom-widgets.html     Comboboxes, typeahead, hidden file input, multi-step
docs/
  simplify-reference.md   Verified Simplify Copilot teardown + roadmap
```

## How the React-safe fill works

React tracks an input's value on a hidden property and ignores `el.value = x`.
Gongzuo calls the native prototype value setter and dispatches bubbling
`input`/`change` events so controlled components register the change — see
`src/lib/filler.ts` (`setNativeValue`).

## Debugging "field not found"

Open DevTools on the page, switch the console context dropdown from *top* to
**Gongzuo — Job Application Autofill**, and run:

```js
__gongzuoDebug()
```

It prints a table of every control Gongzuo saw in that frame: the label/signal
it derived, what it matched, and — for rejected controls — the exact reason
(disabled, not visible, search control, nested in a widget…). Run it inside a
specific iframe by picking that frame in the same dropdown. The first line also
tells you whether the frame is allowed to fill (unknown cross-origin embeds are
scan-only; the popup shows a notice when a blocked frame contains fields).

## Notes & limits

- Custom dropdowns built from `<div>`s (not real `<select>`/`<input>`) can't be
  filled reliably and are skipped.
- Cross-origin iframes can't be read by the content script (browser security);
  same-origin embedded forms are handled.
- Nothing is submitted automatically — Gongzuo only fills, you review and submit.
