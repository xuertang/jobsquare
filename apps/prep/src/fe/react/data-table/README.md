# Data Table

**React + TypeScript. Hooks only, no class components. No UI library.**

> Prompt as read out loud. Interactions, async behavior, error and empty states.

## Clarifying Questions

- Is data fetched or passed as props?
- Controlled or uncontrolled inputs?
- Does it need to be accessible to keyboard/screen-reader users? (Answer: yes.)

## What's being scored

Derived state instead of `useEffect`-to-sync. Correct dependency arrays. Stable
callbacks only where they matter (a memoized child), not sprinkled everywhere. Cleanup
in effects — abort in-flight fetches, clear timers. Keys that aren't array indices.
Race condition on out-of-order responses. Loading / error / empty as real states, not
an afterthought.

Plus the typing, which is scored separately: props typed as a named `type`, discriminated
union for loading/error/success instead of three loose booleans, no `any`, no assertion
to paper over a real narrowing problem. Event handlers take real DOM event types
(`React.ChangeEvent<HTMLInputElement>`), not `any`.

## Follow-up probes

- _"Debounce the input."_ → where does the timer live across renders?
- _"The user types fast — response 2 lands before response 1."_ → `AbortController` or
  a request-id guard.
- _"Make this a reusable hook."_ → and what's its return type — tuple or object?
- _"Make it generic over the row type."_ → `<T,>` in a .tsx file needs the trailing comma.

## What I missed

---
Single-file component in `App.tsx` — no entry point or HTML needed, the shell supplies
both. Run with `./run <folder-name>` from the repo root; `npm run typecheck` for types.
