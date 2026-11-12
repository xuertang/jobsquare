"""Reference solution for ICF Mock 4: Ledger.

KEY DESIGN DECISIONS -- the two choices that make Levels 3 and 4 cheap
----------------------------------------------------------------------
**1. Every account keeps a time-ordered `(timestamp, balance)` log from
Level 1 onwards, and the log is the source of truth for the past.** The
naive model -- `dict[str, int]` of current balances -- answers Levels 1 and
2 perfectly and then dies at Level 4, because `get_balance(t, id, time_at)`
asks a question the model has already thrown away the answer to. Recovering
it late means retrofitting a log through every mutator under time pressure.
Keeping the log from the start costs one `_record()` call per balance change
and turns Level 4's historical read into `bisect` over that list. It also
solves "the account was merged away" for free: a merge appends a *tombstone*
entry `(timestamp, None)` rather than deleting history, so a read before the
merge still resolves and a read at or after it returns `None` -- no special
case, just the same binary search.

**2. Exactly one private `_process_due(timestamp)`, called as the first
statement of every public method.** Level 3 says pending payments fire "at
the start of every operation". Written literally that is eleven copies of the
same loop, eleven chances to forget one (`cancel_payment` and `get_balance`
are the ones people miss), and eleven places to edit when Level 4 changes who
a payment is billed to. Funnelled through one helper, the execution semantics
-- due order `(execute_at, seq)`, deduct-or-discard, credit the outgoing
total only on success -- live in six lines that Level 4 does not touch.

Level 2 is the early warning for decision 1's sibling: `transfer` accumulates
`account.outgoing` as it goes, so `top_spenders` is a sort, not a re-scan of
history. Level 3 then reuses that same field for executed payments, and
Level 4's merge just adds two integers.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from typing import Optional


@dataclass
class _Account:
    """Current state of one account. History lives in `Ledger._history`."""

    account_id: str
    balance: int = 0
    #: Total amount ever sent out: transfers plus successfully executed payments.
    outgoing: int = 0


@dataclass
class _Payment:
    """A scheduled outgoing payment; `account_id` is rebound by a merge."""

    payment_id: str
    account_id: str
    amount: int
    execute_at: int
    seq: int


class Ledger:
    """An in-memory payments ledger with scheduling, merges and history."""

    def __init__(self) -> None:
        # Live accounts only. A merged-away account is removed from here but
        # keeps its history below.
        self._accounts: dict[str, _Account] = {}
        # account_id -> non-decreasing [(timestamp, balance)] where a balance of
        # None is a tombstone meaning "the account did not exist from here on".
        self._history: dict[str, list[tuple[int, Optional[int]]]] = {}
        # Pending payments, kept sorted by (execute_at, seq).
        self._pending: list[_Payment] = []
        self._by_payment_id: dict[str, _Payment] = {}
        self._payment_seq: int = 0

    # ------------------------------------------------------------------
    # Internal primitives
    # ------------------------------------------------------------------

    def _record(
        self, account_id: str, timestamp: int, balance: Optional[int]
    ) -> None:
        """Append one point to an account's balance history."""
        self._history.setdefault(account_id, []).append((timestamp, balance))

    def _process_due(self, timestamp: int) -> None:
        """Execute every pending payment scheduled at or before `timestamp`.

        Called first thing by every public method. Payments run in scheduled
        order, then creation order. A payment whose owner cannot cover it is
        discarded with no effect -- it never reaches the outgoing total.
        """
        while self._pending and self._pending[0].execute_at <= timestamp:
            payment = self._pending.pop(0)
            del self._by_payment_id[payment.payment_id]
            account = self._accounts.get(payment.account_id)
            if account is None or account.balance < payment.amount:
                continue
            account.balance -= payment.amount
            account.outgoing += payment.amount
            # The money moves at the scheduled instant, not at the instant the
            # operation that happened to trigger processing. Because due
            # payments are drained before every operation, `execute_at` is
            # never earlier than the last point already in the log.
            self._record(account.account_id, payment.execute_at, account.balance)

    # ------------------------------------------------------------------
    # Level 1 -- core operations
    # ------------------------------------------------------------------

    def create_account(self, timestamp: int, account_id: str) -> bool:
        """Open `account_id` with a zero balance; False if it already exists."""
        self._process_due(timestamp)
        if account_id in self._accounts:
            return False
        self._accounts[account_id] = _Account(account_id)
        self._record(account_id, timestamp, 0)
        return True

    def deposit(self, timestamp: int, account_id: str, amount: int) -> Optional[int]:
        """Credit `amount` and return the new balance; None if no such account."""
        self._process_due(timestamp)
        account = self._accounts.get(account_id)
        if account is None:
            return None
        account.balance += amount
        self._record(account_id, timestamp, account.balance)
        return account.balance

    def transfer(
        self, timestamp: int, source_id: str, target_id: str, amount: int
    ) -> Optional[int]:
        """Move `amount` between accounts, returning the source's new balance."""
        self._process_due(timestamp)
        if source_id == target_id:
            return None
        source = self._accounts.get(source_id)
        target = self._accounts.get(target_id)
        if source is None or target is None or source.balance < amount:
            return None
        source.balance -= amount
        target.balance += amount
        source.outgoing += amount
        self._record(source_id, timestamp, source.balance)
        self._record(target_id, timestamp, target.balance)
        return source.balance

    # ------------------------------------------------------------------
    # Level 2 -- aggregation
    # ------------------------------------------------------------------

    def top_spenders(self, timestamp: int, n: int) -> str:
        """The `n` accounts with the largest outgoing totals, as `id(amt), ...`."""
        self._process_due(timestamp)
        if n <= 0:
            return ""
        ranked = sorted(
            self._accounts.values(),
            key=lambda account: (-account.outgoing, account.account_id),
        )
        return ", ".join(
            f"{account.account_id}({account.outgoing})" for account in ranked[:n]
        )

    # ------------------------------------------------------------------
    # Level 3 -- scheduled payments
    # ------------------------------------------------------------------

    def schedule_payment(
        self, timestamp: int, account_id: str, amount: int, delay: int
    ) -> Optional[str]:
        """Register an outgoing payment for `timestamp + delay`; returns its id."""
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

    def cancel_payment(
        self, timestamp: int, account_id: str, payment_id: str
    ) -> bool:
        """Cancel a still-pending payment owned by `account_id`."""
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
        """Absorb `id_2` into `id_1`: balance, outgoing total and pending payments."""
        self._process_due(timestamp)
        if id_1 == id_2:
            return False
        survivor = self._accounts.get(id_1)
        absorbed = self._accounts.get(id_2)
        if survivor is None or absorbed is None:
            return False
        survivor.balance += absorbed.balance
        survivor.outgoing += absorbed.outgoing
        for payment in self._pending:
            if payment.account_id == id_2:
                payment.account_id = id_1
        del self._accounts[id_2]
        self._record(id_1, timestamp, survivor.balance)
        self._record(id_2, timestamp, None)  # tombstone: id_2 stops existing here
        return True

    def get_balance(
        self, timestamp: int, account_id: str, time_at: int
    ) -> Optional[int]:
        """The balance `account_id` held at `time_at`, or None if it had none."""
        self._process_due(timestamp)
        history = self._history.get(account_id)
        if not history:
            return None
        index = bisect.bisect_right(history, time_at, key=lambda point: point[0])
        if index == 0:
            return None  # the account did not exist yet at `time_at`
        return history[index - 1][1]  # None here means "merged away by then"
