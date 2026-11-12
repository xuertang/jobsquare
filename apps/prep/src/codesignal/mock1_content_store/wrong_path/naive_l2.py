"""Naive Level 2 -- prefix search and top-N, written inline in both methods.

Level 2 asked for querying and said nothing about storage, so storage did not
change: still two parallel dicts, still four public methods that read them
directly, still a `timestamp` parameter on every signature that no method has
found a use for. That part is identical to the good path's Level 2, which also
changed no storage.

What differs is the two new methods. Each walks `self._bodies` itself, each
formats `id(size)` itself, and each calls `", ".join(...)` itself. Factoring the
walk into a private `_matching` generator, the format string into a `_format`
helper and the join rule into a `_join` helper would be eight extra lines to
serve two callers whose bodies are four lines each -- and at Level 2 the two
callers genuinely do not share anything except a `startswith` test, an f-string
and a separator. "Two is not a pattern" is the usual rule, and by that rule the
inlining is correct.

The rule is fine. What it misses is that the shared thing is not the code, it is
the *question* -- "which ids are in scope?" -- and Level 3 is about to change the
answer to that question. There is nothing at Level 2 that tells you so.

Note the second `timestamp` that goes unread. `find_by_prefix(timestamp, prefix)`
and `top_n_by_size(timestamp, prefix, n)` both take one and neither can use it,
because at this level "in scope" means "present in the dict" and presence is not
a function of time. So the count of methods that accept a `timestamp` and throw
it away goes from four to six, and the file still passes every test. That is the
trap widening, quietly, while nothing goes wrong.
"""

from __future__ import annotations

from typing import Optional


class ContentStore:
    """A CMS-style content repository keyed by `content_id`."""

    def __init__(self) -> None:
        """Initialise an empty store."""
        self._bodies: dict[str, str] = {}
        self._sizes: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Level 1 -- basic CRUD
    # ------------------------------------------------------------------

    def add_content(
        self, timestamp: int, content_id: str, body: str, size: int
    ) -> bool:
        """Store new content under `content_id`; False if that id is taken."""
        if content_id in self._bodies:
            return False
        self._bodies[content_id] = body
        self._sizes[content_id] = size
        return True

    def get_content(self, timestamp: int, content_id: str) -> Optional[str]:
        """Read the body stored under `content_id`, or None if there is none."""
        return self._bodies.get(content_id)

    def update_content(
        self, timestamp: int, content_id: str, body: str, size: int
    ) -> bool:
        """Overwrite the body and size of existing content; False if absent."""
        if content_id not in self._bodies:
            return False
        self._bodies[content_id] = body
        self._sizes[content_id] = size
        return True

    def delete_content(self, timestamp: int, content_id: str) -> bool:
        """Remove `content_id` from the store; False if it was absent."""
        if content_id not in self._bodies:
            return False
        del self._bodies[content_id]
        del self._sizes[content_id]
        return True

    # ------------------------------------------------------------------
    # Level 2 -- prefix search and top-N ranking
    # ------------------------------------------------------------------

    def find_by_prefix(self, timestamp: int, prefix: str) -> str:
        """All content whose id starts with `prefix`, id-ascending."""
        matches = [cid for cid in self._bodies if cid.startswith(prefix)]
        return ", ".join(f"{cid}({self._sizes[cid]})" for cid in sorted(matches))

    def top_n_by_size(self, timestamp: int, prefix: str, n: int) -> str:
        """The `n` largest-by-size matches for `prefix`, ties broken by id."""
        if n <= 0:
            return ""
        matches = [cid for cid in self._bodies if cid.startswith(prefix)]
        matches.sort(key=lambda cid: (-self._sizes[cid], cid))
        return ", ".join(f"{cid}({self._sizes[cid]})" for cid in matches[:n])
