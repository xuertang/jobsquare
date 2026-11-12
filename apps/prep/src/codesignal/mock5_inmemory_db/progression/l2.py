"""Level 2 snapshot -- whole-record and prefix-filtered scans added to Level 1.

Level 2 asked for two readers, `scan` and `scan_by_prefix`, and said nothing at
all about storage. Nothing about storage changed: `_Field`, `self._db`, `_write`
and `_field` are byte for byte what they were at Level 1, and not one of the
three existing public methods was touched. The whole diff is additive.

Two judgement calls, both of them the same call twice:

1. `scan` and `scan_by_prefix` are not two implementations. `scan` *is*
   `scan_by_prefix` with the empty prefix -- the spec says so outright ("every
   field name starts with the empty string") -- so it is one line of delegation
   rather than a second sorted walk to keep in step with the first.

2. Both funnel through one private helper, `_items`, which answers "which
   fields of this record are in scope for a query, in order?". The two public
   methods differ only in the prefix they pass; they do not differ at all in
   what counts as being in scope. Inlining the walk into each would work
   identically today and would double every later edit, because any future
   refinement of "in scope" lands on precisely that question.

Note what `_items` does *not* do. It does not read `record.items()` for values;
it walks the field names and asks `_field` about each one. That is a deliberate
one-line choice: it means the scans inherit whatever `_field` decides readable
means, rather than owning a second opinion about it. `_format` is factored out
for the same reason -- the wire format `field(value)` is shared, so it gets one
definition, and the empty selection renders as `""` by construction rather than
by a special case.
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

    def _items(
        self, timestamp: int, key: str, prefix: str = ""
    ) -> list[tuple[str, _Field]]:
        """Readable `(field, entry)` pairs of `key` matching `prefix`, sorted.

        The single chokepoint for record-wide reads, and the sibling of
        `_field`. It asks `_field` about each candidate name rather than reading
        the dict itself, so it inherits readability for free instead of forming
        a second opinion about it. Sorting is plain lexicographic on the field
        name, per the spec: `f1`, `f10`, `f2`.
        """
        record = self._db.get(key)
        if not record:
            return []
        matches = []
        for name in record:
            if not name.startswith(prefix):
                continue
            entry = self._field(timestamp, key, name)
            if entry is not None:
                matches.append((name, entry))
        matches.sort(key=lambda item: item[0])
        return matches

    @staticmethod
    def _format(items: list[tuple[str, _Field]]) -> str:
        """Render pairs as `f1(v1), f2(v2)`; the empty selection renders as ``."""
        return ", ".join(f"{name}({entry.value})" for name, entry in items)

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

    # ------------------------------------------------------------------
    # Level 2 -- scan and aggregation
    # ------------------------------------------------------------------

    def scan(self, timestamp: int, key: str) -> str:
        """Every field of `key`, field-ascending, as `f1(v1), f2(v2)`."""
        return self.scan_by_prefix(timestamp, key, "")

    def scan_by_prefix(self, timestamp: int, key: str, prefix: str) -> str:
        """Fields of `key` whose name starts with `prefix`, field-ascending."""
        return self._format(self._items(timestamp, key, prefix))
