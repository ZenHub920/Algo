"""Ablation study for solution/policies/heuristic_best.py.

Runs the proposed policy on every day with its optional components switched
on/off, and counts how often each component changes a decision:
  * full               : time-based backlog check + heap seed fallback + UCS
                         re-ordering (the proposed policy)
  * no_time_backlog    : without the time-based backlog check (failsafe)
  * no_ucs             : without UCS re-ordering
  * no_heap_fallback   : seed only the top at-risk location (no fallback)
  * course_extras_off  : UCS and heap fallback off, time-based check on
  * all_off            : all three off (= #8 + adaptive #7, capacity check only)

Runs on all CPU cores. Writes results/ablation_heuristic_best.json. Run from the project root:
    python3 scripts/ablation_heuristic_best.py
"""

import csv
import json
import multiprocessing
import os
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

# name: (time-based backlog, UCS ordering, heap seed fallback)
VARIANTS = {
    "full": (True, True, True),
    "no_time_backlog": (False, True, True),
    "no_ucs": (True, False, True),
    "no_heap_fallback": (True, True, False),
    "course_extras_off": (True, False, False),
    "all_off": (False, False, False),
}


def configure(time_backlog: bool, ucs: bool, fallback: bool) -> None:
    heuristic_best.USE_TIME_BACKLOG = time_backlog
    heuristic_best.USE_UCS_ORDERING = ucs
    heuristic_best.USE_HEAP_SEED_FALLBACK = fallback


def run_day(day: str, counters=None) -> dict:
    paths = day_input_paths(ROOT / "data", day)

    def counting(parcel, context):
        configure(True, True, True)
        chosen = heuristic_best.dispatch(parcel, context)
        if counters is not None:
            for key, switches in (("time_backlog_changed", (False, True, True)),
                                  ("ucs_changed", (True, False, True)),
                                  ("fallback_changed", (True, True, False))):
                configure(*switches)
                if heuristic_best.dispatch(parcel, context) != chosen:
                    counters[key] += 1
            configure(True, True, True)
            if chosen:
                counters["trips"] += 1
        return chosen

    policy = counting if counters is not None else heuristic_best.dispatch
    rows = lambda p: list(csv.DictReader(open(p, encoding="utf-8-sig")))
    with tempfile.TemporaryDirectory() as tmp:
        Simulator(*paths, dispatch_policy=policy).run(Path(tmp) / "log.txt")
        events = log_utils.load_events(Path(tmp) / "log.txt")
    return calculate_metrics(rows(paths[0]), rows(paths[1]), json.loads(paths[2].read_text()), events)


def score_task(task):
    """One (variant, day) run; executed in a worker process."""
    name, day = task
    configure(*VARIANTS[name])
    return name, day, run_day(day)


def count_task(day):
    """Decision counts for the full policy on one day; executed in a worker process."""
    counters = {"trips": 0, "time_backlog_changed": 0, "ucs_changed": 0, "fallback_changed": 0}
    run_day(day, counters)
    return counters


def main() -> int:
    days = [f"day_{n:03d}" for n in range(1, 21)]
    tasks = [(name, day) for name in VARIANTS for day in days]
    with multiprocessing.Pool(os.cpu_count() or 1) as pool:
        runs = pool.map(score_task, tasks)
        day_counts = pool.map(count_task, days)
    results = {}
    for name in VARIANTS:
        metrics = [m for n, d, m in sorted(runs, key=lambda r: r[1]) if n == name]
        scores = [m["service_score"] for m in metrics]
        results[name] = {
            "mean_service_score": round(statistics.mean(scores), 6),
            "mean_delivery_rate": round(statistics.mean(m["delivery_rate"] for m in metrics), 6),
            "mean_trips": round(statistics.mean(m["trips"] for m in metrics), 2),
            "per_day": scores,
        }
        print(f"{name:18} mean service score {statistics.mean(scores):.4f}")
    counters = {key: sum(c[key] for c in day_counts) for key in day_counts[0]}
    results["decision_counts_full_policy"] = counters
    print("trips dispatched by the full policy:", counters["trips"],
          "| decisions changed by: time-based backlog", counters["time_backlog_changed"],
          "| UCS re-ordering", counters["ucs_changed"],
          "| heap seed fallback", counters["fallback_changed"])
    (ROOT / "results" / "ablation_heuristic_best.json").write_text(json.dumps(results, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
