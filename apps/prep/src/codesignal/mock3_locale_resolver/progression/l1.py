"""Mock 3 -- LocaleResolver, as it stood at the END OF LEVEL 1.

This file is a snapshot, not a base class. It is complete and self-contained so
that `diff -u l1.py l2.py` shows exactly what Level 2 cost.

WHAT LEVEL 1 ASKED FOR
    A store of strings keyed by locale and then by key: set, get, delete, list.
    Exact match only -- a lookup never consults any locale other than the one it
    was handed. Values may be "", and "" must stay distinguishable from absent,
    so nothing here tests a value for truthiness. `list_keys` returns the keys
    as one `", "`-joined string, because the problem's global rules say every
    collection-valued read returns a formatted string rather than a list.

ON THE `timestamp` ARGUMENT
    Every public method takes `timestamp: int` first and not one of them reads
    it. That is the problem's global rule, not an oversight here: this exam has
    no time dimension at any level -- nothing expires, nothing is versioned, no
    read targets a past instant. The parameter is accepted and ignored.

THE ONE PIECE OF FORWARD-LOOKING CRAFT
    `_lookup` is the only place in the class that reads a value out of
    `self._data`. `get_string` and `delete_string` both go through it instead of
    poking the dict-of-dicts themselves. That is not a guess about Level 2 -- it
    is the ordinary discipline of having one read primitive rather than three
    copies of the same two-line idiom. It returns `(value, found)` because a
    bare value cannot distinguish a stored "" from a missing key, which is a
    Level-1 requirement, not a future one.

    Nothing else is here. Every other piece of machinery a finished
    LocaleResolver eventually grows is absent from this file, because nothing in
    the Level 1 statement pays for it and guessing at it now would mean writing
    code against a specification that has not been shown yet.
"""

from __future__ import annotations

from typing import Optional


class LocaleResolver:
    """A store of localized strings, keyed by locale and then by key."""

    def __init__(self, default_locale: str = "en") -> None:
        """Create an empty resolver.

        The constructor signature is fixed by the problem's global rules. At
        this level the configured locale is only recorded; no method consults
        it, because exact-match lookup never leaves the locale it was asked
        about.
        """
        self._data: dict[str, dict[str, str]] = {}
        self._default_locale: str = default_locale

    # ======================================================================
    # The read chokepoint
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
