"""Recommended dispatch policy - NOT YET IMPLEMENTED.

TODO: implement once the performance metric is chosen (Task 1) and the
experiments in Task 4 have identified the best approach.

Until then this stub returns [] (dispatch nothing), so the simulator runs end
to end but delivers no parcels.

Run:
    python3 -m simulator --policy solution.policies.heuristic_best \
        --data data --day day_001 --output results/heuristic_best/day_001

Rules from the brief:
    * Keep the dispatch(parcel, context) signature unchanged.
    * Use only `parcel` and `context`; never read files in data/.
    * Treat both arguments as read-only.
    * Standard library only. Shared code goes in solution/policies/helpers.py.
"""

from typing import Dict, List

from simulator.models import Parcel, SimulationContext


def dispatch(parcel: Dict[str, Parcel], context: SimulationContext) -> List[str]:
    """Return parcel IDs in delivery order for context["vehicle_id"], or [] to skip."""

    # TODO: build and return a feasible route (see helpers.is_feasible).
    return []
