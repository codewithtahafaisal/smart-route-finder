// One source of truth for each field's coordinates, shared by search and map.
window.RouteLocations = (() => {
  const selections = new WeakMap();
  const inputs = () => [...document.querySelectorAll("#starting-location, #stop-list .stop-input, #final-destination")];
  const hintFor = (input) => input.closest(".form-field").querySelector(".location-coordinates");

  function clear(input, clearValue = false) {
    const hadSelection = selections.delete(input);
    const hint = hintFor(input);
    hint.textContent = "";
    hint.hidden = true;
    if (clearValue) input.value = "";
    if (hadSelection) document.dispatchEvent(new CustomEvent("route:location-cleared", { detail: { input } }));
  }

  function select(input, location) {
    const lat = Number(location.lat);
    const lon = Number(location.lon);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
    const selection = { ...location, lat, lon };
    selections.set(input, selection);
    input.value = selection.label || `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
    input.setCustomValidity("");
    const hint = hintFor(input);
    hint.id = `${input.id}-coordinates`;
    input.setAttribute("aria-describedby", hint.id);
    hint.textContent = `Latitude: ${lat.toFixed(5)} · Longitude: ${lon.toFixed(5)}`;
    hint.hidden = false;
    document.dispatchEvent(new CustomEvent("route:location-selected", { detail: { input, location: selection } }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }

  document.getElementById("route-form").addEventListener("input", (event) => {
    if (inputs().includes(event.target)) clear(event.target);
  });
  document.addEventListener("route:reset", () => inputs().forEach((input) => clear(input)));
  return { inputs, select, clear, get: (input) => selections.get(input) };
})();
