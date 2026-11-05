"""Proposed policy: urgency-seeded insertion with an adaptive wait rule (#8 + adaptive #7).

Course content used (IS115):
  * Hash maps (Week 7): parcels grouped by location, credit-at-risk totals per
    location, and waiting load per location for the time-based backlog check,
    all Python dicts with O(1) average insert/lookup.
  * Heap-based priority queue (Week 7): helpers.HeapPriorityQueue, built
    bottom-up in O(L), ranks locations by credit at risk; remove_min pops the
    best seed and, if it cannot be reached and back by 18:00, the next one.
  * Uniform Cost Search (Week 10): helpers.ucs_shortest_tour searches the
    state space of visiting orders for the trip's stops; the shortest order is
    adopted only if no parcel on the trip loses predicted credit.
  * Greedy Algorithm 2 for TSP (Week 11 Part 2a, insertion): the trip is
    built by the shared insertion engine, one locally best stop at a time.
  * Exhaustive search vs heuristics (Week 11 Part 1, "fast, general, optimal:
    pick any two") and intractability (Week 13): UCS is an exact search with
    exponential cost O(m^3 * 2^m), so it is used only for trips of at most
    MAX_UCS_STOPS stops; larger trips keep the greedy order. Every other step
    is polynomial.

One dispatch call:
  1. Estimate how long a parcel would wait if this van did not take it.
  2. Seed the trip at the reachable location with the most credit at risk (heap).
  3. Build the rest of the trip by best predicted credit per extra km (shared
     engine helpers.build_insertion_route), with free top-up and backlog fallback.
  4. Re-order the trip's stops by UCS if that shortens it without losing credit.
  5. Adaptive wait: hold the van for one round (return []) only if the trip is
     light, nothing on it would lose credit by waiting, it is not late in the
     day, the fleet has enough driving time left before the cutoff for the
     parcels waiting (time-based backlog), and the vans idle at the hub could
     carry everything waiting (capacity-based backlog).

Why the time-based backlog check: vans run out of driving time, not space
(trips use most of the 320 km range while about half full). Without it,
light trips kept being held in the afternoon until too little fleet time was
left, stranding parcels that arrived after 15:00. The check estimates the
driving time the waiting parcels need (a round trip from the hub per
vanload per location, an over-estimate since one trip can serve several
locations) and refuses to hold if TIME_BACKLOG_FACTOR times that exceeds the
fleet's remaining minutes before the cutoff.

Complexity per call (n available parcels, L locations, m stops, k parcels on
the trip, V vehicles):
  1. O(V)   2. O(n) hash-map totals + O(L) heap build + O(log L) per pop
  3. O(m^2 * (L*k + n))   4. O(m^3 * 2^m) for m <= MAX_UCS_STOPS, else skipped
  5. O(k + n + V) (hold tests, incl. O(n + L + V) time-based backlog).
  Space O(n + L + k + m * 2^m).

Measured on the 20 historical days (results/heuristic_best; ablation in
scripts/ablation_heuristic_best.py and results/ablation_heuristic_best.json):
  * mean service score 0.9559 (worst day 0.942); beats every other policy on
    every one of the 20 days, including #8 + #7 (0.9471);
  * the time-based backlog check changes 126 decisions and is worth +0.0086
    (0.9473 without it): delivery rate rises from 95.4% to 96.2% at the cost
    of more trips (632 vs 556) and more km per delivered parcel (4.87 vs 4.51);
  * UCS re-orders 41 of 632 trips, saving 166.6 km in total (about 4 km per
    re-ordered trip) with no change in score: the minutes saved never let a
    van take different parcels;
  * the heap fallback changes 4 late-day seeds, worth +0.00006.
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
TIME_BACKLOG_FACTOR = 2.0   # Safety factor on estimated driving time needed by waiting parcels
USE_UCS_ORDERING = True     # Switches for the ablation study (scripts/ablation_heuristic_best.py)
USE_HEAP_SEED_FALLBACK = True
USE_TIME_BACKLOG = True


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
    if USE_TIME_BACKLOG:
        # Time-based backlog: hash map of waiting load per location; each location
        # needs one hub round trip per (started) vanload.
        waiting_load_at: Dict[str, float] = {}
        for parcel_id in waiting_ids:
            location = parcel[parcel_id]["delivery_location_id"]
            waiting_load_at[location] = waiting_load_at.get(location, 0.0) + parcel[parcel_id]["size"]
        minutes_needed = math.fsum(
            (dist[HUB][location] + dist[location][HUB]) * MINUTES_PER_KM * math.ceil(load / capacity - TOLERANCE)
            for location, load in waiting_load_at.items())
        minutes_left = math.fsum(
            max(0.0, context["return_cutoff"] - max(now, v["available_at"]) - context["departure_delay"])
            for v in context["fleet"].values())
        if TIME_BACKLOG_FACTOR * minutes_needed > minutes_left:
            return route                                # fleet time is short: waiting would strand parcels
    idle_vans = sum(1 for v in context["fleet"].values() if v["available_at"] <= now)
    waiting_load = sum(parcel[pid]["size"] for pid in waiting_ids)
    if waiting_load > idle_vans * capacity:
        return route                                    # backlog: waiting would strand parcels
    return []                                           # light, nothing urgent, spare capacity: wait
