"""Level 3 snapshot -- payments that fire later, and can be cancelled first.

Level 3 adds two public methods and one sentence that costs more than both of
them: *at the start of every operation -- every public method, mutator or
reader, from every level -- execute all pending payments whose scheduled time
is at or before `timestamp`.*

Written literally, that sentence is the same loop pasted into six methods, six
chances to forget one, and six places to edit when the rules change. Written
once, it is `_process_due(timestamp)`, and it is the first statement of every
public method in this file -- all six of them: `create_account`, `deposit`,
`transfer`, `top_spenders`, `schedule_payment` and `cancel_payment`.

The two that are easy to forget are the two that do not feel like money moving.
`top_spenders` is a reader, and readers feel exempt; they are not, and a
forgotten funnel there reports a stale ranking. `cancel_payment` is worse,
because forgetting it produces a wrong answer that looks right: the spec says
cancelling at or after a payment's scheduled time must return False, and the
only reason it does is that the payment was already drained by the funnel at
the top of that very call. Skip the funnel there and `cancel_payment` happily
cancels a payment that has, by the clock, already gone out -- and the test that
catches it is a single line in one worked example.

Three details of the execution rule are worth keeping in one place, which is
the other half of the argument for a single helper: due order is
`(execute_at, seq)`, so same-instant payments run in creation order and the
first can drain the balance out from under the second; a payment that cannot be
covered is discarded outright, with no deduction, no credit to the outgoing
total and no retry; and a payment never reserves anything, so the balance is
consulted only at execution time.

The Level 1 and 2 model absorbs this without changing shape. Executed payments
spend money exactly the way a transfer does, so they go through the same
`_set_balance` chokepoint and the same `outgoing` counter that Level 2 already
installed -- which is why `top_spenders` needs no clause about payments. The
one deliberate subtlety is *when* the journal entry is stamped: a payment is
recorded at its own `execute_at`, not at the timestamp of the operation that
happened to notice it was due. Draining before every operation is what keeps
that stamp from ever landing behind an entry already in the journal.
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
    """A registered outgoing payment waiting for its scheduled instant."""

    payment_id: str
    account_id: str
    amount: int
    execute_at: int
    seq: int


class Ledger:
    """An in-memory ledger: accounts, transfers, ranking and scheduled payments."""

    def __init__(self) -> None:
        """Initialise an empty ledger."""
        #: Live accounts, keyed by id.
        self._accounts: dict[str, _Account] = {}
        #: The record of what happened: account_id -> ascending
        #: [(timestamp, balance)], one entry per balance change.
        self._journal: dict[str, list[tuple[int, int]]] = {}
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
        journalled at the payment's own `execute_at`, not at `timestamp`.
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
        the time the lookup runs, the payment is gone.
        """
        self._process_due(timestamp)
        payment = self._by_payment_id.get(payment_id)
        if payment is None or payment.account_id != account_id:
            return False
        del self._by_payment_id[payment_id]
        self._pending.remove(payment)
        return True
