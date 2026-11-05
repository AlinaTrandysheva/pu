"""Чистая функция: прямые маршруты и не более двух пересадок."""
from bisect import bisect_left, bisect_right
from collections import defaultdict
from datetime import timedelta
from heapq import heappush, heapreplace

def build_routes(flights, origin, destination, day):
    outgoing = defaultdict(list)
    for flight in flights:
        if flight.departure.date() == day:
            outgoing[flight.origin].append(flight)
    for group in outgoing.values():
        group.sort(key=lambda f: (f.departure, f.carrier, f.number))
    departures = {airport: [f.departure for f in group] for airport, group in outgoing.items()}
    best = []
    serial = 0

    def visit(airport, path, seen, cost):
        nonlocal serial
        if airport == destination:
            serial += 1
            entry = (-cost, -serial, tuple(path))
            if len(best) < 20:
                heappush(best, entry)
            elif entry[:2] > best[0][:2]:
                heapreplace(best, entry)
            return
        if len(path) == 3:
            return
        candidates = outgoing.get(airport, [])
        if path:
            times = departures.get(airport, [])
            low = bisect_left(times, path[-1].arrival + timedelta(hours=1))
            high = bisect_right(times, path[-1].arrival + timedelta(hours=6))
            candidates = candidates[low:high]
        for flight in candidates:
            if flight.destination in seen:
                continue
            new_cost = cost + flight.price
            if len(best) == 20 and new_cost > -best[0][0]:
                continue
            visit(flight.destination, path + [flight], seen | {flight.destination}, new_cost)

    visit(origin, [], {origin}, 0)
    return [{'price': -cost, 'flights': [f.json() for f in path]}
            for cost, index, path in sorted(best, key=lambda x: (-x[0], -x[1]))]
