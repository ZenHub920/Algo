"""Policy #3 - Location batching.

Idea: parcels going to the same location can share one stop, so a trip should
serve a few locations fully rather than many locations once each (the
baseline zigzags and runs out of range with the van half empty).

Each call:
  1. Group available parcels by delivery location.
  2. Seed: pick the location holding the most urgent parcel that can still earn
     credit if driven there directly now (earliest window end). If no parcel
     can still earn credit, pick the location with the most waiting load.
  3. Take that location's parcels (earliest window end first) while capacity allows.
  4. Extend to the nearest unvisited location from the current last stop
     (nearest neighbour) that still fits capacity, range and the 18:00
     return cutoff, and repeat until none does.
Always dispatches if any parcel fits (no waiting rule).

Complexity per call (n available parcels, L locations, m stops on the route):
  grouping and sorting O(n log n); seed choice O(n); extension O(m * L)
  nearest-neighbour scans; filling O(n). Overall O(n log n + m*L).
  Space O(n + L).
"""

from typing import Dict, List

from simulator.models import Parcel, SimulationContext
from solution.policies.helpers import (
    HUB, MINUTES_PER_KM, TOLERANCE, available_parcel_ids, departure_time, service_credit,
)


def dispatch(parcel: Dict[str, Parcel], context: SimulationContext) -> List[str]:
    """Return parcel IDs in delivery order for context["vehicle_id"], or [] to skip."""

    dist = context["travel_distance"]
    capacity = context["capacity"]
    max_km = context["max_trip_distance_km"]
    depart = departure_time(context)
    latest_return = context["return_cutoff"]

    # 1. Group by location, each group sorted by urgency (window end, then ID).
    groups: Dict[str, List[str]] = {}
    for parcel_id in available_parcel_ids(parcel):
        groups.setdefault(parcel[parcel_id]["delivery_location_id"], []).append(parcel_id)
    for ids in groups.values():
        ids.sort(key=lambda pid: (parcel[pid]["delivery_window_end"], pid))

    def round_trip_ok(location: str) -> bool:
        km = dist[HUB][location] + dist[location][HUB]
        return km <= max_km + TOLERANCE and depart + km * MINUTES_PER_KM <= latest_return

    candidates = {loc: ids for loc, ids in groups.items() if round_trip_ok(loc)}
    if not candidates:
        return []

    # 2. Seed location.
    best_key = None
    seed = None
    for location, ids in candidates.items():
        arrive = depart + dist[HUB][location] * MINUTES_PER_KM
        salvageable = [pid for pid in ids
                       if service_credit(arrive, parcel[pid]["delivery_window_end"]) > 0]
        if salvageable:
            key = (0, parcel[salvageable[0]]["delivery_window_end"], location)
        else:
            load = sum(parcel[pid]["size"] for pid in ids)
            key = (1, -load, location)
        if best_key is None or key < best_key:
            best_key, seed = key, location

    # 3-4. Fill the seed, then extend by nearest neighbour.
    route: List[str] = []
    load = 0.0
    km_to_last = 0.0  # km from HUB to the last stop, excluding the return leg
    last = HUB
    visited = set()
    location = seed
    while location is not None:
        leg = dist[last][location]
        total_km = km_to_last + leg + dist[location][HUB]
        if total_km > max_km + TOLERANCE or depart + total_km * MINUTES_PER_KM > latest_return:
            break
        added = False
        for pid in candidates[location]:
            size = parcel[pid]["size"]
            if load + size <= capacity + TOLERANCE:
                route.append(pid)
                load += size
                added = True
        visited.add(location)
        if added:
            km_to_last += leg
            last = location
        if load >= capacity - TOLERANCE:
            break
        # Nearest unvisited location with at least one parcel that still fits.
        location = None
        nearest = None
        for other, ids in candidates.items():
            if other in visited:
                continue
            if not any(load + parcel[pid]["size"] <= capacity + TOLERANCE for pid in ids):
                continue
            extended = km_to_last + dist[last][other] + dist[other][HUB]
            if extended > max_km + TOLERANCE or depart + extended * MINUTES_PER_KM > latest_return:
                continue
            if nearest is None or (dist[last][other], other) < nearest:
                nearest = (dist[last][other], other)
                location = other
    return route
