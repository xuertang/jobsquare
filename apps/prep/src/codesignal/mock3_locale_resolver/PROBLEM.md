# Mock 3 — `LocaleResolver`

**Industry Coding Framework practice exam · 90 minutes · 4 progressive levels · 600 points**
**Language:** Python 3.11
*Theme: Airbnb Content Platform — marketing copy served in many locales with fallback chains.*

---

## How to take this exam

1. Set a **90-minute timer** and do not stop it. Budget: **L1 10 min · L2 20 min · L3 30 min · L4 30 min.**
2. `cp starter.py attempt.py` and work only in `attempt.py`. **`starter.py` contains the Level 1 methods only.** Every later level lists its own method signatures in this document; when you reach a level, copy its signatures into your class and implement them there. That is how the real CodeSignal editor behaves — the next level's methods appear only once you have submitted the current one.
3. **Reveal one level at a time.** Read Level *N*, implement it, run its tests, and only then scroll to Level *N+1*. Reading ahead defeats the purpose — the whole point of ICF is that you do not know what is coming, so you must write code that is cheap to extend.
4. Run the tests for the level you just finished:
   ```bash
   ICF_IMPL=attempt python3 -m pytest -q -m level1     # then -m level2, -m level3, -m level4
   ```
5. **Backward compatibility is graded.** After Level 4, `ICF_IMPL=attempt python3 -m pytest -q` (all levels) must be green. A Level-3 or Level-4 change that breaks a Level-1 test costs you that level's points.
6. Do not read `solution.py` until the timer is done. There is a consolidated **[Spec decisions](#spec-decisions)** section at the bottom of this document; it spans all four levels, so consult only the entry for the level you are currently on.

---

## Global conventions (apply to every level)

- One class, `LocaleResolver`, constructed as `LocaleResolver(default_locale: str = "en")`. The constructor takes **no** timestamp.
- **Every method takes `timestamp: int` as its first argument.** Timestamps arrive non-decreasing. **They are semantically unused** — this problem has no time dimension at all: nothing expires, nothing is versioned, and no read targets a past instant. The parameter exists only so the signatures stay consistent with the ICF framework. Accept it and ignore it. (Yes, really; do not go looking for the trick.)
- **Every method that returns a collection returns one formatted string, not a list.** Entries are joined with **`", "` — a comma and a space** — with no trailing separator, no brackets and no quoting. An empty result is the **empty string `""`**. This applies to `list_keys`, `missing_keys` and `diff_locales`. Scalar reads are unaffected: a missing value is still `None`, and mutators still return `bool`.
- **Locale identifiers** are hyphen-separated tags: `"en"`, `"fr-CA"`, `"zh-Hant-TW"`. Treat them as opaque strings — no BCP-47 parsing beyond splitting on `-`. Comparison is case-sensitive.
- **Keys** are arbitrary non-empty strings (e.g. `"cta.book"`). **Values** are arbitrary strings — **including the empty string `""`, which is a legitimate stored value and must be distinguishable from "absent"**. Any implementation that tests values for truthiness is wrong.
- Locales are created implicitly on first write. A locale with zero keys and a locale that has never been mentioned are **indistinguishable** — every method must behave identically for both.
- No method ever raises for an unknown locale or key, except where explicitly stated (`merge_bundle` on a bad strategy, `configure_cache` on a negative capacity).
- All sorting is plain ascending Python string sort (`sorted()`), which is case-sensitive and puts uppercase before lowercase.

---

# Level 1 — Direct storage (10 minutes · 100 points)

Store and retrieve strings per locale. **Exact match only — no fallback at this level.**

### Signatures

```python
set_string(timestamp: int, locale: str, key: str, value: str) -> None
get_string(timestamp: int, locale: str, key: str) -> Optional[str]
delete_string(timestamp: int, locale: str, key: str) -> bool
list_keys(timestamp: int, locale: str) -> str
```

### Contracts

| Method | Returns |
| --- | --- |
| `set_string` | `None`. Creates the locale if needed. Overwrites silently. |
| `get_string` | The value stored **directly** on `locale`, or `None` if that locale does not define that key. Never consults any other locale. |
| `delete_string` | `True` if an entry existed and was removed; `False` if the locale or key was absent. Deleting is idempotent — the second call returns `False`. |
| `list_keys` | The keys defined directly on `locale`, **sorted ascending**, joined with `", "`. `""` for an unknown or empty locale. |

### Edge cases

- `get_string` on an unknown locale → `None` (not an error).
- `delete_string` on an unknown locale → `False`.
- Deleting the last key of a locale leaves an empty locale, which is equivalent to a nonexistent one.
- `set_string(t, loc, k, "")` stores an empty string; `get_string` must then return `""`, not `None`.
- `list_keys` of a locale with exactly one key has **no separator at all** — just the key. `list_keys` of an empty locale is `""`, not `"[]"` and not `" "`.
- The `timestamp` argument is accepted and ignored. Calling `set_string` with a timestamp of `10**12` and reading it back with `-100` gives the same answer.

### Worked example

```python
r = LocaleResolver()                          # default locale is "en"
r.set_string(1, "en", "cta.book", "Book now")
r.set_string(2, "en", "cta.save", "Save")

r.get_string(3, "en", "cta.book")             # -> "Book now"
r.get_string(4, "en", "cta.ghost")            # -> None
r.get_string(5, "fr", "cta.book")             # -> None   (no fallback at Level 1)
r.list_keys(6, "en")                          # -> "cta.book, cta.save"
r.list_keys(7, "fr")                          # -> ""

r.delete_string(8, "en", "cta.save")          # -> True
r.delete_string(9, "en", "cta.save")          # -> False
r.list_keys(10, "en")                         # -> "cta.book"
```

---

# Level 2 — Fallback chains and coverage (20 minutes · 150 points)

Production traffic asks for `"fr-CA"`, but most copy is only translated into `"fr"`, and some only exists in the default locale. Add chain resolution.

### Signatures

```python
set_default_locale(timestamp: int, locale: str) -> None
get_default_locale(timestamp: int) -> str
resolve(timestamp: int, locale: str, key: str) -> Optional[str]
resolve_with_source(timestamp: int, locale: str, key: str) -> Optional[str]
coverage(timestamp: int, locale: str) -> int
missing_keys(timestamp: int, locale: str) -> str
```

### The fallback chain — read this twice

The chain for a requested locale `L`, given current default `D`, is built as follows:

1. Start with `L` itself.
2. Append each **generalization** of `L`, produced by dropping one trailing hyphen-segment at a time, until one segment remains.
   `"zh-Hant-TW"` → `"zh-Hant"` → `"zh"`.
   `"fr-CA"` → `"fr"`.
   `"fr"` (already bare) → no generalizations at all.
3. Append `D` **only if `D` is not already somewhere in the chain**.

So, with default `"en"`:

| Requested | Chain |
| --- | --- |
| `"fr-CA"` | `fr-CA` → `fr` → `en` |
| `"fr"` | `fr` → `en` |
| `"en"` | `en` |
| `"zh-Hant-TW"` | `zh-Hant-TW` → `zh-Hant` → `zh` → `en` |

Three rules people get wrong:

- **The default locale is appended verbatim; it is NOT generalized.** If the default is `"en-US"`, the chain for `"fr-CA"` is `fr-CA` → `fr` → `en-US`. Bare `"en"` is **never** consulted, even if it exists.
- **If the default already appears on the chain, it is not duplicated and nothing follows it.** With default `"fr"`, the chain for `"fr-CA"` is `fr-CA` → `fr`, full stop — `"en"` is irrelevant.
- **The chain only generalizes, never specializes.** `resolve(t, "fr", k)` never looks at `"fr-CA"`.

`resolve` walks the chain in order and returns the value from the **first locale that defines the key** (defining it as `""` counts as defining it). If no locale on the chain defines it, return `None`.

### Contracts

| Method | Returns |
| --- | --- |
| `set_default_locale` | `None`. The locale need not exist yet. Affects all subsequent chains. |
| `get_default_locale` | The current default locale string. |
| `resolve` | First value along the chain, else `None`. |
| `resolve_with_source` | `f"{value}\|{source_locale}"` — the value, a single pipe `\|`, and the locale that actually supplied it. `None` (not a string) if the key resolves nowhere. Note that a value of `""` yields e.g. `"\|fr"`, and a value containing a pipe is not escaped. |
| `coverage` | Integer percentage, **floored**: `100 * |keys(default) ∩ keys(locale)| // |keys(default)|`. Uses **direct** definitions only — fallback does not count as coverage. |
| `missing_keys` | Keys defined on the default locale but **not directly** on `locale`, sorted ascending and joined with `", "`. `""` when nothing is missing. |

Note the asymmetry between the two string-returning methods here: `resolve_with_source` returns **one** record and uses `"|"` *inside* it; `missing_keys` returns a **list** of records and uses `", "` *between* them. The two separators are unrelated and both appear in this exam.

### Edge cases

- **If the default locale has zero keys, `coverage` is `100`** for every locale (vacuously complete), and `missing_keys` is `""`.
- `coverage(t, default_locale)` is always `100`; `missing_keys(t, default_locale)` is always `""`.
- `coverage` of a locale with zero keys is `0` (unless the default is also empty → `100`).
- Keys a locale defines that the default does *not* define are ignored by `coverage` — it can never exceed 100.

### Worked example A — resolution

```python
r = LocaleResolver()                                    # default "en"
r.set_string(1, "en", "cta.book", "Book now")
r.set_string(2, "en", "cta.save", "Save")
r.set_string(3, "fr", "cta.book", "Reserver")
r.set_string(4, "fr-CA", "hero.title", "Bienvenue au Canada")

r.resolve(5, "fr-CA", "hero.title")                     # -> "Bienvenue au Canada"
r.resolve(6, "fr-CA", "cta.book")                       # -> "Reserver"  (from "fr")
r.resolve(7, "fr-CA", "cta.save")                       # -> "Save"      (from "en")
r.resolve(8, "fr-CA", "cta.ghost")                      # -> None        (nowhere on the chain)
r.resolve(9, "fr", "hero.title")                        # -> None        (never specializes)

r.resolve_with_source(10, "fr-CA", "cta.save")          # -> "Save|en"
r.resolve_with_source(11, "fr", "cta.book")             # -> "Reserver|fr"
r.resolve_with_source(12, "de", "cta.ghost")            # -> None
```

### Worked example B — coverage

```python
# continuing from example A:
# keys(en)    = {cta.book, cta.save}
# keys(fr)    = {cta.book}
# keys(fr-CA) = {hero.title}

r.coverage(13, "fr")              # -> 50    (1 of 2)
r.coverage(14, "fr-CA")           # -> 0     (hero.title is not an "en" key)
r.coverage(15, "en")              # -> 100
r.coverage(16, "ja")              # -> 0
r.missing_keys(17, "fr")          # -> "cta.save"
r.missing_keys(18, "fr-CA")       # -> "cta.book, cta.save"
r.missing_keys(19, "en")          # -> ""
```

### Worked example C — changing the default

```python
r.set_default_locale(20, "fr")
r.get_default_locale(21)                        # -> "fr"
r.resolve_with_source(22, "de", "cta.book")     # -> "Reserver|fr"   (chain: de -> fr)
r.resolve(23, "de", "cta.save")                 # -> None   ("fr" has no cta.save; "en" is no longer on any chain)
r.coverage(24, "en")                            # -> 100    (en defines fr's only key, cta.book)
```

---

# Level 3 — Bounded LRU resolution cache (30 minutes · 150 points)

Chain walks are hot-path work. Add a bounded LRU cache in front of resolution — and keep it **correct** under mutation, which is the real exercise.

### Signatures

```python
configure_cache(timestamp: int, capacity: int) -> None
cache_stats(timestamp: int) -> str
```

### Contracts

- **Cache key** is the pair `(requested_locale, key)` exactly as passed to `resolve` — *not* the locale that supplied the value, and **not** the timestamp. `resolve(t, "fr-CA", k)` and `resolve(t, "fr", k)` are two separate entries even when both return the same string from `"en"`; two calls that differ only in their timestamp are the **same** entry.
- **`resolve` and `resolve_with_source` share one cache.** A cached entry holds both the value and its source locale, so either method can be served from it, and either method's call counts as a hit or a miss.
- **Every** call to `resolve`/`resolve_with_source` increments exactly one of `hits` or `misses`.
- On a miss, the resolution is computed and inserted as **most-recently-used**; if the cache now exceeds capacity, evict the **least-recently-used** entry (one per insertion).
- **A hit refreshes recency** — the entry becomes most-recently-used.
- **Negative results are cached.** A key that resolves nowhere stores a `None` entry that occupies a slot and can be hit and evicted like any other.
- `configure_cache(t, capacity)`: sets the capacity, **drops all entries, and resets `hits` and `misses` to 0**. `capacity == 0` disables caching entirely: every resolve is a miss, `size` stays 0, nothing is ever stored. Negative capacity raises `ValueError`.
- **Before `configure_cache` is ever called, capacity is 0** (caching disabled), so a fresh resolver reports `"hits=0,misses=0,size=0"` and Levels 1–2 behave exactly as before.
- `cache_stats(t)` returns `f"hits={h},misses={m},size={s}"` where `size` is the number of entries currently held. This is a **single record** and uses `","` with no space — it is not a list of entries, so the `", "` list convention does not apply to it.

### Invalidation — be precise, this is where the points are

An entry cached under `(L, k)` was produced by walking a **chain of locales**. That whole chain is what the entry depends on — not just the locale that happened to supply the value.

> **Rule:** a write to `(loc, k)` invalidates every cached entry `(L, k)` whose chain **contains `loc`**.

Consequences you must implement:

- `resolve(t, "fr-CA", "cta.save")` returns a value from `"en"`. Chain touched: `fr-CA`, `fr`, `en`. Now `set_string(t, "fr", "cta.save", ...)` **must invalidate that entry**, because `"fr"` now shadows `"en"`. Indexing entries by their *source* locale is the classic bug here.
- Invalidation is **scoped to the key**. Writing `("fr", "other.key")` never touches entries for `"cta.save"`.
- Invalidation is **scoped to the chain**. Writing `("de", "cta.save")` never touches `("fr-CA", "cta.save")`, since `"de"` is not on that chain.
- **Negative entries depend on the entire chain** (all of it was searched and came up empty), so a write anywhere on it invalidates them.
- Invalidated entries are **removed**, so `size` decreases. `hits`/`misses` are unaffected by invalidation.

Which operations invalidate:

| Operation | Effect on the cache |
| --- | --- |
| `set_string(t, loc, k, v)` | Invalidates `(·, k)` entries whose chain contains `loc` — **always, even if the value is unchanged.** |
| `delete_string(t, loc, k)` | Same, but **only when it returns `True`**. A `False` delete changed nothing and must leave the cache untouched. |
| `set_default_locale(t, new)` | Every chain changes, so **all entries are dropped**. `hits`/`misses` are **preserved** (only `configure_cache` resets them). Setting the default to its current value is a no-op. |
| `merge_bundle` (Level 4) | Invalidates exactly the keys it added or updated — see Level 4. |
| `configure_cache(t, n)` | Drops all entries **and** resets both counters. |

### Edge cases

- `capacity == 0`: `resolve` still returns correct values; every call is a miss; `size` is always 0.
- `capacity == 1`: each new distinct lookup evicts the previous one.
- Invalidating a key that was already evicted is a harmless no-op — it must not corrupt `size` or crash.
- `coverage`, `missing_keys`, `get_string`, `list_keys` and `diff_locales` **do not touch the cache** and never change `hits`/`misses`/`size`.
- Nothing about the cache is time-based. There is no TTL, no expiry and no eviction by age-in-timestamps — recency here means *order of use*, not the value of any `timestamp` argument.

### Worked example A — hit, miss, invalidate

```python
r = LocaleResolver()
r.set_string(1, "en", "cta.book", "Book now")
r.set_string(2, "fr", "cta.book", "Reserver")
r.configure_cache(3, 2)

r.resolve(4, "fr-CA", "cta.book")     # -> "Reserver"   (miss)
r.cache_stats(5)                      # -> "hits=0,misses=1,size=1"
r.resolve(6, "fr-CA", "cta.book")     # -> "Reserver"   (hit)
r.cache_stats(7)                      # -> "hits=1,misses=1,size=1"

r.set_string(8, "fr", "cta.book", "Reserve maintenant")   # invalidates the entry
r.cache_stats(9)                      # -> "hits=1,misses=1,size=0"
r.resolve(10, "fr-CA", "cta.book")    # -> "Reserve maintenant"  (miss)
r.cache_stats(11)                     # -> "hits=1,misses=2,size=1"
```

### Worked example B — chain invalidation (the one that catches people)

```python
r = LocaleResolver()
r.set_string(1, "en", "cta.save", "Save")
r.configure_cache(2, 4)

r.resolve_with_source(3, "fr-CA", "cta.save")   # -> "Save|en"   (chain: fr-CA, fr, en)
r.cache_stats(4)                                # -> "hits=0,misses=1,size=1"

r.set_string(5, "fr", "cta.save", "Enregistrer")   # "fr" is ON the chain -> invalidate
r.cache_stats(6)                                   # -> "hits=0,misses=1,size=0"
r.resolve_with_source(7, "fr-CA", "cta.save")      # -> "Enregistrer|fr"
```

### Worked example C — exact LRU order

```python
r = LocaleResolver()
r.set_string(1, "en", "cta.book", "Book now")
r.configure_cache(2, 2)

r.resolve(3, "fr", "cta.book")    # miss   cache (LRU→MRU): [fr]
r.resolve(4, "de", "cta.book")    # miss   cache: [fr, de]
r.resolve(5, "fr", "cta.book")    # HIT    cache: [de, fr]     <- hit refreshes recency
r.resolve(6, "es", "cta.book")    # miss   evicts "de"; cache: [fr, es]
r.cache_stats(7)                  # -> "hits=1,misses=3,size=2"
r.resolve(8, "de", "cta.book")    # miss   (it was evicted)
r.cache_stats(9)                  # -> "hits=1,misses=4,size=2"
```

---

# Level 4 — Bulk merges and diffs (30 minutes · 200 points)

Translation vendors deliver whole bundles at once, and content managers need to see what changed.

### Signatures

```python
merge_bundle(timestamp: int, locale: str, mapping: dict[str, str], strategy: str) -> str
diff_locales(timestamp: int, locale_a: str, locale_b: str) -> str
```

## `merge_bundle`

Bulk-applies `mapping` (key → value) to `locale`, creating the locale if it does not exist. `strategy` is one of `"overwrite"`, `"keep_existing"`, `"prefer_longer"`; anything else raises `ValueError`.

For each key, determine the **winning value**:

- **Key not currently present in `locale`** → the incoming value always wins, regardless of strategy. Counts as **added**.
- **Key already present**:
  - `"overwrite"` → incoming wins.
  - `"keep_existing"` → existing wins.
  - `"prefer_longer"` → the value with the greater `len()` wins; **on a tie the existing value wins.** (Length is character count; no trimming or normalization.)

Then classify by outcome, **based on whether the stored value actually changed**:

| Outcome | Condition |
| --- | --- |
| **added** | The key did not exist in `locale` before. |
| **updated** | The key existed and the winning value **differs** from the existing one. |
| **skipped** | The key existed and the stored value is **unchanged** — because the strategy kept the existing value, *or* because the incoming value was byte-identical to it. |

> Note the consequence: `merge_bundle(t, loc, {"a": "x"}, "overwrite")` where `loc["a"]` is already `"x"` reports **skipped**, not updated. "Updated" means the data changed.

**Returns** `f"added={a},updated={u},skipped={s}"` — one record, `","` with no space, exactly like `cache_stats`. The three counts always sum to `len(mapping)`.

**Cache interaction:** invalidate exactly the keys that were **added or updated**, using the Level-3 chain rule. Keys counted as *skipped* changed nothing, so their cached entries must survive intact.

### Edge cases

- Empty `mapping` → `"added=0,updated=0,skipped=0"`, and nothing else changes: no keys are written, the cache and its stats are untouched, and `list_keys(t, locale)` is still `""`. You do **not** need to special-case an empty mapping to avoid "creating" the locale — a locale with zero keys is indistinguishable from a nonexistent one (global conventions), so creating an empty bucket is invisible through every method on the class.
- Merging into a locale that does not exist → every key is *added*.
- An incoming value of `""` is a real value: merging `{"k": ""}` with `"overwrite"` over `"hello"` is an **update** to the empty string.
- Under `"prefer_longer"`, `""` never beats a non-empty existing value, and an existing `""` loses to any non-empty incoming value.
- Validate the strategy **before** applying anything — a `ValueError` must leave the store untouched.
- The `timestamp` plays no part in any strategy. "Prefer newer" is not one of the three strategies, and no tie is ever broken by time.

### Worked example

```python
r = LocaleResolver()
r.set_string(1, "fr", "a", "aaaa")
r.set_string(2, "fr", "b", "bb")

r.merge_bundle(3, "fr", {"a": "zz", "b": "bbbb", "c": "new"}, "prefer_longer")
# a: len("zz")=2 < len("aaaa")=4  -> existing kept -> skipped
# b: len("bbbb")=4 > len("bb")=2  -> updated
# c: not present                  -> added
# -> "added=1,updated=1,skipped=1"

r.merge_bundle(4, "fr", {"a": "aaaa", "d": "d"}, "overwrite")
# a: identical value -> skipped ; d: added
# -> "added=1,updated=0,skipped=1"

r.merge_bundle(5, "it", {}, "keep_existing")     # -> "added=0,updated=0,skipped=0"
r.merge_bundle(6, "it", {"x": "1"}, "newest")    # raises ValueError
```

## `diff_locales`

Compares the **direct** entries of two locales (no fallback, no default locale involvement) and returns the difference records as a **single string**, joined with `", "`.

For every key in the union of `keys(locale_a)` and `keys(locale_b)`:

| Situation | Record |
| --- | --- |
| Present in A only | `f"{key}\|only_in_a\|{value_a}"` |
| Present in B only | `f"{key}\|only_in_b\|{value_b}"` |
| Present in both, values differ | `f"{key}\|differs\|{value_a}\|{value_b}"` (A's value first) |
| Present in both, values equal | **omitted entirely** |

The `"|"` inside a record and the `", "` between records are two different separators doing two different jobs. Do not mix them up: `", ".join` goes on the outside, once, at the end.

**Sort order: by key, ascending — NOT by the formatted record string.** These differ, and the change from a list return to a joined string does not rescue you, because the sort happens **before** the join: what a naive implementation compares is still the record strings themselves. With keys `"a"` and `"ab"`, sorting the records compares `"a|only_in_a|1"` against `"ab|only_in_a|2"`; they first differ at index 1, and since `"|"` (0x7C) sorts *after* `"b"` (0x62), a naive `sorted(records)` puts `"ab"` first. The correct answer is `"a|only_in_a|1, ab|only_in_a|2"`; the naive one is `"ab|only_in_a|2, a|only_in_a|1"`. Sort the key field, then format, then join. Keys are unique across the three categories, so sorting by key is a total order.

### Edge cases

- `diff_locales(t, x, x)` → `""` for any `x` (every key is present in both with equal values).
- Either or both locales unknown/empty → the other side's keys are all reported as `only_in_a` / `only_in_b`; two unknown locales → `""`.
- `""` vs `"x"` is a difference: `"note|differs||x"` (note the empty field between the pipes).
- A single difference produces a record with **no** `", "` in it anywhere.
- `diff_locales` never touches the cache or the stats.

### Worked example

```python
r = LocaleResolver()
r.merge_bundle(1, "en", {"greeting": "Hello", "cta": "Book", "en_only": "X"}, "overwrite")
r.merge_bundle(2, "fr", {"greeting": "Bonjour", "cta": "Book", "fr_only": "Y"}, "overwrite")

r.diff_locales(3, "en", "fr")
# -> "en_only|only_in_a|X, fr_only|only_in_b|Y, greeting|differs|Hello|Bonjour"
# "cta" is identical in both, so it is omitted.

r.diff_locales(4, "en", "en")     # -> ""
r.diff_locales(5, "ja", "ko")     # -> ""
```

---

<a id="spec-decisions"></a>
## Spec decisions

These are the corners a terse problem statement would leave ambiguous. This exam pins them down; every one is enforced by at least one test. The level column tells you when it becomes relevant.

| # | L | Decision |
|---|---|---|
| 1 | all | **`timestamp` is the first argument of every method and is semantically unused** — at every level, including Level 4. Nothing expires, nothing is versioned, no read targets a past instant, the LRU cache has no TTL, and no merge strategy breaks a tie by time. Timestamps arrive non-decreasing; the parameter exists only to keep the signatures consistent with the ICF framework. There is no hidden time trick. The constructor is the one exception: `LocaleResolver(default_locale="en")` takes no timestamp. |
| 2 | all | **Collections come back as one `", "`-joined string.** `list_keys`, `missing_keys` and `diff_locales` return a `str`, never a `list`: entries sorted, formatted, then joined with a comma **and** a space, no trailing separator, no brackets, no quoting. An empty result is `""` — not `"[]"`, not `" "`. Scalar reads keep returning `None` when absent and mutators keep returning `bool`; the string convention applies only to the collection-valued reads. |
| 3 | all | **`", "` is a list separator; `"\|"` and `","` are entry-internal.** `resolve_with_source` (`"Save\|en"`), `cache_stats` (`"hits=3,misses=5,size=2"`) and `merge_bundle` (`"added=2,updated=1,skipped=3"`) each return **one** record whose own fields are separated by `"\|"` or by a bare `","`. Those formats are unchanged and unrelated to the `", "` used *between* entries of a collection. Both styles appear in this exam on purpose. |
| 4 | 1 | **`""` is a real value.** `set_string(t, loc, k, "")` stores an empty string and `get_string` must then return `""`, not `None`. Any truthiness test on a value is a bug, and it is tested at every level (`resolve`, `resolve_with_source`, `merge_bundle`, `diff_locales`). |
| 5 | 1 | **An empty locale is a nonexistent locale.** Deleting a locale's last key leaves it indistinguishable from one that was never mentioned; `list_keys` is `""` and `delete_string` is `False` for both. Implementations may keep an empty bucket around — it must simply be invisible through the public API. |
| 6 | 2 | **The default locale is appended verbatim and is never generalized.** With default `"en-US"`, the chain for `"fr-CA"` is `fr-CA` → `fr` → `en-US`; bare `"en"` is never consulted even if it exists. |
| 7 | 2 | **The default is never duplicated on a chain, and nothing follows it.** With default `"fr"`, the chain for `"fr-CA"` is exactly `fr-CA` → `fr`. |
| 8 | 2 | **Chains only generalize.** `resolve(t, "fr", k)` never consults `"fr-CA"`. There is no downward search and no sibling search. |
| 9 | 2 | **`coverage` is floored integer division over *direct* definitions.** Fallback never counts toward coverage; extra keys the default does not define are ignored, so the result can never exceed 100. An **empty default locale gives `100`** for every locale, and `missing_keys` is `""`. |
| 10 | 3 | **The cache key is `(requested_locale, key)`** — the locale as *requested*, not the one that supplied the value, and never the timestamp. Two calls differing only in timestamp hit the same entry. |
| 11 | 3 | **Invalidation is keyed by the whole chain the entry walked**, not by the source locale. A write to any locale on that chain, for that key, drops the entry — including for negative entries, whose chain is the full chain. This is where the Level 3 points are. |
| 12 | 3 | **Caching is off until `configure_cache` is called.** A fresh resolver has capacity 0, so every resolve is a miss, `size` stays 0, and `cache_stats` reads `"hits=0,misses=0,size=0"`. `capacity == 0` explicitly disables caching; a negative capacity raises `ValueError`. |
| 13 | 3 | **`configure_cache` resets the counters; `set_default_locale` does not.** Both drop every entry, but only `configure_cache` zeroes `hits` and `misses`. Setting the default to its current value is a complete no-op and must leave the cache intact. |
| 14 | 4 | **"Updated" means the stored bytes changed.** An `"overwrite"` merge of a byte-identical value is **skipped**, not updated — and being skipped, it must not invalidate that key's cached entries. |
| 15 | 4 | **`prefer_longer` ties go to the existing value**, compared by `len()` with no trimming or normalization. |
| 16 | 4 | **The strategy is validated before anything is written.** An unknown strategy raises `ValueError` and leaves the store byte-for-byte unchanged, even when every key in the mapping would have been a fresh add. |
| 17 | 4 | **`diff_locales` sorts by key, then formats, then joins.** Sorting the rendered records is a genuinely different order, not a hypothetical one: records first differ where the key ends, and `"\|"` (0x7C) sorts above every ASCII letter and digit, so whenever one key is a proper prefix of another the two orders disagree — `"a"` vs `"ab"` is the canonical pair. Joining afterwards does not change this, because the sort has already happened. |

---

## Scoring

| Level | Points | Target time |
| --- | --- | --- |
| 1 — Direct storage | 100 | 10 min |
| 2 — Fallback chains and coverage | 150 | 20 min |
| 3 — Bounded LRU resolution cache | 150 | 30 min |
| 4 — Bulk merges and diffs | 200 | 30 min |
| **Total** | **600** | **90 min** |

Passing bar for a senior offer is roughly **all of L1–L3 plus a working L4**, with every earlier level still green.

## After the timer

Read the module docstring in `solution.py` before you read its code. The single idea it is built around — funnel every read through one private chain-walking chokepoint from Level 1 onward — is what turns Level 3 from a rewrite into a five-line wrapper. If you inlined the chain walk into both `resolve` and `resolve_with_source` at Level 2, note how much of Level 3 you spent paying that back.
