"""Run one or more policies across many days, then the performance monitor on each log.

This automates Task 2 Step 1/Step 4 and the Task 4 experiments; it only calls
the supplied command-line entry points, so results are identical to running
them by hand.

Examples (from the project root):
    python3 scripts/run_experiments.py --policy solution.policies.baseline
    python3 scripts/run_experiments.py --policy solution.policies.baseline \
        --policy solution.policies.heuristic_best --days 1-5
    python3 scripts/run_experiments.py --policy solution.policies.baseline --monitor-only

Outputs, per policy P (last part of the module path) and day D:
    results/P/D/log.txt        from the simulator
    results/P/D/metrics.json   from solution/performance_monitor.py
    results/P/runtimes.json    wall-clock seconds of each simulator run
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent


def parse_days(spec: str) -> List[str]:
    """'1-20' or '1,3,5' or '1-3,7' -> ['day_001', ...]."""

    numbers: List[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            low, high = (int(x) for x in part.split("-", 1))
            numbers.extend(range(low, high + 1))
        elif part:
            numbers.append(int(part))
    return [f"day_{n:03d}" for n in numbers]


def run(command: List[str]) -> subprocess.CompletedProcess:
    """Run a command from the project root, capturing output."""

    return subprocess.run(command, cwd=ROOT, capture_output=True, text=True)


def run_policy(policy: str, days: List[str], data: str, simulate: bool, monitor: bool) -> bool:
    """Simulate and/or monitor every day for one policy; return True if all succeeded."""

    name = policy.rsplit(".", 1)[-1]
    runtimes: Dict[str, float] = {}
    ok = True
    for day in days:
        output = Path("results") / name / day
        if simulate:
            started = time.perf_counter()
            result = run([sys.executable, "-m", "simulator", "--policy", policy,
                          "--data", data, "--day", day, "--output", str(output)])
            runtimes[day] = round(time.perf_counter() - started, 4)
            if result.returncode != 0:
                print(f"[{name}] {day}: SIMULATION FAILED\n{result.stderr.strip()}")
                ok = False
                continue  # A failed run's log may be incomplete; do not measure it.
            delivered = next((line for line in result.stdout.splitlines()
                              if line.startswith("Delivered:")), "")
            print(f"[{name}] {day}: simulated in {runtimes[day]:.2f}s  {delivered}")
        if monitor:
            result = run([sys.executable, "-m", "solution.performance_monitor",
                          "--data", data, "--day", day, "--log", str(output / "log.txt")])
            if result.returncode != 0:
                print(f"[{name}] {day}: MONITOR FAILED\n{result.stderr.strip()}")
                ok = False
    if simulate and runtimes:
        path = ROOT / "results" / name / "runtimes.json"
        existing: Dict[str, float] = {}
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
        existing.update(runtimes)
        path.write_text(json.dumps(dict(sorted(existing.items())), indent=2) + "\n", encoding="utf-8")
    return ok


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--policy", action="append", required=True,
                        help="policy module path; repeat for several policies")
    parser.add_argument("--days", default="1-20", help="day numbers, e.g. 1-20 or 1,4,7 (default 1-20)")
    parser.add_argument("--data", default="data", help="data directory (default: data)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--simulate-only", action="store_true", help="skip the performance monitor")
    group.add_argument("--monitor-only", action="store_true", help="re-measure existing logs only")
    args = parser.parse_args(argv)

    days = parse_days(args.days)
    all_ok = True
    for policy in args.policy:
        all_ok &= run_policy(policy, days, args.data,
                             simulate=not args.monitor_only, monitor=not args.simulate_only)
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
