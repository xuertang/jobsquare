"""ICF Mock 4 -- Ledger. Fill in every method; do not change the signatures.

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


class Ledger:
    """An in-memory payments ledger keyed by `account_id`."""

    def __init__(self) -> None:
        """Initialise an empty ledger."""
        raise NotImplementedError

    def create_account(self, timestamp: int, account_id: str) -> bool:
        """Open `account_id` with a zero balance; False if that id is taken."""
        raise NotImplementedError

    def deposit(self, timestamp: int, account_id: str, amount: int) -> Optional[int]:
        """Credit `amount` to `account_id` and return its new balance."""
        raise NotImplementedError

    def transfer(
            self, timestamp: int, source_id: str, target_id: str, amount: int
    ) -> Optional[int]:
        """Move `amount` from `source_id` to `target_id`; returns the new source balance."""
        raise NotImplementedError
