"""Small deterministic graphs test manual searches, snapping, and stop order."""

import unittest
from unittest.mock import Mock, patch

import networkx as nx

from routing import RoutingError, bfs, dfs, path_details, plan_route, prepare_waypoints


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.graph = nx.MultiDiGraph()
        self.graph.add_edges_from([(1, 2), (2, 3), (3, 4), (4, 6), (1, 5), (5, 6), (4, 1)])
        self.graph.add_node(99)

    def test_bfs_minimizes_hops_and_dfs_discovers_a_nonshortest_path(self):
        with patch.object(nx, "shortest_path", side_effect=AssertionError("Do not use built-in pathfinding")):
            breadth = bfs(self.graph, 1, 6)
            depth = dfs(self.graph, 1, 6)
        self.assertEqual(breadth.path, [1, 5, 6])
        self.assertEqual(depth.path, [1, 2, 3, 4, 6])
        for result in [breadth, depth]:
            self.assertEqual(len(result.explored), len(set(result.explored)))
            self.assertTrue(all(self.graph.has_edge(a, b) for a, b in zip(result.path, result.path[1:])))

    def test_no_path_respects_direction_and_same_node(self):
        for search in [bfs, dfs]:
            self.assertIsNone(search(self.graph, 6, 1).path)
            self.assertIsNone(search(self.graph, 1, 99).path)
            self.assertEqual(search(self.graph, 1, 1).path, [1])
            with self.assertRaises(RoutingError):
                search(self.graph, 1, -999)


class RoadConnectionTests(unittest.TestCase):
    def setUp(self):
        self.graph = nx.MultiDiGraph(crs="EPSG:4326")
        for node, longitude in [(1, 67.0), (2, 67.001), (3, 67.002)]:
            self.graph.add_node(node, x=longitude, y=24.86)
        self.graph.add_edge(1, 2, length=100.0)
        self.graph.add_edge(2, 3, length=110.0)

    def location(self, node, identifier):
        return {"id": identifier, "lat": self.graph.nodes[node]["y"], "lon": self.graph.nodes[node]["x"]}

    def test_snapping_and_true_route_metrics(self):
        locations = [self.location(1, "start"), self.location(3, "destination")]
        for algorithm in ["BFS", "DFS", "UCS", "A*"]:
            result = plan_route(self.graph, locations, algorithm)
            self.assertEqual(result["path"], [1, 2, 3])
            self.assertEqual(result["distance_m"], 210.0)
            self.assertEqual(result["explored_count"], 3)
            self.assertEqual(result["geometry"], [[24.86, 67.0], [24.86, 67.001], [24.86, 67.002]])
            self.assertEqual([point["node_id"] for point in result["waypoints"]], [1, 3])

    def test_stops_are_calculated_in_order_with_the_existing_search(self):
        locations = [self.location(1, "start"), self.location(2, "my-stop"), self.location(3, "destination")]
        locations[1]["label"] = "Stop 2"
        search = Mock(wraps=bfs)
        with patch.dict("routing.ALGORITHMS", {"BFS": search}):
            result = plan_route(self.graph, locations, "BFS")
        self.assertEqual(result["status"], "found")
        self.assertEqual([call.args[1:] for call in search.call_args_list], [(1, 2), (2, 3)])
        self.assertEqual(result["path"], [1, 2, 3])
        self.assertEqual(result["distance_m"], 210)
        self.assertEqual([point["id"] for point in result["waypoints"]], ["start", "my-stop", "destination"])
        self.assertEqual(result["waypoints"][1]["label"], "Stop 2")
        self.assertEqual([(leg["from_node"], leg["to_node"]) for leg in result["segments"]], [(1, 2), (2, 3)])

    def test_bad_coordinates_outside_coverage_and_unsupported_algorithms(self):
        for value in [None, True, float("nan"), 90.0]:
            locations = [self.location(1, "start"), {"id": "destination", "lat": value, "lon": 67.001}]
            with self.assertRaises(RoutingError):
                prepare_waypoints(self.graph, locations)
        with self.assertRaisesRegex(RoutingError, "Road data is missing"):
            prepare_waypoints(self.graph, [self.location(1, "start"), {"id": "end", "lat": 24.9, "lon": 67.1}])
        for algorithm in ["bogus", None, []]:
            with self.assertRaises(RoutingError):
                plan_route(self.graph, [self.location(1, "start"), self.location(3, "end")], algorithm)

    def test_too_distant_junction_is_rejected_even_inside_coverage(self):
        self.graph.nodes[3]["x"] = 67.03
        with self.assertRaisesRegex(RoutingError, "nearest suitable road node"):
            prepare_waypoints(self.graph, [self.location(1, "start"), {"id": "end", "lat": 24.86, "lon": 67.02}])

    def test_parallel_edge_distance_is_measured_after_node_search(self):
        self.graph.add_edge(1, 2, length=70.0)
        distance, geometry = path_details(self.graph, [1, 2, 3])
        self.assertEqual(distance, 180.0)


if __name__ == "__main__":
    unittest.main()
