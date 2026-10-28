"""Collect every results/<policy>/<day>/metrics.json into one comparison table.

Metric-agnostic: it reports whatever numeric keys calculate_metrics returns.

Examples (from the project root):
    python3 scripts/compare_results.py
    python3 scripts/compare_results.py --policies baseline heuristic_best

Writes results/summary.csv (one row per policy, day and metric) and prints, for
each metric, the per-policy mean, min, max and number of days.
"""

import argparse
import csv
import json
import statistics
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"


def collect(policies: Optional[List[str]] = None) -> List[Dict[str, object]]:
    """Return rows of {policy, day, metric, value} for every numeric metric found."""

    rows: List[Dict[str, object]] = []
    policy_dirs = sorted(p for p in RESULTS.iterdir() if p.is_dir()) if RESULTS.exists() else []
    for policy_dir in policy_dirs:
        if policies and policy_dir.name not in policies:
            continue
        for metrics_path in sorted(policy_dir.glob("day_*/metrics.json")):
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            for key, value in metrics.items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    rows.append({"policy": policy_dir.name, "day": metrics_path.parent.name,
                                 "metric": key, "value": value})
    return rows


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--policies", nargs="*", help="policy folder names (default: all)")
    parser.add_argument("--output", type=Path, default=RESULTS / "summary.csv")
    args = parser.parse_args(argv)

    rows = collect(args.policies)
    if not rows:
        print("No metrics.json files found under results/.")
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["policy", "day", "metric", "value"])
        writer.writeheader()
        writer.writerows(rows)

    for metric in sorted({str(row["metric"]) for row in rows}):
        print(f"\n{metric}")
        print(f"  {'policy':<24}{'days':>6}{'mean':>14}{'min':>14}{'max':>14}")
        for policy in sorted({str(row["policy"]) for row in rows}):
            values = [float(row["value"]) for row in rows
                      if row["metric"] == metric and row["policy"] == policy]
            if values:
                print(f"  {policy:<24}{len(values):>6}{statistics.mean(values):>14.4f}"
                      f"{min(values):>14.4f}{max(values):>14.4f}")
    print(f"\nWrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
