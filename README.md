# Algo — IS115 Last-Mile Dispatch Project

One hub, ten homogeneous EVs (capacity 30, range 320 km, 60 km/h), parcels
arriving 08:00–17:30, planning every 10 minutes, 30-minute departure delay,
all vehicles back by 18:00. We write dispatch policies, measure them with a
performance metric of our choosing, and compare them against the supplied
FIFO baseline over 20 historical days.

Python 3.9+; standard library only.

## Status

| Part | State |
|---|---|
| Supplied simulator, data, baseline, monitor template | Copied in unchanged |
| Shared policy helpers (`solution/policies/helpers.py`) | Done: feasibility checks, route distance/timing |
| Log parsing helpers (`solution/log_utils.py`) | Done: metric-neutral |
| Batch runner and comparison scripts (`scripts/`) | Done |
| Baseline logs, days 001–020 | Generated |
| **Task 1: performance metric** | **TODO: not chosen yet** |
| **`calculate_metrics` in `performance_monitor.py`** | **TODO: still the trip-count illustration** |
| **Task 3: dispatch policies** | **TODO: `heuristic_best.py` is a stub returning `[]`** |
| **Task 4: experiments and analysis** | **TODO** (see `docs/report_outline.md`) |

`results/*/day_*/metrics.json` currently hold the placeholder `number_of_trips`
metric. Re-run the monitor once the real metric is in place (command below).

## Layout

```
simulator/                    # Supplied — do not modify
data/                         # Supplied — do not modify (day_001..day_020, dist.csv, config.json)
solution/
├── __init__.py               # Supplied — do not modify
├── performance_monitor.py    # Supplied template — TODO: implement calculate_metrics
├── log_utils.py              # Ours: parse CSV rows + event log into trips/deliveries
└── policies/
    ├── __init__.py           # Supplied — do not modify
    ├── baseline.py           # Supplied FIFO first-fit — do not modify
    ├── helpers.py            # Ours: shared feasibility/route helpers for every policy
    └── heuristic_best.py     # Ours: recommended policy — TODO
results/<policy>/<day>/       # log.txt (simulator) + metrics.json (monitor)
scripts/
├── run_experiments.py        # Simulate + measure many days / policies in one go
└── compare_results.py        # Aggregate every metrics.json into results/summary.csv
tests/                        # unittest: helpers vs. simulator rules, end-to-end smoke tests
docs/report_outline.md        # Skeleton for the Task 1–4 write-up
```

## Commands (run from the project root)

Single day, by hand (as in the brief):

```bash
python3 -m simulator --policy solution.policies.baseline \
    --data data --day day_001 --output results/baseline/day_001
python3 -m solution.performance_monitor \
    --data data --day day_001 --log results/baseline/day_001/log.txt
```

All 20 days for one or more policies:

```bash
python3 scripts/run_experiments.py --policy solution.policies.baseline
python3 scripts/run_experiments.py --policy solution.policies.baseline \
    --policy solution.policies.heuristic_best --days 1-20
```

Re-measure existing logs after changing the metric (no re-simulation):

```bash
python3 scripts/run_experiments.py --policy solution.policies.baseline --monitor-only
```

Compare policies:

```bash
python3 scripts/compare_results.py
```

Tests:

```bash
python3 -m unittest discover -s tests -t .
```

## Adding a new policy

1. Create `solution/policies/<name>.py` exposing `dispatch(parcel, context)`; copy the
   structure of `heuristic_best.py`.
2. Use only `parcel` and `context` (never read `data/`), and treat both as read-only.
3. Reuse `solution.policies.helpers` (`available_parcel_ids`, `can_append`,
   `is_feasible`, `delivery_times`, …) so every policy enforces the hard constraints
   the same way the simulator does.
4. `python3 scripts/run_experiments.py --policy solution.policies.<name>`.

## Key rules from the brief

- Hard constraints per trip: load ≤ 30, distance ≤ 320 km, back at HUB by 18:00 (1080).
- Delivery windows are soft; undelivered parcels are allowed.
- A parcel is selectable when `vehicle_assigned` and `delivery_time` are both `None`.
- Return `[]` to leave a vehicle idle this round; HUB is never in the returned list.
- Departure = `current_time + 30`; km = minutes at 60 km/h; zero service time.
- A metric that leads to a trivial approach scores zero.
