"""Shared, policy-neutral building blocks for dispatch policies.

Everything here only reads the ``parcel`` and ``context`` snapshots passed to
``dispatch`` and never modifies them. Nothing here decides *which* parcels to
send or in *what order* - that is each policy's job.

Import in a policy with:

    from solution.policies.helpers import available_parcel_ids, is_feasible, ...

Conventions (matching the simulator):
    * Times are minutes after midnight; distances are kilometres.
    * Speed is 60 km/h, so 1 km of travel takes 1 minute.
    * A route is an ordered list of parcel IDs; HUB is implicit at both ends.
    * Delivery service time is zero.

Standard library only.
"""

import math
from typing import Callable, Dict, List, Optional, Tuple

from simulator.models import Parcel, SimulationContext

HUB = "HUB"
MINUTES_PER_KM = 1.0  # 60 km/h
TOLERANCE = 1e-9  # Same float tolerance the simulator uses when validating routes

ParcelMap = Dict[str, Parcel]
DistanceMap = Dict[str, Dict[str, float]]


# ---------------------------------------------------------------------------
# Parcel selection primitives
# ---------------------------------------------------------------------------

def is_available(record: Parcel) -> bool:
    """True if a parcel can still be put on a trip (unassigned and undelivered)."""

    return record["vehicle_assigned"] is None and record["delivery_time"] is None


def available_parcel_ids(parcel: ParcelMap) -> List[str]:
    """IDs of all parcels available for selection, sorted by ID for determinism."""

    return sorted(parcel_id for parcel_id, record in parcel.items() if is_available(record))


# ---------------------------------------------------------------------------
# Route geometry and timing
# ---------------------------------------------------------------------------

def route_locations(route: List[str], parcel: ParcelMap) -> List[str]:
    """Full location sequence for a route, including HUB at the start and end."""

    return [HUB] + [parcel[parcel_id]["delivery_location_id"] for parcel_id in route] + [HUB]


def route_load(route: List[str], parcel: ParcelMap) -> float:
    """Total parcel size on a route, in capacity units."""

    return math.fsum(parcel[parcel_id]["size"] for parcel_id in route)


def route_distance(route: List[str], parcel: ParcelMap, distances: DistanceMap) -> float:
    """Total km for HUB -> stops -> HUB, summed the same way as the simulator."""

    if not route:
        return 0.0
    locations = route_locations(route, parcel)
    return math.fsum(distances[a][b] for a, b in zip(locations, locations[1:]))


def departure_time(context: SimulationContext) -> float:
    """Time the vehicle leaves the hub if dispatched in this planning round."""

    return context["current_time"] + context["departure_delay"]


def delivery_times(route: List[str], parcel: ParcelMap, context: SimulationContext) -> List[float]:
    """Predicted delivery time of each parcel on the route, in route order."""

    distances = context["travel_distance"]
    time = departure_time(context)
    location = HUB
    times: List[float] = []
    for parcel_id in route:
        destination = parcel[parcel_id]["delivery_location_id"]
        time += distances[location][destination] * MINUTES_PER_KM
        times.append(time)
        location = destination
    return times


def return_time(route: List[str], parcel: ParcelMap, context: SimulationContext) -> float:
    """Predicted time the vehicle is back at the hub after the route."""

    distance = route_distance(route, parcel, context["travel_distance"])
    return departure_time(context) + distance * MINUTES_PER_KM


# ---------------------------------------------------------------------------
# Hard-constraint checks (mirror simulator._validate_route)
# ---------------------------------------------------------------------------

def route_violations(route: List[str], parcel: ParcelMap, context: SimulationContext) -> List[str]:
    """List every reason the simulator would reject this route; empty list means valid.

    Checks: known, unique, available parcels; capacity; range; return cutoff.
    An empty route is valid (it means "skip this vehicle").
    """

    problems: List[str] = []
    seen = set()
    for parcel_id in route:
        if parcel_id not in parcel:
            problems.append(f"unknown parcel {parcel_id!r}")
            continue
        if parcel_id in seen:
            problems.append(f"duplicate parcel {parcel_id!r}")
        elif not is_available(parcel[parcel_id]):
            problems.append(f"parcel {parcel_id!r} is not available")
        seen.add(parcel_id)
    if problems or not route:
        return problems

    if route_load(route, parcel) > context["capacity"] + TOLERANCE:
        problems.append("exceeds capacity")
    distance = route_distance(route, parcel, context["travel_distance"])
    if distance > context["max_trip_distance_km"] + TOLERANCE:
        problems.append("exceeds range")
    if departure_time(context) + distance * MINUTES_PER_KM > context["return_cutoff"]:
        problems.append("returns after cutoff")
    return problems


def is_feasible(route: List[str], parcel: ParcelMap, context: SimulationContext) -> bool:
    """True if the simulator would accept this route."""

    return not route_violations(route, parcel, context)


def can_append(
    route: List[str], candidate: str, parcel: ParcelMap, context: SimulationContext,
    *, current_load: Optional[float] = None,
) -> bool:
    """True if ``route + [candidate]`` still satisfies every hard constraint.

    ``current_load`` lets a caller that already tracks the route's load skip
    recomputing it; the distance check is always recomputed exactly.
    """

    load = route_load(route, parcel) if current_load is None else current_load
    if load + parcel[candidate]["size"] > context["capacity"] + TOLERANCE:
        return False
    return is_feasible(route + [candidate], parcel, context)


# ---------------------------------------------------------------------------
# Service credit (the performance metric's per-parcel score)
# ---------------------------------------------------------------------------
# Shared by solution/performance_monitor.py and by score-aware policies, so a
# policy optimises exactly what the metric measures.

FULL_CREDIT = 1.0
LATE_STEP_MINUTES = 10.0   # Every started block of 10 minutes late ...
LATE_STEP_PENALTY = 0.1    # ... costs 0.1, so credit is 0 once more than 90 minutes late.
TIME_EPSILON = 1e-6        # Absorbs float noise in fractional delivery times


def lateness(delivery_time: float, window_end: float) -> float:
    """Minutes after the window end (0 if on time or early)."""

    return max(0.0, delivery_time - window_end)


def service_credit(delivery_time: Optional[float], window_end: float) -> float:
    """Credit for one parcel: 1 if delivered by window end (early is not penalised),
    minus 0.1 for every started 10 minutes late, never below 0; undelivered scores 0.

    Examples: on time or early -> 1.0; 0.5 min late -> 0.9; 10 min late -> 0.9;
    10.5 min late -> 0.8; 85 min late -> 0.1; 90.5 min late or more -> 0.0.
    """

    if delivery_time is None:
        return 0.0
    late = lateness(delivery_time, window_end)
    if late <= TIME_EPSILON:
        return FULL_CREDIT
    steps = math.ceil((late - TIME_EPSILON) / LATE_STEP_MINUTES)
    return max(0.0, FULL_CREDIT - LATE_STEP_PENALTY * steps)


def route_credit(route: List[str], parcel: ParcelMap, context: SimulationContext) -> float:
    """Total predicted service credit of a route if dispatched in this round."""

    times = delivery_times(route, parcel, context)
    return math.fsum(service_credit(time, parcel[parcel_id]["delivery_window_end"])
                     for parcel_id, time in zip(route, times))


# ---------------------------------------------------------------------------
# Shared insertion engine (policies #4 and #8)
# ---------------------------------------------------------------------------
# Builds a trip stop by stop. Parcels for one location share a stop. The
# caller supplies value_fn(parcel_id, arrival_time) -> float, the worth of
# delivering that parcel at that time; only parcels with value > 0 drive
# Phase A. See solution/policies/score_insertion.py for the full description.

Stop = Tuple[str, List[str]]


def build_insertion_route(
    parcel: ParcelMap, context: SimulationContext,
    value_fn: Callable[[str, float], float],
    seed_location: Optional[str] = None,
) -> List[str]:
    """Greedy best-value-per-extra-km stop insertion with free top-up and fallback.

    If seed_location is given, that stop is placed first (if it fits the hard
    constraints), regardless of its value per km; insertion then continues.
    """

    dist = context["travel_distance"]
    capacity = context["capacity"]
    max_km = context["max_trip_distance_km"]
    depart = departure_time(context)
    latest_return = context["return_cutoff"]

    by_location: Dict[str, List[str]] = {}
    for parcel_id in available_parcel_ids(parcel):
        by_location.setdefault(parcel[parcel_id]["delivery_location_id"], []).append(parcel_id)
    for ids in by_location.values():
        ids.sort(key=lambda pid: (parcel[pid]["delivery_window_end"], pid))

    stops: List[Stop] = []
    load = 0.0
    route_km = 0.0  # Full round-trip km of the current stops

    def arrivals() -> List[float]:
        times, time, last = [], depart, HUB
        for location, _ in stops:
            time += dist[last][location] * MINUTES_PER_KM
            times.append(time)
            last = location
        return times

    def best_insertion(score_driven: bool):
        """Best (key, position, location, bundle, extra_km), or None."""
        on_route = {location for location, _ in stops}
        times = arrivals()
        best = None
        for location, ids in by_location.items():
            if location in on_route:
                continue
            for position in range(len(stops) + 1):
                prev = HUB if position == 0 else stops[position - 1][0]
                nxt = HUB if position == len(stops) else stops[position][0]
                extra = dist[prev][location] + dist[location][nxt] - dist[prev][nxt]
                new_km = route_km + extra
                if new_km > max_km + TOLERANCE or depart + new_km * MINUTES_PER_KM > latest_return:
                    continue
                arrive = (depart if position == 0 else times[position - 1]) \
                    + dist[prev][location] * MINUTES_PER_KM

                # Bundle: parcels here, most valuable first, within spare capacity.
                spare = capacity - load
                priced = sorted(((value_fn(pid, arrive), pid) for pid in ids),
                                key=lambda item: (-item[0], parcel[item[1]]["delivery_window_end"], item[1]))
                bundle, gain = [], 0.0
                for value, pid in priced:
                    if score_driven and value <= 0.0:
                        break
                    size = parcel[pid]["size"]
                    if size <= spare + TOLERANCE:
                        bundle.append(pid)
                        spare -= size
                        gain += value if score_driven else 1.0
                if not bundle:
                    continue

                # Value lost by later stops, which are delayed by `extra` minutes.
                loss = 0.0
                if score_driven and extra > 0:
                    for index in range(position, len(stops)):
                        old_time = times[index]
                        for pid in stops[index][1]:
                            loss += value_fn(pid, old_time) - value_fn(pid, old_time + extra * MINUTES_PER_KM)
                net = gain - loss
                if score_driven and net <= TOLERANCE:
                    continue
                key = net / (extra + 1.0)
                if best is None or (key, -extra, location) > (best[0], -best[4], best[2]):
                    best = (key, position, location, bundle, extra)
        return best

    def insert(choice) -> None:
        nonlocal load, route_km
        _, position, location, bundle, extra = choice
        stops.insert(position, (location, list(bundle)))
        load += sum(parcel[pid]["size"] for pid in bundle)
        route_km += extra
        taken = set(bundle)
        by_location[location] = [pid for pid in by_location[location] if pid not in taken]

    # Optional forced first stop (used by policy #8 to serve the most urgent location).
    if seed_location is not None and by_location.get(seed_location):
        round_km = dist[HUB][seed_location] + dist[seed_location][HUB]
        if round_km <= max_km + TOLERANCE and depart + round_km * MINUTES_PER_KM <= latest_return:
            arrive = depart + dist[HUB][seed_location] * MINUTES_PER_KM
            ranked = sorted(by_location[seed_location],
                            key=lambda pid: (-value_fn(pid, arrive), parcel[pid]["delivery_window_end"], pid))
            bundle, spare = [], capacity
            for pid in ranked:
                if parcel[pid]["size"] <= spare + TOLERANCE:
                    bundle.append(pid)
                    spare -= parcel[pid]["size"]
            if bundle:
                insert((0.0, 0, seed_location, bundle, round_km))

    # Phase A: maximise value per extra km.
    while True:
        choice = best_insertion(score_driven=True)
        if choice is None:
            break
        insert(choice)

    # Phase C: nothing has positive value - clear the backlog instead of idling.
    if not stops:
        while True:
            choice = best_insertion(score_driven=False)
            if choice is None:
                break
            insert(choice)

    # Phase B: free top-up at locations already on the route.
    for location, bundle in stops:
        for pid in list(by_location.get(location, [])):
            size = parcel[pid]["size"]
            if load + size <= capacity + TOLERANCE:
                bundle.append(pid)
                load += size
                by_location[location].remove(pid)

    return [pid for _, bundle in stops for pid in bundle]


# ---------------------------------------------------------------------------
# Course data structure: heap-based priority queue (IS115 Week 7, Heaps)
# ---------------------------------------------------------------------------

class HeapPriorityQueue:
    """Min-oriented priority queue stored as an array-based complete binary tree.

    Follows the Week 7 slides: add() appends then upheaps, remove_min() swaps
    the root with the last item, removes it and downheaps; building from a list
    uses bottom-up construction (downheap from the last parent to the root).
    Entries are (key, value) pairs ordered by key only; keys must be comparable
    (tuples are used for deterministic tie-breaking).

    Complexity: add O(log n), remove_min O(log n), min O(1), len O(1),
    bottom-up build O(n). Space O(n).
    """

    def __init__(self, items: Optional[List[Tuple]] = None) -> None:
        self._data: List[Tuple] = list(items) if items else []
        if len(self._data) > 1:
            self._heapify()

    def __len__(self) -> int:
        return len(self._data)

    def is_empty(self) -> bool:
        return not self._data

    def add(self, key, value) -> None:
        self._data.append((key, value))
        self._upheap(len(self._data) - 1)

    def min(self) -> Tuple:
        if not self._data:
            raise IndexError("priority queue is empty")
        return self._data[0]

    def remove_min(self) -> Tuple:
        if not self._data:
            raise IndexError("priority queue is empty")
        self._swap(0, len(self._data) - 1)
        item = self._data.pop()
        if self._data:
            self._downheap(0)
        return item

    # --- array-based tree navigation ---
    @staticmethod
    def _parent(j: int) -> int:
        return (j - 1) // 2

    def _swap(self, i: int, j: int) -> None:
        self._data[i], self._data[j] = self._data[j], self._data[i]

    def _upheap(self, j: int) -> None:
        while j > 0:
            parent = self._parent(j)
            if self._data[j][0] < self._data[parent][0]:
                self._swap(j, parent)
                j = parent
            else:
                break

    def _downheap(self, j: int) -> None:
        size = len(self._data)
        while True:
            left, right = 2 * j + 1, 2 * j + 2
            smallest = j
            if left < size and self._data[left][0] < self._data[smallest][0]:
                smallest = left
            if right < size and self._data[right][0] < self._data[smallest][0]:
                smallest = right
            if smallest == j:
                break
            self._swap(j, smallest)
            j = smallest

    def _heapify(self) -> None:
        for j in range(self._parent(len(self._data) - 1), -1, -1):
            self._downheap(j)


# ---------------------------------------------------------------------------
# Course algorithm: Uniform Cost Search (IS115 Week 10, Graph Algorithms)
# ---------------------------------------------------------------------------

def ucs_shortest_tour(stops: List[str], dist: DistanceMap) -> Optional[List[str]]:
    """Shortest order to visit every stop once, starting and ending at HUB.

    Uniform Cost Search over a state-space graph (Week 10: "any problem with a
    state space graph can be solved by routing"):
      * state  = (current location, set of stops already visited);
      * edge   = drive to one unvisited stop (or back to HUB when all are done),
                 weighted by its km;
      * start  = (HUB, {}), goal = back at HUB with every stop visited.
    The frontier is the HeapPriorityQueue above, keyed by path cost so far;
    a state is expanded once (visited set), so with positive km the first goal
    dequeued is the shortest tour.

    Complexity for m stops: O(m * 2^m) states, O(m) edges each, heap
    operations O(log(m * 2^m)) = O(m), so O(m^3 * 2^m) time, O(m * 2^m) space.
    Used only for small trips (see heuristic_best.MAX_UCS_STOPS).
    """

    if not stops:
        return []
    everything = frozenset(stops)
    frontier = HeapPriorityQueue()
    frontier.add((0.0, ()), (HUB, frozenset(), ()))
    expanded = set()
    while not frontier.is_empty():
        (cost, _), (location, visited, path) = frontier.remove_min()
        if location == HUB and visited == everything:
            return list(path)
        state = (location, visited)
        if state in expanded:
            continue
        expanded.add(state)
        if visited == everything:
            frontier.add((cost + dist[location][HUB], path + (HUB,)), (HUB, visited, path))
            continue
        for nxt in stops:
            if nxt not in visited:
                new_cost = cost + dist[location][nxt]
                new_visited = visited | {nxt}
                if (nxt, new_visited) not in expanded:
                    frontier.add((new_cost, path + (nxt,)), (nxt, new_visited, path + (nxt,)))
    return None


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def to_hhmm(minutes: float) -> str:
    """Format minutes after midnight as HH:MM (seconds dropped), for debugging output."""

    whole = int(minutes)
    return f"{whole // 60:02d}:{whole % 60:02d}"
