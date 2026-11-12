# The progression: what `CampaignScheduler` looked like at the end of each level

This directory holds four complete, self-contained implementations. `l1.py` is the file as it
stood the moment Level 1's tests went green, `l2.py` the moment Level 2's did, and so on. None
of them imports from `solution.py`, none imports from any of the others, and none subclasses
another, so a plain diff between two adjacent files is an exact, honest bill for that level:

```
diff -u progression/l1.py progression/l2.py
diff -u progression/l2.py progression/l3.py
diff -u progression/l3.py progression/l4.py
```

Each file passes every test up to and including its own level:

```
ICF_IMPL=progression.l1 python3 -m pytest -q -m "level1"                       # 12 passed
ICF_IMPL=progression.l2 python3 -m pytest -q -m "level1 or level2"             # 25 passed
ICF_IMPL=progression.l3 python3 -m pytest -q -m "level1 or level2 or level3"   # 47 passed
ICF_IMPL=progression.l4 python3 -m pytest -q                                   # 64 passed
```

The one rule that governs all four files is *no clairvoyance*. Each snapshot contains only what
that level's spec justifies. `l1.py` has no budget, no impressions, no rate limiting, no
snapshots and no event log, and its `__init__` takes no arguments, because Level 1 asks for none
of that and writing it anyway would be cheating at the exact skill the drill exists to test.
Reading the four files in order should feel like watching someone who does not know what is
coming, and who nonetheless keeps getting away with it — right up to the level where they stop
getting away with it, which is reported here in full rather than smoothed over.

## The Level 1 timestamp: keep it or drop it?

The ICF convention hands every method a `timestamp` from Level 1 onward, and Level 1's spec is
blunt that nothing reads it. That creates a decision this progression has to take a position on,
so: **`l1.py` keeps it.** `_Campaign` carries a `created_at: int`, and `create_campaign` files
the timestamp it was given onto the record it builds.

The reasoning is a distinction between two things that superficially look alike. Inventing a
`budget` field at Level 1 is speculation: no caller has mentioned money, no signature carries an
amount, and the only way to justify the field is to have read ahead. Storing `created_at` is not
speculation, because the value is already in your hands — a caller passed it, explicitly, on
every single call. Declining to throw it away is bookkeeping, not prediction. The asymmetry is
in the input, not in the guess: you can only store what someone gave you, and nobody has given
you a budget. That is the line `l1.py` draws, and it is a line you can defend out loud in an
interview without claiming any knowledge of Level 3.

Whether it *paid* is a separate question from whether it was defensible, and it is answered
honestly in its own section below. The short version is that it did not pay. It was inert.

## Measured numbers

Computed with a throwaway script using `difflib.SequenceMatcher` over the file lines and an
`ast` walk comparing each method's exact source text between adjacent files (the script was
deleted afterwards; every number here is reproducible from the four files). "Rewritten" counts
lines inside `replace` opcodes — *n* old lines became *m* new ones. The first table is the whole
file; the second strips each file's module docstring, since that docstring is prose about the
design rather than the design itself and it inflates the counts.

**Whole file**

| Transition | lines | added | removed | rewritten | methods carried over unchanged | methods with changed body | new methods |
|---|---|---|---|---|---|---|---|
| L1 → L2 | 107 → 142 | 35 | 0 | 1 → 1 | 7 | 0 | 4 (3 public) |
| L2 → L3 | 142 → 223 | 64 | 0 | 9 → 26 | 7 | 4 (3 public) | 4 (3 public) |
| L3 → L4 | 223 → 337 | 94 | 0 | 19 → 39 | 8 | 7 (7 public) | 7 (3 public) |

**Code only (module docstring excluded)**

| Transition | lines | added | removed | rewritten |
|---|---|---|---|---|
| L1 → L2 | 81 → 110 | 29 | 0 | 0 → 0 |
| L2 → L3 | 110 → 174 | 47 | 0 | 8 → 25 |
| L3 → L4 | 174 → 266 | 94 | 0 | 12 → 10 |

Two cells need footnotes so the tables are not read as better than they are. The `1 → 1` rewrite
in the L1 → L2 whole-file row is the module docstring's first line, where "lifecycle CRUD only"
becomes "CRUD plus ranked queries"; the code-only table shows the real figure, which is zero. And
the seventh new method in the L3 → L4 row is `_Event.describe`, which lives on a private
dataclass rather than on the scheduler, so the scheduler itself gained six methods there, three
of them public. Nothing was ever deleted in any transition — the removed column is zero
throughout, which is the one genuinely clean signal in the tables.

## L1 → L2: the level that cost nothing

Level 2 demanded three public read methods — `list_by_channel`, `top_campaigns` and
`count_active` — which all report only *eligible* campaigns, all share one ranking (priority
descending, then id ascending under plain string comparison), and all share one output format,
`"<id>(priority=<p>)"` joined by `", "` into a single string. The spec is emphatic that Level 3
will widen the definition of eligible and that eligibility should therefore be written once.

The methods this transition touched: none. The methods it added: `_ranked`, plus the three
public readers. `_ranked` is the only place in the file that filters, the only place that sorts,
and the only place that renders an entry; it hands back a ranked list of already-formatted
strings, and the three public methods do nothing but join it, slice-then-join it, or take its
length. Twenty-nine lines of new code appended in a new `# Level 2` section, and not one
existing line of code altered — the code-only rewrite count is a literal zero. The `ast`
comparison confirms all seven pre-existing methods (`__init__`, `_is_eligible`,
`create_campaign`, `get_campaign`, `pause_campaign`, `resume_campaign`, `delete_campaign`) are
byte-identical between `l1.py` and `l2.py`.

That is not luck, and it is worth being precise about why. `_ranked` needs to ask each campaign
for a channel, a priority and a liveness verdict in one place. Level 1 had stored one record per
id instead of three parallel dicts keyed by id, so that question has one place to be asked. Had
Level 1 stored `self._channels`, `self._priorities` and `self._paused` separately, the
comprehension inside `_ranked` would have had to join three dicts by hand, and Level 3's two new
fields would have made it five.

## L2 → L3: the widening predicate

Level 3 is where the data model genuinely changes. Campaigns acquire a remaining budget with a
sentinel for uncapped, `serve` carries a timestamp that is explicitly *not* guaranteed to be
non-decreasing, and each campaign gets its own sliding-window allowance evaluated over the
half-open interval `(timestamp - W, timestamp]`. The constructor widens to
`(window=60, max_impressions_per_window=5)` and becomes the one place in the whole exercise that
raises. And, crucially, the definition of eligible widens: eligible now means active **and** not
budget-exhausted, where exhausted means `remaining_budget == 0`.

The last of those is the interesting one, because it changes a rule that three already-published
public methods depend on. In `l3.py` the entire change is inside `_is_eligible`:

```python
    def _is_eligible(self, campaign: _Campaign) -> bool:
        if not campaign.active:
            return False
        return campaign.budget == UNLIMITED or campaign.budget > 0
```

One line became three. Because `_ranked` is the only caller that matters and the three public
readers are thin wrappers over it, the new exclusion rule propagates all the way out to the
public contract without anyone editing the methods that implement it.

**Byte-identity verification.** This is the mock's central claim, so it was checked rather than
asserted. An `ast` walk extracting each method's exact source segment from `l2.py` and `l3.py`
reports `list_by_channel`, `top_campaigns`, `count_active` and `_ranked` as byte-for-byte
identical across the transition — SHA-256 prefixes `2d262002e03e`, `a34767274d3f`,
`3c7eeca5e152` and `f5e0318fcab3` respectively, matching in both files. A `diff -u` restricted to
the `# Level 2` section of each file emits no changed line at all; the only hunk is the new
`# Level 3` section header appended after it. A level that explicitly redefines what those three
methods return touched none of their source. The same four methods are byte-identical again
between `l3.py` and `l4.py`, so all three public Level 2 readers survive both later levels
unedited. `get_campaign`, `create_campaign` and `delete_campaign` also carry over untouched, and
`get_campaign` staying untouched is itself a graded requirement: exhaustion is not a lifecycle
status, so an exhausted campaign must still report `status=active`.

The widening was not free, though, and the honest accounting matters more than the tidy story.
Four methods changed body: `__init__`, `_is_eligible`, `pause_campaign` and `resume_campaign`.
The first two are the level's actual work. The other two are the bill for having *over-applied*
the predicate at Level 1. In `l1.py` and `l2.py`, `pause_campaign` guards with
`not self._is_eligible(campaign)` and `resume_campaign` with `self._is_eligible(campaign)`,
which is correct at those levels because eligible and active are the same question there. Level
3 splits that question in two — an exhausted campaign is ineligible for delivery but is still
lifecycle-active, must still be pausable, and must still refuse a redundant resume — so both
guards drop back to reading `campaign.active`, the flag those two methods own and mutate. One
line each.

The point is not that the chokepoint prevented that change; it is that the chokepoint made it
findable. `grep -n _is_eligible l2.py` returns three call sites and enumerates, in one command
and with no reasoning required, every place in the file whose behaviour the new rule could
possibly alter. One of the three — `_ranked`, and through it all three public readers — wanted
the new behaviour and got it for nothing. The other two did not, and cost a line apiece. After
the edit `l3.py` has a single call site left, which is the shape the predicate should have had
all along.

The rest of Level 3 is purely additive: a `UNLIMITED = -1` sentinel, two new fields on
`_Campaign`, `set_budget`, `remaining_budget`, `serve`, and `_impressions_in_window`
implementing the half-open window as `sum(1 for ts in campaign.impressions if low < ts <=
timestamp)`. Filtering the whole recorded list against the timestamp handed in — rather than
evicting old entries from a deque as impressions age — is what makes the out-of-order timestamps
of worked example 3d fall out for free: an impression recorded at t=100 simply does not lie in
`(80, 90]`, and it is still sitting there to be counted when a serve at t=105 asks.

Deliberately absent from `l3.py`: any event log. Level 3 asks for no history and no rollback, so
`l3.py` mutates campaign records in place and keeps nothing it does not need. Building the log
here because Level 4 is going to want it would be exactly the same clairvoyance error as putting
budgets in `l1.py`. A grep of `l3.py` for `_Event`, `_log`, `_record`, `_apply` and `_rebuild`
returns nothing.

## L3 → L4: an honest refactor

Level 4 asks for three things Level 3's model cannot answer: capture the entire system state
under a name; put the system back exactly as it was, including rate-limit availability at the
very same timestamps; and produce an ordered audit trail of every successful state-changing
operation for a campaign, a trail that outlives deletion of that campaign and is itself rolled
back by a restore. Mutable state that has been overwritten in place cannot say what it used to
be, and it cannot say what happened to it. No chokepoint written at Level 1 makes that free, and
this section does not pretend one did.

So `l4.py` converts the model. Every mutation becomes an immutable frozen `_Event` appended to a
single append-only `self._log`; `self._campaigns` becomes *derived* state that only `_apply` is
permitted to touch; and every public mutator becomes validate-then-delegate. The measured cost
is 94 added lines, 12 lines rewritten into 10, and changed bodies in seven public methods:
`__init__`, `create_campaign`, `pause_campaign`, `resume_campaign`, `delete_campaign`,
`set_budget` and `serve`. Every method in the file that used to assign to state had to stop
assigning. That is a wide blast radius and it should not be described as a narrow one.

The 94 added lines break down as follows. The `_Event` dataclass is 20 lines, of which
`describe` is 9. The replayer machinery is 34: `_apply` 25, `_rebuild` 5, `_record` 4. That is 54
lines — a little over half the level — spent on a storage model the spec never asked for by
name. The three methods Level 4 actually asked for come to 21 lines: `snapshot` 8, `restore` 8,
`history` 5. The remainder is section comments and blank lines. If you want a one-sentence
summary of where the money went: two-thirds of Level 4 was paying for the ability to answer the
question, and one-third was answering it.

What the earlier chokepoints did buy is the *shape* of the damage rather than its size. Every one
of those seven rewrites is the same mechanical edit — delete the assignment, call
`self._record(_Event(...))`, leave the validation exactly where it was. Not one validation rule
was re-derived and not one read path moved. Eight methods are byte-identical across the
transition, including all four Level 2 query methods and helpers, plus `get_campaign`,
`remaining_budget`, `_impressions_in_window` and, notably, `_is_eligible`. The predicate Level 3
widened survived a change of storage model without being reopened, because it reads materialized
state and materialized state is still a `dict[str, _Campaign]` after the refactor; only the
authority to write it moved.

There is a specific trap here worth naming, because it is why log-and-replay is the safer model
rather than merely the more fashionable one. The obvious cheaper `snapshot` is a copy of
`self._campaigns` — O(state) instead of O(history), and it needs no `_Event` class at all. It is
correct only for as long as you remember that `_Campaign` carries a *mutable* field,
`impressions: list[int]`. A `dict(self._campaigns)`, or a hand-rolled `_Campaign(**vars(c))` per
entry, copies the budget integer correctly and **shares the impressions list**. The resulting
bug is close to invisible: budgets roll back, statuses roll back, `get_campaign` and
`count_active` all look right, and the single symptom is a sliding-window rate limit that
remembers serves a restore was supposed to erase. It surfaces only in a test that restores and
then re-serves at the same timestamps — which is exactly what the spec demands and what
`test_serving_after_restore_behaves_as_if_intervening_serves_never_happened` and
`test_restore_rolls_back_the_sliding_window_impression_log` check. Immutability removes the
question: `_Event` is frozen, so `tuple(self._log)` is structural sharing, O(n) pointers with
zero object copying, and no later activity can reach into a stored capture. The cheapest
implementation of all — storing a bare integer log *offset* — is wrong for a different reason:
restore an early capture, then a later one, and the offset indexes a log that has been truncated
out from under it. Capture the prefix, not the position.

## Did keeping the Level 1 timestamp help?

No. It was inert, and the measurement is small enough to state exactly: `created_at` occupies
**two lines of code in every one of the four files** — the field declaration on `_Campaign`, and
the keyword argument that populates it. Nothing in `l1.py`, `l2.py`, `l3.py` or `l4.py` ever
reads it. No test asks for it. It did not shorten the Level 3 rate limiter, which needs a
per-serve timestamp list rather than a per-campaign creation instant, and it did not shorten the
Level 4 audit trail, which reconstructs everything from the log.

It was not quite costless either. At Level 4, keeping `created_at` alive across a restore means
the `create` event has to carry the timestamp that produced it, so `_Event.timestamp` is a
required positional field of every event rather than the optional keyword it would otherwise
have been (`serve` is the only kind that reads it). That is one design constraint and one extra
keyword argument in `_apply`, bought for nothing.

So the honest verdict is a split one, and it is worth holding both halves. The *decision* was
right — the rule "store what you were given, invent nothing" is the rule that kept `budget` out
of `l1.py`, and `budget` in `l1.py` would have been a genuine failure of the drill. The *return
on this particular application of it* was zero. Discipline that happens to pay is easy to
believe in; discipline that costs two lines and pays nothing, and that you keep anyway because
the alternative rule ("store what you think you will need") is the one that puts budgets in
Level 1, is the version actually worth practising. Do not rewrite this section into a story where
the timestamp turned out to be secretly load-bearing. It was not.

## The decision that paid for everything

One Level 1 decision did pay for everything downstream, and it is not the event log, which did
not exist until Level 4 and could not have been justified before it — nor is it `created_at`,
which paid nothing. It is the decision to answer "may this campaign be selected?" in exactly one
function. At Level 1 that predicate is a one-line body doing nothing a reader could not have
inlined: it returns `campaign.active`, and its only two callers are `pause_campaign` and
`resume_campaign`, which could perfectly well read the flag themselves. It looks like ceremony,
and two levels later it is the reason a redefinition of the published contract of three shipped
public methods costs two added lines in one private method while those three methods stay
byte-identical, verified by hash. The record type is what made the predicate cheap to write in
the first place; the predicate is what made the widening cheap to apply and, just as valuable,
cheap to *audit* under `grep`. Together they are why the only level that genuinely hurt is the
one whose requirement no amount of Level 1 discipline could have absorbed.
