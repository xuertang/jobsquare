"""Level 1 snapshot -- basic CRUD, and nothing else.

This is what the class looked like at the ten-minute mark, before Level 2 had
been read. It knows four operations on a keyed store and it knows nothing else:
no prefixes, no ranking, no lifetimes, no past.

The one interesting decision at this level is what to do with `timestamp`.

Every Level 1 method is handed one and not one of them has any use for it. The
shortest thing that passes drops it on the floor -- that is `naive_l1.py` in
`wrong_path/`, which keeps `body` and `size` in two parallel dicts and lets the
argument fall out of scope, unread and unstored. This file makes the stored
value a `_Record(timestamp, body, size)` instead, and writes the argument down.

STORE WHAT YOU ARE GIVEN; INVENT NOTHING YOU ARE NOT
----------------------------------------------------
That is not a guess about later levels, and the distinction is worth stating
precisely, because this is exactly where "build only what the spec asks for" is
easiest to misapply.

  * Inventing a field nobody mentioned -- a lifetime, a version counter, a
    `created_by`, a per-id sequence of previous values -- is speculation. No
    caller has handed you that value; you would be manufacturing it because you
    suspect something later will want it. That is clairvoyance, and it is what
    this progression refuses to do.

  * Writing down a value the caller explicitly passed you is not speculation.
    It is the absence of a destructive act. The spec put `timestamp` in the
    signature of all four methods; the only way to end Level 1 without it is to
    go out of your way to throw it away. Keeping it costs one field and no
    decisions, and it is the honest shape of "what the caller told us at the
    moment they wrote this".

So `_Record` has exactly the three attributes that appear in `add_content`'s
own signature -- `timestamp`, `body`, `size` -- and it has no fourth.

The second half of that rule is what keeps this level honest, and unlike the
first half it is enforceable by reading the code: **nothing here ever reads
`timestamp`.** `_record` does not compare it, none of the four public methods
branches on it, and no arithmetic anywhere in this file involves it. The store
holds exactly one current record per id, overwritten in place by
`update_content` and removed outright by `delete_content`. There is no per-id
sequence of past values, because Level 1 never asks what an id used to be.
Recording the instant of a write and keeping every write are different
commitments, and only the first one is free.

One ordinary habit is also already in place: every read of the store goes
through a single private accessor, `_record`. All four public methods ask the
same question -- "is there something under this id?" -- and a question asked
four times should have one answer. That is DRY over four call sites that exist
right now, not a hook for a level nobody has read yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class _Record:
    """One piece of stored content, exactly as the caller handed it over.

    `timestamp` is here because `add_content` and `update_content` are given
    one. Nothing at this level looks at it; discarding it would be a choice,
    and keeping it is not.
    """

    timestamp: int
    body: str
    size: int


class ContentStore:
    """A CMS-style content repository keyed by `content_id`."""

    def __init__(self) -> None:
        """Initialise an empty store."""
        # Exactly one current record per id. Not a sequence, not a log.
        self._records: dict[str, _Record] = {}

    # ------------------------------------------------------------------
    # Internal primitives
    # ------------------------------------------------------------------

    def _record(self, content_id: str) -> Optional[_Record]:
        """The record stored under `content_id`, or None if there is none.

        Single chokepoint for reads: no public method looks in `self._records`
        directly, so "what does it mean for an id to be readable?" is answered
        in exactly one place.
        """
        return self._records.get(content_id)

    # ------------------------------------------------------------------
    # Level 1 -- basic CRUD
    # ------------------------------------------------------------------

    def add_content(
        self, timestamp: int, content_id: str, body: str, size: int
    ) -> bool:
        """Store new content under `content_id`; False if that id is taken."""
        if self._record(content_id) is not None:
            return False
        self._records[content_id] = _Record(
            timestamp=timestamp, body=body, size=size
        )
        return True

    def get_content(self, timestamp: int, content_id: str) -> Optional[str]:
        """Read the body stored under `content_id`, or None if there is none."""
        record = self._record(content_id)
        return None if record is None else record.body

    def update_content(
        self, timestamp: int, content_id: str, body: str, size: int
    ) -> bool:
        """Overwrite the body and size of existing content; False if absent."""
        if self._record(content_id) is None:
            return False
        self._records[content_id] = _Record(
            timestamp=timestamp, body=body, size=size
        )
        return True

    def delete_content(self, timestamp: int, content_id: str) -> bool:
        """Remove `content_id` from the store; False if it was absent."""
        if self._record(content_id) is None:
            return False
        del self._records[content_id]
        return True
