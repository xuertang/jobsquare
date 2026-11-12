# The progression — what `Ledger` looked like at the end of each level

`l1.py`, `l2.py`, `l3.py` and `l4.py` are four complete, standalone
implementations of the same class. None imports from another, none subclasses
another, there is no shared base module and none of them imports `solution.py`.
Each is what the file contained at the moment that level's tests went green and
before the next level had been read.

That independence is the whole point of the artifact. Because each file is
whole, the diff between two adjacent ones is the honest bill for that
transition:

```bash
diff -u progression/l1.py progression/l2.py
diff -u progression/l2.py progression/l3.py
diff -u progression/l3.py progression/l4.py
```

Each file passes every test up to and including its own level:

```bash
ICF_IMPL=progression.l1 python3 -m pytest -q -m "level1"                        # 15 passed
ICF_IMPL=progression.l2 python3 -m pytest -q -m "level1 or level2"              # 29 passed
ICF_IMPL=progression.l3 python3 -m pytest -q -m "level1 or level2 or level3"    # 47 passed
ICF_IMPL=progression.l4 python3 -m pytest -q                                    # 66 passed
```

The discipline that makes the exercise worth reading is that no file contains
anything its own level did not ask for. `l1.py` contains no occurrence of the
strings `outgoing`, `payment`, `schedule`, `merge` or `_process_due` — grep it.
`l2.py` has no notion of time passing between calls beyond the timestamp it is
handed. `l3.py` has no merge and no historical read, and stores the current
balance alongside the record of how it got there because Level 3 never asks what
an account *was*.

`l1.py` does carry one thing that looks like foresight, and the next section is
the argument that it is not.

---

## What the noun already tells you

Before you choose a Level 1 data model, ask what the noun in the problem
statement already implies. That question is free information, and it is a
different question from "what might Level 4 want?"

A **ledger** is a record of transactions. That is what the word means in the
domain it was borrowed from: a book of entries, each stamped with when it
happened, from which the current figure is derived. A structure that holds only
the current balance and discards the entries that produced it is not a ledger;
it is a balance sheet. So `l1.py` keeps a per-account, time-ordered
`(timestamp, balance)` journal from the first line of code, and that is not a
bet on an unseen Level 4 — it is the shape of the thing named in the title.
The spec corroborates it twice over before Level 2 is visible: every method is
handed `timestamp` as its first argument, which is only worth doing to a system
that intends to remember when things happened, and timestamps are promised
non-decreasing, which is exactly the promise an append-only log needs in order
to stay sorted without ever being sorted.

Contrast Mock 1 in this kit, whose noun was **content store**. Nothing in those
two words implies retention of superseded versions — a store holds what is in
it now — so a Level 1 version log there would have been genuine speculation,
and the progression for that mock deliberately keeps one current record per id
and lets Level 4 charge a real refactor for the change. Same author, same
instinct, opposite decision, because the nouns are not the same noun.

The rule generalises further than these two problems. *Cache* implies eviction
and therefore a recency or frequency order, before any level mentions it. *File
system* implies a tree, and a flat `dict[str, str]` keyed by full path is
fighting the noun from minute one. *Queue* implies FIFO and therefore ends, not
an index. *Version control* implies a DAG. In each case the domain has already
specified part of your data structure and is handing it to you at no cost, and
taking it is not clairvoyance — it is reading the question.

The line between the two is sharp and worth stating precisely. Taking the
structure the noun implies is legitimate; inventing structure the noun does not
imply, on the theory that a later level might want it, is not. `l1.py` keeps a
journal because a ledger is a journal. `l1.py` does **not** keep a per-account
outgoing counter, because nothing in the word "ledger" says anything about
ranking spenders — and Level 2 duly charged one line for that, which is the
correct price and is documented below rather than hidden.

---

## Level 1 → Level 2: one line of rework, and an honest fork

Level 2 asked for a ranking of every existing account by total outgoing amount,
tie-broken by id, rendered as a single `"id(amt), id(amt)"` string. It said
nothing about storage.

There is a genuine fork here and `l2.py`'s docstring takes a side out loud.
Level 1's journal records *balance*, not *direction*: it knows alice went from
300 to 200 at t=3, not that the 100 went to bob. At Level 2 that gap is
closeable by arithmetic, because a transfer is the only thing in the system
that can make a balance fall, so the sum of the negative deltas in an account's
journal is exactly its outgoing total. A derived `top_spenders` written that
way passes every Level 2 test. `l2.py` does not do it, for a cheap reason and
an expensive one. The cheap one is that it is O(history) per query instead of
O(accounts log accounts). The expensive one is that it infers intent from
arithmetic: it is correct only while "the balance went down" and "this account
spent money" remain the same sentence. At Level 3 they still are, by luck —
executed payments both debit and accrue. At Level 4 they are not: `id_1`
absorbs `id_2`'s outgoing total on merge, and no amount of staring at `id_1`'s
own balance deltas will produce it. The derivation would have survived two
levels and then failed silently, in the level with the least time left.

So the counter was added at Level 2, as a field on `_Account`, maintained by
`transfer`. **One existing method body changed, by one line** —
`source.outgoing += amount`, placed after the guard clauses so that a refused
transfer still accrues nothing. `create_account` and `deposit` were untouched,
because receiving money is not spending and the credit side of the ledger has
no opinion about this level at all. `_set_balance`, `__init__` and the journal
are byte for byte what they were. `top_spenders` itself is a sort and a join.

## Level 2 → Level 3: five methods touched, all five by the same line

Level 3 added two public methods and one sentence that costs more than both of
them: *at the start of every operation — every public method, mutator or
reader, from every level — execute all pending payments whose scheduled time is
at or before `timestamp`.*

Written literally, that sentence is a loop pasted into every public method.
`l3.py` writes it once as `_process_due(timestamp)` and makes it the first
statement of **all six** public methods: `create_account`, `deposit`,
`transfer`, `top_spenders`, `schedule_payment` and `cancel_payment`. Six is the
number to internalise, because the failure mode of this level is arithmetic —
five out of six is not 83% correct, it is a ledger that silently reports stale
state through one door.

The two easiest to forget are the two that do not feel like money moving.
`top_spenders` is a reader, and readers feel exempt; a forgotten funnel there
returns a ranking that predates payments the clock says have already gone out.
`cancel_payment` is the worse of the two, and it is the one this level is really
testing, because forgetting it produces a wrong answer that looks right. The
spec says cancelling at or after a payment's scheduled time returns `False`,
and the *only* mechanism that makes that true is the funnel at the top of that
very call draining the payment before the lookup runs. Omit it and
`cancel_payment` cheerfully cancels a payment that has, by the clock, already
executed — returning `True` where the spec demands `False`, with the balance
and the outgoing total already moved. Nothing else in the method is wrong. One
line, in the method that feels least like it needs it.

What did **not** have to change is the more interesting half. `_set_balance` is
untouched, because an executed payment spends money in exactly the way a
transfer does, so the executor reuses the Level 1 write chokepoint and the
Level 2 counter — which is why `top_spenders` needs no clause about payments
and why the executor is nine lines. The journal is untouched. The one subtlety
the funnel absorbs is *when* an executed payment is stamped: at its own
`execute_at`, not at the timestamp of the call that noticed it was due.
Draining before every operation is precisely what guarantees that stamp never
lands behind an entry already in the journal, which keeps the journal sorted,
which is what the next level needs.

Measured, the rework is `__init__` gaining three fields and four public methods
gaining one line each: **+7 lines, −0**. Everything else in the diff is new
surface area — `_Payment`, `_process_due`, `schedule_payment`, `cancel_payment`.

## Level 3 → Level 4: no carried-over method body changed at all

Level 4 asked for `merge_accounts` and `get_balance`, and this is the level the
Level 1 decision was made for.

`get_balance(timestamp, account_id, time_at)` is eight lines after its
docstring: the funnel call, the journal lookup, a two-line guard for an id that
never existed, one line of `bisect.bisect_right` keyed on the entry timestamp, a
two-line guard for a `time_at` before the account's first entry, and the return.
The search itself is genuinely one line. The claim in the problem statement's
design note — "if every balance change appended to a per-account, time-ordered
log, `get_balance` is a binary search and takes five minutes" — is accurate;
nothing had to be reconstructed because nothing had been thrown away.

`merge_accounts` is seventeen lines after its docstring and moves three things.
Balance and outgoing total are two integer additions. The third, pending
payments, is the one that could have been expensive and was not: the merge
rebinds `payment.account_id` in place, and `_process_due` needs no change
whatsoever, because it resolves the owner by id at the instant the payment
fires rather than capturing an account object when the payment was scheduled.
That single design detail — a five-character difference at Level 3 between
storing `account_id` and storing `account` — is why an inherited payment bills
the survivor, why it can now succeed where it would have failed alone, and why
`cancel_payment` follows ownership without a line of new code. `id_1` can
cancel an inherited payment; `id_2` cannot, because `id_2` is not an account
any more. Neither method was edited to make that true.

The merge does not delete `id_2`'s history; it appends a tombstone
`(timestamp, None)`. A read before the merge lands on a real entry, a read at
or after it lands on the tombstone and returns `None`, and a read before the
account ever existed falls off the front of the list and also returns `None` —
three specified behaviours, one binary search, no special cases. Re-creating
the freed id later appends a fourth era to the same journal, which works
because `_set_balance` has used `setdefault` since Level 1 rather than assuming
a fresh list.

The honest asterisk: that tombstone append is the one place in `l4.py` that
writes to `self._journal` without going through `_set_balance`. It is
deliberate — the end of an account is not a balance change, and it is the only
such event in the entire spec — but it is a second writer, and a file with two
writers is one edit away from having three.

Measured, the only carried-over executable code that changed between `l3.py`
and `l4.py` is **one line in `__init__`**: the journal's type annotation widens
from `list[tuple[int, int]]` to `list[tuple[int, Optional[int]]]` to admit the
tombstone. Zero public method bodies changed. Two docstrings gained a sentence
each — `_process_due`'s, to note that the owner is resolved at fire time, and
`cancel_payment`'s, to note that ownership moves with a merge — and both
describe behaviour that was already there.

---

## Measured

Whole-file, as `diff -u` reports it. Module docstrings differ substantially
between the files and are included in these counts, because they are part of
what you read:

| Transition | file length | `diff -u` added | `diff -u` removed | hunks | public methods added | private helpers added | carried-over public method bodies changed |
|---|---|---|---|---|---|---|---|
| L1 → L2 | 125 → 131 | +50 | −44 | 4 | 1 | 0 | **1 of 3** (`transfer`) |
| L2 → L3 | 131 → 228 | +129 | −32 | 8 | 2 | 1 (`_process_due`) | 4 of 4 |
| L3 → L4 | 228 → 287 | +105 | −46 | 6 | 2 | 0 | **0 of 6** |

Those added/removed figures are dominated by prose. Excluding the module
docstring from both sides:

| Transition | code lines | added | removed |
|---|---|---|---|
| L1 → L2 | 79 → 101 | +25 | −3 |
| L2 → L3 | 101 → 188 | +89 | −2 |
| L3 → L4 | 188 → 238 | +57 | −7 |

Rework only — executable code inside methods that already existed, with
docstrings, comments and every newly added method excluded:

| Transition | methods changed | added | removed | which ones, and what changed |
|---|---|---|---|---|
| L1 → L2 | 1 | +1 | −0 | `transfer`: one line, `source.outgoing += amount` |
| L2 → L3 | 5 | +7 | −0 | `__init__` gains three fields; `create_account`, `deposit`, `transfer`, `top_spenders` each gain the funnel call |
| L3 → L4 | 1 | +1 | −1 | `__init__`: the journal's type annotation widens to admit `None` |

Funnel coverage, counted from the source: `l3.py` has 6 public methods and 6 of
them call `_process_due(timestamp)` as their first statement. `l4.py` has 8
public methods and 8 of them do.

Sizes of the two Level 4 methods, excluding their docstrings: `get_balance` is
8 lines, `merge_accounts` is 17.

### Where the tidy story does not hold

Three places, stated rather than smoothed over.

The Level 1 → Level 2 whole-file diff reads `+50/−44` on a transition whose
actual code rework is a single line. Forty-odd of those lines are the module
docstring being rewritten wholesale for the new level — an artifact of this
artifact, not of the design. The code-only table is the one to read.

Level 2 did pay a retrofit, however small. The problem statement's Level 2
design note says that if your Level 1 `transfer` already incremented an
outgoing counter, this level is four lines. Mine did not, on purpose, because
nothing in Level 1 justified the field — and so `transfer` was edited at Level
2. One line is a cheap bill, but it is not zero, and it is the counterexample
that keeps the domain-implies-structure argument from becoming "put everything
in at Level 1". The noun gave me the journal. It did not give me the counter.

And Level 2 → Level 3 shows 4 of 4 carried-over public methods changed, which
is the worst-looking row in the table. It is also the least alarming, because
all four changed by the same line, and the line is not a concession to a design
error — it is the spec's "at the start of every operation", implemented once
and called four times. The alternative reading, that a per-call preamble should
have been seeded into Level 1's methods so this row would read 0 of 4, is
exactly the clairvoyance this artifact exists to argue against.

---

## The decision that paid for everything

It was not the journal on its own. It was the pair of lines in `l1.py` that say
`self._journal: dict[str, list[tuple[int, int]]] = {}` and, inside a private
`_set_balance`, `account.balance = balance` followed by an append to that list —
one chokepoint through which every balance change in the system must pass, so
that "a balance change is a ledger entry" is enforced in one place rather than
remembered in four. The journal is what Level 4 reads. The chokepoint is why
Levels 2, 3 and 4 never had to go back and teach a fourth or fifth mutator to
write to it: when Level 3 invented an entirely new way for money to leave an
account, the executor spent one call on `_set_balance` and inherited correct
history for free, and when Level 4 asked what a balance was at an instant three
operations ago, the answer was already sitting in a sorted list waiting for a
`bisect`. Neither line required knowing that Levels 2, 3 or 4 existed. Both fall
out of two questions worth asking at minute three of any exam in this format:
*what does the noun in the title already tell me about the shape of this data?*
and *when the shape turns out to be wrong, how many places will I have to edit?*
Here the noun said "keep the entries", and the answer to the second question was
one, and it stayed one for all four levels.
