"""Mock 1, variant solution: ContentStore with a trie-backed prefix index.

WHY THIS FILE EXISTS
--------------------
`solution.py` closes with a deliberate non-optimisation: prefix search scans
the id keyspace. This file is the other branch of that decision, kept separate
so you can see *exactly* what changes -- and, in `bench_prefix.py`, measure what
it buys. Both files pass the identical 68-test suite:

    python3 -m pytest -q                          # solution.py
    ICF_IMPL=solution_trie python3 -m pytest -q   # this file

THE DELTA IS THREE PRIVATE METHODS
----------------------------------
That is the point worth internalising, and it is a claim you can check rather
than take on faith: the class body below overrides exactly three names, all
private, and every public method across all four levels is inherited untouched.

    _append          -- mirror a newly-created id into the index
    _truncate_after  -- mirror ids that rollback erased out of the index
    _live_records    -- ask the index for candidates instead of scanning

Because `solution.py` routes every prefix query through one private primitive,
`_live_records`, that is the whole swap. Six public methods across four levels
-- `add_content`, `get_content`, `update_content`, `delete_content`,
`find_by_prefix`, `top_n_by_size`, plus Level 4's `get_content_at_time` and
`rollback` -- are inherited verbatim and none of them knows a trie exists.

If Level 2's prefix logic had been inlined into `find_by_prefix` and
`top_n_by_size` separately, this swap would be a rewrite instead of a subclass,
and the rollback path would almost certainly have been missed -- which is the
actual failure mode, because the index has to be maintained when *rollback
erases a log*, not when content is deleted. Deleted content keeps its history
and stays indexed; `delete_content` appends a DELETE event and the id must
remain in the trie, because `get_content_at_time` can still see across it.
`_truncate_after` is the only place an id genuinely leaves the store, and it is
the method people forget.

THE ONE OVERRIDE THIS FILE DECLINES TO TAKE
-------------------------------------------
`PrefixIndex.keys_with_prefix` enumerates in lexicographic order, so
`find_by_prefix` could drop its `sorted()` call entirely. That is a real saving
and it is deliberately not taken here, because taking it would mean overriding a
public method and the three-private-methods property above would stop being
true. The property is the lesson; a sort over an already-sorted list is not
worth trading it for. If you want the win in production, override
`find_by_prefix` with the `sorted()` removed and nothing else changes.

WHAT THE BENCHMARK ACTUALLY SAYS
--------------------------------
`bench_prefix.py` measures it rather than assuming it, and the answer is not
the one people expect. Measured on 10,000 ids (counting row over 50,000):

    selective prefix (250 of 10,000 match)   scan  0.90 ms  trie  0.38 ms  2.3x faster
    broad prefix     (all 10,000 match)      scan 10.02 ms  trie 18.05 ms  1.8x SLOWER
    counting matches, not listing them       scan  3.88 ms  trie 0.002 ms  ~2000x faster

So the trie is not a strict improvement. It wins when the prefix excludes most
of the keyspace, and it *loses* when the prefix matches everything, because
enumerating a trie visits one node per character of every result while the scan
runs `str.startswith` in C over a flat dict. Storing the full id at terminal
nodes (see `_TrieNode` below) removes a string concatenation per character per
result, which is what keeps the broad-prefix loss to a small constant factor,
but it cannot close that gap -- it is structural. In a compiled language the
balance shifts, which is worth saying out loud if an interviewer asks.

The one categorical win is the third row. Counting matches is O(len(prefix))
from a subtree refcount, independent of how many match, and no scan can do that
at any keyspace size. If a problem asks *how many* rather than *which*, the
trie stops being an optimisation and becomes a different algorithm.

WHETHER YOU SHOULD DO THIS IN THE EXAM: almost certainly not. A 2.3x win on the
favourable case, at a few hundred ids, is single-digit microseconds -- and the
fifteen minutes it costs come directly out of Level 4, which is worth 200
points. See the header of PATTERN 9 in `../../patterns/icf_patterns.py`. The
reason to have written one anyway is that "would you use a trie here?" is a
live interview question, and "I measured it; it is 1.8x slower for the query
shape this system actually issues" is a far better answer than reciting
O(len(prefix)).

WHAT THE INDEX CAN AND CANNOT DO HERE
-------------------------------------
It narrows candidates by prefix. It cannot tell you whether a candidate is
*live* -- that still costs a `_record_at` per surviving candidate, because
liveness depends on the query timestamp and on TTLs the index knows nothing
about. So the speedup tracks how much of the keyspace the prefix excludes:
large for a selective prefix, exactly zero for the empty prefix, which is the
one `rollback` uses. A trie that indexed liveness would have to be rebuilt on
every clock tick, which is why it does not.
"""

from __future__ import annotations

from typing import Iterator, Optional

from solution import ContentStore as _ScanContentStore
from solution import _Event


class _TrieNode:
    """One character position. `count` is how many ids live in this subtree.

    `key` holds the full id at terminal nodes and None elsewhere. That looks
    redundant -- the id is spelled out by the path -- but reconstructing it during
    traversal means a string concatenation per character per result, which costs
    more than the whole scan it was meant to replace. Storing it trades memory
    for making enumeration O(results) instead of O(total output characters).
    See `bench_prefix.py`: this one field is what holds the broad-prefix loss
    to a small constant factor instead of an order of magnitude, and it is what
    makes the selective case a win at all.
    """

    __slots__ = ("children", "count", "key")

    def __init__(self) -> None:
        self.children: dict[str, _TrieNode] = {}
        self.count: int = 0
        self.key: Optional[str] = None


class PrefixIndex:
    """A set of ids supporting prefix enumeration, counting, and deletion.

    Insertion is the easy half. The correctness of `discard` is what makes a
    trie worth its fifteen minutes or not: every node carries a refcount of the
    ids beneath it, so pruning can stop at the first node another id still
    needs. Unset the terminal flag without refcounts and dead nodes accumulate
    until `count_with_prefix` quietly starts lying.
    """

    def __init__(self) -> None:
        self._root = _TrieNode()

    def __len__(self) -> int:
        return self._root.count

    def __contains__(self, key: str) -> bool:
        node = self._node(key)
        return node is not None and node.key is not None

    def _node(self, prefix: str) -> Optional[_TrieNode]:
        node = self._root
        for ch in prefix:
            node = node.children.get(ch)
            if node is None:
                return None
        return node

    def add(self, key: str) -> bool:
        """Insert `key`; False if already present, so counts never double."""
        if key in self:
            return False
        node = self._root
        node.count += 1
        for ch in key:
            node = node.children.setdefault(ch, _TrieNode())
            node.count += 1
        node.key = key
        return True

    def discard(self, key: str) -> bool:
        """Remove `key`; False if absent. Prunes only what nothing else needs."""
        if key not in self:
            return False
        node = self._root
        node.count -= 1
        path: list[tuple[_TrieNode, str, _TrieNode]] = []
        for ch in key:
            parent, node = node, node.children[ch]
            node.count -= 1
            path.append((parent, ch, node))
        node.key = None
        for parent, ch, child in reversed(path):
            if child.count:
                break
            del parent.children[ch]
        return True

    def count_with_prefix(self, prefix: str) -> int:
        """Ids starting with `prefix`, in O(len(prefix)) -- no traversal."""
        node = self._node(prefix)
        return 0 if node is None else node.count

    def keys_with_prefix(self, prefix: str) -> list[str]:
        """Ids starting with `prefix`, already in lexicographic order."""
        node = self._node(prefix)
        if node is None:
            return []
        out: list[str] = []
        stack: list[_TrieNode] = [node]
        while stack:
            current = stack.pop()
            if current.key is not None:
                out.append(current.key)  # a prefix sorts before its extensions
            # Push reverse-sorted so the smallest child is popped next.
            for ch in sorted(current.children, reverse=True):
                stack.append(current.children[ch])
        return out


class ContentStore(_ScanContentStore):
    """Identical semantics to `solution.ContentStore`; different prefix strategy.

    Everything below this line is the entire difference between the two files:
    three private overrides and one extra attribute. No public method appears.
    """

    def __init__(self) -> None:
        super().__init__()
        #: Mirrors the key set of `self._log` -- every id that has any history.
        #: Note this is the *log* keyspace, not the *live* keyspace: expired and
        #: deleted ids stay indexed because their history is still readable.
        self._ids = PrefixIndex()

    # -- the three methods that differ -------------------------------------

    def _append(self, content_id: str, event: _Event) -> None:
        """Mirror a newly-created id into the index, then delegate."""
        if content_id not in self._log:
            self._ids.add(content_id)
        super()._append(content_id, event)

    def _truncate_after(self, time_at: int) -> None:
        """Rollback can erase whole logs; those ids must leave the index."""
        before = set(self._log)
        super()._truncate_after(time_at)
        for content_id in before - set(self._log):
            self._ids.discard(content_id)

    def _live_records(self, prefix: str, when: int) -> Iterator[tuple[str, _Event]]:
        """Ask the index for candidates instead of scanning the whole keyspace."""
        for content_id in self._ids.keys_with_prefix(prefix):
            record = self._record_at(content_id, when)
            if record is not None:
                yield content_id, record
