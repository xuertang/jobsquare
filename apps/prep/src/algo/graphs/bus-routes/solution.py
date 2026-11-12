"""Bus Routes — O(?) time, O(?) space."""

from typing import List

def solve(routes: List[List[int]], source: int, target: int) -> int:
    if source == target:
        return 0
    
    max_stop = max(max(route) for route in routes)

    if max_stop < target or max_stop < source:
        return -1
    
    n = len(routes)
    min_buses = [float('inf')] * (max_stop + 1)
    min_buses[source] = 0

    flag = True
    while flag:
        flag = False
        for route in routes:
            mini = float('inf')
            for stop in route:
                mini = min(mini, min_buses[stop])
            mini += 1
            for stop in route:
                if min_buses[stop] > mini:
                    min_buses[stop] = mini
                    flag = True
    return min_buses[target] if min_buses[target] < float('inf') else -1


if __name__ == "__main__":
    print(solve([[1,2,7],[3,6,7]], 1, 6)) #2
    print(solve([[7,12],[4,5,15],[6],[15,19],[9,12,13]], 15, 12)) #-1
