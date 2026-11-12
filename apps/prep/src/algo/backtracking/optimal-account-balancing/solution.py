from typing import List
import collections
import itertools
from functools import lru_cache
import math

def minTransfers(transactions: List[List[int]]) -> int:
    """O(n * 3^n) time, O(3^n) space, n = people with a nonzero net balance.
    """
    balances = collections.defaultdict(int)
    tuplify = lambda balance: tuple(sorted((k, v) for k, v in balance.items()))

    @lru_cache(None)
    def dfs(balances):
        if not balances:
            return 0
        res = math.inf
        balances = {k: v for k, v in balances}

        for size in range(2, len(balances) + 1):
            for group in itertools.combinations(balances.keys(), size):
                if sum(balances[k] for k in group) == 0:
                    remaining_balances = {k: v for k, v in balances.items() if k not in group}
                    res = min(res, size - 1 + dfs(tuplify(remaining_balances)))
        return res
    
    for u, v, z in transactions:
        balances[u] -= z
        balances[v] += z
    return dfs(tuplify({k : v for k, v in balances.items() if v}))

def minTransfersBitmask(transactions: List[int]) -> int:
    """O(n * 2^n) time, O(2^n) space, n = people with a nonzero net balance.

    Settling a zero-sum group of size k always costs k - 1 transfers, so the
    total cost is n - (number of groups). Maximize the groups instead.
    """
    balances = collections.defaultdict(int)
    for u, v, z in transactions:
        balances[u] -= z
        balances[v] += z
    debt = [v for v in balances.values() if v]
    n = len(debt)
    if n == 0:
        return 0

    full = 1 << n
    # total[mask] = net balance of the people in mask
    total = [0] * full
    for mask in range(1, full):
        low = (mask & -mask).bit_length() - 1
        total[mask] = total[mask ^ (1 << low)] + debt[low]

    # dp[mask] = max number of disjoint zero-sum groups carved out of mask
    # (leftovers allowed). Dropping any one person can cost at most one group,
    # and if mask itself sums to zero its leftovers form one more group.
    dp = [0] * full
    for mask in range(1, full):
        best = 0
        for i in range(n):
            if mask >> i & 1:
                best = max(best, dp[mask ^ (1 << i)])
        dp[mask] = best + 1 if total[mask] == 0 else best

    return n - dp[full - 1]

transactions = [[0,1,10],[2,0,5]]
print(minTransfers(transactions), minTransfersBitmask(transactions))
transactions1 = [[0,1,10],[1,0,1],[1,2,5],[2,0,5]]
print(minTransfers(transactions1), minTransfersBitmask(transactions1))