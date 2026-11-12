"""Naive Level 4 -- a history side table bolted alongside the five dicts.

Level 4 asks two questions the Level 3 storage physically cannot answer. What
was this id's body at `time_at`? And: put the whole store back the way it was at
`time_at`. Five dicts of *current* state have thrown the past away on every
write; `self._bodies[cid] = body` is destructive and there is no copy anywhere.

So storage has to change. That much is true of the good path too, and pretending
otherwise would be dishonest -- `progression/l3.py` cannot answer these either.
The difference is what the change costs, and the difference comes from having
somewhere to put it.

The good path already funnelled every read through one accessor, so it converted
the store itself: `dict[str, _Record]` became `dict[str, list[_Event]]`, current
state stopped being stored and started being derived, and its public methods did
not notice. This path has six public methods that each read the five dicts by
hand. Converting the dicts away means editing all six, at minute sixty, with the
clock running -- and every one of those six edits is a place to reintroduce the
bugs `naive_l3_buggy.py` already recorded once.

So it does not convert them. It adds a sixth container next to them --
`self._history`, an append-only list of `_Entry` per id -- and keeps the five
current-state dicts exactly as they were, because that is the only change that
leaves the six existing methods alone. The two new Level 4 methods read the
history; everything else keeps reading the dicts.

That is the realistic minute-sixty move and it does work. What it buys is a
store with two representations of the same facts and a write path that has to
update both:

* every one of the three writers now performs five dict assignments (or five
  `del`s) *and* appends an entry, and the two must agree or the store lies;
* `rollback` cannot patch the dicts incrementally, because they hold no history
  to patch, so it truncates the log and then rebuilds all five dicts from
  scratch -- a second, separate implementation of "what is the current state",
  living inside `rollback` and nowhere else;
* the liveness rule now exists in *eight* places: the six from Level 3, plus
  `get_content_at_time` and `rollback`, which have to re-derive it against
  history entries rather than against the dicts, in a slightly different shape.

Note the last one especially. The rule is not repeated eight times identically;
it is repeated in two dialects, one that reads `self._expires[cid]` and one that
reads `entry.expires`. Two dialects of one invariant is how stores start
disagreeing with themselves.

There is one more cost that only shows up under this API, and it is worth
naming. Every method is handed "now" as its own `timestamp` and there is no
`current_time()` anywhere -- the store is never supposed to need to know what
time it is. But `rollback(timestamp, time_at)` here has to *rebuild* the five
current-state dicts, and a rebuilt dict has to record a start time for each
survivor, so `rollback` writes `self._starts[cid] = timestamp` and the dicts now
hold state whose meaning depends on when the last rollback happened. The good
path never faces that question, because it has no current-state dicts to rebuild
-- it appends a restore event to the log and the derivation does the rest. The
side table did not just duplicate the data; it forced the store to take a
position on "now" that the API deliberately never asked it to hold.

None of this is incompetent. It is the cheapest correct thing available *from
here*, which is exactly the point: the expensive decision was made forty minutes
ago and this is the invoice.
"""

from __future__ import annotations

from typing import NamedTuple, Optional

# Entry kinds. RESTORE is written by rollback() and reads back exactly like an
# ADD; keeping it distinct is purely for debuggability.
_ADD = "add"
_UPDATE = "update"
_DELETE = "delete"
_RESTORE = "restore"


class _Entry(NamedTuple):
    """One historical mutation of one content id, ordered by (timestamp, seq)."""

    timestamp: int
    seq: int
    kind: str
    body: Optional[str] = None
    size: Optional[int] = None
    ttl: Optional[int] = None
    expires: Optional[int] = None


class ContentStore:
    """A CMS-style content repository with TTLs, history and rollback."""

    def __init__(self) -> None:
        """Initialise an empty store."""
        self._bodies: dict[str, str] = {}
        self._sizes: dict[str, int] = {}
        self._starts: dict[str, int] = {}
        self._ttls: dict[str, Optional[int]] = {}
        self._expires: dict[str, Optional[int]] = {}
        # Side table added at Level 4: append-only mutation log per id. Holds
        # the same facts as the five dicts above, plus the ones they overwrote.
        self._history: dict[str, list[_Entry]] = {}
        # Tiebreaker so same-timestamp entries keep their call order.
        self._seq: int = 0

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
        expires_at = None if ttl is None else timestamp + ttl
        self._bodies[content_id] = body
        self._sizes[content_id] = size
        self._starts[content_id] = timestamp
        self._ttls[content_id] = ttl
        self._expires[content_id] = expires_at
        self._seq += 1
        self._history.setdefault(content_id, []).append(
            _Entry(timestamp, self._seq, _ADD, body, size, ttl, expires_at)
        )
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
        expires_at = None if renewed_ttl is None else timestamp + renewed_ttl
        self._bodies[content_id] = body
        self._sizes[content_id] = size
        self._starts[content_id] = timestamp
        self._ttls[content_id] = renewed_ttl
        self._expires[content_id] = expires_at
        self._seq += 1
        self._history.setdefault(content_id, []).append(
            _Entry(timestamp, self._seq, _UPDATE, body, size, renewed_ttl, expires_at)
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
        self._seq += 1
        self._history.setdefault(content_id, []).append(
            _Entry(timestamp, self._seq, _DELETE)
        )
        return True

    # ------------------------------------------------------------------
    # Level 2 -- prefix search and top-N ranking, expiry-aware
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

    # ------------------------------------------------------------------
    # Level 4 -- history, point-in-time reads and rollback
    # ------------------------------------------------------------------

    def get_content_at_time(
        self, timestamp: int, content_id: str, time_at: int
    ) -> Optional[str]:
        """Historical read: the body `content_id` held at `time_at`."""
        entries = self._history.get(content_id)
        if not entries:
            return None
        found = None
        for entry in reversed(entries):
            if entry.timestamp <= time_at:
                found = entry
                break
        if found is None or found.kind == _DELETE:
            return None
        if found.expires is not None and time_at >= found.expires:
            return None
        return found.body

    def rollback(self, timestamp: int, time_at: int) -> int:
        """Restore the store to its state at `time_at`, shifting surviving TTLs.

        Returns the number of items live at `timestamp` once the rewrite is done.
        """
        if time_at >= timestamp:
            # No-op: nothing happened after `time_at`. Count what is live at
            # `timestamp`, straight off the current-state dicts.
            count = 0
            for content_id in self._bodies:
                expires = self._expires[content_id]
                if self._starts[content_id] <= timestamp and (
                    expires is None or timestamp < expires
                ):
                    count += 1
            return count

        delta = timestamp - time_at
        # Which ids were live at `time_at`? The dicts cannot say, so this has to
        # be re-derived from history -- a second implementation of liveness, in a
        # different dialect from the six above.
        survivors = []
        for content_id, entries in self._history.items():
            found = None
            for entry in reversed(entries):
                if entry.timestamp <= time_at:
                    found = entry
                    break
            if found is None or found.kind == _DELETE:
                continue
            if found.expires is not None and time_at >= found.expires:
                continue
            survivors.append((content_id, found))

        # Erase everything newer than the target from the log.
        for content_id in list(self._history):
            kept = [e for e in self._history[content_id] if e.timestamp <= time_at]
            if kept:
                self._history[content_id] = kept
            else:
                del self._history[content_id]

        # The five current-state dicts hold no history, so they cannot be
        # rewound -- they have to be thrown away and rebuilt from the survivors.
        self._bodies.clear()
        self._sizes.clear()
        self._starts.clear()
        self._ttls.clear()
        self._expires.clear()

        for content_id, entry in sorted(survivors):
            shifted = None if entry.expires is None else entry.expires + delta
            self._bodies[content_id] = entry.body
            self._sizes[content_id] = entry.size
            self._starts[content_id] = timestamp
            self._ttls[content_id] = entry.ttl
            self._expires[content_id] = shifted
            self._seq += 1
            self._history.setdefault(content_id, []).append(
                _Entry(
                    timestamp,
                    self._seq,
                    _RESTORE,
                    entry.body,
                    entry.size,
                    entry.ttl,
                    shifted,
                )
            )
        # A survivor was live at `time_at`, so its shifted expiry is past
        # `timestamp`: every survivor is live now and the count is their number.
        return len(survivors)
