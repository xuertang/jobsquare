# The progression — what `ContentStore` looked like at the end of each level

`l1.py`, `l2.py`, `l3.py` and `l4.py` are four complete, standalone
implementations of the same class. None of them imports from `solution.py`, none
imports from another, none subclasses another, and there is no shared base
module. Each file is exactly what the class contained at the moment that level's
tests went green and before the next level had been read.

That independence is the whole point of the artifact. Because each file is
whole, the diff between two adjacent ones is the honest bill for that
transition, with nothing hidden behind inheritance:

```bash
diff -u progression/l1.py progression/l2.py
diff -u progression/l2.py progression/l3.py
diff -u progression/l3.py progression/l4.py
```

Each file passes every test up to and including its own level, and no more:

```bash
ICF_IMPL=progression.l1 python3 -m pytest -q -m "level1"                       # 13 passed
ICF_IMPL=progression.l2 python3 -m pytest -q -m "level1 or level2"             # 27 passed
ICF_IMPL=progression.l3 python3 -m pytest -q -m "level1 or level2 or level3"   # 45 passed
ICF_IMPL=progression.l4 python3 -m pytest -q                                   # 68 passed
```

`l4.py` is the destination, and that is checkable rather than aspirational:
strip the docstrings and comments from `l4.py` and from `solution.py` and the
two are identical executable code. So these four files are not an idealised
retelling of how the reference solution was reached. They are a decomposition of
it into the four decisions that actually produced it, in the order the exam
forces you to make them.

The discipline that makes the exercise worth reading is that **no file contains
anything its own level did not ask for**. `l1.py` has no TTL, no expiry, no
event log and no way to ask what an id used to be. Grep it for `ttl`, `expire`,
`_log`, `_Event` or `history` and every one of them returns nothing, in code and
in prose alike; the sole appearance of the word "log" in the whole file is a
comment saying there is not one. `l3.py` has time and TTLs and still stores
exactly one current record per id, because Level 3 never asks what an id used to
be. Seeding an `expires_at` field into Level 1 because you happen to know Level
3 is coming would make the files pleasant to read and the demonstration
worthless.

---

## The one thing `l1.py` does keep, and why it is not cheating

The API convention makes this question sharper than it used to be. **Every
public method takes `timestamp` as its first argument from Level 1 onwards, and
Level 1 has no use for it whatsoever.** Four methods are handed a value nothing
at that level reads. So: is writing it down clairvoyance?

No, and the distinction is the most transferable thing in this directory.

Inventing a field nobody has mentioned — a `ttl`, an `expires_at`, a version
counter, a `created_by` — is speculation. No caller has handed you that value.
To have it you must manufacture it, and the only reason to manufacture it is a
suspicion about requirements you have not been shown. That is the thing this
progression refuses to do, and refusing it is what makes every measurement below
mean anything.

Writing down a value the caller explicitly passed you is a different act
entirely. It is not the addition of information; it is the *absence of a
destructive one*. The spec put `timestamp` in the signature of all four Level 1
methods. The value is already in your hands, already computed by somebody else,
already part of the contract you were handed. The only way to finish Level 1
without it is to go out of your way to drop it on the floor. The naive Level 1
in `wrong_path/` does exactly that — two parallel dicts holding `body` and
`size`, and the argument falls out of scope unread and unstored — and it is not
a strawman; it is shorter, and it passes. `l1.py` instead makes the stored value
a `_Record(timestamp, body, size)`, which is precisely the three attributes that
appear in `add_content`'s own signature, and no fourth.

The half of that rule which can actually be enforced by reading the code is the
second half: **`l1.py` never reads the timestamp.** `_record` does not compare
it, no public method branches on it, no arithmetic anywhere in the file involves
it, and the store holds exactly one current record per id — overwritten in place
by `update_content`, removed outright by `delete_content`. Recording the instant
of a write and keeping every write are entirely different commitments, and only
the first is free. The second is Level 4, and it is charged for in full there.

There is a line `l1.py` deliberately does not cross, and it is worth naming
because it looks like the same decision and is not. Its read accessor is
`_record(content_id)`, with one argument. It would have been easy to write
`_record_at(content_id, when)` at Level 1, ignore `when`, and buy a Level 3 in
which no public method changes at all. That would have been clairvoyance:
nobody handed the *accessor* a `when`, and inventing an unused parameter on a
private helper you wrote yourself is designing against a spec you have not read.
The Level 2 → Level 3 section shows exactly what declining to cross that line
cost — six public methods, one code line each — and that price is the honest
one.

One ordinary habit is also in place from the start: every read of the store goes
through that single accessor. All four Level 1 methods ask the same question
("is there something under this id?"), and a question asked four times should
have one answer. That is DRY over four call sites that exist at minute three,
not a hook for a level nobody has read.

---

## Level 1 → Level 2: querying, at zero cost to the existing code

Level 2 asked for prefix enumeration and top-N-by-size ranking and said nothing
whatsoever about storage. Nothing about storage changed. `_Record` and
`self._records` are byte for byte what they were, and — this is the measured
claim, not an impression — **not one of the four existing public methods was
touched**, nor was `__init__`, nor was `_record`. The entire code diff is
additive apart from a single edited import line, which brings in `Iterable` and
`Iterator`. Two new public methods, three new private helpers, one changed line
in the whole file.

The one judgement call is that `find_by_prefix` and `top_n_by_size` are both
shells over a single private generator, `_live_records`. They differ in how they
sort and in how many results they keep; they do not differ at all in *which ids
are in scope*, and that question — "which records count right now?" — is where
every later requirement is going to land. Giving it one home costs nothing today
and is the difference between editing one method later and editing two.
`_format` and `_join` are factored out for the same reason: the wire format
`id(size)` and the `", "` join rule are each shared by both queries, so each gets
one definition rather than two.

Note also what `_live_records` does *not* do. It does not rummage through
`self._records.items()` looking for values. It walks the keys and then asks
`_record` about each one, which keeps the readability decision inside the
accessor Level 1 built. That is a one-line choice and it is the reason the
helper survives the next two levels with its intent intact.

`timestamp` is still handed to every method, still stored on every write, and
still read by nothing — including the two new queries, which accept it, ignore
it, and sort by id and size alone.

## Level 2 → Level 3: the record widens, and the plumbing is billed

Level 3 introduced per-item TTLs and the half-open liveness rule
`t <= q < t + d`. It adds **no new methods at all** — one optional `ttl`
parameter on the two writers, and the instruction that the argument every method
has been carrying since Level 1 now means something.

The data model change is genuinely small, and it is small for exactly the reason
the previous section argues. The value Level 3 needs above all others is *when
each record was written*, and that is not derivable from anything else — but
`l1.py` already has it, because the caller supplied it and it was not thrown
away. So `_Record` does not gain a `timestamp` field here. It gains `ttl` and
the derived `expires_at`, which are new *inputs* the spec has only now
introduced, plus an `alive_at` predicate holding the liveness comparison. That
whole region of the file, imports and dataclass together, moves by +9 / −4
lines. Because every caller was already handed a record rather than a bare
string, not one of them cares that the record got wider.

What *is* billed is the plumbing, and the tables record it rather than hiding
it. Readability is now a function of two things instead of one, so
`_record(content_id)` becomes `_record_at(content_id, when)` and `_live_records`
grows the same parameter. That reaches every public method: all six changed. But
the shape of the change matters more than the count. `get_content`,
`delete_content`, `find_by_prefix` and `top_n_by_size` each changed exactly two
lines, and one of those two is the docstring — the behavioural edit is a single
line per method, forwarding the `timestamp` it was already holding down to the
chokepoint. The two that changed more, `add_content` (+13 / −4) and
`update_content` (+15 / −4), changed because they genuinely gained a parameter
and a computed `expires_at`, and `update_content` additionally gained the three
lines of TTL-renewal arithmetic that are the level's actual trap.

This is where the progression diverges from the reference solution's telling.
`solution.py` observes that `get_content` "does not change by one character"
between Levels 1 and 3, and that is true of `solution.py`, which starts from the
finished shape. It is not true of anything built without foreknowledge, and
pretending otherwise would be the exact failure mode this directory exists to
avoid. One code line per reader is what the honest version costs, and one line
per reader is still a good afternoon's work compared to rediscovering when each
record was written.

What Level 3 still does not have is any notion of a previous value. There is one
current record per id, `update_content` overwrites it, `delete_content` removes
it, and the prior body is gone. Every Level 3 read is answered from the newest
write, so nothing at this level notices — which is precisely why a candidate can
reach the seventy-minute mark feeling fine.

## Level 3 → Level 4: the record-to-log refactor, reported honestly

Level 4 asks what an id *used to be*. `get_content_at_time` reads the past;
`rollback` rewrites it, discarding every operation newer than a target instant
and re-asserting the survivors at `timestamp` with their remaining lifetimes
intact. `l3.py` cannot answer any of that, and no amount of Level 1 foresight
short of building the log up front would have let it. One current record per id
has destroyed the previous values by construction.

So the storage model changes for real, and this is the transition where anyone
claiming "a good Level 1 makes Level 4 free" is selling something. `_Record`
becomes `_Event` — the same five attributes plus a `kind` and a monotonic `seq`
tiebreaker — and `dict[str, _Record]` becomes `dict[str, list[_Event]]`, an
append-only log per id kept sorted by `(timestamp, seq)`. Current state stops
being stored and starts being derived. A delete stops being
`del self._records[id]` and becomes another event, which is exactly what lets a
historical read see across it. Three new private primitives appear (`_next_seq`,
`_append`, `_last_event_at`), and `_record_at` is rewritten from a dict lookup
plus a timestamp guard into a binary search for the newest event at or before
`when`, followed by the same liveness question it always asked.

`_Event.alive_at` deserves a sentence because it is the one predicate that moved
rather than grew: the "not written yet" test leaves the predicate — an event the
bisect never returns cannot be read — and a DELETE test arrives in its place.
Same number of clauses, different clauses.

What the Level 1 and Level 2 discipline actually bought, measured rather than
asserted: **three of the six carried-over public methods changed body, and all
three are writers.** `add_content` (+11 / −6), `update_content` (+11 / −6) and
`delete_content` (+4 / −1) each swap one assignment — or one `del` — for an
`_append`. Their guards, their return contracts and the TTL-renewal arithmetic
are untouched; only the shape of the thing being written changed. The three
readers — `get_content`, `find_by_prefix` and `top_n_by_size` — are **byte for
byte identical** to `l3.py`. They did not notice the storage engine being
replaced underneath them, because they were asking `_record_at`, not the
container.

That payoff is narrower than the usual telling, and the narrow version is the
true one. The reads were free. The writes were not, and were never going to be,
because "how a mutation is recorded" is precisely the thing that changed. A
one-line `_write(content_id, record)` helper at Level 3 would have collapsed
those three edits into one — and would have been speculative indirection at a
level with nothing to justify it. Three mechanical call sites is the correct
price for not writing it, and it is the difference between a contained refactor
and a rewrite: had `l3.py` stored `dict[str, str]` with each public method
reaching into the dict itself, all six would have had to move and the two new
features would have had nothing to build on.

The new features then cost what a log makes them cost. `get_content_at_time` is
six lines including its docstring, because it is `get_content` with `time_at` in
place of `timestamp` — the derivation the log already performs, pointed at a
different instant. `rollback` is twenty-nine lines and needs no side table and no
undo stack, because the log already *is* the undo stack: truncate every event
newer than the target, then append one RESTORE per survivor at `timestamp` with
its expiry shifted by `delta`.

---

## Measured

The numbers below come from a throwaway `difflib` + `ast` script, since deleted.
"Code only" excludes each file's module docstring, which differs substantially
between snapshots and would otherwise swamp everything. `added` / `removed` /
`changed` are `difflib.SequenceMatcher` opcodes over code lines, where *changed*
counts a replaced block on both sides (`old → new`). "Carried-over public methods
with a changed body" compares each method's full source text, so a docstring edit
counts as a change.

| Transition | file lines | code lines | `diff -u` code | added | removed | changed | hunks | public methods added | **carried-over public methods with a changed body** | private helpers added |
|---|---|---|---|---|---|---|---|---|---|---|
| L1 → L2 | 131 → 150 | 79 → 120 | +42 / −1 | 41 | 0 | 1 → 1 | 3 | 2 | **0 of 4** | 3 |
| L2 → L3 | 150 → 207 | 120 → 159 | +70 / −31 | 16 | 0 | 31 → 54 | 3 | 0 | **6 of 6** | 2 (`_record` → `_record_at`) |
| L3 → L4 | 207 → 309 | 159 → 249 | +134 / −44 | 63 | 4 | 38 → 69 | 7 | 2 | **3 of 6** | 5 |

Rework only — the cost *inside* methods that already existed, excluding every new
method, import, banner comment and module docstring:

| Transition | carried-over methods changed | added | removed | which ones |
|---|---|---|---|---|
| L1 → L2 | 0 | +0 | −0 | none — the diff is additive apart from one import line |
| L2 → L3 | 8 (6 public, 2 private) | +42 | −20 | all six public methods; `__init__`, `_live_records` |
| L3 → L4 | 7 (3 public, 4 private) | +40 | −28 | `add_content`, `update_content`, `delete_content`; `__init__`, `_record_at`, `_live_records`, `_format` |

Per-method rework, so the shape of each transition is visible and not only its
total:

| L2 → L3 method | +/− | | L3 → L4 method | +/− |
|---|---|---|---|---|
| `update_content` | +15 / −4 | | `add_content` | +11 / −6 |
| `add_content` | +13 / −4 | | `update_content` | +11 / −6 |
| `_live_records` | +5 / −3 | | `_record_at` | +7 / −8 |
| `get_content` | +2 / −2 | | `__init__` | +4 / −2 |
| `delete_content` | +2 / −2 | | `delete_content` | +4 / −1 |
| `find_by_prefix` | +2 / −2 | | `_live_records` | +2 / −4 |
| `top_n_by_size` | +2 / −2 | | `_format` | +1 / −1 |
| `__init__` | +1 / −1 | | `get_content` | **unchanged** |
| | | | `find_by_prefix` | **unchanged** |
| | | | `top_n_by_size` | **unchanged** |

In each of the four `+2 / −2` entries on the left, one line of the pair is the
docstring. The behavioural edit in `get_content`, `delete_content`,
`find_by_prefix` and `top_n_by_size` at Level 3 is literally one line apiece.

New surface added at each transition, for scale:

| Transition | new methods | their line count |
|---|---|---|
| L1 → L2 | `find_by_prefix`, `top_n_by_size`, `_live_records`, `_format`, `_join` | 32 |
| L2 → L3 | `_record_at`, `_expiry` | 15 |
| L3 → L4 | `get_content_at_time` (6), `rollback` (29), `_next_seq` (3), `_append` (4), `_last_event_at` (9), `_truncate_after` (8), `_keep_through` (3) | 62 |

## Does the API convention make the L3 → L4 refactor cheaper?

The previous version of this progression was written against the older
convention, where Level 3 introduced a full parallel `*_at` API and the Level 1
and Level 2 methods became one-line delegations to it. That version reported the
L3 → L4 refactor as touching **3 of 13** public methods. This one reports **3 of
6**. It is tempting to read that as a regression, and equally tempting to read
the new convention as an improvement. Both readings are wrong, and since the
stale files were still on disk this was measured rather than guessed.

| | old-convention progression | this progression |
|---|---|---|
| public methods at L3 | 13 | 6 |
| public methods at L4 | 15 | 8 |
| **public methods changed at L3 → L4** | **3** | **3** |
| which ones | `add_content_at`, `update_content_at`, `delete_content_at` | `add_content`, `update_content`, `delete_content` |
| as a fraction | 3 of 13 (23%) | 3 of 6 (50%) |
| rework inside carried-over methods | +41 / −24 | +40 / −28 |
| private helpers changed | 4 | 4 |
| new methods added | 7 (64 lines) | 7 (62 lines) |

**The absolute number is identical, and it is the same three methods: the
writers.** Nothing about the API convention changed what the refactor costs,
because that cost is set by how many places record a mutation, and that was
three under both conventions. The ratio moved only because the old denominator
was padded. Six of those thirteen were pass-through delegations that could not
change no matter what happened to storage, and three more (`current_time` and
the two `*_at` readers) were already one-liners over the chokepoint. Deleting
the legacy layer did not make the refactor more expensive; it removed nine
methods that were never going to change and were therefore never evidence of
anything. If anything the new figure is the more honest one, because 3 of 6 is
what a reader would find by opening the two files, while 3 of 13 flattered the
design with methods that had nothing in them.

The measurement that *did* move is Level 2 → Level 3, and it moved for an
interesting reason. Both conventions report "6 of 6 public methods changed", but
under the old one that was the six Level 1 and Level 2 methods being gutted and
replaced by delegations (+22 / −32 — the public surface got *shorter* at the
level that supposedly broke it), while under the new one it is six methods each
forwarding one more argument (+42 / −20, of which +28 / −8 is `add_content` and
`update_content` genuinely gaining a `ttl` parameter and an expiry computation).
Same headline number, almost nothing in common underneath. It is a good
illustration of why "how many methods changed" is only meaningful next to "and
by how much".

## An honest accounting of the record-to-log conversion

Splitting the L3 → L4 diff into conversion and new features:

| Component | added | removed |
|---|---|---|
| `_Record` → `_Event`, `bisect`/`math` imports, kind constants | +18 | −9 |
| `__init__`, `_record_at`, `_live_records`, `_format` | +14 | −15 |
| the three public writers | +26 | −13 |
| new log primitives (`_next_seq`, `_append`, `_last_event_at`) | +16 | −0 |
| **conversion total** | **+74** | **−37** |
| Level 4 features (`get_content_at_time`, `rollback`, `_truncate_after`, `_keep_through`) | +46 | −0 |

Those two rows sum to +120 against the +134 the whole-file code diff reports;
the remaining fourteen lines are blank separators and section banner comments,
which is exactly the sort of gap that should be stated rather than rounded away.

Seventy-four lines added and thirty-seven removed is not free, and it is close to
a third of the file. What a record model plus a single read chokepoint buys is
not the absence of that refactor but its *containment*, and containment is
measured by how much of the public surface had to move: three writers, no
readers, no signature change to anything that already existed, and every Level 1,
2 and 3 test still green afterwards. The two private entries in the rework table
that look alarming are not: `_format`'s single changed line is a type
annotation, and `_live_records`'s is the name of the container it iterates. Both
are the kind of change a rename makes, not a redesign.

## The decision that paid for everything

It was not the event log. That arrives at Level 4, when the spec finally demands
it, and it arrives as a genuine seventy-line refactor. It was the field
declaration in `l1.py` that reads `timestamp: int`, sitting in a `_Record` that
nothing at Level 1 inspects, next to a comment saying so.

Level 3's entire premise is that the store knows when each record was written.
That value cannot be reconstructed, inferred or defaulted; a store that dropped
it has to be rewritten to acquire it, mid-exam, with the clock running — which is
what `wrong_path/` exists to measure. `l1.py` did not have to be rewritten,
because the value had been handed to it and it had simply declined to throw it
away. That cost one line and required knowing nothing about Levels 2, 3 or 4.

The generalisation is worth carrying into the next exam, and it is sharper than
"design for the future", which is advice that mostly produces `ttl` fields
nobody asked for. It is this: **the parameters of a signature you did not choose
are themselves a specification.** Somebody put `timestamp` first in four methods
that have no use for it. That is not padding and it is not an accident, and the
correct response is neither to build a TTL engine on the strength of it nor to
discard it — it is to write it down, unread, and let the level that needs it find
it already there.
