"""Ablation study for solution/policies/heuristic_best.py.

Runs the proposed policy on every day with the course-algorithm components
switched on/off, and counts how often each component changes a decision:
  * full            : heap seed fallback + UCS re-ordering (the proposed policy)
  * no_ucs          : without UCS re-ordering
  * no_heap_fallback: seed only the top at-risk location (no fallback)
  * neither         : both off (= #8 + adaptive #7 with no course extras)

Writes results/ablation_heuristic_best.json. Run from the project root:
    python3 scripts/ablation_heuristic_best.py
"""

import csv
import json
import statistics
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from simulator.loaders import day_input_paths  # noqa: E402
from simulator.simulator import Simulator  # noqa: E402
from solution import log_utils  # noqa: E402
from solution.performance_monitor import calculate_metrics  # noqa: E402
from solution.policies import heuristic_best  # noqa: E402

VARIANTS = {"full": (True, True), "no_ucs": (False, True),
            "no_heap_fallback": (True, False), "neither": (False, False)}


def configure(ucs: bool, fallback: bool) -> None:
    heuristic_best.USE_UCS_ORDERING = ucs
    heuristic_best.USE_HEAP_SEED_FALLBACK = fallback


def run_day(day: str, counters=None) -> float:
    paths = day_input_paths(ROOT / "data", day)

    def counting(parcel, context):
        configure(True, True)
        chosen = heuristic_best.dispatch(parcel, context)
        if counters is not None and chosen:
            counters["trips"] += 1
            configure(False, True)
            if heuristic_best.dispatch(parcel, context) != chosen:
                counters["ucs_changed"] += 1
            configure(True, False)
            if heuristic_best.dispatch(parcel, context) != chosen:
                counters["fallback_changed"] += 1
            configure(True, True)
        return chosen

    policy = counting if counters is not None else heuristic_best.dispatch
    rows = lambda p: list(csv.DictReader(open(p, encoding="utf-8-sig")))
    with tempfile.TemporaryDirectory() as tmp:
        Simulator(*paths, dispatch_policy=policy).run(Path(tmp) / "log.txt")
        events = log_utils.load_events(Path(tmp) / "log.txt")
    return calculate_metrics(rows(paths[0]), rows(paths[1]), json.loads(paths[2].read_text()), events)["service_score"]


def main() -> int:
    days = [f"day_{n:03d}" for n in range(1, 21)]
    results = {}
    for name, (ucs, fallback) in VARIANTS.items():
        configure(ucs, fallback)
        scores = [run_day(day) for day in days]
        results[name] = {"mean_service_score": round(statistics.mean(scores), 6), "per_day": scores}
        print(f"{name:17} mean service score {statistics.mean(scores):.4f}")
    counters = {"trips": 0, "ucs_changed": 0, "fallback_changed": 0}
    for day in days:
        run_day(day, counters)
    configure(True, True)
    results["decision_counts_full_policy"] = counters
    print("trips dispatched by the full policy:", counters["trips"],
          "| changed by UCS re-ordering:", counters["ucs_changed"],
          "| changed by heap seed fallback:", counters["fallback_changed"])
    (ROOT / "results" / "ablation_heuristic_best.json").write_text(json.dumps(results, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
