"""Calculate performance metrics from one simulation run's event log."""

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

from simulator.loaders import day_input_paths
from solution.log_utils import (
    extract_deliveries, extract_trips, join_outcomes, parse_config, parse_distances,
    parse_parcels, validate_metrics,
)
from solution.policies.helpers import HUB, TIME_EPSILON, lateness, service_credit


def calculate_metrics(
    parcels: List[Dict[str, str]],
    distances: List[Dict[str, str]],
    config: Dict[str, Any],
    events: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Return a JSON-serializable dictionary for the chosen performance metric.

    parcels and distances are the rows of the day's CSV files, config is the
    contents of config.json, and events are the records from the run's log.
    CSV values are strings, so convert them before calculating. In particular,
    parcel times are "HH:MM" strings while event times are minutes after
    midnight: "17:00" is 17 * 60 = 1020.
    """

    # --- Parse raw inputs into typed structures (metric-neutral) -------------
    # All parcels in the day's CSV, including ones never delivered.
    parcel_info = parse_parcels(parcels)          # {parcel_id: {arrival_time, delivery_location_id,
                                                  #   delivery_window_start/end (minutes), size}}
    dist = parse_distances(distances)             # {origin: {destination: km}}
    fleet = parse_config(config)                  # {number_of_vehicles, capacity, vehicle_range_km}
    deliveries = extract_deliveries(events)       # {parcel_id: {time, vehicle_id, trip_id}}
    outcomes = join_outcomes(parcel_info, deliveries)  # every parcel + delivered/delivery_time
    trips = extract_trips(events)                 # {(vehicle_id, trip_id): {departure_time,
                                                  #   parcel_ids, delivery_times, return_time}}

    # --- Performance metric: weighted service score (Task 1) -----------------
    # Each parcel earns credit (helpers.service_credit, shared with policies):
    #   1.0 if delivered by its window end (early delivery is not penalised),
    #   minus 0.1 for every started 10 minutes late (0 once > 90 min late),
    #   0 if never delivered.
    # service_score = total credit / ALL parcels in the day's file, so leaving
    # parcels undelivered can never raise the score (avoids a trivial policy).
    credits = {pid: service_credit(r["delivery_time"], r["delivery_window_end"])
               for pid, r in outcomes.items()}
    total = len(outcomes)
    total_credit = math.fsum(credits.values())

    delivered = [r for r in outcomes.values() if r["delivered"]]
    late = [lateness(r["delivery_time"], r["delivery_window_end"]) for r in delivered]
    late = [minutes for minutes in late if minutes > TIME_EPSILON]
    early = sum(1 for r in delivered if r["delivery_time"] < r["delivery_window_start"] - TIME_EPSILON)
    zero_credit = sum(1 for pid, r in outcomes.items() if r["delivered"] and credits[pid] == 0.0)

    # Supporting figures (explain results; they do not rank policies).
    trip_km = []
    trip_load = []
    for trip in trips.values():
        stops = [HUB] + [parcel_info[p]["delivery_location_id"] for p in trip["parcel_ids"]] + [HUB]
        trip_km.append(math.fsum(dist[a][b] for a, b in zip(stops, stops[1:])))
        trip_load.append(math.fsum(parcel_info[p]["size"] for p in trip["parcel_ids"]))
    total_km = math.fsum(trip_km)

    def ratio(numerator: float, denominator: float) -> Optional[float]:
        return round(numerator / denominator, 6) if denominator else None

    result: Dict[str, Any] = {
        "service_score": ratio(total_credit, total),          # PRIMARY METRIC, 0..1
        "total_credit": round(total_credit, 6),
        "parcels_total": total,
        "parcels_delivered": len(delivered),
        "delivery_rate": ratio(len(delivered), total),
        "on_time_deliveries": len(delivered) - len(late),
        "on_time_rate": ratio(len(delivered) - len(late), total),
        "late_deliveries": len(late),
        "zero_credit_deliveries": zero_credit,
        "mean_minutes_late": round(math.fsum(late) / len(late), 6) if late else 0.0,
        "early_deliveries": early,
        "trips": len(trips),
        "total_km": round(total_km, 6),
        "km_per_delivered_parcel": ratio(total_km, len(delivered)),
        "mean_load_utilisation": ratio(math.fsum(trip_load), len(trip_load) * fleet["capacity"]),
    }

    # Appendix C: string keys, JSON-serializable, finite numbers only.
    return validate_metrics(result)


def main(argv: Optional[List[str]] = None) -> int:
    """Load one day's inputs and event log, then write the metrics report."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"),
                        help="directory containing dist.csv, config.json and demand/")
    parser.add_argument("--day", required=True, help="day identifier, for example day_001")
    parser.add_argument("--log", type=Path, required=True,
                        help="event log from a simulator run")
    parser.add_argument("--output", type=Path,
                        help="JSON report (default: metrics.json beside the selected log)")
    args = parser.parse_args(argv)
    try:
        parcel_path, distance_path, config_path = day_input_paths(args.data, args.day)
        output = args.output if args.output is not None else args.log.with_name("metrics.json")
        # The input files all live in the data directory, so this also protects them.
        if output.resolve() == args.data.resolve() or args.data.resolve() in output.resolve().parents:
            raise ValueError("report output must be outside the input data directory")
        if output.resolve() == args.log.resolve():
            raise ValueError("report output must not overwrite the log")
        with parcel_path.open(newline="", encoding="utf-8-sig") as stream:
            parcels = list(csv.DictReader(stream))
        with distance_path.open(newline="", encoding="utf-8-sig") as stream:
            distances = list(csv.DictReader(stream))
        config = json.loads(config_path.read_text(encoding="utf-8-sig"))
        with args.log.open(encoding="utf-8") as stream:
            events = [json.loads(line) for line in stream if line.strip()]
        metrics = calculate_metrics(parcels, distances, config, events)
        report = json.dumps(metrics, indent=2, allow_nan=False) + "\n"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report, encoding="utf-8")
    except (OSError, ValueError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print(f"Metrics report: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
