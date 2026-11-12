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
from dataclasses import dataclass


@dataclass
class _Field:

    value: str


class InMemoryDB:
    """A record store mapping each `key` to a set of `field -> value` pairs."""

    def __init__(self) -> None:
        """Initialise an empty database."""
        self._db: dict[str, dict[str, _Field]] = {}

    def _write(self, key, field, value):
        self._db.setdefault(key, {})[field] = _Field(value)

    def _field(self, timestamp, key: str, field: str) -> Optional[_Field]:
        record = self._db.get(key)
        if record is None:
            return None
        return record.get(field)

    def set(self, timestamp: int, key: str, field: str, value: str) -> None:
        """Create or overwrite `field` on the record `key`."""
        self._write(key, field, value)

    def get(self, timestamp: int, key: str, field: str) -> Optional[str]:
        """Read `field` from the record `key`, or None if there is no such value."""
        entry = self._field(timestamp, key, field)
        return None if entry is None else entry.value

    def delete(self, timestamp: int, key: str, field: str) -> bool:
        """Remove `field` from the record `key`; False if it was not there."""
        if self._field(timestamp, key, field) is None:
            return False
        record = self._db[key]
        del record[field]
        if not record:
            del self._db[key]
        return True
