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
from dataclasses import dataclass


@dataclass
class _Account:
    account_id: str
    balance: int = 0
    outgoing: int = 0


class Ledger:
    """An in-memory payments ledger keyed by `account_id`."""

    def __init__(self) -> None:
        """Initialise an empty ledger."""
        self._accounts: dict[str, _Account] = {}
        self._journal: dict[str, list[tuple[int, int]]] = {}

    def _set_balance(self, account, timestamp, balance):
        account.balance = balance
        self._journal.setdefault(account.account_id, []).append((timestamp, balance))

    def create_account(self, timestamp: int, account_id: str) -> bool:
        """Open `account_id` with a zero balance; False if that id is taken."""
        if account_id in self._accounts:
            return False
        account = _Account(account_id)
        self._accounts[account_id] = account
        self._set_balance(account, timestamp, 0)
        return True

    def deposit(self, timestamp: int, account_id: str, amount: int) -> Optional[int]:
        """Credit `amount` to `account_id` and return its new balance."""
        account = self._accounts.get(account_id)
        if account is None:
            return None
        self._set_balance(account, timestamp, account.balance + amount)
        return account.balance

    def transfer(
            self, timestamp: int, source_id: str, target_id: str, amount: int
    ) -> Optional[int]:
        """Move `amount` from `source_id` to `target_id`; returns the new source balance."""
        if source_id == target_id:
            return None
        source = self._accounts.get(source_id)
        target = self._accounts.get(target_id)
        if source is None or target is None or source.balance < amount:
            return None
        self._set_balance(source, timestamp, source.balance - amount)
        self._set_balance(target, timestamp, target.balance + amount)
        source.outgoing += amount
        return source.balance

    def top_spenders(self, timestamp, n):
        if n <= 0:
            return ''
        ranked = sorted(self._accounts.values(), key=lambda account: (-account.outgoing, account.account_id))
        return ', '.join(f"{a.account_id}({a.outgoing})" for a in ranked[:n])