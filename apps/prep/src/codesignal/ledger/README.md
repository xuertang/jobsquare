# `Ledger`

**Format:** CodeSignal Industry Coding Framework · 90 minutes · 4 progressive levels · 600 points
**Language:** Python 3.11
**Theme:** Airbnb Payments — the in-memory ledger behind host payouts, guest refunds and scheduled disbursements.

> Sourced from a real circulating CodeSignal ICF problem. The signatures, the return types and the output format are reproduced as given; nothing has been redesigned to be friendlier.

---

## How to take this exam

1. Set a **90 minute timer**. Do not stop it between levels.
2. `cp starter.py attempt.py` and work only in `attempt.py`. **`starter.py` contains the Level 1 methods only.** Every later level lists its own method signatures in this document; when you reach a level, copy its signatures into your class and implement them there. That is how the real CodeSignal editor behaves — the next level's methods appear only once you have submitted the current one.
3. **Reveal one level at a time.** Read Level 1, implement it, run its tests, and only then scroll to Level 2. Peeking ahead defeats the entire point of the format — the exam is testing whether your Level 1 data model survives Levels 3 and 4.
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

### Global conventions (true for every level)

- The class is named **`Ledger`**. Every method takes `timestamp` as its **first** argument.
- `account_id` is a non-empty string; ids are unique among *existing* accounts.
- **Balances are integers** and are never negative: an operation that would overdraw is refused, not partially applied.
- **`amount` is a positive integer.** `amount <= 0` is out of contract and is not tested; you may do whatever you like with it.
- **Timestamps arrive non-decreasing** across calls. You will never be asked to insert an operation into the past.
- **Missing accounts never raise.** Readers and value-returning mutators return `None`; boolean mutators return `False`.
- A refused operation changes **nothing** — no partial debit, no partial credit.
- Ordering of every returned string is fully specified. Never rely on dict insertion order.

---

# Level 1 — Core operations

**~10 minutes · 100 points**

Accounts, deposits and transfers.

### Signatures

```python
create_account(timestamp: int, account_id: str) -> bool
deposit(timestamp: int, account_id: str, amount: int) -> Optional[int]
transfer(timestamp: int, source_id: str, target_id: str, amount: int) -> Optional[int]
```

### Contracts

| Method | Returns |
|---|---|
| `create_account` | `True` if a new account was opened with **balance 0**. `False` if `account_id` already exists — and in that case **nothing is modified** (the existing balance is not reset). |
| `deposit` | The account's **new balance** after adding `amount`. `None` if the account does not exist — and nothing is created. |
| `transfer` | The **source's new balance** after moving `amount` from `source_id` to `target_id`. `None` if either account is missing, if `source_id == target_id`, or if the source's balance is `< amount`. |

### Edge cases

- A brand-new account has balance `0`, so any transfer out of it fails immediately.
- `transfer` where the source balance is **exactly** `amount` succeeds and returns `0`. Only `balance < amount` fails.
- `transfer(t, "a", "a", x)` is **always** `None`, even when `a` exists and has the money. A self-transfer is not a no-op success.
- A failed transfer must leave *both* balances untouched — check every failure condition before you move anything.
- There is no way to read a balance in Levels 1–3. `deposit` returning the new balance is the only observation point; the test suite uses a deposit of `1` as a probe. `get_balance` arrives in Level 4.

### Worked example A — accounts and deposits

```python
led = Ledger()

led.create_account(1, "alice")     # -> True
led.create_account(2, "alice")     # -> False   (duplicate; balance untouched)
led.deposit(3, "alice", 500)       # -> 500
led.deposit(4, "alice", 250)       # -> 750
led.deposit(5, "ghost", 100)       # -> None    (no such account)
```

### Worked example B — transfers and every way they fail

```python
led = Ledger()
led.create_account(1, "alice")
led.create_account(1, "bob")

led.deposit(2, "alice", 300)             # -> 300
led.transfer(3, "alice", "bob", 100)     # -> 200   (source's new balance)
led.transfer(4, "alice", "bob", 500)     # -> None  (insufficient funds)
led.transfer(5, "alice", "alice", 10)    # -> None  (self-transfer)
led.transfer(6, "alice", "ghost", 10)    # -> None  (missing target)
led.transfer(7, "alice", "bob", 200)     # -> 0     (exactly the balance: allowed)
led.deposit(8, "bob", 1)                 # -> 301   (bob got 100 + 200)
```

---

# Level 2 — Aggregation

**~20 minutes · 150 points**

Finance wants to know who is moving the most money.

### Signatures

```python
top_spenders(timestamp: int, n: int) -> str
```

### Contract

Rank **every existing account** by its **total outgoing amount** — the sum of everything it has ever sent via `transfer` — and return the top `n`.

Sort by:
1. **outgoing total descending**, then
2. **`account_id` ascending** as the tie-break.

### Output format — read this twice

A **single string**, not a list:

```
"id1(amt1), id2(amt2), id3(amt3)"
```

The separator is a **comma followed by a space**. One entry has no separator. Zero entries is the **empty string** `""`.

### Edge cases

- **Accounts with zero outgoing are included.** They simply sort last (see Spec decisions #1).
- `n <= 0` → `""`.
- `n` greater than the number of accounts → all accounts, never padded.
- An empty ledger → `""` for any `n`.
- **Receiving** money is not spending. Only the source side of a transfer accrues.
- A **failed** transfer accrues nothing — a rejected self-transfer or an overdraw must not move the total.

### The design note you should read before writing this

If your Level 1 `transfer` already incremented a per-account `outgoing` counter, this level is a sort and a `join` — about four lines. If it did not, you are now scanning something to reconstruct the totals, and you will pay for it again in Level 3 when a second thing starts spending money. Fix the model, not the method.

### Worked example A — ranking, ties and `n`

```python
led = Ledger()
for acct in ("alice", "bob", "carol", "dave"):
    led.create_account(1, acct)
    led.deposit(1, acct, 1000)

led.transfer(2, "alice", "dave", 300)    # -> 700
led.transfer(3, "bob", "dave", 200)      # -> 800
led.transfer(4, "bob", "carol", 100)     # -> 700
led.transfer(5, "carol", "dave", 100)    # -> 1000

led.top_spenders(6, 3)    # -> 'alice(300), bob(300), carol(100)'
led.top_spenders(6, 4)    # -> 'alice(300), bob(300), carol(100), dave(0)'
led.top_spenders(6, 99)   # -> 'alice(300), bob(300), carol(100), dave(0)'
led.top_spenders(6, 1)    # -> 'alice(300)'
led.top_spenders(6, 0)    # -> ''
led.top_spenders(6, -2)   # -> ''
```

`alice` and `bob` both sent 300; `'alice' < 'bob'`, so alice is first. `dave` received 600 and sent nothing, so it ranks last with `dave(0)`.

### Worked example B — empty ledger and the tie-break

```python
Ledger().top_spenders(1, 5)              # -> ''

led = Ledger()
led.create_account(1, "zoe")
led.create_account(1, "amy")
led.create_account(1, "sink")
led.deposit(2, "zoe", 500)
led.deposit(2, "amy", 500)
led.transfer(3, "zoe", "sink", 500)      # -> 0
led.transfer(3, "amy", "sink", 500)      # -> 0

led.top_spenders(4, 3)   # -> 'amy(500), zoe(500), sink(0)'
```

---

# Level 3 — Scheduled payments

**~30 minutes · 150 points**

Payouts are scheduled ahead of time and can be cancelled before they land.

### Signatures

```python
schedule_payment(timestamp: int, account_id: str, amount: int, delay: int) -> Optional[str]
cancel_payment(timestamp: int, account_id: str, payment_id: str) -> bool
```

### Contracts

| Method | Returns |
|---|---|
| `schedule_payment` | A unique payment id — `"payment1"`, `"payment2"`, … — after registering an outgoing payment of `amount` to execute at `timestamp + delay`. **Nothing happens to the balance now.** `None` if `account_id` does not exist. |
| `cancel_payment` | `True` if a **not-yet-executed** payment with that id, **owned by `account_id`**, was cancelled. `False` if the id is unknown, already executed, already cancelled, or belongs to a different account. |

Payment ids are **globally sequential** across all accounts, starting at `"payment1"` (Spec decisions #6).

### Execution semantics — the whole level is here

**At the start of every operation** — every public method, mutator or reader, from every level — execute all pending payments whose scheduled time is `<= timestamp`, in order of:

1. **scheduled time ascending**, then
2. **creation order** (the order `schedule_payment` was called).

For each such payment, with `account` being its **current owner**:

- if `account.balance >= amount`: **deduct** `amount` from the balance and **add** `amount` to the account's outgoing total, so it counts toward `top_spenders`;
- otherwise the payment **fails**: it is **discarded** with no effect at all — no deduction, no outgoing credit, and **no retry later**.

Consequences you must get right:

- **A payment never reserves balance.** Between scheduling and execution the money is fully spendable, and the balance is only checked at execution time (Spec decisions #4).
- **`delay = 0` means due immediately — which still means the *next* operation.** `schedule_payment` registers the payment and returns; it does not execute it, not even its own. The first operation at or after that timestamp drains it (Spec decisions #8).
- **Due payments run before the current call's own logic**, including before `cancel_payment` looks anything up. So cancelling **at or after** the scheduled time returns `False` — the payment has already gone (Spec decisions #5).
- A read such as `top_spenders` triggers execution exactly like a write does.

### The refactor this level is testing

Written naively, "at the start of every operation" becomes the same loop pasted into every method — and the two people forget are `cancel_payment` and, next level, `get_balance`. Write one private `_process_due(timestamp)` and make it the first statement of every public method. Level 4 then changes *who a payment is billed to* without touching that loop at all.

### Edge cases

- `cancel_payment` for an id that never existed → `False`.
- `cancel_payment` called twice → `True` then `False`.
- `cancel_payment` with the right id but the wrong `account_id` → `False`, **and the payment stays pending**. It is not cancelled by a stranger.
- Two payments due at the same instant execute in creation order — so the first can drain the balance and make the second fail.
- A payment scheduled for the far future simply sits there; a ledger that is never touched again never executes it.

### Worked example A — `delay = 0` fires on the next call, not this one

```python
led = Ledger()
led.create_account(1, "alice")
led.deposit(1, "alice", 1000)              # -> 1000

led.schedule_payment(5, "alice", 400, 0)   # -> 'payment1'   due at 5, nothing deducted yet
led.deposit(5, "alice", 1)                 # -> 601          this call executed it: 1000 - 400 + 1
```

### Worked example B — cancellation, ownership and the too-late case

```python
led = Ledger()
led.create_account(1, "alice")
led.create_account(1, "bob")
led.deposit(1, "alice", 1000)

led.schedule_payment(2, "alice", 400, 10)     # -> 'payment1'   due at 12
led.schedule_payment(2, "alice", 100, 20)     # -> 'payment2'   due at 22
led.schedule_payment(2, "ghost", 100, 1)      # -> None         no such account

led.cancel_payment(3, "bob", "payment1")      # -> False   wrong owner (still pending!)
led.cancel_payment(3, "alice", "payment9")    # -> False   unknown id
led.cancel_payment(3, "alice", "payment2")    # -> True    cancelled before its due time

led.cancel_payment(12, "alice", "payment1")   # -> False   too late: it ran at the top of this call
led.deposit(12, "alice", 1)                   # -> 601     1000 - 400 + 1
led.top_spenders(12, 1)                       # -> 'alice(400)'
```

### Worked example C — same due time, creation order, and a failure that is discarded

```python
led = Ledger()
led.create_account(1, "alice")
led.deposit(1, "alice", 100)

led.schedule_payment(2, "alice", 60, 5)   # -> 'payment1'   due at 7
led.schedule_payment(2, "alice", 60, 5)   # -> 'payment2'   due at 7

led.deposit(7, "alice", 1)   # -> 41   payment1 took 60 (100 -> 40); payment2 failed and was dropped
led.top_spenders(7, 1)       # -> 'alice(60)'   only the successful payment counts
```

---

# Level 4 — Merges and historical balances

**~30 minutes · 200 points**

Two host accounts turn out to be the same person, and Finance wants to know what a balance was last Tuesday.

### Signatures

```python
merge_accounts(timestamp: int, id_1: str, id_2: str) -> bool
get_balance(timestamp: int, account_id: str, time_at: int) -> Optional[int]
```

### `merge_accounts(timestamp, id_1, id_2)`

Merge `id_2` **into** `id_1`. The direction matters: `id_1` survives, `id_2` disappears.

`id_1` absorbs, at `timestamp`:

- `id_2`'s **balance** (added to its own);
- `id_2`'s **outgoing total** (added to its own, so `top_spenders` reflects the union);
- `id_2`'s **pending payments** — they keep their existing payment ids, still fire at their original scheduled times, and are now **billed to `id_1`'s balance**.

`id_2` is then removed: it no longer exists for `deposit`, `transfer`, `create_account` duplication, `top_spenders`, or as a payment owner.

Returns `True` on success. `False` if either account is missing or `id_1 == id_2` — and then nothing is modified.

**`cancel_payment(t, id_1, "paymentX")` must work for a payment that originally belonged to `id_2`**, and `cancel_payment(t, id_2, "paymentX")` must not — `id_2` is not an account any more.

### `get_balance(timestamp, account_id, time_at)`

The balance `account_id` held **as of `time_at`**, considering every effect whose own time is `<= time_at`. Returns `None` if the account did not exist at `time_at`.

- `timestamp` is the clock for *this call* — due payments are executed first, as always. `time_at` is the instant being asked about.
- Effects at exactly `time_at` **are** included: a deposit at `t=10` is visible to `get_balance(20, id, 10)`.
- Before the account was created → `None`. For an id that never existed → `None`.
- A scheduled payment is recorded **at its scheduled instant**, not at the instant of the operation that happened to trigger it. A payment due at 15 and drained by a call at 20 makes `get_balance(20, id, 14)` and `get_balance(20, id, 15)` differ.
- **This must stay correct for an account that was later merged away** — see Spec decisions #10 and #11.

### The design note

This method is the exam's verdict on your Level 1. If every balance change appended to a per-account, time-ordered `(timestamp, balance)` log, `get_balance` is a binary search over that list and takes five minutes. If you only ever stored the current balance, the information is gone and you are retrofitting a log through `deposit`, `transfer`, the payment executor and the merge — with 25 minutes left.

The same log makes the merge tidy: don't delete `id_2`'s history, append a *tombstone* to it. A read before the merge resolves normally; a read at or after it lands on the tombstone and returns `None`.

### Edge cases

- `merge_accounts(t, "a", "a")` → `False`, even if `a` exists.
- Merging an account that has already been merged away → `False` (it no longer exists).
- After a merge, `create_account` with the freed id **succeeds** — and history keeps all three eras straight: the old account, the gap, the new one.
- An inherited payment can now succeed where it would have failed, because `id_1`'s balance is bigger. That is the point of the merge.
- Levels 1–3 must still behave exactly as specified, on a ledger that also has payments and merges in flight.

### Worked example A — a merge absorbs balance, spending and identity

```python
led = Ledger()
for acct in ("alice", "bob", "sink"):
    led.create_account(1, acct)
led.deposit(1, "alice", 500)
led.deposit(1, "bob", 200)

led.transfer(2, "alice", "sink", 100)    # -> 400
led.transfer(2, "bob", "sink", 50)       # -> 150

led.merge_accounts(5, "alice", "bob")    # -> True
led.get_balance(6, "alice", 6)           # -> 550    400 + 150
led.top_spenders(6, 5)                   # -> 'alice(150), sink(0)'   100 + 50; bob is gone
led.deposit(6, "bob", 10)                # -> None   bob no longer exists
led.merge_accounts(7, "alice", "alice")  # -> False  same id
led.merge_accounts(7, "alice", "bob")    # -> False  bob is not an account any more
```

### Worked example B — historical reads

```python
led = Ledger()
led.create_account(5, "alice")
led.deposit(10, "alice", 100)
led.deposit(20, "alice", 50)

led.get_balance(30, "alice",  4)   # -> None   did not exist yet
led.get_balance(30, "alice",  5)   # -> 0      created here, with balance 0
led.get_balance(30, "alice",  9)   # -> 0
led.get_balance(30, "alice", 10)   # -> 100    effects at exactly time_at count
led.get_balance(30, "alice", 19)   # -> 100
led.get_balance(30, "alice", 20)   # -> 150
led.get_balance(30, "ghost",  10)  # -> None
```

### Worked example C — history across a merge, from both sides

```python
led = Ledger()
led.create_account(1, "alice")
led.create_account(1, "bob")
led.deposit(2, "alice", 100)
led.deposit(2, "bob", 250)

led.merge_accounts(5, "alice", "bob")    # -> True

led.get_balance(10, "bob",   4)   # -> 250    bob's history survives the merge
led.get_balance(10, "bob",   5)   # -> None   bob stopped existing at t=5
led.get_balance(10, "bob",  10)   # -> None
led.get_balance(10, "alice", 4)   # -> 100    alice's own past, without bob's money
led.get_balance(10, "alice", 5)   # -> 350    the merge is an event at its own timestamp
```

### Worked example D — an inherited payment fires against the survivor

```python
led = Ledger()
led.create_account(1, "alice")
led.create_account(1, "bob")
led.deposit(1, "alice", 500)                # bob has 0 and could never afford this alone

led.schedule_payment(2, "bob", 300, 20)     # -> 'payment1'   due at 22
led.merge_accounts(3, "alice", "bob")       # -> True
led.cancel_payment(4, "bob", "payment1")    # -> False   bob is not an account any more
                                            #            (alice could cancel it here)
led.get_balance(22, "alice", 21)   # -> 500   still pending at 21
led.get_balance(22, "alice", 22)   # -> 200   executed at 22, billed to alice
led.top_spenders(22, 1)            # -> 'alice(300)'
```

---

## Spec decisions

The source problem is terse. Where it is silent, this mock takes the following readings, and the test suite pins **every one of them** — the tests are not guessing.

| # | Question | Decision |
|---|---|---|
| 1 | Does `top_spenders` include accounts with zero outgoing? | **Yes.** Every existing account is ranked; zero-outgoing accounts simply sort last under *outgoing desc, id asc*. |
| 2 | What separates entries in the output? | **`", "` — a comma and a space.** (This differs from the other mocks in this kit; it follows the source.) An empty result is `""`. |
| 3 | Degenerate `n`? | `n <= 0` → `""`. `n` greater than the account count → all accounts, no padding. |
| 4 | Does scheduling reserve the balance? | **No.** The balance is checked only at execution time; between scheduling and execution the money is fully spendable. |
| 5 | Can you cancel a payment at its scheduled time? | **No.** Due payments run at the start of every operation, *before* `cancel_payment`'s own lookup, so cancelling at or after the scheduled time returns `False`. |
| 6 | Are payment ids per-account or global? | **Global**, sequential across all accounts, starting at `"payment1"`. |
| 7 | Does a failed payment count toward the outgoing total? | **No.** Insufficient balance means the payment is discarded with no effect whatsoever, and it never retries. |
| 8 | What does `delay = 0` mean? | The payment is **due immediately**, and therefore executes at the start of the **next** operation — never inside `schedule_payment` itself. |
| 9 | What about `amount <= 0`? | **Out of contract.** The source states amounts are positive integers; the behaviour is undefined and is not tested. |
| 10 | `get_balance` for an account that was merged away? | History is preserved. A `time_at` **before** the merge returns the balance it held then; a `time_at` **at or after** the merge returns `None`, because the account no longer existed. |
| 11 | After a merge, `get_balance(id_1, time_at)` for a past `time_at`? | Returns `id_1`'s **own** historical balance, without `id_2`'s. The merge is an event at its own timestamp; history before it is unchanged. |

One further reading, stated for completeness but deliberately **not** tested: `get_balance` is a historical read, so `time_at <= timestamp` is expected. A `time_at` in the future is out of contract.

---

## Scoring

| Level | Points | Suggested time |
|---|---|---|
| 1 — Core operations | 100 | 10 min |
| 2 — Aggregation | 150 | 20 min |
| 3 — Scheduled payments | 150 | 30 min |
| 4 — Merges & historical balances | 200 | 30 min |
| **Total** | **600** | **90 min** |

Levels 1 and 2 must still pass after Level 4 is implemented. A Level 4 that breaks Level 1 scores 200, not 600.

## After the exam

Read the module docstring at the top of `solution.py` before reading the code. It names the two decisions the whole exam turns on — the per-account balance log, and the single `_process_due` funnel — and what the naive alternative costs.

Then ask yourself two questions honestly. Did `top_spenders` make you go back and change `transfer`? And when you reached `get_balance`, did you have the past, or did you have to go and get it? Those two moments are the exam. Everything else is typing.
