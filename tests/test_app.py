"""Flask integration checks without external services or road downloads."""

import unittest
from unittest.mock import patch

import networkx as nx

from app import app
from road_network import GraphNotFoundError


class AppTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.graph = nx.MultiDiGraph(crs="EPSG:4326")
        self.graph.add_node(1, x=67.0, y=24.86)
        self.graph.add_node(2, x=67.001, y=24.86)
        self.graph.add_edge(1, 2, length=100.0)
        self.locations = [{"id": "start", "lat": 24.86, "lon": 67.0}, {"id": "end", "lat": 24.86, "lon": 67.001}]

    def test_homepage_and_original_assets_still_work(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"leaflet@1.9.4", response.data)
        self.assertIn(b'data-autocomplete="true"', response.data)
        self.assertIn(b'data-search-provider="Photon"', response.data)
        self.assertIn(b'/static/js/locations.js?v=', response.data)
        self.assertIn(b'<option value="UCS">', response.data)
        self.assertIn(b'<option value="A*">', response.data)
        for script in ["map", "script", "locations", "search", "routing"]:
            with self.client.get(f"/static/js/{script}.js") as asset:
                self.assertEqual(asset.status_code, 200)

    def test_route_endpoint_returns_real_search_result_and_errors(self):
        with patch.object(app.extensions["road_network"], "get_graph_for_locations", return_value=self.graph):
            for algorithm in ["BFS", "DFS", "UCS", "A*"]:
                response = self.client.post("/api/routes", json={"algorithm": algorithm, "locations": self.locations})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json["algorithm"], algorithm)
                self.assertEqual(response.json["path"], [1, 2])
                self.assertEqual(response.json["distance_m"], 100.0)
                self.assertTrue(response.json["geometry"])
                self.assertGreaterEqual(response.json["execution_ms"], 0)
            self.assertEqual(self.client.post("/api/routes", json={"algorithm": "INVALID", "locations": self.locations}).status_code, 422)
            self.assertEqual(self.client.post("/api/routes", json={"algorithm": "BFS", "locations": []}).status_code, 422)
        self.assertEqual(self.client.post("/api/routes", json=[]).status_code, 400)
        with patch.object(app.extensions["road_network"], "get_graph_for_locations", side_effect=GraphNotFoundError("missing")):
            self.assertEqual(self.client.post("/api/routes", json={"algorithm": "BFS", "locations": self.locations}).status_code, 503)

    def test_search_endpoint_and_malformed_payloads(self):
        with patch.object(app.extensions["geocoder"], "search", return_value=[]) as search:
            self.assertEqual(self.client.post("/api/locations/search", json={"query": "Karachi"}).json, {"results": [], "provider": "Nominatim"})
            search.assert_called_once_with("Karachi", trigger="submit")
        self.assertEqual(self.client.post("/api/locations/search", json=[]).status_code, 400)

    def test_typing_uses_autocomplete_provider_and_keeps_public_nominatim_explicit(self):
        with patch.object(app.extensions["autocomplete"], "search", return_value=[]) as autocomplete, patch.object(app.extensions["geocoder"], "search") as nominatim:
            response = self.client.post("/api/locations/search", json={"query": "Sadd", "trigger": "typing"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json["provider"], "Photon")
            autocomplete.assert_called_once_with("Sadd", trigger="typing")
            nominatim.assert_not_called()

    def test_no_path_endpoint_reports_exploration_without_fabricated_route(self):
        self.graph.add_node(3, x=67.002, y=24.86)
        self.graph.add_node(4, x=67.003, y=24.86)
        self.graph.add_edge(3, 4, length=100.0)
        self.locations[-1]["lon"] = 67.003
        with patch.object(app.extensions["road_network"], "get_graph_for_locations", return_value=self.graph):
            for algorithm in ["BFS", "DFS", "UCS", "A*"]:
                response = self.client.post("/api/routes", json={"algorithm": algorithm, "locations": self.locations})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json["status"], "no_path")
                self.assertIsNone(response.json["path"])
                self.assertIsNone(response.json["distance_m"])
                self.assertEqual(response.json["geometry"], [])
                self.assertEqual(response.json["explored_count"], 2)

    def test_route_endpoint_requests_coverage_for_the_actual_selected_locations(self):
        # Both points are outside the original center's small pilot box.
        self.graph.nodes[1]["x"] = 67.03
        self.graph.nodes[2]["x"] = 67.031
        self.locations[0]["lon"] = 67.03
        self.locations[1]["lon"] = 67.031
        with patch.object(app.extensions["road_network"], "get_graph_for_locations", return_value=self.graph) as coverage:
            response = self.client.post("/api/routes", json={"algorithm": "BFS", "locations": self.locations})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["status"], "found")
        self.assertEqual(coverage.call_args.args[0][0]["lon"], 67.03)
        self.assertIn("2 nodes", response.json["network"]["detail"])

    def test_invalid_locations_never_start_a_road_download(self):
        with patch.object(app.extensions["road_network"], "get_graph_for_locations") as coverage:
            response = self.client.post("/api/routes", json={"algorithm": "BFS", "locations": []})
        self.assertEqual(response.status_code, 422)
        coverage.assert_not_called()

    def test_same_snapped_node_returns_zero_distance_for_all_algorithms(self):
        self.graph.add_edge(2, 1, length=100.0)
        self.locations[1]["lon"] = self.locations[0]["lon"]
        with patch.object(app.extensions["road_network"], "get_graph_for_locations", return_value=self.graph):
            for algorithm in ["BFS", "DFS", "UCS", "A*"]:
                response = self.client.post("/api/routes", json={"algorithm": algorithm, "locations": self.locations})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json["path"], [1])
                self.assertEqual(response.json["distance_m"], 0)
                self.assertEqual(response.json["explored_count"], 1)

    def test_weighted_route_requests_reject_missing_or_invalid_coordinates(self):
        for algorithm in ["UCS", "A*"]:
            for invalid in [{"id": "end", "lon": 67.001}, {"id": "end", "lat": None, "lon": 67.001},
                            {"id": "end", "lat": float("nan"), "lon": 67.001}]:
                with patch.object(app.extensions["road_network"], "get_graph_for_locations") as coverage:
                    response = self.client.post("/api/routes", json={"algorithm": algorithm, "locations": [self.locations[0], invalid]})
                self.assertEqual(response.status_code, 422)
                coverage.assert_not_called()


if __name__ == "__main__":
    unittest.main()
