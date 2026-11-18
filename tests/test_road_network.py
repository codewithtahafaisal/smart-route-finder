"""Offline checks for graph validation, persistence, caching, and error handling."""

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import networkx as nx

import road_network as roads


class RoadNetworkTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="smart-route-tests-")
        self.addCleanup(self.temporary.cleanup)
        data_patch = patch.object(roads, "DATA_DIR", Path(self.temporary.name))
        data_patch.start()
        self.addCleanup(data_patch.stop)
        self.config = roads.load_config()

    def example_graph(self):
        """A clearly synthetic fixture, never used as application road data."""
        graph = nx.MultiDiGraph(crs="EPSG:4326", simplified=True)
        graph.graph["srf_area"] = self.config.signature
        graph.add_node(101, x=67.0, y=24.86)
        graph.add_node(202, x=67.001, y=24.861)
        graph.add_edge(101, 202, key=0, length=150.0, osmid=11, oneway=True)
        graph.add_edge(101, 202, key=1, length=170.0, osmid=12, oneway=True)
        graph.add_edge(202, 101, key=0, length=151.0, osmid=13, oneway=True)
        return graph

    def test_graphml_round_trip_preserves_ids_directions_parallel_edges_and_lengths(self):
        original = self.example_graph()
        path = roads.save_graph(original, self.config)
        loaded = roads.load_graph(self.config)
        self.assertEqual(path, self.config.graph_path)
        self.assertIsInstance(loaded, nx.MultiDiGraph)
        self.assertEqual(set(original.nodes), set(loaded.nodes))
        self.assertEqual(set(original.edges(keys=True)), set(loaded.edges(keys=True)))
        self.assertEqual(loaded.nodes[101]["x"], 67.0)
        self.assertEqual(loaded.nodes[101]["y"], 24.86)
        self.assertEqual(loaded[101][202][1]["length"], 170.0)
        self.assertIs(loaded[101][202][0]["oneway"], True)

    def test_missing_and_malformed_graphml_have_actionable_errors(self):
        with self.assertRaises(roads.GraphNotFoundError):
            roads.load_graph(self.config)
        self.config.graph_path.write_text("<not-valid-graphml", encoding="utf-8")
        with self.assertRaisesRegex(roads.RoadNetworkError, "prepare --rebuild"):
            roads.load_graph(self.config)

    def test_invalid_coordinates_and_weights_are_rejected(self):
        for attribute, value in [("x", float("nan")), ("y", 120), ("x", None)]:
            with self.subTest(attribute=attribute, value=value):
                graph = self.example_graph()
                graph.nodes[101][attribute] = value
                with self.assertRaises(roads.RoadNetworkError):
                    roads.validate_graph(graph, self.config)
        for value in [float("nan"), float("inf"), -1, None]:
            with self.subTest(length=value):
                graph = self.example_graph()
                graph[101][202][0]["length"] = value
                with self.assertRaises(roads.RoadNetworkError):
                    roads.validate_graph(graph, self.config)
        graph = self.example_graph()
        del graph[101][202][0]["length"]
        with self.assertRaisesRegex(roads.RoadNetworkError, "length"):
            roads.validate_graph(graph, self.config)

    def test_wrong_area_empty_graph_and_undirected_graph_are_rejected(self):
        with self.assertRaises(roads.RoadNetworkError):
            roads.validate_graph(nx.MultiGraph(self.example_graph()), self.config)
        with self.assertRaises(roads.RoadNetworkError):
            roads.validate_graph(nx.MultiDiGraph(), self.config)
        other = replace(self.config, distance_m=self.config.distance_m + 100)
        self.assertNotEqual(self.config.graph_path, other.graph_path)
        with self.assertRaisesRegex(roads.RoadNetworkError, "selected area"):
            roads.validate_graph(self.example_graph(), other)

    def test_prepare_downloads_once_then_reuses_graphml_without_network(self):
        with patch.object(roads, "download_graph", return_value=self.example_graph()) as download:
            roads.prepare_graph(self.config)
            roads.prepare_graph(self.config)
            self.assertEqual(download.call_count, 1)

    def test_failed_save_keeps_existing_valid_graphml(self):
        roads.save_graph(self.example_graph(), self.config)
        original_bytes = self.config.graph_path.read_bytes()
        with patch.object(roads.ox, "save_graphml", side_effect=OSError("simulated disk error")):
            with self.assertRaisesRegex(roads.RoadNetworkError, "Could not save"):
                roads.save_graph(self.example_graph(), self.config)
        self.assertEqual(self.config.graph_path.read_bytes(), original_bytes)
        self.assertFalse(list(self.config.graph_path.parent.glob("*.tmp")))

    def test_download_failure_keeps_existing_graph_and_reports_connection_problem(self):
        roads.save_graph(self.example_graph(), self.config)
        original_bytes = self.config.graph_path.read_bytes()
        with patch.object(roads.ox, "graph_from_point", side_effect=ConnectionError("offline")):
            with self.assertRaisesRegex(roads.RoadNetworkError, "internet connection"):
                roads.prepare_graph(self.config, rebuild=True)
        self.assertEqual(self.config.graph_path.read_bytes(), original_bytes)

    def test_invalid_configuration_is_reported(self):
        path = Path(self.temporary.name) / "bad-config.json"
        for text in ['{', '[]', '{"center": [24.86]}']:
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(roads.RoadNetworkError):
                roads.load_config(path)

    def test_store_uses_memory_and_reports_missing_or_invalid_files(self):
        store = roads.RoadNetworkStore()
        self.assertEqual(store.status()["state"], "missing")
        roads.save_graph(self.example_graph(), self.config)
        with patch.object(roads, "load_graph", wraps=roads.load_graph) as load:
            first = store.get_graph()
            self.assertIs(first, store.get_graph())
            self.assertEqual(load.call_count, 1)
        self.assertEqual(store.status()["state"], "loaded")
        self.config.graph_path.unlink()
        self.assertEqual(store.status()["state"], "missing")
        self.config.graph_path.write_text("invalid GraphML", encoding="utf-8")
        self.assertEqual(store.status()["state"], "error")


if __name__ == "__main__":
    unittest.main()
