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
from typing import Dict, List, Optional

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
# Formatting
# ---------------------------------------------------------------------------

def to_hhmm(minutes: float) -> str:
    """Format minutes after midnight as HH:MM (seconds dropped), for debugging output."""

    whole = int(minutes)
    return f"{whole // 60:02d}:{whole % 60:02d}"
