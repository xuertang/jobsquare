"""Level 4 snapshot -- history, point-in-time reads, and rollback.

This is the level that costs a real refactor, and pretending otherwise would be
dishonest. Level 3 stored exactly one current record per id because Level 3 only
ever asked what an id *is*. Level 4 asks what an id *was*, and a single current
record has thrown that away. No amount of Level 1 foresight avoids this: the
storage model genuinely has to change.

What changes is the shape of the store. `_Record` becomes `_Event` -- the same
attributes plus a `kind` and a monotonic `seq` tiebreaker -- and
`dict[str, _Record]` becomes `dict[str, list[_Event]]`, an append-only per-id
log kept sorted by `(timestamp, seq)`. Current state is no longer stored at all;
it is derived. A delete stops being `del self._records[id]` and becomes another
event, which is precisely what makes the history survivable.

What does *not* change is the public surface. Every read in this file still ends
at `_record_at(content_id, when)`, and that method's contract is unchanged --
"the record readable under this id at this instant, or None". Only its body is
rewritten: instead of one dict lookup it binary-searches the id's log for the
last event at or before `when` and asks whether that event leaves the content
readable. Because the six read methods were already asking the chokepoint rather
than the container, none of them noticed.

The three write methods did notice, and that is the honest cost: `add_content_at`,
`update_content_at` and `delete_content_at` each swap an assignment (or a `del`)
for an `_append`. Their guard clauses, return contracts and TTL-renewal
arithmetic are untouched. The Level 1 and Level 2 methods, which are pure
delegations, are byte-identical to Level 3.

`get_content_at_time` is then free -- it is `get_content_at` without the clock
advance, which is to say it is the chokepoint with a different argument -- and
`rollback` is expressible inside the same log: truncate every event newer than
the target, then re-assert the survivors at `now` with their expiries shifted by
`delta`. Rollback needs no side table and no undo stack, because the log already
is the undo stack.
"""

from __future__ import annotations

import bisect
import math
from dataclasses import dataclass
from typing import Iterable, Iterator, Optional

# Event kinds. RESTORE is written by rollback() and reads back exactly like an
# ADD; keeping it distinct is purely for debuggability.
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
        """True if this event leaves the content readable at `when`."""
        if self.kind == _DELETE:
            return False
        return self.expires_at is None or when < self.expires_at


class ContentStore:
    """A CMS-style content repository with TTLs, history and rollback."""

    #: Timestamp used by the untimestamped Level 1/2 API.
    DEFAULT_TIMESTAMP = 0

    def __init__(self) -> None:
        """Initialise an empty store with its clock at zero."""
        # content_id -> append-only event log, kept sorted by (timestamp, seq).
        self._log: dict[str, list[_Event]] = {}
        # Globally monotonic tiebreaker so same-timestamp events keep call order.
        self._seq: int = 0
        # Largest timestamp handed to any *_at method; never decreases.
        self._clock: int = 0

    # ------------------------------------------------------------------
    # Internal primitives
    # ------------------------------------------------------------------

    def _next_seq(self) -> int:
        """Hand out the next global sequence number."""
        self._seq += 1
        return self._seq

    def _advance(self, timestamp: int) -> None:
        """Move the store's clock forward; it never goes backwards."""
        if timestamp > self._clock:
            self._clock = timestamp

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
        """The record readable under `content_id` at `when`, else None.

        Single chokepoint for reads: no public method looks in `self._log`
        directly, so "what does it mean for an id to be readable?" is answered
        in exactly one place -- and at this level that answer became a search
        through history rather than a dictionary lookup.
        """
        event = self._last_event_at(content_id, when)
        if event is None or not event.alive_at(when):
            return None
        return event

    def _matching(self, prefix: str, when: int) -> Iterator[tuple[str, _Event]]:
        """Every (id, record) readable at `when` whose id starts with `prefix`.

        Both query methods funnel through here, so the definition of "in scope
        for a prefix query" exists once. Note that it asks `_record_at`, rather
        than reading the store, so it inherits liveness and history for free.
        """
        for content_id in self._log:
            if not content_id.startswith(prefix):
                continue
            record = self._record_at(content_id, when)
            if record is not None:
                yield content_id, record

    @staticmethod
    def _format(content_id: str, record: _Event) -> str:
        """Render a record in the wire format `id(size)`."""
        return f"{content_id}({record.size})"

    @staticmethod
    def _expiry(timestamp: int, ttl: Optional[int]) -> Optional[int]:
        """Absolute expiry for something written at `timestamp` with `ttl`."""
        return None if ttl is None else timestamp + ttl

    # ------------------------------------------------------------------
    # Level 1 -- basic CRUD (delegates to the Level 3 API)
    # ------------------------------------------------------------------

    def add_content(self, content_id: str, body: str, size: int) -> bool:
        """Store new never-expiring content at the default timestamp."""
        return self.add_content_at(
            self.DEFAULT_TIMESTAMP, content_id, body, size, ttl=None
        )

    def get_content(self, content_id: str) -> Optional[str]:
        """Read the body of `content_id` at the default timestamp, else None."""
        return self.get_content_at(self.DEFAULT_TIMESTAMP, content_id)

    def update_content(self, content_id: str, body: str, size: int) -> bool:
        """Overwrite body and size of existing content at the default timestamp."""
        return self.update_content_at(
            self.DEFAULT_TIMESTAMP, content_id, body, size, ttl=None
        )

    def delete_content(self, content_id: str) -> bool:
        """Delete `content_id` at the default timestamp; False if it was absent."""
        return self.delete_content_at(self.DEFAULT_TIMESTAMP, content_id)

    # ------------------------------------------------------------------
    # Level 2 -- prefix search and top-N ranking (delegates to Level 3)
    # ------------------------------------------------------------------

    def find_by_prefix(self, prefix: str) -> list[str]:
        """All content whose id starts with `prefix`, id-ascending."""
        return self.find_by_prefix_at(self.DEFAULT_TIMESTAMP, prefix)

    def top_n_by_size(self, prefix: str, n: int) -> list[str]:
        """The `n` largest-by-size matches for `prefix`, ties broken by id."""
        return self.top_n_by_size_at(self.DEFAULT_TIMESTAMP, prefix, n)

    # ------------------------------------------------------------------
    # Level 3 -- explicit time and TTL
    # ------------------------------------------------------------------

    def add_content_at(
        self,
        timestamp: int,
        content_id: str,
        body: str,
        size: int,
        ttl: Optional[int] = None,
    ) -> bool:
        """Add content at `timestamp`; False if that id is already live there."""
        self._advance(timestamp)
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

    def get_content_at(self, timestamp: int, content_id: str) -> Optional[str]:
        """Body of `content_id` as of `timestamp`, or None if not live then."""
        self._advance(timestamp)
        record = self._record_at(content_id, timestamp)
        return None if record is None else record.body

    def update_content_at(
        self,
        timestamp: int,
        content_id: str,
        body: str,
        size: int,
        ttl: Optional[int] = None,
    ) -> bool:
        """Overwrite live content and renew its TTL from `timestamp`."""
        self._advance(timestamp)
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

    def delete_content_at(self, timestamp: int, content_id: str) -> bool:
        """Delete content live at `timestamp`; False if it was not live."""
        self._advance(timestamp)
        if self._record_at(content_id, timestamp) is None:
            return False
        self._append(
            content_id,
            _Event(timestamp=timestamp, seq=self._next_seq(), kind=_DELETE),
        )
        return True

    def find_by_prefix_at(self, timestamp: int, prefix: str) -> list[str]:
        """`id(size)` for every live match at `timestamp`, id-ascending."""
        self._advance(timestamp)
        matches = self._matching(prefix, timestamp)
        return [self._format(cid, rec) for cid, rec in sorted(matches)]

    def top_n_by_size_at(self, timestamp: int, prefix: str, n: int) -> list[str]:
        """The `n` largest live matches at `timestamp`, size desc then id asc."""
        self._advance(timestamp)
        if n <= 0:
            return []
        ranked = sorted(
            self._matching(prefix, timestamp),
            key=lambda item: (-item[1].size, item[0]),
        )
        return [self._format(cid, rec) for cid, rec in ranked[:n]]

    def current_time(self) -> int:
        """The store's clock: largest timestamp passed to any *_at method."""
        return self._clock

    # ------------------------------------------------------------------
    # Level 4 -- history, point-in-time reads and rollback
    # ------------------------------------------------------------------

    def get_content_at_time(self, content_id: str, timestamp: int) -> Optional[str]:
        """Historical read of the body as of `timestamp`; does not move the clock."""
        record = self._record_at(content_id, timestamp)
        return None if record is None else record.body

    def rollback(self, timestamp: int) -> int:
        """Restore the store to its state at `timestamp`, shifting surviving TTLs.

        Returns the number of items live at `current_time()` once the rewrite is
        done -- which for a real rollback is the survivor count, since every
        survivor is re-asserted at `now`.
        """
        now = self._clock
        if timestamp >= now:
            # Nothing happened after `timestamp`; nothing to undo or shift.
            return sum(1 for _ in self._matching("", now))

        delta = now - timestamp
        survivors = sorted(self._matching("", timestamp))
        self._truncate_after(timestamp)
        for content_id, record in survivors:
            self._append(
                content_id,
                _Event(
                    timestamp=now,
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
        return len(survivors)

    def _truncate_after(self, timestamp: int) -> None:
        """Erase every event strictly newer than `timestamp`."""
        for content_id in list(self._log):
            kept = self._keep_through(self._log[content_id], timestamp)
            if kept:
                self._log[content_id] = kept
            else:
                del self._log[content_id]

    @staticmethod
    def _keep_through(log: Iterable[_Event], timestamp: int) -> list[_Event]:
        """The events in `log` that are at or before `timestamp`."""
        return [event for event in log if event.timestamp <= timestamp]
