"""Known-cost, offline tests for the custom UCS and geographic A* searches."""

import math
import random
import unittest
from unittest.mock import patch

import networkx as nx

from routing import RoutingError, a_star, bfs, dfs, geographic_heuristic, haversine_distance, ucs, weighted_costs


class WeightedSearchTests(unittest.TestCase):
    def known_graph(self):
        """Synthetic meter costs are at least the geographic edge distances."""
        graph = nx.MultiDiGraph(crs="EPSG:4326")
        for node, (latitude, longitude) in {
            1: (0, 0), 2: (0, 0.001), 3: (0.001, 0),
            4: (0.001, 0.001), 5: (0, 0.002), 99: (0.002, 0.002),
        }.items():
            graph.add_node(node, y=latitude, x=longitude)
        for source, target, length in [(1, 3, 130), (1, 2, 180), (1, 5, 700),
                                        (3, 4, 130), (4, 5, 170), (2, 5, 180)]:
            graph.add_edge(source, target, length=length)
        return graph

    def assert_metrics(self, result, path, distance):
        self.assertEqual(result.path, path)
        if distance is None:
            self.assertIsNone(result.distance_m)
        else:
            self.assertAlmostEqual(result.distance_m, distance)
        self.assertEqual(result.explored_count, len(result.explored))
        self.assertEqual(len(set(result.explored)), result.explored_count)
        self.assertGreaterEqual(result.execution_ms, 0)

    def test_known_optimal_path_differs_from_bfs_and_dfs(self):
        graph = self.known_graph()
        with patch.object(nx, "shortest_path", side_effect=AssertionError("Built-in pathfinding is forbidden")), \
             patch.object(nx, "dijkstra_path", side_effect=AssertionError("Built-in pathfinding is forbidden")), \
             patch.object(nx, "astar_path", side_effect=AssertionError("Built-in pathfinding is forbidden")):
            uniform = ucs(graph, 1, 5)
            guided = a_star(graph, 1, 5)
        self.assert_metrics(uniform, [1, 2, 5], 360)
        self.assert_metrics(guided, [1, 2, 5], 360)
        self.assertLess(guided.explored_count, uniform.explored_count)
        self.assertEqual(bfs(graph, 1, 5).path, [1, 5])
        # Existing iterative DFS marks nodes when queued, so the direct goal
        # keeps its first parent even while deeper branches are explored.
        self.assertEqual(dfs(graph, 1, 5).path, [1, 5])

    def test_parallel_edges_use_the_same_minimum_length(self):
        graph = self.known_graph()
        graph.add_edge(1, 2, length=120)
        for search in [ucs, a_star]:
            self.assert_metrics(search(graph, 1, 5), [1, 2, 5], 300)

    def test_unreachable_reversed_direction_and_same_node(self):
        graph = self.known_graph()
        for search in [ucs, a_star]:
            self.assert_metrics(search(graph, 1, 99), None, None)
            self.assert_metrics(search(graph, 5, 1), None, None)
            self.assert_metrics(search(graph, 1, 1), [1], 0)
            with self.assertRaises(RoutingError):
                search(graph, 1, -123)

    def test_cheaper_rediscovery_and_stale_heap_entries(self):
        graph = nx.DiGraph()
        for node in ["start", "a", "b", "goal", "unreachable"]:
            graph.add_node(node, x=0, y=0)
        for source, target, cost in [("start", "a", 9), ("start", "b", 2),
                                     ("b", "a", 1), ("a", "goal", 2), ("b", "goal", 50)]:
            graph.add_edge(source, target, length=cost)
        for search in [ucs, a_star]:
            self.assert_metrics(search(graph, "start", "goal"), ["start", "b", "a", "goal"], 5)
            result = search(graph, "start", "unreachable")
            self.assert_metrics(result, None, None)
            self.assertEqual(result.explored_count, 4)

    def test_equal_priority_mixed_node_ids_do_not_need_comparison(self):
        graph = nx.MultiDiGraph()
        for node in [1, "left", ("right",), "goal"]:
            graph.add_node(node, x=0, y=0)
        for source, target in [(1, "left"), (1, ("right",)), ("left", "goal"), (("right",), "goal")]:
            graph.add_edge(source, target, length=1)
        for search in [ucs, a_star]:
            self.assert_metrics(search(graph, 1, "goal"), [1, "left", "goal"], 2)

    def test_zero_cost_cycles_and_conservative_heuristic_fallback(self):
        graph = nx.MultiDiGraph()
        for node, longitude in [(1, 0), (2, 0.001), (3, 0.002)]:
            graph.add_node(node, x=longitude, y=0)
        for source, target, cost in [(1, 2, 0), (2, 1, 0), (2, 3, 5), (1, 3, 50)]:
            graph.add_edge(source, target, length=cost)
        for search in [ucs, a_star]:
            self.assert_metrics(search(graph, 1, 3), [1, 2, 3], 5)
        self.assertEqual(a_star(graph, 1, 3).heuristic_scale, 0)

    def test_missing_negative_nonfinite_and_nonnumeric_weights(self):
        for value in [None, -1, float("nan"), float("inf"), "180", True, 10**400]:
            for search in [ucs, a_star]:
                with self.subTest(value=value, search=search.__name__):
                    graph = self.known_graph()
                    graph[1][2][0]["length"] = value
                    with self.assertRaises(RoutingError):
                        search(graph, 1, 5)
        graph = self.known_graph()
        del graph[1][2][0]["length"]
        with self.assertRaises(RoutingError):
            ucs(graph, 1, 5)

    def test_astar_rejects_missing_or_invalid_node_coordinates(self):
        for attribute, value in [("x", None), ("y", float("nan")), ("y", 100), ("x", True)]:
            graph = self.known_graph()
            graph.nodes[2][attribute] = value
            with self.assertRaisesRegex(RoutingError, "coordinates"):
                a_star(graph, 1, 5)
        graph = self.known_graph()
        del graph.nodes[2]["x"]
        with self.assertRaises(RoutingError):
            a_star(graph, 1, 5)

    def test_haversine_units_symmetry_and_heuristic_consistency(self):
        self.assertEqual(haversine_distance(0, 0, 0, 0), 0)
        self.assertAlmostEqual(haversine_distance(0, 0, 0, 1), 111195.0837, places=3)
        self.assertAlmostEqual(haversine_distance(24.86, 67.0, 24.88, 67.02),
                               haversine_distance(24.88, 67.02, 24.86, 67.0))
        self.assertTrue(math.isfinite(haversine_distance(0, 0, 0, 180)))
        graph = self.known_graph()
        weights = weighted_costs(graph, 1, 5)
        heuristic, scale = geographic_heuristic(graph, 5, weights)
        self.assertAlmostEqual(scale, 1)
        self.assertEqual(heuristic(5), 0)
        self.assertLessEqual(heuristic(1), 360)
        for (source, target), length in weights.items():
            self.assertLessEqual(heuristic(source), length + heuristic(target) + 1e-9)

    def test_scaled_heuristic_is_safe_for_unrealistically_short_test_weights(self):
        graph = self.known_graph()
        for _, _, edge in graph.edges(data=True):
            edge["length"] /= 1000
        result = a_star(graph, 1, 5)
        self.assertAlmostEqual(result.distance_m, 0.36)
        self.assertAlmostEqual(result.distance_m, ucs(graph, 1, 5).distance_m)
        self.assertLess(result.heuristic_scale, 0.01)

    def test_both_searches_match_exhaustive_simple_path_costs(self):
        """An independent tiny-graph oracle, without NetworkX pathfinding."""
        generator = random.Random(61)
        for case in range(30):
            graph = nx.MultiDiGraph()
            for node in range(6):
                graph.add_node(node, y=24.86 + node // 3 * 0.001, x=67.0 + node % 3 * 0.001)
            for source in graph:
                for target in graph:
                    if source != target and generator.random() < 0.3:
                        a, b = graph.nodes[source], graph.nodes[target]
                        length = math.ceil(haversine_distance(a["y"], a["x"], b["y"], b["x"])) + generator.randint(0, 100)
                        graph.add_edge(source, target, length=length)
            best = math.inf
            candidates = [(0, [0], 0.0)]
            while candidates:
                node, path, cost = candidates.pop()
                if node == 5:
                    best = min(best, cost)
                    continue
                for neighbor in graph.successors(node):
                    if neighbor not in path:
                        length = min(edge["length"] for edge in graph[node][neighbor].values())
                        candidates.append((neighbor, path + [neighbor], cost + length))
            for search in [ucs, a_star]:
                with self.subTest(case=case, algorithm=search.__name__):
                    result = search(graph, 0, 5)
                    if math.isinf(best):
                        self.assertIsNone(result.path)
                    else:
                        self.assertAlmostEqual(result.distance_m, best)


if __name__ == "__main__":
    unittest.main()
