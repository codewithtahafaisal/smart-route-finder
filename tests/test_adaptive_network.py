"""Offline regression tests for automatic road coverage and GraphML reuse."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import networkx as nx

import road_network as roads
from routing import validate_locations


class AdaptiveNetworkTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="smart-route-area-tests-")
        self.addCleanup(self.directory.cleanup)
        directory_patch = patch.object(roads, "DATA_DIR", Path(self.directory.name))
        directory_patch.start()
        self.addCleanup(directory_patch.stop)
        self.settings = roads.load_config()
        self.locations = validate_locations([
            {"id": "start", "lat": 24.8605712, "lon": 67.0317406},
            {"id": "end", "lat": 24.8534668, "lon": 67.0049279},
        ])

    def graph_for_area(self, config):
        # Synthetic fixture only. The application always downloads real OSM data.
        graph = nx.MultiDiGraph(crs="EPSG:4326", simplified=True)
        graph.graph["srf_area"] = config.signature
        for node, location in enumerate(self.locations, start=1):
            graph.add_node(node, x=location["lon"], y=location["lat"])
        graph.add_edge(1, 2, length=3000.0)
        graph.add_edge(2, 1, length=3000.0)
        return graph

    def test_generated_bounds_cover_all_points_with_room_for_surrounding_roads(self):
        area = roads.route_area_for_locations(self.locations, self.settings)
        self.assertTrue(roads.bounds_cover_locations(area.bbox, self.locations))
        self.assertLess(area.bbox[0], min(point["lon"] for point in self.locations))
        self.assertGreater(area.bbox[3], max(point["lat"] for point in self.locations))
        self.assertEqual(area, roads.route_area_for_locations(self.locations, self.settings))

    def test_a_covering_original_graph_needs_no_download(self):
        graph = self.graph_for_area(self.settings)
        locations = [{"id": "start", "lat": 24.86, "lon": 67.0},
                     {"id": "end", "lat": 24.861, "lon": 67.001}]
        store = roads.RoadNetworkStore()
        with patch.object(store, "get_graph", return_value=graph), patch.object(roads, "download_graph", side_effect=AssertionError("No download needed")):
            self.assertIs(store.get_graph_for_locations(locations), graph)

    def test_outside_pilot_downloads_once_then_reuses_disk_and_memory(self):
        store = roads.RoadNetworkStore()
        with patch.object(roads, "download_graph", side_effect=self.graph_for_area) as download:
            first = store.get_graph_for_locations(self.locations)
            self.assertIs(store.get_graph_for_locations(self.locations), first)
            fresh_store = roads.RoadNetworkStore()
            restored = fresh_store.get_graph_for_locations(self.locations)
        self.assertEqual(download.call_count, 1)
        self.assertEqual(list(restored.edges), list(first.edges))
        self.assertTrue(roads.bounds_cover_locations(roads.graph_bounds(restored), self.locations))
        self.assertIn("2 nodes", fresh_store.status()["detail"])

    def test_nearby_request_reuses_a_covering_area_with_different_exact_points(self):
        store = roads.RoadNetworkStore()
        with patch.object(roads, "download_graph", side_effect=self.graph_for_area) as download:
            graph = store.get_graph_for_locations(self.locations)
            nearby = [{"id": "start", "lat": 24.86, "lon": 67.025},
                      {"id": "end", "lat": 24.855, "lon": 67.008}]
            self.assertIs(store.get_graph_for_locations(nearby), graph)
        self.assertEqual(download.call_count, 1)

    def test_invalid_cached_area_is_rebuilt_and_does_not_return_wrong_coverage(self):
        area = roads.route_area_for_locations(self.locations, self.settings)
        area.graph_path.write_text("not valid GraphML", encoding="utf-8")
        with patch.object(roads, "download_graph", side_effect=self.graph_for_area) as download:
            graph = roads.RoadNetworkStore().get_graph_for_locations(self.locations)
        download.assert_called_once()
        self.assertEqual(roads.load_graph(area).number_of_nodes(), graph.number_of_nodes())

    def test_download_failure_preserves_existing_saved_areas(self):
        area = roads.route_area_for_locations(self.locations, self.settings)
        roads.save_graph(self.graph_for_area(area), area)
        original = area.graph_path.read_bytes()
        far_locations = [{"id": "start", "lat": 24.95, "lon": 67.1},
                         {"id": "end", "lat": 24.96, "lon": 67.11}]
        with patch.object(roads, "download_graph", side_effect=roads.RoadNetworkError("offline")):
            with self.assertRaises(roads.RoadNetworkError):
                roads.RoadNetworkStore().get_graph_for_locations(far_locations)
        self.assertEqual(area.graph_path.read_bytes(), original)

    def test_large_requests_are_rejected_before_any_download(self):
        locations = [{"id": "start", "lat": 24.86, "lon": 67},
                     {"id": "end", "lat": 35, "lon": 74}]
        with patch.object(roads, "download_graph") as download:
            with self.assertRaises(roads.RouteCoverageError):
                roads.RoadNetworkStore().get_graph_for_locations(locations)
        download.assert_not_called()

    def test_adaptive_download_uses_rectangular_driving_graph(self):
        area = roads.route_area_for_locations(self.locations, self.settings)
        with patch.object(roads.ox, "graph_from_bbox", return_value=self.graph_for_area(area)) as fetch:
            graph = roads.download_graph(area)
        self.assertEqual(fetch.call_args.args[0], area.bbox)
        self.assertEqual(fetch.call_args.kwargs["network_type"], "drive")
        self.assertEqual(graph.graph["srf_area"], area.signature)


if __name__ == "__main__":
    unittest.main()
