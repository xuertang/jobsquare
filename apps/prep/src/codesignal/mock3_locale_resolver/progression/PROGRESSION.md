# The `LocaleResolver` progression — four snapshots

## How to read these files

`l1.py`, `l2.py`, `l3.py` and `l4.py` are four photographs of the same class at four moments: the end of Level 1, the end of Level 2, and so on. Each is complete and standalone. None imports from `solution.py`, none subclasses another, and there is no shared base module — the duplication is the point, because it makes the diff between two adjacent files an exact measurement of what a level cost.

```bash
cd /root/airbnb-icf-prep/mocks/mock3_locale_resolver
diff -u progression/l1.py progression/l2.py     # what fallback chains cost
diff -u progression/l2.py progression/l3.py     # what the cache cost — the interesting one
diff -u progression/l3.py progression/l4.py     # what merge and diff cost
```

Each snapshot passes every test up to and including its own level, and no later ones exist for it to fail:

```bash
ICF_IMPL=progression.l1 python3 -m pytest -q -m "level1"                      # 13 passed
ICF_IMPL=progression.l2 python3 -m pytest -q -m "level1 or level2"            # 30 passed
ICF_IMPL=progression.l3 python3 -m pytest -q -m "level1 or level2 or level3"  # 48 passed
ICF_IMPL=progression.l4 python3 -m pytest -q                                  # 65 passed
```

The discipline these files were written under is worth stating, because it is what makes them useful rather than decorative: each snapshot contains only what that level's own statement pays for. `l1.py` has no fallback machinery, no default-locale consultation, no cache, no statistics and no bulk operations — not because they are hard, but because at Level 1 nobody has said they will ever be needed, and a snapshot that quietly pre-builds them would be a lie about how the exam actually goes. Grepping `l1.py` for `cache`, `chain`, `fallback` and `merge` returns nothing at all; the word `default` appears three times, twice as the constructor parameter the problem's global rules force on Level 1 and once inside `dict.setdefault`. The single genuine exception to the discipline is argued for below, and it is the whole thesis.

---

## Level 1 → Level 2: chains, and the reason the Level-1 methods never moved

Level 2 says production asks for `"fr-CA"` while most copy exists only in `"fr"` and some only in the default locale. Concretely that means a mutable default, a chain built by dropping trailing hyphen-segments and then appending the default verbatim (never generalized, never duplicated, nothing after it), a `resolve` that returns the first value along that chain, a `resolve_with_source` that also names the locale that supplied it, and two coverage reports computed over *direct* definitions only.

What changed is almost entirely addition. Of the five methods Level 1 shipped, all five — `_lookup`, `set_string`, `get_string`, `delete_string`, `list_keys` — are byte-for-byte identical in `l2.py`. `__init__` differs only in its docstring; its two statements are unchanged, and the docstring had to change because the default locale stops being inert and starts terminating every chain. Everything else in the diff is new: `_chain`, `_resolve_entry`, and the six public Level-2 methods.

The reason nothing had to move is the decision made at Level 1. `l1.py` reads `self._data` from exactly one place — `_lookup(locale, key)`, which returns `(value, found)` rather than a bare value, because a Level-1 requirement already says `""` is a real stored value and must be distinguishable from absent. That is defensible as ordinary craft with no knowledge of Level 2: one read primitive instead of the same two-line `self._data.get(locale, {})` idiom copy-pasted into `get_string` and `delete_string`. But it also turns out to be exactly the primitive a chain walk is built from, because a chain walk is nothing but a sequence of exact-match lookups. So `_resolve_entry` calls `_lookup` once per candidate locale and adds no new way of touching storage.

The new code has a shape that matters more than its size. There is exactly one function in the class that walks a chain, `_resolve_entry`, and it returns everything any caller could conceivably want: the value, the locale that supplied it, and the tuple of locales it consulted. `resolve` is `return self._resolve_entry(locale, key)[0]`. `resolve_with_source` unpacks the triple and formats two of its three fields. Neither contains a loop. The natural alternative — write the loop in `resolve`, then write a slightly different loop in `resolve_with_source` that also tracks the winning candidate — passes every Level-2 test just as well, and is measured against this one in the next section.

Two smaller things Level 2 settles. `missing_keys` joins with `", "` for the same reason `list_keys` already did, because the global rules say a collection-valued read returns one formatted string; `resolve_with_source` is *not* such a read, and its `"|"` separates the two fields of a single record rather than two entries of a list. And one thing in `l2.py` is genuinely speculative and should be admitted rather than smuggled: the third element of the returned triple, the chain, has no reader at Level 2. It is kept because it is free — the walk computed it in order to walk it — and because a function that reports what it consulted is a better-behaved function than one that reports only its answer. That instinct is what Level 3 turns out to charge for.

---

## Level 2 → Level 3: what the cache actually cost

This is the transition the problem is built around, so it deserves the numbers first. Adding a bounded LRU cache with chain-correct invalidation added **72 lines and changed 2**, and it changed the body of **four** public methods: `__init__`, `set_string`, `delete_string` and `set_default_locale`. It changed the body of one private method, `_resolve_entry`. It did **not** touch `resolve`, `resolve_with_source`, `get_string`, `list_keys`, `coverage`, `missing_keys`, `_chain` or `_lookup` — nine methods in total are byte-identical between `l2.py` and `l3.py`.

Look at which four public methods changed and the pattern is obvious: they are the constructor and the three methods that *mutate*. `__init__` gained seven lines of cache state. `set_string` and `delete_string` gained one line each, a call to `self._invalidate(locale, key)` — in `delete_string`'s case placed after the early `return False`, because a delete that removed nothing must leave the cache alone. `set_default_locale` gained three lines: an equality guard so that setting the default to its current value is a genuine no-op, and a flush, because changing the default rewrites every chain in the map at once. Not one *read* method changed. That is the entire claim being demonstrated.

The mechanical trick is small and worth naming, and the measurement catches it unusually cleanly. `_resolve_entry` kept its name and became the LRU wrapper — twelve lines including its `def` and docstring: check the cache, count a hit and refresh recency, or count a miss, compute, and store. The chain-walking body it used to contain moved down into `_resolve_uncached`, and it moved *verbatim*. That is why the whole-file "changed" count for this transition is **2** rather than something in the teens: the only two replaced lines in the entire file are the class docstring and the single `def` line where `_resolve_entry` became `_resolve_uncached`. Twelve lines of chain walk register as unchanged because they genuinely are unchanged. Because the name at the call sites did not move either, the two public read methods did not have to be reopened at all.

### The counterfactual, measured

To make the comparison real rather than rhetorical, the inlined design was actually written and actually run. A Level-2 variant in which the chain construction and the walk are duplicated inside `resolve` and `resolve_with_source` with no chokepoint, and a Level-3 variant built on top of it, both pass their levels' tests — 30 and 48 respectively, the same counts the chokepoint snapshots post — so this is a fair fight between two correct implementations, not a strawman.

| Transition | code lines | added | removed | changed | public methods with changed body | private methods with changed body |
| --- | --- | --- | --- | --- | --- | --- |
| L1 → L2 | 45 → 95 | 55 | 0 | 8 | 1 (`__init__`, docstring only) | 0 |
| **L2 → L3** | **95 → 167** | **72** | **0** | **2** | **4** (`__init__`, `set_string`, `delete_string`, `set_default_locale`) | **1** (`_resolve_entry`) |
| L3 → L4 | 167 → 213 | 46 | 0 | 1 | 0 | 0 |
| *counterfactual* L2 → L3, chain walk inlined | 83 → 172 | 81 | 0 | 13 | **6** | 0 |

Line counts exclude each file's module docstring, which is narrative apparatus rather than implementation, and exclude blank lines; method and class docstrings and inline comments are counted, since they are part of the code a reader maintains. "Changed" counts lines inside `difflib` replace hunks, sized by the larger side. The `changed` column is a whole-file measurement and is therefore low wherever a block was moved rather than rewritten, which is exactly the property being measured.

The second table is the sharper one. It asks, for each method that already existed at Level 2, how many lines Level 3 had to add to it or rewrite inside it.

| Pre-existing method | chokepoint design | inlined design |
| --- | --- | --- |
| `__init__` | +7 | +7 |
| `set_string` | +1 | +1 |
| `delete_string` | +1 | +1 |
| `set_default_locale` | +3 | +3 |
| `_resolve_entry` | 11 lines replaced (body extracted verbatim, wrapper installed in its place) | — (does not exist) |
| `resolve` | **untouched** | +8 added, 5 replaced |
| `resolve_with_source` | **untouched** | +11 added, 7 replaced |

The bookkeeping cost is identical in both worlds — the same seven lines of cache state, the same invalidation calls on the two writers, the same flush on `set_default_locale`, and the same **43 lines** of cache machinery in `_store`, `_unindex`, `_invalidate`, `_drop_all_entries`, `configure_cache` and `cache_stats`, which the script confirms are byte-identical across the two designs. What differs is that the inlined design must also reopen the two hot read methods and grow cache-lookup, miss-counting, chain-collection and store logic inside each of them, separately, in code that has to agree with itself on every detail. `resolve` and `resolve_with_source` together are **9 lines at Level 2 and still 9 lines at Level 3** in the chokepoint design. In the inlined design they are **22 lines at Level 2 and 49 at Level 3** — more than doubling, in the two functions that were already the most intricate in the file, at the point in a timed exam where the remaining budget is smallest.

Two honest caveats about these numbers, because they do not support a story quite as tidy as "the chokepoint is free". First, at the end of Level 2 the chokepoint design is the *larger* file: 95 lines against the inlined variant's 83, a twelve-line premium paid for `_chain` and `_resolve_entry` existing as named functions at all. A candidate who stopped at Level 2 would have written more code for no measured benefit. The crossover happens inside Level 3 and it is narrow — 167 lines against 172, five lines of net advantage. If the argument for the chokepoint rested on total line count it would be a weak argument. Second, the +72 versus +81 gap is likewise modest. The case is not really about volume; it is about *where* the volume lands, which is what the fourth and sixth columns of the first table measure and the second table measures in detail. Six pre-existing method bodies reopened versus five, but crucially two of the six are the ones that had to be got exactly right.

And the duplication is not benign. Every invariant the cache has must now hold in two places: exactly one of `hits` or `misses` increments per call; a hit refreshes recency; both methods must produce and store the *same* entry so that a `resolve` miss can serve a later `resolve_with_source` hit from the same slot; a negative result must be stored, not skipped; and the entry must carry the chain, not just the source. In the chokepoint design those five facts live in one twelve-line wrapper that no public method can see. In the inlined design there are two copies of each, and a test like `test_resolve_with_source_shares_the_same_cache_entry` fails if they drift by one line. That is the real cost, and it is a defect-probability cost rather than a line-count one — which is why the line counts undersell it.

### The invalidation key, which is where the points really are

The subtler half of Level 3 is not the LRU; it is deciding what a cached entry *depends on*. The instinct is to index each entry by the locale that produced its value, and that is wrong. If `("fr-CA", "cta.save")` resolved from `"en"`, the entry still depends on `"fr"`: the moment `"fr"` defines that key it shadows `"en"`, and the cached answer becomes stale even though nothing was written to `"en"` at all. The specification states the rule directly — a write to `(loc, k)` invalidates every entry `(L, k)` whose *chain contains* `loc` — and `test_set_on_parent_locale_invalidates_child_resolution` exists precisely to catch the source-locale version.

So `l3.py` registers each entry in a reverse index under `(loc, key)` for **every** `loc` on the chain it walked, which makes invalidation an `O(affected)` dict pop rather than an `O(cache)` scan, and makes it scoped correctly in both directions: writing `("de", "cta.save")` touches nothing on `"fr-CA"`'s chain, and writing `("fr", "other.key")` touches nothing for `"cta.save"`. Negative results need no special handling at all — a lookup that found nothing walked the entire chain, so its chain is the full chain, and a write anywhere on it invalidates the entry, which is exactly what `test_negative_results_are_cached_and_invalidated` demands.

This is only possible because `_resolve_entry` was already returning the chain at Level 2 with no caller to read it. That is the one piece of speculation in `l2.py` and it is the one that pays: without it, Level 3 would have to either recompute the chain at insertion time or scan the whole cache on every write.

---

## Level 3 → Level 4: the transition that does not force anything

Level 4 asks for bulk vendor deliveries — `merge_bundle` with three conflict strategies and an added/updated/skipped report — and `diff_locales` for content managers. It added 46 lines and changed exactly one pre-existing line, the class docstring. **All twenty-one methods in `l3.py` are byte-for-byte identical in `l4.py`.** The two new public methods and one module-level tuple of legal strategy names are the whole diff.

It is worth being honest about why, because it is not a triumph of design: this problem's Level 4 simply does not demand anything the storage model cannot already answer. Merge is a loop of writes with a policy in front of it; diff is a set union over two buckets. Both sit on top of the plain `dict[str, dict[str, str]]` that has been there since Level 1, and neither needs history, ordering, or any information that was thrown away earlier. A different Level 4 could have been much crueller, and in the other mocks in this kit it is.

What Level 4 *does* force is remembering that a bulk write is still a write. `merge_bundle` must invalidate exactly the keys it added or updated and must leave alone the entries for keys it skipped, since by definition nothing about those changed. That is one `self._invalidate(locale, key)` call on each of the two branches that actually store something, and it is cheap only because Level 3 put invalidation behind a single private method with a stable signature; had invalidation been open-coded into `set_string`, Level 4 would be re-deriving the reverse-index logic here, in the last half hour of the exam. The related trap is that "skipped" is defined by the *stored value being unchanged*, not by the strategy having declined — an `"overwrite"` with a byte-identical value is a skip, and `test_fully_skipped_merge_leaves_cache_intact` checks that its cached resolutions survive.

Two smaller things the diff shows. `merge_bundle`'s presence check goes through `_lookup`, the Level-1 chokepoint, rather than testing the bucket directly; the point is that `""` is a real stored value, and a merge that decided presence by truthiness would classify an existing `""` as *added*, silently overwriting it in defiance of `keep_existing` and of `prefer_longer`'s tie rule. And `diff_locales` deliberately does *not* go through any resolution chokepoint. It is specified over direct entries, with no fallback and no default-locale involvement, so reading `self._data` is not laziness — routing it through `_resolve_entry` would be a bug that touched the cache and moved the counters, which `test_diff_locales_does_not_touch_the_cache` would catch. Its own trap survives the conversion to string returns intact: the sort happens before the join, so what a naive implementation compares is still the formatted records, `"|"` outranks every letter, and `"a"` against `"ab"` produces a genuinely different answer. Sort the key field, then format, then join.

---

## How this mock's shape differs from the rest of the kit

It is useful that the mocks do not all teach the same lesson, and this one is the odd one out at the top.

Elsewhere in the kit, Level 4 reaches backwards. The point-in-time and rollback mock needs to know what the store looked like at an arbitrary past timestamp, which is information a store that only keeps current values has already destroyed; the snapshot-and-audit mock likewise demands a record of every state-changing operation that the earlier levels had no reason to keep. In both, Level 4 changes the *storage model* underneath every method already written, and the lesson is about keeping an event log, or at least a representation you can snapshot and replay, before anything tells you that you will need one.

Mock 3 does not do that. Its Level 4 is additive to the point of being anticlimactic — 46 lines added, zero method bodies changed, twenty-one methods byte-identical — because merge and diff are functions of the current state and nothing else. The pressure in this problem is all in the *middle*, at Level 3, and it lands on two different things: whether reads go through one chokepoint, and whether the cache is keyed by what an entry depends on rather than by where its value came from. Those are the two mistakes that cost real points here, and neither of them is an event-log mistake. A candidate who came out of the point-in-time mock with "always keep a history" as their only takeaway would have learned nothing that helps on this one; the transferable habit is narrower and more general — *find the read primitive, name it, and let everything go through it* — and Mock 3 is the mock that isolates it. The Level 4 lesson it does carry is a quieter one, about the blast radius of a derived structure: once a cache exists, every new write path in the system inherits an obligation to invalidate it, and the only thing that keeps that obligation cheap is having put invalidation behind one named method the first time.

---

## A note on the inert `timestamp`

Every public method in all four snapshots takes `timestamp: int` as its first argument, and an AST sweep of the four files confirms that not one method body contains a reference to the name. That is not sloppiness in the snapshots; it is the specification. This problem has no time dimension at any level — nothing expires, nothing is versioned, no read targets a past instant, the LRU has no TTL and recency means order of use, and no merge strategy breaks a tie by time.

What that tells a candidate is narrow and worth stating exactly, because the wrong generalisation from it is expensive in both directions. It tells you that the presence of a `timestamp` parameter is not by itself evidence of a time requirement: the ICF framework puts it on every signature for uniformity, and a candidate who spends five minutes of a ninety-minute exam hunting for the hidden temporal trick here has spent five minutes on nothing. It does **not** tell you that timestamps are decorative in general. In other problems in this kit the parameter is load-bearing at Level 4 and the entire storage model turns on having recorded it. The habit worth carrying is therefore not "ignore the timestamp" and not "always store the timestamp", but "read the level statement for whether anything is asked *as of* a moment, and let that, not the signature, decide" — and, as a cheap hedge, to keep the current-state store in a shape that could be wrapped in a history without the reads having to change, which is the same chokepoint discipline arriving by a different road.

---

## The decision that paid for everything

The single choice at Level 1 that paid for all three later levels was refusing to read `self._data` from more than one place: `_lookup(locale, key)` returning `(value, found)`, with `get_string` and `delete_string` both going through it. At the time it saves nothing — it is arguably one line longer than inlining `self._data.get(locale, {})` twice, and the Level-2 measurement above shows the habit still running a twelve-line deficit an hour into the exam. But it establishes that a read has a name, and every subsequent level is an application of that habit rather than a rediscovery of it: Level 2's chain walk is built out of `_lookup` and becomes a second, higher chokepoint, `_resolve_entry`; Level 3 slides a cache inside that chokepoint, reopens only the constructor and the three mutators, and touches no read method at all; Level 4's merge reuses `_lookup` for its presence check and gets `""`-correctness for free. The nine byte-identical methods across `l2.py` and `l3.py`, the two-line whole-file change count for the transition the problem is built around, and the twenty-one byte-identical methods across `l3.py` and `l4.py` are all downstream of a decision made in the first ten minutes that looked, at the time, like nothing.
