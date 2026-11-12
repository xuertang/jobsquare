"""Level 1 snapshot -- basic CRUD, and nothing else.

This is what the class looked like at the ten-minute mark, before Level 2 had
been read. It knows about four operations on a keyed store and it knows about
nothing else: no ranking, no prefixes, no clock, no history.

Two habits are already in place, and both are defensible as ordinary craft
rather than as guesses about what comes next:

1. The value stored under an id is a small `_Record`, not a bare `str`. The
   spec already hands us two attributes -- `body` and `size` -- so a record is
   simply the honest shape of the thing. It costs three lines now and it is the
   only reason later attributes can be added without rewriting the callers.

2. Every read of the store goes through one private accessor, `_record`. No
   public method touches `self._records` on the read path. `get_content`,
   `add_content`, `update_content` and `delete_content` all ask the same
   question -- "is there something under this id?" -- so they should ask it in
   the same place. That single accessor is the chokepoint every later level
   will edit instead of editing the public surface.

Neither habit requires knowing that Levels 2, 3 or 4 exist.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class _Record:
    """One piece of stored content: the body served, plus its size metadata."""

    body: str
    size: int


class ContentStore:
    """A CMS-style content repository keyed by `content_id`."""

    def __init__(self) -> None:
        """Initialise an empty store."""
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

    def add_content(self, content_id: str, body: str, size: int) -> bool:
        """Store new content under `content_id`; False if that id is taken."""
        if self._record(content_id) is not None:
            return False
        self._records[content_id] = _Record(body=body, size=size)
        return True

    def get_content(self, content_id: str) -> Optional[str]:
        """Read the body stored under `content_id`, or None if there is none."""
        record = self._record(content_id)
        return None if record is None else record.body

    def update_content(self, content_id: str, body: str, size: int) -> bool:
        """Overwrite the body and size of existing content; False if absent."""
        if self._record(content_id) is None:
            return False
        self._records[content_id] = _Record(body=body, size=size)
        return True

    def delete_content(self, content_id: str) -> bool:
        """Remove `content_id` from the store; False if it was absent."""
        if self._record(content_id) is None:
            return False
        del self._records[content_id]
        return True
