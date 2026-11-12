"""Level 3 snapshot -- move and copy added to Level 2.

This is the level the Level 1 factoring was buying insurance against, and the
bill has now arrived. `move` and `copy` each resolve *two* paths and split a
target into (parent, name). Counting from `mkdir`, that is the fifth and sixth
time this class needs to turn a path string into a node -- except that it does
not need to, because the walk has one definition and both new methods simply
call it.

Nothing existing changed. `_Node`, `_components`, `_join`, `_resolve`,
`_parent_and_name`, `_create`, `_walk_files` and all five earlier public
methods are byte for byte what they were at Level 2. The diff is purely
additive, which is the exam's whole claim stated as a measurement.

Three things are new below the public surface, and each has its callers in
view at the moment it is written:

    _is_inside(ancestor, candidate)  the component-wise containment test.
                                     "/ab/moved" is not inside "/a" even though
                                     the string starts with it, so this is a
                                     prefix test on component *lists* and never
                                     on the raw strings.
    _relocatable(src, dst)           the six shared refusals -- src missing, dst
                                     taken, dst's parent missing, dst's parent
                                     is a file, root on either side, dst inside
                                     src. `move` and `copy` reject on identical
                                     grounds, so they reject in one place.
    _clone(node)                     a deep copy of a subtree: the recursive
                                     half of `copy`, kept apart from the
                                     validating half.

`_relocatable` is also what makes "a failed mutation changes nothing" free
rather than delicate. Every refusal is decided before either method has written
a single byte into the tree, so there is no partially detached subtree to
unwind and no half-written clone to delete. The `dst inside src` check in
particular has to happen before the recursion starts, or the clone would copy
into what it is still traversing and never terminate.
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

    def _clone(self, node: _Node) -> _Node:
        """A deep copy of `node`: the clone shares no mutable state with it."""
        if not node.is_dir:
            return _Node(is_dir=False, size=node.size)
        clone = _Node(is_dir=True)
        for name, child in node.children.items():
            clone.children[name] = self._clone(child)
        return clone

    def _is_inside(self, ancestor: str, candidate: str) -> bool:
        """True if `candidate` lies within the subtree of `ancestor`.

        Component-wise, not string-prefix: "/ab/moved" is not inside "/a".
        """
        prefix = self._components(ancestor)
        return self._components(candidate)[: len(prefix)] == prefix

    def _relocatable(self, src: str, dst: str) -> Optional[tuple[_Node, _Node, str]]:
        """Shared validation for move/copy: (source, dst_parent, dst_name) or None.

        Every way these two operations can fail is decided here, before either
        of them touches the tree -- which is what makes a failed mutation a
        genuine no-op instead of an unwind.
        """
        if not self._components(src) or not self._components(dst):
            return None  # root is neither a legal source nor a legal target
        source = self._resolve(src)
        if source is None:
            return None  # src must exist
        if self._resolve(dst) is not None:
            return None  # dst must not exist (this also rejects src == dst)
        dst_parent, dst_name = self._parent_and_name(dst)
        if dst_parent is None:
            return None  # dst's parent is missing or is a file
        if self._is_inside(src, dst):
            return None  # cannot relocate a directory into its own subtree
        return source, dst_parent, dst_name

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

    # ------------------------------------------------------------------
    # Level 3 -- move and copy
    # ------------------------------------------------------------------

    def move(self, timestamp: int, src: str, dst: str) -> bool:
        """Relocate `src` (and its whole subtree) so its full path becomes `dst`."""
        relocation = self._relocatable(src, dst)
        if relocation is None:
            return False
        source, dst_parent, dst_name = relocation
        # `src` resolved and is not root, so its parent is a real directory.
        src_parent, src_name = self._parent_and_name(src)
        del src_parent.children[src_name]
        dst_parent.children[dst_name] = source
        return True

    def copy(self, timestamp: int, src: str, dst: str) -> bool:
        """Deep-copy `src` to `dst`, leaving the original in place."""
        relocation = self._relocatable(src, dst)
        if relocation is None:
            return False
        source, dst_parent, dst_name = relocation
        dst_parent.children[dst_name] = self._clone(source)
        return True
