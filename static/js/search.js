// Live Photon suggestions are debounced. The Search button uses Nominatim;
// public Nominatim is never queried automatically while the user types.
(() => {
  const form = document.getElementById("route-form");
  const autocomplete = form.dataset.autocomplete === "true";
  const states = new Map();

  function close(state) {
    clearTimeout(state.timer);
    state.controller?.abort();
    state.version += 1;
    state.results = [];
    state.active = -1;
    state.panel.hidden = true;
    state.input.setAttribute("aria-expanded", "false");
    state.input.removeAttribute("aria-activedescendant");
    state.button.disabled = false;
    state.button.textContent = "Search";
    state.input.removeAttribute("aria-busy");
  }

  function announce(state, message) {
    state.list.replaceChildren();
    state.message.textContent = message;
    state.panel.hidden = false;
    state.input.setAttribute("aria-expanded", "true");
  }

  function choose(state, result) {
    close(state);
    RouteLocations.select(state.input, result);
    state.input.focus();
  }

  async function search(state, trigger = "submit") {
    close(state);
    const query = state.input.value.trim();
    if (query.length < 3) {
      announce(state, "Enter at least 3 characters, then press Search.");
      return;
    }
    const version = state.version;
    state.controller = new AbortController();
    state.button.disabled = true;
    state.button.textContent = "Searching…";
    state.input.setAttribute("aria-busy", "true");
    announce(state, "Finding matching Karachi locations…");
    try {
      const response = await fetch("/api/locations/search", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, trigger }), signal: state.controller.signal,
      });
      const data = await response.json().catch(() => { throw new Error("Location search returned an invalid response. Please retry."); });
      if (version !== state.version || !state.input.isConnected || query !== state.input.value.trim()) return;
      if (!response.ok) throw new Error(data.error || "Location search failed. Please retry.");
      if (!Array.isArray(data.results)) throw new Error("Location search returned an invalid response. Please retry.");
      state.results = data.results;
      state.active = -1;
      state.attribution.firstChild.textContent = `${data.provider || form.dataset.searchProvider || "OpenStreetMap search"} · `;
      announce(state, data.results.length ? "Choose a location:" : "No matching Karachi locations found. Try a fuller name, press Search, or pick on the map.");
      data.results.forEach((result, index) => {
        const item = document.createElement("li");
        item.id = `${state.input.id}-result-${index}`;
        item.setAttribute("role", "option");
        item.setAttribute("aria-selected", "false");
        const label = document.createElement("strong");
        label.textContent = result.label;
        const details = document.createElement("span");
        details.textContent = result.details;
        item.append(label, details);
        item.addEventListener("mousedown", (event) => event.preventDefault());
        item.addEventListener("click", () => choose(state, result));
        state.list.appendChild(item);
      });
    } catch (error) {
      if (error.name !== "AbortError" && version === state.version && state.input.isConnected) {
        const explanation = error.message === "Failed to fetch" ? "Search could not connect. Check your internet connection and retry." : error.message;
        announce(state, explanation + (trigger === "typing" ? " You can also press Search for a full-name search." : ""));
      }
    } finally {
      if (version === state.version) {
        state.button.disabled = false;
        state.button.textContent = "Search";
        state.input.removeAttribute("aria-busy");
      }
    }
  }

  function attach(input) {
    if (states.has(input)) return;
    const control = document.createElement("div");
    control.className = "location-search-control";
    input.before(control);
    control.appendChild(input);
    const button = document.createElement("button");
    button.type = "button";
    button.className = "button location-search-button";
    button.textContent = "Search";
    button.setAttribute("aria-label", "Search locations for this field");
    control.appendChild(button);
    const panel = document.createElement("div");
    panel.className = "location-suggestions";
    panel.hidden = true;
    const message = document.createElement("p");
    message.className = "search-message";
    message.setAttribute("role", "status");
    const list = document.createElement("ul");
    list.id = `${input.id}-suggestions`;
    list.setAttribute("role", "listbox");
    list.setAttribute("aria-label", "Karachi location results");
    const attribution = document.createElement("p");
    attribution.className = "search-attribution";
    const link = document.createElement("a");
    link.href = "https://www.openstreetmap.org/copyright";
    link.textContent = "© OpenStreetMap contributors";
    attribution.append(`${form.dataset.searchProvider || "Photon"} · `, link);
    panel.append(message, list, attribution);
    control.appendChild(panel);
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("aria-controls", list.id);
    input.setAttribute("aria-expanded", "false");
    const state = { input, button, panel, message, list, attribution, results: [], active: -1, version: 0 };
    states.set(input, state);
    button.addEventListener("click", () => search(state));
    input.addEventListener("input", () => {
      close(state);
      state.results = [];
      if (input.value.trim().length < 3) return;
      if (autocomplete) state.timer = setTimeout(() => search(state, "typing"), 700);
      else announce(state, "Press Search or Enter to find matching Karachi locations.");
    });
    input.addEventListener("keydown", (event) => {
      if (event.key === "Escape") close(state);
      if (["ArrowDown", "ArrowUp"].includes(event.key) && !panel.hidden && state.results.length) {
        event.preventDefault();
        state.active = (state.active + (event.key === "ArrowDown" ? 1 : -1) + state.results.length) % state.results.length;
        [...list.children].forEach((item, index) => item.setAttribute("aria-selected", String(index === state.active)));
        const active = list.children[state.active];
        input.setAttribute("aria-activedescendant", active.id);
        active.scrollIntoView({ block: "nearest" });
      }
      if (event.key === "Enter") {
        event.preventDefault();
        event.stopPropagation();
        if (!panel.hidden && state.active >= 0 && state.results[state.active]) choose(state, state.results[state.active]);
        else search(state);
      }
      if (event.key === "Tab") close(state);
    });
  }

  function syncFields() {
    const inputs = RouteLocations.inputs();
    states.forEach((state, input) => {
      if (!inputs.includes(input)) { close(state); states.delete(input); }
    });
    inputs.forEach(attach);
    inputs.forEach((input) => {
      const label = input.closest(".form-field").querySelector("label").textContent.trim();
      states.get(input).button.setAttribute("aria-label", `Search locations for ${label}`);
    });
  }
  document.addEventListener("click", (event) => {
    states.forEach((state) => {
      if (!state.input.closest(".form-field").contains(event.target)) close(state);
    });
  });
  document.addEventListener("route:location-selected", (event) => {
    const state = states.get(event.detail.input);
    if (state) close(state);
  });
  document.addEventListener("route:stops-changed", syncFields);
  document.addEventListener("route:reset", () => states.forEach(close));
  syncFields();
})();
