"""Level 3 snapshot -- explicit timestamps and TTL.

This is the level the exam is really built around, and it is where a
`dict[str, str]` model starts costing money. Here it costs two edits.

First, `_Record` grows three attributes: the `timestamp` it was written at, the
`ttl` duration it carries (None means never expires), and the derived
`expires_at` instant. Because callers were already handed a record rather than a
raw string, not one of them cares that the record got wider.

Second, the read chokepoint changes shape: `_record(id)` becomes
`_record_at(id, when)`, and the entire liveness rule -- not yet written, already
expired, written with a dead-on-arrival duration -- lives inside it. `_matching`
grows the same `when` parameter and forwards it. That is the whole of the
semantic change; everything else in this file is new surface area, not rework.

The Level 1 and Level 2 methods are now one-line delegations to their `*_at`
counterparts at `timestamp=0` with no expiry, exactly as the spec defines them.
There is deliberately no second code path for the legacy API: two
implementations of the same contract is two places for it to drift.

What this file does *not* have is history. Level 3 never asks what an id used to
be, only what it is at the instant being queried, so each id stores exactly one
current record and a delete removes it. That is the right amount of machinery
for the spec in hand, and Level 4 will charge for it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Optional


@dataclass(frozen=True)
class _Record:
    """One piece of stored content, with the window over which it is readable."""

    body: str
    size: int
    timestamp: int
    ttl: Optional[int] = None
    expires_at: Optional[int] = None

    def visible_at(self, when: int) -> bool:
        """True if this record is readable at `when`: t <= when < t + ttl."""
        if when < self.timestamp:
            return False
        return self.expires_at is None or when < self.expires_at


class ContentStore:
    """A CMS-style content repository with explicit time and TTLs."""

    #: Timestamp used by the untimestamped Level 1/2 API.
    DEFAULT_TIMESTAMP = 0

    def __init__(self) -> None:
        """Initialise an empty store with its clock at zero."""
        self._records: dict[str, _Record] = {}
        # Largest timestamp handed to any *_at method; never decreases.
        self._clock: int = 0

    # ------------------------------------------------------------------
    # Internal primitives
    # ------------------------------------------------------------------

    def _advance(self, timestamp: int) -> None:
        """Move the store's clock forward; it never goes backwards."""
        if timestamp > self._clock:
            self._clock = timestamp

    def _record_at(self, content_id: str, when: int) -> Optional[_Record]:
        """The record readable under `content_id` at `when`, else None.

        Single chokepoint for reads: no public method looks in `self._records`
        directly, so "what does it mean for an id to be readable?" is answered
        in exactly one place -- and at this level that answer grew a clock.
        """
        record = self._records.get(content_id)
        if record is None or not record.visible_at(when):
            return None
        return record

    def _matching(self, prefix: str, when: int) -> Iterator[tuple[str, _Record]]:
        """Every (id, record) readable at `when` whose id starts with `prefix`.

        Both query methods funnel through here, so the definition of "in scope
        for a prefix query" exists once. Note that it asks `_record_at`, rather
        than reading the dict, so it inherits liveness for free.
        """
        for content_id in self._records:
            if not content_id.startswith(prefix):
                continue
            record = self._record_at(content_id, when)
            if record is not None:
                yield content_id, record

    @staticmethod
    def _format(content_id: str, record: _Record) -> str:
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
        self._records[content_id] = _Record(
            body=body,
            size=size,
            timestamp=timestamp,
            ttl=ttl,
            expires_at=self._expiry(timestamp, ttl),
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
        self._records[content_id] = _Record(
            body=body,
            size=size,
            timestamp=timestamp,
            ttl=renewed_ttl,
            expires_at=self._expiry(timestamp, renewed_ttl),
        )
        return True

    def delete_content_at(self, timestamp: int, content_id: str) -> bool:
        """Delete content live at `timestamp`; False if it was not live."""
        self._advance(timestamp)
        if self._record_at(content_id, timestamp) is None:
            return False
        del self._records[content_id]
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
