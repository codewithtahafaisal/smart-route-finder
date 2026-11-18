// Shared request snapshots, response validation, and honest metric formatting.
window.RouteData = (() => {
  const algorithms = ["BFS", "DFS", "UCS", "A*"];
  const number = (value) => typeof value === "number" && Number.isFinite(value) && value >= 0;
  const integer = (value) => Number.isSafeInteger(value) && value >= 0;
  const coordinate = (point) => Array.isArray(point) && point.length === 2 && point.every(Number.isFinite) && Math.abs(point[0]) <= 90 && Math.abs(point[1]) <= 180;
  const equal = (a, b) => Math.abs(a - b) <= Math.max(1e-6, Math.abs(b) * 1e-9);
  function require(condition) {
    if (!condition) throw new Error("The server returned inconsistent route data. The previous successful journey has been kept. Please retry.");
  }

  function locations(report = true) {
    const inputs = RouteLocations.inputs().filter((input) => input.required || input.value.trim());
    const result = [];
    for (const input of inputs) {
      const point = RouteLocations.get(input);
      if (!point || !coordinate([point.lat, point.lon])) {
        if (report) {
          input.setCustomValidity("Choose a search suggestion or pick this location on the map.");
          input.reportValidity();
        }
        return null;
      }
      const label = input.closest(".form-field").querySelector("label").textContent.trim().replace(/\s*\*$/, "").trim();
      result.push({ id: input.id, label, name: input.value.trim(), lat: point.lat, lon: point.lon });
    }
    return result.length >= 2 ? result : null;
  }
  const key = (points) => points ? JSON.stringify(points.map((p) => [p.id, p.label, p.name, p.lat, p.lon])) : null;
  const currentKey = () => key(locations(false));

  function validateWaypoints(waypoints, requested) {
    require(Array.isArray(waypoints) && waypoints.length === requested.length);
    waypoints.forEach((point, index) => {
      const expected = requested[index];
      require(point && point.id === expected.id && point.label === expected.label && typeof point.name === "string");
      require(coordinate([point.lat, point.lon]) && Math.abs(point.lat - expected.lat) < 1e-9 && Math.abs(point.lon - expected.lon) < 1e-9);
      require(integer(point.node_id) && number(point.snap_distance_m));
    });
  }

  function directDistance(a, b) {
    const radians = (v) => v * Math.PI / 180;
    const lat1 = radians(a[0]), lat2 = radians(b[0]);
    const value = Math.sin((lat2 - lat1) / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(radians(b[1] - a[1]) / 2) ** 2;
    return 6371009 * 2 * Math.asin(Math.sqrt(Math.min(1, Math.max(0, value))));
  }

  function validateRoute(data, requested, algorithm) {
    require(data && algorithms.includes(data.algorithm) && data.algorithm === algorithm && ["found", "no_path"].includes(data.status));
    validateWaypoints(data.waypoints, requested);
    require(data.stop_count === requested.length - 2 && data.segment_count === requested.length - 1);
    require(Array.isArray(data.segments) && data.segments.length === data.segment_count);
    require(number(data.execution_ms) && integer(data.explored_count) && typeof data.message === "string");
    require(typeof data.travel_time_note === "string");
    require(Array.isArray(data.explored_nodes) && data.explored_nodes.length === data.explored_count && data.explored_nodes.every(integer));
    require(data.unique_explored_count === new Set(data.explored_nodes).size);
    require(data.estimated_travel_time_s === null || number(data.estimated_travel_time_s));
    const combined = [], path = [], failed = [];
    let distance = 0, explored = 0, execution = 0;
    data.segments.forEach((leg, index) => {
      const from = data.waypoints[index], to = data.waypoints[index + 1];
      require(leg && leg.algorithm === algorithm && leg.index === index + 1 && ["found", "no_path"].includes(leg.status));
      require(leg.from_id === from.id && leg.to_id === to.id && leg.from_node === from.node_id && leg.to_node === to.node_id);
      require([leg.from_label, leg.to_label, leg.from_name, leg.to_name].every((text) => typeof text === "string"));
      require(integer(leg.explored_count) && number(leg.execution_ms));
      require(Array.isArray(leg.explored_nodes) && leg.explored_nodes.length === leg.explored_count && leg.explored_nodes.every(integer));
      explored += leg.explored_count;
      execution += leg.execution_ms;
      if (leg.status === "no_path") {
        require(leg.path === null && leg.distance_m === null && Array.isArray(leg.geometry) && leg.geometry.length === 0);
        failed.push(leg.index);
        return;
      }
      require(number(leg.distance_m) && Array.isArray(leg.path) && leg.path.length > 0 && leg.path.every(integer));
      require(leg.path[0] === from.node_id && leg.path.at(-1) === to.node_id);
      require(Array.isArray(leg.geometry) && leg.geometry.length > 0 && leg.geometry.every(coordinate));
      // Endpoint proximity also catches reversed latitude/longitude, even when
      // both reversed numbers would otherwise be valid geographic coordinates.
      require(directDistance(leg.geometry[0], [from.lat, from.lon]) <= from.snap_distance_m + 5);
      require(directDistance(leg.geometry.at(-1), [to.lat, to.lon]) <= to.snap_distance_m + 5);
      (path.length ? leg.path.slice(1) : leg.path).forEach((node) => path.push(node));
      leg.geometry.forEach((point) => {
        if (!combined.length || point[0] !== combined.at(-1)[0] || point[1] !== combined.at(-1)[1]) combined.push(point);
      });
      distance += leg.distance_m;
    });
    require(data.explored_count === explored && equal(data.execution_ms, execution));
    require(Array.isArray(data.failed_segments) && JSON.stringify(data.failed_segments) === JSON.stringify(failed));
    if (data.status === "found") {
      require(!failed.length && number(data.distance_m) && equal(data.distance_m, distance));
      require(Array.isArray(data.path) && JSON.stringify(data.path) === JSON.stringify(path));
      require(Array.isArray(data.geometry) && JSON.stringify(data.geometry) === JSON.stringify(combined));
    } else {
      require(failed.length > 0 && data.path === null && data.distance_m === null && Array.isArray(data.geometry) && !data.geometry.length);
    }
    return data;
  }

  function validateComparison(data, requested) {
    require(data && Array.isArray(data.results) && data.results.length === algorithms.length);
    validateWaypoints(data.waypoints, requested);
    require(data.stop_count === requested.length - 2 && data.segment_count === requested.length - 1);
    require(new Set(data.results.map((row) => row.algorithm)).size === algorithms.length);
    data.results.forEach((row) => {
      require(algorithms.includes(row.algorithm));
      if (["found", "no_path"].includes(row.status)) validateRoute(row, requested, row.algorithm);
      else {
        require(["error", "unavailable"].includes(row.status) && typeof row.message === "string");
        require(row.path === null && row.distance_m === null && row.explored_count === null && Array.isArray(row.geometry) && row.geometry.length === 0);
        require(row.execution_ms === null || number(row.execution_ms));
      }
    });
    return data;
  }

  async function requestJSON(url, payload, signal) {
    const response = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload), signal });
    const data = await response.json().catch(() => { throw new Error("The server returned an unreadable response. Please retry."); });
    if (!response.ok) throw new Error(typeof data.error === "string" ? data.error : "The request failed. Please retry.");
    return data;
  }

  const format = {
    km: (meters) => !number(meters) ? "Unavailable" : meters > 0 && meters < 1 ? "<0.001 km" : `${(meters / 1000).toFixed(3)} km`,
    ms: (value) => !number(value) ? "Unavailable" : value > 0 && value < 0.01 ? "<0.01 ms" : `${value.toFixed(2)} ms`,
    count: (value) => integer(value) ? value.toLocaleString() : "Unavailable",
  };
  return { algorithms, locations, key, currentKey, validateRoute, validateComparison, requestJSON, format };
})();
