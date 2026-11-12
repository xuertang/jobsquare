"""Reference solution for ICF Mock 5: InMemoryDB.

KEY DESIGN DECISION -- one liveness predicate, decided at Level 1
-----------------------------------------------------------------
Level 1 has no concept of expiry. The obvious Level 1 storage is therefore

    dict[key][field] -> value          # a bare string

and it is the wrong answer, because Level 3 bolts a TTL onto every field and
suddenly *five* methods have to ask "is this field still alive?" -- `get`,
`delete`, `scan`, `scan_by_prefix`, and `backup`. A store of bare strings has
nowhere to put the expiry, so the Level 3 refactor rewrites the type of every
value in the database and edits every method that touches one.

So this solution stores a *record* from the first line of Level 1:

    dict[key][field] -> _Field(value, expires_at)      # expires_at None == forever

`expires_at` is dead weight for two whole levels. It costs one dataclass and
one `None`. What it buys is that the only code that ever asks about time is
`_Field.alive_at`, and every read in the program is routed through exactly one
of two helpers that consult it -- `_live_field` (point read) and `_live_items`
(sorted, prefix-filtered scan). Level 3 is then not a refactor at all: it is
one new public method, `set_with_ttl`, that passes a non-`None` `expires_at`
into the same `_write` that `set` already used. Nothing else changes. `get`,
`delete`, `scan` and `scan_by_prefix` filter expired fields at Level 3 because
they were already filtering them at Level 1 -- against a predicate that could
never fire yet.

That is the whole trick of this exam format: pay a few lines at Level 1 for a
shape that the later levels can extend without editing, rather than a shape
they have to unpick.

LEVEL 4 -- why a snapshot must store REMAINING lifespan, not absolute expiry
----------------------------------------------------------------------------
`backup` is not a `copy.deepcopy` of the live state, and this is the one place
where the obvious implementation is genuinely, silently wrong.

`restore` moves the time origin. A field restored at `timestamp` is supposed
to resume with whatever lifespan it had left when the snapshot was taken -- not
to reappear with the wall-clock expiry it had in a previous era. So the
snapshot stores `expires_at - backup_timestamp` (a *duration*), and `restore`
turns it back into `restore_timestamp + remaining` (an *instant*).

Concretely, the bug you get from deep-copying `expires_at`:

    set_with_ttl(10, "wallet_a", "balance", "100", 100)   # expires at 110
    backup(15)                                            # 95 units remain
    restore(1000, 15)
    get(1000, "wallet_a", "balance")

With remaining-lifespan snapshots the field is alive for [1000, 1095) and that
`get` returns "100". With absolute-expiry snapshots the field comes back
already carrying `expires_at = 110`, the clock is at 1000, and the `get`
returns `None` -- the restore silently restored nothing. `deepcopy` is the
natural thing to reach for under time pressure and it passes every test that
does not jump the clock across the restore. `test_restore_resumes_remaining_
lifespan_after_a_far_clock_jump` in the suite is the one that catches it.

Permanent fields are the degenerate case: their remaining lifespan is `None`,
which survives the round trip untouched and stays permanent forever.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from typing import Optional

#: A field's snapshotted form: (value, remaining lifespan or None for permanent).
_Snapshot = dict[str, dict[str, tuple[str, Optional[int]]]]


@dataclass(frozen=True)
class _Field:
    """One stored field: its value plus the instant it stops being readable."""

    value: str
    expires_at: Optional[int] = None  # None means "never expires"

    def alive_at(self, when: int) -> bool:
        """The single liveness predicate: alive for t <= when < expires_at."""
        return self.expires_at is None or when < self.expires_at


class InMemoryDB:
    """A key -> {field: value} record store with TTLs, backup and restore."""

    def __init__(self) -> None:
        # key -> field -> _Field. Records with no fields at all are dropped.
        self._db: dict[str, dict[str, _Field]] = {}
        # Append-only, non-decreasing in timestamp: (timestamp, snapshot).
        self._backups: list[tuple[int, _Snapshot]] = []

    # ------------------------------------------------------------------
    # Internal primitives -- every read in the class goes through these
    # ------------------------------------------------------------------

    def _write(self, key: str, field: str, value: str, expires_at: Optional[int]) -> None:
        """Create or overwrite `field` on `key`, replacing value and lifespan."""
        self._db.setdefault(key, {})[field] = _Field(value, expires_at)

    def _live_field(self, timestamp: int, key: str, field: str) -> Optional[_Field]:
        """The record for `key`/`field` if it is alive at `timestamp`, else None."""
        record = self._db.get(key)
        if record is None:
            return None
        entry = record.get(field)
        if entry is None or not entry.alive_at(timestamp):
            return None
        return entry

    def _live_items(
        self, timestamp: int, key: str, prefix: str = ""
    ) -> list[tuple[str, _Field]]:
        """Every live `(field, record)` of `key` matching `prefix`, field-ascending."""
        record = self._db.get(key)
        if not record:
            return []
        matches = [
            (field, entry)
            for field, entry in record.items()
            if field.startswith(prefix) and entry.alive_at(timestamp)
        ]
        matches.sort(key=lambda item: item[0])
        return matches

    @staticmethod
    def _format(items: list[tuple[str, _Field]]) -> str:
        """Render fields as `f1(v1), f2(v2)`; the empty selection renders as ``."""
        return ", ".join(f"{field}({entry.value})" for field, entry in items)

    # ------------------------------------------------------------------
    # Level 1 -- core operations
    # ------------------------------------------------------------------

    def set(self, timestamp: int, key: str, field: str, value: str) -> None:
        """Set `field` on `key` to `value` permanently, clearing any TTL."""
        self._write(key, field, value, expires_at=None)

    def get(self, timestamp: int, key: str, field: str) -> Optional[str]:
        """The value of `key`/`field` if live at `timestamp`, else None."""
        entry = self._live_field(timestamp, key, field)
        return None if entry is None else entry.value

    def delete(self, timestamp: int, key: str, field: str) -> bool:
        """Remove `key`/`field`; True only if it was live at `timestamp`."""
        record = self._db.get(key)
        if record is None or field not in record:
            return False
        was_live = record[field].alive_at(timestamp)
        # Purge unconditionally: an expired field is removed too, so nothing
        # can observe or resurrect it later.
        del record[field]
        if not record:
            del self._db[key]
        return was_live

    # ------------------------------------------------------------------
    # Level 2 -- scan and aggregation
    # ------------------------------------------------------------------

    def scan(self, timestamp: int, key: str) -> str:
        """All live fields of `key` at `timestamp`, field-ascending."""
        return self.scan_by_prefix(timestamp, key, "")

    def scan_by_prefix(self, timestamp: int, key: str, prefix: str) -> str:
        """Live fields of `key` whose name starts with `prefix`, field-ascending."""
        return self._format(self._live_items(timestamp, key, prefix))

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
        """Snapshot live state with REMAINING lifespans; return the record count."""
        snapshot: _Snapshot = {}
        for key, record in self._db.items():
            live = {
                field: (
                    entry.value,
                    None if entry.expires_at is None else entry.expires_at - timestamp,
                )
                for field, entry in record.items()
                if entry.alive_at(timestamp)
            }
            if live:  # records with no live field are neither stored nor counted
                snapshot[key] = live
        self._backups.append((timestamp, snapshot))
        return len(snapshot)

    def restore(self, timestamp: int, time_to_restore: int) -> None:
        """Replace all state with the latest backup at or before `time_to_restore`."""
        index = bisect.bisect_right(
            self._backups, time_to_restore, key=lambda entry: entry[0]
        )
        if index == 0:  # no backup at or before that instant -- no-op
            return
        _, snapshot = self._backups[index - 1]
        self._db = {
            key: {
                field: _Field(
                    value,
                    None if remaining is None else timestamp + remaining,
                )
                for field, (value, remaining) in record.items()
            }
            for key, record in snapshot.items()
        }
