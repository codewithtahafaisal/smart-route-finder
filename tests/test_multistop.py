"""Ordered journeys, real leg metrics, and all-or-nothing route publication."""

import unittest
from unittest.mock import Mock, patch

import networkx as nx

from app import app
from routing import ALGORITHMS, RoutingError, plan_route


class MultiStopTests(unittest.TestCase):
    def setUp(self):
        self.graph = nx.MultiDiGraph(crs="EPSG:4326")
        for node in range(1, 7):
            self.graph.add_node(node, x=67 + (node - 1) * 0.001, y=24.86)
        for node in range(1, 6):
            self.graph.add_edge(node, node + 1, length=90 + node * 10)
            self.graph.add_edge(node + 1, node, length=140 + node * 10)

    def locations(self, nodes):
        return [{"id": f"field-{index}", "name": f"Synthetic junction {node}",
                 "lat": self.graph.nodes[node]["y"], "lon": self.graph.nodes[node]["x"]}
                for index, node in enumerate(nodes)]

    def assert_totals(self, response):
        self.assertEqual(response["explored_count"], sum(leg["explored_count"] for leg in response["segments"]))
        self.assertEqual(response["unique_explored_count"], len(set(response["explored_nodes"])))
        self.assertAlmostEqual(response["execution_ms"], sum(leg["execution_ms"] for leg in response["segments"]))
        if response["status"] == "found":
            self.assertAlmostEqual(response["distance_m"], sum(leg["distance_m"] for leg in response["segments"]))

    def test_zero_one_and_three_stops_for_every_algorithm(self):
        for algorithm, search in ALGORITHMS.items():
            for nodes in [[1, 5], [1, 3, 5], [1, 2, 3, 4, 5]]:
                with self.subTest(algorithm=algorithm, nodes=nodes):
                    tracked = Mock(wraps=search)
                    with patch.dict("routing.ALGORITHMS", {algorithm: tracked}):
                        result = plan_route(self.graph, self.locations(nodes), algorithm)
                    self.assertEqual(result["status"], "found")
                    self.assertEqual(result["algorithm"], algorithm)
                    self.assertEqual(result["path"], [1, 2, 3, 4, 5])
                    self.assertEqual(result["distance_m"], 460)
                    self.assertEqual(len(result["segments"]), len(nodes) - 1)
                    self.assertEqual([call.args[1:] for call in tracked.call_args_list], list(zip(nodes, nodes[1:])))
                    self.assertEqual([leg["algorithm"] for leg in result["segments"]], [algorithm] * (len(nodes) - 1))
                    self.assertEqual(len(result["geometry"]), 5)
                    self.assert_totals(result)

    def test_changed_stop_order_and_deliberate_revisits_are_preserved(self):
        for algorithm in ALGORITHMS:
            result = plan_route(self.graph, self.locations([1, 4, 2, 5]), algorithm)
            self.assertEqual([point["node_id"] for point in result["waypoints"]], [1, 4, 2, 5])
            self.assertEqual(result["path"], [1, 2, 3, 4, 3, 2, 3, 4, 5])
            self.assertEqual([(leg["from_node"], leg["to_node"]) for leg in result["segments"]], [(1, 4), (4, 2), (2, 5)])
            self.assert_totals(result)

    def test_repeated_consecutive_waypoints_have_zero_cost_without_duplicate_boundaries(self):
        for algorithm in ALGORITHMS:
            result = plan_route(self.graph, self.locations([1, 2, 2, 5]), algorithm)
            self.assertEqual(result["path"], [1, 2, 3, 4, 5])
            self.assertEqual(result["segments"][1]["path"], [2])
            self.assertEqual(result["segments"][1]["distance_m"], 0)
            self.assertEqual(result["segments"][1]["explored_count"], 1)
            self.assert_totals(result)
            same = plan_route(self.graph, self.locations([2, 2, 2, 2, 2]), algorithm)
            self.assertEqual(same["path"], [2])
            self.assertEqual(same["distance_m"], 0)
            self.assertEqual(len(same["geometry"]), 1)

    def test_failed_middle_segment_never_publishes_a_partial_journey(self):
        self.graph.remove_edge(2, 3)
        self.graph.remove_edge(3, 2)
        for algorithm in ALGORITHMS:
            result = plan_route(self.graph, self.locations([1, 2, 3, 4]), algorithm)
            self.assertEqual(result["status"], "no_path")
            self.assertEqual(result["failed_segments"], [2])
            self.assertEqual([leg["status"] for leg in result["segments"]], ["found", "no_path", "found"])
            self.assertIsNone(result["path"])
            self.assertIsNone(result["distance_m"])
            self.assertEqual(result["geometry"], [])
            self.assertIn("Segment 2 (Stop 1 → Stop 2)", result["message"])
            self.assertEqual(result["segments"][0]["distance_m"], 100)
            self.assertEqual(result["segments"][2]["distance_m"], 120)
            self.assert_totals(result)

    def test_multiple_failures_are_all_identified(self):
        self.graph.remove_edge(2, 3)
        self.graph.remove_edge(3, 2)
        result = plan_route(self.graph, self.locations([1, 3, 2, 4]), "UCS")
        self.assertEqual(result["failed_segments"], [1, 2, 3])
        self.assertTrue(all(leg["status"] == "no_path" for leg in result["segments"]))

    def test_missing_or_distant_stop_is_rejected_before_search(self):
        for invalid in [{"id": "stop"}, {"id": "stop", "lat": 24.9, "lon": 67.1}]:
            locations = self.locations([1, 5])
            locations.insert(1, invalid)
            with patch.dict("routing.ALGORITHMS", {"UCS": Mock(side_effect=AssertionError("Must validate first"))}):
                with self.assertRaises(RoutingError):
                    plan_route(self.graph, locations, "UCS")

    def test_flask_uses_all_selected_points_and_returns_each_leg(self):
        client = app.test_client()
        locations = self.locations([1, 2, 3, 4, 5])
        for algorithm in ALGORITHMS:
            with patch.object(app.extensions["road_network"], "get_graph_for_locations", return_value=self.graph) as coverage:
                response = client.post("/api/routes", json={"algorithm": algorithm, "locations": locations})
            self.assertEqual(response.status_code, 200)
            result = response.json
            self.assertEqual(result["status"], "found")
            self.assertEqual(len(result["segments"]), 4)
            self.assertEqual([point["id"] for point in coverage.call_args.args[0]], [point["id"] for point in locations])
            self.assertEqual([point["name"] for point in result["waypoints"]], [point["name"] for point in locations])
            self.assert_totals(result)


if __name__ == "__main__":
    unittest.main()
