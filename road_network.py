"""Download, validate, save, and reuse driving networks for selected locations.

Routes automatically reuse or prepare the area they need. The optional pilot
CLI remains available as ``prepare`` and ``check``. No route algorithms live here.
"""

from __future__ import annotations

import argparse
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile
from threading import Lock

import networkx as nx
import osmnx as ox


PROJECT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = PROJECT_DIR / "road_network_config.json"
DATA_DIR = PROJECT_DIR / "data"


class RoadNetworkError(Exception):
    """A configuration, download, graph validation, or file error."""


class GraphNotFoundError(RoadNetworkError):
    """The selected area's saved graph has not been prepared yet."""


class RouteCoverageError(RoadNetworkError):
    """A request exceeds the manageable size of this local downloader."""


@dataclass(frozen=True)
class AreaConfig:
    center: tuple[float, float]
    distance_m: float
    request_timeout_seconds: int = 90
    overpass_url: str = "https://overpass-api.de/api"
    route_buffer_m: float = 1500
    route_max_area_km2: float = 2500

    @property
    def signature(self) -> str:
        """Only area/model changes affect which saved graph we reuse."""
        return json.dumps(
            {"center": self.center, "distance_m": self.distance_m,
             "network_type": "drive", "schema": 1},
            sort_keys=True, separators=(",", ":"),
        )

    @property
    def graph_path(self) -> Path:
        area_id = hashlib.sha256(self.signature.encode("utf-8")).hexdigest()[:12]
        return DATA_DIR / f"karachi_drive_{area_id}.graphml"


@dataclass(frozen=True)
class RouteAreaConfig:
    """A reusable rectangular area covering the selected route locations."""

    bbox: tuple[float, float, float, float]  # west, south, east, north
    request_timeout_seconds: int = 90
    overpass_url: str = "https://overpass-api.de/api"

    @property
    def signature(self) -> str:
        return json.dumps({"bbox": self.bbox, "network_type": "drive", "schema": 1},
                          sort_keys=True, separators=(",", ":"))

    @property
    def graph_path(self) -> Path:
        # Bounds in the filename let us find covering caches without loading
        # every GraphML file. The embedded signature is checked when loading.
        coordinates = "_".join(f"{value:.2f}" for value in self.bbox)
        return DATA_DIR / f"route_drive_{coordinates}.graphml"


NetworkConfig = AreaConfig | RouteAreaConfig


def load_config(filepath: Path = CONFIG_PATH) -> AreaConfig:
    """Read and check the small, beginner-editable JSON configuration."""
    try:
        values = json.loads(Path(filepath).read_text(encoding="utf-8-sig"))
        if not isinstance(values, dict):
            raise ValueError("the configuration must be a JSON object")
        center = values["center"]
        if not isinstance(center, list) or len(center) != 2:
            raise ValueError("center must be [latitude, longitude]")
        numbers = [*center, values["distance_m"], values["request_timeout_seconds"]]
        if any(isinstance(value, bool) or not isinstance(value, (int, float))
               or not math.isfinite(value) for value in numbers):
            raise ValueError("coordinates, distance, and timeout must be finite numbers")
        latitude, longitude = map(float, center)
        distance = float(values["distance_m"])
        timeout = values["request_timeout_seconds"]
        route_buffer = values.get("route_buffer_m", 1500)
        route_max_area = values.get("route_max_area_km2", 2500)
        for value, name, lower, upper in [(route_buffer, "route_buffer_m", 100, 10000),
                                         (route_max_area, "route_max_area_km2", 1, 10000)]:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lower <= value <= upper:
                raise ValueError(f"{name} must be a number from {lower} to {upper}")
        if not (-90 < latitude < 90 and -180 <= longitude <= 180):
            raise ValueError("center must contain valid latitude/longitude values")
        if not 100 <= distance <= 5000:
            raise ValueError("distance_m must be between 100 and 5000 to limit download size")
        if not isinstance(timeout, int) or not 10 <= timeout <= 300:
            raise ValueError("request_timeout_seconds must be an integer from 10 to 300")
        endpoint = values["overpass_url"]
        if not isinstance(endpoint, str) or not endpoint.startswith("https://"):
            raise ValueError("overpass_url must be an HTTPS API base URL")
        return AreaConfig((latitude, longitude), distance, timeout, endpoint.rstrip("/"), float(route_buffer), float(route_max_area))
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
        raise RoadNetworkError(f"Cannot read configuration {filepath}: {exc}") from exc


def validate_graph(graph: nx.MultiDiGraph, config: NetworkConfig | None = None) -> None:
    """Check all coordinates and length weights; never invent missing lengths."""
    if not isinstance(graph, nx.MultiDiGraph):
        raise RoadNetworkError("The road network must be a directed NetworkX MultiDiGraph.")
    if not graph.number_of_nodes() or not graph.number_of_edges():
        raise RoadNetworkError("The road network is empty. Try another small center/area.")
    if str(graph.graph.get("crs", "")).upper() != "EPSG:4326":
        raise RoadNetworkError("The road graph must use latitude/longitude (EPSG:4326).")
    if config is not None and graph.graph.get("srf_area") != config.signature:
        raise RoadNetworkError("The saved graph does not match the selected area. Run prepare --rebuild.")

    for node_id, attributes in graph.nodes(data=True):
        try:
            latitude = float(attributes["y"])
            longitude = float(attributes["x"])
            if not (math.isfinite(latitude) and math.isfinite(longitude)
                    and -90 <= latitude <= 90 and -180 <= longitude <= 180):
                raise ValueError("coordinates are outside their valid range")
            attributes["y"], attributes["x"] = latitude, longitude
        except (KeyError, ValueError, TypeError, OverflowError) as exc:
            raise RoadNetworkError(f"Node {node_id} has missing or invalid coordinates.") from exc

    for source, target, key, attributes in graph.edges(keys=True, data=True):
        try:
            length = float(attributes["length"])
            if not math.isfinite(length) or length < 0:
                raise ValueError("length must be finite and nonnegative")
            attributes["length"] = length
        except (KeyError, ValueError, TypeError, OverflowError) as exc:
            raise RoadNetworkError(f"Road edge {(source, target, key)} has no valid length in meters.") from exc


def download_graph(config: NetworkConfig) -> nx.MultiDiGraph:
    """OSMnx already returns a NetworkX MultiDiGraph with one-way directions."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ox.settings.use_cache = True
    ox.settings.cache_folder = DATA_DIR / "osmnx_cache"
    ox.settings.requests_timeout = config.request_timeout_seconds
    ox.settings.overpass_url = config.overpass_url
    ox.settings.http_user_agent = "SmartRouteFinder/0.1 (local educational project; OSMnx)"

    try:
        options = {"network_type": "drive", "simplify": True,
                   "retain_all": False, "truncate_by_edge": False}
        if isinstance(config, RouteAreaConfig):
            graph = ox.graph_from_bbox(config.bbox, **options)
        else:
            graph = ox.graph_from_point(config.center, dist=config.distance_m,
                                        dist_type="bbox", **options)
    except Exception as exc:
        # Translate third-party network/Overpass errors at the download boundary.
        raise RoadNetworkError(
            "Road-network download failed. Check your internet connection and the "
            "Overpass server, then retry prepare. Existing GraphML files are unchanged. "
            f"Details: {exc}"
        ) from exc

    graph.graph["srf_area"] = config.signature
    graph.graph["srf_source"] = "OpenStreetMap contributors (ODbL)"
    graph.graph["srf_downloaded_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    # OSMnx calculates lengths in meters before simplifying the street geometry.
    validate_graph(graph, config)
    return graph


def load_graph(config: NetworkConfig, filepath: Path | None = None) -> nx.MultiDiGraph:
    """Load GraphML locally and restore OSMnx's numeric/geometric attribute types."""
    path = Path(filepath) if filepath is not None else config.graph_path
    if not path.is_file():
        raise GraphNotFoundError(f"No saved graph at {path}. Run python road_network.py prepare.")
    try:
        graph = ox.load_graphml(path)
        validate_graph(graph, config)
        return graph
    except Exception as exc:
        raise RoadNetworkError(
            f"Cannot load valid graph data from {path}. Run prepare --rebuild to repair it. Details: {exc}"
        ) from exc


def save_graph(graph: nx.MultiDiGraph, config: NetworkConfig, filepath: Path | None = None) -> Path:
    """Validate a temporary GraphML file before replacing the saved file."""
    validate_graph(graph, config)
    path = Path(filepath) if filepath is not None else config.graph_path
    temporary_path = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".graphml.tmp", delete=False) as temporary:
            temporary_path = Path(temporary.name)
        ox.save_graphml(graph, filepath=temporary_path)
        restored = load_graph(config, temporary_path)
        if (restored.number_of_nodes(), restored.number_of_edges()) != (graph.number_of_nodes(), graph.number_of_edges()):
            raise RoadNetworkError("GraphML verification changed the node or edge count.")
        temporary_path.replace(path)
        return path
    except Exception as exc:
        raise RoadNetworkError(f"Could not save graph to {path}: {exc}") from exc
    finally:
        if temporary_path is not None:
            with suppress(OSError):
                temporary_path.unlink(missing_ok=True)


def prepare_graph(config: AreaConfig | None = None, *, rebuild: bool = False) -> nx.MultiDiGraph:
    """Prepare/reuse the optional original pilot-area graph from the CLI."""
    config = config or load_config()
    if config.graph_path.exists() and not rebuild:
        return load_graph(config)
    graph = download_graph(config)
    save_graph(graph, config)
    return graph


def graph_bounds(graph: nx.MultiDiGraph) -> tuple:
    area = json.loads(graph.graph.get("srf_area", "{}"))
    if "bbox" in area:
        return tuple(area["bbox"])
    if "center" in area and "distance_m" in area:
        return ox.utils_geo.bbox_from_point(area["center"], dist=area["distance_m"])
    return (min(data["x"] for _, data in graph.nodes(data=True)),
            min(data["y"] for _, data in graph.nodes(data=True)),
            max(data["x"] for _, data in graph.nodes(data=True)),
            max(data["y"] for _, data in graph.nodes(data=True)))


def bounds_cover_locations(bounds, locations) -> bool:
    west, south, east, north = bounds
    return all(west <= point["lon"] <= east and south <= point["lat"] <= north for point in locations)


def route_area_for_locations(locations, settings: AreaConfig) -> RouteAreaConfig:
    """Pad all selected points and round outwards to a ~1 km reuse grid."""
    latitude = sum(point["lat"] for point in locations) / len(locations)
    latitude_padding = settings.route_buffer_m / 111195
    longitude_padding = latitude_padding / math.cos(math.radians(latitude))
    west = max(-180, min(point["lon"] for point in locations) - longitude_padding)
    east = min(180, max(point["lon"] for point in locations) + longitude_padding)
    south = max(-85, min(point["lat"] for point in locations) - latitude_padding)
    north = min(85, max(point["lat"] for point in locations) + latitude_padding)
    bounds = (round(math.floor(west * 100) / 100, 2), round(math.floor(south * 100) / 100, 2),
              round(math.ceil(east * 100) / 100, 2), round(math.ceil(north * 100) / 100, 2))
    area_km2 = (bounds[2]-bounds[0]) * (bounds[3]-bounds[1]) * 111.195**2 * math.cos(math.radians(latitude))
    if area_km2 > settings.route_max_area_km2:
        raise RouteCoverageError(
            "These locations are too far apart for the local road downloader. "
            "Long-distance trips need a larger regional road dataset; nearby/city trips load automatically."
        )
    return RouteAreaConfig(bounds, settings.request_timeout_seconds, settings.overpass_url)


def network_summary(graph) -> dict:
    return {"state": "loaded", "label": "Loaded", "detail":
            f"{graph.number_of_nodes():,} nodes · {graph.number_of_edges():,} directed road segments",
            "bounds": list(graph_bounds(graph))}


class RoadNetworkStore:
    """Load locally for status; expand coverage only for an explicit route request."""

    def __init__(self) -> None:
        self._graph = None
        self._stamp = None
        self._lock = Lock()
        self._route_lock = Lock()
        self._route_graph = None
        self._route_stamp = None

    def get_graph(self) -> nx.MultiDiGraph:
        config = load_config()
        path = config.graph_path
        with self._lock:
            try:
                file_stat = path.stat()
            except FileNotFoundError as exc:
                self._graph = None
                self._stamp = None
                raise GraphNotFoundError("The selected area's road network is not prepared yet.") from exc
            except OSError as exc:
                raise RoadNetworkError(f"Cannot access the saved road network: {exc}") from exc
            # Windows can reuse modification timestamps during fast replacements.
            stamp = (path, file_stat.st_mtime_ns, file_stat.st_size, file_stat.st_ino)
            if stamp != self._stamp:
                self._graph = load_graph(config)
                self._stamp = stamp
            return self._graph

    def get_graph_for_locations(self, locations) -> nx.MultiDiGraph:
        """Reuse covering data, or prepare real roads around validated points."""
        settings = load_config()
        with self._route_lock:
            try:
                pilot = self.get_graph()
                if bounds_cover_locations(graph_bounds(pilot), locations):
                    self._route_graph = pilot
                    self._route_stamp = None
                    return pilot
            except RoadNetworkError:
                # Missing pilot data must not prevent automatic route preparation.
                pass

            candidates = []
            for path in DATA_DIR.glob("route_drive_*.graphml"):
                try:
                    bounds = tuple(float(value) for value in path.stem.split("_")[2:])
                    if len(bounds) == 4 and bounds_cover_locations(bounds, locations):
                        candidates.append((bounds, path))
                except ValueError:
                    continue
            candidates.sort(key=lambda item: (item[0][2]-item[0][0]) * (item[0][3]-item[0][1]))
            for bounds, path in candidates:
                config = RouteAreaConfig(bounds, settings.request_timeout_seconds, settings.overpass_url)
                try:
                    file_stat = path.stat()
                    stamp = (path, file_stat.st_mtime_ns, file_stat.st_size, file_stat.st_ino)
                    if stamp == self._route_stamp and self._route_graph is not None:
                        return self._route_graph
                    graph = load_graph(config, path)
                except (RoadNetworkError, OSError):
                    continue
                self._route_graph, self._route_stamp = graph, stamp
                return graph

            config = route_area_for_locations(locations, settings)
            graph = download_graph(config)
            save_graph(graph, config)
            file_stat = config.graph_path.stat()
            self._route_graph = graph
            self._route_stamp = (config.graph_path, file_stat.st_mtime_ns, file_stat.st_size, file_stat.st_ino)
            return graph

    def status(self) -> dict:
        try:
            graph = self._route_graph if self._route_graph is not None else self.get_graph()
            return network_summary(graph)
        except GraphNotFoundError:
            return {"state": "missing", "label": "On demand", "detail": "Road data loads automatically when you request a route."}
        except RoadNetworkError as exc:
            return {"state": "error", "label": "Unavailable", "detail": str(exc)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "check"))
    parser.add_argument("--config", type=Path, default=CONFIG_PATH, help="Path to the area JSON configuration")
    parser.add_argument("--rebuild", action="store_true", help="Rebuild GraphML; reuse OSMnx's cached response when available")
    args = parser.parse_args()
    if args.rebuild and args.command != "prepare":
        parser.error("--rebuild is only available with prepare")
    try:
        config = load_config(args.config)
        cached = config.graph_path.is_file() and not args.rebuild
        print(f"Selected area: center={config.center}, distance={config.distance_m:g} m (bounding box)", flush=True)
        print(f"GraphML: {config.graph_path}", flush=True)
        if args.command == "prepare":
            print("Loading saved GraphML..." if cached else "Preparing driving network from OpenStreetMap (may take a minute)...", flush=True)
            graph = prepare_graph(config, rebuild=args.rebuild)
        else:
            graph = load_graph(config)
        print(f"Validated {graph.number_of_nodes():,} nodes and {graph.number_of_edges():,} directed road segments.")
        print("Every node has x/y coordinates; every edge has a nonnegative length in meters.")
        print("Loaded locally; no download needed." if args.command == "check" or cached else "GraphML saved and reloaded successfully.")
        return 0
    except (RoadNetworkError, OSError) as exc:
        print(f"Road network error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
