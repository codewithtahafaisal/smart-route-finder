"""Compare custom searches on one graph and one shared set of snapped nodes."""

import logging
from time import perf_counter

from routing import ALGORITHMS, RoutingError, plan_waypoints, prepare_waypoints

COMPARISON_ALGORITHMS = ("BFS", "DFS", "UCS", "A*")
logger = logging.getLogger(__name__)


def compare_algorithms(graph, locations):
    # Snap once so every algorithm gets identical node IDs as well as coordinates.
    waypoints = prepare_waypoints(graph, locations)
    results = []
    for algorithm in COMPARISON_ALGORITHMS:
        empty = {"algorithm": algorithm, "path": None, "geometry": [],
                 "distance_m": None, "explored_count": None, "execution_ms": None}
        if not callable(ALGORITHMS.get(algorithm)):
            results.append({**empty, "status": "unavailable", "message": f"{algorithm} is not available. No other algorithm was substituted."})
            continue
        started = perf_counter()
        try:
            results.append(plan_waypoints(graph, waypoints, algorithm))
        except Exception as exc:
            # A failed implementation must not prevent the other measured rows.
            message = str(exc) if isinstance(exc, RoutingError) else "The search failed. See the Flask terminal for details."
            if not isinstance(exc, RoutingError):
                logger.exception("%s comparison failed", algorithm)
            results.append({**empty, "status": "error", "message": message,
                            "execution_ms": (perf_counter() - started) * 1000})
    return {"waypoints": waypoints, "stop_count": len(waypoints) - 2,
            "segment_count": len(waypoints) - 1, "results": results}
