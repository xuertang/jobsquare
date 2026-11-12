"""Mock 3 -- LocaleResolver, as it stood at the END OF LEVEL 4 (final).

Snapshot, not a subclass. `diff -u l3.py l4.py` is unusually boring, and that is
the finding: Level 4 here is pure addition.

WHAT LEVEL 4 ASKED FOR
    Vendors deliver whole bundles at once, so: `merge_bundle` with three conflict
    strategies and an added/updated/skipped report, plus `diff_locales` for
    content managers to see what two locales disagree about.

WHAT ACTUALLY CHANGED
    Two new public methods, one module-level tuple of legal strategy names, and
    nothing else. No existing method body was touched -- not the storage layout,
    not the chokepoints, not the cache. That is worth saying plainly because it
    is not what the other mocks do at this level: their Level 4 demands history
    nobody recorded, which forces the storage model to change underneath
    everything already written. Here `self._data` stays the plain dict-of-dicts
    it was at Level 1, and merge and diff are bookkeeping over it.

    The one thing Level 4 does force is remembering that a bulk write is still a
    write: `merge_bundle` must invalidate exactly the keys it added or updated
    and leave the entries for skipped keys intact, since nothing about them
    changed. That is one `self._invalidate(locale, key)` call on each of the two
    branches that actually store something -- cheap only because Level 3 built
    the reverse index and put invalidation behind a single private method. Note
    too that "skipped" is defined by the *stored value being unchanged*, not by
    the strategy having declined, so an "overwrite" with a byte-identical value
    is a skip and its cached resolutions must survive.

    `merge_bundle`'s presence check goes through `_lookup`, the Level-1
    chokepoint, rather than testing the bucket for truthiness: "" is a real
    stored value, and a merge that decided presence by truthiness would call an
    existing "" *added* and overwrite it in defiance of `keep_existing` and of
    `prefer_longer`'s tie rule.

    `diff_locales` reads `self._data` directly rather than going through a
    chokepoint, which is exactly right: it is specified over *direct* entries,
    with no fallback and no default-locale involvement, so it must not touch the
    cache or the counters. It sorts by *key* and only then formats and joins --
    sorting the rendered records is a different order, because "|" outranks
    every letter, and "a" vs "ab" is the pair that exposes it.

THE INVALIDATION KEY -- the difficulty this problem is really about
    An entry is not a function of the locale that supplied its value. It is a
    function of every locale that was *consulted* to produce it. `("fr-CA", k)`
    resolved from "en" still depends on "fr": the moment "fr" defines k, it
    shadows "en" and the cached answer is wrong. So each entry is registered in a
    reverse index under `(loc, key)` for every loc on its chain, and invalidation
    is a dict pop over the affected set rather than a scan of the whole cache.
    Negative entries fall out of this for free -- their chain is the entire
    chain, every locale of which was searched and found wanting.

    This is the whole reason `_resolve_entry` returned its chain at Level 2 with
    nobody to read it. That unused third tuple slot is the index key.

ON THE `timestamp` ARGUMENT
    Level 4 is the last chance for a time dimension to appear, and it does not.
    No strategy is "prefer newer", no tie is broken by time, and `merge_bundle`
    and `diff_locales` ignore their first argument exactly as every method
    before them does.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Optional

# What one resolution knows: (value, source_locale, chain_walked).
_Entry = tuple[Optional[str], Optional[str], tuple[str, ...]]

_STRATEGIES = ("overwrite", "keep_existing", "prefer_longer")


class LocaleResolver:
    """Localized string store with fallback chains, an LRU cache and bulk merges."""

    def __init__(self, default_locale: str = "en") -> None:
        """Create an empty resolver terminating every chain at `default_locale`."""
        self._data: dict[str, dict[str, str]] = {}
        self._default_locale: str = default_locale
        # --- cache state; capacity 0 means caching is off until configured ---
        self._capacity: int = 0
        self._cache: "OrderedDict[tuple[str, str], _Entry]" = OrderedDict()
        # reverse index: (chain_locale, key) -> cache keys whose chain touched it
        self._index: dict[tuple[str, str], set[tuple[str, str]]] = {}
        self._hits: int = 0
        self._misses: int = 0

    # ======================================================================
    # The read chokepoints
    # ======================================================================

    def _lookup(self, locale: str, key: str) -> tuple[Optional[str], bool]:
        """Read one entry directly off `locale`.

        Returns `(value, found)`. The boolean is load-bearing: `("", True)` and
        `(None, False)` are different answers and callers must be able to tell
        them apart.
        """
        bucket = self._data.get(locale)
        if bucket is not None and key in bucket:
            return bucket[key], True
        return None, False

    def _chain(self, locale: str) -> tuple[str, ...]:
        """Build the fallback chain: generalizations of `locale`, then the default.

        The default is appended verbatim and is never itself generalized, and it
        is not appended at all if it already sits on the chain -- in which case
        nothing follows it.
        """
        parts = locale.split("-")
        chain = ["-".join(parts[:i]) for i in range(len(parts), 0, -1)]
        if self._default_locale not in chain:
            chain.append(self._default_locale)
        return tuple(chain)

    def _resolve_uncached(self, locale: str, key: str) -> _Entry:
        """THE chain chokepoint: the only code here that walks a chain.

        Returns `(value, source_locale, chain)`. `source_locale` is None exactly
        when the key resolves nowhere, which is what distinguishes a stored ""
        from a miss. `chain` is every locale that was consulted.
        """
        chain = self._chain(locale)
        for candidate in chain:
            value, found = self._lookup(candidate, key)
            if found:
                return value, candidate, chain
        return None, None, chain

    def _resolve_entry(self, locale: str, key: str) -> _Entry:
        """LRU cache in front of the chain walk. Every resolution reads through here."""
        ck = (locale, key)
        if self._capacity > 0 and ck in self._cache:
            self._hits += 1
            self._cache.move_to_end(ck)
            return self._cache[ck]
        self._misses += 1
        entry = self._resolve_uncached(locale, key)
        if self._capacity > 0:
            self._store(ck, entry)
        return entry

    # ======================================================================
    # Level 1 -- direct storage
    # ======================================================================

    def set_string(self, timestamp: int, locale: str, key: str, value: str) -> None:
        """Store `value` under `key` for `locale`, overwriting any prior value."""
        self._data.setdefault(locale, {})[key] = value
        self._invalidate(locale, key)

    def get_string(self, timestamp: int, locale: str, key: str) -> Optional[str]:
        """Return the value stored directly on `locale`, else None."""
        return self._lookup(locale, key)[0]

    def delete_string(self, timestamp: int, locale: str, key: str) -> bool:
        """Delete a direct entry; True if something was removed, else False."""
        _, found = self._lookup(locale, key)
        if not found:
            return False
        del self._data[locale][key]
        self._invalidate(locale, key)
        return True

    def list_keys(self, timestamp: int, locale: str) -> str:
        """Return `locale`'s own keys, sorted ascending and joined with ", "."""
        return ", ".join(sorted(self._data.get(locale, {})))

    # ======================================================================
    # Level 2 -- fallback chains and coverage
    # ======================================================================

    def set_default_locale(self, timestamp: int, locale: str) -> None:
        """Set the locale that terminates every fallback chain."""
        if locale == self._default_locale:
            return
        self._default_locale = locale
        self._drop_all_entries()  # every chain changed; hit/miss counters survive

    def get_default_locale(self, timestamp: int) -> str:
        """Return the current default locale."""
        return self._default_locale

    def resolve(self, timestamp: int, locale: str, key: str) -> Optional[str]:
        """Return the first value found along the fallback chain, else None."""
        return self._resolve_entry(locale, key)[0]

    def resolve_with_source(self, timestamp: int, locale: str, key: str) -> Optional[str]:
        """Return "<value>|<source_locale>" for a resolved key, else None."""
        value, source, _ = self._resolve_entry(locale, key)
        if source is None:
            return None
        return f"{value}|{source}"

    def coverage(self, timestamp: int, locale: str) -> int:
        """Floored percentage of the default locale's keys defined directly on `locale`."""
        base = self._data.get(self._default_locale, {})
        if not base:
            return 100
        mine = self._data.get(locale, {})
        return sum(1 for k in base if k in mine) * 100 // len(base)

    def missing_keys(self, timestamp: int, locale: str) -> str:
        """Default-locale keys `locale` lacks, sorted ascending and joined with ", "."""
        base = self._data.get(self._default_locale, {})
        mine = self._data.get(locale, {})
        return ", ".join(sorted(k for k in base if k not in mine))

    # ======================================================================
    # Level 3 -- bounded LRU resolution cache
    # ======================================================================

    def configure_cache(self, timestamp: int, capacity: int) -> None:
        """Set cache capacity (0 disables), dropping all entries and resetting stats."""
        if capacity < 0:
            raise ValueError("capacity must be non-negative")
        self._capacity = capacity
        self._drop_all_entries()
        self._hits = 0
        self._misses = 0

    def cache_stats(self, timestamp: int) -> str:
        """Return "hits=<h>,misses=<m>,size=<s>"."""
        return f"hits={self._hits},misses={self._misses},size={len(self._cache)}"

    # --- cache internals ---------------------------------------------------

    def _store(self, ck: tuple[str, str], entry: _Entry) -> None:
        """Insert as most-recently-used, index it by its whole chain, evict LRU."""
        self._cache[ck] = entry
        self._cache.move_to_end(ck)
        key = ck[1]
        for loc in entry[2]:
            self._index.setdefault((loc, key), set()).add(ck)
        while len(self._cache) > self._capacity:
            victim, victim_entry = self._cache.popitem(last=False)
            self._unindex(victim, victim_entry)

    def _unindex(self, ck: tuple[str, str], entry: _Entry) -> None:
        """Remove a cache key from every reverse-index bucket it registered under."""
        key = ck[1]
        for loc in entry[2]:
            bucket = self._index.get((loc, key))
            if bucket is not None:
                bucket.discard(ck)
                if not bucket:
                    self._index.pop((loc, key), None)

    def _invalidate(self, locale: str, key: str) -> None:
        """Drop every cached resolution whose chain touched `locale` for `key`."""
        affected = self._index.pop((locale, key), None)
        if not affected:
            return
        for ck in list(affected):
            entry = self._cache.pop(ck, None)
            if entry is not None:
                self._unindex(ck, entry)

    def _drop_all_entries(self) -> None:
        """Drop every cached entry; leave capacity and the hit/miss counters alone."""
        self._cache.clear()
        self._index.clear()

    # ======================================================================
    # Level 4 -- bulk merge and diff
    # ======================================================================

    def merge_bundle(
        self, timestamp: int, locale: str, mapping: dict[str, str], strategy: str
    ) -> str:
        """Bulk-apply `mapping` under a strategy; return "added=a,updated=u,skipped=s"."""
        if strategy not in _STRATEGIES:
            raise ValueError(f"unknown strategy: {strategy}")
        bucket = self._data.setdefault(locale, {})
        added = updated = skipped = 0
        for key, incoming in mapping.items():
            existing, present = self._lookup(locale, key)
            if not present:
                bucket[key] = incoming
                self._invalidate(locale, key)
                added += 1
                continue
            if strategy == "keep_existing":
                winner = existing
            elif strategy == "overwrite":
                winner = incoming
            else:  # prefer_longer -- a tie leaves the existing value in place
                winner = incoming if len(incoming) > len(existing) else existing
            if winner == existing:
                skipped += 1  # nothing stored, so cached resolutions stay valid
            else:
                bucket[key] = winner
                self._invalidate(locale, key)
                updated += 1
        return f"added={added},updated={updated},skipped={skipped}"

    def diff_locales(self, timestamp: int, locale_a: str, locale_b: str) -> str:
        """Per-key difference records between two locales, by key, joined with ", "."""
        a = self._data.get(locale_a, {})
        b = self._data.get(locale_b, {})
        records: list[tuple[str, str]] = []
        for key in a.keys() | b.keys():
            if key not in b:
                records.append((key, f"{key}|only_in_a|{a[key]}"))
            elif key not in a:
                records.append((key, f"{key}|only_in_b|{b[key]}"))
            elif a[key] != b[key]:
                records.append((key, f"{key}|differs|{a[key]}|{b[key]}"))
        records.sort(key=lambda pair: pair[0])  # by key, NOT by formatted record
        return ", ".join(record for _, record in records)
