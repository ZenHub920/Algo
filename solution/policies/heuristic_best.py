"""Proposed policy: urgency-seeded insertion with an adaptive wait rule (#8 + adaptive #7).

Course content used (IS115):
  * Hash maps (Week 7): parcels grouped by location and credit-at-risk totals
    per location, both Python dicts with O(1) average insert/lookup.
  * Heap-based priority queue (Week 7): helpers.HeapPriorityQueue, built
    bottom-up in O(L), ranks locations by credit at risk; remove_min pops the
    best seed and, if it cannot be reached and back by 18:00, the next one.
  * Uniform Cost Search (Week 10): helpers.ucs_shortest_tour searches the
    state space of visiting orders for the trip's stops; the shortest order is
    adopted only if no parcel on the trip loses predicted credit.

One dispatch call:
  1. Estimate how long a parcel would wait if this van did not take it.
  2. Seed the trip at the reachable location with the most credit at risk (heap).
  3. Build the rest of the trip by best predicted credit per extra km (shared
     engine helpers.build_insertion_route), with free top-up and backlog fallback.
  4. Re-order the trip's stops by UCS if that shortens it without losing credit.
  5. Adaptive wait: hold the van for one round (return []) only if the trip is
     light, nothing on it would lose credit by waiting, it is not late in the
     day, and the vans idle at the hub could carry everything waiting.

Complexity per call (n available parcels, L locations, m stops, k parcels on
the trip, V vehicles):
  1. O(V)   2. O(n) hash-map totals + O(L) heap build + O(log L) per pop
  3. O(m^2 * (L*k + n))   4. O(m^3 * 2^m) for m <= MAX_UCS_STOPS, else skipped
  5. O(k + n + V).   Space O(n + L + k + m * 2^m).

Measured on the 20 historical days (results/heuristic_best, scripts/ablation_heuristic_best.py):
  * mean service score 0.9473 (worst day 0.933); beats every other policy on
    each day except #8 + #7 (4 days better, 4 worse, 12 equal);
  * UCS re-orders 41 of 556 trips, saving 166.5 km in total (about 4 km per
    re-ordered trip) with no change in score: the minutes saved never let a
    van take different parcels;
  * the heap fallback changes 11 late-day seeds, also with no change in score;
  * differences from #8 + #7 come from the seed tie-break (heap pops the
    alphabetically first of equally at-risk locations), worth +0.0002 overall.
"""

import math
from typing import Dict, List

from simulator.models import Parcel, SimulationContext
from solution.policies.helpers import (
    HUB, MINUTES_PER_KM, TOLERANCE, HeapPriorityQueue, available_parcel_ids,
    build_insertion_route, delivery_times, departure_time, route_credit, route_distance,
    route_load, service_credit, ucs_shortest_tour,
)

PLANNING_INTERVAL = 10.0    # Planning rounds every 10 minutes (fixed by the brief)
EXTRA_WAIT = 30.0           # Minutes added to the wait estimate for the next van's own detour
HOLD_LOAD_FRACTION = 0.7    # Only hold trips filled below 70% of capacity
LAST_HOLD_MARGIN = 80.0     # Never hold within 80 minutes of the return cutoff (16:40 for 18:00)
MAX_UCS_STOPS = 7           # UCS is exponential in stops; larger trips keep the insertion order
USE_UCS_ORDERING = True     # Switches for the ablation study (scripts/ablation_heuristic_best.py)
USE_HEAP_SEED_FALLBACK = True


def dispatch(parcel: Dict[str, Parcel], context: SimulationContext) -> List[str]:
    """Return parcel IDs in delivery order for context["vehicle_id"], or [] to wait."""

    now = context["current_time"]
    dist = context["travel_distance"]
    capacity = context["capacity"]
    depart = departure_time(context)
    waiting_ids = available_parcel_ids(parcel)

    def credit(parcel_id: str, arrival: float) -> float:
        return service_credit(arrival, parcel[parcel_id]["delivery_window_end"])

    # 1. How long would a parcel wait for another van? Next planning round at which
    #    another vehicle is ready, plus that van's own detour.
    others = [v["available_at"] for vid, v in context["fleet"].items() if vid != context["vehicle_id"]]
    next_free = min(others) if others else now + PLANNING_INTERVAL
    next_round = max(now + PLANNING_INTERVAL,
                     math.ceil(next_free / PLANNING_INTERVAL) * PLANNING_INTERVAL)
    wait = next_round - now + EXTRA_WAIT

    # 2. Seed. Hash map: credit at risk per location. Heap: pop the location with the
    #    most at risk (keys negated for a max-first order), skipping any that cannot
    #    be reached and returned from by the cutoff.
    at_risk: Dict[str, float] = {}
    for parcel_id in waiting_ids:
        location = parcel[parcel_id]["delivery_location_id"]
        arrive = depart + dist[HUB][location] * MINUTES_PER_KM
        lost = credit(parcel_id, arrive) - credit(parcel_id, arrive + wait)
        if lost > 0:
            at_risk[location] = at_risk.get(location, 0.0) + lost
    ranking = HeapPriorityQueue([((-risk, location), location) for location, risk in at_risk.items()])
    seed = None
    while not ranking.is_empty():
        _, location = ranking.remove_min()
        round_km = dist[HUB][location] + dist[location][HUB]
        if (round_km <= context["max_trip_distance_km"] + TOLERANCE
                and depart + round_km * MINUTES_PER_KM <= context["return_cutoff"]):
            seed = location
            break
        if not USE_HEAP_SEED_FALLBACK:
            break

    # 3. Build the trip: seed first, then best credit per extra km (shared engine).
    route = build_insertion_route(parcel, context, credit, seed_location=seed)
    if not route:
        return []

    # 4. UCS re-ordering: shortest visiting order of the trip's stops, kept only if
    #    it is strictly shorter and no predicted credit is lost.
    stops: List[str] = []
    by_stop: Dict[str, List[str]] = {}
    for parcel_id in route:
        location = parcel[parcel_id]["delivery_location_id"]
        if location not in by_stop:
            stops.append(location)
            by_stop[location] = []
        by_stop[location].append(parcel_id)
    if USE_UCS_ORDERING and 2 <= len(stops) <= MAX_UCS_STOPS:
        tour = ucs_shortest_tour(stops, dist)
        if tour is not None and tour != stops:
            candidate = [pid for location in tour for pid in by_stop[location]]
            if (route_distance(candidate, parcel, dist) < route_distance(route, parcel, dist) - TOLERANCE
                    and route_credit(candidate, parcel, context) >= route_credit(route, parcel, context) - TOLERANCE):
                route = candidate

    # 5. Adaptive wait rule: go now unless every hold condition is met.
    if now >= context["return_cutoff"] - LAST_HOLD_MARGIN:
        return route                                    # late in the day: always go
    if route_load(route, parcel) >= HOLD_LOAD_FRACTION * capacity:
        return route                                    # full enough
    for parcel_id, time in zip(route, delivery_times(route, parcel, context)):
        if credit(parcel_id, time) > credit(parcel_id, time + PLANNING_INTERVAL):
            return route                                # something on board would lose credit
    idle_vans = sum(1 for v in context["fleet"].values() if v["available_at"] <= now)
    waiting_load = sum(parcel[pid]["size"] for pid in waiting_ids)
    if waiting_load > idle_vans * capacity:
        return route                                    # backlog: waiting would strand parcels
    return []                                           # light, nothing urgent, spare capacity: wait
