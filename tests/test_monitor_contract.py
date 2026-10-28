"""Checks for the calculate_metrics contract in Appendix C.

Run from the project root:  python3 -m unittest discover -s tests -t .
"""

import csv
import json
import math
import tempfile
import unittest
from pathlib import Path

from simulator.loaders import day_input_paths
from simulator.simulator import Simulator, load_policy
from solution import log_utils
from solution.performance_monitor import calculate_metrics

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DAY = "day_001"


def raw_inputs():
    """Load inputs exactly as performance_monitor.main does (CSV rows of strings)."""
    parcels_path, distances_path, config_path = day_input_paths(DATA, DAY)
    with parcels_path.open(newline="", encoding="utf-8-sig") as stream:
        parcels = list(csv.DictReader(stream))
    with distances_path.open(newline="", encoding="utf-8-sig") as stream:
        distances = list(csv.DictReader(stream))
    config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    return parcels, distances, config


class MonitorContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        log = Path(cls.tmp.name) / "log.txt"
        paths = day_input_paths(DATA, DAY)
        Simulator(*paths, dispatch_policy=load_policy("solution.policies.baseline")).run(log)
        cls.events = log_utils.load_events(log)
        cls.parcels, cls.distances, cls.config = raw_inputs()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_raw_inputs_are_strings_with_parcel_id(self):
        row = self.parcels[0]
        self.assertIn("parcel_id", row)
        self.assertNotIn("delivery_time", row)
        self.assertTrue(all(isinstance(value, str) for value in row.values()))
        self.assertEqual(set(self.distances[0]), {"location_1", "location_2", "dist"})

    def test_parsing_converts_types(self):
        info = log_utils.parse_parcels(self.parcels)
        record = info[self.parcels[0]["parcel_id"]]
        self.assertIsInstance(record["arrival_time"], float)
        self.assertIsInstance(record["size"], float)
        self.assertEqual(log_utils.parse_parcels([{**self.parcels[0], "arrival_time": "17:00"}])
                         [self.parcels[0]["parcel_id"]]["arrival_time"], 1020.0)
        dist = log_utils.parse_distances(self.distances)
        self.assertEqual(dist["HUB"]["HUB"], 0.0)
        fleet = log_utils.parse_config(self.config)
        self.assertEqual(fleet, {"number_of_vehicles": 10, "capacity": 30.0, "vehicle_range_km": 320.0})

    def test_join_covers_undelivered_parcels(self):
        outcomes = log_utils.join_outcomes(log_utils.parse_parcels(self.parcels),
                                           log_utils.extract_deliveries(self.events))
        self.assertEqual(len(outcomes), len(self.parcels))
        delivered = [r for r in outcomes.values() if r["delivered"]]
        missing = log_utils.undelivered_ids(outcomes)
        self.assertEqual(len(delivered) + len(missing), len(self.parcels))
        self.assertTrue(missing, "baseline day_001 leaves some parcels undelivered")
        self.assertIsNone(outcomes[missing[0]]["delivery_time"])
        self.assertTrue(all(r["delivery_time"] is not None for r in delivered))

    def test_calculate_metrics_return_value(self):
        metrics = calculate_metrics(self.parcels, self.distances, self.config, self.events)
        self.assertIsInstance(metrics, dict)
        self.assertTrue(all(isinstance(key, str) for key in metrics))
        json.dumps(metrics, allow_nan=False)  # Same check the supplied script applies
        self.assertEqual(metrics["number_of_trips"],
                         len(log_utils.events_of_type(self.events, "hub_departure")))

    def test_validate_metrics_rejects_bad_values(self):
        log_utils.validate_metrics({"score": 0.8, "by_day": {"a": [1, 2]}, "note": None})
        for bad in ({"score": math.nan}, {"score": math.inf}, {1: 0.5},
                    {"nested": {"x": -math.inf}}, {"s": {1, 2}}, [("score", 1)]):
            with self.assertRaises(ValueError):
                log_utils.validate_metrics(bad)


if __name__ == "__main__":
    unittest.main()
