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
"""

from __future__ import annotations

from typing import Optional, List
from dataclasses import dataclass
from collections import defaultdict


@dataclass
class _Event:
    body: Optional[str] = None
    size: Optional[int] = None


class ContentStore:
    """A CMS-style content repository keyed by `content_id`."""

    def __init__(self) -> None:
        """Initialise an empty store."""
        self._log: dict[str, List[_Event]] = defaultdict(List[_Event])

    def add_content(self, content_id: str, body: str, size: int) -> bool:
        """Store new content under `content_id`; False if that id is taken."""
        if content_id in self._log:
            return False
        self._log[content_id] = []
        self._log[content_id].append(_Event(body=body, size=size))
        return True

    def get_content(self, content_id: str) -> Optional[str]:
        """Read the body stored under `content_id`, or None if there is none."""
        if content_id not in self._log:
            return None
        return self._log[content_id][-1].body

    def update_content(self, content_id: str, body: str, size: int) -> bool:
        """Overwrite the body and size of existing content; False if absent."""
        if content_id not in self._log:
            return False
        self._log[content_id].append(_Event(body=body, size=size))
        return True

    def delete_content(self, content_id: str) -> bool:
        """Remove `content_id` from the store; False if it was absent."""
        if content_id not in self._log:
            return False
        del self._log[content_id]
        return True

    def find_by_prefix(self, prefix: str) -> list[str]:
        res = []
        for content_id, event in self._log.items():
            if content_id.startswith(prefix):
                res.append(f"{content_id}({event[-1].size})")
        return sorted(res)

    def top_n_by_size(self, prefix: str, n: int) -> list[str]:
        top = []
        for content_id, event in self._log.items():
            if content_id.startswith(prefix):
                top.append([content_id, event])
        top.sort(key=lambda item: (-item[1][-1].size, item[0]))

        res = []
        for i in range(min(n, len(top))):
            content_id, event = top[i]
            res.append(f"{content_id}({event[-1].size})")
        return res
