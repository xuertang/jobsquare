"""ICF Mock 3 -- LocaleResolver. Fill in every method; do not change the signatures.

HOW TO USE THIS FILE
--------------------
This skeleton contains **Level 1 only**. That is deliberate: the exam is timed
level by level, and seeing the later levels early would give away the design.

When you finish a level, go back to `PROBLEM.md` and read the next one. Each
level lists its own method signatures -- copy them into your class yourself and
implement them there. Nothing is pre-stubbed for you beyond Level 1, exactly as
in the real CodeSignal editor, where the next level's methods only appear once
you have submitted the current one.

Copy this file to `attempt.py` and run one level at a time:

    ICF_IMPL=attempt python3 -m pytest -q -m level1
"""

from __future__ import annotations

from typing import Optional


class LocaleResolver:
    """A store of localized strings, keyed by locale and then by key."""

    def __init__(self, default_locale: str = "en") -> None:
        """Create an empty resolver with `default_locale` as its default locale."""
        raise NotImplementedError

    def set_string(self, timestamp: int, locale: str, key: str, value: str) -> None:
        """Store `value` under `key` for `locale`, overwriting any prior value."""
        raise NotImplementedError

    def get_string(self, timestamp: int, locale: str, key: str) -> Optional[str]:
        """Return the value stored directly on `locale`, else None."""
        raise NotImplementedError

    def delete_string(self, timestamp: int, locale: str, key: str) -> bool:
        """Delete a direct entry; True if something was removed, else False."""
        raise NotImplementedError

    def list_keys(self, timestamp: int, locale: str) -> str:
        """Return `locale`'s own keys, sorted ascending and joined with ", "."""
        raise NotImplementedError
