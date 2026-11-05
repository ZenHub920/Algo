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
| Task 1: performance metric | Done: weighted service score (below), in `solution/performance_monitor.py` |
| Task 2: baseline performance | Done: `results/baseline/`, days 001–020 |
| Task 3: dispatch policies | Done: six policies plus the supplied baseline (Results below) |
| Task 4: experiments and analysis | Done: `results/<policy>/`, `results/summary.csv`, `results/ablation_heuristic_best.json`; write-up notes in `docs/report_outline.md` |
| Shared code | `solution/policies/helpers.py` (route checks, `service_credit`, insertion engine, heap, UCS), `solution/log_utils.py` (log parsing) |
| Tests | 38 unit and end-to-end tests in `tests/` |

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
├── performance_monitor.py    # Supplied template, completed: calculate_metrics computes the service score
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
    └── heuristic_best.py     # PROPOSED: #8 + adaptive #7 (time-based backlog), heap seed ranking, UCS stop ordering
results/<policy>/<day>/       # log.txt (simulator) + metrics.json (monitor); runtimes.json per policy
results/summary.csv           # every metric, every policy and day (scripts/compare_results.py)
results/ablation_heuristic_best.json  # proposed policy with components switched off
scripts/
├── run_experiments.py        # Simulate + measure many days / policies in one go
├── ablation_heuristic_best.py # Switch the time-based backlog check, heap fallback and UCS off to measure their effect
└── compare_results.py        # Aggregate every metrics.json into results/summary.csv
tests/                        # unittest: helpers vs. simulator, metric and Appendix C contract,
                              #   heap and UCS, every policy valid on every day, end-to-end
docs/report_outline.md        # Task 1–4 write-up notes: key points and where the evidence is
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

Counting undelivered parcels in the denominator matters: the baseline leaves most
parcels undelivered (day_001: 349 of 799 delivered).

## Results (20 historical days)

Means over day_001–day_020; all from `results/<policy>/day_*/metrics.json`.
Simulated-day times measured on one MacBook for all policies.

| Policy | Service score | Worst / best day | Delivered | On time | Late deliveries per day | Km per delivered parcel | Trips per day | Seconds per simulated day |
|---|---|---|---|---|---|---|---|---|
| **Proposed** (`heuristic_best`) | **0.956** | 0.942 / 0.969 | 96.2% | 93.9% | 18.8 | 4.87 | 31.6 | 0.73 |
| #8 + #7 (`urgency_holdback`) | 0.947 | 0.934 / 0.959 | 95.4% | 92.8% | 20.5 | 4.54 | 27.8 | 0.79 |
| #8 (`urgency_insertion`) | 0.914 | 0.879 / 0.949 | 96.0% | 86.2% | 77.9 | 5.37 | 34.3 | 0.62 |
| #4 (`score_insertion`) | 0.908 | 0.872 / 0.949 | 96.0% | 86.6% | 74.4 | 5.38 | 34.7 | 0.60 |
| #3 (`location_batching`) | 0.901 | 0.857 / 0.947 | 96.1% | 84.0% | 95.9 | 5.39 | 34.5 | 0.52 |
| Baseline (`baseline`) | 0.274 | 0.248 / 0.312 | 40.5% | 27.4% | 103.6 | 16.33 | 20.7 | 0.30 |
| #1 (`edd_heap`) | 0.198 | 0.170 / 0.234 | 51.5% | 17.2% | 272.4 | 12.70 | 21.3 | 0.33 |

The proposed policy beats every other policy on all 20 days. Ablation
(`scripts/ablation_heuristic_best.py`): the time-based backlog check is worth
+0.0086 (0.9473 without it) and changes 126 of its decisions; UCS re-ordering
(41 trips) and the heap seed fallback (4 trips) change routes but not the score.

**Recommendation:** `heuristic_best.py`. Grouping parcels by location (0.27 → 0.90)
and holding light vans while the fleet has time to spare (0.91 → 0.956) carry
almost all of the gain.

## Course content used

| IS115 topic | Where |
|---|---|
| Queue / FIFO (Week 5) | The supplied baseline serves parcels first-in, first-out |
| Hash maps (Week 7) | Parcels grouped by location, credit at risk per location, and waiting load per location for the time-based backlog check (`helpers.build_insertion_route`, `heuristic_best`, `location_batching`) |
| Heap-based priority queue, upheap/downheap, bottom-up build (Week 7) | `helpers.HeapPriorityQueue`; seed ranking in `heuristic_best`; deadline queue in `edd_heap` |
| Heap sort (Week 7) | `edd_heap`: repeated `remove_min` gives earliest-deadline order |
| Uniform Cost Search with a priority queue (Week 10) | `helpers.ucs_shortest_tour`: exact shortest visiting order of a trip's stops, used by `heuristic_best` |
| Greedy Algorithm 1 for TSP, nearest neighbour (Week 11 Part 2a) | `location_batching`: after the seed, repeatedly extend to the nearest unvisited location from the last stop |
| Greedy Algorithm 2 for TSP, insertion (Week 11 Part 2a) | `helpers.build_insertion_route` (#4, #8, #8 + #7, `heuristic_best`): grow the trip by inserting the best location at the best position. Generalises Greedy 2: every location and every position are tried, ranked by predicted credit per extra km instead of distance alone |
| Greedy choice rule, "local decisions do not guarantee the best global solution" (Week 11 Part 1) | `edd_heap` always takes the earliest deadline next and scores below the FIFO baseline |
| Exhaustive search vs heuristics; fast / general / optimal trade-off (Week 11 Part 1) | `heuristic_best` uses exact search (UCS) only for trips of at most 7 stops and the greedy order otherwise |
| Intractability, polynomial vs exponential complexity (Week 13) | UCS is exponential, O(m^3 2^m) for m stops, so it is capped at 7 stops; every other step of every policy, including the backlog checks, is polynomial |

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
