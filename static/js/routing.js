// The displayed successful journey is independent of the editable form draft.
(() => {
  const form = document.getElementById("route-form");
  const button = form.querySelector('[type="submit"]');
  const buttonLabel = document.getElementById("calculate-route-label");
  const status = document.getElementById("route-result-status");
  const note = document.getElementById("route-result-note");
  const notice = document.getElementById("displayed-route-note");
  const details = document.getElementById("journey-details");
  const attempt = document.getElementById("route-attempt");
  const values = Object.fromEntries(["algorithm", "distance", "travel-time", "explored", "execution", "stops", "segments"].map((name) => [name, document.getElementById(`result-${name}`)]));
  let lastSuccess, controller, failure = "", generation = 0;

  function message(text) {
    const element = document.getElementById("form-message");
    element.textContent = text;
    element.hidden = false;
  }
  function busy(value) {
    button.disabled = value;
    buttonLabel.textContent = value ? "Calculating…" : "Calculate Complete Route";
    if (value) button.setAttribute("aria-busy", "true");
    else button.removeAttribute("aria-busy");
  }
  function syncNotice(loading = false) {
    const stale = lastSuccess && (lastSuccess.key !== RouteData.currentKey() || lastSuccess.data.algorithm !== document.getElementById("algorithm").value);
    notice.hidden = !lastSuccess || (!stale && !failure && !loading);
    notice.textContent = loading ? "Calculating a new request. The map and results still show the last successful journey."
      : failure ? "The latest calculation failed. The map and results still show the last successful journey; it is not the newly requested route."
      : "Inputs changed. The map and results show the previous successful journey. Outlined markers are draft locations; recalculate to update.";
    if (lastSuccess) status.textContent = `${lastSuccess.data.algorithm}: ${stale || failure ? "previous successful route" : "complete route"}`;
    window.RouteMap?.setStale(Boolean(stale));
  }
  function changed() {
    generation += 1;
    controller?.abort();
    busy(false);
    syncNotice();
  }

  function renderSegments(container, data) {
    container.replaceChildren();
    data.segments.forEach((leg) => {
      const item = document.createElement("li");
      const title = document.createElement("strong");
      const summary = document.createElement("span");
      title.textContent = `${leg.from_label}: ${leg.from_name} → ${leg.to_label}: ${leg.to_name}`;
      const found = leg.status === "found";
      summary.textContent = `${found ? "Found" : "No path"} · ${found ? RouteData.format.km(leg.distance_m) : "Distance unavailable"} · ${RouteData.format.count(leg.explored_count)} explored nodes · ${RouteData.format.ms(leg.execution_ms)}`;
      if (!found) item.classList.add("segment-failed");
      item.append(title, summary);
      container.appendChild(item);
    });
  }

  function commit(data, requested) {
    // Validate before touching either view. Map layers are prepared before the
    // old layers are removed, then the dashboard commits in this same JS turn.
    RouteData.validateRoute(data, requested, data.algorithm);
    if (data.status !== "found") throw new Error("Only a complete successful journey can be displayed.");
    window.RouteMap?.showRoute(data);
    lastSuccess = { data, locations: requested, key: RouteData.key(requested) };
    failure = "";
    attempt.hidden = true;
    values.algorithm.textContent = data.algorithm;
    values.distance.textContent = RouteData.format.km(data.distance_m);
    values.explored.textContent = RouteData.format.count(data.explored_count);
    values.execution.textContent = RouteData.format.ms(data.execution_ms);
    values.stops.textContent = RouteData.format.count(data.stop_count);
    values.segments.textContent = RouteData.format.count(data.segment_count);
    values["travel-time"].textContent = data.estimated_travel_time_s === null ? "Not estimated" : `${(data.estimated_travel_time_s / 60).toFixed(1)} min`;
    values["travel-time"].title = data.travel_time_note;
    note.textContent = data.message;
    const list = document.getElementById("journey-locations");
    list.replaceChildren();
    data.waypoints.forEach((point) => {
      const item = document.createElement("li"), label = document.createElement("strong"), text = document.createElement("span");
      label.textContent = `${point.label} · ${point.name}`;
      text.textContent = `${point.lat.toFixed(5)}, ${point.lon.toFixed(5)} · ${point.snap_distance_m.toFixed(0)} m to the mapped road junction`;
      item.append(label, text);
      list.appendChild(item);
    });
    renderSegments(document.getElementById("segment-results"), data);
    details.hidden = false;
    if (data.network && typeof data.network.label === "string" && typeof data.network.detail === "string") {
      document.getElementById("road-network-state").textContent = data.network.label;
      document.getElementById("road-network-detail").textContent = `· ${data.network.detail}`;
      const networkStatus = document.getElementById("road-network-status");
      networkStatus.title = data.network.detail;
      networkStatus.querySelector(".status-dot").className = "status-dot network-dot-loaded";
    }
    syncNotice();
    message(data.message);
  }

  function failed(text, data = null, requested = []) {
    failure = text;
    attempt.hidden = false;
    const trail = requested.map((point) => point.name).join(" → ");
    document.getElementById("route-attempt-message").textContent = `${trail ? trail + ". " : ""}${text}${data ? ` Search effort: ${RouteData.format.count(data.explored_count)} explored nodes; ${RouteData.format.ms(data.execution_ms)}.` : ""}`;
    const list = document.getElementById("attempt-segments");
    if (data) renderSegments(list, data);
    else list.replaceChildren();
    if (!lastSuccess) {
      status.textContent = "No complete route";
      note.textContent = "No successful complete journey is displayed. Review the latest attempt below.";
    }
    syncNotice();
    message(text);
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const requested = RouteData.locations();
    if (!requested) { failed("Choose a search suggestion or map point for each entered location."); return; }
    const algorithm = document.getElementById("algorithm").value;
    if (!RouteData.algorithms.includes(algorithm)) { failed("Choose BFS, DFS, UCS, or A*."); return; }
    const requestKey = RouteData.key(requested), requestGeneration = ++generation;
    controller?.abort();
    controller = new AbortController();
    busy(true);
    syncNotice(true);
    message("Loading road data and calculating each segment. A new area may take a few minutes; saved areas are reused.");
    try {
      const response = await RouteData.requestJSON("/api/routes", { algorithm, locations: requested }, controller.signal);
      if (generation !== requestGeneration || requestKey !== RouteData.currentKey()) return;
      const data = RouteData.validateRoute(response, requested, algorithm);
      if (data.status === "found") commit(data, requested);
      else failed(data.message, data, requested);
    } catch (error) {
      if (error.name !== "AbortError" && generation === requestGeneration) failed(error.message === "Failed to fetch" ? "Cannot connect to Flask. Check that the application is running." : error.message, null, requested);
    } finally {
      if (generation === requestGeneration) busy(false);
    }
  });

  window.RouteDashboard = {
    showComparison(data, requested) {
      if (RouteData.key(requested) !== RouteData.currentKey()) { message("These comparison results belong to previous inputs. Compare the current journey before displaying a result."); return; }
      changed();
      document.getElementById("algorithm").value = data.algorithm;
      commit(data, requested);
    },
  };
  form.addEventListener("input", changed);
  form.addEventListener("change", changed);
  ["route:location-selected", "route:location-cleared", "route:stops-changed"].forEach((name) => document.addEventListener(name, changed));
  document.addEventListener("route:reset", () => {
    changed();
    lastSuccess = null;
    failure = "";
    details.hidden = attempt.hidden = notice.hidden = true;
    Object.entries(values).forEach(([name, element]) => element.textContent = name === "travel-time" ? "Not estimated" : "—");
    status.textContent = "Awaiting calculation";
    note.textContent = "Select locations and calculate a complete journey. Comparisons run separately when requested.";
  });
})();
