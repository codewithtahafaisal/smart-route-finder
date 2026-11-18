"""Identical graph/waypoints, honest statuses, and measured comparison results."""
import unittest
from unittest.mock import Mock, patch

import networkx as nx

from app import app
from comparison import compare_algorithms
from road_network import GraphNotFoundError
from routing import ALGORITHMS, RoutingError, plan_route, prepare_waypoints


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.graph = nx.MultiDiGraph(crs="EPSG:4326")
        for node in range(1, 5):
            self.graph.add_node(node, x=67 + (node - 1) * 0.001, y=24.86)
        for source, target, length in [(1, 2, 100), (2, 3, 110), (3, 4, 120), (1, 4, 1000), (4, 3, 140), (3, 2, 150)]:
            self.graph.add_edge(source, target, length=length)

    def locations(self, nodes):
        return [{"id": f"field-{index}", "name": f"Test junction {node}",
                 "lat": self.graph.nodes[node]["y"], "lon": self.graph.nodes[node]["x"]}
                for index, node in enumerate(nodes)]

    def test_all_algorithms_share_one_graph_and_one_snapping_pass(self):
        tracked = {name: Mock(wraps=search) for name, search in ALGORITHMS.items()}
        locations = self.locations([1, 2, 3, 4])
        with patch.dict(ALGORITHMS, tracked), patch("comparison.prepare_waypoints", wraps=prepare_waypoints) as snapping:
            data = compare_algorithms(self.graph, locations)
        snapping.assert_called_once_with(self.graph, locations)
        self.assertEqual(data["stop_count"], 2)
        self.assertEqual(data["segment_count"], 3)
        for row in data["results"]:
            self.assertEqual(row["status"], "found")
            self.assertEqual(row["distance_m"], 330)
            self.assertEqual(row["waypoints"], data["waypoints"])
            self.assertEqual(row["explored_count"], sum(leg["explored_count"] for leg in row["segments"]))
            self.assertAlmostEqual(row["execution_ms"], sum(leg["execution_ms"] for leg in row["segments"]))
            self.assertTrue(all(call.args[0] is self.graph for call in tracked[row["algorithm"]].call_args_list))
            self.assertEqual([call.args[1:] for call in tracked[row["algorithm"]].call_args_list], [(1, 2), (2, 3), (3, 4)])

    def test_comparison_matches_independent_route_distances_and_paths(self):
        locations = self.locations([1, 4])
        data = compare_algorithms(self.graph, locations)
        by_name = {row["algorithm"]: row for row in data["results"]}
        self.assertEqual(by_name["BFS"]["distance_m"], 1000)
        self.assertEqual(by_name["UCS"]["distance_m"], 330)
        self.assertEqual(by_name["A*"]["distance_m"], 330)
        for row in data["results"]:
            route = plan_route(self.graph, locations, row["algorithm"])
            self.assertEqual(row["path"], route["path"])
            self.assertEqual(row["distance_m"], route["distance_m"])
            self.assertEqual(row["explored_count"], route["explored_count"])
            self.assertIsNone(row["estimated_travel_time_s"])
            self.assertEqual(row["stop_count"], 0)
            self.assertEqual(row["segment_count"], 1)
            self.assertGreaterEqual(row["execution_ms"], 0)

    def test_failed_and_unavailable_algorithms_do_not_silently_substitute(self):
        with patch.dict(ALGORITHMS, {"DFS": Mock(side_effect=RoutingError("Test search failure")), "A*": None}):
            data = compare_algorithms(self.graph, self.locations([1, 4]))
        rows = {row["algorithm"]: row for row in data["results"]}
        self.assertEqual(rows["BFS"]["status"], "found")
        self.assertEqual(rows["UCS"]["status"], "found")
        self.assertEqual(rows["DFS"]["status"], "error")
        self.assertIn("Test search failure", rows["DFS"]["message"])
        self.assertEqual(rows["A*"]["status"], "unavailable")
        for name in ["DFS", "A*"]:
            self.assertIsNone(rows[name]["distance_m"])
            self.assertIsNone(rows[name]["explored_count"])
            self.assertIsNone(rows[name]["path"])
        self.assertIsNone(rows["A*"]["execution_ms"])

    def test_unexpected_algorithm_error_is_isolated_and_logged(self):
        with patch.dict(ALGORITHMS, {"DFS": Mock(side_effect=ValueError("Test implementation error"))}), patch("comparison.logger.exception") as log:
            result = compare_algorithms(self.graph, self.locations([1, 4]))
        self.assertEqual([row["status"] for row in result["results"]], ["found", "error", "found", "found"])
        log.assert_called_once()

    def test_unreachable_leg_has_no_total_distance_or_complete_geometry(self):
        self.graph.remove_edges_from([(2, 3, 0), (3, 2, 0), (1, 4, 0)])
        self.graph.add_edge(2, 1, length=100)  # Stop 2 still needs an outgoing road.
        for row in compare_algorithms(self.graph, self.locations([1, 2, 4]))["results"]:
            self.assertEqual(row["status"], "no_path")
            self.assertEqual(row["failed_segments"], [2])
            self.assertIsNone(row["distance_m"])
            self.assertIsNone(row["path"])
            self.assertEqual(row["geometry"], [])
            self.assertGreater(row["explored_count"], 0)

    def test_endpoint_loads_coverage_once_and_validates_before_loading(self):
        client = app.test_client()
        with patch.object(app.extensions["road_network"], "get_graph_for_locations", return_value=self.graph) as coverage:
            response = client.post("/api/comparisons", json={"locations": self.locations([1, 2, 3, 4])})
        self.assertEqual(response.status_code, 200)
        coverage.assert_called_once()
        self.assertEqual(len(response.json["results"]), 4)
        self.assertIn("4 nodes", response.json["network"]["detail"])
        with patch.object(app.extensions["road_network"], "get_graph_for_locations") as coverage:
            for bad in [[], [{"id": "start"}, {"id": "end"}], None]:
                self.assertEqual(client.post("/api/comparisons", json={"locations": bad}).status_code, 422)
        coverage.assert_not_called()
        self.assertEqual(client.post("/api/comparisons", json=[]).status_code, 400)
        with patch.object(app.extensions["road_network"], "get_graph_for_locations", side_effect=GraphNotFoundError("missing")):
            self.assertEqual(client.post("/api/comparisons", json={"locations": self.locations([1, 4])}).status_code, 503)


if __name__ == "__main__":
    unittest.main()
