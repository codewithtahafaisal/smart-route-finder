"""The starting point for the Smart Route Finder Flask application."""

from pathlib import Path

from flask import Flask, jsonify, render_template, request

from comparison import compare_algorithms
from geocoding import Geocoder, GeocodingError, PhotonGeocoder
from road_network import RoadNetworkError, RoadNetworkStore, RouteCoverageError, network_summary
from routing import ALGORITHMS, RoutingError, plan_route, validate_locations


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024
# Development changes must not leave an old template using newer JavaScript.
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
app.extensions["road_network"] = RoadNetworkStore()
app.extensions["geocoder"] = Geocoder()
app.extensions["autocomplete"] = PhotonGeocoder()


@app.url_defaults
def version_static_files(endpoint, values):
    """Refresh changed CSS/JS while preserving normal browser caching otherwise."""
    if endpoint == "static" and "filename" in values:
        path = Path(app.static_folder) / values["filename"]
        if path.is_file():
            values.setdefault("v", path.stat().st_mtime_ns)


def autocomplete_service():
    geocoder = app.extensions["geocoder"]
    return geocoder if geocoder.autocomplete_enabled else app.extensions["autocomplete"]


@app.route("/")
def home():
    """Show the homepage using the HTML file in the templates folder."""
    return render_template(
        "index.html",
        road_network_status=app.extensions["road_network"].status(),
        search_autocomplete=autocomplete_service().autocomplete_enabled,
        search_provider=autocomplete_service().provider_name,
    )


@app.post("/api/locations/search")
def search_locations():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="Provide a JSON location query."), 400
    try:
        trigger = data.get("trigger", "submit")
        service = autocomplete_service() if trigger == "typing" else app.extensions["geocoder"]
        results = service.search(data.get("query"), trigger=trigger)
        return jsonify(results=results, provider=service.provider_name)
    except GeocodingError as exc:
        return jsonify(error=str(exc)), 503


@app.post("/api/routes")
def find_route():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get("algorithm"), str):
        return jsonify(error="Provide an algorithm and selected locations as JSON."), 400
    try:
        if data["algorithm"] not in ALGORITHMS:
            raise RoutingError("Choose BFS, DFS, UCS, or A*.")
        locations = validate_locations(data.get("locations"))
        graph = app.extensions["road_network"].get_graph_for_locations(locations)
        result = plan_route(graph, locations, data["algorithm"])
        result["network"] = network_summary(graph)
        return jsonify(result)
    except RouteCoverageError as exc:
        return jsonify(error=str(exc)), 422
    except RoadNetworkError:
        return jsonify(error="Road data for these locations could not be loaded. Check your internet connection and retry; previously saved areas remain available."), 503
    except RoutingError as exc:
        return jsonify(error=str(exc)), 422


@app.post("/api/comparisons")
def compare_routes():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="Provide selected locations as JSON."), 400
    try:
        locations = validate_locations(data.get("locations"))
        graph = app.extensions["road_network"].get_graph_for_locations(locations)
        result = compare_algorithms(graph, locations)
        result["network"] = network_summary(graph)
        return jsonify(result)
    except RouteCoverageError as exc:
        return jsonify(error=str(exc)), 422
    except RoadNetworkError:
        return jsonify(error="Road data could not be loaded for this comparison. Check your connection and retry."), 503
    except RoutingError as exc:
        return jsonify(error=str(exc)), 422


if __name__ == "__main__":
    # Start the local development server when you run this file directly.
    app.run(use_reloader=True, use_debugger=False)
