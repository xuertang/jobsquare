"""Reference solution for Mock 3: LocaleResolver (Airbnb Content Platform theme).

A note before the lesson, so nobody wastes time hunting for a trick: every
public method takes `timestamp: int` as its first argument and **not one of them
reads it**. There is no time dimension in this problem -- nothing expires, is
versioned, or is read as-of a past instant. The parameter is there because the
ICF framework puts it there. Accept it and ignore it.

KEY DESIGN DECISION -- the one that makes Levels 3 and 4 nearly free:

    Route every read through a single private chokepoint from Level 1 onward.

There are exactly two read primitives in this problem: a *direct* lookup
(`self._data[locale].get(key)`) and a *chain walk* over the fallback locales.
Level 1 only needs the first; the temptation is to inline the chain walk into
`resolve` at Level 2 and inline it again into `resolve_with_source`. Do that and
Level 3 forces you to rewrite two methods and Level 4 forces you to reason about
cache invalidation in a third place. Instead, `_resolve_uncached` is the ONLY
code that walks a chain, and it returns everything any caller could want:
`(value, source_locale, chain)`. `resolve` and `resolve_with_source` become
one-liners over `_lookup`, and `_lookup` is a five-line LRU decorator added at
Level 3 without touching a single Level-2 method.

The second insight is about *invalidation keys*. A naive cache indexes entries
by the locale that produced the value -- which is wrong. If `("fr-CA", "book")`
resolved from `"en"`, writing `fr/book` still changes the answer, because "fr"
sits on the chain between them. So `_resolve_uncached` returns the whole chain
it *touched*, and every entry is registered in a reverse index under
`(chain_locale, key)` for every locale on that chain. Invalidation is then an
O(affected) dict pop instead of an O(cache) scan, and negative ("nowhere")
results invalidate correctly too, because their chain is the full chain.

Everything else -- coverage, diffs, merge strategies -- is bookkeeping over
`self._data`, deliberately kept as a plain dict-of-dicts so that no level ever
needs a data-model migration. Note that every method returning a *collection*
returns one `", "`-joined string rather than a list, so each of them ends in the
same three characters: sort the underlying data, format, `", ".join`. Sorting
the formatted records instead of the data is a real bug and `diff_locales` is
where it bites.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Optional

# A cached entry: (value, source_locale, chain_touched)
_Entry = tuple[Optional[str], Optional[str], tuple[str, ...]]

_STRATEGIES = ("overwrite", "keep_existing", "prefer_longer")


class LocaleResolver:
    """Localized string store with fallback chains, an LRU cache and bulk merges."""

    def __init__(self, default_locale: str = "en") -> None:
        self._data: dict[str, dict[str, str]] = {}
        self._default: str = default_locale
        # --- Level 3 cache state -------------------------------------------
        self._capacity: int = 0
        self._cache: "OrderedDict[tuple[str, str], _Entry]" = OrderedDict()
        # reverse index: (chain_locale, key) -> set of cache keys touching it
        self._index: dict[tuple[str, str], set[tuple[str, str]]] = {}
        self._hits: int = 0
        self._misses: int = 0

    # ======================================================================
    # Level 1 -- direct storage
    # ======================================================================

    def set_string(self, timestamp: int, locale: str, key: str, value: str) -> None:
        """Store `value` under `key` for `locale`, overwriting any prior value."""
        self._data.setdefault(locale, {})[key] = value
        self._invalidate(locale, key)

    def get_string(self, timestamp: int, locale: str, key: str) -> Optional[str]:
        """Return the value stored directly on `locale` (no fallback), else None."""
        return self._data.get(locale, {}).get(key)

    def delete_string(self, timestamp: int, locale: str, key: str) -> bool:
        """Delete a direct entry; True if something was removed, else False."""
        bucket = self._data.get(locale)
        if bucket is None or key not in bucket:
            return False
        del bucket[key]
        self._invalidate(locale, key)
        return True

    def list_keys(self, timestamp: int, locale: str) -> str:
        """Return `locale`'s own keys, sorted ascending and joined with ", "."""
        return ", ".join(sorted(self._data.get(locale, {})))

    # ======================================================================
    # Level 2 -- fallback chains, coverage
    # ======================================================================

    def set_default_locale(self, timestamp: int, locale: str) -> None:
        """Set the locale that terminates every fallback chain."""
        if locale == self._default:
            return
        self._default = locale
        self._clear_cache_entries()  # every chain changed; stats are preserved

    def get_default_locale(self, timestamp: int) -> str:
        """Return the current default locale."""
        return self._default

    def _chain(self, locale: str) -> tuple[str, ...]:
        """Fallback chain: generalizations of `locale`, then the default locale."""
        parts = locale.split("-")
        chain = ["-".join(parts[:i]) for i in range(len(parts), 0, -1)]
        if self._default not in chain:
            chain.append(self._default)
        return tuple(chain)

    def _resolve_uncached(self, locale: str, key: str) -> _Entry:
        """THE chokepoint: walk the chain once, report value, source and chain."""
        chain = self._chain(locale)
        for candidate in chain:
            bucket = self._data.get(candidate)
            if bucket is not None and key in bucket:
                return bucket[key], candidate, chain
        return None, None, chain

    def _lookup(self, locale: str, key: str) -> _Entry:
        """Level-3 LRU wrapper around the chokepoint. Everything reads through here."""
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

    def resolve(self, timestamp: int, locale: str, key: str) -> Optional[str]:
        """Return the first value found along the fallback chain, else None."""
        return self._lookup(locale, key)[0]

    def resolve_with_source(self, timestamp: int, locale: str, key: str) -> Optional[str]:
        """Return "<value>|<source_locale>" for a resolved key, else None."""
        value, source, _ = self._lookup(locale, key)
        if source is None:
            return None
        return f"{value}|{source}"

    def coverage(self, timestamp: int, locale: str) -> int:
        """Floored percentage of the default locale's keys defined directly on `locale`."""
        base = self._data.get(self._default, {})
        if not base:
            return 100
        mine = self._data.get(locale, {})
        hit = sum(1 for k in base if k in mine)
        return hit * 100 // len(base)

    def missing_keys(self, timestamp: int, locale: str) -> str:
        """Default-locale keys `locale` lacks, sorted ascending and joined with ", "."""
        base = self._data.get(self._default, {})
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
        self._clear_cache_entries()
        self._hits = 0
        self._misses = 0

    def cache_stats(self, timestamp: int) -> str:
        """Return "hits=<h>,misses=<m>,size=<s>"."""
        return f"hits={self._hits},misses={self._misses},size={len(self._cache)}"

    # --- cache internals ---------------------------------------------------

    def _store(self, ck: tuple[str, str], entry: _Entry) -> None:
        """Insert an entry as most-recently-used, evicting LRU past capacity."""
        self._cache[ck] = entry
        self._cache.move_to_end(ck)
        _, _, chain = entry
        key = ck[1]
        for loc in chain:
            self._index.setdefault((loc, key), set()).add(ck)
        while len(self._cache) > self._capacity:
            victim, victim_entry = self._cache.popitem(last=False)
            self._unindex(victim, victim_entry)

    def _unindex(self, ck: tuple[str, str], entry: _Entry) -> None:
        """Remove a cache key from every reverse-index bucket it registered under."""
        _, _, chain = entry
        key = ck[1]
        for loc in chain:
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

    def _clear_cache_entries(self) -> None:
        """Drop all cached entries; leave capacity and hit/miss counters alone."""
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
        for key in sorted(mapping):
            incoming = mapping[key]
            if key not in bucket:
                bucket[key] = incoming
                self._invalidate(locale, key)
                added += 1
                continue
            existing = bucket[key]
            if strategy == "keep_existing":
                winner = existing
            elif strategy == "overwrite":
                winner = incoming
            else:  # prefer_longer -- ties go to the existing value
                winner = incoming if len(incoming) > len(existing) else existing
            if winner == existing:
                skipped += 1
            else:
                bucket[key] = winner
                self._invalidate(locale, key)
                updated += 1
        return f"added={added},updated={updated},skipped={skipped}"

    def diff_locales(self, timestamp: int, locale_a: str, locale_b: str) -> str:
        """Per-key difference records between two locales, by key, joined with ", "."""
        a = self._data.get(locale_a, {})
        b = self._data.get(locale_b, {})
        out: list[tuple[str, str]] = []
        for key in a.keys() | b.keys():
            in_a, in_b = key in a, key in b
            if in_a and not in_b:
                out.append((key, f"{key}|only_in_a|{a[key]}"))
            elif in_b and not in_a:
                out.append((key, f"{key}|only_in_b|{b[key]}"))
            elif a[key] != b[key]:
                out.append((key, f"{key}|differs|{a[key]}|{b[key]}"))
        out.sort(key=lambda pair: pair[0])  # by KEY, before formatting
        return ", ".join(record for _, record in out)
