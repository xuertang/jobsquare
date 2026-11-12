# The progression — what `ContentStore` looked like at the end of each level

`l1.py`, `l2.py`, `l3.py` and `l4.py` are four complete, standalone
implementations of the same class. None of them imports from another, none
subclasses another, and there is no shared base module. Each one is exactly what
the file contained at the moment that level's tests went green and before the
next level had been read.

That independence is the point of the artifact. Because the files are whole, the
diff between two adjacent ones is the honest bill for that transition:

```bash
diff -u progression/l1.py progression/l2.py
diff -u progression/l2.py progression/l3.py
diff -u progression/l3.py progression/l4.py
```

Each file passes every test up to and including its own level:

```bash
ICF_IMPL=progression.l1 python3 -m pytest -q -m "level1"                        # 12 passed
ICF_IMPL=progression.l2 python3 -m pytest -q -m "level1 or level2"              # 25 passed
ICF_IMPL=progression.l3 python3 -m pytest -q -m "level1 or level2 or level3"    # 42 passed
ICF_IMPL=progression.l4 python3 -m pytest -q                                    # 64 passed
```

The one discipline that makes the whole exercise worth reading is that no file
contains anything its own level did not ask for. `l1.py` has no timestamp, no
TTL, no expiry and no history — grep it. `l3.py` has time and TTL and still
stores exactly one current record per id, because Level 3 never asks what an id
used to be. Seeding a `created_at` field into Level 1 because you happen to know
Level 3 is coming would make the files pleasant and the demonstration worthless.

Two things `l1.py` does carry, and both are defensible without any knowledge of
what comes next. It stores a small `_Record` dataclass rather than a bare string,
because the spec already hands you two attributes — `body` and `size` — and a
record is simply the honest shape of that. And it routes every read through one
private accessor, `_record`, because all four Level 1 methods ask the same
question ("is there something under this id?") and a question asked four times
should have one answer. Everything below is the story of what those two habits
bought.

---

## Level 1 → Level 2: querying, at zero cost to the existing code

Level 2 asked for prefix enumeration and top-N-by-size ranking, and said nothing
whatsoever about storage. Nothing about storage changed. `_Record` and
`self._records` are byte for byte what they were at Level 1, and — this is the
measured claim, not an impression — not one of the four existing public methods
was touched. `add_content`, `get_content`, `update_content` and `delete_content`
are identical between the two files, as is the `_record` accessor. The entire
diff is additive: two new public methods, two new private helpers, and the
`Iterator` import they need.

The only real judgement call at this level is that `find_by_prefix` and
`top_n_by_size` are both shells over a single private generator, `_matching`.
They differ in how they sort and how many results they keep; they do not differ
at all in which ids are in scope. Inlining the prefix walk into each of them
would have worked identically today and would have doubled the edit at every
level afterwards, because every future notion of "in scope" — expiry, deletion,
a rewritten history — lands on precisely that question and nowhere else.
`_format` is factored out for the same reason: the wire format `id(size)` is
shared, so it gets one definition.

Note also what `_matching` does *not* do. It does not read `self._records`
looking for a value; it walks the keys and then asks `_record` about each one.
That is a deliberate one-line choice and it is why the helper survives the next
two levels with its intent intact.

## Level 2 → Level 3: the data model actually changes, and the blast radius is two methods

Level 3 introduced an explicit integer clock, per-item TTLs with the `t <= q < t + d`
liveness rule, a full parallel `*_at` API, and a backward-compatibility contract
defining every Level 1 and Level 2 method as its timestamped counterpart called
at `timestamp = 0` with `ttl = None`.

The semantic change is confined to two places. `_Record` grows three attributes —
the `timestamp` it was written at, the `ttl` duration it carries, and the derived
`expires_at` instant — plus a `visible_at` predicate holding the liveness rule.
Because every caller was already handed a record rather than a raw string, not
one of them cares that the record got wider. And the read chokepoint changes
shape: `_record(id)` becomes `_record_at(id, when)`, with the whole notion of
readability — not yet written, already expired, written with a dead-on-arrival
duration — inside it. `_matching` grows the same `when` parameter and forwards
it; its body is otherwise the same five lines. `_format` is untouched.

The surprising line in the measurement table is that all six carried-over public
methods changed. That number is real and it deserves an honest reading rather
than a defence. It is not the data model charging rent; it is the spec's
backward-compatibility table being implemented. `add_content`, `get_content`,
`update_content`, `delete_content`, `find_by_prefix` and `top_n_by_size` each
lost their entire body and became a one-line delegation to the `*_at` variant at
`DEFAULT_TIMESTAMP`. Collectively they gained 14 lines and lost 26 — the public
Level 1 and Level 2 surface got *shorter* at the level that supposedly broke it.
The alternative, keeping the old bodies alongside the new ones, means two
implementations of one contract and two places for it to drift; the spec
explicitly tells you not to do that.

Everything else in the diff is new surface area rather than rework: the seven
`*_at` methods, `_advance` for the clock, and `_expiry` for the one piece of
arithmetic that would otherwise be written three times.

## Level 3 → Level 4: history, and the first genuine refactor

Level 4 asked for point-in-time reads and a rollback that rewrites the past,
shifts surviving TTLs forward by the rewound interval, and erases the history of
anything created after the target. `l3.py` cannot answer any of that, and no
amount of Level 1 foresight would have let it. A single current record per id has
thrown the past away by construction.

So the storage model changes for real. `_Record` becomes `_Event` — the same
attributes plus a `kind` and a monotonic `seq` tiebreaker — and
`dict[str, _Record]` becomes `dict[str, list[_Event]]`, an append-only log per id
kept sorted by `(timestamp, seq)`. Current state stops being stored at all and
starts being derived. A delete stops being `del self._records[id]` and becomes
another event, which is exactly what makes history survivable across a delete.

What survives untouched is the public surface. `_record_at(content_id, when)`
keeps its signature and its contract — "the record readable under this id at this
instant, or None" — and only its body is rewritten, from one dict lookup into a
binary search for the last event at or before `when` followed by the same
liveness question. Ten of the thirteen carried-over public methods are byte for
byte identical to `l3.py`: `get_content_at`, `find_by_prefix_at`,
`top_n_by_size_at`, `current_time`, and all six Level 1 and Level 2 delegations.
They did not notice the storage swap because they were asking the chokepoint, not
the container.

The three that did notice are the writers — `add_content_at`, `update_content_at`
and `delete_content_at` — each of which swaps an assignment (or a `del`) for an
`_append`. Their guard clauses, their return contracts and the TTL-renewal
arithmetic in `update_content_at` are all unchanged; what changed is the shape of
the thing being written. `_matching` changed by one line, iterating `self._log`
instead of `self._records`. `_format` changed by one line, a type annotation.

`get_content_at_time` then costs four lines, because it is `get_content_at`
without the clock advance, which is to say it is the chokepoint with a different
argument. `rollback` costs thirty-one, and needs no side table and no undo stack,
because the log already is the undo stack: truncate every event newer than the
target, then re-assert the survivors at `now` with expiries shifted by `delta`.

---

## Measured

Whole-file, as `diff -u` reports it (module docstrings differ substantially
between files and are included here, since they are part of what you read):

| Transition | file length | `diff -u` added | `diff -u` removed | hunks | public methods added | carried-over public methods with a changed body | private helpers added |
|---|---|---|---|---|---|---|---|
| L1 → L2 | 87 → 119 | +46 | −18 | 3 | 2 | **0 of 4** | 2 |
| L2 → L3 | 119 → 225 | +140 | −48 | 3 | 7 | 6 of 6 | 3 (`_record` renamed to `_record_at`) |
| L3 → L4 | 225 → 338 | +155 | −53 | 7 | 2 | **3 of 13** | 5 |

Rework only — the cost inside methods that already existed, excluding every new
method, banner comment, import and docstring at module level:

| Transition | carried-over methods changed | added | removed | which ones |
|---|---|---|---|---|
| L1 → L2 | 0 | +0 | −0 | none — the diff is purely additive |
| L2 → L3 | 8 (6 public, 2 private) | +23 | −33 | the six L1/L2 methods became delegations (+14/−26, net 12 lines shorter); `__init__`, `_matching` |
| L3 → L4 | 7 (3 public, 4 private) | +41 | −24 | `add_content_at`, `update_content_at`, `delete_content_at`; `__init__`, `_record_at`, `_matching`, `_format` |

Isolating the record-to-event-log conversion itself — the L3 → L4 diff with the
Level 4 feature section (`get_content_at_time`, `rollback`, `_truncate_after`,
`_keep_through`; 54 lines) and both module docstrings removed:

| Component of the conversion | added | removed |
|---|---|---|
| `_Record` → `_Event`, plus `bisect`/`math` imports and the kind constants | +27 | −11 |
| new private log primitives (`_append` 4, `_last_event_at` 9, `_next_seq` 4) | +17 | −0 |
| the three public write methods | +26 | −13 |
| `__init__`, `_record_at`, `_matching`, `_format` | +15 | −11 |
| **conversion total** | **+85** | **−35** |

## An honest accounting of the L3 → L4 refactor

The conversion is real work: about 85 lines added and 35 removed, on top of the
54 lines the two new Level 4 features cost on their own. Anyone claiming a good
Level 1 design makes Level 4 free is selling something. What a record model plus
a read chokepoint actually buys is not the absence of the refactor but its
*containment*, and the number that measures containment is how much of the
public surface had to move.

Three public methods out of thirteen changed body, and all three changed on the
write side only: `add_content_at`, `update_content_at` and `delete_content_at`
each replaced one storage statement with an `_append`, for a combined +26/−13.
Not one read method changed. `get_content_at`, `find_by_prefix_at`,
`top_n_by_size_at` and `current_time` are identical across the two files, and so
are all six of the Level 1 and Level 2 delegations. That is the claim holding:
every read in `l4.py` still bottoms out at `_record_at`, so rewriting
`_record_at` from a dict lookup into a log search was invisible to them.

The claim I will not make is that the *writes* were free. They were not, and they
were never going to be, because "how a mutation is recorded" is the thing that
changed. A `_write(content_id, record)` helper at Level 3 would have collapsed
those three edits into one, and it would also have been a helper with exactly one
line in it, added on speculation, at a level where nothing justified it. Three
mechanical call sites is the correct price for not writing speculative
indirection, and it is the difference between a contained refactor and a rewrite:
had `l3.py` stored `dict[str, str]` and had each public method reached into that
dict itself, every one of the thirteen would have had to move.

One more line in the table is worth reading honestly. `_format`'s single changed
line is a type annotation, and `_matching`'s is the container it iterates. Both
are private, both are one line, and both are the kind of change a rename makes
rather than a redesign.

## The decision that paid for all of it

It was not the event log — that arrives at Level 4, when the spec finally demands
it, and it arrives as a genuine refactor. It was the two lines in `l1.py` that
say `self._records: dict[str, _Record] = {}` and `return self._records.get(content_id)`
inside a private `_record`. Storing a record instead of a string is what let
Level 3 add three attributes without any caller noticing; funnelling reads
through one accessor is what let Level 4 change the entire storage engine while
ten of thirteen public methods slept through it. Neither required knowing that
Levels 2, 3 or 4 existed. Both are just the answer to a question worth asking at
minute three of any exam like this one: *when the shape of the stored thing turns
out to be wrong, how many places will I have to edit?* At Level 1 the answer was
one, and it stayed one.
