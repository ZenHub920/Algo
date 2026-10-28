"""Metric-neutral parsing helpers for solution/performance_monitor.py.

calculate_metrics() receives raw inputs: CSV rows as strings, config as a
dict, and log events as dicts. These functions turn them into convenient,
typed structures. They do not compute any performance metric.

Usage inside calculate_metrics:

    from solution.log_utils import parse_parcels, parse_distances, extract_trips, ...

    parcel_info = parse_parcels(parcels)       # {parcel_id: {... times in minutes ...}}
    dist = parse_distances(distances)          # {origin: {destination: km}}
    fleet = parse_config(config)               # numeric config values
    deliveries = extract_deliveries(events)    # {parcel_id: {time, vehicle_id, trip_id}}
    outcomes = join_outcomes(parcel_info, deliveries)  # every parcel, delivered or not
    trips = extract_trips(events)              # {(vehicle_id, trip_id): {...}}
    ...
    return validate_metrics(result)            # Appendix C: str keys, finite numbers

Standard library only.
"""

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union

from simulator.loaders import parse_time

Event = Dict[str, Any]
TripKey = Tuple[int, int]  # (vehicle_id, trip_id)


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

def parse_parcels(rows: List[Dict[str, str]]) -> Dict[str, Dict[str, Any]]:
    """Convert demand CSV rows into {parcel_id: record}; HH:MM becomes minutes, size a float."""

    parsed: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        parsed[row["parcel_id"].strip()] = {
            "arrival_time": parse_time(row["arrival_time"].strip()),
            "delivery_location_id": row["delivery_location_id"].strip(),
            "delivery_window_start": parse_time(row["delivery_window_start"].strip()),
            "delivery_window_end": parse_time(row["delivery_window_end"].strip()),
            "size": float(row["size"]),
        }
    return parsed


def parse_distances(rows: List[Dict[str, str]]) -> Dict[str, Dict[str, float]]:
    """Convert dist.csv rows into a nested {origin: {destination: km}} lookup."""

    lookup: Dict[str, Dict[str, float]] = {}
    for row in rows:
        lookup.setdefault(row["location_1"].strip(), {})[row["location_2"].strip()] = float(row["dist"])
    return lookup


def parse_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise config.json: number_of_vehicles as int, capacity and range as floats."""

    return {
        "number_of_vehicles": int(config["number_of_vehicles"]),
        "capacity": float(config["capacity"]),
        "vehicle_range_km": float(config["vehicle_range_km"]),
    }


def load_events(path: Union[str, Path]) -> List[Event]:
    """Read a JSON Lines event log (Appendix B)."""

    with Path(path).open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


# ---------------------------------------------------------------------------
# Event log views
# ---------------------------------------------------------------------------

def events_of_type(events: List[Event], event_type: str) -> List[Event]:
    """All events of one type, in log order."""

    return [event for event in events if event["event_type"] == event_type]


def extract_deliveries(events: List[Event]) -> Dict[str, Dict[str, Any]]:
    """{parcel_id: {"time", "vehicle_id", "trip_id"}} for every delivered parcel."""

    return {
        event["parcel_id"]: {
            "time": event["time"],
            "vehicle_id": event["vehicle_id"],
            "trip_id": event["trip_id"],
        }
        for event in events_of_type(events, "delivery")
    }


def extract_arrivals(events: List[Event]) -> Dict[str, float]:
    """{parcel_id: hub arrival time} for every parcel_arrival event."""

    return {event["parcel_id"]: event["time"] for event in events_of_type(events, "parcel_arrival")}


def extract_trips(events: List[Event]) -> Dict[TripKey, Dict[str, Any]]:
    """Rebuild each completed or in-progress trip from the log.

    Returns {(vehicle_id, trip_id): {
        "vehicle_id", "trip_id",
        "departure_time",           # hub_departure time
        "parcel_ids",               # in delivery order
        "delivery_times",           # aligned with parcel_ids
        "return_time",              # vehicle_return that ends the trip; None if not in log
    }}

    The 08:00 vehicle_return records that initialise vehicles are not trips and
    are ignored: a vehicle_return only closes a trip that has departed.
    """

    trips: Dict[TripKey, Dict[str, Any]] = {}
    open_trip: Dict[int, TripKey] = {}  # vehicle_id -> trip currently on the road
    for event in events:
        kind = event["event_type"]
        if kind == "hub_departure":
            key = (event["vehicle_id"], event["trip_id"])
            trips[key] = {
                "vehicle_id": event["vehicle_id"],
                "trip_id": event["trip_id"],
                "departure_time": event["time"],
                "parcel_ids": [],
                "delivery_times": [],
                "return_time": None,
            }
            open_trip[event["vehicle_id"]] = key
        elif kind == "delivery":
            trip = trips[(event["vehicle_id"], event["trip_id"])]
            trip["parcel_ids"].append(event["parcel_id"])
            trip["delivery_times"].append(event["time"])
        elif kind == "vehicle_return" and event["vehicle_id"] in open_trip:
            trips[open_trip.pop(event["vehicle_id"])]["return_time"] = event["time"]
    return trips


def join_outcomes(
    parcel_info: Dict[str, Dict[str, Any]], deliveries: Dict[str, Dict[str, Any]]
) -> Dict[str, Dict[str, Any]]:
    """Match every input parcel to its delivery record by parcel_id (Appendix C).

    Covers ALL parcels in the day's CSV, including ones never delivered.
    Each record is the parsed parcel plus:
        "delivered": bool
        "delivery_time", "vehicle_id", "trip_id": from the log, or None if undelivered
    """

    joined: Dict[str, Dict[str, Any]] = {}
    for parcel_id, record in parcel_info.items():
        delivery = deliveries.get(parcel_id)
        joined[parcel_id] = {
            **record,
            "delivered": delivery is not None,
            "delivery_time": delivery["time"] if delivery else None,
            "vehicle_id": delivery["vehicle_id"] if delivery else None,
            "trip_id": delivery["trip_id"] if delivery else None,
        }
    unknown = set(deliveries) - set(parcel_info)
    if unknown:
        raise ValueError(f"log delivers parcels missing from the demand file: {sorted(unknown)[:5]}")
    return joined


def undelivered_ids(outcomes: Dict[str, Dict[str, Any]]) -> List[str]:
    """Sorted IDs of parcels with no delivery record."""

    return sorted(parcel_id for parcel_id, record in outcomes.items() if not record["delivered"])


def trips_by_vehicle(trips: Dict[TripKey, Dict[str, Any]]) -> Dict[int, List[Dict[str, Any]]]:
    """Group trips by vehicle, each list ordered by trip_id."""

    grouped: Dict[int, List[Dict[str, Any]]] = {}
    for (vehicle_id, _), trip in sorted(trips.items()):
        grouped.setdefault(vehicle_id, []).append(trip)
    return grouped


# ---------------------------------------------------------------------------
# Output contract (Appendix C: calculate_metrics return value)
# ---------------------------------------------------------------------------

def validate_metrics(metrics: Any) -> Dict[str, Any]:
    """Check calculate_metrics' return value against Appendix C and return it unchanged.

    Rules: a dict with string keys; values JSON-serializable; every number
    finite (no NaN or infinity). Nested lists/dicts are checked recursively.
    Raises ValueError naming the offending key.
    """

    if not isinstance(metrics, dict):
        raise ValueError("calculate_metrics must return a dict")

    def check(value: Any, where: str) -> None:
        if value is None or isinstance(value, (str, bool)):
            return
        if isinstance(value, (int, float)):
            if not math.isfinite(value):
                raise ValueError(f"{where}: {value!r} is not finite")
            return
        if isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                check(item, f"{where}[{index}]")
            return
        if isinstance(value, dict):
            for key, item in value.items():
                if not isinstance(key, str):
                    raise ValueError(f"{where}: key {key!r} is not a string")
                check(item, f"{where}.{key}")
            return
        raise ValueError(f"{where}: {type(value).__name__} is not JSON-serializable")

    for key, value in metrics.items():
        if not isinstance(key, str):
            raise ValueError(f"metric name {key!r} is not a string")
        check(value, key)
    return metrics
