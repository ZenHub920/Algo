"""End-to-end checks: policies run in the real simulator and logs parse cleanly.

Run from the project root:  python3 -m unittest discover -s tests -t .
"""

import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from simulator.loaders import day_input_paths
from simulator.simulator import Simulator, load_policy
from solution import log_utils

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DAY = "day_001"


def simulate(policy_module: str, log_path: Path) -> Simulator:
    parcels, distances, config = day_input_paths(DATA, DAY)
    simulator = Simulator(parcels, distances, config, dispatch_policy=load_policy(policy_module))
    simulator.run(log_path)
    return simulator


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_baseline_runs_and_log_parses(self):
        simulator = simulate("solution.policies.baseline", self.dir / "log.txt")
        events = log_utils.load_events(self.dir / "log.txt")
        deliveries = log_utils.extract_deliveries(events)
        trips = log_utils.extract_trips(events)

        self.assertEqual(set(deliveries), simulator.delivered)
        self.assertEqual(len(trips), len(log_utils.events_of_type(events, "hub_departure")))
        for trip in trips.values():
            self.assertIsNotNone(trip["return_time"])
            self.assertLessEqual(trip["return_time"], 1080.0)
            self.assertEqual(len(trip["parcel_ids"]), len(trip["delivery_times"]))
            self.assertEqual(trip["delivery_times"], sorted(trip["delivery_times"]))

    def test_trip_distance_matches_log(self):
        simulate("solution.policies.baseline", self.dir / "log.txt")
        events = log_utils.load_events(self.dir / "log.txt")
        parcels_path, distances_path, _ = day_input_paths(DATA, DAY)
        with parcels_path.open(newline="", encoding="utf-8-sig") as stream:
            parcels = log_utils.parse_parcels(list(csv.DictReader(stream)))
        with distances_path.open(newline="", encoding="utf-8-sig") as stream:
            dist = log_utils.parse_distances(list(csv.DictReader(stream)))
        for trip in log_utils.extract_trips(events).values():
            stops = ["HUB"] + [parcels[p]["delivery_location_id"] for p in trip["parcel_ids"]] + ["HUB"]
            km = sum(dist[a][b] for a, b in zip(stops, stops[1:]))
            self.assertAlmostEqual(trip["return_time"] - trip["departure_time"], km, places=6)

    def test_helpers_agree_with_simulator_validation(self):
        """Every route the baseline returns is accepted by the simulator and by helpers."""
        from solution.policies import baseline, helpers

        checked = []

        def checked_dispatch(parcel, context):
            route = baseline.dispatch(parcel, context)
            self.assertEqual(helpers.route_violations(route, parcel, context), [])
            checked.append(len(route))
            return route

        parcels, distances, config = day_input_paths(DATA, DAY)
        Simulator(parcels, distances, config, dispatch_policy=checked_dispatch).run(self.dir / "log.txt")
        self.assertTrue(any(checked))

    def test_heuristic_best_runs(self):
        simulator = simulate("solution.policies.heuristic_best", self.dir / "log.txt")
        self.assertGreater(len(simulator.delivered), 0)

    def test_performance_monitor_cli(self):
        simulate("solution.policies.baseline", self.dir / "log.txt")
        result = subprocess.run(
            [sys.executable, "-m", "solution.performance_monitor", "--data", str(DATA),
             "--day", DAY, "--log", str(self.dir / "log.txt")],
            cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.dir / "metrics.json").exists())


if __name__ == "__main__":
    unittest.main()
