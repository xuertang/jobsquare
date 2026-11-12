# ICF Mock 2 — `CampaignScheduler`

**Format:** CodeSignal Industry Coding Framework · 90 minutes · 4 progressive levels · 600 points
**Language:** Python 3.11
**Theme:** Content Platform / Marketing Technology — the delivery engine behind marketing campaigns.

> **Provenance.** The *scenario* here is original rather than lifted from a circulating
> problem. The *surface* is not: `timestamp` as the first parameter of every method from
> Level 1 onward, single-string returns for every collection, and the level split all follow
> the real ICF format exactly, so practising against this file trains the same reflexes as
> the sourced mocks in this kit. Every ambiguity is pinned in
> **[Spec decisions](#spec-decisions)** at the bottom, and every entry there has a test.

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

## Global conventions (true for every level)

- The class is named **`CampaignScheduler`**. **Every public method takes `timestamp: int` as
  its first argument**, from Level 1 onward — including the methods whose behaviour does not
  depend on it. Levels 1, 2 and 4 never read it. Keep it in the signature anyway: it is part
  of the contract the graders call, and it is the parameter Level 3 builds a sliding window
  out of.
- **Every method that reports a collection returns one string, never a list.** Entries are
  joined by **`", "` — a comma followed by a space**. A single entry carries no separator, and
  an empty result is the empty string `""`. This applies to `list_by_channel`, `top_campaigns`
  and `history`.
- Scalar readers return **`None`** when the thing asked about does not exist. Mutators return
  **`bool`**. Nothing anywhere returns a list, a tuple or a dict.
- **Timestamps are non-negative integers, and they arrive non-decreasing across calls — with
  exactly one deliberate exception, `serve`.** `serve` carries **no** monotonicity guarantee:
  it may be handed a timestamp lower than one you have already seen, and Level 3 specifies
  precisely what that must do. The two rules do not collide, because `serve` is the only
  method in the whole exercise whose result depends on the timestamp it is given; for every
  other method the guarantee is unobservable anyway.
- Ordering of every returned string is fully specified. Never rely on dict insertion order.
- A rejected operation changes **nothing** — no partial deduction, no consumed allowance.
- Nothing raises, anywhere, except the Level 3 constructor validating its own arguments.
  Every other rejection is a `False` or a `None`.

---

## Context

You are building the delivery engine behind marketing campaigns. A **campaign** targets one
**channel** (`"email"`, `"web"`, `"push"`, …) and carries an integer **priority**. Later levels
add spend budgets, per-campaign throttling, and an auditable rollback facility.

All state lives in one class, `CampaignScheduler`. Every level extends the same class.

---

## Level 1 — Campaign lifecycle (100 points, ~10 min)

### Signatures

```python
create_campaign(timestamp: int, campaign_id: str, channel: str, priority: int) -> bool
get_campaign(timestamp: int, campaign_id: str) -> str | None
pause_campaign(timestamp: int, campaign_id: str) -> bool
resume_campaign(timestamp: int, campaign_id: str) -> bool
delete_campaign(timestamp: int, campaign_id: str) -> bool
```

`__init__(self) -> None` creates an empty scheduler. `CampaignScheduler()` takes no arguments
at this level.

> **`timestamp` is unused at this level.** Every method accepts it; nothing reads it. Do not
> delete it from your signatures, and do not invent a meaning for it. It has one.

### `create_campaign(timestamp, campaign_id, channel, priority) -> bool`
Registers a new campaign in the **active** state.
- Returns `True` on success.
- Returns `False` if `campaign_id` already exists **and makes no change whatsoever** (the
  existing campaign keeps its original channel and priority — do not overwrite).
- `priority` may be zero or negative.

### `get_campaign(timestamp, campaign_id) -> str | None`
Returns exactly:
```
"<campaign_id>(channel=<channel>, priority=<priority>, status=<status>)"
```
where `<status>` is `"active"` or `"paused"`. Note the spaces after each comma.
Returns `None` if the campaign does not exist.

### `pause_campaign(timestamp, campaign_id) -> bool`
- `True` if the campaign exists and was active (it becomes paused).
- `False` if the campaign does not exist **or was already paused**.

### `resume_campaign(timestamp, campaign_id) -> bool`
- `True` if the campaign exists and was paused (it becomes active).
- `False` if the campaign does not exist **or was already active**.

### `delete_campaign(timestamp, campaign_id) -> bool`
- `True` if the campaign existed and was removed.
- `False` if it did not exist.
- After deletion the id is free: re-creating it produces a **brand-new campaign**, active, with
  whatever channel and priority are supplied at re-creation. Nothing from the old campaign
  carries over.

### Worked example 1a
```python
s = CampaignScheduler()

s.create_campaign(1, "summer-promo", "email", 8)   # True
s.create_campaign(2, "summer-promo", "push", 2)    # False  (duplicate, no overwrite)
s.get_campaign(3, "summer-promo")
# 'summer-promo(channel=email, priority=8, status=active)'

s.pause_campaign(4, "summer-promo")                # True
s.get_campaign(5, "summer-promo")
# 'summer-promo(channel=email, priority=8, status=paused)'
s.pause_campaign(6, "summer-promo")                # False  (already paused)
s.resume_campaign(7, "summer-promo")               # True
s.resume_campaign(8, "summer-promo")               # False  (already active)

s.delete_campaign(9, "summer-promo")               # True
s.get_campaign(10, "summer-promo")                 # None
s.delete_campaign(11, "summer-promo")              # False
s.pause_campaign(12, "no-such-thing")              # False
```

### Worked example 1b — re-creation is a clean slate
```python
s = CampaignScheduler()
s.create_campaign(1, "c", "email", 9)
s.pause_campaign(2, "c")
s.delete_campaign(3, "c")

s.create_campaign(4, "c", "web", 2)                # True
s.get_campaign(5, "c")
# 'c(channel=web, priority=2, status=active)'      <- active, not paused
```

---

## Level 2 — Querying, ranking and aggregation (150 points, ~20 min)

### Signatures

```python
list_by_channel(timestamp: int, channel: str) -> str
top_campaigns(timestamp: int, n: int) -> str
count_active(timestamp: int) -> int
```

`timestamp` is still unused. Still keep it.

> **READ THIS TWICE.** All three Level 2 methods report only **eligible** campaigns.
> At Level 2, *eligible* means **the campaign exists and its status is `active`.*
> Paused campaigns and deleted campaigns are invisible to all three. Level 3 will widen this
> definition — write it as one predicate you can change in one place.

**Canonical ranking**, used identically by both listing methods:
1. `priority` **descending**;
2. ties broken by `campaign_id` **ascending**, plain Python string comparison
   (so `"Mid" < "alpha" < "zeta"` — uppercase sorts first).

### Output format — read this twice

Both listing methods return **a single string, not a list**. Each entry is rendered
(note: no channel, no status):
```
"<campaign_id>(priority=<priority>)"
```
and entries are joined by **`", "` — a comma followed by a space**:
```
"blast(priority=9), alpha(priority=5), zeta(priority=5)"
```
One entry has no separator. Zero entries is the empty string `""`, never `"[]"` and never a
list. Entries contain commas of their own; nothing is quoted or escaped to hide that.

### `list_by_channel(timestamp, channel) -> str`
Ranked eligible campaigns whose channel equals `channel` exactly (case-sensitive).
Returns `""` for a channel with no eligible campaigns, including a channel never used.

### `top_campaigns(timestamp, n) -> str`
The first `n` entries of the ranked listing of **all** eligible campaigns, across every channel.
- If `n` exceeds the number of eligible campaigns, return all of them (do not pad).
- If `n <= 0`, return `""`.

### `count_active(timestamp) -> int`
The number of eligible campaigns across all channels. `0` on an empty scheduler.

### Worked example 2a
```python
s = CampaignScheduler()
s.create_campaign(1, "zeta",   "email", 5)
s.create_campaign(1, "alpha",  "email", 5)
s.create_campaign(1, "blast",  "email", 9)
s.create_campaign(1, "push-a", "push",  7)

s.list_by_channel(2, "email")
# 'blast(priority=9), alpha(priority=5), zeta(priority=5)'
s.list_by_channel(2, "sms")     # ''
s.top_campaigns(2, 3)
# 'blast(priority=9), push-a(priority=7), alpha(priority=5)'
s.count_active(2)               # 4
```

### Worked example 2b — paused campaigns vanish from every query
```python
s.pause_campaign(3, "blast")    # True

s.list_by_channel(4, "email")   # 'alpha(priority=5), zeta(priority=5)'
s.top_campaigns(4, 2)           # 'push-a(priority=7), alpha(priority=5)'
s.count_active(4)               # 3
s.top_campaigns(4, 0)           # ''
s.top_campaigns(4, 100)
# 'push-a(priority=7), alpha(priority=5), zeta(priority=5)'

s.get_campaign(4, "blast")      # still works:
# 'blast(channel=email, priority=9, status=paused)'
```

---

## Level 3 — Budgets and sliding-window rate limiting (150 points, ~30 min)

### Signatures

```python
__init__(self, window: int = 60, max_impressions_per_window: int = 5) -> None
set_budget(timestamp: int, campaign_id: str, amount: int) -> bool
remaining_budget(timestamp: int, campaign_id: str) -> int | None
serve(timestamp: int, campaign_id: str, cost: int) -> bool
```

**The `timestamp` you have been carrying since Level 1 now means something.** It is the instant
the call happens, and `serve` is judged against a window ending at it.

**`serve` timestamps are not guaranteed to be non-decreasing.** Every other method still gets
them in order; `serve` does not. Evaluate every window against the timestamp you were handed,
never against "now" and never against the highest timestamp you have seen.

### `__init__(self, window=60, max_impressions_per_window=5)`

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

#### `set_budget(timestamp, campaign_id, amount) -> bool`
Sets the remaining budget to **exactly** `amount`, absolutely — prior spend is irrelevant, and
this may raise *or* lower the remaining amount.
- `False` if the campaign does not exist.
- `False` if `amount < 0`, with no change to state. (Consequence: once a budget is set there is
  no way back to uncapped. `-1` is a *report* value, not an accepted input.)
- `True` otherwise. `set_budget(t, id, 0)` is legal and immediately exhausts the campaign.

#### `remaining_budget(timestamp, campaign_id) -> int | None`
- The remaining budget, or `-1` if the campaign is uncapped.
- **`None` if the campaign does not exist.** Distinguish these three carefully:
  `None` = no such campaign, `-1` = uncapped, `0` = exhausted.

### `serve(timestamp, campaign_id, cost) -> bool`

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
> - **Rate limiting never affects listings.** The three Level 2 methods take a `timestamp`,
>   so you *could* evaluate a window in them — do not. Throttling is transient state about a
>   moment; eligibility is about the campaign. A campaign that is currently rate-limited still
>   appears in every listing and still counts toward `count_active`.
>
> If you wrote one `_is_eligible(campaign)` predicate at Level 2, this whole section is a
> two-line edit to that one method and the three public methods do not change at all.

### Worked example 3a — budget drain and exhaustion
```python
s = CampaignScheduler(window=10, max_impressions_per_window=2)
s.create_campaign(0, "promo", "email", 5)

s.remaining_budget(0, "promo")  # -1   (uncapped)
s.set_budget(0, "promo", 100)   # True
s.serve(1, "promo", 40)         # True
s.remaining_budget(1, "promo")  # 60
s.serve(2, "promo", 40)         # True   -> 20 left
s.serve(3, "promo", 10)         # False  rate limit: t=1 and t=2 both lie in (-7, 3]
s.serve(11, "promo", 10)        # True   window (1, 11] excludes t=1, holds only t=2 -> 10 left
s.serve(12, "promo", 10)        # True   window (2, 12] holds only t=11  -> 0 left

s.remaining_budget(12, "promo") # 0
s.count_active(12)              # 0      exhausted -> ineligible
s.list_by_channel(12, "email")  # ''
s.get_campaign(12, "promo")
# 'promo(channel=email, priority=5, status=active)'   <- status is untouched
s.serve(13, "promo", 1)         # False  no budget

s.set_budget(14, "promo", 25)   # True   re-funding revives it
s.count_active(14)              # 1
```

### Worked example 3b — the window boundary
```python
s = CampaignScheduler(window=10, max_impressions_per_window=1)
s.create_campaign(0, "c", "web", 1)

s.serve(100, "c", 1)            # True
s.serve(109, "c", 1)            # False  window (99, 109] still contains 100
s.serve(110, "c", 1)            # True   window (100, 110] excludes 100 -- aged out
```

### Worked example 3c — rejections are free
```python
s = CampaignScheduler(window=10, max_impressions_per_window=1)
s.create_campaign(0, "c", "email", 1)
s.set_budget(0, "c", 10)

s.serve(1, "c", 99)             # False  over budget
s.serve(1, "c", 0)              # False  cost must be >= 1
s.pause_campaign(1, "c")        # True
s.serve(1, "c", 5)              # False  paused
s.resume_campaign(1, "c")       # True

s.remaining_budget(1, "c")      # 10     none of the failures cost anything
s.serve(1, "c", 5)              # True   the rate-limit slot was never consumed
```

### Worked example 3d — serve timestamps may go backwards
```python
s = CampaignScheduler(window=10, max_impressions_per_window=1)
s.create_campaign(0, "c", "web", 1)

s.serve(100, "c", 1)            # True
s.serve(90, "c", 1)             # True   window (80, 90] is empty: t=100 is in the *future*
s.serve(99, "c", 1)             # False  window (89, 99] contains the impression at 90
s.serve(105, "c", 1)            # False  window (95, 105] contains the impression at 100
s.serve(111, "c", 1)            # True   (101, 111] holds neither 90 nor 100
```

---

## Level 4 — Snapshot, restore and audit trail (200 points, ~30 min)

### Signatures

```python
snapshot(timestamp: int, name: str) -> bool
restore(timestamp: int, name: str) -> bool
history(timestamp: int, campaign_id: str) -> str
```

`timestamp` goes back to being unused here: a snapshot is of *state*, not of an instant, and
history is complete rather than windowed.

### `snapshot(timestamp, name) -> bool`
Captures the **entire system state** under `name`: which campaigns exist, their channels,
priorities, statuses, remaining budgets, and their sliding-window impression logs.
- Taking a snapshot with a name already in use **overwrites** the earlier capture.
- Returns `False` for an empty name (`""`), storing nothing. Otherwise `True`.
- A snapshot is a value, not a lock: later activity must not mutate a stored snapshot.

### `restore(timestamp, name) -> bool`
Returns the system to the exact state captured by `snapshot(t, name)`.
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

### `history(timestamp, campaign_id) -> str`
The ordered audit trail of every **successful, state-changing** operation for that campaign,
oldest first, as **one string with entries joined by `", "`**. Failed operations (a rejected
duplicate `create_campaign`, a redundant `pause`, a rejected `serve`, a negative `set_budget`)
are **never** recorded.

Exact entry strings:

| Operation | History entry |
|---|---|
| `create_campaign(t, id, channel, priority)` | `"create(channel=<channel>, priority=<priority>)"` |
| `pause_campaign(t, id)` | `"pause"` |
| `resume_campaign(t, id)` | `"resume"` |
| `delete_campaign(t, id)` | `"delete"` |
| `set_budget(t, id, amount)` | `"set_budget(<amount>)"` |
| successful `serve(t, id, cost)` | `"serve(t=<t>, cost=<cost>)"` |

So a full trail reads:
```
'create(channel=email, priority=8), set_budget(100), serve(t=3, cost=25), pause, resume, delete'
```
Yes, individual entries contain `", "` themselves. That is fine and is not escaped — the
format is a join, not a parseable encoding.

- Only `serve` records its timestamp; the other entries do not mention `t` at all, even though
  every method now receives one.
- `snapshot` and `restore` are system-level and are **not** recorded in any campaign's history.
- Returns `""` for an id that has never existed.
- **The audit trail outlives the campaign.** After `delete_campaign`, `get_campaign` returns
  `None` but `history` still returns the full trail ending in `"delete"`. Re-creating the id
  *appends* to that same trail.

### Worked example 4a — restore rewinds budget, throttle and history
```python
s = CampaignScheduler(window=10, max_impressions_per_window=2)
s.create_campaign(0, "promo", "email", 5)
s.set_budget(0, "promo", 100)
s.snapshot(0, "baseline")       # True

s.serve(1, "promo", 30)         # True
s.serve(2, "promo", 30)         # True
s.serve(3, "promo", 30)         # False  rate limited
s.remaining_budget(3, "promo")  # 40
s.history(3, "promo")
# 'create(channel=email, priority=5), set_budget(100), serve(t=1, cost=30), serve(t=2, cost=30)'

s.restore(3, "baseline")        # True
s.remaining_budget(3, "promo")  # 100
s.history(3, "promo")
# 'create(channel=email, priority=5), set_budget(100)'
s.serve(3, "promo", 30)         # True   the earlier serves never happened
```

### Worked example 4b — snapshots outlive restores
```python
s = CampaignScheduler()
s.snapshot(0, "empty")          # True   taken before anything exists
s.create_campaign(1, "a", "email", 5)
s.snapshot(2, "with-a")         # True
s.create_campaign(3, "b", "push", 3)

s.restore(4, "empty")           # True
s.get_campaign(4, "a")          # None
s.history(4, "a")               # ''
s.count_active(4)               # 0

s.restore(5, "with-a")          # True   "with-a" is still reachable
s.get_campaign(5, "a")          # 'a(channel=email, priority=5, status=active)'
s.get_campaign(5, "b")          # None
s.restore(5, "nope")            # False  and nothing changed
s.count_active(5)               # 1
```

### Worked example 4c — history survives deletion
```python
s = CampaignScheduler()
s.create_campaign(1, "a", "email", 1)
s.delete_campaign(2, "a")
s.get_campaign(3, "a")          # None
s.history(3, "a")
# 'create(channel=email, priority=1), delete'

s.create_campaign(4, "a", "web", 2)   # True
s.history(5, "a")
# 'create(channel=email, priority=1), delete, create(channel=web, priority=2)'
```

---

## Spec decisions

Where the contract above could be read two ways, this mock takes the following readings, and
the test suite pins **every one of them**. Consult only the entries for the level you are on.

| # | Level | Question | Decision |
|---|---|---|---|
| 1 | all | What separates entries in a returned collection? | **`", "` — a comma and a space.** An empty result is `""`, never `"[]"`, never a list. Entries that contain commas of their own are not quoted or escaped. |
| 2 | all | Why does Level 1 take a `timestamp` it never reads? | Because the format does. It is not decoration: Level 3 turns it into a sliding window. Removing it from your Level 1 signatures breaks the graders. |
| 3 | all | Are timestamps non-decreasing? | **Yes for every method except `serve`.** `serve` explicitly carries no such guarantee (Level 3, decision #10). Since `serve` is the only method whose result depends on its timestamp, the guarantee is unobservable elsewhere. |
| 4 | 1 | Does a duplicate `create_campaign` update anything? | **No.** It returns `False` and the existing channel, priority and status are untouched. |
| 5 | 1 | What does re-creating a deleted id produce? | A **brand-new active campaign** with the newly supplied channel and priority. No budget, no impressions, no paused flag carries over — but the audit trail does (decision #14). |
| 6 | 1 | Is `priority` constrained? | **No.** Zero and negative priorities are legal and rank normally. |
| 7 | 2 | What is the tie-break for equal priorities? | **`campaign_id` ascending under plain Python string comparison**, so uppercase sorts before lowercase: `"Mid" < "alpha" < "zeta"`. |
| 8 | 2 | Degenerate `n` for `top_campaigns`? | `n <= 0` → `""`. `n` greater than the eligible population → all of them, never padded. |
| 9 | 3 | What are the three `remaining_budget` outcomes? | **`None`** = no such campaign; **`-1`** = uncapped; **`0`** = exhausted. `-1` is a report value only — `set_budget` rejects any negative `amount`, so once capped a campaign can never return to uncapped. |
| 10 | 3 | May `serve` timestamps move backwards? | **Yes, deliberately.** Judge every serve against `(timestamp - W, timestamp]` for the timestamp you were handed. An impression already recorded at a *higher* timestamp is out of range, not deleted — it will block again when a serve near it arrives. |
| 11 | 3 | Which end of the window is inclusive? | **Half-open `(t - W, t]`**: an impression at exactly `t - W` has aged out; one at exactly `t` (a same-tick earlier serve) counts. |
| 12 | 3 | Does rate limiting affect the Level 2 listings? | **No** — even though those methods now receive a `timestamp` and could evaluate a window. Throttling is transient; eligibility is `active` and not exhausted, nothing more. Budget exhaustion *does* affect them; throttling never does. |
| 13 | 3 | Is exhaustion a status? | **No.** An exhausted campaign is invisible to the listings but `get_campaign` still reports `status=active`. Only `pause`/`resume` change status. |
| 14 | 4 | Does `history` survive `delete_campaign`? | **Yes.** The trail outlives the campaign and ends in `"delete"`; re-creating the id appends to the same trail rather than starting a new one. |
| 15 | 4 | Do non-`serve` history entries record their timestamp? | **No.** Only `"serve(t=…, cost=…)"` mentions the timestamp, even though every method now receives one. |
| 16 | 4 | Is the snapshot store part of the captured state? | **No.** Snapshots survive restores, so you can restore an early snapshot and then a later one. Restoring only rewinds campaigns, budgets, impressions and history. |
| 17 | 4 | Are `snapshot` and `restore` audited? | **No.** They are system-level and appear in no campaign's history. |

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

## After the exam

Read the module docstring at the top of `solution.py` before reading the code. It names the
two decisions the whole exam turns on — the append-only event log with a dumb replayer, and
the single `_is_eligible` predicate — and what the naive alternatives cost.

Then ask yourself two questions honestly. When Level 3 widened *eligible*, did you edit one
method or three? And when Level 4 asked you to roll back a rate limit, did you have the past,
or did you deep-copy the present and quietly share that per-campaign impression list?
