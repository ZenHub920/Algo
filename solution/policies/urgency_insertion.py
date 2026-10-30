"""Policy #8 - Urgency-seeded insertion (policy #4 + serve the most at-risk location first).

Why: policy #4 ranks stops by value per extra km, so an urgent parcel at a
far location (value ~1 / ~80 km) never beats a cluster of nearby parcels, keeps
getting skipped and ends up hours late. Adding urgency to the value alone does
not fix this (tested: +0.001), because the per-km ratio dominates.

Change (the only difference from #4): before insertion, the trip is seeded
with the location holding the most credit AT RISK, i.e. the credit its
parcels would lose if they waited for the next van:
    at_risk(p) = credit(delivered now) - credit(delivered after WAIT minutes)
The rest of the trip is then built exactly as in #4 (shared engine
helpers.build_insertion_route: best credit per extra km, free top-up,
backlog fallback). If nothing is at risk, it behaves exactly like #4.

WAIT = minutes until the next planning round at which another vehicle is
ready (from context["fleet"]), plus EXTRA_WAIT for that van's own detour.

Complexity per call: seeding O(n + V) (V vehicles), then #4's
O(m^2 * (L*k + n)). Space O(n + L + k).
"""

import math
from typing import Dict, List, Optional

from simulator.models import Parcel, SimulationContext
from solution.policies.helpers import (
    HUB, MINUTES_PER_KM, available_parcel_ids, build_insertion_route, departure_time,
    service_credit,
)

EXTRA_WAIT = 30.0         # Minutes added to the estimated wait for the next van
PLANNING_INTERVAL = 10.0  # Planning rounds every 10 minutes (from the brief)


def estimated_wait(context: SimulationContext) -> float:
    """Minutes until another van could plausibly leave for this parcel instead."""

    now = context["current_time"]
    others = [vehicle["available_at"] for vehicle_id, vehicle in context["fleet"].items()
              if vehicle_id != context["vehicle_id"]]
    next_free = min(others) if others else now + PLANNING_INTERVAL
    next_round = max(now + PLANNING_INTERVAL,
                     math.ceil(next_free / PLANNING_INTERVAL) * PLANNING_INTERVAL)
    return next_round - now + EXTRA_WAIT


def most_at_risk_location(parcel: Dict[str, Parcel], context: SimulationContext) -> Optional[str]:
    """Location whose waiting parcels would lose the most credit by waiting; None if none would."""

    dist = context["travel_distance"]
    depart = departure_time(context)
    wait = estimated_wait(context)
    risk: Dict[str, float] = {}
    for parcel_id in available_parcel_ids(parcel):
        location = parcel[parcel_id]["delivery_location_id"]
        arrive = depart + dist[HUB][location] * MINUTES_PER_KM
        end = parcel[parcel_id]["delivery_window_end"]
        lost = service_credit(arrive, end) - service_credit(arrive + wait, end)
        if lost > 0:
            risk[location] = risk.get(location, 0.0) + lost
    if not risk:
        return None
    return max(risk, key=lambda location: (risk[location], location))


def dispatch(parcel: Dict[str, Parcel], context: SimulationContext) -> List[str]:
    """Return parcel IDs in delivery order for context["vehicle_id"], or [] to skip."""

    def value(parcel_id: str, arrival: float) -> float:
        return service_credit(arrival, parcel[parcel_id]["delivery_window_end"])

    return build_insertion_route(parcel, context, value,
                                 seed_location=most_at_risk_location(parcel, context))
