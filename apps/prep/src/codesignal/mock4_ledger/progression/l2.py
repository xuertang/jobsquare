"""Level 2 snapshot -- ranking accounts by how much they have sent out.

Level 2 asked one question: rank every existing account by its total outgoing
amount, sorted by total descending then id ascending, rendered as a single
`"id(amt), id(amt)"` string. It said nothing about storage.

**The fork this level presents, and which way this file took it.** Level 1's
journal records *balance*, not *direction*. It knows alice went from 300 to 200
at t=3; it does not know that the 100 went to bob rather than being burned.
Today that gap is closeable by arithmetic -- a transfer is the only thing in
the system that makes a balance go down, so the sum of the negative deltas in
an account's journal is exactly its outgoing total -- and a `top_spenders`
built that way would pass every test in this level. This file does not do that,
for two reasons. It is O(history) per query rather than O(accounts log
accounts), and, more seriously, it infers intent from arithmetic: it is right
only for as long as "balance went down" and "this account spent money" remain
the same statement. A ledger that later grows a second way to lose money, or
any way to acquire another account's totals, breaks the inference silently and
in a direction no test at this level would catch.

So the counter is added now, as a field, and `transfer` maintains it: exactly
one existing method body changes, by one line. `outgoing` is a fact about the
account that the spec has now named, and facts the spec names get stored rather
than re-derived. `top_spenders` is then a sort and a join.

Nothing else moved. `_Account` gained a field, `_set_balance` and the journal
are byte for byte what they were, and `create_account` and `deposit` are
untouched -- receiving money is not spending, so the credit side of the ledger
has no opinion about this level at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class _Account:
    """A live account: its id, its current balance, and what it has sent out."""

    account_id: str
    balance: int = 0
    #: Total amount ever sent out of this account by a successful transfer.
    outgoing: int = 0


class Ledger:
    """An in-memory ledger: accounts, deposits, transfers and spend ranking."""

    def __init__(self) -> None:
        """Initialise an empty ledger."""
        #: Live accounts, keyed by id.
        self._accounts: dict[str, _Account] = {}
        #: The record of what happened: account_id -> ascending
        #: [(timestamp, balance)], one entry per balance change.
        self._journal: dict[str, list[tuple[int, int]]] = {}

    # ------------------------------------------------------------------
    # Internal primitives
    # ------------------------------------------------------------------

    def _set_balance(self, account: _Account, timestamp: int, balance: int) -> None:
        """Move `account` to `balance` at `timestamp`, journalling the change.

        Single chokepoint for writes: no method assigns to `account.balance`
        directly, so "a balance change is a ledger entry" is enforced in one
        place rather than remembered in several. Timestamps arrive
        non-decreasing, so appending keeps each account's journal sorted.
        """
        account.balance = balance
        self._journal.setdefault(account.account_id, []).append((timestamp, balance))

    # ------------------------------------------------------------------
    # Level 1 -- core operations
    # ------------------------------------------------------------------

    def create_account(self, timestamp: int, account_id: str) -> bool:
        """Open `account_id` with a zero balance; False if it already exists."""
        if account_id in self._accounts:
            return False
        account = _Account(account_id)
        self._accounts[account_id] = account
        self._set_balance(account, timestamp, 0)
        return True

    def deposit(self, timestamp: int, account_id: str, amount: int) -> Optional[int]:
        """Credit `amount` and return the new balance; None if no such account."""
        account = self._accounts.get(account_id)
        if account is None:
            return None
        self._set_balance(account, timestamp, account.balance + amount)
        return account.balance

    def transfer(
        self, timestamp: int, source_id: str, target_id: str, amount: int
    ) -> Optional[int]:
        """Move `amount` between accounts, returning the source's new balance.

        Every failure condition is checked before anything moves, so a refused
        transfer leaves both balances -- and both journals -- untouched, and
        accrues nothing to the source's outgoing total.
        """
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

    # ------------------------------------------------------------------
    # Level 2 -- aggregation
    # ------------------------------------------------------------------

    def top_spenders(self, timestamp: int, n: int) -> str:
        """The `n` biggest senders as `id(amt), id(amt)`; "" if `n <= 0`.

        Every existing account is ranked, including those that have never sent
        anything -- they sort last under "outgoing descending, id ascending".
        """
        if n <= 0:
            return ""
        ranked = sorted(
            self._accounts.values(),
            key=lambda account: (-account.outgoing, account.account_id),
        )
        return ", ".join(f"{a.account_id}({a.outgoing})" for a in ranked[:n])
