"""No live API calls: fixtures test caching, filtering, and service failures."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import requests

from geocoding import Geocoder, GeocodingError, PhotonGeocoder


def result(name="Test Hall", lat="24.8534", lon="67.0049"):
    return {"name": name, "display_name": f"{name}, Karachi, Pakistan", "lat": lat, "lon": lon,
            "address": {"country_code": "pk"}, "osm_id": 123, "osm_type": "way"}


class GeocodingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="smart-route-geocoding-")
        self.addCleanup(self.directory.cleanup)
        self.service = Geocoder(Path(self.directory.name)/"cache.sqlite3", endpoint="https://nominatim.openstreetmap.org/search")

    def response(self, rows):
        response = Mock(status_code=200)
        response.json.return_value = rows
        return response

    def test_filtering_duplicate_results_and_invalid_responses(self):
        rows = [result(), result("Test Hall Karachi", "24.85341"), result("London", "51.5", "-0.1"), None, {"lat": "bad"}]
        self.assertEqual(len(self.service.clean_results(rows)), 1)
        with self.assertRaises(GeocodingError):
            self.service.clean_results({"unexpected": "object"})

    def test_persistent_cache_avoids_another_network_request(self):
        with patch("geocoding.requests.get", return_value=self.response([result()])) as get:
            first = self.service.search("Test Hall")
            second = Geocoder(self.service.database).search("  test   hall ")
        self.assertEqual(first, second)
        self.assertEqual(get.call_count, 1)
        self.assertEqual(get.call_args.kwargs["params"]["countrycodes"], "pk")
        self.assertEqual(get.call_args.kwargs["params"]["bounded"], 1)
        self.assertIn("SmartRouteFinder", get.call_args.kwargs["headers"]["User-Agent"])

    def test_public_service_never_allows_typing_requests_even_if_flag_requested(self):
        service = Geocoder(self.service.database, autocomplete=True)
        self.assertFalse(service.autocomplete_enabled)
        with patch("geocoding.requests.get", side_effect=AssertionError("No autocomplete traffic")):
            for trigger in ["typing", [], {}]:
                with self.assertRaises(GeocodingError):
                    service.search("Test Hall", trigger=trigger)
        self.assertTrue(Geocoder(self.service.database, endpoint="http://localhost:8080/search", autocomplete=True).autocomplete_enabled)

    def test_rate_limit_is_shared_across_instances(self):
        with patch("geocoding.requests.get", return_value=self.response([])), patch("geocoding.time.time", return_value=1000), patch("geocoding.time.sleep") as sleep:
            self.service.search("First query")
            Geocoder(self.service.database).search("Second query")
        sleep.assert_called_once()
        self.assertGreaterEqual(sleep.call_args.args[0], 1)

    def test_network_and_invalid_query_errors_are_actionable(self):
        with patch("geocoding.requests.get", side_effect=requests.Timeout("offline")):
            with self.assertRaisesRegex(GeocodingError, "internet"):
                self.service.search("Test Hall")
        for query in [None, "x", 123, "x"*161]:
            with self.assertRaises(GeocodingError):
                self.service.search(query)

    def test_photon_supports_real_prefix_requests_without_nominatim(self):
        service = PhotonGeocoder(self.service.database)
        payload = {"features": [{"properties": {"name": "Saddar", "city": "Karachi", "country": "Pakistan", "countrycode": "PK"},
                                 "geometry": {"type": "Point", "coordinates": [67.03, 24.86]}}]}
        with patch("geocoding.requests.get", return_value=self.response(payload)) as get:
            results = service.search("Sadd", trigger="typing")
        self.assertTrue(service.autocomplete_enabled)
        self.assertEqual(results[0]["label"], "Saddar")
        self.assertEqual(results[0]["source"], "photon")
        self.assertEqual(results[0]["lat"], 24.86)
        self.assertIn("photon.komoot.io", get.call_args.args[0])
        self.assertEqual(get.call_args.kwargs["params"]["q"], "Sadd")
        self.assertEqual(get.call_args.kwargs["params"]["bbox"], "66.8,24.65,67.6,25.35")

    def test_photon_filters_foreign_results_and_invalid_features(self):
        payload = {"features": [None, {"geometry": {"type": "LineString"}},
                    {"properties": {"name": "London", "countrycode": "GB"},
                     "geometry": {"type": "Point", "coordinates": [-0.1, 51.5]}}]}
        self.assertEqual(PhotonGeocoder.clean_results(payload), [])
        with self.assertRaises(GeocodingError):
            PhotonGeocoder.clean_results([])

    def test_duplicate_area_centers_do_not_show_identical_suggestions(self):
        rows = [{"label": "Saddar", "details": "Saddar, Karachi, Pakistan", "lat": 24.86057, "lon": 67.03174},
                {"label": "Saddar", "details": "Saddar, Karachi, Pakistan", "lat": 24.85965, "lon": 67.03082}]
        self.assertEqual(len(Geocoder.deduplicate(rows)), 1)


if __name__ == "__main__":
    unittest.main()
