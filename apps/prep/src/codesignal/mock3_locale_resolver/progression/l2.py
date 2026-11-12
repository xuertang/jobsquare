"""Mock 3 -- LocaleResolver, as it stood at the END OF LEVEL 2.

Snapshot, not a subclass. `diff -u l1.py l2.py` is the record of what fallback
chains actually cost.

WHAT LEVEL 2 ASKED FOR
    Requests arrive for "fr-CA" but most copy exists only in "fr", and some only
    in the default locale. So: a mutable default locale, a chain built by
    dropping trailing hyphen-segments and then appending the default verbatim,
    `resolve` (first value along the chain), `resolve_with_source` (the same
    plus the locale that supplied it), and two direct-coverage reports.

WHAT ACTUALLY CHANGED
    `_lookup` from Level 1 is untouched, and so are `set_string`, `get_string`,
    `delete_string` and `list_keys` -- a chain is a sequence of exact-match
    lookups, so the Level-1 primitive is what the chain walk is built out of.
    `__init__` keeps both of its statements; only its docstring changes, because
    the default locale stops being inert and starts terminating every chain.

    The new code is one chokepoint, `_resolve_entry`. It is the only code in the
    class that walks a chain, and it hands back everything a caller could want:
    the value, the locale that supplied it, and the chain it walked. `resolve`
    and `resolve_with_source` are one-liners over it and contain no traversal
    logic of their own. The alternative -- a loop in `resolve` and a second,
    subtly different loop in `resolve_with_source` -- passes exactly the same
    tests today and is the expensive choice tomorrow.

    Honest note: the third element of the returned triple, the chain, has no
    caller at this level. It is the one speculative thing in this file. It is
    free -- the walk already computed it -- and returning it costs one word in
    a tuple, so it stays.

    `missing_keys` joins with ", " for the same reason `list_keys` does: the
    global rules say a collection-valued read returns one formatted string.
    Note that `resolve_with_source` is *not* such a read -- it returns a single
    record whose own two fields are separated by "|". Two different separators
    doing two different jobs, and this file has one of each.

ON THE `timestamp` ARGUMENT
    Still first, still unread, still nothing to do with any chain. Level 2 adds
    a fallback dimension, not a time dimension.
"""

from __future__ import annotations

from typing import Optional

# What one resolution knows: (value, source_locale, chain_walked).
_Entry = tuple[Optional[str], Optional[str], tuple[str, ...]]


class LocaleResolver:
    """A store of localized strings with fallback-chain resolution."""

    def __init__(self, default_locale: str = "en") -> None:
        """Create an empty resolver terminating every chain at `default_locale`."""
        self._data: dict[str, dict[str, str]] = {}
        self._default_locale: str = default_locale

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

    def _resolve_entry(self, locale: str, key: str) -> _Entry:
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

    # ======================================================================
    # Level 1 -- direct storage
    # ======================================================================

    def set_string(self, timestamp: int, locale: str, key: str, value: str) -> None:
        """Store `value` under `key` for `locale`, overwriting any prior value."""
        self._data.setdefault(locale, {})[key] = value

    def get_string(self, timestamp: int, locale: str, key: str) -> Optional[str]:
        """Return the value stored directly on `locale`, else None."""
        return self._lookup(locale, key)[0]

    def delete_string(self, timestamp: int, locale: str, key: str) -> bool:
        """Delete a direct entry; True if something was removed, else False."""
        _, found = self._lookup(locale, key)
        if not found:
            return False
        del self._data[locale][key]
        return True

    def list_keys(self, timestamp: int, locale: str) -> str:
        """Return `locale`'s own keys, sorted ascending and joined with ", "."""
        return ", ".join(sorted(self._data.get(locale, {})))

    # ======================================================================
    # Level 2 -- fallback chains and coverage
    # ======================================================================

    def set_default_locale(self, timestamp: int, locale: str) -> None:
        """Set the locale that terminates every fallback chain."""
        self._default_locale = locale

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
