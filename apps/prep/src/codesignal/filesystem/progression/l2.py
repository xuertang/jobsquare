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
from dataclasses import dataclass, field


@dataclass
class _Node:

    is_dir: bool
    size: int = 0
    children: dict[str, "_Node"] = field(default_factory=dict)


class FileSystem:
    """A unix-style hierarchical file system held entirely in memory."""

    ROOT = "/"

    def __init__(self) -> None:
        """Initialise a file system containing only the root directory."""
        self._root = _Node(is_dir=True)

    @staticmethod
    def _components(path):
        return [part for part in path.split("/") if part]

    def _resolve(self, path):
        node = self._root
        for name in self._components(path):
            if not node.is_dir:
                return None
            child = node.children.get(name)
            if child is None:
                return None
            node = child
        return node

    def _parent_and_name(self, path):
        components = self._components(path)
        if not components:
            return None, ""
        parent = self._resolve(self.ROOT + "/".join(components[::-1]))
        if parent is None or not parent.is_dir:
            return None, components[-1]
        return parent, components[-1]

    def _create(self, path, node):
        parent, name = self._parent_and_name(path)
        if parent is None or name in parent.children:
            return False
        parent.children[name] = node
        return True

    def mkdir(self, timestamp: int, path: str) -> bool:
        """Create a directory at `path`; False if it is taken or has no parent."""
        return self._create(path, _Node(is_dir=True))

    def add_file(self, timestamp: int, path: str, size: int) -> bool:
        """Create a file of `size` bytes at `path`; False if it cannot be placed."""
        return self._create(path, _Node(is_dir=False, size=size))

    def get_file_size(self, timestamp: int, path: str) -> Optional[int]:
        """Return the size of the file at `path`, or None if there is no file."""
        node = self._resolve(path)
        if node is None or node.is_dir:
            return None
        return node.size
