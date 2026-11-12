# The progression — what `InMemoryDB` looked like at the end of each level

`l1.py`, `l2.py`, `l3.py` and `l4.py` are four complete, standalone
implementations of the same class. None of them imports from another, none
imports from `solution.py`, none subclasses another, and there is no shared base
module. Each one is exactly what the file contained at the moment that level's
tests went green and before the next level had been read.

That independence is the whole point of the artifact. Because the files are
whole, the diff between two adjacent ones is the honest bill for that
transition, with nothing hidden behind inheritance:

```bash
diff -u progression/l1.py progression/l2.py
diff -u progression/l2.py progression/l3.py
diff -u progression/l3.py progression/l4.py
```

Each file passes every test up to and including its own level:

```bash
ICF_IMPL=progression.l1 python3 -m pytest -q -m "level1"                        # 14 passed
ICF_IMPL=progression.l2 python3 -m pytest -q -m "level1 or level2"              # 29 passed
ICF_IMPL=progression.l3 python3 -m pytest -q -m "level1 or level2 or level3"    # 44 passed
ICF_IMPL=progression.l4 python3 -m pytest -q                                    # 66 passed
```

The discipline that makes the exercise worth reading is that no file contains
anything its own level did not ask for. `l1.py` has no TTL, no `expires_at`, no
liveness predicate and no history — `grep -iE "ttl|expire|alive|backup" l1.py`
returns nothing, and so does the same grep on `l2.py`. Seeding an expiry
attribute into Level 1 because you happen to know Level 3 is coming would make
the files pleasant and the demonstration worthless.

## An honest divergence from `solution.py`

`solution.py`'s module docstring argues for storing `_Field(value, expires_at)`
from the first line of Level 1, on the grounds that `expires_at` is dead weight
for two levels and costs one dataclass and one `None`. As advice to a candidate
who has already read all four levels — which is to say, as advice for the second
time you sit this problem — that is right. As a claim about what Level 1
justifies, it is one step too clairvoyant. Nothing in Level 1 mentions time
beyond an unused parameter, and a reader who finds `expires_at = None` in a file
whose spec has no notion of expiry is entitled to ask where it came from. So
`l1.py` here stores `_Field(value)` — a record with exactly one attribute — and
routes every read through one private accessor.

The interesting claim survives the divergence intact, and arguably it only
becomes a claim at all once the divergence is made. Level 3 is cheap here not
because the field was pre-installed but because the *record* and the *accessor*
already existed, so there was somewhere to put the field and somewhere to ask
about it. The measured cost of adding TTL to this model is one attribute on
`_Field`, one predicate on `_Field`, one condition inside `_field`, and one
public method rewritten — and the counterfactual below shows what the same
change costs a model that skipped both habits. If you want the version where
Level 3 truly costs *nothing*, read `solution.py`; if you want the version where
Level 3 costs what an honest Level 1 can be asked to pay for it, read these.

---

## Level 1 → Level 2: querying, at zero cost to the existing code

Level 2 asked for two readers, `scan` and `scan_by_prefix`, and said nothing
whatsoever about storage. Nothing about storage changed. `_Field`, `self._db`,
`_write` and `_field` are byte for byte what they were at Level 1, and — this is
the measured claim, not an impression — not one of the three existing public
methods was touched. `set`, `get` and `delete` are identical between the two
files. The entire diff is additive: two new public methods, two new private
helpers, and nothing else. The code-only diff reports `+41 / −0`, with the minus
column genuinely empty.

Two judgement calls at this level, and they are the same call made twice.
`scan` is not a second implementation of `scan_by_prefix`; it is a one-line
delegation with the empty prefix, because the spec itself defines it that way
("every field name starts with the empty string") and two sorted walks kept
manually in step is one more thing that can drift. And both funnel through a
single private helper, `_items`, which answers "which fields of this record are
in scope for a query, in order?". The two public methods differ only in the
prefix they hand it; they do not differ at all in what counts as being in scope.
Inlining the walk into each would work identically today and would double every
later edit, because any future refinement of "in scope" lands on precisely that
question and nowhere else.

The line in `_items` that matters most is easy to miss. It does not read
`record.items()` for values; it walks the field names and asks `_field` about
each one, exactly as `_matching` asks `_record` in Mock 1's progression. That is
a deliberate one-line choice, and it is the reason the helper survives the next
level without being reopened. A scan that reads the dict directly holds a second
opinion about what "readable" means; a scan that asks the accessor holds none.

## Level 2 → Level 3: the centrepiece

Level 3 adds one method, `set_with_ttl`, and then redefines the whole program.
A field written at `t` with lifetime `d` is readable only on the half-open
interval `[t, t + d)`, and an expired field must be invisible to `get`, to
`delete`, to `scan` and to `scan_by_prefix` alike. The spec is blunt that this
is the real work of the level: "the rest of this level is a refactor."

Here it is not a refactor, and the structural change is exactly what the brief
predicted: one field added to an existing record, one predicate edited, and
nothing else structural. `_Field` grows one attribute, `expires_at`, with `None`
meaning permanent, and one method, `alive_at`, which contains the liveness rule
and nothing else. `_field` — the single read accessor that has existed since
Level 1 — gains one condition that consults it. `_write` grows a defaulted
`expires_at` parameter so that both writers are the same call with a different
argument, which is the code-level statement of the spec's own claim that plain
`set` is `set_with_ttl` with an infinite lifespan.

**Exactly one carried-over public method changed body: `delete`.** One of five.
`set`, `get`, `scan` and `scan_by_prefix` are byte-identical across the
transition, and so are `_items`, `_format` and `__init__`. `_items` in
particular is worth pausing on, because it is the method that most obviously
*should* have changed — it is a scan, and scans now have to skip expired fields.
It did not change, because it asks `_field` about each field name rather than
reading the dict, so it inherited the new definition of readable without being
reopened. That is the single line from Level 2 paying for itself.

`delete` is the honest exception and it deserves its reason stated rather than
excused. It changed because at Level 3 it stopped being a pure read. Spec
decision 8 requires an expired field to answer `False` *and* to be purged, so
that no stale entry can be resurrected by a later `restore`. "Was it live?" and
"is it present?" are two different questions at Level 3 where at Level 2 they
were one, and `delete` is the only method in the class that has to ask both — so
it is also the only one that cannot route through an accessor that collapses
them. One method losing its chokepoint is the correct price for a requirement
that genuinely distinguishes presence from liveness.

One more thing to be transparent about, because it is the kind of number that
can be quietly engineered. `set` is byte-identical only because `_write`'s new
parameter is defaulted, so `set`'s existing call `self._write(key, field, value)`
still means "permanent". Spelling it `self._write(key, field, value,
expires_at=None)` at the call site, as `solution.py` does, is equally correct,
arguably clearer, and would make the headline number two of five instead of one
of five. Nothing semantic turns on it. The reported count is one, and this
paragraph is why it is one.

## The counterfactual: what the same level costs a bare-string model

The kit claims that a naive `dict[key][field] -> str` model forces the expiry
check into five separate places — `get`, `delete`, `scan`, `scan_by_prefix`, and
later `backup`. That claim was cheap to test, so it was tested rather than
asserted. Three throwaway files were written: `cf_l2.py`, a Level 2
implementation with no record type and no accessors, in which every public
method reaches into `self._db` itself; `cf_l3.py`, the same file with TTL added
as a `(value, expires_at)` tuple; and `cf_l4.py`, that file with backup and
restore. All three pass their level's suite — 29, 44 and 66 tests respectively,
identical to the progression files — so the comparison is between two working
implementations rather than between a real one and a strawman. They lived in
`/tmp` and have been deleted; the reconstruction takes about ten minutes if you
want to reproduce it.

The claim holds exactly, and the count is exactly five. In `cf_l3.py` the
comparison `timestamp < expires_at` appears independently inside `get`,
`delete`, `scan` and `scan_by_prefix`; in `cf_l4.py` it appears a fifth time
inside `backup`, because there is no predicate to inherit and no chokepoint to
ask. In `l3.py` and `l4.py` the comparison appears once, inside `alive_at`, and
is consulted from two call sites. At Level 2 → Level 3 the bare-string model had
**five of five** carried-over public methods rewritten — `set`, `get`, `delete`,
`scan` and `scan_by_prefix` — against **one of five** here.

What the counterfactual does *not* support is a story about line volume, and
that is worth saying plainly rather than burying. Excluding module docstrings,
the bare-string Level 3 diff is `+33 / −14` against the progression's
`+40 / −18`; counting only rework inside methods that already existed and
ignoring docstrings, it is `+19 / −6` against `+14 / −6`. The naive transition
is *smaller in added lines*, because the progression pays for a dataclass
attribute, a predicate with a docstring and a widened `_write` signature that
the naive version never writes at all. If your metric is characters typed on the
day, Level 3 is close to a wash, and anyone selling the record model on line
count is selling the wrong thing.

The metric that separates them is how many methods had to be *reopened*: six
units against three, five public against one. That is the number that predicts
what happens when the spec is ambiguous, when you are forty minutes in, and when
you have to be sure you did not miss a site. In the bare-string model there is
no way to be sure except to read every method; in this one there is one
predicate and `grep -n alive_at` enumerates its entire blast radius in three
lines. And the naive model's bill has not finished arriving at Level 3 — the
fifth copy of the rule is still to come, inside a method that does not exist yet.

## Level 3 → Level 4: semantically hard, structurally free

Level 4 is where Mocks 1 and 2 charge for everything their Level 1 could not
foresee, and it is where this problem does the opposite. Structurally it is the
cheapest transition in the file set. `_Field`, `_write`, `_field`, `_items`,
`_format` and all six public methods from Levels 1 to 3 are byte-identical
between `l3.py` and `l4.py`. **Zero carried-over public methods changed body.**
The only existing method touched at all is `__init__`, which gains one line for
the backup history — two lines counting the comment. Everything else is new
surface: `backup` at 21 lines, `restore` at 24, a `bisect` import and a type
alias. Code-only, the transition is `+58 / −1`.

The reason is worth stating as a distinction rather than as luck, because the
contrast with the other mocks is the lesson. In Mock 1 the Level 4 requirement
is point-in-time reads and a rollback that rewrites the past; in Mock 2 it is an
audit trail that outlives deletion. Both ask *what did this look like before?*,
and a store that keeps only current state has thrown that away by construction —
no chokepoint makes that free, and both progressions record a genuine conversion
to an append-only event log, with Mock 1 rewriting three public write methods
and Mock 2 rewriting seven. Here the requirement is *put this state somewhere
and put it back later*. Current state is precisely what the store already has.
Nothing has to be remembered that was not already being kept, so nothing about
the model has to change.

What is hard here is semantic, and it fits in one sentence: `restore` relocates
the origin of time, so a snapshot must store durations, not instants. A field
written at `10` with `ttl = 100` expires at `110`; backed up at `15` it must be
stored as *95 units remaining*, so that restoring it at `1000` puts it back
alive on `[1000, 1095)`. The obvious implementation — `copy.deepcopy` of the
live state — brings it back carrying `expires_at = 110` while the clock reads
`1000`, so the field is already dead and the restore silently restored nothing.
That bug is invisible to every test that restores near the backup timestamp;
only a test that jumps the clock across the restore can see it, which is exactly
what `test_restore_resumes_remaining_lifespan_after_a_far_clock_jump` does. So
`backup` stores `expires_at - timestamp` and `restore` computes
`timestamp + remaining`, with permanent fields as the degenerate case: `None`
remaining survives the round trip and stays `None`, needing no branch beyond one
conditional expression on each side.

This is the level's real teaching, and it is a different lesson from the one the
first three levels teach. Levels 1 to 3 are about where code goes. Level 4 is
about what a stored number *means* — an instant and a duration are the same
integer and different facts, and no amount of chokepoint discipline tells you
which one to write down. The structural cheapness is what makes it visible:
because nothing else was competing for attention in this diff, the only thing
left to get wrong was the arithmetic.

Two smaller decisions are visible in `l4.py` and both are the same habit
continuing. `backup` reads through `_items` rather than walking the dict, so
"live enough to be snapshotted" is the same question `scan` asks rather than a
fifth private answer to it — the sort `_items` performs is wasted work for a
snapshot, and that agreement is what the waste buys. And the backup history is a
list ordered by timestamp rather than a dict keyed by one, because the spec wants
the *latest backup at or before* an instant and wants two backups at the same
timestamp to resolve by call order; a list plus `bisect_right` gives both, and a
dict gives neither.

---

## Measured

Produced by a throwaway `difflib`/`ast` script, since deleted. "Changed body" is
an AST comparison with docstrings stripped, so a method that only had its prose
rewritten does not count as changed; no method in any transition changed only its
docstring, so the two readings agree here.

Whole-file, as `difflib` reports it. Module docstrings differ substantially
between files and are included, since they are part of what you read:

| Transition | file length | added | removed | hunks | public methods added | carried-over public methods with a changed body | other units added |
|---|---|---|---|---|---|---|---|
| L1 → L2 | 106 → 145 | +64 | −25 | 8 | 2 | **0 of 3** | 2 (`_items`, `_format`) |
| L2 → L3 | 145 → 178 | +74 | −41 | 18 | 1 | **1 of 5** (`delete`) | 2 (`_Field.expires_at`, `_Field.alive_at`) |
| L3 → L4 | 178 → 246 | +102 | −34 | 12 | 2 | **0 of 6** | 1 (`_Snapshot` alias) |

The same three diffs with module docstrings excluded, which is the closer measure
of code actually written:

| Transition | code lines | added | removed | hunks |
|---|---|---|---|---|
| L1 → L2 | 74 → 115 | +41 | **−0** | 2 |
| L2 → L3 | 115 → 137 | +40 | −18 | 12 |
| L3 → L4 | 137 → 194 | +58 | −1 | 5 |

Rework only — the cost inside methods that already existed, excluding every new
method, import, banner comment and docstring:

| Transition | carried-over units changed | added | removed | which ones |
|---|---|---|---|---|
| L1 → L2 | 0 | +0 | −0 | none — the diff is purely additive |
| L2 → L3 | 3 (1 public, 2 private) | +14 | −6 | `delete`; `_write`, `_field` |
| L3 → L4 | 1 (0 public, 1 private) | +2 | −0 | `__init__` |

The counterfactual, measured the same way. `cf_l2`/`cf_l3`/`cf_l4` are working
`dict[key][field] -> str` implementations with no record type and no accessors,
each passing its level's full suite (29 / 44 / 66):

| Metric | progression | bare-string counterfactual |
|---|---|---|
| L2 → L3, carried-over public methods with a changed body | **1 of 5** | **5 of 5** |
| L2 → L3, carried-over units changed (any visibility) | 3 | 6 |
| L2 → L3, rework lines excluding docstrings | +14 / −6 | +19 / −6 |
| L2 → L3, code-only whole-file diff | +40 / −18 | +33 / −14 |
| independent copies of the liveness comparison at L3 | **1** (`alive_at`) | **4** (`get`, `delete`, `scan`, `scan_by_prefix`) |
| independent copies of the liveness comparison at L4 | **1** | **5** (the four above, plus `backup`) |
| L3 → L4, carried-over public methods with a changed body | 0 of 6 | 0 of 6 |

The last row is a tie and should be read as one. Backup and restore are new
methods in both models, so neither transition disturbs existing public code; the
bare-string model's Level 4 penalty is not a rewrite, it is that its fifth copy
of the liveness rule gets written into `backup` where nobody will ever diff it
against the other four.

---

## The decision that paid for all of it

It was not `expires_at`, which does not exist until Level 3 and could not have
been justified before it. It was the two lines in `l1.py` that say
`self._db: dict[str, dict[str, _Field]] = {}` and, inside a private `_field`,
`return record.get(field)`. Storing a one-attribute record instead of a bare
string is what gave Level 3 somewhere to put the expiry without changing the
type of every value in the database; funnelling every read through one accessor
is what gave it one place to ask about it, and what let `_items`, `scan` and
`scan_by_prefix` sleep through a change to the meaning of readability. Neither
required knowing that Levels 2, 3 or 4 existed. A record with one field looks
like ceremony on the day you write it, and a private accessor that wraps a
single `dict.get` looks like more of the same; what they are is the answer to a
question worth asking at minute three of any exam in this format — *when the
shape of the stored thing turns out to be wrong, how many places will I have to
edit?* At Level 1 the answer was one. At Level 4 it was still one, and the
counterfactual says the alternative answer was five.
