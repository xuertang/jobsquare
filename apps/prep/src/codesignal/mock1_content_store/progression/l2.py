"""Level 2 snapshot -- prefix search and top-N ranking added to Level 1.

Level 2 asked for querying and said nothing whatsoever about storage. Nothing
about storage changed. `_Record` is byte for byte what it was at Level 1 --
still `(timestamp, body, size)`, still one current record per id -- and none of
the four Level 1 methods was touched. The whole diff is additive.

The one judgement call here is that `find_by_prefix` and `top_n_by_size` are
both shells over a single private generator, `_live_records`. They differ in how
they sort and in how many results they keep. They do not differ at all in *which
ids are in scope*, and that question -- "which records count right now?" -- is
the one every later requirement is going to land on. Giving it one home costs
nothing today and is the difference between editing one method later and editing
two. `_format` and `_join` are factored out for the same reason: the wire format
`id(size)` and the `", "` join rule are each shared by both queries, so each
gets one definition.

"Live" at this level means precisely "present under that id" -- `delete_content`
removes the entry, so deleted content is not a match, and there is nothing else
that can make a record invisible. The name is a name for the question, not a
claim about what else might answer it later.

Note what `_live_records` does *not* do: it does not rummage in
`self._records.items()`. It walks the keys and then asks `_record` about each
one, so the readability decision stays in the accessor Level 1 built.

`timestamp` is still handed to every method, is still stored on every write, and
is still read by nothing -- including the two new queries, which take it, ignore
it, and sort by id and size alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Iterator, Optional


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

    def _live_records(self, prefix: str) -> Iterator[tuple[str, _Record]]:
        """Every (id, record) currently in scope whose id starts with `prefix`.

        The single definition of "which records count", shared by both queries.
        """
        for content_id in self._records:
            if not content_id.startswith(prefix):
                continue
            record = self._record(content_id)
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

    # ------------------------------------------------------------------
    # Level 2 -- prefix search and top-N ranking
    # ------------------------------------------------------------------

    def find_by_prefix(self, timestamp: int, prefix: str) -> str:
        """`id(size)` for every match, id-ascending, as one joined string."""
        matches = sorted(self._live_records(prefix), key=lambda m: m[0])
        return self._join(self._format(cid, rec) for cid, rec in matches)

    def top_n_by_size(self, timestamp: int, prefix: str, n: int) -> str:
        """The `n` largest matches, size descending then id ascending."""
        if n <= 0:
            return ""
        ranked = sorted(
            self._live_records(prefix),
            key=lambda item: (-item[1].size, item[0]),
        )
        return self._join(self._format(cid, rec) for cid, rec in ranked[:n])
