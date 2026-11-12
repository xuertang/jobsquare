"""Level 2 snapshot -- subtree aggregation added to Level 1.

Level 2 asked two questions about a whole subtree: how many bytes are under
this directory, and which file under it is the largest. It said nothing about
how the tree is stored, and nothing about storage changed. `_Node`, `_resolve`,
`_parent_and_name` and `_create` are byte for byte what they were at Level 1,
and not one of the three Level 1 public methods was touched.

Both new methods open the same way every Level 1 method opened -- `_resolve`,
then reject a missing node -- which is the first dividend from having named
that walk. The one new judgement call is that they also *close* the same way:
both need every file in a subtree together with its full path, so that
enumeration is one private generator, `_walk_files`, rather than two nearly
identical recursions. `get_dir_size` sums what it yields and
`find_largest_file` takes a minimum over it; they do not differ at all in which
files are in scope.

`_join` is pulled out for the narrow reason that the root case is where path
formatting goes wrong. A file directly under root is "/name", not "//name", and
that fact should be asserted in one place rather than at every recursion step.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator, Optional


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

    @staticmethod
    def _join(directory: str, name: str) -> str:
        """Append `name` to a directory path without doubling the separator."""
        return f"{directory.rstrip('/')}/{name}"

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

    def _walk_files(self, node: _Node, path: str) -> Iterator[tuple[str, _Node]]:
        """Every (full_path, file_node) in the subtree rooted at `node`.

        The one subtree traversal. Both Level 2 queries want exactly this pair
        -- the path for reporting, the node for its size -- and differ only in
        what they do with the stream.
        """
        if not node.is_dir:
            yield path, node
            return
        for name, child in node.children.items():
            yield from self._walk_files(child, self._join(path, name))

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

    # ------------------------------------------------------------------
    # Level 2 -- aggregation over the tree
    # ------------------------------------------------------------------

    def get_dir_size(self, timestamp: int, path: str) -> Optional[int]:
        """Total bytes of every file under `path`; None if `path` is not a directory.

        An empty directory is 0, which is a different answer from None, so the
        `is_dir` test comes before the sum rather than after it.
        """
        node = self._resolve(path)
        if node is None or not node.is_dir:
            return None
        return sum(file.size for _, file in self._walk_files(node, path))

    def find_largest_file(self, timestamp: int, path: str) -> Optional[str]:
        """Path of the largest file under `path`, ties broken by smallest full path.

        The sort key is (-size, full_path), so the tie-break is on the whole
        path and not on the file name: "/a/z.txt" beats "/b/a.txt".
        """
        node = self._resolve(path)
        if node is None or not node.is_dir:
            return None
        best: Optional[tuple[int, str]] = None
        for full_path, file in self._walk_files(node, path):
            key = (-file.size, full_path)
            if best is None or key < best:
                best = key
        return None if best is None else best[1]
