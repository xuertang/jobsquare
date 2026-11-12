"""Level 4 snapshot -- merging two accounts, and reading the past.

This is the level that decides whether Level 1 was right. `get_balance(t, id,
time_at)` asks what an account held at an instant that has already gone by. A
ledger that stored only current balances cannot answer it, and cannot be made
to answer it except by retrofitting a journal through `deposit`, `transfer`,
the payment executor and the merge -- with half an hour left on the clock.

This ledger has kept that journal since Level 1, because a ledger is a record
of transactions and that is what the word means. So the entire historical read
is a binary search:

    index = bisect.bisect_right(entries, time_at, key=...)

Eight lines including the funnel call, the empty-journal guard and the
"nothing recorded yet at `time_at`" guard. Nothing had to be reconstructed,
because nothing had been thrown away.

The merge is the interesting half. Three things move from `id_2` to `id_1` --
balance, outgoing total, and pending payments -- and only the third needs any
thought. A payment is billed to whoever owns it *at execution time*, so the
merge rebinds `payment.account_id` in place and `_process_due` needs no change
whatsoever: it already looks the owner up at the moment it fires rather than
capturing an account object at scheduling time. That is the second dividend of
Level 3's single funnel. An inherited payment can now succeed where it would
have failed alone, because it is drawing on the survivor's balance, and
`cancel_payment` follows ownership for free -- `id_1` can cancel it, `id_2`
cannot, because `id_2` is no longer an account.

What the merge must not do is delete `id_2`'s history. It appends a
**tombstone**: `(timestamp, None)`, meaning "from here on, this account did not
exist". A historical read before the merge lands on a real entry and resolves
normally; a read at or after it lands on the tombstone and returns None; a read
before the account was ever created falls off the front of the journal and also
returns None. All three cases are the same binary search with no special
handling, and re-creating the freed id later simply appends a fourth era to the
same journal -- which is why `_set_balance` uses `setdefault` rather than
assuming a fresh list.

The tombstone append inside `merge_accounts` is the one place in this file that
writes to `self._journal` without going through `_set_balance`, and that is
deliberate rather than sloppy: it is not a balance change, it is the end of an
account, and it is the only such event in the spec. Everything else still funnels.

Two files' worth of design, restated: every public method still starts with
`_process_due(timestamp)` -- eight of them now -- and every balance change
still goes through `_set_balance`. The only carried-over code this level had to
touch is the journal's type annotation, which now admits None.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from typing import Optional


@dataclass
class _Account:
    """A live account: its id, its current balance, and what it has sent out."""

    account_id: str
    balance: int = 0
    #: Total ever sent out: transfers plus successfully executed payments.
    outgoing: int = 0


@dataclass
class _Payment:
    """A registered outgoing payment; `account_id` is rebound by a merge."""

    payment_id: str
    account_id: str
    amount: int
    execute_at: int
    seq: int


class Ledger:
    """An in-memory ledger with ranking, scheduled payments, merges and history."""

    def __init__(self) -> None:
        """Initialise an empty ledger."""
        #: Live accounts, keyed by id. A merged-away account is removed from
        #: here but keeps its journal below.
        self._accounts: dict[str, _Account] = {}
        #: The record of what happened: account_id -> ascending
        #: [(timestamp, balance)], one entry per balance change, where a
        #: balance of None is a tombstone meaning "gone from here on".
        self._journal: dict[str, list[tuple[int, Optional[int]]]] = {}
        #: Payments not yet executed or cancelled, sorted by (execute_at, seq).
        self._pending: list[_Payment] = []
        self._by_payment_id: dict[str, _Payment] = {}
        self._payment_seq: int = 0

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

    def _process_due(self, timestamp: int) -> None:
        """Execute every pending payment scheduled at or before `timestamp`.

        The first statement of every public method. Payments run in scheduled
        order and then creation order; one whose owner cannot cover it is
        discarded with no effect at all and never retried. The money is
        journalled at the payment's own `execute_at`, not at `timestamp`, and
        the owner is looked up when it fires -- so a merged payment bills the
        survivor without this loop knowing merges exist.
        """
        while self._pending and self._pending[0].execute_at <= timestamp:
            payment = self._pending.pop(0)
            del self._by_payment_id[payment.payment_id]
            account = self._accounts.get(payment.account_id)
            if account is None or account.balance < payment.amount:
                continue
            self._set_balance(
                account, payment.execute_at, account.balance - payment.amount
            )
            account.outgoing += payment.amount

    # ------------------------------------------------------------------
    # Level 1 -- core operations
    # ------------------------------------------------------------------

    def create_account(self, timestamp: int, account_id: str) -> bool:
        """Open `account_id` with a zero balance; False if it already exists."""
        self._process_due(timestamp)
        if account_id in self._accounts:
            return False
        account = _Account(account_id)
        self._accounts[account_id] = account
        self._set_balance(account, timestamp, 0)
        return True

    def deposit(self, timestamp: int, account_id: str, amount: int) -> Optional[int]:
        """Credit `amount` and return the new balance; None if no such account."""
        self._process_due(timestamp)
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

    # ------------------------------------------------------------------
    # Level 2 -- aggregation
    # ------------------------------------------------------------------

    def top_spenders(self, timestamp: int, n: int) -> str:
        """The `n` biggest senders as `id(amt), id(amt)`; "" if `n <= 0`.

        Every existing account is ranked, including those that have never sent
        anything -- they sort last under "outgoing descending, id ascending".
        A read drains due payments exactly as a write does.
        """
        self._process_due(timestamp)
        if n <= 0:
            return ""
        ranked = sorted(
            self._accounts.values(),
            key=lambda account: (-account.outgoing, account.account_id),
        )
        return ", ".join(f"{a.account_id}({a.outgoing})" for a in ranked[:n])

    # ------------------------------------------------------------------
    # Level 3 -- scheduled payments
    # ------------------------------------------------------------------

    def schedule_payment(
        self, timestamp: int, account_id: str, amount: int, delay: int
    ) -> Optional[str]:
        """Register an outgoing payment for `timestamp + delay`; returns its id.

        Nothing is deducted or reserved now. `delay = 0` means due immediately,
        which still means the *next* operation: this call drains what was due
        before it, not the payment it is about to create.
        """
        self._process_due(timestamp)
        if account_id not in self._accounts:
            return None
        self._payment_seq += 1
        payment = _Payment(
            payment_id=f"payment{self._payment_seq}",
            account_id=account_id,
            amount=amount,
            execute_at=timestamp + delay,
            seq=self._payment_seq,
        )
        bisect.insort(
            self._pending, payment, key=lambda item: (item.execute_at, item.seq)
        )
        self._by_payment_id[payment.payment_id] = payment
        return payment.payment_id

    def cancel_payment(self, timestamp: int, account_id: str, payment_id: str) -> bool:
        """Cancel a still-pending payment owned by `account_id`.

        False for an unknown id, one already executed or cancelled, or one
        owned by somebody else -- and in that last case the payment stays
        pending, because a stranger does not get to cancel it. The funnel above
        is what makes "cancel at or after the scheduled time" return False: by
        the time the lookup runs, the payment is gone. Ownership is whatever it
        is now, so a merge moves the right to cancel along with the payment.
        """
        self._process_due(timestamp)
        payment = self._by_payment_id.get(payment_id)
        if payment is None or payment.account_id != account_id:
            return False
        del self._by_payment_id[payment_id]
        self._pending.remove(payment)
        return True

    # ------------------------------------------------------------------
    # Level 4 -- merges and historical reads
    # ------------------------------------------------------------------

    def merge_accounts(self, timestamp: int, id_1: str, id_2: str) -> bool:
        """Absorb `id_2` into `id_1`: balance, outgoing total, pending payments.

        `id_1` survives and `id_2` stops existing at `timestamp`. False if
        either is missing or the two ids are equal, and then nothing moves.
        """
        self._process_due(timestamp)
        if id_1 == id_2:
            return False
        survivor = self._accounts.get(id_1)
        absorbed = self._accounts.get(id_2)
        if survivor is None or absorbed is None:
            return False
        survivor.outgoing += absorbed.outgoing
        for payment in self._pending:
            if payment.account_id == id_2:
                payment.account_id = id_1
        del self._accounts[id_2]
        self._set_balance(survivor, timestamp, survivor.balance + absorbed.balance)
        # Not a balance change but the end of an account: a tombstone, so that
        # reads before `timestamp` still resolve and reads after it do not.
        self._journal[id_2].append((timestamp, None))
        return True

    def get_balance(
        self, timestamp: int, account_id: str, time_at: int
    ) -> Optional[int]:
        """The balance `account_id` held at `time_at`, or None if it had none.

        `timestamp` is this call's clock; `time_at` is the instant being asked
        about. Effects stamped exactly `time_at` count.
        """
        self._process_due(timestamp)
        entries = self._journal.get(account_id)
        if not entries:
            return None
        index = bisect.bisect_right(entries, time_at, key=lambda entry: entry[0])
        if index == 0:
            return None  # nothing recorded yet: the account did not exist
        return entries[index - 1][1]  # None here means "merged away by then"
