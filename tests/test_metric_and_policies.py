"""Tests for the service-credit rule and for policies #3, #4, #8 and #8+#7.

Run from the project root:  python3 -m unittest discover -s tests -t .
"""

import tempfile
import unittest
from pathlib import Path

from simulator.loaders import day_input_paths
from simulator.simulator import Simulator
from solution.policies import (
    helpers, location_batching, score_insertion, urgency_holdback, urgency_insertion,
)

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


class ServiceCreditTests(unittest.TestCase):
    def test_rule(self):
        end = 600.0
        cases = [
            (None, 0.0),        # undelivered
            (500.0, 1.0),       # early: no penalty
            (600.0, 1.0),       # exactly on time
            (600.5, 0.9),       # any lateness starts the first 10-minute block
            (610.0, 0.9),
            (610.5, 0.8),
            (685.0, 0.1),
            (690.0, 0.1),
            (690.5, 0.0),       # more than 90 minutes late
            (900.0, 0.0),       # never negative
        ]
        for delivered_at, expected in cases:
            with self.subTest(delivered_at=delivered_at):
                self.assertAlmostEqual(helpers.service_credit(delivered_at, end), expected)

    def test_float_noise_does_not_cost_a_step(self):
        self.assertAlmostEqual(helpers.service_credit(610.0000000001, 600.0), 0.9)
        self.assertAlmostEqual(helpers.service_credit(600.0000000001, 600.0), 1.0)


class PolicyValidityTests(unittest.TestCase):
    """Every route returned on every day passes the simulator's own validation."""

    def run_policy(self, policy, day):
        checked = []

        def wrapped(parcel, context):
            route = policy(parcel, context)
            self.assertEqual(helpers.route_violations(route, parcel, context), [], (day, route))
            checked.append(len(route))
            return route

        with tempfile.TemporaryDirectory() as tmp:
            simulator = Simulator(*day_input_paths(DATA, day), dispatch_policy=wrapped)
            simulator.run(Path(tmp) / "log.txt")
        return simulator

    def test_location_batching_all_days(self):
        for number in range(1, 21):
            with self.subTest(day=number):
                self.assertTrue(self.run_policy(location_batching.dispatch, f"day_{number:03d}").delivered)

    def test_score_insertion_all_days(self):
        for number in range(1, 21):
            with self.subTest(day=number):
                self.assertTrue(self.run_policy(score_insertion.dispatch, f"day_{number:03d}").delivered)

    def test_urgency_insertion_all_days(self):
        for number in range(1, 21):
            with self.subTest(day=number):
                self.assertTrue(self.run_policy(urgency_insertion.dispatch, f"day_{number:03d}").delivered)

    def test_urgency_holdback_all_days(self):
        for number in range(1, 21):
            with self.subTest(day=number):
                self.assertTrue(self.run_policy(urgency_holdback.dispatch, f"day_{number:03d}").delivered)

    def test_hold_rule(self):
        parcel = {"P1": {"arrival_time": 480.0, "delivery_location_id": "L1",
                         "delivery_window_start": 480.0, "delivery_window_end": 1080.0, "size": 1.0,
                         "delivery_time": None, "vehicle_assigned": None, "trip_id": None}}
        context = {"current_time": 540.0, "vehicle_id": 1, "capacity": 30.0,
                   "travel_distance": {"HUB": {"HUB": 0.0, "L1": 10.0}, "L1": {"HUB": 10.0, "L1": 0.0}},
                   "departure_delay": 30.0, "return_cutoff": 1080.0, "max_trip_distance_km": 320.0,
                   "fleet": {1: {"available_at": 540.0, "max_trip_distance_km": 320.0}}}
        self.assertTrue(urgency_holdback.should_hold(["P1"], parcel, context))     # light, not urgent
        parcel["P1"]["delivery_window_end"] = 580.0                                  # arrives 580: at risk
        self.assertFalse(urgency_holdback.should_hold(["P1"], parcel, context))
        parcel["P1"]["delivery_window_end"] = 1080.0
        context["current_time"] = 1000.0                                             # late in the day
        self.assertFalse(urgency_holdback.should_hold(["P1"], parcel, context))
        parcel["P1"]["size"] = 25.0
        context["current_time"] = 540.0                                              # heavy enough
        self.assertFalse(urgency_holdback.should_hold(["P1"], parcel, context))
        self.assertFalse(urgency_holdback.should_hold([], parcel, context))

    def test_policies_do_not_modify_inputs(self):
        import copy

        def guard(policy):
            def wrapped(parcel, context):
                before = (copy.deepcopy(parcel), copy.deepcopy(context))
                route = policy(parcel, context)
                self.assertEqual((parcel, context), before)
                return route
            return wrapped

        for policy in (location_batching.dispatch, score_insertion.dispatch,
                       urgency_insertion.dispatch, urgency_holdback.dispatch):
            with tempfile.TemporaryDirectory() as tmp:
                Simulator(*day_input_paths(DATA, "day_001"), dispatch_policy=guard(policy)).run(
                    Path(tmp) / "log.txt")


if __name__ == "__main__":
    unittest.main()
