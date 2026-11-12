"""Mock 3 -- LocaleResolver, as it stood at the END OF LEVEL 3.

Snapshot, not a subclass. `diff -u l2.py l3.py` is the payoff diff of this whole
exercise: a bounded LRU cache with correct invalidation, added without rewriting
a single one of the six public methods Level 2 shipped.

WHAT LEVEL 3 ASKED FOR
    A bounded LRU cache in front of chain resolution, keyed by the *requested*
    locale and key, shared by `resolve` and `resolve_with_source`, counting a hit
    or a miss on every call, caching negative results, and -- the part the points
    are actually in -- staying correct under mutation.

WHAT ACTUALLY CHANGED
    `_resolve_entry` kept its name and became a ten-line LRU wrapper; the chain
    walk it used to contain moved verbatim into `_resolve_uncached`. Because the
    name at the call sites did not move, `resolve` and `resolve_with_source` are
    byte-for-byte what they were at Level 2. So are `get_string`, `list_keys`,
    `coverage` and `missing_keys`. The three methods that had to change are the
    three that *mutate*: `set_string` and `delete_string` each gained one call to
    `_invalidate`, and `set_default_locale` gained an is-this-a-no-op guard plus
    a cache flush, because changing the default rewrites every chain in the map.

THE INVALIDATION KEY -- the actual difficulty
    An entry is not a function of the locale that supplied its value. It is a
    function of every locale that was *consulted* to produce it. `("fr-CA", k)`
    resolved from "en" still depends on "fr": the moment "fr" defines k, it
    shadows "en" and the cached answer is wrong. So each entry is registered in a
    reverse index under `(loc, key)` for every loc on its chain, and invalidation
    is a dict pop over the affected set rather than a scan of the whole cache.
    Negative entries fall out of this for free -- their chain is the entire
    chain, every locale of which was searched and found wanting.

    This is the whole reason `_resolve_entry` returned its chain at Level 2 with
    nobody to read it. That unused third tuple slot is now the index key.

ON THE `timestamp` ARGUMENT
    Worth restating here, because "LRU cache" is where a candidate is most
    tempted to invent a time dimension. There is none. Recency means order of
    use, not the value of any `timestamp`; there is no TTL and no expiry; and
    two resolves differing only in their timestamp are the *same* cache entry,
    which is why `timestamp` is not part of the cache key.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Optional

# What one resolution knows: (value, source_locale, chain_walked).
_Entry = tuple[Optional[str], Optional[str], tuple[str, ...]]


class LocaleResolver:
    """A store of localized strings with fallback chains and a bounded LRU cache."""

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
