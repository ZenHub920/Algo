"""Tests for solution/policies/helpers.py using the toy example from the brief.

Run from the project root:  python3 -m unittest discover -s tests -t .
"""

import copy
import unittest

from solution.policies import helpers


def make_parcel():
    return {
        "P001": {"arrival_time": 480.0, "delivery_location_id": "L001",
                 "delivery_window_start": 540.0, "delivery_window_end": 660.0, "size": 4.0,
                 "delivery_time": None, "vehicle_assigned": None, "trip_id": None},
        "P002": {"arrival_time": 510.0, "delivery_location_id": "L002",
                 "delivery_window_start": 540.0, "delivery_window_end": 720.0, "size": 6.0,
                 "delivery_time": None, "vehicle_assigned": None, "trip_id": None},
        "P003": {"arrival_time": 500.0, "delivery_location_id": "L001",
                 "delivery_window_start": 540.0, "delivery_window_end": 720.0, "size": 1.0,
                 "delivery_time": None, "vehicle_assigned": 2, "trip_id": 1},
    }


def make_context():
    return {
        "current_time": 540.0,
        "vehicle_id": 1,
        "capacity": 30.0,
        "travel_distance": {
            "HUB": {"HUB": 0.0, "L001": 10.0, "L002": 15.0},
            "L001": {"HUB": 10.0, "L001": 0.0, "L002": 8.0},
            "L002": {"HUB": 15.0, "L001": 8.0, "L002": 0.0},
        },
        "departure_delay": 30.0,
        "return_cutoff": 1080.0,
        "max_trip_distance_km": 320.0,
        "fleet": {1: {"available_at": 540.0, "max_trip_distance_km": 320.0}},
    }


class HelperTests(unittest.TestCase):
    def setUp(self):
        self.parcel = make_parcel()
        self.context = make_context()

    def test_available_excludes_assigned(self):
        self.assertEqual(helpers.available_parcel_ids(self.parcel), ["P001", "P002"])

    def test_route_distance_and_times(self):
        route = ["P001", "P002"]
        self.assertEqual(helpers.route_locations(route, self.parcel), ["HUB", "L001", "L002", "HUB"])
        self.assertAlmostEqual(helpers.route_distance(route, self.parcel, self.context["travel_distance"]), 33.0)
        self.assertEqual(helpers.departure_time(self.context), 570.0)
        self.assertEqual(helpers.delivery_times(route, self.parcel, self.context), [580.0, 588.0])
        self.assertEqual(helpers.return_time(route, self.parcel, self.context), 603.0)
        self.assertEqual(helpers.route_load(route, self.parcel), 10.0)

    def test_feasible_route(self):
        self.assertTrue(helpers.is_feasible(["P001", "P002"], self.parcel, self.context))
        self.assertTrue(helpers.is_feasible([], self.parcel, self.context))

    def test_rejects_unavailable_duplicate_unknown(self):
        self.assertIn("not available", helpers.route_violations(["P003"], self.parcel, self.context)[0])
        self.assertIn("duplicate", helpers.route_violations(["P001", "P001"], self.parcel, self.context)[0])
        self.assertIn("unknown", helpers.route_violations(["P999"], self.parcel, self.context)[0])

    def test_capacity(self):
        self.context["capacity"] = 9.0
        self.assertEqual(helpers.route_violations(["P001", "P002"], self.parcel, self.context),
                         ["exceeds capacity"])
        self.assertFalse(helpers.can_append(["P001"], "P002", self.parcel, self.context))

    def test_range(self):
        self.context["max_trip_distance_km"] = 30.0
        self.assertIn("exceeds range", helpers.route_violations(["P001", "P002"], self.parcel, self.context))

    def test_cutoff(self):
        self.context["current_time"] = 1020.0  # departs 17:30, returns 18:03
        self.assertEqual(helpers.route_violations(["P001", "P002"], self.parcel, self.context),
                         ["returns after cutoff"])
        self.assertTrue(helpers.is_feasible(["P001"], self.parcel, self.context))  # returns 17:50

    def test_inputs_not_modified(self):
        before_parcel, before_context = copy.deepcopy(self.parcel), copy.deepcopy(self.context)
        helpers.is_feasible(["P001", "P002"], self.parcel, self.context)
        helpers.delivery_times(["P001", "P002"], self.parcel, self.context)
        self.assertEqual(self.parcel, before_parcel)
        self.assertEqual(self.context, before_context)

    def test_to_hhmm(self):
        self.assertEqual(helpers.to_hhmm(510.5), "08:30")


if __name__ == "__main__":
    unittest.main()
