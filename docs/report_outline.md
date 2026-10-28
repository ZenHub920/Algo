# IS115 Project Report — Outline

Skeleton only. Fill each section as the work is done.

## 1. Performance metric

- [ ] Metric chosen: _TBD_
- [ ] Why it matters for last-mile delivery
- [ ] Exact calculation (formula, inputs used from parcels / distances / config / events)
- [ ] Assumptions (e.g. treatment of undelivered parcels, early vs late deliveries)
- [ ] Why it does not lead to a trivial approach

## 2. Baseline performance

- [ ] Baseline policy summary (FIFO first-fit, ignores delivery windows)
- [ ] Results for day_001 – day_020 (table from `results/summary.csv`)
- [ ] Observations

## 3. Dispatch algorithms

For each approach:

- [ ] Idea and pseudocode
- [ ] Module: `solution/policies/<name>.py`
- [ ] Time complexity per `dispatch` call (in terms of n available parcels, L locations, …)
- [ ] Space complexity

## 4. Experiments and analysis

- [ ] Setup (same 20 days, same simulator, same metric)
- [ ] Results table and charts (all policies vs baseline)
- [ ] Runtime comparison (`results/<policy>/runtimes.json`)
- [ ] Trade-offs
- [ ] Where each approach performs well / poorly, and why
- [ ] Recommended approach (`heuristic_best.py`) and justification
