"""Level 2 snapshot -- prefix search and top-N ranking added to Level 1.

What Level 2 asked for was querying: list everything under a prefix, and rank
the largest few under a prefix. What it did *not* ask for was any change to how
content is stored, and none was made -- `_Record` and `_records` are byte for
byte what they were at Level 1.

The one judgement call is that both new public methods are shells over a single
private generator, `_matching`. `find_by_prefix` and `top_n_by_size` differ only
in how they sort and how many results they keep; the "which ids are in scope"
question is identical for both, so it is asked once. Inlining the prefix walk
into each method would have worked just as well today and would have doubled the
edit later, because every future notion of "in scope" -- expiry, deletion,
history -- lands on exactly that question.

`_format` is pulled out for the same reason: the wire format `id(size)` is
shared by both methods and should have one definition.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Optional


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

    def _matching(self, prefix: str) -> Iterator[tuple[str, _Record]]:
        """Every (id, record) readable right now whose id starts with `prefix`.

        Both query methods funnel through here, so the definition of "in scope
        for a prefix query" exists once. Note that it asks `_record`, rather
        than reading the dict, so it inherits readability for free.
        """
        for content_id in self._records:
            if not content_id.startswith(prefix):
                continue
            record = self._record(content_id)
            if record is not None:
                yield content_id, record

    @staticmethod
    def _format(content_id: str, record: _Record) -> str:
        """Render a record in the wire format `id(size)`."""
        return f"{content_id}({record.size})"

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

    # ------------------------------------------------------------------
    # Level 2 -- prefix search and top-N ranking
    # ------------------------------------------------------------------

    def find_by_prefix(self, prefix: str) -> list[str]:
        """All content whose id starts with `prefix`, id-ascending."""
        return [self._format(cid, rec) for cid, rec in sorted(self._matching(prefix))]

    def top_n_by_size(self, prefix: str, n: int) -> list[str]:
        """The `n` largest-by-size matches for `prefix`, ties broken by id."""
        if n <= 0:
            return []
        ranked = sorted(
            self._matching(prefix),
            key=lambda item: (-item[1].size, item[0]),
        )
        return [self._format(cid, rec) for cid, rec in ranked[:n]]
