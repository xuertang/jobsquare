"""Where does the trie actually beat the scan? Measure it; don't assert it.

    python3 bench_prefix.py            # equivalence fuzz + timing table
    python3 bench_prefix.py --quick    # skip the largest keyspace

Two things happen here. First a differential fuzz proves `solution.py` and
`solution_trie.py` are semantically identical under random operation
sequences -- because a benchmark comparing two implementations is worthless
until you know they compute the same answer. Then a timing table sweeps
keyspace size against prefix selectivity, which is the only honest way to
answer "should I have built a trie."

Read the table with the exam in mind. The interesting column is not the
speedup at 100,000 ids; it is the speedup at the few hundred ids these
problems actually use, where the trie's advantage is small enough to be noise
and its cost -- fifteen minutes of your Level 4 -- is not.

A note on the clock. The API has no `current_time()`: every method is handed
"now" as its own first argument, `rollback(timestamp, time_at)` included. So
the fuzz keeps its own `clock` variable, advances it monotonically, and passes
it in. That is exactly the contract the store relies on -- mutating calls
arrive with non-decreasing timestamps -- and the fuzz also issues reads at
instants in the *past*, which the contract explicitly permits and which is the
only way to exercise `get_content_at_time` and the historical read paths.
"""

from __future__ import annotations

import random
import sys
import time

import solution
import solution_trie

# ---------------------------------------------------------------------------
# Part 1 -- differential equivalence fuzz
# ---------------------------------------------------------------------------

_SURFACES = ["home", "home-hero", "home-cta", "host", "hostel", "footer", "h", "x"]


def _random_id(rng: random.Random) -> str:
    return f"{rng.choice(_SURFACES)}-{rng.randrange(12)}"


def fuzz(rounds: int = 300, ops: int = 60, seed: int = 0) -> None:
    """Drive both stores through identical random op sequences; assert equality."""
    for round_index in range(rounds):
        rng = random.Random(seed + round_index)
        a, b = solution.ContentStore(), solution_trie.ContentStore()
        # The fuzz's own clock. Mutating calls must be non-decreasing, so this
        # only ever moves forward; reads are free to name instants behind it.
        clock = 0
        for _ in range(ops):
            clock += rng.randrange(0, 4)
            cid = _random_id(rng)
            past = rng.randrange(0, clock + 1)
            choice = rng.random()
            if choice < 0.30:
                ttl = rng.choice([None, 1, 5, 20])
                args = (clock, cid, f"body{clock}", rng.randrange(1000), ttl)
                assert a.add_content(*args) == b.add_content(*args)
            elif choice < 0.45:
                args = (clock, cid, f"upd{clock}", rng.randrange(1000))
                assert a.update_content(*args) == b.update_content(*args)
            elif choice < 0.55:
                assert a.delete_content(clock, cid) == b.delete_content(clock, cid)
            elif choice < 0.75:
                # Reads may name any instant, including one in the past.
                when = clock if rng.random() < 0.5 else past
                pfx = rng.choice(["", "h", "ho", "home", "home-", "z", "footer"])
                assert a.find_by_prefix(when, pfx) == b.find_by_prefix(when, pfx)
            elif choice < 0.88:
                when = clock if rng.random() < 0.5 else past
                pfx = rng.choice(["", "h", "home", "x"])
                n = rng.randrange(0, 5)
                assert a.top_n_by_size(when, pfx, n) == b.top_n_by_size(when, pfx, n)
            elif choice < 0.95:
                args = (clock, cid, past)
                assert a.get_content_at_time(*args) == b.get_content_at_time(*args)
            else:
                # Mostly a real rewind; occasionally `time_at >= timestamp`, the
                # documented no-op, which returns a live count and changes nothing.
                target = past if rng.random() < 0.85 else clock + rng.randrange(0, 5)
                assert a.rollback(clock, target) == b.rollback(clock, target)
            # Scalar reads agree too, at now and at an instant in the past.
            assert a.get_content(clock, cid) == b.get_content(clock, cid)
            assert a.get_content(past, cid) == b.get_content(past, cid)
        # Final full-state comparison, not just per-op returns.
        assert a.find_by_prefix(clock, "") == b.find_by_prefix(clock, "")
        assert a.top_n_by_size(clock, "", 10**6) == b.top_n_by_size(clock, "", 10**6)
        # The index must exactly mirror the log keyspace after all that churn,
        # including whatever rollback erased.
        assert sorted(b._ids.keys_with_prefix("")) == sorted(b._log)
        assert len(b._ids) == len(b._log)
        # And the enumeration order the index promises is really sorted, since
        # `_live_records` relies on nothing else being needed to make it so.
        assert b._ids.keys_with_prefix("") == sorted(b._log)
    print(f"equivalence fuzz: {rounds} rounds x {ops} ops -> identical, index consistent")


# ---------------------------------------------------------------------------
# Part 2 -- timing
# ---------------------------------------------------------------------------


def _entries(result: str) -> int:
    """How many entries a `", "`-joined collection string holds."""
    return 0 if not result else result.count(", ") + 1


def _build(cls, n: int):
    """`n` ids spread over 40 surfaces, so a surface prefix selects ~n/40."""
    store = cls()
    for i in range(n):
        store.add_content(0, f"surface{i % 40:03d}-item{i:06d}", "body", i % 997)
    return store


def _time(fn, repeats: int) -> float:
    start = time.perf_counter()
    for _ in range(repeats):
        fn()
    return (time.perf_counter() - start) / repeats * 1000  # ms per call


def timings(sizes: list[int]) -> None:
    print()
    print(
        f"{'ids':>8}  {'prefix':<14} {'matches':>8}  {'scan ms':>9}  "
        f"{'trie ms':>9}  {'speedup':>8}"
    )
    print("-" * 66)
    for n in sizes:
        scan_store = _build(solution.ContentStore, n)
        trie_store = _build(solution_trie.ContentStore, n)
        repeats = max(3, min(200, 20000 // n))
        for label, prefix in (
            ("selective", "surface007-"),
            ("broad", "surface0"),
            ("empty", ""),
        ):
            matches = _entries(scan_store.find_by_prefix(0, prefix))
            scan_ms = _time(lambda: scan_store.find_by_prefix(0, prefix), repeats)
            trie_ms = _time(lambda: trie_store.find_by_prefix(0, prefix), repeats)
            ratio = scan_ms / trie_ms if trie_ms else float("inf")
            print(
                f"{n:>8}  {label:<14} {matches:>8}  {scan_ms:>9.3f}  "
                f"{trie_ms:>9.3f}  {ratio:>7.2f}x"
            )
        print()


def count_only(n: int = 50_000) -> None:
    """The case with no scan-based answer at all: counting, not enumerating."""
    trie_store = _build(solution_trie.ContentStore, n)
    scan_store = _build(solution.ContentStore, n)
    prefix = "surface007-"
    scan_ms = _time(lambda: _entries(scan_store.find_by_prefix(0, prefix)), 20)
    trie_ms = _time(lambda: trie_store._ids.count_with_prefix(prefix), 20)
    print(f"counting matches over {n} ids for prefix {prefix!r}:")
    print(f"  scan (must enumerate)      {scan_ms:9.3f} ms")
    print(
        f"  trie subtree count         {trie_ms:9.5f} ms   "
        f"<- O(len(prefix)), independent of n"
    )
    print(f"  ratio                      {scan_ms / trie_ms:9.0f}x")
    print("  This is the one shape where the trie is not an optimisation but a")
    print("  different algorithm. If a problem asks how many, not which, build it.")


if __name__ == "__main__":
    quick = "--quick" in sys.argv
    fuzz(rounds=100 if quick else 300)
    timings([200, 2_000, 20_000] if quick else [200, 1_000, 10_000, 100_000])
    count_only(20_000 if quick else 50_000)
