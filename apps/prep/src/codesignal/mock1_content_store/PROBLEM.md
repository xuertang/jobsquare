# ICF Mock 1 — `ContentStore`

**Format:** CodeSignal Industry Coding Framework · 90 minutes · 4 progressive levels · 600 points
**Language:** Python 3.11
**Theme:** Airbnb Content Platform — the repository that stores marketing content (hero copy, banners, host guides) served to guests and hosts.

> This problem is written to the conventions of the real circulating ICF problems (the same ones mocks 4–6 are reproduced from): **`timestamp` is the first argument of every method from Level 1 onwards**, even where the level never looks at it, and **every method that returns a collection returns one formatted string**. Both of those feel wrong the first time. Both are the format.

---

## How to take this exam

1. Set a **90 minute timer**. Do not stop it between levels.
2. `cp starter.py attempt.py` and work only in `attempt.py`. **`starter.py` contains the Level 1 methods only.** Every later level lists its own method signatures in this document; when you reach a level, copy its signatures into your class and implement them there. That is how the real CodeSignal editor behaves — the next level's methods appear only once you have submitted the current one.
3. **Reveal one level at a time.** Read Level 1, implement it, run its tests, and only then scroll to Level 2. Peeking ahead defeats the entire point of the format — the exam is testing whether your Level 1 data model survives Level 3.
4. Run tests per level:
   ```bash
   ICF_IMPL=attempt python3 -m pytest -q -m level1
   ICF_IMPL=attempt python3 -m pytest -q -m level2
   ICF_IMPL=attempt python3 -m pytest -q -m level3
   ICF_IMPL=attempt python3 -m pytest -q -m level4
   ```
5. **Backward compatibility is graded.** After Level 4, `-m level1` and `-m level2` must still pass. At the end, run the whole suite:
   ```bash
   ICF_IMPL=attempt python3 -m pytest -q
   ```
6. Suggested budget: L1 10 min · L2 20 min · L3 30 min · L4 30 min. If you are over budget on a level, move on — partial credit across four levels beats a perfect Level 2.
7. There is a consolidated **[Spec decisions](#spec-decisions)** section at the bottom of this document; it spans all four levels, so consult only the entry for the level you are currently on.

### Global conventions (true for every level)

- The class is named **`ContentStore`**. Every method takes `timestamp` as its **first** argument. Levels 1 and 2 never need to read it; it is there from the start anyway, and you should ask yourself why before you reach Level 3.
- `content_id` is a non-empty string; ids are unique within the store.
- `body` is an arbitrary string (the empty string is legal).
- `size` is a non-negative integer (0 is legal). It is metadata you store and rank by; it has nothing to do with `len(body)`.
- All timestamps and TTLs are integers.
- **Timestamps arrive non-decreasing for every mutating call** — `add_content`, `update_content`, `delete_content` and `rollback`. You will never be asked to insert a write into the middle of the history. **Reads may name any instant**, including one in the past.
- **Missing / not-visible content never raises.** Scalar readers return `None`; collection readers return `""`; mutators return `False`.
- **Every method that returns a collection returns a single string**, entries joined by `", "` — a comma and a space — and `""` when there is nothing to return. Never a list.
- Ordering of every returned string is fully specified. Never rely on dict insertion order.

---

# Level 1 — Basic CRUD

**~10 minutes · 100 points**

Implement a store that holds content records keyed by `content_id`.

### Signatures

```python
add_content(timestamp: int, content_id: str, body: str, size: int) -> bool
get_content(timestamp: int, content_id: str) -> Optional[str]
update_content(timestamp: int, content_id: str, body: str, size: int) -> bool
delete_content(timestamp: int, content_id: str) -> bool
```

> `timestamp` is the first argument of all four and **nothing at this level uses it**. That is not a typo and it is not padding. Copy the signatures exactly as given.

### Contracts

| Method | Returns |
|---|---|
| `add_content` | `True` if the content was stored. `False` if `content_id` already exists — and in that case **nothing is modified** (no overwrite of body or size). |
| `get_content` | The stored `body` string, or `None` if `content_id` does not exist (or was deleted). |
| `update_content` | `True` if the content existed and its `body` **and** `size` were both replaced. `False` if `content_id` does not exist — and in that case nothing is created. |
| `delete_content` | `True` if the content existed and was removed. `False` if `content_id` does not exist. |

### Edge cases

- `get` / `delete` / `update` on an empty store: `None` / `False` / `False`.
- `delete` is **not** idempotent in its return value: deleting the same id twice gives `True` then `False`.
- After a delete, `add_content` with the same id succeeds again (`True`).
- `body = ""` and `size = 0` are valid values, not "missing". `get_content` returning `""` is a hit; returning `None` is a miss. Do not conflate them.
- Several operations may share one `timestamp`. They apply in **call order** (Spec decisions #4).

### Worked example

```python
s = ContentStore()

s.add_content(1, "home-hero", "Belong anywhere", 4200)        # -> True
s.add_content(2, "home-hero", "Duplicate", 10)                # -> False  (no overwrite)
s.get_content(2, "home-hero")                                 # -> 'Belong anywhere'
s.get_content(2, "home-nope")                                 # -> None

s.update_content(3, "home-hero", "Belong anywhere v2", 4500)  # -> True
s.get_content(3, "home-hero")                                 # -> 'Belong anywhere v2'
s.update_content(4, "ghost", "x", 1)                          # -> False

s.delete_content(5, "home-hero")                              # -> True
s.get_content(5, "home-hero")                                 # -> None
s.delete_content(6, "home-hero")                              # -> False
```

---

# Level 2 — Prefix search and top-N ranking

**~20 minutes · 150 points**

Content ids are namespaced by product surface (`home-hero`, `home-banner`, `host-guide`). Add querying.

### Signatures

```python
find_by_prefix(timestamp: int, prefix: str) -> str
top_n_by_size(timestamp: int, prefix: str, n: int) -> str
```

`timestamp` is still unused at this level.

### Output format — read this twice

A **single string**, not a list. Each entry is

```
<content_id>(<size>)      e.g.  home-hero(4200)
```

with no spaces inside the entry and `size` rendered as a plain integer. Entries are joined by a **comma followed by a space**:

```
"home-banner(4200), home-footer(800), home-hero(4200)"
```

One entry has no separator. **Zero entries is the empty string `""`**, not `"()"` and not `[]`.

### Contracts

**`find_by_prefix(timestamp, prefix)`** — every existing content whose `content_id` starts with `prefix`, formatted as above, sorted by **`content_id` ascending** (plain Python string ordering).
- `prefix = ""` matches **everything**.
- A `prefix` equal to a full id matches that id (a string is a prefix of itself).
- No matches, or an empty store → `""`.
- Deleted content is not a match. Sizes reflect the most recent `update_content`.

**`top_n_by_size(timestamp, prefix, n)`** — the `n` largest content whose id starts with `prefix`, sorted by:
1. **`size` descending** (largest first), then
2. **`content_id` ascending** as the tie-break.

- If fewer than `n` items match, return all of them (never pad).
- `n <= 0` → `""`.
- No matches → `""`.
- Same `prefix` semantics as `find_by_prefix`.

### The design note you should read before writing this

Both methods are "select the visible records matching a prefix, order them, render them". Write **one** private helper that yields the visible `(id, record)` pairs for a prefix, and make both methods a sort plus a `", ".join` over it. Level 3 changes what *visible* means, in one place. Level 4 changes nothing here at all. Two hand-rolled scans instead means editing both, twice.

### Worked example

```python
s = ContentStore()
s.add_content(1, "home-hero",   "Belong anywhere", 4200)
s.add_content(1, "home-banner", "Summer sale",     4200)
s.add_content(1, "home-footer", "Legal",            800)
s.add_content(1, "host-guide",  "Hosting 101",     9000)

s.find_by_prefix(2, "home-")
# -> 'home-banner(4200), home-footer(800), home-hero(4200)'      # id ascending

s.find_by_prefix(2, "")
# -> 'home-banner(4200), home-footer(800), home-hero(4200), host-guide(9000)'

s.find_by_prefix(2, "zz")            # -> ''

s.top_n_by_size(2, "home-", 2)
# -> 'home-banner(4200), home-hero(4200)'   # tie on 4200 -> 'banner' < 'hero'

s.top_n_by_size(2, "", 3)
# -> 'host-guide(9000), home-banner(4200), home-hero(4200)'

s.top_n_by_size(2, "host-", 50)      # -> 'host-guide(9000)'   # n > match count
s.top_n_by_size(2, "home-", 0)       # -> ''

s.delete_content(3, "home-banner")
s.find_by_prefix(4, "home-")         # -> 'home-footer(800), home-hero(4200)'
```

---

# Level 3 — Time and TTL

**~30 minutes · 150 points**

Marketing content is scheduled: a promo banner is live for a campaign window and then must vanish. The `timestamp` you have been carrying since Level 1 now means something, and content can carry a **TTL** (a lifetime in ticks).

### Signatures

**No new methods.** One optional parameter is added to the two writers:

```python
add_content(timestamp: int, content_id: str, body: str, size: int,
            ttl: Optional[int] = None) -> bool
update_content(timestamp: int, content_id: str, body: str, size: int,
               ttl: Optional[int] = None) -> bool
```

`get_content`, `delete_content`, `find_by_prefix` and `top_n_by_size` keep the signatures you already have. Because `ttl` defaults to `None`, every Level 1 and Level 2 call site keeps working unchanged.

### The liveness rule — memorise this exactly

Content written at time `t` with TTL `d` is **live** for a query at time `q` when:

```
t <= q < t + d
```

That is: **inclusive at the start, exclusive at the end.** It is alive at `t` itself, alive at `t + d - 1`, and **dead at exactly `t + d`**.

- `ttl = None` means **never expires**.
- `ttl <= 0` means the content is dead the instant it is written. `add_content` still returns `True` (the write happened), but the content is immediately invisible to every reader.
- Content is invisible to any query at `q < t` — it does not exist yet.

### Contracts

**`add_content`** — `True` if written. `False` if content with that id is **live at `timestamp`** (then nothing changes). If the id previously existed but is now **deleted or expired**, the add **succeeds** and resurrects the id with fresh body, size and TTL.

**`get_content`** — the `body` if the id is live at `timestamp`, else `None`.

**`update_content`** — `False` if the id is not live at `timestamp` (an expired item **cannot** be updated back to life). Otherwise replaces `body` and `size`, and **renews the TTL from `timestamp`**:
- if `ttl` is `None` (the default), the item keeps its **current TTL duration**, restarting from `timestamp` → new expiry is `timestamp + current_duration`;
- if `ttl` is given, it **replaces** the duration → new expiry is `timestamp + ttl`;
- if the item's duration is `None` (never expires), it stays never-expiring.

This is the level's trap: an update at `t + d - 1` **rescues** content that was one tick from death.

**`delete_content`** — `True` if the id was live at `timestamp` and is now deleted; `False` otherwise. Deleting already-expired content returns `False`.

**`find_by_prefix` / `top_n_by_size`** — identical to Level 2, except only content **live at `timestamp`** is considered. All ordering, formatting and `n` rules are unchanged; an all-expired result is `""`.

### What this level is really asking

Nothing above is a new method. If Level 1 stored `dict[str, tuple[body, size]]` and threw `timestamp` away, you are now rewriting storage: you need to know when each record was written, what its duration is, and — one level from now — what it used to be. If Level 1 recorded a timestamped record per write, this level is one extra field and one comparison.

### Backward compatibility

There is no legacy API to delegate to and no second code path to maintain — the Level 1 and Level 2 methods *are* these methods. A workload that never passes `ttl` never expires anything and behaves exactly as it did in Levels 1–2.

### Worked examples

```python
# --- boundaries ---
s = ContentStore()
s.add_content(10, "a", "A", 100, ttl=5)   # live for q in [10, 15)
s.get_content(10, "a")   # -> 'A'      (inclusive start)
s.get_content(14, "a")   # -> 'A'      (t + ttl - 1)
s.get_content(15, "a")   # -> None     (exclusive end: dead at exactly t + ttl)
s.get_content( 9, "a")   # -> None     (does not exist yet)
```

```python
# --- TTL renewal and expiry sweeping through queries ---
s = ContentStore()
s.add_content(10, "home-hero",   "v1",    4200, 50)   # -> True   expires at 60
s.add_content(20, "home-banner", "promo",  900,  5)   # -> True   expires at 25

s.get_content(24, "home-banner")     # -> 'promo'
s.get_content(25, "home-banner")     # -> None
s.find_by_prefix(24, "home-")        # -> 'home-banner(900), home-hero(4200)'
s.find_by_prefix(25, "home-")        # -> 'home-hero(4200)'

s.update_content(59, "home-hero", "v2", 4300)   # -> True, rescued one tick early;
                                                #    TTL 50 restarts -> expires at 109
s.get_content(60,  "home-hero")      # -> 'v2'
s.get_content(108, "home-hero")      # -> 'v2'
s.get_content(109, "home-hero")      # -> None

s.add_content(109, "home-hero", "v3", 100, None)  # -> True (expired id is re-addable)
s.top_n_by_size(109, "", 5)          # -> 'home-hero(100)'
```

---

# Level 4 — History, point-in-time reads, and rollback

**~30 minutes · 200 points**

The content team ships a bad campaign and needs to reconstruct what a page looked like last Tuesday, then undo everything since.

### Signatures

```python
get_content_at_time(timestamp: int, content_id: str, time_at: int) -> Optional[str]
rollback(timestamp: int, time_at: int) -> int
```

`timestamp` is, as always, the clock for *this call* — "now". `time_at` is the past instant being asked about. Read the two apart carefully under time pressure: they are both integers and swapping them compiles.

### `get_content_at_time(timestamp, content_id, time_at)`

A **historical** read: the `body` that `content_id` had at `time_at`, considering only operations whose own timestamp is `<= time_at`, and applying the same liveness rule as Level 3.

- Returns `None` if the id had not been created yet at `time_at`, was deleted at or before `time_at`, or had already expired at `time_at`.
- Returns `None` for ids that never existed.
- Later operations are invisible to it: if the body was `"v1"` at `time_at = 15` and was updated to `"v2"` at `t = 20`, then `get_content_at_time(30, id, 15) == "v1"` **even after** the update has been applied.
- It is a read. It changes nothing.

### `rollback(timestamp, time_at)`

Restores the entire store to the state it had at `time_at`. "Now" is `timestamp`, the call's own first argument; there is no hidden clock. Let `delta = timestamp - time_at`.

1. **Every operation with an operation-timestamp `> time_at` is discarded**, along with its history. Content created after `time_at` ceases to exist entirely (`get_content_at_time` on it returns `None` for every query instant). Updates and deletes after `time_at` are undone.
2. **Survivors** are exactly the ids that were live at `time_at` (per the Level 3 liveness rule). Each survivor is re-asserted **at `timestamp`** with the `body`, `size` and TTL duration it had at `time_at`.
3. **TTLs are shifted forward by `delta`.** A survivor whose expiry was `E` now expires at `E + delta`. Equivalently: **whatever remaining lifetime an item had at `time_at`, it has that same remaining lifetime again at `timestamp`.** Content with `ttl = None` is unaffected — it still never expires.
4. Time does not run backwards. Subsequent calls are still expected to use timestamps `>= timestamp`.
5. If `time_at >= timestamp`, the rollback is a **no-op** (`delta = 0`, nothing is discarded, nothing is re-asserted).

**Returns:** the number of content items **live at `timestamp` once the rollback has completed** (`int`); `0` if the store is now empty. Note that this is deliberately *not* "the number live at `time_at`", and the two readings differ in both directions:

- an item that had already expired by `timestamp` but was live at `time_at` **is** counted, because its expiry has just been shifted past `timestamp`;
- in the no-op case (`time_at >= timestamp`) an item live at `timestamp` but expired by `time_at` is still counted, because nothing was discarded.

### Historical reads after a rollback

A rollback re-asserts each survivor **at `timestamp`** with a shifted expiry, and erases the operations in `(time_at, timestamp]`. A consequence worth stating explicitly: a historical read aimed *inside* that window can report an item as absent even though the same item is live at `timestamp`. The window is a genuine gap in the rewritten history, not a bug.

```python
s = ContentStore()
s.add_content(20, "b", "B1", 200, 5)   # expires at 25
s.get_content(40, "b")           # -> None  (expired)
s.rollback(40, 20)               # -> 1     delta = 20; b restored at 40, expires 45

s.get_content_at_time(40, "b", 30)   # -> None  ('b' had expired at 25 in the surviving history)
s.get_content(44, "b")               # -> 'B1'  (restored at now = 40 with 5 ticks left)
```

### Edge cases

- `rollback` on an empty store → `0`.
- `rollback(t, 0)` before anything existed → `0`, and the store is completely empty afterwards, including its history.
- Rolling back twice in a row is legal; the second rollback operates on the already-rewritten history.
- After a rollback, all normal mutations continue to work. An item restored with a shifted expiry can be updated (renewing from the update's timestamp) or deleted as usual.
- Backward compatibility still applies: the Level 1, 2 and 3 behaviours must be unchanged.

### The design note

`get_content_at_time` is the exam's verdict on your Level 1. If every write appended a timestamped record and "current state" was always *derived* from that log, this method is the derivation you already have, pointed at `time_at` instead of `timestamp` — five minutes. If you only ever stored current state, the information is gone, and you are retrofitting a log through four mutators with 30 minutes left.

The same log makes rollback tidy: truncate each id's log at `time_at`, then append one restore record per survivor at `timestamp` with the shifted expiry. No side table, no second notion of state.

### Worked examples

```python
# --- point-in-time reads ---
s = ContentStore()
s.add_content(10, "c", "v1", 100)
s.update_content(20, "c", "v2", 200)

s.get_content_at_time(30, "c", 15)   # -> 'v1'   (the update at t=20 is invisible)
s.get_content_at_time(30, "c", 20)   # -> 'v2'   (operations at exactly time_at are applied)
s.get_content_at_time(30, "c", 25)   # -> 'v2'
s.get_content_at_time(30, "c",  9)   # -> None   (did not exist yet)
```

```python
# --- rollback with TTL shifting ---
s = ContentStore()
s.add_content(10, "a", "A1", 100, 50)   # expires at 60
s.add_content(20, "b", "B1", 200,  5)   # expires at 25
s.update_content(30, "a", "A2", 700)    # renews: expires at 80

s.get_content_at_time(30, "a", 15)   # -> 'A1'
s.get_content_at_time(30, "a", 30)   # -> 'A2'
s.get_content_at_time(30, "b", 24)   # -> 'B1'
s.get_content_at_time(30, "b", 25)   # -> None   (expired, exclusive end)

s.get_content(40, "a")               # -> 'A2'

s.rollback(40, 20)                   # -> 2      now = 40, delta = 20
# State at t=20 was: a = 'A1' size 100 expiring at 60; b = 'B1' size 200 expiring at 25.
# The update at t=30 is discarded. Both survive, expiries shift by +20.

s.get_content_at_time(40, "a", 40)   # -> 'A1'   (the t=30 update is gone from history)
s.get_content(44, "b")               # -> 'B1'   b had 5 ticks left at t=20 -> dies at 45
s.get_content(45, "b")               # -> None
s.get_content(79, "a")               # -> 'A1'   a had 40 ticks left at t=20 -> dies at 80
s.get_content(80, "a")               # -> None
s.find_by_prefix(50, "")             # -> 'a(100)'   b already gone, a back to size 100
```

```python
# --- rollback discards newer content entirely ---
s = ContentStore()
s.add_content(10, "x", "X", 1)
s.add_content(20, "y", "Y", 2)

s.rollback(20, 15)                   # -> 1   (now = 20, delta = 5; 'y' never happened)
s.get_content(30, "x")               # -> 'X'
s.get_content(30, "y")               # -> None
s.get_content_at_time(30, "y", 20)   # -> None   (its history was erased too)
s.find_by_prefix(30, "")             # -> 'x(1)'
```

---

## Spec decisions

Where the contract above could be read two ways, this mock takes the following readings, and the test suite pins **every one of them** — the tests are not guessing.

| # | Question | Decision |
|---|---|---|
| 1 | Why does Level 1 take a `timestamp` it never uses? | Because the real format does. Every public method takes `timestamp` first from Level 1 onwards, including the ones that only start using it at Level 3 and the ones that never use it at all. Treat an unused Level 1 parameter as the format telling you what is coming. |
| 2 | What separates entries in a returned collection? | **`", "` — a comma and a space.** Every collection-returning method returns one string; an empty result is `""`. There is no list-returning method anywhere in this problem. |
| 3 | Is there a `current_time()` / logical clock? | **No.** Every method is handed "now" as its own `timestamp`, `rollback` included, so the store never needs to remember the largest timestamp it has seen. A method that took a clock reading from thin air would be the odd one out. |
| 4 | Two operations at the same `timestamp`? | Applied in **call order**. Same-instant ties never resolve arbitrarily. |
| 5 | Can a read name an instant in the past? | **Yes.** Only *mutating* calls are guaranteed non-decreasing. A read at `q` is answered from the history as of `q`, which is exactly why `get_content_at_time` costs nothing to add at Level 4. |
| 6 | `prefix = ""`? | Matches **everything**. A prefix equal to a full id matches that id. |
| 7 | Degenerate `n`? | `n <= 0` → `""`. `n` greater than the match count → all matches, no padding. |
| 8 | The liveness interval? | **Half-open: `t <= q < t + ttl`.** Alive at `t`, alive at `t + ttl - 1`, dead at exactly `t + ttl`. |
| 9 | `ttl <= 0`? | The write **happens** — `add_content` returns `True` — and the content is dead on arrival, invisible to every reader including one at `timestamp` itself. |
| 10 | `update_content` with `ttl` omitted? | Keeps the item's **current duration** and restarts it from `timestamp`. It does **not** keep the old absolute expiry, and it does **not** clear the TTL. An update at `t + ttl - 1` therefore rescues content one tick from death. |
| 11 | `update_content` on expired content? | `False`, and nothing is created. Expiry is not reversible by update; only a fresh `add_content` resurrects an id. |
| 12 | `delete_content` on expired content? | `False`. It was not live, so there was nothing to delete. |
| 13 | `add_content` over a deleted or expired id? | **Succeeds** (`True`) and resurrects the id with fresh body, size and TTL. Only content that is *live at `timestamp`* blocks an add. |
| 14 | `body = ""` versus missing? | Different. `get_content` returning `""` is a hit; `None` is a miss. Likewise `size = 0` is a legal size. |
| 15 | What does `rollback` return? | The number of items **live at `timestamp`** after the rollback finishes — not the number live at `time_at`. See the two asymmetric cases spelled out in Level 4. |
| 16 | `rollback` with `time_at >= timestamp`? | A **no-op**: nothing discarded, nothing shifted, nothing re-asserted. It still returns the live count at `timestamp`. |
| 17 | Does `rollback` erase history, or just current state? | **History.** An id created after `time_at` is gone entirely, and `get_content_at_time` cannot see it at any instant. The window `(time_at, timestamp]` becomes a real gap in the surviving ids' histories too. |
| 18 | Is `time_at > timestamp` meaningful for `get_content_at_time`? | Out of contract — it is a *historical* read, so `time_at <= timestamp` is expected. Not tested. |

---

## Scoring

| Level | Points | Suggested time |
|---|---|---|
| 1 — CRUD | 100 | 10 min |
| 2 — Prefix search & top-N | 150 | 20 min |
| 3 — Time & TTL | 150 | 30 min |
| 4 — History & rollback | 200 | 30 min |
| **Total** | **600** | **90 min** |

Levels 1 and 2 must still pass after Level 4 is implemented. A Level 4 that breaks Level 1 scores 200, not 600.

## After the exam

Read the module docstring at the top of `solution.py` before reading the code. If you had to significantly rewrite your storage between Level 2 and Level 3, or between Level 3 and Level 4, that is the lesson — and it is the single most common reason strong engineers run out of time on this format.

Then ask yourself one question honestly: when you reached Level 3, did `get_content` need editing? In the reference solution it did not, because it was already `_record_at(content_id, timestamp)` at Level 1 and that is still exactly what it is at Level 4.

---

## Stretch — "would you use a trie for the prefix search?"

Not part of the 90 minutes. This is the follow-up an interviewer asks in the round *after* the CodeSignal, and it is worth having a real answer to.

`solution.py` implements prefix search with a linear scan over the id keyspace. `solution_trie.py` is the same class — same public signatures, same `", "`-joined string returns — with a refcounted trie behind it, passing this identical test suite:

```bash
ICF_IMPL=solution_trie python3 -m pytest -q      # 68 passed
python3 bench_prefix.py                          # equivalence fuzz + timings
```

Three things to take from the comparison.

**The swap touches three private methods and no public one.** `_append`, `_truncate_after`, and `_live_records` — that is all. Every public method across four levels is untouched. That is not luck; it is what routing every prefix query through a single primitive buys you, and it is the same property that made Levels 3 and 4 cheap. The method people forget is `_truncate_after`, because the index has to be maintained when *rollback erases a log*, not when content is deleted — deleted content keeps its history and stays indexed.

**The trie is not a strict improvement.** Measured over 10,000 ids:

| query shape | scan | trie | |
|---|---|---|---|
| selective prefix (250 of 10,000 match) | 0.90 ms | 0.38 ms | 2.3× faster |
| broad prefix (all 10,000 match) | 10.02 ms | 18.05 ms | **1.8× slower** |
| count the matches, don't list them | 3.88 ms | 0.002 ms | ~2000× faster |

Enumerating a trie visits one node per character of every result, in Python, while `str.startswith` over a flat dict runs in C. Storing the full id on the terminal node instead of rebuilding it during traversal recovers a good chunk of that — it is what moves the selective case from 1.5× to 2.4× — but the broad-prefix loss is structural. Note also that the trie narrows candidates by prefix only; liveness still costs a `_record_at` per survivor, because TTLs are not something the index can know about.

**The third row is the only categorical win,** and it is the answer to give. Counting matches is a subtree refcount in O(len(prefix)), independent of how many match, and no scan does that at any keyspace size. If a problem asks *how many* rather than *which* — or asks for autocomplete, longest-common-prefix, or shortest-unique-prefix — it is trie-shaped and you should say so. Otherwise the linear scan is the senior answer, and knowing *why* is the thing actually being tested.
