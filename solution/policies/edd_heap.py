"""Policy #1 - Earliest deadline first with a heap-based priority queue.

Course content used (IS115):
  * Heap-based priority queue (Week 7): available parcels are loaded into
    helpers.HeapPriorityQueue by bottom-up construction, keyed by window end
    (then arrival time, then ID for a deterministic order).
  * Heap sort (Week 7, "using a heap in a priority queue implementation"):
    repeated remove_min yields parcels in earliest-deadline order.

Each parcel popped is added to the trip if it still fits capacity, range and
the 18:00 return cutoff (first-fit, like the baseline); otherwise it is skipped
and later parcels are still tried. Stops are visited in deadline order.
Always dispatches if anything fits (no waiting rule).

It differs from the FIFO baseline only in the priority (deadline instead of
arrival), so it isolates the value of prioritising urgent parcels without any
grouping by location.

Complexity per call (n available parcels): bottom-up build O(n), n removals
O(n log n), constant-time feasibility update per parcel: O(n log n) overall.
Space O(n).
"""

from typing import Dict, List

from simulator.models import Parcel, SimulationContext
from solution.policies.helpers import (
    HUB, MINUTES_PER_KM, TOLERANCE, HeapPriorityQueue, available_parcel_ids, departure_time,
)


def dispatch(parcel: Dict[str, Parcel], context: SimulationContext) -> List[str]:
    """Return parcel IDs in delivery order for context["vehicle_id"], or [] to skip."""

    dist = context["travel_distance"]
    depart = departure_time(context)
    queue = HeapPriorityQueue([
        ((parcel[pid]["delivery_window_end"], parcel[pid]["arrival_time"], pid), pid)
        for pid in available_parcel_ids(parcel)
    ])
    route: List[str] = []
    load = 0.0
    km_to_last = 0.0  # km from HUB to the last stop, excluding the return leg
    last = HUB
    while not queue.is_empty():
        _, pid = queue.remove_min()
        record = parcel[pid]
        if load + record["size"] > context["capacity"] + TOLERANCE:
            continue
        destination = record["delivery_location_id"]
        to_here = km_to_last + dist[last][destination]
        total = to_here + dist[destination][HUB]
        if (total > context["max_trip_distance_km"] + TOLERANCE
                or depart + total * MINUTES_PER_KM > context["return_cutoff"]):
            continue
        route.append(pid)
        load += record["size"]
        km_to_last, last = to_here, destination
    return route
