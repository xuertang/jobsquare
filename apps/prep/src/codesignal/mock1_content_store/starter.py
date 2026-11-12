"""ICF Mock 1 -- ContentStore. Fill in every method; do not change the signatures.

HOW TO USE THIS FILE
--------------------
This skeleton contains **Level 1 only**. That is deliberate: the exam is timed
level by level, and seeing the later levels early would give away the design.

When you finish a level, go back to `PROBLEM.md` and read the next one. Each
level lists its own method signatures -- copy them into your class yourself and
implement them there. Nothing is pre-stubbed for you beyond Level 1, exactly as
in the real CodeSignal editor, where the next level's methods only appear once
you have submitted the current one.

Yes, `timestamp` really is the first argument of every Level 1 method, and no,
Level 1 never inspects it. Copy the signatures as given.
"""

from __future__ import annotations

from typing import Optional


class ContentStore:
    """A CMS-style content repository keyed by `content_id`."""

    def __init__(self) -> None:
        """Initialise an empty store."""
        raise NotImplementedError

    def add_content(
        self, timestamp: int, content_id: str, body: str, size: int
    ) -> bool:
        """Store new content under `content_id`; False if that id is taken."""
        raise NotImplementedError

    def get_content(self, timestamp: int, content_id: str) -> Optional[str]:
        """Read the body stored under `content_id`, or None if there is none."""
        raise NotImplementedError

    def update_content(
        self, timestamp: int, content_id: str, body: str, size: int
    ) -> bool:
        """Overwrite the body and size of existing content; False if absent."""
        raise NotImplementedError

    def delete_content(self, timestamp: int, content_id: str) -> bool:
        """Remove `content_id` from the store; False if it was absent."""
        raise NotImplementedError
