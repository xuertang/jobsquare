"""ICF Mock 5 -- InMemoryDB, with Level 4 as point-in-time reads (`get_when`).

WHY THIS LEVEL IS A DATA-MODEL CHANGE, NOT A NEW METHOD
--------------------------------------------------------
Levels 1-3 store exactly one version of each field:

    dict[key][field] -> _Field(value, expires_at)

`set` overwrites it and `delete` erases it. That model answers "what is this
field now" and structurally *cannot* answer "what was it at `at_ts`" -- the
old value is not slow to find, it is gone. So `get_when` cannot be bolted on
as a fifth read against the same store; the store has to start remembering.

The change is to make each field an append-only log of versions:

    dict[key][field] -> [ _Version(written_at, value, expires_at), ... ]

`set` appends. `delete` appends a *tombstone* (`value is None`) instead of
erasing. Nothing is ever removed, so any past instant remains answerable.

THE UNIFYING MOVE -- every read is the same read
-------------------------------------------------
Once the log exists, `get` and `get_when` stop being two different operations:

    get(ts, k, f)            == _resolve(ts,    k, f)
    get_when(ts, k, f, at)   == _resolve(at,    k, f)

`get` is just `get_when` asked about the present. `scan`, `scan_by_prefix` and
`backup` route through the same `_resolve`, so there is exactly one place in
the class that knows how to turn (instant, key, field) into a value, and all
five readers inherit its rules for free.

`_resolve(when, key, field)` is three checks in order, and the order matters:

    1. the newest version with `written_at <= when`   -- else None (not yet written)
    2. that version is not a tombstone                -- else None (deleted by then)
    3. that version is alive at `when`                -- else None (TTL expired by then)

Check 1 is a `bisect_right` on a list that is sorted because timestamps arrive
non-decreasing -- the same property the exam guarantees in its preamble.

THE TRAP -- delete must stop purging
-------------------------------------
The Level 1-3 `delete` purges the field outright, and its docstring defends
this: "an expired field is removed too, so nothing can observe or resurrect it
later". Under `get_when` that comment describes a bug. History *is* the point;
a field deleted at t=60 must still read back at at_ts=30. Deleting therefore
appends a tombstone dated `timestamp` and leaves every earlier version intact.

WHAT `at_ts` IN THE FUTURE MEANS
---------------------------------
Nothing is ever written into the future, so for `at_ts >= timestamp` the log
has no versions the present does not already have, and `_resolve` naturally
returns the same answer `get` would. No clamping is required or performed.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from typing import Optional

#: A field's snapshotted form: (value, remaining lifespan or None for permanent).
_Snapshot = dict[str, dict[str, tuple[str, Optional[int]]]]


@dataclass(frozen=True)
class _Version:
    """One entry in a field's history. `value is None` marks a deletion."""

    written_at: int
    value: Optional[str]
    expires_at: Optional[int] = None  # None means "never expires"

    @property
    def is_tombstone(self) -> bool:
        return self.value is None

    def alive_at(self, when: int) -> bool:
        """The single liveness predicate: alive for written_at <= when < expires_at."""
        return self.expires_at is None or when < self.expires_at


class InMemoryDB:
    """A key -> {field: value} record store with TTLs, history, backup and restore."""

    def __init__(self) -> None:
        # key -> field -> append-only version log, ascending by written_at.
        self._db: dict[str, dict[str, list[_Version]]] = {}
        # Append-only, non-decreasing in timestamp: (timestamp, snapshot).
        self._backups: list[tuple[int, _Snapshot]] = []

    # ------------------------------------------------------------------
    # Internal primitives -- every read in the class goes through _resolve
    # ------------------------------------------------------------------

    def _append(
        self, timestamp: int, key: str, field: str, value: Optional[str], expires_at: Optional[int]
    ) -> None:
        """Append a version (or a tombstone, when `value` is None) to the log."""
        log = self._db.setdefault(key, {}).setdefault(field, [])
        log.append(_Version(timestamp, value, expires_at))

    def _resolve(self, when: int, key: str, field: str) -> Optional[_Version]:
        """The version of `key`/`field` in force at `when`, or None if there is none.

        None covers all three ways a field can fail to read: never written by
        `when`, deleted by `when`, or expired by `when`.
        """
        log = self._db.get(key, {}).get(field)
        if not log:
            return None
        # Last version whose written_at <= when. Ties go to the later write.
        # `when + 1` with bisect_left is the `<=` search: bisect_left lands
        # before equal keys, so searching the next instant puts the index after
        # every version stamped `when`. Timestamps are integers, which is what
        # makes +1 the correct successor -- do not "simplify" this to `when`.
        index = bisect.bisect_left(log, when + 1, key=lambda version: version.written_at)
        if index == 0:
            return None  # the field did not exist yet at `when`
        version = log[index - 1]
        if version.is_tombstone or not version.alive_at(when):
            return None
        return version

    def _resolved_items(
        self, when: int, key: str, prefix: str = ""
    ) -> list[tuple[str, _Version]]:
        """Every readable `(field, version)` of `key` matching `prefix`, field-ascending."""
        record = self._db.get(key)
        if not record:
            return []
        matches = []
        for field in record:
            if not field.startswith(prefix):
                continue
            version = self._resolve(when, key, field)
            if version is not None:
                matches.append((field, version))
        matches.sort(key=lambda item: item[0])
        return matches

    @staticmethod
    def _format(items: list[tuple[str, _Version]]) -> str:
        """Render fields as `f1(v1), f2(v2)`; the empty selection renders as ``."""
        return ", ".join(f"{field}({version.value})" for field, version in items)

    # ------------------------------------------------------------------
    # Level 1 -- core operations
    # ------------------------------------------------------------------

    def set(self, timestamp: int, key: str, field: str, value: str) -> None:
        """Set `field` on `key` to `value` permanently, clearing any TTL."""
        self._append(timestamp, key, field, value, expires_at=None)

    def get(self, timestamp: int, key: str, field: str) -> Optional[str]:
        """The value of `key`/`field` if readable at `timestamp`, else None."""
        version = self._resolve(timestamp, key, field)
        return None if version is None else version.value

    def delete(self, timestamp: int, key: str, field: str) -> bool:
        """Tombstone `key`/`field`; True only if it was readable at `timestamp`."""
        if self._resolve(timestamp, key, field) is None:
            return False  # absent, already deleted, or expired -- nothing to do
        self._append(timestamp, key, field, value=None, expires_at=None)
        return True

    # ------------------------------------------------------------------
    # Level 2 -- scan and aggregation
    # ------------------------------------------------------------------

    def scan(self, timestamp: int, key: str) -> str:
        """All readable fields of `key` at `timestamp`, field-ascending."""
        return self.scan_by_prefix(timestamp, key, "")

    def scan_by_prefix(self, timestamp: int, key: str, prefix: str) -> str:
        """Readable fields of `key` whose name starts with `prefix`, field-ascending."""
        return self._format(self._resolved_items(timestamp, key, prefix))

    # ------------------------------------------------------------------
    # Level 3 -- TTL
    # ------------------------------------------------------------------

    def set_with_ttl(
        self, timestamp: int, key: str, field: str, value: str, ttl: int
    ) -> None:
        """Set `key`/`field`, readable for `timestamp <= q < timestamp + ttl`."""
        self._append(timestamp, key, field, value, expires_at=timestamp + ttl)

    # ------------------------------------------------------------------
    # Level 4 -- point-in-time reads
    # ------------------------------------------------------------------

    def get_when(
        self, timestamp: int, key: str, field: str, at_ts: int
    ) -> Optional[str]:
        """The value `key`/`field` held at `at_ts`, or None if it held none then.

        `timestamp` is the clock at which the question is asked and does not
        affect the answer; the history is immutable, so asking later does not
        change what was true at `at_ts`.
        """
        version = self._resolve(at_ts, key, field)
        return None if version is None else version.value

    # ------------------------------------------------------------------
    # Level 4 (retained) -- backup and restore
    # ------------------------------------------------------------------

    def backup(self, timestamp: int) -> int:
        """Snapshot readable state with REMAINING lifespans; return the record count."""
        snapshot: _Snapshot = {}
        for key in self._db:
            live = {
                field: (
                    version.value,
                    None if version.expires_at is None else version.expires_at - timestamp,
                )
                for field, version in self._resolved_items(timestamp, key)
            }
            if live:  # records with no readable field are neither stored nor counted
                snapshot[key] = live
        self._backups.append((timestamp, snapshot))
        return len(snapshot)

    def restore(self, timestamp: int, time_to_restore: int) -> None:
        """Replace readable state with the latest backup at or before `time_to_restore`.

        Written as new versions dated `timestamp` rather than by rewriting the
        log, so that `get_when` can still see across the restore: the state
        before it stays exactly as it was recorded.
        """
        # Same `<=` search as _resolve: latest backup at or before the target.
        index = bisect.bisect_left(
            self._backups, time_to_restore + 1, key=lambda entry: entry[0]
        )
        if index == 0:  # no backup at or before that instant -- no-op
            return
        _, snapshot = self._backups[index - 1]

        # Tombstone everything currently readable that the snapshot does not hold.
        for key in list(self._db):
            for field, _ in self._resolved_items(timestamp, key):
                if field not in snapshot.get(key, {}):
                    self._append(timestamp, key, field, value=None, expires_at=None)

        # Re-assert the snapshot, turning remaining lifespans back into instants.
        for key, record in snapshot.items():
            for field, (value, remaining) in record.items():
                self._append(
                    timestamp,
                    key,
                    field,
                    value,
                    None if remaining is None else timestamp + remaining,
                )
