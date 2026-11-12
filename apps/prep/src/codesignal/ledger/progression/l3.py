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

import bisect
from typing import Optional, List
from dataclasses import dataclass


@dataclass
class _Account:
    account_id: str
    balance: int = 0
    outgoing: int = 0


@dataclass
class _Payment:
    payment_id: str
    account_id: str
    amount: int
    execute_at: int
    seq: int


class Ledger:
    """An in-memory payments ledger keyed by `account_id`."""

    def __init__(self) -> None:
        """Initialise an empty ledger."""
        self._accounts: dict[str, _Account] = {}
        self._journal: dict[str, list[tuple[int, int]]] = {}
        self._pending: List[_Payment] = []
        self._by_payment_id: dict[str, _Payment] = {}
        self._payment_seq = 0

    def _set_balance(self, account, timestamp, balance):
        account.balance = balance
        self._journal.setdefault(account.account_id, []).append((timestamp, balance))

    def _process_due(self, timestamp: int):
        while self._pending and self._pending[0].execute_at <= timestamp:
            payment = self._pending.pop(0)
            del self._by_payment_id[payment.payment_id]
            account = self._accounts.get(payment.account_id)
            if account is None or account.balance < payment.amount:
                continue
            self._set_balance(account, payment.execute_at, account.balance - payment.amount)
            account.outgoing += payment.amount

    def create_account(self, timestamp: int, account_id: str) -> bool:
        """Open `account_id` with a zero balance; False if that id is taken."""
        self._process_due(timestamp)
        if account_id in self._accounts:
            return False
        account = _Account(account_id)
        self._accounts[account_id] = account
        self._set_balance(account, timestamp, 0)
        return True

    def deposit(self, timestamp: int, account_id: str, amount: int) -> Optional[int]:
        """Credit `amount` to `account_id` and return its new balance."""
        self._process_due(timestamp)
        account = self._accounts.get(account_id)
        if account is None:
            return None
        self._set_balance(account, timestamp, account.balance + amount)
        return account.balance

    def transfer(
            self, timestamp: int, source_id: str, target_id: str, amount: int
    ) -> Optional[int]:
        """Move `amount` from `source_id` to `target_id`; returns the new source balance."""
        self._process_due(timestamp)
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
        self._process_due(timestamp)
        if n <= 0:
            return ''
        ranked = sorted(self._accounts.values(), key=lambda account: (-account.outgoing, account.account_id))
        return ', '.join(f"{a.account_id}({a.outgoing})" for a in ranked[:n])

    def schedule_payment(self, timestamp, account_id, amount, delay):
        self._process_due(timestamp)
        if account_id not in self._accounts:
            return None
        self._payment_seq += 1
        payment = _Payment(
            payment_id=f"payment{self._payment_seq}",
            account_id=account_id,
            amount=amount,
            execute_at=timestamp+delay,
            seq=self._payment_seq
        )
        bisect.insort(self._pending, payment, key=lambda item: (item.execute_at, item.seq))
        self._by_payment_id[payment.payment_id] = payment
        return payment.payment_id

    def cancel_payment(self, timestamp, account_id, payment_id):
        self._process_due(timestamp)
        payment = self._by_payment_id.get(payment_id)
        if payment is None or payment.account_id != account_id:
            return False
        del self._by_payment_id[payment_id]
        self._pending.remove(payment)
        return True
