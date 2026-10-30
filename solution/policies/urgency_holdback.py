"""Policy #8 + #7 - Urgency-seeded insertion with a hold-back (wait) rule.

Why: every policy so far sends a van out as soon as anything fits, even when
the trip is nearly empty. That van is then away for hours, so when urgent
parcels arrive soon after there may be no van left to take them; meanwhile
waiting parcels would have built up into a fuller, better-batched trip.

Change (the only difference from #8): #8 builds the trip as usual, then the
van is HELD at the hub for this round (return []) when all of these hold:
  * the trip would use less than HOLD_LOAD_FRACTION of capacity;
  * no parcel on it would lose credit by waiting one more round (10 minutes);
  * it is before LAST_HOLD_TIME (late in the day, always go).
A held van is reconsidered in the next planning round with fresh parcels.

HOLD_LOAD_FRACTION sensitivity (mean service score, 20 days, tested while
building this policy): 0.3 -> 0.922, 0.5 -> 0.941, 0.7 -> 0.947, 0.9 -> 0.948.
0.7 is the start of the plateau, so the result does not hinge on fine tuning.

Complexity per call: #8's O(m^2 * (L*k + n)) plus O(k) for the hold test.
Space O(n + L + k).
"""

from typing import Dict, List

from simulator.models import Parcel, SimulationContext
from solution.policies import urgency_insertion
from solution.policies.helpers import delivery_times, route_load, service_credit

HOLD_LOAD_FRACTION = 0.7  # Hold trips filled below 70% of capacity ...
LAST_HOLD_TIME = 1000.0   # ... but only before 16:40 (minutes after midnight)
PLANNING_INTERVAL = 10.0  # Holding delays departure by one planning round


def should_hold(route: List[str], parcel: Dict[str, Parcel], context: SimulationContext) -> bool:
    """True if this trip should wait one round instead of leaving now."""

    if not route or context["current_time"] >= LAST_HOLD_TIME:
        return False
    if route_load(route, parcel) >= HOLD_LOAD_FRACTION * context["capacity"]:
        return False
    for parcel_id, time in zip(route, delivery_times(route, parcel, context)):
        end = parcel[parcel_id]["delivery_window_end"]
        if service_credit(time, end) > service_credit(time + PLANNING_INTERVAL, end):
            return False  # Something on this trip would lose credit by waiting.
    return True


def dispatch(parcel: Dict[str, Parcel], context: SimulationContext) -> List[str]:
    """Return parcel IDs in delivery order for context["vehicle_id"], or [] to skip."""

    route = urgency_insertion.dispatch(parcel, context)
    return [] if should_hold(route, parcel, context) else route
