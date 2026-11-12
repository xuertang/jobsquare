# prep

SWE interview prep. One folder per problem. Every problem folder has a `README.md`
(the prompt + what's being scored + follow-ups) next to a runnable solution.

## Layout

```
src/
  algo/          LeetCode-style, foldered by pattern rather than by problem name
  ds/            data structures you implement from scratch (LRU, trie, union-find, ...)
  codesignal/    4-level industry-style: one stateful service, grown across 4 rounds
  fe/
    js/          vanilla JS fundamentals (debounce, promise pool, event emitter, deep clone)
    ui/          DOM builds, no framework
    react/       component builds, hooks, state
  system/
    backend/     classic distributed system design
    frontend/    FE system design (feed, autocomplete, design system, offline)
_templates/      skeletons: algo, ds, codesignal, fe-js, fe-ui, fe-react, fe-react-ts, system
scripts/         ./new (scaffold), ./run (dev server), ./pytest (Python problems)
notes/           cross-cutting cheatsheets (complexity, patterns, behavioral stories)
```

## Running it from the repo root

Every command here works from `apps/prep`, and the repo root has a `./prep` forwarder so
you don't have to `cd` first. These pairs are the same command:

```sh
./prep new codesignal parking-lot     cd apps/prep && ./new codesignal parking-lot
./prep run wishlist                   cd apps/prep && ./run wishlist
./prep pytest ledger -m level1        cd apps/prep && ./pytest ledger -m level1
```

The rest of this README uses the short form. `./prep` with no arguments lists what it
takes.

## Conventions

- **`README.md` is the prompt.** GitHub renders it when you open the folder, so it's the
  first thing you see. Never a bare problem statement — it also carries clarifying
  questions, the scoring rubric, and follow-up probes.
- **Folder names are kebab-case and describe the problem**, not the ranking:
  `src/algo/sliding-window/longest-substring-k-distinct/`.
- **Solutions are runnable standalone.** Python for algo/ds/codesignal, plain
  `.js`/`.html`/`.jsx` for frontend. No build step, no shared package.
- **Tests live beside the solution** (`test_solution.py`, `solution.test.js`) where the
  problem has a crisp contract. System design has no tests — it has `notes.md`.
- One problem per folder. Variants of the same problem stay in the same folder as extra
  sections in the README, not as sibling folders.

## Running the frontend problems

```sh
npm install          # once

./run                # list what's runnable
./run wishlist       # fuzzy match on folder name
./run react/data-table
./run _templates/fe-ui
```

One dev server, three folder layouts, detected in this order:

| Layout | Trigger | Served as |
| --- | --- | --- |
| `html` | `index.html` at the folder root | as-is, no build (vanilla DOM problems) |
| `entry` | own `index.tsx` / `index.jsx` / `main.tsx` | your entry; HTML from `./index.html`, `./public/index.html`, or a built-in fallback, with the `<script>` tag injected if missing |
| `shell` | only `App.tsx` / `App.jsx` | mounted via `scripts/react-shell/` |

`shell` keeps a React problem down to a single file — no per-problem `package.json`,
entry point, or vite config before you can start. `entry` is the CRA shape, and is what
you want the moment a problem needs its own CSS, providers, or router. Hot reload works
in all three. `--no-open` skips launching the browser.

TypeScript works everywhere with no extra setup — `.tsx`/`.ts` are transformed by vite
on the fly, and where a folder has both `App.tsx` and `App.jsx` the typed one wins.

```sh
npm run typecheck    # tsc --noEmit across src/ and _templates/
npm test             # vitest, for the src/fe/js utility problems
```

Note that `npm run typecheck` type-checks but never emits — vite does the transform, so
type errors never block the dev server. That's deliberate: a red type error shouldn't
stop you mid-drill, but you should see it before you call a problem done.

## Running the Python problems

```sh
./pytest                     # every problem that has tests
./pytest ledger              # fuzzy match on folder name, exact match wins
./pytest codesignal          # every problem whose path matches, all of codesignal/
./pytest ledger -m level1    # anything it doesn't recognise goes through to pytest
./pytest --list
```

Each problem folder is its own pytest process, with the working directory set to that
folder. One pytest across the whole tree cannot work: every problem names its tests
`test_solution.py` and imports a bare `solution`, so pytest dies on `import file
mismatch` and reads the wrong `pytest.ini`. Running from inside the
folder is also how you'd do it by hand, so each problem's own `markers` and `testpaths`
apply unchanged, and `pytest` on its own inside a folder still works exactly as before.

Sweeping several problems prints a per-folder header and a pass/fail summary, and exits
non-zero if any of them failed. A folder with no tests collected is reported separately
rather than counted as a pass.

The interpreter is the repo venv (`.venv/bin/python`) when there is one, otherwise
`python3`; `PREP_PYTHON=/path/to/python` overrides. No activated shell needed either way.

For the CodeSignal problems, `ICF_IMPL` picks which file gets tested: the reference
`solution.py` by default, or your own cold attempt:

```sh
ICF_IMPL=attempt ./pytest ledger -m level1
```

## Adding a problem

```sh
./new                                # list types, algo patterns, system tracks
./new react memory-game              # TypeScript by default
./new react memory-game --js         # JS instead
./new ui autocomplete
./new js debounce
./new algo two-pointers/container-with-most-water
./new ds lru-cache
./new codesignal parking-lot
./new system backend/url-shortener
```

| Type | Lands in | From |
| --- | --- | --- |
| `react` | `src/fe/react/<name>` | `_templates/fe-react-ts` (or `fe-react` with `--js`) |
| `ui` | `src/fe/ui/<name>` | `_templates/fe-ui` |
| `js` | `src/fe/js/<name>` | `_templates/fe-js` |
| `algo` | `src/algo/<pattern>/<name>` | `_templates/algo` |
| `ds` | `src/ds/<name>` | `_templates/ds` |
| `codesignal` | `src/codesignal/<name>` | `_templates/codesignal` |
| `system` | `src/system/<track>/<name>` | `_templates/system` |

The copy isn't literal — placeholder headings get the real name, so `./new ds lru-cache`
produces `# LRU Cache` and `` `LRUCache` ``, not `<Problem Name>`. Names must be
kebab-case, and it refuses to overwrite a non-empty folder. Valid algo patterns and
system tracks are read from the directories that exist, so adding a new pattern is just
`mkdir src/algo/<pattern>` — no edit to the script.

Then fill in the README first, solve it cold, and only afterwards write down what you
missed in the "What I missed" section. That section is the entire point of the repo —
a solved problem with an empty retro is a problem you'll fail again.

## Per-category index

Each category folder keeps its own `README.md` index table (problem, difficulty, last
attempted, confidence). Update the row when you redo a problem.
