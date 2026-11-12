# ICF Mock 5 — `InMemoryDB`

**Format:** CodeSignal Industry Coding Framework · 90 minutes · 4 progressive levels · 600 points
**Language:** Python 3.11
**Theme:** Airbnb Payments — the in-memory record store behind wallet metadata (`wallet_a` has a `balance`, a `status`, a time-limited `promo`, …).

> This problem is a faithful rendering of a real circulating CodeSignal ICF problem. The signatures, the semantics and the output format are the source's; the ambiguities the source leaves open are resolved in **[Spec decisions](#spec-decisions)** below, and every one of them is pinned by a test.

---

## How to take this exam

1. Set a **90 minute timer**. Do not stop it between levels.
2. `cp starter.py attempt.py` and work only in `attempt.py`. **`starter.py` contains the Level 1 methods only.** Every later level lists its own method signatures in this document; when you reach a level, copy its signatures into your class and implement them there. That is how the real CodeSignal editor behaves — the next level's methods appear only once you have submitted the current one.
3. **Reveal one level at a time.** Read Level 1, implement it, run its tests, and only then scroll to Level 2. Peeking ahead defeats the entire point of the format — this problem in particular is testing whether your Level 1 data model survives Level 3.
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
6. Suggested budget: L1 10 min · L2 20 min · L3 25 min · L4 35 min. If you are over budget on a level, move on — partial credit across four levels beats a perfect Level 2.

### Global conventions (true for every level)

- The database maps a `key` to a **record**: a set of `field -> value` pairs. Different keys are completely independent; different fields of one key are completely independent.
- `key`, `field` and `value` are strings. The empty string is a legal `value` — `get` returning `""` is a **hit**, `get` returning `None` is a **miss**. Do not conflate them.
- Every operation takes an integer `timestamp` as its **first** argument. **Timestamps arrive non-decreasing** across calls; you will never be asked to write into the past.
- **Nothing raises.** A missing key, a missing field or an expired field is answered with `None`, `False` or `""` as appropriate for the method.
- Ordering of scan output is always fully specified — never rely on insertion order.

---

# Level 1 — Core operations

**~10 minutes · 100 points**

Implement the record store: each `key` holds a set of `field -> value` pairs.

### Methods

```python
set(timestamp: int, key: str, field: str, value: str) -> None
get(timestamp: int, key: str, field: str) -> Optional[str]
delete(timestamp: int, key: str, field: str) -> bool
```

### Contracts

| Method | Returns |
|---|---|
| `set` | `None`, always. Creates the record `key` if it does not exist, then creates or **overwrites** `field` on it. There is no "already exists" failure — `set` always succeeds. |
| `get` | The stored value of `key`/`field`, or `None` if the key does not exist, or the key exists but has no such field. |
| `delete` | `True` if `key`/`field` existed and was removed. `False` if the key does not exist, or the key exists but has no such field. |

### Edge cases

- `get` / `delete` on an empty database: `None` / `False`.
- `get` / `delete` on an existing key with a **missing field**: `None` / `False`. This is a distinct code path from a missing key; test both.
- `delete` is **not** idempotent in its return value: deleting the same field twice gives `True` then `False`.
- After a delete, `set` on the same field succeeds again and the field reads back normally.
- `value = ""` is legal and is a hit.
- The `timestamp` argument is unused at Level 1. Take it anyway — it is in the signature for a reason, and Level 3 will explain which one.

### Worked examples

```python
db = InMemoryDB()

db.set(1, "wallet_a", "balance", "100")     # -> None
db.set(2, "wallet_a", "status", "active")   # -> None

db.get(3, "wallet_a", "balance")            # -> '100'
db.get(3, "wallet_a", "currency")           # -> None   (key exists, field does not)
db.get(3, "wallet_zzz", "balance")          # -> None   (key does not exist)
```

```python
db.set(4, "wallet_a", "balance", "250")     # -> None   (overwrite, no error)
db.get(5, "wallet_a", "balance")            # -> '250'

db.delete(6, "wallet_a", "balance")         # -> True
db.get(7, "wallet_a", "balance")            # -> None
db.delete(8, "wallet_a", "balance")         # -> False  (already gone)
db.delete(9, "wallet_a", "currency")        # -> False  (never existed)
db.delete(10, "wallet_zzz", "balance")      # -> False  (no such key)

db.get(11, "wallet_a", "status")            # -> 'active'   (other fields untouched)
```

---

# Level 2 — Scan and aggregation

**~20 minutes · 150 points**

Add whole-record and prefix-filtered reads. These build on Level 1 — they must see exactly what `get` sees.

### Methods

```python
scan(timestamp: int, key: str) -> str
scan_by_prefix(timestamp: int, key: str, prefix: str) -> str
```

### Output format

Both methods return a **single formatted string**, not a list:

```
"field1(value1), field2(value2), field3(value3)"
```

The separator is a **comma followed by a space** — `", "`. Each entry is `field(value)` with no spaces inside it. The empty selection renders as the empty string `""`, never `"()"` and never `None`.

### Contracts

**`scan(timestamp, key)`** — every field of the record `key`, sorted by **field name ascending** (plain Python string ordering), formatted as above.
- Missing key → `""`.
- Existing key with no fields left (all deleted) → `""`.

**`scan_by_prefix(timestamp, key, prefix)`** — the same, restricted to fields whose **name** starts with `prefix`. The prefix filters the *field* name, never the key and never the value.
- `prefix = ""` matches every field, i.e. it is exactly `scan`.
- A `prefix` equal to a full field name matches that field (a string is a prefix of itself).
- No matching field, or a missing key → `""`.

### Edge cases

- Sorting is plain lexicographic string ordering, not numeric: `f1`, `f10`, `f2`.
- A single result has no separator at all: `"only(v)"`.
- Deleted fields are not in the output. Overwritten fields show the latest value.
- Records are isolated: scanning `wallet_b` never shows a field of `wallet_a`.

### Worked examples

```python
db = InMemoryDB()
db.set(1, "wallet_a", "status", "active")
db.set(1, "wallet_a", "balance", "100")
db.set(1, "wallet_a", "balance_pending", "20")
db.set(1, "wallet_a", "currency", "USD")

db.scan(2, "wallet_a")
# -> 'balance(100), balance_pending(20), currency(USD), status(active)'

db.scan_by_prefix(2, "wallet_a", "bal")
# -> 'balance(100), balance_pending(20)'

db.scan_by_prefix(2, "wallet_a", "")
# -> 'balance(100), balance_pending(20), currency(USD), status(active)'   (== scan)

db.scan_by_prefix(2, "wallet_a", "currency")   # -> 'currency(USD)'   (prefix == full name)
db.scan_by_prefix(2, "wallet_a", "zzz")        # -> ''
db.scan(2, "wallet_ghost")                     # -> ''
```

```python
db = InMemoryDB()
db.set(1, "k", "a", "1")
db.scan(2, "k")                    # -> 'a(1)'      (single entry, no separator)
db.delete(3, "k", "a")             # -> True
db.scan(4, "k")                    # -> ''          (record emptied out)

db.set(5, "k", "f10", "x")
db.set(5, "k", "f2",  "y")
db.set(5, "k", "f1",  "z")
db.scan_by_prefix(6, "k", "f")     # -> 'f1(z), f10(x), f2(y)'   (string order, not numeric)
```

---

# Level 3 — TTL

**~25 minutes · 150 points**

Some wallet metadata is temporary: a promo code, a payment hold, a fraud flag. A field can now be written with a **TTL** — a lifetime in ticks measured from the timestamp of the write.

### Methods

```python
set_with_ttl(timestamp: int, key: str, field: str, value: str, ttl: int) -> None
```

That is the only new method. **The rest of this level is a refactor**, and it is the real work.

### The liveness rule — memorise this exactly

A field written at time `t` with TTL `d` is **alive** for a query at time `q` when:

```
t <= q < t + d
```

**Inclusive at the start, exclusive at the end.** Alive at `t` itself, alive at `t + d - 1`, and **dead at exactly `t + d`**.

- Plain `set` is now defined as `set_with_ttl` with an **infinite** lifespan. It is not a separate mechanism; it is the degenerate case.
- `ttl <= 0` means the field is **dead on arrival** and never readable by anything — not even at `timestamp` itself. `set_with_ttl` still returns `None`; the write happened, it is just already expired.

### The refactor — every Level 1 and Level 2 method changes behaviour

An expired field is invisible to **everything**:

| Method | Behaviour on an expired field |
|---|---|
| `get` | `None` |
| `delete` | `False` — it was not there to delete |
| `scan` | skipped; if every field of the record has expired, the result is `""` |
| `scan_by_prefix` | skipped, same as `scan` |

If you find yourself writing the same `now < expires_at` comparison in five places, stop and pull it into **one predicate** that every read consults. That single choice is what this level is grading. A Level 1 model that stored a bare `value` per field has nowhere to put the expiry and must now have every value site rewritten; a Level 1 model that stored a `(value, expires_at)` record — with `expires_at = None` meaning "forever" — needs one new method and no edits at all.

### Overwrite semantics

| Write | Effect on an existing field |
|---|---|
| `set(t, k, f, v)` | Replaces the value **and clears any TTL** — the field becomes permanent again. |
| `set_with_ttl(t, k, f, v, ttl)` | Replaces the value **and the lifespan**, with the new lifespan measured from the **new** `t`: alive on `[t, t + ttl)`. Whatever the old expiry was is discarded. |

Both are plain overwrites. There is no such thing as "extending" a TTL or "inheriting" the previous one.

### Worked examples

```python
# --- boundaries, and dead-on-arrival TTLs ---
db = InMemoryDB()
db.set_with_ttl(10, "wallet_a", "balance", "100", 5)   # alive on [10, 15)

db.get(10, "wallet_a", "balance")     # -> '100'   inclusive start
db.get(14, "wallet_a", "balance")     # -> '100'   t + ttl - 1
db.get(15, "wallet_a", "balance")     # -> None    exclusive end
db.delete(15, "wallet_a", "balance")  # -> False   expired == not there

db.set_with_ttl(16, "wallet_a", "hold", "50",  0)      # ttl == 0
db.get(16, "wallet_a", "hold")        # -> None    dead on arrival
db.set_with_ttl(17, "wallet_a", "hold", "50", -3)      # ttl < 0
db.get(17, "wallet_a", "hold")        # -> None    dead on arrival
```

```python
# --- expiry sweeping through a record as the clock advances ---
db = InMemoryDB()
db.set(10, "wallet_a", "currency", "USD")                # permanent
db.set_with_ttl(10, "wallet_a", "promo", "SUMMER", 4)    # alive on [10, 14)
db.set_with_ttl(10, "wallet_a", "hold",  "50",     2)    # alive on [10, 12)

db.scan(11, "wallet_a")                   # -> 'currency(USD), hold(50), promo(SUMMER)'
db.scan(12, "wallet_a")                   # -> 'currency(USD), promo(SUMMER)'
db.scan(14, "wallet_a")                   # -> 'currency(USD)'

db.scan_by_prefix(11, "wallet_a", "h")    # -> 'hold(50)'
db.scan_by_prefix(12, "wallet_a", "h")    # -> ''
```

```python
# --- plain set clears a TTL; set_with_ttl re-arms from the new timestamp ---
db = InMemoryDB()
db.set_with_ttl(10, "wallet_a", "balance", "100", 5)   # would die at 15
db.set(12, "wallet_a", "balance", "200")               # now permanent
db.get(15,     "wallet_a", "balance")   # -> '200'   survives the old expiry
db.get(10**9,  "wallet_a", "balance")   # -> '200'

db.set_with_ttl(20, "wallet_a", "balance", "300", 5)   # re-armed: alive on [20, 25)
db.get(24, "wallet_a", "balance")       # -> '300'
db.get(25, "wallet_a", "balance")       # -> None
```

---

# Level 4 — Backup and restore

**~35 minutes · 200 points**

Payments needs point-in-time recovery: snapshot the database, and later roll the whole thing back to a snapshot.

### Methods

```python
backup(timestamp: int) -> int
restore(timestamp: int, time_to_restore: int) -> None
```

### `backup(timestamp)`

Take a snapshot of the database as it is at `timestamp`, and return the number of **records** (keys) that have **at least one live field**.

- Only **live** fields are snapshotted. Expired fields are not stored and do not count.
- A key whose fields have **all** expired is neither stored nor counted.
- The count is of **records, not fields**. A key with six live fields counts `1`.
- An empty database, or a database in which everything has expired, returns `0`.
- `backup` does not change the live state. It is a read plus an append to the backup history.

**Each snapshotted field stores its REMAINING lifespan, not its absolute expiry.** A field written at `10` with `ttl = 100` expires at `110`; backed up at `15` it is stored with `95` units remaining. A permanent field is stored as permanent. This is the entire point of the level — see [Why remaining and not absolute](#why-remaining-and-not-absolute).

### `restore(timestamp, time_to_restore)`

Find the **latest backup taken at or before `time_to_restore`** and make the database's state identical to it. Returns `None`.

- **`restore` replaces the entire state.** It is not a merge. Records created after the chosen backup are gone. Records or fields deleted after it come back. Values changed after it revert.
- **Restored TTLs resume relative to `timestamp`.** A field stored with `95` units remaining is alive on `[timestamp, timestamp + 95)`. Permanent fields stay permanent.
- If there is **no backup at or before `time_to_restore`**, `restore` is a **no-op**: the database is left exactly as it was.
- The backup history itself is not affected by a restore. You can restore and then take another backup, including at the very same timestamp.

<a id="why-remaining-and-not-absolute"></a>
### Why remaining and not absolute

`restore` moves the time origin, so a snapshot of absolute expiry instants is wrong the moment the clock jumps:

```python
db.set_with_ttl(10, "wallet_a", "balance", "100", 100)   # expires at 110
db.backup(15)                                            # 95 units remain
db.restore(1000, 15)
db.get(1000, "wallet_a", "balance")
```

Storing remaining lifespan, the field is alive on `[1000, 1095)` and that `get` returns `'100'`. Storing absolute expiry — which is what a `deepcopy` of your live state gives you — the field comes back carrying `expires_at = 110`, the clock is at `1000`, and the `get` returns `None`. The restore silently restored nothing. `deepcopy` is the natural reach under time pressure and it passes every test that does not jump the clock across a restore.

### Worked examples

```python
# --- restore replaces the whole state ---
db = InMemoryDB()
db.set(1, "wallet_a", "balance", "100")
db.set(1, "wallet_a", "status",  "active")
db.set(1, "wallet_b", "balance", "200")

db.backup(2)                        # -> 2      two records, three fields

db.set(3, "wallet_c", "balance", "300")   # created after the backup
db.delete(4, "wallet_b", "balance")       # -> True   deleted after the backup
db.set(5, "wallet_a", "balance", "999")   # changed after the backup
db.scan(5, "wallet_a")              # -> 'balance(999), status(active)'

db.restore(6, 2)                    # -> None
db.scan(6, "wallet_a")              # -> 'balance(100), status(active)'   reverted
db.scan(6, "wallet_b")              # -> 'balance(200)'                   resurrected
db.scan(6, "wallet_c")              # -> ''                               erased
```

```python
# --- TTLs resume from the restore timestamp ---
db = InMemoryDB()
db.set_with_ttl(10, "wallet_a", "balance", "100", 100)   # expires at 110
db.backup(15)                       # -> 1     stored with 95 units remaining
db.restore(1000, 15)                # -> None  alive on [1000, 1095)

db.get(1000, "wallet_a", "balance")   # -> '100'
db.get(1094, "wallet_a", "balance")   # -> '100'   1000 + 95 - 1
db.get(1095, "wallet_a", "balance")   # -> None    1000 + 95
db.scan(1094, "wallet_a")             # -> 'balance(100)'
db.scan(1095, "wallet_a")             # -> ''
```

```python
# --- backup counts records with a live field; restore picks the latest eligible one ---
db = InMemoryDB()
db.set_with_ttl(10, "wallet_a", "balance", "100", 5)   # alive on [10, 15)
db.set(10, "wallet_b", "status", "active")             # permanent

db.backup(14)                       # -> 2   'wallet_a' has 1 unit left
db.backup(15)                       # -> 1   'wallet_a' has expired: not stored, not counted

db.restore(20, 14)                  # -> None  balance resumes with 1 unit: [20, 21)
db.get(20, "wallet_a", "balance")   # -> '100'
db.get(21, "wallet_a", "balance")   # -> None

db.restore(30, 15)                  # -> None  that snapshot never held 'wallet_a'
db.get(30, "wallet_a", "balance")   # -> None
db.get(30, "wallet_b", "status")    # -> 'active'

db.restore(40, 9)                   # -> None  no backup at or before 9: no-op
db.get(40, "wallet_b", "status")    # -> 'active'   state untouched
```

---

<a id="spec-decisions"></a>
## Spec decisions

The source problem leaves the following open. These are the readings this kit implements and tests; if you resolved one differently in your attempt, that is worth a note, not a panic — but know which one you chose.

1. **The scan separator is `", "` — comma *and* space.** This differs from the other mocks in this kit, which use compact formats. Follow the source here. The empty selection is `""`.
2. **`scan` on a missing key, on a key whose fields have all expired, and on a key with no fields left all return `""`.** The three cases are indistinguishable from the outside; there is no "no such record" sentinel.
3. **`scan_by_prefix` with `prefix = ""` is exactly `scan`.** Every field name starts with the empty string.
4. **Plain `set` on a field that currently carries a TTL makes it permanent again.** `set` is `set_with_ttl` with an infinite lifespan, and it is a full overwrite of value *and* lifespan — so the TTL is cleared, not preserved.
5. **`set_with_ttl` on an existing field replaces both value and lifespan, and the new lifespan is measured from the new timestamp.** There is no accumulation or extension: `set_with_ttl(14, k, f, v, 5)` over a field written at `10` gives `[14, 19)`, not `[10, 19)` and not `[14, 15)`.
6. **`ttl <= 0` is dead on arrival.** With the half-open rule, `t <= q < t + 0` is empty, so the field is never readable — not even at `t`. Negative TTLs behave the same. The call still succeeds and returns `None`; there is no error.
7. **Liveness is half-open: `t <= q < t + ttl`.** Alive at `t + ttl - 1`, dead at exactly `t + ttl`. Both boundary instants are tested.
8. **`delete` on an expired field returns `False`, and the field is purged from storage.** Observably: the return is `False`, and afterwards `get` still returns `None`, `scan` still omits it, and `backup` still does not count it — identical to the field never having existed. The purge is an internal invariant with one purpose, to guarantee there is no path by which a stale expired entry could be resurrected by a later `restore`. A subsequent `set` on the same field recreates it normally.
9. **`backup` counts RECORDS, not fields.** A key with six live fields contributes `1`. A key whose fields have all expired contributes `0` and is not stored in the snapshot at all.
10. **`restore` replaces the entire state.** Records created after the chosen backup cease to exist; records and fields deleted after it come back; values changed after it revert. It is a wholesale swap, not a merge and not a field-level union.
11. **If no backup exists at or before `time_to_restore`, `restore` is a no-op.** The database is left exactly as it was, and nothing is raised.
12. **Two backups at the same timestamp: the later call wins.** Backups are an ordered history; the one selected is the last entry with `backup_timestamp <= time_to_restore`, resolving ties by call order.
13. **Remaining lifespan is computed at backup time as `expire_at - backup_timestamp`, and is always `>= 1` for anything stored.** A field with `0` remaining has already expired by the half-open rule and is therefore not live, not counted and not snapshotted.
14. **`restore` is an ordinary operation.** It can be immediately followed by a `backup` at the same timestamp, and that backup snapshots the just-restored state. There is no special case, no ordering constraint beyond the global non-decreasing-timestamp rule, and the backup history survives a restore untouched.

---

## Scoring

| Level | Points | Suggested time |
|---|---|---|
| 1 — Core operations | 100 | 10 min |
| 2 — Scan & aggregation | 150 | 20 min |
| 3 — TTL | 150 | 25 min |
| 4 — Backup & restore | 200 | 35 min |
| **Total** | **600** | **90 min** |

Levels 1 and 2 must still pass after Levels 3 and 4 are implemented. A Level 4 that breaks Level 1 scores 200, not 600.

## After the exam

Read the module docstring at the top of `solution.py` before reading the code. Two questions are worth answering honestly:

1. **When you added TTL at Level 3, how many methods did you edit?** If the answer is more than one plus the new `set_with_ttl`, your Level 1 storage was a `dict[key][field] -> str` and the level cost you a rewrite instead of a method. The fix costs three lines at Level 1: store a record carrying `(value, expires_at)` from the start, with `expires_at = None` meaning permanent, and route every read through one liveness predicate.
2. **Did your `backup` deep-copy the live state?** If so, run the Level 4 headline test — `test_restore_resumes_remaining_lifespan_after_a_far_clock_jump`. A snapshot has to store *durations*, because `restore` moves the origin of time. This is the single most common way a candidate loses Level 4 while believing it works, because every test that restores near the backup timestamp still passes.
