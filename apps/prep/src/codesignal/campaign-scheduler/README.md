# `CampaignScheduler`

**Marketing Campaign Delivery System** · Content Platform / Marketing Technology
**Total: 600 points · 90 minutes**

---

## How to take this exam

1. Set a **90-minute timer** and do not stop it. The clock is the exam.
2. `cp starter.py attempt.py` and implement inside `attempt.py`. Do not open `solution.py`.
   `starter.py` holds **Level 1 only** — that is not an omission. Each later level's method
   signatures are printed in this file when you reach that level, and you add them to your
   class yourself, exactly as the real CodeSignal editor works.
3. **Reveal one level at a time.** Read Level 1 only, implement it, run its tests, and *then*
   scroll to Level 2. Reading ahead destroys the point of the drill — the whole skill being
   tested is absorbing a requirement that invalidates your data model.
4. After each level, run only that level's tests:
   ```
   ICF_IMPL=attempt pytest -m level1     # then -m level2, -m level3, -m level4
   ```
5. At the end, run everything: `ICF_IMPL=attempt pytest`. **Level 1 and 2 tests must still
   pass after Level 4 is implemented.** Backward compatibility is graded, not optional.

Suggested budget: **10 / 20 / 30 / 30 minutes**. If a level overruns, move on — partial credit
across four levels beats a perfect Level 3 and an empty Level 4.

---

## Context

You are building the delivery engine behind marketing campaigns. A **campaign** targets one
**channel** (`"email"`, `"web"`, `"push"`, …) and carries an integer **priority**. Later levels
add spend budgets, per-campaign throttling, and an auditable rollback facility.

All state lives in one class, `CampaignScheduler`. Every level extends the same class.

---

## Level 1 — Campaign lifecycle (100 points, ~10 min)

### `__init__(self) -> None`
Creates an empty scheduler. `CampaignScheduler()` takes no arguments at this level.

### `create_campaign(campaign_id: str, channel: str, priority: int) -> bool`
Registers a new campaign in the **active** state.
- Returns `True` on success.
- Returns `False` if `campaign_id` already exists **and makes no change whatsoever** (the
  existing campaign keeps its original channel and priority — do not overwrite).
- `priority` may be zero or negative.

### `get_campaign(campaign_id: str) -> str | None`
Returns exactly:
```
"<campaign_id>(channel=<channel>, priority=<priority>, status=<status>)"
```
where `<status>` is `"active"` or `"paused"`. Note the spaces after each comma.
Returns `None` if the campaign does not exist.

### `pause_campaign(campaign_id: str) -> bool`
- `True` if the campaign exists and was active (it becomes paused).
- `False` if the campaign does not exist **or was already paused**.

### `resume_campaign(campaign_id: str) -> bool`
- `True` if the campaign exists and was paused (it becomes active).
- `False` if the campaign does not exist **or was already active**.

### `delete_campaign(campaign_id: str) -> bool`
- `True` if the campaign existed and was removed.
- `False` if it did not exist.
- After deletion the id is free: re-creating it produces a **brand-new campaign**, active, with
  whatever channel and priority are supplied at re-creation. Nothing from the old campaign
  carries over.

### Worked example 1a
```python
s = CampaignScheduler()

s.create_campaign("summer-promo", "email", 8)   # True
s.create_campaign("summer-promo", "push", 2)    # False  (duplicate, no overwrite)
s.get_campaign("summer-promo")
# "summer-promo(channel=email, priority=8, status=active)"

s.pause_campaign("summer-promo")                # True
s.get_campaign("summer-promo")
# "summer-promo(channel=email, priority=8, status=paused)"
s.pause_campaign("summer-promo")                # False  (already paused)
s.resume_campaign("summer-promo")               # True
s.resume_campaign("summer-promo")               # False  (already active)

s.delete_campaign("summer-promo")               # True
s.get_campaign("summer-promo")                  # None
s.delete_campaign("summer-promo")               # False
s.pause_campaign("no-such-thing")               # False
```

### Worked example 1b — re-creation is a clean slate
```python
s = CampaignScheduler()
s.create_campaign("c", "email", 9)
s.pause_campaign("c")
s.delete_campaign("c")

s.create_campaign("c", "web", 2)                # True
s.get_campaign("c")
# "c(channel=web, priority=2, status=active)"   <- active, not paused
```

---

## Level 2 — Querying, ranking and aggregation (150 points, ~20 min)

> **READ THIS TWICE.** All three Level 2 methods report only **eligible** campaigns.
> At Level 2, *eligible* means **the campaign exists and its status is `active`.*
> Paused campaigns and deleted campaigns are invisible to all three. Level 3 will widen this
> definition — write it as one predicate you can change in one place.

**Canonical ranking**, used identically by both listing methods:
1. `priority` **descending**;
2. ties broken by `campaign_id` **ascending**, plain Python string comparison
   (so `"Mid" < "alpha" < "zeta"` — uppercase sorts first).

**Ranked listing format** (note: no channel, no status):
```
"<campaign_id>(priority=<priority>)"
```

### `list_by_channel(channel: str) -> list[str]`
Ranked list of eligible campaigns whose channel equals `channel` exactly (case-sensitive).
Returns `[]` for a channel with no eligible campaigns, including a channel that was never used.

### `top_campaigns(n: int) -> list[str]`
The first `n` entries of the ranked list of **all** eligible campaigns, across every channel.
- If `n` exceeds the number of eligible campaigns, return all of them (do not pad).
- If `n <= 0`, return `[]`.

### `count_active() -> int`
The number of eligible campaigns across all channels. `0` on an empty scheduler.

### Worked example 2a
```python
s = CampaignScheduler()
s.create_campaign("zeta",   "email", 5)
s.create_campaign("alpha",  "email", 5)
s.create_campaign("blast",  "email", 9)
s.create_campaign("push-a", "push",  7)

s.list_by_channel("email")
# ['blast(priority=9)', 'alpha(priority=5)', 'zeta(priority=5)']
s.list_by_channel("sms")        # []
s.top_campaigns(3)
# ['blast(priority=9)', 'push-a(priority=7)', 'alpha(priority=5)']
s.count_active()                # 4
```

### Worked example 2b — paused campaigns vanish from every query
```python
s.pause_campaign("blast")

s.list_by_channel("email")      # ['alpha(priority=5)', 'zeta(priority=5)']
s.top_campaigns(2)              # ['push-a(priority=7)', 'alpha(priority=5)']
s.count_active()                # 3
s.top_campaigns(0)              # []
s.top_campaigns(100)
# ['push-a(priority=7)', 'alpha(priority=5)', 'zeta(priority=5)']

s.get_campaign("blast")         # still works: "blast(channel=email, priority=9, status=paused)"
```

---

## Level 3 — Budgets and sliding-window rate limiting (150 points, ~30 min)

Delivery calls now carry an explicit integer `timestamp`. Timestamps are non-negative but are
**not guaranteed to be non-decreasing** across calls — evaluate every window against the
timestamp you are handed, never against "now".

### `__init__(self, window: int = 60, max_impressions_per_window: int = 5) -> None`

Widen the constructor you wrote at Level 1 to take two new parameters. **Keep both defaults**,
so the no-argument `CampaignScheduler()` used by Levels 1 and 2 still works unchanged.

- `window` (call it **W**) — the width of the sliding window, a positive integer.
- `max_impressions_per_window` — the maximum number of **successful** serves a *single*
  campaign may accumulate inside any window. Rate limits are **per campaign**, not global;
  every campaign gets its own allowance from the same shared W and maximum.

Both must be **positive integers**: raise `ValueError` if `window < 1` or if
`max_impressions_per_window < 1`. This is the one place in the whole exercise that raises;
every other rejection is a `False` return.

### Budgets

Every campaign has a **remaining budget**, an integer.
- A newly created campaign is **uncapped**. `remaining_budget` reports uncapped as **`-1`**.
- Uncapped campaigns never drain, no matter how much they serve.

#### `set_budget(campaign_id: str, budget: int) -> bool`
Sets the remaining budget to **exactly** `budget`, absolutely — prior spend is irrelevant, and
this may raise *or* lower the remaining amount.
- `False` if the campaign does not exist.
- `False` if `budget < 0`, with no change to state. (Consequence: once a budget is set there is
  no way back to uncapped. `-1` is a *report* value, not an accepted input.)
- `True` otherwise. `set_budget(id, 0)` is legal and immediately exhausts the campaign.

#### `remaining_budget(campaign_id: str) -> int | None`
- The remaining budget, or `-1` if the campaign is uncapped.
- **`None` if the campaign does not exist.** Distinguish these three carefully:
  `None` = no such campaign, `-1` = uncapped, `0` = exhausted.

### `serve(timestamp: int, campaign_id: str, cost: int) -> bool`

Delivers one impression. Returns `True` only if **all** of the following hold:
1. The campaign exists.
2. Its status is `active` (not paused).
3. `cost >= 1`.
4. The campaign is uncapped, **or** `remaining_budget >= cost` — the comparison is
   `>=`, so a serve that lands the budget on exactly `0` **succeeds**.
5. The number of impressions **already recorded** for this campaign — that is, every serve
   that succeeded in an *earlier call*, whatever its timestamp — whose recorded timestamp
   falls in the window **`(timestamp - W, timestamp]`** is **strictly less than**
   `max_impressions_per_window`.
   *"Previous" means previous in call order, not lower timestamp.* Because calls may arrive
   out of order, an already-recorded impression may sit at a timestamp **greater than** the
   one you are handed; such an impression is outside `(timestamp - W, timestamp]` and
   therefore does not count. Filter the whole recorded log by the window of the timestamp you
   were given — never discard an impression permanently just because a later-timestamped
   serve has been seen.

On success: deduct `cost` (uncapped campaigns stay at `-1`), record an impression at
`timestamp`, return `True`.

**On failure, return `False` and change nothing.** A rejected serve does not deduct budget and
does not consume a rate-limit slot.

> **Window boundary — exact semantics.** The window is **half-open: exclusive on the left,
> inclusive on the right.** An impression at exactly `timestamp - W` has *aged out* and does
> not count. An impression at `timestamp - W + 1` still counts. An impression at exactly
> `timestamp` (a same-tick earlier serve) counts.

### Effect on Level 2 — state this rule precisely

> **Eligibility is widened.** A campaign is *eligible* iff its status is `active` **AND** it is
> not budget-exhausted, where **exhausted means `remaining_budget == 0`**. Uncapped (`-1`) and
> any positive remaining budget are both fine.
>
> Therefore `list_by_channel`, `top_campaigns` and `count_active` must all **exclude
> campaigns whose remaining budget has reached exactly 0**, and must include them again if
> `set_budget` re-funds them.
>
> Two things that are deliberately *not* affected:
> - **`get_campaign` is unchanged.** Exhaustion is not a lifecycle status. An exhausted
    >   campaign still reports `status=active`.
> - **Rate limiting never affects listings.** Throttling is transient and depends on a
    >   timestamp; the Level 2 methods take no timestamp, so a currently-throttled campaign still
    >   appears in all listings.

### Worked example 3a — budget drain and exhaustion
```python
s = CampaignScheduler(window=10, max_impressions_per_window=2)
s.create_campaign("promo", "email", 5)

s.remaining_budget("promo")     # -1   (uncapped)
s.set_budget("promo", 100)      # True
s.serve(1, "promo", 40)         # True
s.remaining_budget("promo")     # 60
s.serve(2, "promo", 40)         # True   -> 20 left
s.serve(3, "promo", 10)         # False  rate limit: t=1 and t=2 both lie in (-7, 3]
s.serve(11, "promo", 10)        # True   window (1, 11] excludes t=1, holds only t=2 -> 10 left
s.serve(12, "promo", 10)        # True   window (2, 12] holds only t=11  -> 0 left

s.remaining_budget("promo")     # 0
s.count_active()                # 0      exhausted -> ineligible
s.list_by_channel("email")      # []
s.get_campaign("promo")
# "promo(channel=email, priority=5, status=active)"   <- status is untouched
s.serve(13, "promo", 1)         # False  no budget

s.set_budget("promo", 25)       # True   re-funding revives it
s.count_active()                # 1
```

### Worked example 3b — the window boundary
```python
s = CampaignScheduler(window=10, max_impressions_per_window=1)
s.create_campaign("c", "web", 1)

s.serve(100, "c", 1)            # True
s.serve(109, "c", 1)            # False  window (99, 109] still contains 100
s.serve(110, "c", 1)            # True   window (100, 110] excludes 100 -- aged out
```

### Worked example 3c — rejections are free
```python
s = CampaignScheduler(window=10, max_impressions_per_window=1)
s.create_campaign("c", "email", 1)
s.set_budget("c", 10)

s.serve(1, "c", 99)             # False  over budget
s.serve(1, "c", 0)              # False  cost must be >= 1
s.pause_campaign("c")
s.serve(1, "c", 5)              # False  paused
s.resume_campaign("c")

s.remaining_budget("c")         # 10     none of the failures cost anything
s.serve(1, "c", 5)              # True   the rate-limit slot was never consumed
```

### Worked example 3d — timestamps may go backwards
```python
s = CampaignScheduler(window=10, max_impressions_per_window=1)
s.create_campaign("c", "web", 1)

s.serve(100, "c", 1)            # True
s.serve(90, "c", 1)             # True   window (80, 90] is empty: t=100 is in the *future*
s.serve(99, "c", 1)             # False  window (89, 99] contains the impression at 90
s.serve(105, "c", 1)            # False  window (95, 105] contains the impression at 100
s.serve(111, "c", 1)            # True   (101, 111] holds neither 90 nor 100
```

---

## Level 4 — Snapshot, restore and audit trail (200 points, ~30 min)

### `snapshot(name: str) -> bool`
Captures the **entire system state** under `name`: which campaigns exist, their channels,
priorities, statuses, remaining budgets, and their sliding-window impression logs.
- Taking a snapshot with a name already in use **overwrites** the earlier capture.
- Returns `False` for an empty name (`""`), storing nothing. Otherwise `True`.
- A snapshot is a value, not a lock: later activity must not mutate a stored snapshot.

### `restore(name: str) -> bool`
Returns the system to the exact state captured by `snapshot(name)`.
- `False` if no snapshot by that name exists, **with no change to the current state**.
- `True` otherwise.

Precise semantics — all of these are graded:
- Campaigns created after the snapshot **cease to exist** (`get_campaign` → `None`,
  `remaining_budget` → `None`). Campaigns deleted after the snapshot **come back**.
- Budgets roll back to their snapshotted values.
- The impression log rolls back, so **serving after a restore behaves exactly as if the
  intervening serves had never happened** — including rate-limit availability at the very
  same timestamps.
- `history` rolls back too (see below).
- **The snapshot store itself is *not* part of the captured state.** Snapshots survive
  restores, so you may restore an early snapshot and then restore a later one.

### `history(campaign_id: str) -> list[str]`
The ordered audit trail of every **successful, state-changing** operation for that campaign,
oldest first. Failed operations (a rejected duplicate `create_campaign`, a redundant `pause`, a
rejected `serve`, a negative `set_budget`) are **never** recorded.

Exact strings:

| Operation | History entry |
|---|---|
| `create_campaign(id, channel, priority)` | `"create(channel=<channel>, priority=<priority>)"` |
| `pause_campaign(id)` | `"pause"` |
| `resume_campaign(id)` | `"resume"` |
| `delete_campaign(id)` | `"delete"` |
| `set_budget(id, b)` | `"set_budget(<b>)"` |
| successful `serve(t, id, cost)` | `"serve(t=<t>, cost=<cost>)"` |

- `snapshot` and `restore` are system-level and are **not** recorded in any campaign's history.
- Returns `[]` for an id that has never existed.
- **The audit trail outlives the campaign.** After `delete_campaign`, `get_campaign` returns
  `None` but `history` still returns the full trail ending in `"delete"`. Re-creating the id
  *appends* to that same trail.

### Worked example 4a — restore rewinds budget, throttle and history
```python
s = CampaignScheduler(window=10, max_impressions_per_window=2)
s.create_campaign("promo", "email", 5)
s.set_budget("promo", 100)
s.snapshot("baseline")          # True

s.serve(1, "promo", 30)         # True
s.serve(2, "promo", 30)         # True
s.serve(3, "promo", 30)         # False  rate limited
s.remaining_budget("promo")     # 40
s.history("promo")
# ['create(channel=email, priority=5)', 'set_budget(100)',
#  'serve(t=1, cost=30)', 'serve(t=2, cost=30)']

s.restore("baseline")           # True
s.remaining_budget("promo")     # 100
s.history("promo")
# ['create(channel=email, priority=5)', 'set_budget(100)']
s.serve(3, "promo", 30)         # True   the earlier serves never happened
```

### Worked example 4b — snapshots outlive restores
```python
s = CampaignScheduler()
s.snapshot("empty")             # taken before anything exists
s.create_campaign("a", "email", 5)
s.snapshot("with-a")
s.create_campaign("b", "push", 3)

s.restore("empty")              # True
s.get_campaign("a")             # None
s.history("a")                  # []
s.count_active()                # 0

s.restore("with-a")             # True   "with-a" is still reachable
s.get_campaign("a")             # "a(channel=email, priority=5, status=active)"
s.get_campaign("b")             # None
s.restore("nope")               # False  and nothing changed
s.count_active()                # 1
```

### Worked example 4c — history survives deletion
```python
s = CampaignScheduler()
s.create_campaign("a", "email", 1)
s.delete_campaign("a")
s.get_campaign("a")             # None
s.history("a")
# ['create(channel=email, priority=1)', 'delete']

s.create_campaign("a", "web", 2)
s.history("a")
# ['create(channel=email, priority=1)', 'delete', 'create(channel=web, priority=2)']
```

---

## Scoring

| Level | Points | Suggested time |
|---|---|---|
| 1 — lifecycle CRUD | 100 | 10 min |
| 2 — querying and ranking | 150 | 20 min |
| 3 — budgets and rate limiting | 150 | 30 min |
| 4 — snapshot / restore / audit | 200 | 30 min |
| **Total** | **600** | **90 min** |

A level scores only if its tests pass **with all later levels implemented**. A Level 3 change
that breaks a Level 1 contract forfeits Level 1.
