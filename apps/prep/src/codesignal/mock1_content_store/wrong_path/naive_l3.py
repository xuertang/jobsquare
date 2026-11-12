"""Naive Level 3 -- expiry bolted on, all six read sites now corrected.

This is `naive_l3_buggy.py` after the two misses have been found and fixed. It
passes Levels 1 through 3.

The shape is unchanged and worth looking at directly. Level 3 needs to know
three things about each item -- when it was written, what duration it carries,
and when it dies -- and the good path added exactly those three as fields on the
`_Record` it was already storing. This path adds exactly the same three facts as
three more parallel dicts, so the store is now five dicts wide and every write
method has five assignments and every delete has five `del`s.

Note where the three new facts come from. Two of them, the duration and the
expiry instant, are genuinely new: Level 3 introduced `ttl` and nothing before
it could have supplied one. The third, `_starts`, is the `timestamp` this file
has been handed on every call since Level 1 and has thrown away every time. It
is not being *computed* at Level 3, it is being *recovered* -- and it can only
be recovered for writes that happen from now on. Everything written before this
moment in a real system would have no start time at all. In the exam the store
is empty at the start of each test, so nothing is lost; that is the exam being
kind, not the design being safe.

The five-way write is the visible cost. The invisible one is that the liveness
rule

    self._starts[cid] <= timestamp and
    (self._expires[cid] is None or timestamp < self._expires[cid])

is now written out six times, in `add_content`, `get_content`, `update_content`,
`delete_content`, `find_by_prefix` and `top_n_by_size`. Six copies is six things
to keep in sync the next time the rule moves, and six chances to have missed one
-- which is precisely what `naive_l3_buggy.py` records happening.

Extracting a private `_is_live(cid, when)` helper right now would collapse those
six copies to one, and it is the obvious thing to do once you have typed the
rule for the third time. It is also, exactly, the chokepoint the good path built
at minute three, arriving forty minutes late and after the bugs. Building it now
does not undo Level 3; it does help Level 4. It is not built here, because the
point of this file is to measure what the omission costs when it is carried.
"""

from __future__ import annotations

from typing import Optional


class ContentStore:
    """A CMS-style content repository with explicit time and TTLs."""

    def __init__(self) -> None:
        """Initialise an empty store."""
        self._bodies: dict[str, str] = {}
        self._sizes: dict[str, int] = {}
        self._starts: dict[str, int] = {}
        self._ttls: dict[str, Optional[int]] = {}
        self._expires: dict[str, Optional[int]] = {}

    # ------------------------------------------------------------------
    # Level 1 -- basic CRUD, now with TTLs
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
        if content_id in self._bodies:
            expires = self._expires[content_id]
            live = self._starts[content_id] <= timestamp and (
                expires is None or timestamp < expires
            )
            if live:
                return False
        self._bodies[content_id] = body
        self._sizes[content_id] = size
        self._starts[content_id] = timestamp
        self._ttls[content_id] = ttl
        self._expires[content_id] = None if ttl is None else timestamp + ttl
        return True

    def get_content(self, timestamp: int, content_id: str) -> Optional[str]:
        """Body of `content_id` as of `timestamp`, or None if not live then."""
        if content_id not in self._bodies:
            return None
        if timestamp < self._starts[content_id]:
            return None
        expires = self._expires[content_id]
        if expires is not None and timestamp >= expires:
            return None
        return self._bodies[content_id]

    def update_content(
        self,
        timestamp: int,
        content_id: str,
        body: str,
        size: int,
        ttl: Optional[int] = None,
    ) -> bool:
        """Overwrite live content and renew its TTL from `timestamp`."""
        if content_id not in self._bodies:
            return False
        if timestamp < self._starts[content_id]:
            return False
        expires = self._expires[content_id]
        if expires is not None and timestamp >= expires:
            return False
        renewed_ttl = self._ttls[content_id] if ttl is None else ttl
        self._bodies[content_id] = body
        self._sizes[content_id] = size
        self._starts[content_id] = timestamp
        self._ttls[content_id] = renewed_ttl
        self._expires[content_id] = (
            None if renewed_ttl is None else timestamp + renewed_ttl
        )
        return True

    def delete_content(self, timestamp: int, content_id: str) -> bool:
        """Delete content live at `timestamp`; False if it was not live."""
        if content_id not in self._bodies:
            return False
        if timestamp < self._starts[content_id]:
            return False
        expires = self._expires[content_id]
        if expires is not None and timestamp >= expires:
            return False
        del self._bodies[content_id]
        del self._sizes[content_id]
        del self._starts[content_id]
        del self._ttls[content_id]
        del self._expires[content_id]
        return True

    # ------------------------------------------------------------------
    # Level 2 -- prefix search and top-N ranking, now expiry-aware
    # ------------------------------------------------------------------

    def find_by_prefix(self, timestamp: int, prefix: str) -> str:
        """`id(size)` for every live match at `timestamp`, id-ascending."""
        matches = []
        for content_id in self._bodies:
            if not content_id.startswith(prefix):
                continue
            if timestamp < self._starts[content_id]:
                continue
            expires = self._expires[content_id]
            if expires is not None and timestamp >= expires:
                continue
            matches.append(content_id)
        return ", ".join(f"{cid}({self._sizes[cid]})" for cid in sorted(matches))

    def top_n_by_size(self, timestamp: int, prefix: str, n: int) -> str:
        """The `n` largest live matches at `timestamp`, size desc then id asc."""
        if n <= 0:
            return ""
        matches = []
        for content_id in self._bodies:
            if not content_id.startswith(prefix):
                continue
            if timestamp < self._starts[content_id]:
                continue
            expires = self._expires[content_id]
            if expires is not None and timestamp >= expires:
                continue
            matches.append(content_id)
        matches.sort(key=lambda cid: (-self._sizes[cid], cid))
        return ", ".join(f"{cid}({self._sizes[cid]})" for cid in matches[:n])
