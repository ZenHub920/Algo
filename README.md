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
| Task 1: performance metric | Chosen: weighted service score (see below) |
| `calculate_metrics` inputs/outputs (Appendix C) | Done: inputs parsed, deliveries joined to parcels, return value validated |
| Metric in `calculate_metrics` | Done: `service_score` plus supporting figures |
| Task 3: dispatch policies | Done: `edd_heap.py` (#1), `location_batching.py` (#3), `score_insertion.py` (#4), `urgency_insertion.py` (#8), `urgency_holdback.py` (#8 + #7) and the proposed `heuristic_best.py` (#8 + adaptive #7, with heap and UCS) |
| **Task 4: experiments and analysis** | **TODO** (see `docs/report_outline.md`) |

## Performance metric: weighted service score

Per parcel (`helpers.service_credit`, shared by the monitor and the policies):

- **1.0** if delivered by its window end. Early delivery is not penalised.
- **−0.1 for every started 10 minutes late** (0.5 min late → 0.9, 10.5 min → 0.8),
  never below 0, so credit is 0 once more than 90 minutes late.
- **0** if never delivered.

`service_score` = total credit ÷ **all** parcels in the day's file (0 to 1). The
denominator includes undelivered parcels and the few that no policy could deliver
in time, so withholding parcels can never raise the score.

Supporting figures in `metrics.json` (they explain results; they don't rank
policies): delivery rate, on-time rate, late and zero-credit deliveries, mean
minutes late, early deliveries, trips, total km, km per delivered parcel, mean
load utilisation.

## Layout

```
simulator/                    # Supplied — do not modify
data/                         # Supplied — do not modify (day_001..day_020, dist.csv, config.json)
solution/
├── __init__.py               # Supplied — do not modify
├── performance_monitor.py    # Supplied template — parsing wired in; TODO: the metric itself
├── log_utils.py              # Ours: parse inputs + log, join deliveries to parcels, validate output
└── policies/
    ├── __init__.py           # Supplied — do not modify
    ├── baseline.py           # Supplied FIFO first-fit — do not modify
    ├── helpers.py            # Ours: shared route helpers, service_credit, insertion engine,
    │                         #   HeapPriorityQueue (Week 7) and ucs_shortest_tour (Week 10)
    ├── edd_heap.py           # Policy #1: earliest deadline first via heap priority queue (heap sort)
    ├── location_batching.py  # Policy #3: batch parcels by location, nearest-neighbour extension
    ├── score_insertion.py    # Policy #4: insert stops by predicted credit per extra km
    ├── urgency_insertion.py  # Policy #8: #4, but start each trip at the most at-risk location
    ├── urgency_holdback.py   # Policy #8 + #7: #8, but hold light, non-urgent trips one round
    └── heuristic_best.py     # PROPOSED: #8 + adaptive #7, heap seed ranking, UCS stop ordering
results/<policy>/<day>/       # log.txt (simulator) + metrics.json (monitor)
scripts/
├── run_experiments.py        # Simulate + measure many days / policies in one go
├── ablation_heuristic_best.py # Switch heap fallback / UCS off to measure their effect
└── compare_results.py        # Aggregate every metrics.json into results/summary.csv
tests/                        # unittest: helpers vs. simulator, Appendix C contract, end-to-end
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

## `calculate_metrics(parcels, distances, config, events)` (Appendix C)

Called once per run by `solution/performance_monitor.py`. Its inputs are raw:

| Argument | Shape | Already handled by |
|---|---|---|
| `parcels` | list of CSV row dicts, **all strings**, with `parcel_id`; includes parcels never delivered; no assignment/delivery fields | `log_utils.parse_parcels` (HH:MM → minutes, size → float) |
| `distances` | list of `dist.csv` rows (`location_1`, `location_2`, `dist` as string) | `log_utils.parse_distances` → `[origin][destination]` km |
| `config` | dict: `number_of_vehicles`, `capacity`, `vehicle_range_km` | `log_utils.parse_config` |
| `events` | log records in chronological order (Appendix B) | `extract_deliveries`, `extract_trips` |

Deliveries are matched to parcels by `parcel_id` with `log_utils.join_outcomes`,
which returns **every** parcel with `delivered`, `delivery_time`, `vehicle_id` and
`trip_id` (all `None` if undelivered) for window and undelivered-parcel analysis.

Return value: a dict of string metric names to JSON-serializable values, all
numbers finite (no NaN or infinity). The script writes it to `metrics.json`.
`calculate_metrics` passes its result through `log_utils.validate_metrics`, which
enforces this.

The template already parses everything; the only TODO is the metric itself.
Note that the baseline leaves many parcels undelivered (day_001: 349 of 799
delivered), so how the metric treats undelivered parcels matters.

## Course content used

| IS115 topic | Where |
|---|---|
| Hash maps (Week 7) | Parcels grouped by location and credit at risk per location (`helpers.build_insertion_route`, `heuristic_best`, `location_batching`) |
| Heap-based priority queue, upheap/downheap, bottom-up build (Week 7) | `helpers.HeapPriorityQueue`; seed ranking in `heuristic_best`; deadline queue in `edd_heap` |
| Heap sort (Week 7) | `edd_heap`: repeated `remove_min` gives earliest-deadline order |
| Uniform Cost Search with a priority queue (Week 10) | `helpers.ucs_shortest_tour`: shortest visiting order of a trip's stops, used by `heuristic_best` |
| Queue / FIFO (Week 5) | The supplied baseline serves parcels first-in, first-out |

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
