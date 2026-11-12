import heapq
import bisect


class Account:
    def __init__(self, account_id, created_at):
        self.id = account_id
        self.created_at = created_at
        self.removed_at = None
        self.balance = 0
        self.outgoing = 0
        self.history = [(created_at, 0)]


class Payment:
    def __init__(self, pid, account_id, amount, executed_at, order):
        self.id = pid
        self.account_id = account_id
        self.amount = amount
        self.executed_at = executed_at
        self.order = order


class Ledger:
    def __init__(self):
        self.accounts = {}
        self.payments = {}
        self._heap = []
        self._counter = 0

    def _live(self, account_id):
        a = self.accounts.get(account_id)
        return a if a and a.removed_at is None else None

    def _record(self, acct, timestamp):
        if acct.history and acct.history[-1][0] == timestamp:
            acct.history[-1] = (timestamp, acct.balance)
        else:
            acct.history.append((timestamp, acct.balance))

    def _process_due(self, timestamp):
        while self._heap and self._heap[0][0] <= timestamp:
            execute_at, _, pid = heapq.heappop(self._heap)
            pay = self.payments.get(pid)
            if pay is None:
                continue
            del self.payments[pid]
            acct = self._live(pay.account_id)
            if acct is None:
                continue
            if acct.balance >= pay.amount:
                acct.balance -= pay.amount
                acct.outgoing += pay.amount
                self._record(acct, execute_at)

    def create_account(self, timestamp, account_id):
        self._process_due(timestamp)
        if account_id in self.accounts:  # merged-away ids stay reserved
            return False
        self.accounts[account_id] = Account(account_id, timestamp)
        return True

    def deposit(self, timestamp, account_id, amount):
        self._process_due(timestamp)
        acct = self._live(account_id)
        if acct is None:
            return None
        acct.balance += amount
        self._record(acct, timestamp)
        return acct.balance

    def transfer(self, timestamp, source_id, target_id, amount):
        self._process_due(timestamp)
        src, tgt = self._live(source_id), self._live(target_id)
        if src is None or tgt is None or source_id == target_id:
            return None
        if src.balance < amount:
            return None
        src.balance -= amount
        src.outgoing += amount
        tgt.balance += amount
        self._record(src, timestamp)
        self._record(tgt, timestamp)
        return src.balance

    def top_spenders(self, timestamp, n):
        self._process_due(timestamp)
        live = [a for a in self.accounts.values() if a.removed_at is None]
        live.sort(key=lambda a: (-a.outgoing, a.id))
        return ', '.join(f"{a.id}({a.outgoing})" for a in live[:n])

    def schedule_payment(self, timestamp, account_id, amount, delay):
        self._process_due(timestamp)
        if self._live(account_id) is None:
            return None
        self._counter += 1
        pid = f"payment{self._counter}"
        pay = Payment(pid, account_id, amount, timestamp + delay, self._counter)
        self.payments[pid] = pay
        heapq.heappush(self._heap, (pay.executed_at, pay.order, pid))
        return pid

    def cancel_payment(self, timestamp, account_id, payment_id):
        self._process_due(timestamp)
        if self._live(account_id) is None:
            return False
        pay = self.payments.get(payment_id)
        if pay is None or pay.account_id != account_id:
            return False
        del self.payments[payment_id]
        return True

    def merge_accounts(self, timestamp, id_1, id_2):
        self._process_due(timestamp)
        if id_1 == id_2:
            return False
        a1, a2 = self._live(id_1), self._live(id_2)
        if a1 is None or a2 is None:
            return False
        a1.balance += a2.balance
        a1.outgoing += a2.outgoing
        self._record(a1, timestamp)
        for pay in self.payments.values():  # reassign pending payments
            if pay.account_id == id_2:
                pay.account_id = id_1
        a2.removed_at = timestamp  # history stays frozen for lookups
        return True

    def get_balance(self, timestamp, account_id, time_at):
        self._process_due(timestamp)
        acct = self.accounts.get(account_id)  # incl. merged-away accounts
        if acct is None or time_at < acct.created_at:
            return None
        if acct.removed_at is not None and time_at >= acct.removed_at:
            return None
        idx = bisect.bisect_right(acct.history, (time_at, float("inf"))) - 1
        return acct.history[idx][1] if idx >= 0 else None


L = Ledger()
assert L.create_account(1, "a") is True
assert L.create_account(2, "b") is True
assert L.deposit(3, "a", 100) == 100
assert L.transfer(4, "a", "b", 30) == 70
assert L.transfer(5, "a", "b", 20) == 50
assert L.top_spenders(6, 3) == "a(50), b(0)"
assert L.schedule_payment(7, "b", 40, 10) == "payment1"  # fires at 17
assert L.deposit(18, "a", 0) == 50  # payment1 fires: b 50->10
assert L.top_spenders(19, 2) == "a(50), b(40)"  # b's payment counted
assert L.get_balance(20, "b", 3) == 0  # before any transfer in
assert L.get_balance(21, "b", 6) == 50  # before the payment
assert L.get_balance(22, "b", 18) == 10  # after the payment

assert L.create_account(25, "c") is True
assert L.deposit(26, "c", 100) == 100
assert L.schedule_payment(27, "c", 30, 100) == "payment2"  # fires at 127
assert L.merge_accounts(28, "a", "c") is True  # a absorbs c; payment2 -> a
assert L.cancel_payment(29, "a", "payment2") is True  # cancellable via new owner
print(L.get_balance(30, "c", 26))
assert L.get_balance(30, "c", 26) == 100  # frozen pre-merge history
assert L.get_balance(31, "c", 30) is None  # c gone after merge at 28
print("all passed")
