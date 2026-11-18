"""Manual BFS, DFS, UCS, A* and ordered multi-stop journeys on real roads."""

from collections import deque
from dataclasses import dataclass
import heapq
from itertools import count
import math
from numbers import Real
from time import perf_counter

import osmnx as ox

from road_network import graph_bounds


class RoutingError(Exception):
    """Invalid locations, unsupported algorithms, or unavailable road connections."""


@dataclass
class SearchResult:
    path: list | None
    explored: list
    distance_m: float | None = None
    execution_ms: float | None = None
    heuristic_scale: float | None = None

    @property
    def explored_count(self):
        return len(self.explored)


def reconstruct_path(parents, destination):
    path = []
    while destination is not None:
        path.append(destination)
        destination = parents[destination]
    return list(reversed(path))


def bfs(graph, start, destination):
    """A FIFO queue explores one edge-depth at a time.

    BFS minimizes the NUMBER OF EDGES, not physical road distance. Edge length
    weights are deliberately not used to choose the discovered node path.
    """
    if start not in graph or destination not in graph:
        raise RoutingError("Both route nodes must exist in the road graph.")
    frontier = deque([start])
    parents = {start: None}
    explored = []
    while frontier:
        node = frontier.popleft()
        explored.append(node)
        if node == destination:
            return SearchResult(reconstruct_path(parents, destination), explored)
        for neighbor in graph.successors(node):
            if neighbor not in parents:
                parents[neighbor] = node
                frontier.append(neighbor)
    return SearchResult(None, explored)


def dfs(graph, start, destination):
    """A LIFO stack follows a branch before trying other branches.

    DFS returns a discovered path; it does NOT guarantee the shortest route.
    Marking nodes when pushed prevents cycles and duplicate stack entries.
    """
    if start not in graph or destination not in graph:
        raise RoutingError("Both route nodes must exist in the road graph.")
    frontier = [start]
    parents = {start: None}
    explored = []
    while frontier:
        node = frontier.pop()
        explored.append(node)
        if node == destination:
            return SearchResult(reconstruct_path(parents, destination), explored)
        for neighbor in reversed(list(graph.successors(node))):
            if neighbor not in parents:
                parents[neighbor] = node
                frontier.append(neighbor)
    return SearchResult(None, explored)


def edge_length(attributes):
    """All distance searches and displayed paths use this same meter weight."""
    value = attributes.get("length")
    if isinstance(value, bool) or not isinstance(value, Real):
        raise RoutingError("Every road segment needs a numeric length in meters.")
    try:
        length = float(value)
    except OverflowError as exc:
        raise RoutingError("Road lengths must be finite and nonnegative.") from exc
    if not math.isfinite(length) or length < 0:
        raise RoutingError("Road lengths must be finite and nonnegative.")
    return length


def weighted_costs(graph, start, destination):
    """Validate costs and keep the cheapest directed parallel edge per pair."""
    if start not in graph or destination not in graph:
        raise RoutingError("Both route nodes must exist in the road graph.")
    if not graph.is_directed():
        raise RoutingError("Road searches require a directed graph.")
    costs = {}
    for source, target, attributes in graph.edges(data=True):
        length = edge_length(attributes)
        pair = (source, target)
        costs[pair] = min(costs.get(pair, math.inf), length)
    return costs


def ucs(graph, start, destination):
    """Uniform Cost Search expands the cheapest accumulated distance first.

    No heuristic or built-in pathfinding is used. With nonnegative lengths,
    the first expansion of the destination has the optimal distance.
    """
    started = perf_counter()
    weights = weighted_costs(graph, start, destination)
    sequence = count()  # Ties never require comparing unlike node-ID types.
    frontier = [(0.0, next(sequence), start)]
    cost_so_far = {start: 0.0}
    parents = {start: None}
    settled, explored = set(), []

    while frontier:
        cost, _, node = heapq.heappop(frontier)
        if node in settled or cost != cost_so_far.get(node):
            continue  # An improved queue entry made this one stale.
        settled.add(node)
        explored.append(node)
        if node == destination:
            path = reconstruct_path(parents, destination)
            return SearchResult(path, explored, cost, (perf_counter() - started) * 1000)
        for neighbor in graph.successors(node):
            candidate = cost + weights[(node, neighbor)]
            if not math.isfinite(candidate):
                raise RoutingError("Accumulated road distance is too large to represent.")
            if candidate < cost_so_far.get(neighbor, math.inf):
                cost_so_far[neighbor] = candidate
                parents[neighbor] = node
                heapq.heappush(frontier, (candidate, next(sequence), neighbor))
    return SearchResult(None, explored, execution_ms=(perf_counter() - started) * 1000)


def haversine_distance(latitude1, longitude1, latitude2, longitude2):
    """Geographic straight-line distance in meters, using OSMnx's Earth radius."""
    lat1, lat2 = math.radians(latitude1), math.radians(latitude2)
    delta_lat = lat2 - lat1
    delta_lon = math.radians(longitude2 - longitude1)
    value = math.sin(delta_lat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2)**2
    value = min(1.0, max(0.0, value))  # Protect square roots from floating-point drift.
    return 6371009.0 * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def geographic_heuristic(graph, destination, weights):
    """Build a consistent lower bound without changing any road-edge costs.

    Real road lengths should be at least their endpoint great-circle distance.
    If rounding/imported test weights violate that, alpha scales all estimates
    down. For every edge, alpha * geographic_distance(u,v) <= length(u,v).
    The triangle inequality then gives h(u) <= length(u,v) + h(v).
    A zero-cost edge between different positions reduces alpha to zero: A*
    safely behaves like UCS rather than returning a potentially wrong route.
    """
    coordinates = {}
    for node, attributes in graph.nodes(data=True):
        try:
            latitude, longitude = float(attributes["y"]), float(attributes["x"])
            if isinstance(attributes["y"], bool) or isinstance(attributes["x"], bool):
                raise ValueError("coordinates must be numbers")
            if not (math.isfinite(latitude) and math.isfinite(longitude)
                    and -90 <= latitude <= 90 and -180 <= longitude <= 180):
                raise ValueError("invalid geographic coordinates")
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise RoutingError(f"A* needs valid latitude/longitude coordinates for road node {node}.") from exc
        coordinates[node] = (latitude, longitude)

    scale = 1.0
    for (source, target), length in weights.items():
        direct = haversine_distance(*coordinates[source], *coordinates[target])
        if direct > 0:
            scale = min(scale, length / direct)
    scale *= 1 - 1e-12  # Conservative margin for floating-point calculations.
    estimates = {}

    def estimate(node):
        if node not in estimates:
            estimates[node] = scale * haversine_distance(*coordinates[node], *coordinates[destination])
        return estimates[node]

    return estimate, scale


def a_star(graph, start, destination):
    """A* expands the smallest f = g + h: distance so far plus a lower bound."""
    started = perf_counter()
    weights = weighted_costs(graph, start, destination)
    heuristic, scale = geographic_heuristic(graph, destination, weights)
    sequence = count()
    g_score = {start: 0.0}
    f_score = {start: heuristic(start)}
    parents = {start: None}
    frontier = [(f_score[start], next(sequence), start, 0.0)]
    settled, explored = set(), []

    while frontier:
        _, _, node, queued_cost = heapq.heappop(frontier)
        if node in settled or queued_cost != g_score.get(node):
            continue
        settled.add(node)
        explored.append(node)
        if node == destination:
            path = reconstruct_path(parents, destination)
            return SearchResult(path, explored, g_score[node], (perf_counter() - started) * 1000, scale)
        for neighbor in graph.successors(node):
            candidate = g_score[node] + weights[(node, neighbor)]
            if not math.isfinite(candidate):
                raise RoutingError("Accumulated road distance is too large to represent.")
            if candidate < g_score.get(neighbor, math.inf):
                parents[neighbor] = node
                g_score[neighbor] = candidate
                f_score[neighbor] = candidate + heuristic(neighbor)
                heapq.heappush(frontier, (f_score[neighbor], next(sequence), neighbor, candidate))
    return SearchResult(None, explored, execution_ms=(perf_counter() - started) * 1000, heuristic_scale=scale)


ALGORITHMS = {"BFS": bfs, "DFS": dfs, "UCS": ucs, "A*": a_star}


def validate_locations(locations):
    """Reject missing/invalid coordinates before any road-data request."""
    if not isinstance(locations, list) or not 2 <= len(locations) <= 22:
        raise RoutingError("Provide a start and destination, with at most 20 optional stops.")
    validated, identifiers = [], set()
    for index, location in enumerate(locations):
        label = "Starting Location" if index == 0 else "Final Destination" if index == len(locations)-1 else f"Stop {index}"
        if 0 < index < len(locations)-1 and isinstance(location, dict):
            # Blank optional rows are omitted. Preserve the entered row's name.
            supplied = location.get("label")
            if isinstance(supplied, str) and supplied.startswith("Stop ") and supplied[5:].isdigit() and len(supplied) <= 20:
                label = supplied
        try:
            identifier = location["id"]
            lat, lon = location["lat"], location["lon"]
            if not isinstance(identifier, str) or not identifier or len(identifier) > 80 or identifier in identifiers:
                raise ValueError("field identifiers must be unique")
            if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in [lat, lon]):
                raise ValueError("invalid coordinates")
            if not (-85 <= lat <= 85 and -180 <= lon <= 180):
                raise ValueError("coordinates are outside the supported map range")
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise RoutingError(f"{label}: select a search result or map point with valid coordinates.") from exc
        identifiers.add(identifier)
        validated.append({**location, "label": label, "lat": float(lat), "lon": float(lon)})
    return validated


def prepare_waypoints(graph, locations, max_snap_m=250):
    """Snap fields independently and preserve Start -> Stops -> Destination order."""
    locations = validate_locations(locations)
    try:
        west, south, east, north = graph_bounds(graph)
    except (ValueError, KeyError, TypeError) as exc:
        raise RoutingError("The road-network coverage metadata is invalid.") from exc
    waypoints = []
    for index, location in enumerate(locations):
        label, identifier, lat, lon = location["label"], location["id"], location["lat"], location["lon"]
        if not (south <= lat <= north and west <= lon <= east):
            raise RoutingError(f"Road data is missing around {label}; please retry so its area can be loaded.")
        # Starts need outgoing roads, destinations incoming roads, and stops both.
        suitable = [node for node in graph if
                    (index == len(locations)-1 or graph.out_degree(node) > 0) and
                    (index == 0 or graph.in_degree(node) > 0)]
        if not suitable:
            raise RoutingError(f"{label} has no suitable directed road connection.")
        candidates = graph.subgraph(suitable)
        node, distance = ox.distance.nearest_nodes(candidates, X=lon, Y=lat, return_dist=True)
        if distance > max_snap_m:
            raise RoutingError(f"{label} is {distance:.0f} m from the nearest suitable road node (limit {max_snap_m} m). Choose a point closer to a road junction.")
        name = location.get("name")
        name = name.strip()[:200] if isinstance(name, str) and name.strip() else f"{lat:.5f}, {lon:.5f}"
        waypoints.append({"id": identifier, "label": label, "name": name, "lat": lat, "lon": lon,
                          "node_id": int(node), "snap_distance_m": float(distance)})
    return waypoints


def path_details(graph, path):
    """Measure the discovered path and use its actual road geometry for display."""
    if len(path) == 1:
        return 0.0, [[graph.nodes[path[0]]["y"], graph.nodes[path[0]]["x"]]]
    distance, coordinates = 0.0, []
    for source, target in zip(path, path[1:]):
        # Weighted searches use this same minimum parallel-road cost while
        # searching. BFS/DFS choose a node path first, without using lengths.
        alternatives = graph[source][target].values() if graph.is_multigraph() else [graph[source][target]]
        edge = min(alternatives, key=edge_length)
        distance += edge_length(edge)
        a, b = graph.nodes[source], graph.nodes[target]
        points = list(edge["geometry"].coords) if edge.get("geometry") is not None else [(a["x"], a["y"]), (b["x"], b["y"])]
        if (points[-1][0]-a["x"])**2 + (points[-1][1]-a["y"])**2 < (points[0][0]-a["x"])**2 + (points[0][1]-a["y"])**2:
            points.reverse()
        for lon, lat in points:
            if not coordinates or coordinates[-1] != [lat, lon]:
                coordinates.append([lat, lon])
    return distance, coordinates


def calculate_segment(graph, start, destination, algorithm, index):
    """Run the selected custom search for one leg between already-snapped nodes."""
    started = perf_counter()
    try:
        result = ALGORITHMS[algorithm](graph, start["node_id"], destination["node_id"])
    except RoutingError as exc:
        raise RoutingError(f"Segment {index} ({start['label']} → {destination['label']}): {exc}") from exc
    elapsed = (perf_counter() - started) * 1000
    if result.execution_ms is not None:
        elapsed = result.execution_ms
    segment = {"index": index, "algorithm": algorithm,
               "from_node": start["node_id"], "to_node": destination["node_id"],
               "from_id": start["id"], "to_id": destination["id"],
               "from_label": start["label"], "to_label": destination["label"],
               "from_name": start["name"], "to_name": destination["name"],
               "status": "found" if result.path is not None else "no_path", "path": result.path,
               "explored_nodes": result.explored, "explored_count": result.explored_count,
               "execution_ms": elapsed, "distance_m": None, "geometry": []}
    if result.path is not None:
        segment["distance_m"], segment["geometry"] = path_details(graph, result.path)
    if result.heuristic_scale is not None:
        segment["heuristic_scale"] = result.heuristic_scale
    return segment


def plan_route(graph, locations, algorithm):
    """Snap selected locations, then calculate their ordered journey."""
    if not isinstance(algorithm, str) or algorithm not in ALGORITHMS:
        raise RoutingError("Choose BFS, DFS, UCS, or A*.")
    return plan_waypoints(graph, prepare_waypoints(graph, locations), algorithm)


def plan_waypoints(graph, waypoints, algorithm):
    """Calculate every leg in the user's order; publish only complete journeys.

    Explored counts and search times are summed across independent leg searches.
    The same road node can be explored again in another leg. Only the shared
    boundary node is removed when joining paths: deliberate revisits stay intact.
    """
    if not isinstance(algorithm, str) or algorithm not in ALGORITHMS:
        raise RoutingError("Choose BFS, DFS, UCS, or A*.")
    segments = [calculate_segment(graph, start, end, algorithm, index)
                for index, (start, end) in enumerate(zip(waypoints, waypoints[1:]), 1)]
    failed = [segment for segment in segments if segment["status"] != "found"]
    explored = [node for segment in segments for node in segment["explored_nodes"]]
    response = {"status": "no_path" if failed else "found", "algorithm": algorithm,
                "waypoints": waypoints, "segments": segments,
                "path": None, "distance_m": None, "geometry": [],
                "explored_nodes": explored, "explored_count": len(explored),
                "unique_explored_count": len(set(explored)),
                "stop_count": len(waypoints) - 2, "segment_count": len(segments),
                "estimated_travel_time_s": None,
                "travel_time_note": "Not estimated: no road-speed or travel-time model is configured.",
                "execution_ms": sum(segment["execution_ms"] for segment in segments),
                "failed_segments": [segment["index"] for segment in failed]}
    if not failed:
        path, geometry = [], []
        for segment in segments:
            path.extend(segment["path"] if not path else segment["path"][1:])
            for point in segment["geometry"]:
                if not geometry or geometry[-1] != point:
                    geometry.append(point)
        response.update(path=path, geometry=geometry,
                        distance_m=sum(segment["distance_m"] for segment in segments))
        response["message"] = {
            "BFS": "BFS minimizes road-edge count for each segment, not distance.",
            "DFS": "DFS finds a path for each segment but does not guarantee the shortest route.",
            "UCS": "UCS found shortest-distance paths for all segments using road lengths in meters.",
            "A*": "A* found shortest-distance paths for all segments using road lengths and a geographic distance estimate.",
        }[algorithm]
        response["message"] = f"Complete journey: {len(segments)} segment(s) in your entered order. " + response["message"]
        response["message"] += " Distance covers snapped road nodes only; access to those nodes is excluded. Travel time is not estimated."
    else:
        labels = "; ".join(f"Segment {segment['index']} ({segment['from_label']} → {segment['to_label']})" for segment in failed)
        response["message"] = f"Journey incomplete: no directed road path for {labels}. No partial route is displayed. Choose different locations."
    if algorithm == "A*":
        response["heuristic_scale"] = min(segment["heuristic_scale"] for segment in segments)
    return response
