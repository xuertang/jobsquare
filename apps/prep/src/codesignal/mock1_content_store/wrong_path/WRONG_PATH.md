# The wrong path, built and measured

`progression/PROGRESSION.md` argues that one Level 1 decision — store a record,
route reads through a single accessor — is what makes Levels 3 and 4 affordable.
Until now that argument was made against a hypothesis. The alternative was
described but never written, so the comparison rested on an assertion about code
that did not exist.

This directory contains that alternative, built for real and run against the same
68 tests. `naive_l1.py` through `naive_l4.py` are a complete four-level
progression written the way a competent-but-hurried candidate actually writes
one: the shortest thing that passes each level, with no thought given to what
comes next. `naive_l3_buggy.py` is the honest first draft of Level 3, kept
because what it gets wrong is the entire point. `measure.py` computes the
comparison, and every number in this document is pasted from its output rather
than typed by hand.

The headline is not the one I expected going in, and it is stated in full under
*Total cost* below. On one of the two normalisations the naive path is *cheaper*
in total typing. It loses on how many places have to agree with each other, and
on how many chances that gives you to be wrong.

## Reproducing

```bash
ICF_IMPL=wrong_path.naive_l1        python3 -m pytest -q -m "level1"
ICF_IMPL=wrong_path.naive_l2        python3 -m pytest -q -m "level1 or level2"
ICF_IMPL=wrong_path.naive_l3_buggy  python3 -m pytest -q -m "level1 or level2 or level3"
ICF_IMPL=wrong_path.naive_l3        python3 -m pytest -q -m "level1 or level2 or level3"
ICF_IMPL=wrong_path.naive_l4        python3 -m pytest -q
python3 wrong_path/measure.py
```

| file | command | result |
|---|---|---|
| `naive_l1.py` | `-m "level1"` | 13 passed, 55 deselected |
| `naive_l2.py` | `-m "level1 or level2"` | 27 passed, 41 deselected |
| `naive_l3_buggy.py` | `-m "level1 or level2 or level3"` | **1 failed, 44 passed**, 23 deselected |
| `naive_l3.py` | `-m "level1 or level2 or level3"` | 45 passed, 23 deselected |
| `naive_l4.py` | (whole suite) | 68 passed |

The five implementation files are standalone. None imports from another, from
`solution.py`, or from `progression/`; each imports only `typing` and
`__future__`. `measure.py` imports neither progression — it reads both as text
and parses them with `ast`, so its numbers describe source and cannot be
perturbed by runtime behaviour. It also tolerates `progression/` being absent or
on an older API revision, in which case it reports the naive path alone and says
so. The good path is unmodified and still passes 13 / 27 / 45 / 68 at its four
levels.

## What the naive path gets right

The naive path is not a strawman, and if it reads as one the demonstration is
worthless. Level 1 asks for four operations over a keyed store holding two values
per key. Two parallel dicts — `_bodies` and `_sizes` — is the most direct
expression of that, and it is genuinely shorter than a dataclass plus a container
of it: 32 lines against 39 with all docstrings and comments stripped, 44 against
78 as actually written. `get_content` is one line,
`return self._bodies.get(content_id)`, where the record version needs three.
There is no private read accessor because each of the four public methods asks
the dict a one-line question and a helper wrapping `dict.get` would be
indirection with no second reader. "Do not add abstraction until two callers need
it" is real advice, and at Level 1 it points squarely at this file.

Level 2 does not change that verdict; it widens the gap. Level 2 asks for
querying and says nothing about storage, so neither path touches storage, and
both diffs are purely additive — zero carried-over methods change in either.
But the naive path adds two methods of four lines each, inlining the `startswith`
walk, the `id(size)` f-string and the `", "` join into both, where the good path
adds two public methods *and* three private helpers, `_live_records`, `_format`
and `_join`. That is 9 lines against 19 code-only, 11 against 30 as written.
Cumulatively, at the end of Level 2 — a third of the way through the exam, 250 of
the 600 points already banked — the naive file is **22 lines shorter code-only
(43 vs 65, 34% smaller)** and **54 lines shorter as written (65 vs 119)**, and
its Level 1 → Level 2 transition cost **41% of the churn** of the good path's
code-only (11 vs 27) and exactly **half** as written (21 vs 42).

A candidate who stopped here would be right and would have been right the whole
way. Nothing in Levels 1 or 2 contains any information that argues for the record
or the chokepoint. That is what makes the choice locally rational rather than
stupid, and it is why this failure mode catches strong engineers: it is not a
lapse in judgement, it is correct judgement applied to a spec that has
deliberately withheld the relevant fact.

## Where it starts costing: the Level 3 expiry bolt-on

Level 3 introduces per-item TTLs and finally gives the `timestamp` argument
something to do. It needs three new facts about every stored item: the timestamp
it was written at, the duration it carries, and the instant it dies. Both paths
must store all three. The good path adds them as fields on the `_Record` it was
already storing — and it already had the first of the three, because it wrote
`timestamp` down at Level 1. The naive path has no record to add fields to, so
the same three facts become three more parallel dicts: `_starts`, `_ttls`,
`_expires`. At the end of Level 3 the good path's store is one container wide
(`_records`) and the naive path's is five.

Something about this level is worth noticing before the numbers. **Level 3
introduces no new methods and renames nothing.** Because `timestamp` has been the
first parameter of every public method since Level 1, there is no parallel
timestamped API to add and no signature to change; the entire level lands inside
existing method bodies. That is why the naive path's Level 2 → Level 3 transition
has **zero lines of new surface** and 57 lines of rework code-only, against the
good path's 9 and 14. Nothing about the shape of the naive file announces that a
load-bearing change just happened. It is the same six methods it always had, and
five of them now silently mean something different.

That is the visible cost and it is the smaller one. The real cost is the
liveness rule, `t <= q < t + d`, and where it has to live. `measure.py` counts
this two ways, both mechanically. A *storage read site* is a method that loads a
storage container somewhere that is not the target of an assignment or a `del` —
the places that reach into the store to answer a question. A *liveness site* is a
method containing a comparison whose source text mentions an expiry identifier —
the places that actually spell the rule out.

| at Level 3 | good path | naive path |
|---|---|---|
| storage read sites | **2** | **6** |
| defs spelling out the liveness rule | **1** | **6** |
| individual expiry comparisons | **2** | **12** |
| storage containers in `__init__` | 1 | 5 |
| rework inside carried-over defs (code-only) | 14 | **57** |
| new surface added (code-only) | 9 | **0** |

The good path's two read sites are `_record_at` and `_live_records`, and
`_live_records` does not test liveness itself — it asks `_record_at`. So the rule
exists in exactly one place, `_Record.alive_at`, and expiry landing at Level 3
meant teaching one method a new fact. The naive path's six read sites are
`add_content`, `get_content`, `update_content`, `delete_content`,
`find_by_prefix` and `top_n_by_size` — every public method it has, and all six had
to be visited and taught the rule independently. Six is not six times the typing;
twelve comparisons against two is only ten lines. Six is six things that must
stay in agreement forever, and six chances to be wrong once.

### The two misses

`naive_l3_buggy.py` is what actually came out of that pass, before the tests were
run. Two of the six sites are wrong. The bugs are not contrived — each is what
falls out of patching six places in a file while a clock runs, and each has a
different flavour of oversight.

**`test_add_over_expired_id_succeeds_and_resurrects` fails.** The duplicate-id
guard in `add_content` is still the Level 1 guard, `if content_id in self._bodies`.
The spec says an add over an expired id must succeed and resurrect it; this
returns `False`, because presence of a key is not liveness:

```
>       assert store.add_content(5, "a", "v2", 2, ttl=5) is True
E       AssertionError: assert False is True
1 failed, 44 passed, 23 deselected
```

What makes this the most likely miss of the two is that it is the one read path
that does not look like a read — it is a guard clause on a *writer*. Going around
adding liveness checks to the readers does not take you there. The good path
could not make this mistake, not because its author was more careful, but because
`add_content`'s guard is `if self._record_at(content_id, timestamp) is not None`,
and `_record_at` is the same method `get_content` uses. Getting the guard right
was not a separate act.

**The second miss survives the Level 3 suite entirely, and it is the most
valuable thing in this directory.** `find_by_prefix` got the expiry half of the
rule and not the "not yet written" half — it checks `timestamp >= expires` but
never `timestamp < self._starts[cid]`. The reason is worth stating precisely,
because it is not carelessness: `find_by_prefix` already had a loop with a
`continue` in it, so the patch was to drop one more `continue` into the loop that
was already there, and the thing on your mind while reading a level titled *Time
and TTL* is expiry, not the fact that a query can now name an instant before a
write. One method further down, `top_n_by_size` got the whole rule correctly,
because its match collection had to be rebuilt anyway to fit the liveness filter
alongside the two-key sort — and rebuilding it meant re-deriving the rule from
the spec rather than inheriting Level 2's assumptions. **Editing carries the old
assumptions forward; rewriting does not.** That is the whole difference between
the two sites, and it is invisible in the diff.

Level 3 guarantees non-decreasing timestamps on mutating calls, and none of its
own tests reads a prefix at an instant earlier than a write, so the missing half
is never exercised. The Level 3 suite passes it. It detonates one level later:

```
ICF_IMPL=wrong_path.naive_l3_buggy python3 -m pytest -q \
    test_solution.py::test_ttl_and_never_expiring_content_coexist

        store.add_content(0, "a", "A", 1)          # no ttl: forever
        store.add_content(5, "b", "B", 2, ttl=3)   # dies at 8
        assert store.get_content(0, "b") is None   # not written yet -- passes
>       assert store.find_by_prefix(0, "") == "a(1)"
E       AssertionError: assert 'a(1), b(2)' == 'a(1)'
1 failed
```

Read those last two assertions together. `get_content` and `find_by_prefix` are
asked the *same question about the same id at the same instant* and give
different answers, because on this path they are two independent implementations
of one rule and only one of them was fully patched. That divergence is
structurally impossible in the good path: both routes end at `_record_at`.

The lesson is not "bugs happen". It is that neither of these is a mistake a type
checker, a linter or the interpreter can see. Every dict is present, every key is
populated, every method returns the right type. The invariant is a convention
held in the author's head across six locations, and the only mechanism enforcing
it is the author's memory at minute fifty. A model with N unguarded read paths
gives you N chances to forget; here one miss cost a visible test failure and the
other bought forty minutes of false confidence, on a file that reported 44 of 45
green. In the good path there is exactly one place to forget, and forgetting it
fails everything at once, immediately.

### The new observation: an argument discarded, not a field uninvented

There is one thing this convention makes visible that a `current_time()`-style
API would not. The naive Level 1 does not merely fail to invent a field it was
never given. It is *handed* `timestamp` on every one of four calls, stores
`content_id`, stores `body`, stores `size`, and drops the fourth argument on the
floor. Three of four arguments are written down and one is destroyed. On the page
that is a much sharper mistake than "did not think to record a creation time",
and it is mechanically detectable: `ruff`'s `ARG002` and `pylint`'s
`unused-argument` flag every one of those four methods without being asked.

Does that make the error easier to catch in practice? **Not at the moment it is
made — and arguably harder.** The one signal that would flag it is pre-emptively
explained away by the spec itself, which says in bold that Level 1 never reads
`timestamp`. A warning you have been told in advance to expect is a warning you
switch off, and it fires uniformly on all four methods, which reads as intentional
convention rather than as a defect. Worse, the good path's own Level 1
`get_content` also ignores its `timestamp` — only its *writers* use it — so even
"which methods ignore the argument" does not cleanly separate the two designs at
Level 1. The signal is loud, universal, and pre-authorised, which is the worst
combination a signal can have.

Where it does pay off is later, and this is a real difference from the old
convention. At Level 3, "which methods still never mention `timestamp`?" is a
mechanical, greppable query over the file, and on this path it returns exactly
the sites that have not yet been taught the liveness rule. The old
`add_content_at`-style API offered no such handle: there, the missing thing was a
field nobody had named. So the honest answer is split. **Harder to catch at the
moment of the mistake, because the spec licenses the smell; easier to enumerate
at the moment of repair, because the unused argument marks every unpatched
site.** Note which of those two the candidate under time pressure actually gets:
the second one, and only if they think to run the query. Neither of
`naive_l3_buggy.py`'s two bugs would have been caught by it anyway — both are in
methods that *do* mention `timestamp`, just not enough times.

## The Level 4 wall

Level 4 asks two things that five dicts of current state cannot answer at any
price. `get_content_at_time(timestamp, cid, time_at)` wants the body an id had at
`time_at`; the dicts hold the body it has *now*, and `self._bodies[cid] = body`
destroyed the previous one on the way past. `rollback(timestamp, time_at)` wants
the whole store returned to its state at `time_at`, with surviving TTLs shifted
forward — which needs, for every id, what its body, size and TTL duration were at
`time_at`, and whether it was live then at all. A `del` on delete threw even the
id's existence away.

This is not a failing of the naive path specifically. `progression/l3.py` cannot
answer these either, and the good path's own writeup is explicit that no amount
of Level 1 foresight avoids the refactor. The past is not derivable from the
present. Something in storage has to start holding it, and that is a storage
change in any design. The only question Level 4 actually asks is *where the new
container goes*, and the answer is forced by how many methods are looking at the
old one.

The good path replaced its container. `dict[str, _Record]` became
`dict[str, list[_Event]]`, an append-only log per id; current state stopped being
stored and started being derived; `_record_at` kept its exact signature and
contract and had only its body rewritten, from a dict lookup into a binary search
for the last event at or before `when`. Five of its twelve carried-over defs came
through byte-identical, and — the row that matters — **`get_content`,
`find_by_prefix` and `top_n_by_size` are among them.** The three readers did not
change by one character between Level 3 and Level 4, because they were asking the
chokepoint rather than the container.

The naive path cannot do that, and it does not try. Converting five dicts into a
log means editing all six methods that read them, at minute sixty, each edit
another chance to reintroduce the Level 3 bugs. So `naive_l4.py` makes the only
cheap move available from where it stands: it adds a *sixth* container,
`_history`, beside the five and leaves the five exactly as they were. The two new
Level 4 methods read the history; the other six keep reading the dicts. It works
— 68 of 68 — and it is the right call given the starting position. It is also
double bookkeeping, and the measurement shows exactly where that surfaces.

| L3 → L4 | good path | naive path |
|---|---|---|
| churn, code-only | 66 | 84 |
| churn, as written | 142 | 137 |
| rework inside carried-over defs (code-only) | 12 | 12 |
| carried-over defs whose body changed | 7 of 12 | 4 of 7 |
| new surface, code-only | 37 | 56 |
| liveness sites after | 2 | 8 |
| expiry comparisons after | 3 | 19 |
| instance attributes after | 2 | 7 |
| final file size, code-only | 131 | **175** |

Read the rework row honestly: at Level 4 the naive path reworks *exactly as much*
as the good path, and touches fewer existing methods. That is not the naive path
winning. It is the naive path declining the refactor, which it can only do by
keeping two authoritative representations of the same facts. Every writer now
performs five dict assignments *and* appends an entry, and if the two ever
disagree the store lies with no test to catch it. `rollback` cannot rewind the
dicts incrementally — they contain no history to rewind — so it truncates the log
and then rebuilds all five dicts from scratch, which is a second, independent
implementation of "what is the current state" living inside one method. And the
liveness rule, already written six times, is now written eight, in two dialects:
six sites compare against `self._expires[cid]` and two compare against
`entry.expires`. Nineteen expiry comparisons against the good path's three. The
cost was not refused, it was converted from rework into permanent surface area:
the finished naive file is 175 lines of code against 131, **34% larger**, for
identical behaviour.

One extra consequence is specific to this API and worth recording. There is no
`current_time()` anywhere in this problem — every method is told what "now" is by
its own first argument, precisely so the store never has to hold a clock. The
good path never breaks that: `rollback` appends a restore event at the caller's
`timestamp` and the derivation does the rest. The naive path's `rollback` has to
*rebuild* five current-state dicts, and a rebuilt `_starts` entry has to say
something, so it writes `self._starts[cid] = timestamp`. The five dicts now hold
state whose meaning depends on when the last rollback happened. The side table
did not merely duplicate the data; it forced the store to take a position on
"now" that the API deliberately never asked it to hold.

## Total cost, honestly

```
                     good path    naive path
churn, code-only           121           152     (+26%)
churn, as written          255           238     (naive 7% LOWER)
rework, code-only           26            69     (naive 2.7x)
rework, as written          85            97
final size, code-only      131           175     (+34%)
```

One of those rows is worse for the good path, and pretending otherwise would
poison everything above. On the as-written measure the naive path costs **less**
total churn over the whole exam — 238 against 255. That happens because the good
path's files carry substantially more docstring and comment prose per method, so
its diffs are longer for reasons that have nothing to do with its data model.
That is exactly why `measure.py` reports a code-only variant, canonicalised
through `ast.unparse` with all docstrings and comments removed. On that variant
the naive path costs 26% more churn over the exam and ends 34% larger. I trust
the code-only numbers and I would not defend the as-written ones in either
direction.

The rework rows are the ones that changed most against the previous revision of
this document, and the change is instructive rather than convenient. Under the
older API — where each level added a parallel `*_at` method — rework barely
separated the two paths (34 vs 39 code-only) and the document said so, declining
to claim it as a win. Under this convention it separates them by 2.7x, 26 against
69. The reason is mechanical, not rhetorical: with `timestamp` on every signature
from Level 1, Level 3 adds no methods at all, so *every* line of its cost falls
inside existing method bodies, which is what "rework" measures. The naive path's
Level 2 → Level 3 is 57 lines of rework and zero lines of new surface; the good
path's is 14 and 9. The old measure was diluted by signature churn that had
nothing to do with either data model. This one is not, and it now says what the
read-site count always said.

So the claim can be made a little more firmly than before, and the firm part is
still narrow. The naive path is meaningfully cheaper for the first third of the
exam and meaningfully more expensive by the end; the crossover is at Level 3,
exactly where the spec first changes the definition of which records are
readable; one invariant lives in 1 place versus 6 at Level 3 and 2 versus 8 at
Level 4; and when that invariant had to be introduced across six sites instead of
one, two of the six came out wrong on the first pass, of which one was not caught
by the level's own tests. What the numbers still cannot show is time. I have not
converted lines into minutes anywhere in this document and will not: typing speed
is not measured here, the debugging time for the two bugs is not measured here,
and a number invented for either would be the least defensible sentence on the
page and would discredit the measured ones next to it. The defensible claim is
about *shape* — how many places must agree — and shape is what got measured.

## When the naive path is genuinely right

The bet the good path makes is not "records beat dicts" in general. It is
specifically that *the predicate defining which records are readable* is the thing
this exam format mutates, and that funnelling every read through one place is
therefore cheap insurance. That bet can lose, and it loses in at least two
realistic worlds.

If the exam were two levels, the naive path wins outright and by a clear margin —
34% less code at the end of Level 2 and 41% of the churn on the only transition.
No qualification is needed; the good path's `_live_records`, `_format`, `_join`
and `_record` are pure overhead in a two-level world, four helpers serving callers
that never diverge. More sharply: if Level 4 had asked for something orthogonal to
history, the chokepoint would have earned nothing. A Level 4 asking for a
secondary index — group content by category, or maintain a global size
leaderboard — lands as new surface in both designs, and the naive path is arguably
*better positioned*, because "add another parallel dict keyed by id" is the move
it is already making and the record model would need a new field plus a new index
anyway. A Level 4 asking for bulk operations, a different output format, or
import/export would be close to free in both, and the whole argument would be
moot.

The honest generalisation is not "always build the chokepoint." It is that a read
chokepoint is cheap at Level 1 — one private method, three lines — and that it
pays out precisely when a later level redefines visibility. TTLs, soft deletes,
permissions, tenancy, versioning and point-in-time reads are all the same shape,
and between them they cover most of what problems in this format actually escalate
into. That makes it a good bet rather than a certain one, and the measurement here
prices it: roughly 22 lines of premium paid across Levels 1 and 2, against a
Level 3 where one place must learn the new rule instead of six, and a Level 4 that
ends 44 lines smaller with one representation of state instead of two.

## `measure.py` output, verbatim

```
==============================================================================
ICF Mock 1 -- ContentStore: good path vs naive path, measured
==============================================================================

  good path:   progression/l1.py .. l4.py
  naive path:  wrong_path/naive_l1.py .. naive_l4.py

Module docstrings are excluded from every count below, so the
comparison is about code rather than about how much each file
explains itself.

==============================================================================
AS WRITTEN -- module docstrings excluded; method docstrings,
comments and blank lines included.
==============================================================================

FILE LENGTH (lines)
------------------------------------------------------------------------------
level   |  good path | naive path | naive - good
------------------------------------------------------------------------------
L1      |         78 |         44 |          -34
L2      |        119 |         65 |          -54
L3      |        158 |        130 |          -28
L4      |        248 |        261 |          +13

WHOLE-FILE CHURN PER TRANSITION
------------------------------------------------------------------------------
           |            good path          |           naive path          
transition |  added removed changed   churn|  added removed changed   churn
------------------------------------------------------------------------------
L1->L2     |     41       0       1      42|     21       0       0      21
L2->L3     |     40       1      30      71|     65       0      15      80
L3->L4     |    100      10      32     142|    131       0       6     137
------------------------------------------------------------------------------
TOTAL      |                            255|                            238

REWORK VS NEW SURFACE PER TRANSITION
------------------------------------------------------------------------------
           |            good path          |           naive path          
transition | methods  rework    new retired| methods  rework    new retired
------------------------------------------------------------------------------
L1->L2     |     0/6       0     30       0|     0/5       0     11       0
L2->L3     |    8/10      42     17       8|     7/7      77      0       0
L3->L4     |    7/12      43     66       3|     4/7      20     89       0
------------------------------------------------------------------------------
TOTAL      |              85               |              97               

  methods = defs present in BOTH files whose source differs, over
            the number of defs present in both. Renames excluded.
  rework  = churn INSIDE those carried-over defs (alignment-proof).
  new     = lines of defs that exist only in the later file.

STORAGE READ SITES PER LEVEL
------------------------------------------------------------------------------
level   |  good path | naive path 
------------------------------------------------------------------------------
L1      |          1 |          4 
L2      |          2 |          6 
L3      |          2 |          6 
L4      |          4 |          8 

LIVENESS-RULE SITES PER LEVEL (defs that spell the rule out)
------------------------------------------------------------------------------
        |      good path    |     naive path    
level   |     defs  compares|     defs  compares
------------------------------------------------------------------------------
L1      |        0         0|        0         0
L2      |        0         0|        0         0
L3      |        1         2|        6        12
L4      |        2         3|        8        19

  L3 good path: _Record.alive_at(2)
  L3 naive path: ContentStore.add_content(2), ContentStore.get_content(2), ContentStore.update_content(2), ContentStore.delete_content(2), ContentStore.find_by_prefix(2), ContentStore.top_n_by_size(2)
  L4 good path: _Event.alive_at(2), ContentStore.rollback(1)
  L4 naive path: ContentStore.add_content(2), ContentStore.get_content(2), ContentStore.update_content(2), ContentStore.delete_content(2), ContentStore.find_by_prefix(2), ContentStore.top_n_by_size(2), ContentStore.get_content_at_time(2), ContentStore.rollback(5)

The Level 3 read sites, named. These are the distinct call sites that
had to be visited and taught the liveness rule when expiry landed:

  good path (2):
    ContentStore._record_at
    ContentStore._live_records
  naive path (6):
    ContentStore.add_content
    ContentStore.get_content
    ContentStore.update_content
    ContentStore.delete_content
    ContentStore.find_by_prefix
    ContentStore.top_n_by_size

Storage containers detected at Level 3:
  good path: _records
  naive path: _bodies, _expires, _sizes, _starts, _ttls

PER-TRANSITION DETAIL
==============================================================================
good path
------------------------------------------------------------------------------
  L1->L2: +41 -0 ~1 (churn 42) | rework 0 in 0 of 6 carried-over defs
    added:   ContentStore._format, ContentStore._join, ContentStore._live_records, ContentStore.find_by_prefix, ContentStore.top_n_by_size
  L2->L3: +40 -1 ~30 (churn 71) | rework 42 in 8 of 10 carried-over defs
    changed: ContentStore.__init__, ContentStore._live_records, ContentStore.add_content, ContentStore.delete_content, ContentStore.find_by_prefix, ContentStore.get_content, ContentStore.top_n_by_size, ContentStore.update_content
    added:   ContentStore._expiry, ContentStore._record_at, _Record.alive_at
    removed: ContentStore._record
  L3->L4: +100 -10 ~32 (churn 142) | rework 43 in 7 of 12 carried-over defs
    changed: ContentStore.__init__, ContentStore._format, ContentStore._live_records, ContentStore._record_at, ContentStore.add_content, ContentStore.delete_content, ContentStore.update_content
    added:   ContentStore._append, ContentStore._keep_through, ContentStore._last_event_at, ContentStore._next_seq, ContentStore._truncate_after, ContentStore.get_content_at_time, ContentStore.rollback, _Event.alive_at
    removed: _Record.alive_at

naive path
------------------------------------------------------------------------------
  L1->L2: +21 -0 ~0 (churn 21) | rework 0 in 0 of 5 carried-over defs
    added:   ContentStore.find_by_prefix, ContentStore.top_n_by_size
  L2->L3: +65 -0 ~15 (churn 80) | rework 77 in 7 of 7 carried-over defs
    changed: ContentStore.__init__, ContentStore.add_content, ContentStore.delete_content, ContentStore.find_by_prefix, ContentStore.get_content, ContentStore.top_n_by_size, ContentStore.update_content
  L3->L4: +131 -0 ~6 (churn 137) | rework 20 in 4 of 7 carried-over defs
    changed: ContentStore.__init__, ContentStore.add_content, ContentStore.delete_content, ContentStore.update_content
    added:   ContentStore.get_content_at_time, ContentStore.rollback

==============================================================================
CODE-ONLY VARIANT -- all docstrings, comments, blank lines and
formatting differences removed by round-tripping through ast.unparse.
One canonical line per statement.
==============================================================================

FILE LENGTH (lines)
------------------------------------------------------------------------------
level   |  good path | naive path | naive - good
------------------------------------------------------------------------------
L1      |         39 |         32 |           -7
L2      |         65 |         43 |          -22
L3      |         79 |         94 |          +15
L4      |        131 |        175 |          +44

WHOLE-FILE CHURN PER TRANSITION
------------------------------------------------------------------------------
           |            good path          |           naive path          
transition |  added removed changed   churn|  added removed changed   churn
------------------------------------------------------------------------------
L1->L2     |     26       0       1      27|     11       0       0      11
L2->L3     |     14       0      14      28|     51       0       6      57
L3->L4     |     52       0      14      66|     81       0       3      84
------------------------------------------------------------------------------
TOTAL      |                            121|                            152

REWORK VS NEW SURFACE PER TRANSITION
------------------------------------------------------------------------------
           |            good path          |           naive path          
transition | methods  rework    new retired| methods  rework    new retired
------------------------------------------------------------------------------
L1->L2     |     0/6       0     19       0|     0/5       0      9       0
L2->L3     |    7/10      14      9       2|     7/7      57      0       0
L3->L4     |    7/12      12     37       2|     4/7      12     56       0
------------------------------------------------------------------------------
TOTAL      |              26               |              69               

  methods = defs present in BOTH files whose source differs, over
            the number of defs present in both. Renames excluded.
  rework  = churn INSIDE those carried-over defs (alignment-proof).
  new     = lines of defs that exist only in the later file.

STORAGE READ SITES PER LEVEL
------------------------------------------------------------------------------
level   |  good path | naive path 
------------------------------------------------------------------------------
L1      |          1 |          4 
L2      |          2 |          6 
L3      |          2 |          6 
L4      |          4 |          8 

LIVENESS-RULE SITES PER LEVEL (defs that spell the rule out)
------------------------------------------------------------------------------
        |      good path    |     naive path    
level   |     defs  compares|     defs  compares
------------------------------------------------------------------------------
L1      |        0         0|        0         0
L2      |        0         0|        0         0
L3      |        1         2|        6        12
L4      |        2         3|        8        19

  L3 good path: _Record.alive_at(2)
  L3 naive path: ContentStore.add_content(2), ContentStore.get_content(2), ContentStore.update_content(2), ContentStore.delete_content(2), ContentStore.find_by_prefix(2), ContentStore.top_n_by_size(2)
  L4 good path: _Event.alive_at(2), ContentStore.rollback(1)
  L4 naive path: ContentStore.add_content(2), ContentStore.get_content(2), ContentStore.update_content(2), ContentStore.delete_content(2), ContentStore.find_by_prefix(2), ContentStore.top_n_by_size(2), ContentStore.get_content_at_time(2), ContentStore.rollback(5)
```
