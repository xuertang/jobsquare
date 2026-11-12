"""Naive Level 3, first attempt -- expiry bolted on, and two sites missed.

THIS FILE IS EXPECTED TO FAIL ITS TESTS. It is the honest first draft, kept as
evidence. `naive_l3.py` is the corrected version.

Level 3 hands you three new facts about every stored item: the timestamp it was
written at, the TTL duration it carries, and the absolute instant it dies. The
good path put those three facts on the `_Record` it was already storing and
taught its one read accessor the liveness rule. This path has no record and no
accessor, so the same three facts become three more parallel dicts --
`_starts`, `_ttls`, `_expires` -- and the liveness rule has to be typed out
again at every place that reads the store.

Note what Level 3 does *not* require here, and how that hides the damage. There
are no new methods and no renames: `timestamp` has been the first parameter of
all six public methods since Level 1, so the diff is confined to method bodies.
Nothing about the shape of the file announces that a load-bearing change just
happened. The `timestamp` this file has spent two levels ignoring simply starts
mattering, in six places at once, and the compiler has no opinion about any of
them.

Those six places are the four CRUD methods and the two query methods. Six copies
of

    if timestamp < self._starts[cid]: not live
    expires = self._expires[cid]
    if expires is not None and timestamp >= expires: not live

is what "the compiler cannot help you" looks like in practice. Nothing in this
file is wrong in a way Python will tell you about; the dicts are all present and
all populated. The only thing that goes wrong is that a human patching six
places under a clock patches five.

The two misses in this draft, in the order a candidate makes them:

1. `add_content` -- the duplicate-id guard is still the Level 1 guard,
   `if content_id in self._bodies`. It is the one read path that does not *look*
   like a read, so it does not get visited when you go around adding liveness
   checks to the readers. Expired content therefore cannot be re-added, and the
   spec is explicit that it must be.

2. `find_by_prefix` -- gets the expiry half of the rule and not the "not yet
   written" half. This is the difference between a method you *edit* and a
   method you *rewrite*. `find_by_prefix` already had a loop with a `continue`
   in it, so the patch was to drop one more `continue` into the loop that was
   there -- and the thing on your mind while reading a level titled "Time and
   TTL" is expiry, not the fact that a query can now name an instant before a
   write. `top_n_by_size`, one method down, got the whole rule correctly,
   because its `matches` collection had to be rebuilt anyway to accommodate the
   liveness filter alongside the two-key sort, and rebuilding it meant
   re-deriving the rule from the spec instead of inheriting Level 2's
   assumptions. Editing carries the old assumptions forward; rewriting does not.

The second miss is the interesting one, and the reason this file is kept. It is
invisible to Level 3. Level 3 guarantees non-decreasing timestamps on mutating
calls and its own tests never read a prefix at an instant earlier than a write,
so the missing half of the rule is never exercised and the Level 3 suite passes
it. It detonates one level later, in Level 4's backward-compatibility test,
where a read at `t = 0` must not see content written at `t = 5`. See
`WRONG_PATH.md` for the exact failure.
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
        # BUG 1: presence in the dict is not liveness. An id that has expired is
        # still a key here, and the spec says an add over it must succeed.
        if content_id in self._bodies:
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
            # BUG 2: the expiry half of the rule is here; the "not yet written"
            # half is not. Level 3 never reads before a write, so this passes.
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
