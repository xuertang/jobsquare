"""Level 1 snapshot -- mkdir, add_file, get_file_size, and nothing else.

This is what the class looked like at the ten-minute mark, before Level 2 had
been read. It knows how to build a tree and read one file's size back out, and
that is the whole of what it knows: no aggregation over subtrees, no
relocation, no duplication, no reporting.

The tree itself is not the interesting decision. A directory is a node with
named children and a file is a node with a size; every candidate writes that,
and nobody loses this exam on it. The interesting decision is that the *path
walk* is a named primitive rather than four lines pasted into each method:

    _resolve(path)          -> the node at `path`, or None if any component is
                               missing or a non-final component is a file
    _parent_and_name(path)  -> (parent_dir_node, last_component), with a None
                               parent when the parent is missing, is a file, or
                               `path` is root (root has no parent)
    _create(path, node)     -> attach `node` at `path`, or False if the path is
                               taken or the parent is unusable

This is not a guess about what comes later. It is ordinary DRY, and the
justification is entirely visible inside Level 1: `mkdir`, `add_file` and
`get_file_size` all begin by turning a string like "/docs/work/b.txt" into a
node, so the walk has three callers before a single later method exists. The
`(parent, name)` split has two callers -- both creators -- and `_create` has
the same two, because "refuse if taken, refuse if the parent is missing or is a
file, otherwise attach" is the whole of `mkdir` and the whole of `add_file`
apart from which node gets attached.

Three callers for the walk and two for the placement rule is the entire
argument. Nothing here needs to know that Levels 2, 3 or 4 exist, and nothing
here anticipates them: `_Node` carries `is_dir`, `size` and `children` and not
one field more, there is no subtree traversal, and there is no notion of
relocating anything. The bet being made is only the general one --
that a walk written once is a walk debugged once -- and the off-by-one on the
root path is the specific bug it is being written once to avoid.

`timestamp` is accepted by every method and never read. Nothing in this problem
expires or is versioned; the parameter exists to keep the signatures consistent
with the ICF framework.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class _Node:
    """One entry in the tree: a directory with children, or a file with a size."""

    is_dir: bool
    size: int = 0
    children: dict[str, "_Node"] = field(default_factory=dict)


class FileSystem:
    """An in-memory unix-style file system of directories and sized files."""

    ROOT = "/"

    def __init__(self) -> None:
        """Start with root existing, empty, and always a directory."""
        self._root = _Node(is_dir=True)

    # ------------------------------------------------------------------
    # Internal primitives -- every public method is a shell over these
    # ------------------------------------------------------------------

    @staticmethod
    def _components(path: str) -> list[str]:
        """Split an absolute path into its components; root splits to []."""
        return [part for part in path.split("/") if part]

    def _resolve(self, path: str) -> Optional[_Node]:
        """The node at `path`, or None if any component along the way is missing.

        The single chokepoint for "what is at this path?". Walking *through* a
        file fails here rather than in each caller, because a file has no
        children.
        """
        node = self._root
        for name in self._components(path):
            if not node.is_dir:
                return None
            child = node.children.get(name)
            if child is None:
                return None
            node = child
        return node

    def _parent_and_name(self, path: str) -> tuple[Optional[_Node], str]:
        """The directory that would hold `path`, and `path`'s final component.

        The parent is None when `path` is root (root has no parent), when the
        parent directory does not exist, or when it exists but is a file. All
        three are refusals for the same reason -- there is nowhere to attach --
        so they collapse into one answer.
        """
        components = self._components(path)
        if not components:
            return None, ""
        parent = self._resolve(self.ROOT + "/".join(components[:-1]))
        if parent is None or not parent.is_dir:
            return None, components[-1]
        return parent, components[-1]

    def _create(self, path: str, node: _Node) -> bool:
        """Attach `node` at `path`; False if taken or the parent is unusable.

        Both creators are this method with a different node, so the three
        failure conditions -- path taken, parent missing, parent is a file --
        are written once.
        """
        parent, name = self._parent_and_name(path)
        if parent is None or name in parent.children:
            return False
        parent.children[name] = node
        return True

    # ------------------------------------------------------------------
    # Level 1 -- core operations
    # ------------------------------------------------------------------

    def mkdir(self, timestamp: int, path: str) -> bool:
        """Create one empty directory at `path`; False if it cannot be placed."""
        return self._create(path, _Node(is_dir=True))

    def add_file(self, timestamp: int, path: str, size: int) -> bool:
        """Create a file of `size` bytes at `path`; False if it cannot be placed."""
        return self._create(path, _Node(is_dir=False, size=size))

    def get_file_size(self, timestamp: int, path: str) -> Optional[int]:
        """The size of the file at `path`; None if missing or a directory.

        A directory is None and a zero-byte file is 0; the `is_dir` test keeps
        those two answers distinct, which a truthiness check would not.
        """
        node = self._resolve(path)
        if node is None or node.is_dir:
            return None
        return node.size
