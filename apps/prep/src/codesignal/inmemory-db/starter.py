"""ICF Mock 5 -- InMemoryDB. Fill in every method; do not change the signatures.

HOW TO USE THIS FILE
--------------------
This skeleton contains **Level 1 only**. That is deliberate: the exam is timed
level by level, and seeing the later levels early would give away the design.

When you finish a level, go back to `PROBLEM.md` and read the next one. Each
level lists its own method signatures -- copy them into your class yourself and
implement them there. Nothing is pre-stubbed for you beyond Level 1, exactly as
in the real CodeSignal editor, where the next level's methods only appear once
you have submitted the current one.
"""

from __future__ import annotations

from typing import Optional


class InMemoryDB:
    """A record store mapping each `key` to a set of `field -> value` pairs."""

    def __init__(self) -> None:
        """Initialise an empty database."""
        raise NotImplementedError

    def set(self, timestamp: int, key: str, field: str, value: str) -> None:
        """Create or overwrite `field` on the record `key`."""
        raise NotImplementedError

    def get(self, timestamp: int, key: str, field: str) -> Optional[str]:
        """Read `field` from the record `key`, or None if there is no such value."""
        raise NotImplementedError

    def delete(self, timestamp: int, key: str, field: str) -> bool:
        """Remove `field` from the record `key`; False if it was not there."""
        raise NotImplementedError
