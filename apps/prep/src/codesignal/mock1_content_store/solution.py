"""Reference solution for ICF Mock 1: ContentStore.

KEY DESIGN DECISION -- why levels 3 and 4 are nearly free here
--------------------------------------------------------------
Every public method takes `timestamp` as its first argument from Level 1
onwards, and at Levels 1-2 nothing has expired yet, so that argument looks like
dead weight. That is the trap. The cheap Level 1 is `dict[str, (body, size)]`
with `timestamp` dropped on the floor; it passes Levels 1 and 2 outright, and
it has already thrown away everything Levels 3 and 4 need.

The choice this solution makes instead, at Level 1: *never store a bare string
where a record will eventually be needed*, and *never store current state where
a history will eventually be needed*. The single source of truth is an
append-only event log per content id -- immutable `_Event` records
(timestamp, seq, kind, body, size, ttl, expires_at) -- and "current state" is
not stored at all. It is *derived* by one primitive:

    _record_at(content_id, q) -> the last event with event.timestamp <= q,
                                 or None if that event is a DELETE or has
                                 already expired at q.

Every public method in all four levels is a thin shell over that primitive:

  * L1 `get_content(timestamp, id)`           -> _record_at(id, timestamp)
  * L3 `get_content(timestamp, id)`           -> _record_at(id, timestamp)
  * L4 `get_content_at_time(t, id, time_at)`  -> _record_at(id, time_at)
  * L2/L3 prefix + top-N                      -> _record_at across the id
                                                 keyspace, then sort and join

Read the first two lines again. They are not analogous, they are *the same
line*: Level 3 does not change `get_content` by one character. Carrying
`timestamp` in the signature from Level 1 is what makes that true, and it is
the strongest form of the argument -- the level that "introduces time"
introduces no new code in the reader path at all. What Level 3 actually costs
is one extra field on the record (`expires_at`), one comparison inside
`_Event.alive_at`, and a defaulted `ttl` parameter on the two writers.

Level 4 then costs *zero* new machinery for `get_content_at_time`, because a
log-plus-derived-state model can already answer "what did this look like at
time q" for any q -- the naive dict-of-current-bodies model has destroyed that
information and must be rewritten from scratch with 30 minutes left. Rollback
is log truncation plus re-asserting the survivors at the caller's `timestamp`
with shifted expiries, which is expressible *inside the same log* rather than
as a side table.

Note also what is *absent*: there is no logical clock in this class, and no
`current_time()`. `rollback(timestamp, time_at)` is told what "now" is by its
own first argument, exactly like every other method, so the store never has to
remember the largest timestamp it has seen. State you do not keep cannot drift.

The one thing deliberately left un-optimised: prefix search scans the id
keyspace (see `_live_records`). At interview scale that is correct and honest.

`solution_trie.py` is the other branch of that decision -- the same class, same
signatures, with a refcounted trie behind `_live_records` -- and it passes this
identical test suite:

    ICF_IMPL=solution_trie python3 -m pytest -q

Two things are worth taking from it. First, swapping the strategy touches
exactly three private methods -- `_append`, `_truncate_after` and
`_live_records` -- and no public one, which is what routing every prefix query
through a single primitive buys you. Second, `bench_prefix.py` measures the
tradeoff instead of asserting it, and the trie turns out to be 2.3x faster for
selective prefixes, 1.8x *slower* when the prefix matches everything, and
~2000x faster for counting matches without listing them. Only that last case is
a categorical win.
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
        """The live record for `content_id` as of `when`, or None if not readable."""
        event = self._last_event_at(content_id, when)
        if event is None or not event.alive_at(when):
            return None
        return event

    def _live_records(self, prefix: str, when: int) -> Iterator[tuple[str, _Event]]:
        """Every (id, record) live at `when` whose id starts with `prefix`."""
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
    #
    # The `ttl` parameter on the two writers is the *only* thing Level 3 adds
    # to this section; it defaults to None, so every Level 1 call site is
    # untouched. See the Level 3 banner below.
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
    # Level 3 -- explicit time and TTL
    #
    # There is deliberately no code here. Level 3 adds:
    #   * `expires_at` to `_Event` and one comparison in `_Event.alive_at`;
    #   * `ttl=None` on `add_content` and `update_content` above;
    #   * three lines in `update_content` that renew the duration from
    #     `timestamp` (`renewed_ttl`).
    # Nothing else in the class changed, and no reader changed at all. If
    # implementing this level made you rewrite storage, that is the lesson.
    # ------------------------------------------------------------------

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
