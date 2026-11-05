# IS115 Project Report — Outline and Key Points

Write-up notes for Tasks 1–4: the point each section makes and where its
evidence is in this repo. All figures are means over day_001–day_020.

## 1. Performance metric

- **Metric:** weighted service score. Per parcel: 1.0 if delivered by the window end
  (early is not penalised), minus 0.1 for every started 10 minutes late, never below 0;
  0 if never delivered. Score = total credit ÷ all parcels in the day's file.
- **Why it matters:** customers judge the last mile by punctuality; a slightly late
  parcel is worth more than none, one hours late is close to worthless.
- **Calculation:** `calculate_metrics` in `solution/performance_monitor.py`, using
  `helpers.service_credit` (shared with the policies) and `log_utils.join_outcomes`
  to match deliveries to every parcel by `parcel_id`.
- **Assumptions:** early delivery is free (the window is "preferred"); any lateness
  costs at least 0.1; the denominator includes undelivered and undeliverable parcels.
- **Not trivial:** withholding parcels can never raise the score (doing nothing scores 0),
  unlike distance- or trip-count metrics.
- **Sensitivity:** with 0.1 per 5, 10, 15, 20, 30 or 60 minutes, the waiting policies
  stay best; their lead shrinks as the penalty gets more lenient (0.049 → 0.004).

## 2. Baseline performance

- **Policy:** supplied FIFO first-fit; ignores windows and geography.
- **Result:** service score 0.274; 40.5% delivered, 27.4% on time; every late delivery
  more than 90 minutes late. Evidence: `results/baseline/`, `results/summary.csv`.
- **Observation:** trips use about 252 of 320 km while vans are half full, so range,
  not capacity, is the limit: 16.3 km per delivered parcel.

## 3. Dispatch algorithms

Each policy adds one idea to the previous one (`solution/policies/`); complexity per
`dispatch` call with n waiting parcels, L locations, m stops, k parcels per trip,
V vans.

| Policy | Idea | Time per call | Space |
|---|---|---|---|
| #1 `edd_heap` | Earliest deadline first via heap priority queue (heap sort) | O(n log n) | O(n) |
| #3 `location_batching` | Most urgent location first, then nearest neighbour (Greedy 1) | O(n log n + m·L) | O(n + L) |
| #4 `score_insertion` | Greedy insertion by predicted credit per extra km (Greedy 2) | O(m²·(L·k + n)) | O(n + L + k) |
| #8 `urgency_insertion` | #4, starting where the most credit is at risk | O(n + V) + #4 | O(n + L + k) |
| #8 + #7 `urgency_holdback` | #8 + hold light, non-urgent vans one round | #8 + O(k) | O(n + L + k) |
| Proposed `heuristic_best` | #8 + adaptive wait (capacity- and time-based backlog checks), heap-ranked start, UCS stop order (≤ 7 stops) | #8 + O(L) heap + O(m³·2ᵐ) UCS + O(n + L + V) checks | O(n + L + k + m·2ᵐ) |

Course content: hash maps and heap priority queue (Week 7), Uniform Cost Search
(Week 10), greedy TSP algorithms 1 and 2 (Week 11), intractability (Week 13); see
the README's "Course content used".

## 4. Experiments and analysis

- **Setup:** all seven policies on the same 20 days, same simulator, same metric;
  `scripts/run_experiments.py`, `scripts/compare_results.py`.
- **Results:** README "Results" table; per day and per metric in `results/summary.csv`.
  Proposed 0.956 (worst day 0.942) beats every policy on all 20 days.
- **Runtime:** 0.30 s (baseline) to 0.79 s (#8 + #7) per simulated day;
  `results/<policy>/runtimes.json`.
- **What drives the gains:** grouping by location 0.274 → 0.901; holding light vans
  0.914 → 0.947; the time-based backlog check 0.947 → 0.956 by delivering parcels
  that arrive after 15:00 instead of stranding them.
- **Ablation** (`results/ablation_heuristic_best.json`): time-based check +0.0086,
  126 decisions changed; UCS re-orders 41 trips (about 166 km saved over 20 days)
  and the heap fallback 4, with no change in score.
- **Where approaches fail:** EDD (0.198) chases parcels already too late; #4 abandons
  parcels it cannot deliver on time, so they end up very late; waiting policies lose to
  never-waiting ones when arrivals are spread evenly through the day.
- **Trade-offs:** better policies cost more computation (still under 1 s per day) and,
  for the proposed policy, more trips (31.6 against 27.8) to deliver more parcels.
- **Recommended approach:** `heuristic_best.py`.
