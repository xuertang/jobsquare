"""Level 4 snapshot -- backup and restore, which cost the model nothing.

Level 4 asks for point-in-time recovery: snapshot the database, later roll the
whole thing back to a snapshot, and count the records that had at least one live
field. Structurally this is the cheapest level in the problem. Nothing about the
storage model changes. `_Field`, `_write`, `_field`, `_items`, `_format` and all
six public methods from Levels 1 to 3 are byte-identical to `l3.py`; `__init__`
gains one line for the backup history, and two new public methods sit on top.

That is unusual, and it is worth being clear about *why* it is true here rather
than presenting it as a general law. It is true because a backup is a read and a
restore is a write, and this class already had exactly one way to do each. In
Mocks 1 and 2 the Level 4 requirement is "what did this look like before?", and
a store that keeps only current state has thrown that away by construction --
there the level forces a genuine conversion to an append-only log. Here the
requirement is "put this state somewhere and put it back later", and current
state is precisely what the store already has. Nothing has to be remembered that
was not already being kept.

WHERE THIS LEVEL IS ACTUALLY HARD -- REMAINING, NOT ABSOLUTE
-------------------------------------------------------------
The difficulty is semantic and it fits in one sentence: `restore` relocates the
origin of time, so a snapshot must store *durations*, not *instants*.

    set_with_ttl(10, "wallet_a", "balance", "100", 100)   # expires at 110
    backup(15)                                            # 95 units remain
    restore(1000, 15)
    get(1000, "wallet_a", "balance")

A snapshot of remaining lifespan puts the field back alive on `[1000, 1095)` and
that `get` returns `"100"`. A `copy.deepcopy` of the live state -- which is the
obvious implementation, and cheaper to write -- puts it back carrying
`expires_at = 110` while the clock reads `1000`, so the field is already dead
and the restore silently restored nothing. Every test that restores near the
backup timestamp passes either way; only a test that jumps the clock across the
restore can tell them apart.

So `backup` stores `expires_at - timestamp` and `restore` turns it back into
`timestamp + remaining`. Permanent fields are the degenerate case: `None`
remaining survives the round trip and stays permanent, with no branch of its
own beyond the one conditional expression on each side.

Two smaller decisions. `backup` reads through `_items` rather than walking the
dict, so "live enough to be snapshotted" is the same question `scan` asks, not a
fifth private answer to it -- the sort `_items` performs is wasted work here, and
that agreement is what it buys. And the backup history is a list ordered by
timestamp rather than a dict keyed by one, because the spec wants the *latest
backup at or before* an instant and wants two backups at the same timestamp to
resolve by call order; a list plus `bisect_right` gives both, and a dict gives
neither.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from typing import Optional

#: A snapshotted field: (value, remaining lifespan, or None for permanent).
_Snapshot = dict[str, dict[str, tuple[str, Optional[int]]]]


@dataclass(frozen=True)
class _Field:
    """One stored field: its value, plus the instant it stops being readable."""

    value: str
    expires_at: Optional[int] = None  # None means "never expires"

    def alive_at(self, when: int) -> bool:
        """The single liveness rule: alive for `t <= when < expires_at`."""
        return self.expires_at is None or when < self.expires_at


class InMemoryDB:
    """A record store mapping each `key` to a set of `field -> value` pairs."""

    def __init__(self) -> None:
        """Initialise an empty database with an empty backup history."""
        # key -> field -> _Field. A record with no fields left is dropped, so
        # "the key exists" and "the key has a field" never disagree.
        self._db: dict[str, dict[str, _Field]] = {}
        # Append-only and non-decreasing in timestamp: (timestamp, snapshot).
        self._backups: list[tuple[int, _Snapshot]] = []

    # ------------------------------------------------------------------
    # Internal primitives -- every read in the class goes through these
    # ------------------------------------------------------------------

    def _write(
        self, key: str, field: str, value: str, expires_at: Optional[int] = None
    ) -> None:
        """Create or overwrite `field` on `key`, replacing value and lifespan.

        The single write chokepoint. Both writers are this call with a different
        `expires_at`, so there is no such thing as inheriting or extending a
        previous lifespan -- a write replaces the whole record.
        """
        self._db.setdefault(key, {})[field] = _Field(value, expires_at)

    def _field(self, timestamp: int, key: str, field: str) -> Optional[_Field]:
        """The field at `key`/`field` if it is live at `timestamp`, else None.

        Single chokepoint for reads. Everything that can make a field
        unreadable -- no such key, no such field, expired -- is decided here and
        collapses to `None` at the boundary, so no public method owns a second
        opinion about what "readable" means.
        """
        record = self._db.get(key)
        if record is None:
            return None
        entry = record.get(field)
        if entry is None or not entry.alive_at(timestamp):
            return None
        return entry

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
        """Remove `key`/`field`; True only if it was live at `timestamp`."""
        record = self._db.get(key)
        if record is None or field not in record:
            return False
        was_live = record[field].alive_at(timestamp)
        # Purge unconditionally. An expired field answers False, but it is also
        # removed, so no later operation can observe or resurrect a stale entry.
        del record[field]
        if not record:
            del self._db[key]
        return was_live

    # ------------------------------------------------------------------
    # Level 2 -- scan and aggregation
    # ------------------------------------------------------------------

    def scan(self, timestamp: int, key: str) -> str:
        """Every field of `key`, field-ascending, as `f1(v1), f2(v2)`."""
        return self.scan_by_prefix(timestamp, key, "")

    def scan_by_prefix(self, timestamp: int, key: str, prefix: str) -> str:
        """Fields of `key` whose name starts with `prefix`, field-ascending."""
        return self._format(self._items(timestamp, key, prefix))

    # ------------------------------------------------------------------
    # Level 3 -- TTL
    # ------------------------------------------------------------------

    def set_with_ttl(
        self, timestamp: int, key: str, field: str, value: str, ttl: int
    ) -> None:
        """Set `key`/`field`, alive for `timestamp <= q < timestamp + ttl`."""
        self._write(key, field, value, expires_at=timestamp + ttl)

    # ------------------------------------------------------------------
    # Level 4 -- backup and restore
    # ------------------------------------------------------------------

    def backup(self, timestamp: int) -> int:
        """Snapshot live state with REMAINING lifespans; return the record count.

        Remaining rather than absolute: see the module docstring. A record with
        no live field is neither stored nor counted, and the count is of
        records, not fields.
        """
        snapshot: _Snapshot = {}
        for key in self._db:
            live = self._items(timestamp, key)
            if not live:  # every field expired: not stored, not counted
                continue
            snapshot[key] = {
                name: (
                    entry.value,
                    None if entry.expires_at is None else entry.expires_at - timestamp,
                )
                for name, entry in live
            }
        self._backups.append((timestamp, snapshot))
        return len(snapshot)

    def restore(self, timestamp: int, time_to_restore: int) -> None:
        """Replace all state with the latest backup at or before `time_to_restore`.

        A wholesale swap, not a merge: records created since are gone, records
        deleted since come back, values changed since revert. Restored lifespans
        resume from `timestamp`. With no eligible backup this is a no-op, and
        the backup history itself is never touched.
        """
        index = bisect.bisect_right(
            self._backups, time_to_restore, key=lambda entry: entry[0]
        )
        if index == 0:  # no backup at or before that instant
            return
        _, snapshot = self._backups[index - 1]
        self._db = {
            key: {
                name: _Field(
                    value,
                    None if remaining is None else timestamp + remaining,
                )
                for name, (value, remaining) in record.items()
            }
            for key, record in snapshot.items()
        }
