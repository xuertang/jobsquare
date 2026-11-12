# CodeSignal-style (4 levels)

One stateful service, grown over four rounds. The whole exercise tests whether your
Level 1 data model survives Level 3. Levels are cumulative — nothing may regress.

The shape is always the same:

1. **L1 — CRUD.** Deliberately easy. The real question is what you record while doing it.
2. **L2 — Aggregation.** Top-N with a tie-break and an exact output format. Trivial if L1
   maintained the counter, a refactor if it didn't.
3. **L3 — A new axis.** Scheduling, TTL, hierarchy, deletion. Breaks a naive L1.
4. **L4 — History / merge / time travel.** Needs per-entity versioned state.

Budget roughly 20 / 15 / 25 / 20 minutes. Read all four levels before writing anything.
