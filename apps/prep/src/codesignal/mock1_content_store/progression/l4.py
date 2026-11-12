"""Level 4 snapshot -- history, point-in-time reads, and rollback.

This is the level that costs a real refactor, and pretending otherwise would be
dishonest. Level 4 asks what an id *used to be* -- `get_content_at_time` reads
the past, and `rollback` rewrites it, discarding every operation newer than a
target instant and re-asserting the survivors at `timestamp` with their
remaining lifetimes intact. `l3.py` cannot answer any of that, and no amount of
Level 1 foresight would have let it: one current record per id has thrown the
previous values away by construction, and the only way to have them is to have
kept every write.

THE REFACTOR, STATED PLAINLY
----------------------------
The storage model changes for real. `_Record` becomes `_Event` -- the same five
attributes plus a `kind` and a monotonic `seq` tiebreaker -- and
`dict[str, _Record]` becomes `dict[str, list[_Event]]`, an append-only log per
id kept sorted by `(timestamp, seq)`. Current state stops being stored and
starts being *derived*. A delete stops being `del self._records[id]` and becomes
another event, which is exactly what lets a historical read see across it.

Three private primitives are new -- `_next_seq`, `_append`, `_last_event_at` --
and `_record_at` is rewritten from a dict lookup plus a timestamp guard into a
binary search for the newest event at or before `when`, followed by the same
liveness question. Its signature and its contract are unchanged: "the record
readable under this id at this instant, or None". `_Record.alive_at` becomes
`_Event.alive_at` and shifts one clause: the "not written yet" test moves out
of the predicate and into the bisect (an event the search never returns cannot
be read), and a DELETE test moves in.

WHAT THE CHOKEPOINT SAVED, MEASURED RATHER THAN ASSERTED
--------------------------------------------------------
Three of the six carried-over public methods changed body, and all three are
writers: `add_content`, `update_content` and `delete_content` each swap one
assignment (or one `del`) for an `_append`. Their guards, their return contracts
and the TTL-renewal arithmetic are untouched -- only the shape of the thing
being written changed. The three readers -- `get_content`, `find_by_prefix`,
`top_n_by_size` -- are byte for byte identical to `l3.py`. They did not notice
the storage engine being replaced underneath them, because they were asking
`_record_at`, not the container.

That is the actual payoff, and it is narrower than the usual telling. The reads
were free; the writes were not, and were never going to be, because "how a
mutation is recorded" is precisely the thing that changed. A one-line
`_write(id, record)` helper at Level 3 would have collapsed those three edits
into one -- and would have been speculative indirection at a level with nothing
to justify it. Three mechanical call sites is the right price for not writing
it.

`get_content_at_time` then costs two lines, because it is `get_content` with
`time_at` in place of `timestamp` -- the derivation the log already performs,
pointed at a different instant. `rollback` costs about thirty, and needs no side
table and no undo stack, because the log already is the undo stack: truncate
every event newer than the target, then append one RESTORE per survivor at
`timestamp` with its expiry shifted by `delta`.

Note what is still absent: there is no logical clock and no `current_time()`.
`rollback(timestamp, time_at)` is told what "now" is by its own first argument,
exactly like every other method, so the store never has to remember the largest
timestamp it has seen. State you do not keep cannot drift.
"""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass
from typing import Iterable, Iterator, Optional

# Event kinds. RESTORE is written by rollback() and behaves exactly like an
# ADD when read back -- keeping it distinct is purely for debuggability.
_ADD = "add"
_UPDATE = "update"
_DELETE = "delete"
_RESTORE = "restore"


@dataclass(frozen=True)
class _Event:
    """One immutable mutation of one content id, ordered by (timestamp, seq)."""

    timestamp: int
    seq: int
    kind: str
    body: Optional[str] = None
    size: Optional[int] = None
    ttl: Optional[int] = None
    expires_at: Optional[int] = None

    def alive_at(self, when: int) -> bool:
        """True if this event leaves the content readable at time `when`."""
        if self.kind == _DELETE:
            return False
        return self.expires_at is None or when < self.expires_at


class ContentStore:
    """A CMS-style content repository with TTLs, history and rollback."""

    def __init__(self) -> None:
        """Initialise an empty store."""
        # content_id -> event log, kept sorted by (timestamp, seq).
        self._log: dict[str, list[_Event]] = {}
        # Globally monotonic tiebreaker so same-timestamp events keep call order.
        self._seq: int = 0

    # ------------------------------------------------------------------
    # Internal primitives
    # ------------------------------------------------------------------

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _append(self, content_id: str, event: _Event) -> None:
        """Insert an event into the id's log, preserving (timestamp, seq) order."""
        log = self._log.setdefault(content_id, [])
        bisect.insort(log, event, key=lambda e: (e.timestamp, e.seq))

    def _last_event_at(self, content_id: str, when: int) -> Optional[_Event]:
        """The most recent event for `content_id` with timestamp <= `when`."""
        log = self._log.get(content_id)
        if not log:
            return None
        idx = bisect.bisect_right(
            log, (when, math.inf), key=lambda e: (e.timestamp, e.seq)
        )
        return log[idx - 1] if idx else None

    def _record_at(self, content_id: str, when: int) -> Optional[_Event]:
        """The live record for `content_id` as of `when`, or None if not readable.

        Same signature and same contract as `l3.py`'s; only the body moved,
        from a dict lookup to a search of the id's log.
        """
        event = self._last_event_at(content_id, when)
        if event is None or not event.alive_at(when):
            return None
        return event

    def _live_records(self, prefix: str, when: int) -> Iterator[tuple[str, _Event]]:
        """Every (id, record) live at `when` whose id starts with `prefix`.

        The single definition of "which records count", shared by both queries.
        """
        for content_id in self._log:
            if not content_id.startswith(prefix):
                continue
            record = self._record_at(content_id, when)
            if record is not None:
                yield content_id, record

    @staticmethod
    def _format(content_id: str, record: _Event) -> str:
        """Render a record as the wire format `id(size)`."""
        return f"{content_id}({record.size})"

    @staticmethod
    def _join(entries: Iterable[str]) -> str:
        """The kit-wide collection format: entries joined by a comma and a space."""
        return ", ".join(entries)

    @staticmethod
    def _expiry(timestamp: int, ttl: Optional[int]) -> Optional[int]:
        """Absolute expiry for something written at `timestamp` with `ttl`."""
        return None if ttl is None else timestamp + ttl

    # ------------------------------------------------------------------
    # Level 1 -- basic CRUD
    # ------------------------------------------------------------------

    def add_content(
        self,
        timestamp: int,
        content_id: str,
        body: str,
        size: int,
        ttl: Optional[int] = None,
    ) -> bool:
        """Add content at `timestamp`; False if that id is already live there."""
        if self._record_at(content_id, timestamp) is not None:
            return False
        self._append(
            content_id,
            _Event(
                timestamp=timestamp,
                seq=self._next_seq(),
                kind=_ADD,
                body=body,
                size=size,
                ttl=ttl,
                expires_at=self._expiry(timestamp, ttl),
            ),
        )
        return True

    def get_content(self, timestamp: int, content_id: str) -> Optional[str]:
        """Body of `content_id` as of `timestamp`, or None if not live then."""
        record = self._record_at(content_id, timestamp)
        return None if record is None else record.body

    def update_content(
        self,
        timestamp: int,
        content_id: str,
        body: str,
        size: int,
        ttl: Optional[int] = None,
    ) -> bool:
        """Overwrite live content and renew its TTL from `timestamp`."""
        current = self._record_at(content_id, timestamp)
        if current is None:
            return False
        renewed_ttl = current.ttl if ttl is None else ttl
        self._append(
            content_id,
            _Event(
                timestamp=timestamp,
                seq=self._next_seq(),
                kind=_UPDATE,
                body=body,
                size=size,
                ttl=renewed_ttl,
                expires_at=self._expiry(timestamp, renewed_ttl),
            ),
        )
        return True

    def delete_content(self, timestamp: int, content_id: str) -> bool:
        """Delete content live at `timestamp`; False if it was not live."""
        if self._record_at(content_id, timestamp) is None:
            return False
        self._append(
            content_id,
            _Event(timestamp=timestamp, seq=self._next_seq(), kind=_DELETE),
        )
        return True

    # ------------------------------------------------------------------
    # Level 2 -- prefix search and top-N ranking
    # ------------------------------------------------------------------

    def find_by_prefix(self, timestamp: int, prefix: str) -> str:
        """`id(size)` for every live match at `timestamp`, id-ascending."""
        matches = sorted(self._live_records(prefix, timestamp), key=lambda m: m[0])
        return self._join(self._format(cid, rec) for cid, rec in matches)

    def top_n_by_size(self, timestamp: int, prefix: str, n: int) -> str:
        """The `n` largest live matches at `timestamp`, size desc then id asc."""
        if n <= 0:
            return ""
        ranked = sorted(
            self._live_records(prefix, timestamp),
            key=lambda item: (-item[1].size, item[0]),
        )
        return self._join(self._format(cid, rec) for cid, rec in ranked[:n])

    # ------------------------------------------------------------------
    # Level 4 -- history and rollback
    # ------------------------------------------------------------------

    def get_content_at_time(
        self, timestamp: int, content_id: str, time_at: int
    ) -> Optional[str]:
        """Historical read: the body `content_id` held at `time_at`."""
        record = self._record_at(content_id, time_at)
        return None if record is None else record.body

    def rollback(self, timestamp: int, time_at: int) -> int:
        """Restore the store to its state at `time_at`, shifting surviving TTLs."""
        if time_at >= timestamp:
            # Nothing happened after `time_at`; nothing to undo or shift.
            return sum(1 for _ in self._live_records("", timestamp))

        delta = timestamp - time_at
        # Materialise before truncating: `_live_records` walks `self._log`.
        survivors = sorted(self._live_records("", time_at), key=lambda item: item[0])
        self._truncate_after(time_at)
        for content_id, record in survivors:
            self._append(
                content_id,
                _Event(
                    timestamp=timestamp,
                    seq=self._next_seq(),
                    kind=_RESTORE,
                    body=record.body,
                    size=record.size,
                    ttl=record.ttl,
                    expires_at=(
                        None if record.expires_at is None else record.expires_at + delta
                    ),
                ),
            )
        # A survivor was live at `time_at`, so its expiry E satisfies
        # E > time_at, hence E + delta > timestamp: every survivor is live at
        # `timestamp` and the count is exactly len(survivors).
        return len(survivors)

    def _truncate_after(self, time_at: int) -> None:
        """Erase every event strictly newer than `time_at`."""
        for content_id in list(self._log):
            kept = self._keep_through(self._log[content_id], time_at)
            if kept:
                self._log[content_id] = kept
            else:
                del self._log[content_id]

    @staticmethod
    def _keep_through(log: Iterable[_Event], time_at: int) -> list[_Event]:
        return [event for event in log if event.timestamp <= time_at]
