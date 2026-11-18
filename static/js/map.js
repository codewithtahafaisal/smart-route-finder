// Leaflet is loaded before this deferred script. Form behavior stays in script.js.
function initializeRouteMap() {
  const mapContainer = document.getElementById("route-map");
  const mapPanel = document.getElementById("map-preview");
  const targetSelect = document.getElementById("map-target");
  const clearButton = document.getElementById("clear-map-marker");
  const selectedLabel = document.getElementById("selected-location-label");
  const selectedCoordinates = document.getElementById("selected-coordinates");
  const mapStatus = document.getElementById("map-status");
  const mapError = document.getElementById("map-error");
  const locationForm = document.getElementById("route-form");
  const instructions = document.getElementById("map-instructions");
  const recenterButton = document.getElementById("recenter-route");
  const myLocationButton = document.getElementById("my-location");
  const myLocationLabel = document.getElementById("my-location-label");
  const viewMessage = document.getElementById("map-view-message");
  const relocateButton = document.getElementById("relocate-route");
  const karachi = [24.8607, 67.0011];
  const initialZoom = 12;

  // Keep the rest of the form usable if the CDN is blocked or unavailable.
  if (!window.L) {
    mapStatus.textContent = "Map unavailable";
    mapContainer.hidden = true;
    mapError.textContent = "The map library could not load. Check your internet connection and reload the page. You can still use the route form.";
    mapError.hidden = false;
    return;
  }

  if (!window.RouteLocations) {
    mapStatus.textContent = "Restart required";
    mapContainer.hidden = true;
    mapError.textContent = "This page is out of date. Stop Flask with Ctrl+C, start it again, then refresh the browser to restore map selection.";
    mapError.hidden = false;
    return;
  }

  const map = L.map(mapContainer, {
    zoomAnimation: false,
    fadeAnimation: false,
    markerZoomAnimation: false,
    worldCopyJump: true,
    minZoom: 2,
  }).setView(karachi, initialZoom);

  // One record per field: its input element, marker, and selected coordinates.
  const locations = new Map();
  let routeLine;
  let routeMarkers, routeSnapshot;
  let fitFrame = 0, followRoute = false, programmaticView = false;
  let currentLocationMarker;
  let locationRequest = 0;
  let viewVersion = 0;
  let tileLoadFailed = false;
  const tiles = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  });

  tiles.on("loading", () => {
    tileLoadFailed = false;
    mapStatus.textContent = "Loading tiles";
    mapError.hidden = true;
  });
  tiles.on("tileerror", () => {
    tileLoadFailed = true;
    mapStatus.textContent = "Tiles unavailable";
    mapError.textContent = "Some map tiles could not load. Check your internet connection and reload the page. Marker selection is still available.";
    mapError.hidden = false;
  });
  tiles.on("load", () => {
    mapStatus.textContent = tileLoadFailed ? "Tiles unavailable" : "OpenStreetMap";
  });
  tiles.addTo(map);

  function showViewMessage(text) {
    viewMessage.textContent = text;
    viewMessage.hidden = false;
  }

  function showFullJourney(announce = false) {
    if (routeSnapshot) {
      followRoute = true;
      scheduleRouteFit();
      if (announce) showViewMessage("Showing the last successful complete journey. Draft selections and current location are separate.");
      return;
    }
    // Before a successful route, the original control still fits draft markers.
    const bounds = L.latLngBounds([]);
    locations.forEach((location) => bounds.extend(location.latlng));
    if (routeLine) bounds.extend(routeLine.getBounds());
    if (!bounds.isValid()) {
      if (announce) showViewMessage("Select a start, stop, or destination to show your journey on the map.");
      return;
    }
    map.invalidateSize({ pan: false });
    map.fitBounds(bounds, { padding: [32, 32], maxZoom: 16, animate: false });
    if (announce) showViewMessage(routeLine ? "Showing the complete route and all journey markers." : "Showing your selected journey markers. Calculate the complete route to see the roads.");
  }

  function scheduleRouteFit() {
    cancelAnimationFrame(fitFrame);
    fitFrame = requestAnimationFrame(() => {
      if (!routeSnapshot || !followRoute) return;
      // Wait for real layout dimensions, not a guessed timeout. ResizeObserver
      // schedules another frame if the panel is currently hidden or collapsed.
      if (mapContainer.clientWidth <= 64 || mapContainer.clientHeight <= 92) return;
      const bounds = routeSnapshot.bounds;
      programmaticView = true;
      try {
        map.invalidateSize({ pan: false });
        const options = { paddingTopLeft: [32, 64], paddingBottomRight: [32, 32], maxZoom: 16, animate: false };
        map.fitBounds(bounds, options);
        if (!map.getBounds().contains(bounds)) map.fitBounds(bounds.pad(0.05), { ...options, maxZoom: Math.max(2, map.getZoom() - 1) });
      } finally { programmaticView = false; }
    });
  }

  function updateDraftVisibility() {
    locations.forEach((location) => {
      const previous = routeSnapshot?.waypoints.find((point) => point.id === location.input.id);
      const same = previous && previous.lat === location.latlng.lat && previous.lon === location.latlng.lng && previous.label === getFieldLabel(location.input);
      if (same) location.marker.remove();
      else {
        if (!map.hasLayer(location.marker)) location.marker.addTo(map);
        updateMarkerLabel(location);
      }
    });
  }

  relocateButton.addEventListener("click", () => {
    viewVersion += 1;
    if (!routeSnapshot) { showViewMessage("Calculate a complete successful route before using Relocate to Route."); return; }
    showFullJourney(true);
  });
  [["go-start", "starting-location", "starting location"], ["go-destination", "final-destination", "destination"]].forEach(([buttonId, inputId, label]) => {
    document.getElementById(buttonId).addEventListener("click", () => {
      const selection = RouteLocations.get(document.getElementById(inputId));
      if (!selection) { showViewMessage(`Select a ${label} first.`); return; }
      viewVersion += 1;
      followRoute = false;
      map.setView([selection.lat, selection.lon], 16, { animate: false });
      showViewMessage(`Showing the selected ${label}. Route layers and results are unchanged.`);
    });
  });
  map.on("dragstart", () => { followRoute = false; viewVersion += 1; });
  map.on("zoomstart", () => { if (!programmaticView) { followRoute = false; viewVersion += 1; } });

  function setLocationBusy(busy) {
    myLocationButton.disabled = busy;
    myLocationLabel.textContent = busy ? "Locating…" : "My Location";
    if (busy) myLocationButton.setAttribute("aria-busy", "true");
    else myLocationButton.removeAttribute("aria-busy");
  }

  recenterButton.addEventListener("click", () => {
    viewVersion += 1;  // A late geolocation result must not undo this view choice.
    showFullJourney(true);
  });

  myLocationButton.addEventListener("click", () => {
    if (!window.isSecureContext) {
      showViewMessage("My Location needs HTTPS or localhost. On this computer, open http://127.0.0.1:5000/ and try again.");
      return;
    }
    if (!navigator.geolocation) {
      showViewMessage("Your browser does not support current location. You can still choose journey locations on the map.");
      return;
    }
    const request = ++locationRequest;
    const requestedView = ++viewVersion;
    setLocationBusy(true);
    showViewMessage("Waiting for your browser's location. Allow location access if prompted; your journey selections stay unchanged.");

    function failure(error) {
      if (request !== locationRequest) return;
      setLocationBusy(false);
      const explanations = {
        1: "Location permission was denied. Allow location access in your browser's site settings, then try My Location again.",
        2: "Your current location is unavailable. Check your device's location settings and try again.",
        3: "The location request timed out. Please try My Location again.",
      };
      showViewMessage(explanations[error.code] || "Your browser could not provide a location. Please try again.");
    }

    // One request, only on this button click. No watchPosition or tracking loop.
    try {
      navigator.geolocation.getCurrentPosition((position) => {
        if (request !== locationRequest) return;
        const { latitude, longitude, accuracy } = position.coords;
        if (!Number.isFinite(latitude) || !Number.isFinite(longitude) || Math.abs(latitude) > 90 || Math.abs(longitude) > 180) {
          failure({ code: 2 });
          return;
        }
        setLocationBusy(false);
        const point = L.latLng(latitude, longitude);
        if (currentLocationMarker) currentLocationMarker.setLatLng(point);
        else {
          currentLocationMarker = L.marker(point, {
            icon: L.divIcon({ className: "current-location-marker", iconSize: [20, 20], iconAnchor: [10, 10] }),
            title: "Your current location (browser estimate)",
            zIndexOffset: 1000,
          }).addTo(map).bindTooltip("Your current location (browser estimate)");
          currentLocationMarker.getElement().setAttribute("aria-label", "Your current location, separate from the journey");
        }
        if (requestedView === viewVersion) { followRoute = false; map.setView(point, 16, { animate: false }); }
        const precision = Number.isFinite(accuracy) && accuracy >= 0 ? ` Reported accuracy: about ${Math.round(accuracy)} m.` : "";
        showViewMessage(`Current location: ${latitude.toFixed(5)}, ${longitude.toFixed(5)}.${precision} Your journey selections are unchanged.`);
      }, failure, { enableHighAccuracy: false, timeout: 15000, maximumAge: 0 });
    } catch {
      failure({ code: 2 });
    }
  });

  function getLocationInputs() {
    return [
      document.getElementById("starting-location"),
      ...document.querySelectorAll("#stop-list input"),
      document.getElementById("final-destination"),
    ];
  }

  function getFieldLabel(input) {
    if (input.id === "starting-location") return "Starting Location";
    if (input.id === "final-destination") return "Final Destination";
    return input.closest(".stop-row").querySelector("label").textContent;
  }

  function getMarkerLabel(input) {
    if (input.id === "starting-location") return "Start";
    if (input.id === "final-destination") return "Destination";
    return getFieldLabel(input);
  }

  function coordinateText(latlng) {
    return `Latitude: ${latlng.lat.toFixed(5)} · Longitude: ${latlng.lng.toFixed(5)}`;
  }

  function getCoordinateHint(input) {
    return input.closest(".form-field").querySelector(".location-coordinates");
  }

  function updateSelectionSummary() {
    const input = document.getElementById(targetSelect.value);
    if (!input) return;
    const location = locations.get(targetSelect.value);
    selectedLabel.textContent = getFieldLabel(input);
    selectedCoordinates.textContent = location
      ? coordinateText(location.latlng)
      : "No map location selected for this field.";
    clearButton.disabled = !location;
    instructions.textContent = location
      ? `${getFieldLabel(input)} selected. Click the map again or drag its marker to change it.`
      : `Click or tap the map to set ${getFieldLabel(input)}. Drag the map to explore.`;
    mapContainer.classList.add("is-picking");
    locationForm.querySelectorAll(".map-pick-button").forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.locationInput === input.id));
    });
  }

  function activateField(identifier, revealMarker = false) {
    const input = document.getElementById(identifier);
    if (!getLocationInputs().includes(input)) return;
    targetSelect.value = identifier;
    updateSelectionSummary();
    const location = locations.get(identifier);
    if (revealMarker) { followRoute = false; viewVersion += 1; }
    if (revealMarker && location) map.panTo(location.latlng, { animate: false });
  }

  function markerIcon(input) {
    let type = "stop";
    let text = getFieldLabel(input).replace("Stop ", "");
    if (input.id === "starting-location") {
      type = "start";
      text = "S";
    } else if (input.id === "final-destination") {
      type = "destination";
      text = "D";
    }
    return L.divIcon({
      className: `route-marker route-marker-${type}${routeSnapshot ? " route-marker-draft" : ""}`,
      html: `<span>${text}</span>`,
      iconSize: [32, 32],
      iconAnchor: [16, 16],
      tooltipAnchor: [0, -18],
    });
  }

  function updateMarkerLabel(location) {
    const label = getMarkerLabel(location.input);
    location.marker.setIcon(markerIcon(location.input));
    location.marker.bindTooltip(`${routeSnapshot ? "Draft " : ""}${label}`, { direction: "top" });
    const element = location.marker.getElement();
    if (element) {
      element.setAttribute("aria-label", `${routeSnapshot ? "Draft " : ""}${label}. ${coordinateText(location.latlng)}. Drag to move.`);
      element.title = label;
    }
  }

  function removeLocation(input) {
    const location = locations.get(input.id);
    if (!location) return;
    location.marker.remove();
    locations.delete(input.id);
  }

  function syncLocationFields() {
    const inputs = getLocationInputs();
    const previousTarget = targetSelect.value;

    // An ID may be reused after Reset, so also check the actual input element.
    locations.forEach((location) => {
      if (!inputs.includes(location.input)) removeLocation(location.input);
    });
    targetSelect.replaceChildren();
    inputs.forEach((input) => {
      const hint = getCoordinateHint(input);
      hint.id = `${input.id}-coordinates`;
      input.setAttribute("aria-describedby", hint.id);
      const option = document.createElement("option");
      option.value = input.id;
      option.textContent = getFieldLabel(input);
      targetSelect.appendChild(option);
      const location = locations.get(input.id);
      if (location) updateMarkerLabel(location);
    });
    targetSelect.value = inputs.some((input) => input.id === previousTarget)
      ? previousTarget
      : "starting-location";
    locationForm.querySelectorAll(".map-pick-button").forEach((button) => {
      button.disabled = false;
    });
    updateSelectionSummary();
    updateDraftVisibility();
  }

  function selectLocation(latlng) {
    const input = document.getElementById(targetSelect.value);
    if (!input) return;
    const point = latlng.wrap();
    RouteLocations.select(input, { lat: point.lat, lon: point.lng, source: "map" });
  }

  function showLocation(input, selection) {
    targetSelect.value = input.id;
    const point = L.latLng(selection.lat, selection.lon);
    let location = locations.get(input.id);
    if (location) {
      location.latlng = point;
      location.marker.setLatLng(point);
    } else {
      const marker = L.marker(point, {
        icon: markerIcon(input),
        draggable: true,
        autoPan: true,
      }).addTo(map);
      location = { input, marker, latlng: point };
      locations.set(input.id, location);
      marker.on("click", () => {
        targetSelect.value = input.id;
        updateSelectionSummary();
      });
      marker.on("dragend", () => {
        targetSelect.value = input.id;
        selectLocation(marker.getLatLng());
      });
    }

    updateMarkerLabel(location);
    updateSelectionSummary();
    updateDraftVisibility();
    if (selection.source !== "map") map.panTo(point, { animate: false });
  }

  document.addEventListener("route:location-selected", (event) => {
    showLocation(event.detail.input, event.detail.location);
  });
  document.addEventListener("route:location-cleared", (event) => {
    removeLocation(event.detail.input);
    updateSelectionSummary();
  });
  window.RouteMap = {
    setStale() { updateDraftVisibility(); },
    showRoute(data) {
      if (data.status !== "found" || !Array.isArray(data.geometry) || !data.geometry.length) throw new Error("A complete route with valid coordinates is required.");
      const bounds = L.latLngBounds(data.geometry);
      data.waypoints.forEach((point) => bounds.extend([point.lat, point.lon]));
      if (!bounds.isValid()) throw new Error("The route bounds are invalid. The previous route was kept.");
      const newLine = L.featureGroup(data.segments.map((segment) => {
        const tooltip = document.createElement("span");
        tooltip.textContent = `Segment ${segment.index}: ${segment.from_label} → ${segment.to_label}`;
        return L.polyline(segment.geometry, { color: "#087f83", weight: 4 }).bindTooltip(tooltip);
      }));
      const newMarkers = L.featureGroup(data.waypoints.map((point, index) => {
        const type = index === 0 ? "start" : index === data.waypoints.length - 1 ? "destination" : "stop";
        const text = type === "start" ? "S" : type === "destination" ? "D" : point.label.replace("Stop ", "");
        const marker = L.marker([point.lat, point.lon], {
          icon: L.divIcon({ className: `route-marker route-marker-${type} calculated-marker`, html: `<span>${text}</span>`, iconSize: [32, 32], iconAnchor: [16, 16] }),
          draggable: true, title: `${point.label}: ${point.name} (calculated journey; drag to edit a draft)`,
        });
        const markerTooltip = document.createElement("span");
        markerTooltip.textContent = `${point.label}: ${point.name}`;
        marker.bindTooltip(markerTooltip);
        marker.on("click", () => {
          const input = document.getElementById(point.id);
          if (input && getLocationInputs().includes(input)) activateField(point.id);
          else showViewMessage("This marker belongs to the previous successful journey.");
        });
        marker.on("dragend", () => {
          const changedPoint = marker.getLatLng();
          marker.setLatLng([point.lat, point.lon]);
          const input = document.getElementById(point.id);
          if (input && getLocationInputs().includes(input)) RouteLocations.select(input, { lat: changedPoint.lat, lon: changedPoint.lng, source: "map" });
          else showViewMessage("This marker belongs to the previous journey. Choose the new location using the form.");
        });
        return marker;
      }));
      try { newLine.addTo(map); newMarkers.addTo(map); }
      catch (error) { newLine.remove(); newMarkers.remove(); throw error; }
      routeLine?.remove();
      routeMarkers?.remove();
      routeLine = newLine;
      routeMarkers = newMarkers;
      routeSnapshot = { bounds, waypoints: data.waypoints };
      updateDraftVisibility();
      viewVersion += 1;
      followRoute = true;
      scheduleRouteFit();
    },
  };

  map.on("click", (event) => selectLocation(event.latlng));
  targetSelect.addEventListener("change", () => activateField(targetSelect.value, true));
  clearButton.addEventListener("click", () => {
    const input = document.getElementById(targetSelect.value);
    RouteLocations.clear(input, true);
    updateSelectionSummary();
    input.dispatchEvent(new Event("change", { bubbles: true }));
    mapContainer.focus({ preventScroll: true });
  });

  locationForm.addEventListener("click", (event) => {
    const button = event.target.closest(".map-pick-button");
    if (!button) return;
    activateField(button.dataset.locationInput, true);
    map.invalidateSize({ pan: false });
    mapPanel.scrollIntoView({ block: "start", behavior: "auto" });
    mapContainer.focus({ preventScroll: true });
  });
  locationForm.addEventListener("focusin", (event) => {
    if (getLocationInputs().includes(event.target)) activateField(event.target.id);
  });
  document.addEventListener("route:stops-changed", syncLocationFields);
  document.addEventListener("route:reset", () => {
    cancelAnimationFrame(fitFrame);
    routeLine?.remove();
    routeMarkers?.remove();
    routeLine = routeMarkers = routeSnapshot = undefined;
    followRoute = false;
    locationRequest += 1;  // Ignore any pending browser callback after a reset.
    viewVersion += 1;
    setLocationBusy(false);
    if (currentLocationMarker) { currentLocationMarker.remove(); currentLocationMarker = undefined; }
    viewMessage.hidden = true;
    locations.forEach((location) => removeLocation(location.input));
    targetSelect.value = "starting-location";
    syncLocationFields();
    map.setView(karachi, initialZoom, { animate: false });
  });
  mapContainer.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && event.target === mapContainer) {
      event.preventDefault();
      selectLocation(map.getCenter());
    }
  });

  // Observe the actual panel, including responsive changes unrelated to a window resize.
  if ("ResizeObserver" in window) {
    const resizeObserver = new ResizeObserver(() => {
      map.invalidateSize({ pan: false });
      if (followRoute && routeSnapshot) scheduleRouteFit();
    });
    resizeObserver.observe(mapContainer);
  }
  targetSelect.disabled = false;
  recenterButton.disabled = false;
  relocateButton.disabled = false;
  document.getElementById("go-start").disabled = false;
  document.getElementById("go-destination").disabled = false;
  myLocationButton.disabled = false;
  syncLocationFields();
}

initializeRouteMap();
