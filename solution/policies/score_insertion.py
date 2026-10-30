"""Policy #4 - Score-aware cheapest insertion.

Idea: build the trip by repeatedly inserting the stop that adds the most
predicted service credit per extra kilometre, using exactly the metric's
credit function (helpers.service_credit). Parcels for one location share a
stop, so inserting a stop brings a bundle of parcels.

Each call:
  Phase A (score-driven). Repeat:
     for every location not yet on the route, and every insertion position:
       - extra km  = d(prev, loc) + d(loc, next) - d(prev, next)
       - check capacity, range and the 18:00 return cutoff
       - gain = credit of the parcels at loc that can still earn credit
                (best credit first, until capacity is full)
       - loss = credit lost by stops after the insertion point, which now
                arrive `extra km` minutes later
       - value = (gain - loss) / (extra km + 1)
     insert the best option if gain - loss > 0; otherwise stop.
  Phase B (free top-up). Fill spare capacity with any other parcels for
     locations already on the route (no extra km, no delay).
  Phase C (fallback). If no parcel can earn credit anywhere, still clear the
     backlog: insert stops by parcels-per-extra-km instead.
Always dispatches if any parcel fits (no waiting rule).

Complexity per call (n available parcels, L locations, m stops, k parcels on
the route): each insertion step tries L*(m+1) positions, each costing O(k) to
re-price later stops plus O(n_loc) to price the bundle, so O(L*m*k + m*n) per
step and O(m^2 * (L*k + n)) per call. Space O(n + L + k).

The engine lives in helpers.build_insertion_route (shared with policy #8);
this policy values a parcel purely by its predicted service credit.
"""

from typing import Dict, List

from simulator.models import Parcel, SimulationContext
from solution.policies.helpers import build_insertion_route, service_credit


def dispatch(parcel: Dict[str, Parcel], context: SimulationContext) -> List[str]:
    """Return parcel IDs in delivery order for context["vehicle_id"], or [] to skip."""

    def value(parcel_id: str, arrival: float) -> float:
        return service_credit(arrival, parcel[parcel_id]["delivery_window_end"])

    return build_insertion_route(parcel, context, value)
