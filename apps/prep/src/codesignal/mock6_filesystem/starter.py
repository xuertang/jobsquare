"""ICF Mock 6 -- FileSystem. Fill in every method; do not change the signatures.

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

from typing import Optional


class FileSystem:
    """A unix-style hierarchical file system held entirely in memory."""

    def __init__(self) -> None:
        """Initialise a file system containing only the root directory."""
        raise NotImplementedError

    def mkdir(self, timestamp: int, path: str) -> bool:
        """Create a directory at `path`; False if it is taken or has no parent."""
        raise NotImplementedError

    def add_file(self, timestamp: int, path: str, size: int) -> bool:
        """Create a file of `size` bytes at `path`; False if it cannot be placed."""
        raise NotImplementedError

    def get_file_size(self, timestamp: int, path: str) -> Optional[int]:
        """Return the size of the file at `path`, or None if there is no file."""
        raise NotImplementedError
