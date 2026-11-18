// Comparisons are explicit requests and never automatically replace the map.
(() => {
  const button = document.getElementById("compare-algorithms");
  const status = document.getElementById("comparison-status");
  const message = document.getElementById("comparison-message");
  const content = document.getElementById("comparison-results");
  const rows = document.getElementById("comparison-rows");
  let saved, pendingKey, controller, generation = 0;

  function busy(value) {
    button.disabled = value;
    button.textContent = value ? "Comparing…" : "Compare Algorithms";
    if (value) button.setAttribute("aria-busy", "true");
    else button.removeAttribute("aria-busy");
  }
  function refresh() {
    const current = RouteData.currentKey();
    if (controller && pendingKey !== current) {
      generation += 1;
      controller.abort();
      controller = null;
      busy(false);
      status.textContent = "Comparison canceled";
      message.textContent = "Locations changed while comparing. Press Compare Algorithms to compare the current journey.";
    }
    if (!saved) return;
    const stale = saved.key !== current;
    status.textContent = stale ? "Previous journey" : `${saved.data.results.filter((row) => row.status === "found").length} of 4 complete`;
    message.textContent = stale ? "These results belong to the comparison journey shown below. Compare the current locations to refresh them."
      : "Measured on identical locations, stop order, snapped nodes, and road graph. Use Show Route to explicitly display a successful comparison result.";
    rows.querySelectorAll("button").forEach((control) => {
      control.disabled = stale;
      control.title = stale ? "Compare the current journey before displaying a result" : "Display this measured route on the map and dashboard";
    });
  }

  function charts(data) {
    const container = document.getElementById("comparison-charts");
    container.replaceChildren();
    const successful = data.results.filter((row) => row.status === "found");
    if (!successful.length) {
      const empty = document.createElement("p");
      empty.textContent = "No complete successful routes are available for charts.";
      container.appendChild(empty);
      return;
    }
    [
      ["Route distance (km)", "distance_m", RouteData.format.km],
      ["Explored nodes", "explored_count", RouteData.format.count],
      ["Execution time (ms)", "execution_ms", RouteData.format.ms],
    ].forEach(([title, field, format]) => {
      const figure = document.createElement("figure"), caption = document.createElement("figcaption"), list = document.createElement("ul");
      caption.textContent = title;
      const maximum = Math.max(...successful.map((row) => row[field]));
      successful.forEach((row) => {
        const item = document.createElement("li"), name = document.createElement("span"), track = document.createElement("span"), bar = document.createElement("span"), value = document.createElement("span");
        name.textContent = row.algorithm;
        name.className = "chart-label";
        track.className = "chart-track";
        track.setAttribute("aria-hidden", "true");
        bar.className = "chart-bar";
        bar.style.width = `${maximum > 0 ? row[field] / maximum * 100 : 0}%`;
        track.appendChild(bar);
        value.className = "chart-value";
        value.textContent = format(row[field]);
        item.append(name, track, value);
        list.appendChild(item);
      });
      figure.append(caption, list);
      container.appendChild(figure);
    });
  }

  function render(data, requested) {
    saved = { data, requested, key: RouteData.key(requested) };
    content.hidden = false;
    document.getElementById("comparison-journey").textContent = requested.map((point) => `${point.label}: ${point.name}`).join(" → ") + ` · ${data.stop_count} stops · ${data.segment_count} segments`;
    rows.replaceChildren();
    const names = { found: "Complete", no_path: "No complete path", error: "Failed", unavailable: "Unavailable" };
    data.results.forEach((row) => {
      const tr = document.createElement("tr");
      [row.algorithm, RouteData.format.km(row.distance_m), RouteData.format.count(row.explored_count), RouteData.format.ms(row.execution_ms)].forEach((text) => {
        const td = document.createElement("td");
        td.textContent = text;
        tr.appendChild(td);
      });
      const state = document.createElement("td"), title = document.createElement("strong");
      title.textContent = names[row.status];
      state.appendChild(title);
      if (row.status !== "found") {
        const explanation = document.createElement("span");
        explanation.className = "comparison-error";
        explanation.textContent = row.message;
        state.appendChild(explanation);
      }
      const action = document.createElement("td");
      if (row.status === "found") {
        const show = document.createElement("button");
        show.type = "button";
        show.className = "button secondary-button comparison-show";
        show.textContent = "Show Route";
        show.setAttribute("aria-label", `Show ${row.algorithm} comparison route`);
        show.addEventListener("click", () => {
          try { RouteDashboard.showComparison({ ...row, network: data.network }, requested); }
          catch (error) { message.textContent = error.message; }
        });
        action.appendChild(show);
      } else action.textContent = "—";
      tr.append(state, action);
      rows.appendChild(tr);
    });
    charts(data);
    refresh();
  }

  button.addEventListener("click", async () => {
    if (!document.getElementById("route-form").reportValidity()) return;
    const requested = RouteData.locations();
    if (!requested) { message.textContent = "Select a suggestion or map point for every entered location before comparing."; return; }
    const version = ++generation;
    controller?.abort();
    controller = new AbortController();
    pendingKey = RouteData.key(requested);
    busy(true);
    status.textContent = "Comparing";
    message.textContent = "Running each custom algorithm on the same journey. The displayed route stays unchanged.";
    try {
      const data = await RouteData.requestJSON("/api/comparisons", { locations: requested }, controller.signal);
      if (version !== generation || pendingKey !== RouteData.currentKey()) return;
      render(RouteData.validateComparison(data, requested), requested);
    } catch (error) {
      if (error.name !== "AbortError" && version === generation) {
        status.textContent = "Comparison unavailable";
        message.textContent = `${error.message} ${saved ? "The previous comparison is retained for its stated journey." : ""}`;
      }
    } finally {
      if (version === generation) { busy(false); controller = null; }
    }
  });
  ["input", "change"].forEach((name) => document.getElementById("route-form").addEventListener(name, refresh));
  ["route:location-selected", "route:location-cleared", "route:stops-changed"].forEach((name) => document.addEventListener(name, refresh));
  document.addEventListener("route:reset", () => {
    generation += 1;
    controller?.abort();
    controller = saved = null;
    busy(false);
    content.hidden = true;
    rows.replaceChildren();
    document.getElementById("comparison-charts").replaceChildren();
    status.textContent = "Not run";
    message.textContent = "Choose locations, then press Compare Algorithms. Comparison does not change the displayed route.";
  });
})();
