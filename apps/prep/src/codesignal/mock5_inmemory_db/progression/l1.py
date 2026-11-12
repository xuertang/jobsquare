"""Level 1 snapshot -- set, get and delete over `key -> field -> value`.

This is what the class looked like at the ten-minute mark, before Level 2 had
been read. It knows about three operations on a two-level keyed store and it
knows about nothing else: no scanning, no formatting, no notion of a field
ceasing to be readable, no history. None of the later levels' vocabulary occurs
anywhere in this file, because at Level 1 nothing justifies any of it.

Two habits are already in place, and both are defensible as ordinary craft
rather than as guesses about what comes next:

1. The thing stored under a field name is a small `_Field` record, not a bare
   `str`. Today it holds exactly one attribute, which looks like ceremony. It
   is the cheap half of a bet that any programmer makes every time they name a
   type: that the stored thing is a *thing* with attributes, and that the set
   of attributes is more likely to grow than to shrink.

2. Every read of the store goes through one private accessor, `_field`. No
   public method looks in `self._db` on the read path. `get` and `delete` ask
   the same question -- "is there something readable at this key and field?" --
   so they ask it in the same place, and any future refinement of the word
   "readable" has exactly one home.

The accessor takes `timestamp` even though it does not use it. That is not
foresight about a later level; it is that a private helper answering a public
method's question should take the public method's arguments, and that Level 1's
own spec goes out of its way to say the timestamp is in every signature for a
reason. Passing along an argument you were handed costs nothing.

Neither habit requires knowing that Levels 2, 3 or 4 exist.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class _Field:
    """One stored field of one record: the value written under its name."""

    value: str


class InMemoryDB:
    """A record store mapping each `key` to a set of `field -> value` pairs."""

    def __init__(self) -> None:
        """Initialise an empty database."""
        # key -> field -> _Field. A record with no fields left is dropped, so
        # "the key exists" and "the key has a field" never disagree.
        self._db: dict[str, dict[str, _Field]] = {}

    # ------------------------------------------------------------------
    # Internal primitives -- every read in the class goes through these
    # ------------------------------------------------------------------

    def _write(self, key: str, field: str, value: str) -> None:
        """Create or overwrite `field` on `key`, creating the record if absent.

        The single write chokepoint, for the same reason `_field` is the single
        read chokepoint: `set` is not the only thing that will ever want to put
        a field into the store.
        """
        self._db.setdefault(key, {})[field] = _Field(value)

    def _field(self, timestamp: int, key: str, field: str) -> Optional[_Field]:
        """The field stored at `key`/`field` as seen at `timestamp`, else None.

        Single chokepoint for reads. No public method touches `self._db` to
        answer "is there something here?", so that question has exactly one
        answer and exactly one place to be refined. The two miss cases the spec
        insists are distinct -- no such key, and a key with no such field -- are
        distinguished here and collapse to `None` only at the boundary.
        """
        record = self._db.get(key)
        if record is None:
            return None
        return record.get(field)

    # ------------------------------------------------------------------
    # Level 1 -- core operations
    # ------------------------------------------------------------------

    def set(self, timestamp: int, key: str, field: str, value: str) -> None:
        """Set `field` on `key` to `value`, creating or overwriting it."""
        self._write(key, field, value)

    def get(self, timestamp: int, key: str, field: str) -> Optional[str]:
        """The value at `key`/`field`, or None if there is nothing there.

        `""` is a legal value and a hit; only the miss returns `None`.
        """
        entry = self._field(timestamp, key, field)
        return None if entry is None else entry.value

    def delete(self, timestamp: int, key: str, field: str) -> bool:
        """Remove `key`/`field`; True only if it was there to be removed."""
        if self._field(timestamp, key, field) is None:
            return False
        record = self._db[key]
        del record[field]
        if not record:
            del self._db[key]
        return True
