"""Tests for the course data structure and algorithm (heap priority queue, UCS)
and for the policies that use them (edd_heap, heuristic_best).

Run from the project root:  python3 -m unittest discover -s tests -t .
"""

import copy
import csv
import itertools
import random
import tempfile
import unittest
from pathlib import Path

from simulator.loaders import day_input_paths
from simulator.simulator import Simulator
from solution import log_utils
from solution.policies import edd_heap, heuristic_best, helpers
from solution.policies.helpers import HeapPriorityQueue, ucs_shortest_tour

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


class HeapPriorityQueueTests(unittest.TestCase):
    def test_add_then_remove_min_sorts(self):
        rng = random.Random(1)
        for _ in range(100):
            keys = [rng.randint(0, 30) for _ in range(rng.randint(1, 50))]
            heap = HeapPriorityQueue()
            for index, key in enumerate(keys):
                heap.add((key, index), index)
            self.assertEqual([heap.remove_min()[0][0] for _ in range(len(keys))], sorted(keys))
            self.assertTrue(heap.is_empty())

    def test_bottom_up_build_matches(self):
        rng = random.Random(2)
        keys = [(rng.random(), i) for i in range(200)]
        heap = HeapPriorityQueue([(key, None) for key in keys])
        self.assertEqual(heap.min()[0], min(keys))
        self.assertEqual([heap.remove_min()[0] for _ in range(len(keys))], sorted(keys))

    def test_heap_order_property_holds(self):
        heap = HeapPriorityQueue([((k,), k) for k in [9, 4, 7, 1, 8, 2, 6, 3, 5]])
        data = heap._data
        for child in range(1, len(data)):
            self.assertLessEqual(data[(child - 1) // 2][0], data[child][0])

    def test_empty_raises(self):
        with self.assertRaises(IndexError):
            HeapPriorityQueue().remove_min()
        with self.assertRaises(IndexError):
            HeapPriorityQueue().min()


class UniformCostSearchTests(unittest.TestCase):
    def setUp(self):
        with open(DATA / "dist.csv", newline="", encoding="utf-8-sig") as stream:
            self.dist = log_utils.parse_distances(list(csv.DictReader(stream)))
        self.locations = sorted(loc for loc in self.dist if loc != "HUB")

    def km(self, order):
        stops = ["HUB"] + list(order) + ["HUB"]
        return sum(self.dist[a][b] for a, b in zip(stops, stops[1:]))

    def test_matches_brute_force(self):
        rng = random.Random(3)
        for size in range(1, 8):
            for _ in range(4):
                stops = rng.sample(self.locations, size)
                tour = ucs_shortest_tour(stops, self.dist)
                self.assertCountEqual(tour, stops)
                best = min(self.km(order) for order in itertools.permutations(stops))
                self.assertAlmostEqual(self.km(tour), best, places=9)

    def test_small_hand_example(self):
        dist = {"HUB": {"HUB": 0, "A": 1, "B": 10, "C": 10},
                "A": {"HUB": 1, "A": 0, "B": 2, "C": 9},
                "B": {"HUB": 10, "A": 2, "B": 0, "C": 2},
                "C": {"HUB": 10, "A": 9, "B": 2, "C": 0}}
        tour = ucs_shortest_tour(["C", "A", "B"], dist)
        self.assertIn(tour, (["A", "B", "C"], ["C", "B", "A"]))  # 1+2+2+10 = 15 either way

    def test_empty(self):
        self.assertEqual(ucs_shortest_tour([], self.dist), [])


class CoursePolicyTests(unittest.TestCase):
    def run_checked(self, policy, day):
        def wrapped(parcel, context):
            before = (copy.deepcopy(parcel), copy.deepcopy(context))
            route = policy(parcel, context)
            self.assertEqual((parcel, context), before, "policy modified its inputs")
            self.assertEqual(helpers.route_violations(route, parcel, context), [], (day, route))
            return route

        with tempfile.TemporaryDirectory() as tmp:
            simulator = Simulator(*day_input_paths(DATA, day), dispatch_policy=wrapped)
            simulator.run(Path(tmp) / "log.txt")
        return simulator

    def test_edd_heap_all_days(self):
        for number in range(1, 21):
            with self.subTest(day=number):
                self.assertTrue(self.run_checked(edd_heap.dispatch, f"day_{number:03d}").delivered)

    def test_heuristic_best_all_days(self):
        for number in range(1, 21):
            with self.subTest(day=number):
                self.assertTrue(self.run_checked(heuristic_best.dispatch, f"day_{number:03d}").delivered)

    def test_edd_heap_takes_earliest_deadline_first(self):
        parcel = {
            pid: {"arrival_time": 480.0, "delivery_location_id": "L1", "delivery_window_start": 480.0,
                  "delivery_window_end": end, "size": 20.0, "delivery_time": None,
                  "vehicle_assigned": None, "trip_id": None}
            for pid, end in (("P1", 900.0), ("P2", 600.0), ("P3", 700.0))
        }
        context = {"current_time": 480.0, "vehicle_id": 1, "capacity": 30.0,
                   "travel_distance": {"HUB": {"HUB": 0.0, "L1": 10.0}, "L1": {"HUB": 10.0, "L1": 0.0}},
                   "departure_delay": 30.0, "return_cutoff": 1080.0, "max_trip_distance_km": 320.0,
                   "fleet": {1: {"available_at": 480.0, "max_trip_distance_km": 320.0}}}
        self.assertEqual(edd_heap.dispatch(parcel, context), ["P2"])  # only one 20-unit parcel fits


if __name__ == "__main__":
    unittest.main()
