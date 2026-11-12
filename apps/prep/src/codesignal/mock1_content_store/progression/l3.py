"""Level 3 snapshot -- the timestamp starts meaning something, and TTLs arrive.

This is the level the exam is built around, and it is where the Level 1 decision
either pays or bills. Level 3 adds no new methods at all: one optional `ttl`
parameter on the two writers, and the rule that a record written at `t` with
duration `d` is readable for `t <= q < t + d`.

WHAT THE LEVEL 1 DECISION ACTUALLY BOUGHT
-----------------------------------------
The value Level 3 needs above all others is *when each record was written*, and
it is not derivable from anything else. `l1.py` already has it, because
`add_content` and `update_content` were handed it and it was written down rather
than discarded. So `_Record` does not need a new `timestamp` field here; it
needs `ttl` and the derived `expires_at`, which are new *inputs* the spec has
only now introduced. That is the whole distinction the Level 1 docstring argues
for, cashed out: the field that came from the caller was already there, the
fields nobody had mentioned were not, and only the second kind had to be added.

WHAT IT DID NOT BUY, HONESTLY
-----------------------------
It did not buy a zero-edit Level 3. `l1.py`'s accessor was `_record(content_id)`
-- one argument, because at Level 1 there was no second question to ask.
Readability is now a function of *two* things, so the accessor becomes
`_record_at(content_id, when)` and `_live_records` grows the same parameter,
which means every public method changes by exactly one line: the call to the
chokepoint now forwards the `timestamp` it has been carrying since Level 1.
Six methods, one line each, no restructuring. Giving `_record` an unused `when`
parameter at Level 1 would have made that zero, and it would have been designing
against a spec nobody had read. One line per method is the correct price for not
doing that, and it is worth contrasting with the reference solution's claim that
`get_content` "does not change by one character" between Levels 1 and 3 -- true
of the reference, which starts from the finished shape, and not true of anything
built without foreknowledge.

WHAT IS STILL NOT HERE
----------------------
There is still exactly one current record per id. `update_content` overwrites
it, `delete_content` removes it, and the previous value is gone. Level 3 never
asks what an id used to be -- every one of its reads is answered from the newest
write -- so there is no per-id log, no version chain and no restore path. That
is a deliberate stopping point, and `l4.py` is what it costs.

The liveness rule lives in exactly two lines: the `when < self.expires_at`
comparison inside `_Record.alive_at`, and the `record.timestamp > when` guard in
`_record_at` that keeps content invisible before it exists. Every reader in the
file -- `get_content`, both queries, and the guards inside all three mutators --
inherits both by going through the chokepoint.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Iterator, Optional


@dataclass(frozen=True)
class _Record:
    """One piece of stored content: what was written, when, and for how long.

    `timestamp` was here at Level 1, unread, because the caller supplied it.
    `ttl` and `expires_at` are what Level 3 actually added.
    """

    timestamp: int
    body: str
    size: int
    ttl: Optional[int] = None
    expires_at: Optional[int] = None

    def alive_at(self, when: int) -> bool:
        """True if this record has not expired by `when` (half-open interval)."""
        return self.expires_at is None or when < self.expires_at


class ContentStore:
    """A CMS-style content repository with TTLs, keyed by `content_id`."""

    def __init__(self) -> None:
        """Initialise an empty store."""
        # Still exactly one current record per id. Not a sequence, not a log.
        self._records: dict[str, _Record] = {}

    # ------------------------------------------------------------------
    # Internal primitives
    # ------------------------------------------------------------------

    def _record_at(self, content_id: str, when: int) -> Optional[_Record]:
        """The record readable under `content_id` at `when`, or None.

        Single chokepoint for reads. Everything that can make an id
        unreadable -- never written, written later than `when`, or expired by
        `when` -- is decided here and nowhere else.
        """
        record = self._records.get(content_id)
        if record is None or record.timestamp > when:
            return None
        return record if record.alive_at(when) else None

    def _live_records(
        self, prefix: str, when: int
    ) -> Iterator[tuple[str, _Record]]:
        """Every (id, record) live at `when` whose id starts with `prefix`.

        The single definition of "which records count", shared by both queries.
        """
        for content_id in self._records:
            if not content_id.startswith(prefix):
                continue
            record = self._record_at(content_id, when)
            if record is not None:
                yield content_id, record

    @staticmethod
    def _format(content_id: str, record: _Record) -> str:
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
    # The `ttl` parameter on the two writers is the only thing Level 3 adds to
    # this section's signatures; it defaults to None, so every Level 1 and
    # Level 2 call site keeps working untouched.
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
        self._records[content_id] = _Record(
            timestamp=timestamp,
            body=body,
            size=size,
            ttl=ttl,
            expires_at=self._expiry(timestamp, ttl),
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
        self._records[content_id] = _Record(
            timestamp=timestamp,
            body=body,
            size=size,
            ttl=renewed_ttl,
            expires_at=self._expiry(timestamp, renewed_ttl),
        )
        return True

    def delete_content(self, timestamp: int, content_id: str) -> bool:
        """Delete content live at `timestamp`; False if it was not live."""
        if self._record_at(content_id, timestamp) is None:
            return False
        del self._records[content_id]
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
