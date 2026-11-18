// Manage repeatable stops and form reset. Search/routing live in separate files.
const routeForm = document.getElementById("route-form");
const routeFields = document.getElementById("route-fields");
const startingLocation = document.getElementById("starting-location");
const finalDestination = document.getElementById("final-destination");
const stopList = document.getElementById("stop-list");
const stopTemplate = document.getElementById("stop-template");
const addStopButton = document.getElementById("add-stop");
const formMessage = document.getElementById("form-message");
const stopAnnouncement = document.getElementById("stop-announcement");

let nextStopId = 1;

function clearFormMessage() {
  formMessage.textContent = "";
  formMessage.hidden = true;
}

// Keep visible labels and accessible remove-button names in the same order.
function updateStopLabels() {
  stopList.querySelectorAll(".stop-row").forEach((row, index) => {
    const stopNumber = index + 1;
    const input = row.querySelector("input");
    const label = row.querySelector("label");
    const removeButton = row.querySelector(".remove-stop");

    label.textContent = `Stop ${stopNumber}`;
    label.htmlFor = input.id;
    removeButton.setAttribute("aria-label", `Remove stop ${stopNumber}`);
    removeButton.title = `Remove stop ${stopNumber}`;
    const upButton = row.querySelector(".move-stop-up");
    const downButton = row.querySelector(".move-stop-down");
    upButton.disabled = index === 0;
    downButton.disabled = index === stopList.children.length - 1;
    upButton.setAttribute("aria-label", `Move stop ${stopNumber} up`);
    downButton.setAttribute("aria-label", `Move stop ${stopNumber} down`);
    const pickButton = row.querySelector(".map-pick-button");
    pickButton.dataset.locationInput = input.id;
    pickButton.setAttribute("aria-label", `Pick location for stop ${stopNumber} on map`);
  });

  // Let the map update its field selector and remove any deleted stop's marker.
  addStopButton.disabled = stopList.children.length >= 20;
  document.dispatchEvent(new CustomEvent("route:stops-changed"));
}

function addStop(focusInput = true) {
  if (stopList.children.length >= 20) return;
  const row = stopTemplate.content.firstElementChild.cloneNode(true);
  const input = row.querySelector("input");

  // IDs stay unique even after a stop in the middle of the list is removed.
  input.id = `stop-${nextStopId}`;
  nextStopId += 1;
  stopList.appendChild(row);
  updateStopLabels();
  clearFormMessage();

  if (focusInput) {
    input.focus();
    stopAnnouncement.textContent = `Stop ${stopList.children.length} added.`;
  }
}

addStopButton.addEventListener("click", () => addStop());

// One listener handles the remove buttons on both existing and new rows.
stopList.addEventListener("click", (event) => {
  const orderButton = event.target.closest(".stop-order-button");
  if (orderButton) {
    const row = orderButton.closest(".stop-row");
    const moveUp = orderButton.classList.contains("move-stop-up");
    const adjacent = moveUp ? row.previousElementSibling : row.nextElementSibling;
    if (!adjacent) return;
    // Move the existing DOM row, retaining its input and selected coordinates.
    stopList.insertBefore(moveUp ? row : adjacent, moveUp ? adjacent : row);
    updateStopLabels();
    clearFormMessage();
    row.querySelector("input").focus();
    stopAnnouncement.textContent = "Stop order updated. Recalculate the complete route.";
    return;
  }
  const removeButton = event.target.closest(".remove-stop");
  if (!removeButton) return;

  const row = removeButton.closest(".stop-row");
  const removedLabel = row.querySelector("label").textContent;
  const adjacentRow = row.nextElementSibling || row.previousElementSibling;

  row.remove();
  updateStopLabels();
  clearFormMessage();
  stopAnnouncement.textContent = `${removedLabel} removed.`;

  // Keep focus in a useful place after the clicked button disappears.
  if (adjacentRow) {
    adjacentRow.querySelector("input").focus();
  } else {
    addStopButton.focus();
  }
});

routeForm.addEventListener("input", (event) => {
  if (event.target instanceof HTMLInputElement) {
    event.target.setCustomValidity("");
  }
  clearFormMessage();
});

routeForm.addEventListener("change", clearFormMessage);

routeForm.addEventListener("reset", () => {
  // The browser resets the starting location, destination, and algorithm.
  // Rebuild the dynamic list to restore one empty optional stop as well.
  stopList.replaceChildren();
  nextStopId = 1;
  addStop(false);
  startingLocation.setCustomValidity("");
  finalDestination.setCustomValidity("");
  stopAnnouncement.textContent = "Form reset. One optional stop is available.";
  document.dispatchEvent(new CustomEvent("route:reset"));
  startingLocation.focus();
});

// Initial state: empty locations, one optional stop, and BFS selected in HTML.
addStop(false);
routeFields.disabled = false;
