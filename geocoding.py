"""Karachi place searches with persistent caching and a shared request limit.

Photon supports live suggestions. Public Nominatim is used only for explicit
searches because its usage policy prohibits autocomplete.
"""

from contextlib import closing
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import time
from urllib.parse import urlparse

import requests


class GeocodingError(Exception):
    """A search that cannot be completed without misleading the user."""


class Geocoder:
    provider_name = "Nominatim"

    def __init__(self, database=None, endpoint=None, autocomplete=None):
        self.database = Path(database or Path(__file__).parent / "data" / "geocoding_cache.sqlite3")
        self.endpoint = (endpoint or os.environ.get("NOMINATIM_URL", "https://nominatim.openstreetmap.org/search")).rstrip("/")
        hostname = (urlparse(self.endpoint).hostname or "").lower().rstrip(".")
        self.is_public = hostname == "nominatim.openstreetmap.org"
        requested = autocomplete if autocomplete is not None else os.environ.get("GEOCODING_AUTOCOMPLETE") == "1"
        self.autocomplete_enabled = bool(requested and not self.is_public)

    @staticmethod
    def deduplicate(results):
        unique = []
        for result in results:
            words = re.findall(r"\w+", result["label"].casefold())
            duplicate = False
            for earlier in unique:
                earlier_words = re.findall(r"\w+", earlier["label"].casefold())
                distance = math.hypot((result["lat"]-earlier["lat"])*111320,
                                      (result["lon"]-earlier["lon"])*111320*math.cos(math.radians(result["lat"])))
                same_address = result["label"].casefold() == earlier["label"].casefold() and result["details"].casefold() == earlier["details"].casefold()
                if (same_address and distance <= 250) or (len(words) >= 2 and words[:2] == earlier_words[:2] and distance <= 25):
                    duplicate = True
                    break
            if not duplicate:
                unique.append(result)
        return unique[:6]

    @staticmethod
    def clean_results(rows):
        """Keep actual Pakistani results inside a broad Karachi search box."""
        if not isinstance(rows, list):
            raise GeocodingError("The location service returned an invalid response. Please retry.")
        results, seen = [], set()
        for row in rows:
            try:
                if not isinstance(row, dict):
                    continue
                lat, lon = float(row["lat"]), float(row["lon"])
                address = row.get("address") or {}
                if not isinstance(address, dict):
                    continue
                display = str(row["display_name"]).strip()
                country = address.get("country_code", "")
                if not isinstance(country, str) or country.lower() != "pk":
                    continue
                if not (math.isfinite(lat) and math.isfinite(lon) and 24.65 <= lat <= 25.35 and 66.8 <= lon <= 67.6):
                    continue
                key = (display.casefold(), round(lat, 4), round(lon, 4))
                if not display or key in seen:
                    continue
                seen.add(key)
                results.append({"label": str(row.get("name") or display.split(",")[0])[:160],
                                "details": display[:500], "lat": lat, "lon": lon,
                                "source": "nominatim", "osm_id": row.get("osm_id"),
                                "osm_type": row.get("osm_type")})
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
        return Geocoder.deduplicate(results)

    def query_parameters(self, query):
        return {"q": f"{query}, Karachi, Pakistan", "format": "jsonv2", "limit": 8,
                "countrycodes": "pk", "viewbox": "66.8,25.35,67.6,24.65",
                "bounded": 1, "addressdetails": 1, "dedupe": 1, "accept-language": "en"}

    def search(self, query, *, trigger="submit"):
        if not isinstance(query, str) or not 3 <= len(query.strip()) <= 160:
            raise GeocodingError("Enter a location name between 3 and 160 characters.")
        if not isinstance(trigger, str) or trigger not in {"submit", "typing"} or (trigger == "typing" and not self.autocomplete_enabled):
            raise GeocodingError("Press Search or Enter. Public Nominatim does not permit autocomplete.")
        query = " ".join(query.split())
        key = json.dumps([self.endpoint, query.casefold()])
        try:
            self.database.parent.mkdir(parents=True, exist_ok=True)
            # BEGIN IMMEDIATE serializes requests across threads AND local processes.
            # The database is shared by all fields/users of this local application.
            with closing(sqlite3.connect(self.database, timeout=25)) as connection, connection:
                connection.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, saved REAL, results TEXT)")
                connection.execute("CREATE TABLE IF NOT EXISTS rate_limit (id INTEGER PRIMARY KEY, last_request REAL)")
                connection.commit()
                connection.execute("BEGIN IMMEDIATE")
                cached = connection.execute("SELECT saved, results FROM cache WHERE key=?", (key,)).fetchone()
                if cached and time.time() - cached[0] < 7 * 86400:
                    try:
                        return self.deduplicate(json.loads(cached[1]))
                    except (KeyError, TypeError, ValueError):
                        connection.execute("DELETE FROM cache WHERE key=?", (key,))
                last = connection.execute("SELECT last_request FROM rate_limit WHERE id=1").fetchone()
                if last:
                    time.sleep(max(0, 1.1 - (time.time() - last[0])))
                connection.execute("INSERT OR REPLACE INTO rate_limit VALUES (1, ?)", (time.time(),))
                response = None
                try:
                    response = requests.get(
                        self.endpoint,
                        params=self.query_parameters(query),
                        headers={"User-Agent": "SmartRouteFinder/0.1 (local educational route planner)", "Accept": "application/json"},
                        timeout=(5, 12), allow_redirects=False,
                    )
                    response.raise_for_status()
                    if response.status_code != 200:
                        raise GeocodingError("The location service is unavailable. Please retry later.")
                    results = self.clean_results(response.json())
                except (requests.RequestException, ValueError, GeocodingError) as exc:
                    # Keep the rate-limit reservation even when a request fails.
                    connection.commit()
                    raise GeocodingError("Location search failed. Check your internet connection or try again later.") from exc
                finally:
                    if response is not None:
                        response.close()
                connection.execute("DELETE FROM cache WHERE saved < ?", (time.time() - 7 * 86400,))
                connection.execute("INSERT OR REPLACE INTO cache VALUES (?, ?, ?)", (key, time.time(), json.dumps(results)))
                return results
        except (sqlite3.Error, OSError, json.JSONDecodeError) as exc:
            raise GeocodingError("Location search is busy or its cache is unavailable. Please retry shortly.") from exc


class PhotonGeocoder(Geocoder):
    """OpenStreetMap-based autocomplete with the same cache and rate limit."""

    provider_name = "Photon"

    def __init__(self, database=None, endpoint=None):
        super().__init__(database, endpoint=endpoint or os.environ.get("PHOTON_URL", "https://photon.komoot.io/api/"), autocomplete=True)

    def query_parameters(self, query):
        return {"q": query, "lat": 24.8607, "lon": 67.0011, "zoom": 12,
                "bbox": "66.8,24.65,67.6,25.35", "countrycode": "PK", "limit": 8, "lang": "en"}

    @staticmethod
    def clean_results(payload):
        if not isinstance(payload, dict) or not isinstance(payload.get("features"), list):
            raise GeocodingError("The location service returned an invalid response. Please retry.")
        rows = []
        for feature in payload["features"]:
            try:
                properties = feature["properties"]
                geometry = feature["geometry"]
                if geometry["type"] != "Point":
                    continue
                lon, lat = geometry["coordinates"]
                name = properties.get("name") or properties.get("street")
                if not isinstance(name, str) or not name.strip():
                    continue
                parts = []
                for value in [name, properties.get("street"), properties.get("district"),
                              properties.get("city"), properties.get("state"), properties.get("country")]:
                    if isinstance(value, str) and value and value not in parts:
                        parts.append(value)
                rows.append({"name": name, "display_name": ", ".join(parts), "lat": lat, "lon": lon,
                             "address": {"country_code": properties.get("countrycode", "")},
                             "osm_id": properties.get("osm_id"), "osm_type": properties.get("osm_type")})
            except (KeyError, TypeError, ValueError):
                continue
        results = Geocoder.clean_results(rows)
        for result in results:
            result["source"] = "photon"
        return results
