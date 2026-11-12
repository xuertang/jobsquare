"""Reference solution for ICF Mock 6: FileSystem.

KEY DESIGN DECISION -- path resolution and subtree walking as named primitives
-----------------------------------------------------------------------------
This exam is the odd one out in this kit. The other mocks are won by choosing
the right *storage* shape (an append-only log, a sorted interval list, a
fallback chain). Here there is no time dimension, no history, and no expiry:
`timestamp` is accepted by every method and never read. The tree itself is
obvious -- a node with `children` for directories, a `size` for files. Nobody
loses this exam on the data structure.

You lose it on **repetition**. Every single method starts by turning a string
like `"/docs/work/b.txt"` into a node, and every *mutating* method also has to
split a target into `(parent_node, final_name)`. So the two primitives written
before `mkdir` is finished are:

    _resolve(path)           -> the node at `path`, or None if any component
                                is missing or a non-final component is a file
    _parent_and_name(path)   -> (parent_dir_node, last_component), with a
                                None parent when the parent is missing, is a
                                file, or `path` is root (root has no parent)

`mkdir`, `add_file` and `get_file_size` are then one line of logic each on top
of those. That feels like over-engineering at minute six. It stops feeling
that way at Level 3, where `move` and `copy` each resolve *two* paths and split
a target -- six more walks. A candidate who inlined `path.split("/")` three
times at Level 1 writes the walk for the fifth and sixth time at minute fifty,
under time pressure, and that is where the off-by-one on the root path lives.

Level 4 makes exactly the same argument about the *second* primitive, and it
makes it harder rather than softer. Level 2 needs to enumerate every file in a
subtree twice -- once to sum sizes (`get_dir_size`), once to take a maximum
(`find_largest_file`) -- so the natural move at minute twenty-five is:

    _walk_files(node, path)  -> yields (full_path, file_node) for every file
                                in the subtree, at any depth, building the
                                full path as it descends

`get_dir_size` is then a `sum(...)` over it and `find_largest_file` is a `min`
on `(-size, path)`. Level 4's `find_files_by_size` is a *third* consumer of the
identical enumeration: filter on `size >= threshold`, sort by path, format.
Written on top of `_walk_files` its body is **10 lines** (measured below, from
`node = self._resolve(path)` to the `", ".join`) and it needs no new traversal
machinery at all. Written by a candidate who put two separate ad-hoc
recursions inside `get_dir_size` and `find_largest_file` -- each accumulating
into a local, each re-deriving the child path with its own `"/" + name` join --
Level 4 is a third recursion, written at minute seventy, and the root-path join
bug (`"//pic.png"`) gets one more chance to appear in the *rendered output*,
where it is visible to the grader as a wrong string rather than swallowed by a
sum.

So the two questions this exam actually asks are: how many times did you write
the path walk, and how many times did you write the subtree walk.
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
    """An in-memory unix-style file system with move, copy and size queries."""

    ROOT = "/"

    def __init__(self) -> None:
        # Root always exists and is always a directory.
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
        """The node at `path`, or None if any component along the way is missing."""
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
        """The directory that would hold `path` and its final component."""
        components = self._components(path)
        if not components:
            return None, ""  # root has no parent
        parent = self._resolve("/".join([""] + components[:-1]) or self.ROOT)
        if parent is None or not parent.is_dir:
            return None, components[-1]
        return parent, components[-1]

    def _create(self, path: str, node: _Node) -> bool:
        """Attach `node` at `path`; False if taken or the parent is unusable."""
        parent, name = self._parent_and_name(path)
        if parent is None or name in parent.children:
            return False
        parent.children[name] = node
        return True

    def _walk_files(self, node: _Node, path: str) -> Iterator[tuple[str, _Node]]:
        """Every (full_path, file_node) in the subtree rooted at `node`."""
        if not node.is_dir:
            yield path, node
            return
        for name, child in node.children.items():
            yield from self._walk_files(child, self._join(path, name))

    def _clone(self, node: _Node) -> _Node:
        """A deep copy of `node`: the clone shares no mutable state with it."""
        if not node.is_dir:
            return _Node(is_dir=False, size=node.size)
        copy = _Node(is_dir=True)
        for name, child in node.children.items():
            copy.children[name] = self._clone(child)
        return copy

    def _is_inside(self, ancestor: str, candidate: str) -> bool:
        """True if `candidate` lies strictly within the subtree of `ancestor`."""
        prefix = self._components(ancestor)
        return self._components(candidate)[: len(prefix)] == prefix

    def _relocatable(self, src: str, dst: str) -> Optional[tuple[_Node, _Node, str]]:
        """Shared validation for move/copy: (source, dst_parent, dst_name) or None."""
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
        """Create a directory at `path`; False if taken or the parent is unusable."""
        return self._create(path, _Node(is_dir=True))

    def add_file(self, timestamp: int, path: str, size: int) -> bool:
        """Create a file of `size` bytes at `path`; False if it cannot be placed."""
        return self._create(path, _Node(is_dir=False, size=size))

    def get_file_size(self, timestamp: int, path: str) -> Optional[int]:
        """The size of the file at `path`; None if missing or a directory."""
        node = self._resolve(path)
        if node is None or node.is_dir:
            return None
        return node.size

    # ------------------------------------------------------------------
    # Level 2 -- aggregation over the tree
    # ------------------------------------------------------------------

    def get_dir_size(self, timestamp: int, path: str) -> Optional[int]:
        """Total bytes of every file under `path`; None if `path` is not a directory."""
        node = self._resolve(path)
        if node is None or not node.is_dir:
            return None
        return sum(file.size for _, file in self._walk_files(node, path))

    def find_largest_file(self, timestamp: int, path: str) -> Optional[str]:
        """Path of the largest file under `path`, ties broken by smallest full path."""
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
        # `src` resolved, so it is not root and its parent is a real directory.
        src_parent, src_name = self._parent_and_name(src)
        if src_parent is not None:
            del src_parent.children[src_name]
        dst_parent.children[dst_name] = source
        return True

    def copy(self, timestamp: int, src: str, dst: str) -> bool:
        """Deep-copy `src` to `dst`, leaving `src` in place; False if illegal."""
        relocation = self._relocatable(src, dst)
        if relocation is None:
            return False
        source, dst_parent, dst_name = relocation
        dst_parent.children[dst_name] = self._clone(source)
        return True

    # ------------------------------------------------------------------
    # Level 4 -- backward-compatible export
    # ------------------------------------------------------------------

    def find_files_by_size(self, timestamp: int, path: str, threshold: int) -> str:
        """Files of >= `threshold` bytes under `path` as "p(size), ...", by path.

        A filter over the same `_walk_files` enumeration Level 2 already needed:
        no new traversal, and the empty-result case falls out of `", ".join`.
        """
        node = self._resolve(path)
        if node is None or not node.is_dir:
            return ""  # missing, or a file -- the return type has no None
        matches = [
            (full_path, file.size)
            for full_path, file in self._walk_files(node, path)
            if file.size >= threshold
        ]
        matches.sort(key=lambda match: match[0])  # by PATH, before formatting
        return ", ".join(f"{file_path}({size})" for file_path, size in matches)
