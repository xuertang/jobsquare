"""Level 1 snapshot -- accounts, deposits and transfers, and nothing else.

This is what the class looked like at the ten-minute mark, before Level 2 had
been read. It can open an account, add money to one, and move money between
two. It has no ranking, no future-dated work, no way to combine two accounts
and no reader: Levels 1 to 3 expose no way to look a balance up, so `deposit`
returning the new total is the only observation point there is.

One decision in this file looks like foresight and is not, so it is worth
arguing for explicitly:

**Every balance change is appended to a per-account, time-ordered
`(timestamp, balance)` journal, and `_set_balance` is the single place a
balance is allowed to change.**

The justification is the noun in the problem statement, not knowledge of what
Level 4 will ask. A ledger *is* a record of transactions -- that is what the
word means in the domain it comes from. A book that holds only the current
figure and discards the entries that produced it is not a ledger; it is a
balance sheet. So an append-only journal is not a bet on a future requirement,
it is the shape of the thing named in the title. The spec reinforces it from
two directions before Level 2 is even visible: every single method is handed
`timestamp` as its first argument, which is only worth doing to a system that
means to remember when things happened, and timestamps are promised
non-decreasing, which is the promise you need for an append-only log to stay
sorted without ever sorting it.

Contrast that with Mock 1 in this kit, whose noun was "content store". Nothing
in the words "content store" implies retention of superseded versions -- a
store holds what is in it now -- so a Level 1 version log there would have been
genuine speculation about an unseen Level 4, and the discipline was to store
exactly one current record per id and let Level 4 charge for the change. The
distinction is not "keep history when in doubt". It is: read the noun, take
whatever structure it already gives you for free, and guess at nothing beyond
it.

The journal is kept beside the live accounts rather than inside them, which is
also just the domain's own layout: the journal is the record of what happened,
the chart of accounts is the live index over it. `_Account.balance` is a
running total denormalised out of the journal so that the hot path stays O(1),
exactly as a real ledger keeps a balance column on every line.

What this file deliberately does not have is any per-call preamble, any notion
of work that fires later, or any counter beyond the balance itself. Level 1
asks for three operations and it gets three operations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class _Account:
    """A live account: its id and its current balance."""

    account_id: str
    balance: int = 0


class Ledger:
    """An in-memory ledger: accounts, deposits and transfers."""

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
        transfer leaves both balances -- and both journals -- untouched.
        """
        if source_id == target_id:
            return None
        source = self._accounts.get(source_id)
        target = self._accounts.get(target_id)
        if source is None or target is None or source.balance < amount:
            return None
        self._set_balance(source, timestamp, source.balance - amount)
        self._set_balance(target, timestamp, target.balance + amount)
        return source.balance
