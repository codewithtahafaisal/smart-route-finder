# Smart Route Finder

A beginner-friendly Python web application built with Flask. The homepage is a
responsive route planning dashboard with a route form, an interactive Leaflet
map using OpenStreetMap tiles, and a clearly labeled results panel. The map
starts in Karachi, Pakistan. OSMnx automatically prepares and caches real driving
roads covering your selected locations. Location search and manual BFS, DFS, UCS,
and A* are available. Complete journeys visit intermediate stops in the user's
order using the saved graph. Map controls show the full journey or your current
browser-provided location independently. No paid map APIs are needed.
The results dashboard also compares all four algorithms on the same journey
and graph, with measured tables/charts and reliable route navigation controls.

## Project structure

```text
Smart Route Finder/
|-- .venv/                 # The project's isolated Python environment
|-- app.py                 # Flask application and homepage URL
|-- road_network.py        # Download, validate, save, and load road graphs
|-- road_network_config.json # Configurable center, size, and Overpass settings
|-- geocoding.py            # Cached Photon autocomplete + Nominatim searches
|-- routing.py              # Manual BFS/DFS/UCS/A*, snapping, and ordered journeys
|-- comparison.py           # All algorithms share one graph and snapping pass
|-- requirements.txt       # Python packages this project needs
|-- data/
|   |-- README.md          # Generated data and attribution notes
|   |-- karachi_drive_<area-id>.graphml # Generated graph for one selected area
|   |-- route_drive_<bounds>.graphml # Automatically generated route-area graphs
|   |-- geocoding_cache.sqlite3 # Generated place-search cache and request limit
|   `-- osmnx_cache/       # Generated cached OpenStreetMap API responses
|-- tests/
|   |-- test_road_network.py # Graph storage checks
|   |-- test_adaptive_network.py # Automatic coverage and cache reuse
|   |-- test_geocoding.py   # Search cache, rate limit, and error checks
|   |-- test_routing.py     # BFS/DFS, snapping, and ordered stops
|   |-- test_weighted_search.py # UCS/A* optimality and heuristic checks
|   |-- test_multistop.py    # Ordered legs, totals, revisits, and failed journeys
|   |-- test_comparison.py   # Shared inputs/graph, failures, timings, and API
|   `-- test_app.py         # Flask endpoints and asset checks
|-- templates/
|   `-- index.html         # Homepage HTML
|-- static/
|   |-- css/
|   |   `-- style.css      # Homepage appearance
|   `-- js/
|       |-- locations.js   # Independent field-coordinate selections
|       |-- script.js      # Add/remove stops, reset, and form feedback
|       |-- route-data.js   # Request snapshots, response validation, formatting
|       |-- map.js         # Journey markers/roads, recenter, and one-shot geolocation
|       |-- search.js      # Location result dropdowns and keyboard controls
|       |-- routing.js     # Successful dashboard snapshot and failed attempts
|       `-- comparison.js  # Comparison requests, table, CSS charts, Show Route
|-- .gitignore             # Files to exclude from Git
`-- README.md              # These instructions
```

Flask looks for HTML pages in `templates/` and serves CSS and JavaScript from
`static/`. A virtual environment keeps this project's packages separate from
other Python projects. Do not edit files inside `.venv/`.

## First-time setup (Windows PowerShell)

Python, pip, and the virtual environment were checked during setup. The steps
below show how to set up the project again if needed. If `.venv` and the installed
dependencies are already present, skip to **Start the application**.

### 1. Open the project folder

Open a PowerShell terminal and run:

```powershell
cd "path\to\smart-route-finder"
```

If you move the project, use its new folder location instead.

### 2. Check Python and pip

```powershell
python --version
python -m pip --version
```

Each command should print a version. Use `python` on this computer: the separate
`py` launcher did not detect the installed Python during setup.

If Python is missing on another computer, install Python from
[python.org](https://www.python.org/downloads/), enable the installer's option to
add Python to PATH, and reopen PowerShell. If pip is missing, run
`python -m ensurepip --upgrade`, then check again.

### 3. Create a virtual environment

Run this once, or if the `.venv` folder is missing:

```powershell
python -m venv .venv
```

### 4. Install dependencies

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

An internet connection is needed to download the packages. `requirements.txt`
contains Flask, OSMnx, NetworkX, requests, and scikit-learn. Scikit-learn is needed
for OSMnx's nearest-node lookup on the latitude/longitude graph. Pip also installs their required supporting
packages, including NumPy, pandas, GeoPandas, Shapely, pyproj, and requests.
Compatible Windows wheels were verified with this project's Python 3.15
environment. You do not need to install these supporting packages separately.

These instructions call the environment's Python directly, so activation is
optional and no PowerShell execution policy change is needed.

## Prepare the road network

**Normal use no longer requires manual area preparation.** Select locations
and click **Calculate Complete Route** or **Compare Algorithms**. The app:

1. Reuses an existing graph if it covers every selected location.
2. Otherwise downloads actual driving roads around the selected points, with
   surrounding roads included for connections and detours.
3. Validates and saves a separate GraphML file, then runs the selected custom
   search for every leg in the order you entered.

The first request for a new area can take a few minutes. The interface shows
**Calculating journey** during this time. Subsequent requests, including nearby
locations inside an already cached area, reuse local files without downloading
again. The road-network indicator updates to the actual graph used by the route.
Road data is requested only after Calculate Complete Route or Compare Algorithms,
never on map movement or autocomplete keystrokes. Valid locations are not restricted to the old small
central-Karachi pilot area.

The original small-area CLI is still available as an **optional pilot preload**:

```powershell
.\.venv\Scripts\python.exe road_network.py prepare
```

This downloads real OpenStreetMap driving-road data through the Overpass API,
validates it, saves GraphML in `data/`, and checks that the saved graph can be
loaded again. The command prints the exact file path and actual node/edge counts.
Public Overpass servers can be busy, so preparation may take a few minutes.

Run the same command again to reuse the existing GraphML without downloading:

```powershell
.\.venv\Scripts\python.exe road_network.py prepare
```

To load and check the graph without any internet requests:

```powershell
.\.venv\Scripts\python.exe road_network.py check
```

Opening or refreshing the page **never starts a road-data download**. Without
preloaded data the status shows **On demand**; Calculate Complete Route prepares
the required area automatically. Existing valid saved graphs remain available if a new
download fails. A corrupt automatically generated area is rebuilt when needed.

### Select a manageable Karachi area

Edit `road_network_config.json`:

- `center`: `[latitude, longitude]`, initially `[24.8607, 67.0011]` in Karachi.
- `distance_m`: initially `1000`. This is the approximate distance from the
  center to each side of a bounding box, so the selected area is about 2 km by
  2 km. It is not a road-distance radius. OSMnx may query an additional boundary
  buffer when constructing the graph.
- `request_timeout_seconds`: initially `90` per HTTP request. OSMnx's public
  server rate-limit waits and retries can add time beyond this request timeout.
- `overpass_url`: the HTTPS Overpass API base URL, initially
  `https://overpass-api.de/api`.
- `route_buffer_m`: initially `1500`. Surrounding road coverage added around the
  selected locations for automatic downloads. Bounds are rounded outward on a
  0.01-degree grid so nearby requests can reuse the same saved area.
- `route_max_area_km2`: initially `2500`. A limit on a single automatic download
  to keep this local educational app manageable. Very long intercity trips need
  a suitable regional dataset rather than an enormous on-demand download.

Start with `distance_m` between 500 and 1500. The configuration accepts distances
from 100 to 5000 meters to help avoid accidental city-wide downloads. Different
centers or sizes produce separate filenames, preserving previously prepared
areas. `center` and `distance_m` configure only the optional original pilot,
not which locations the route interface accepts. Route requests automatically
select their own coverage from the chosen coordinates.

An alternative configuration file can be supplied with
`road_network.py prepare --config path\to\area.json`. The homepage always uses
the project's `road_network_config.json`.

### Graph representation and validation

OSMnx returns a NetworkX **MultiDiGraph**, so no lossy graph conversion is needed:

- Nodes retain their OpenStreetMap integer IDs. `graph.nodes[node_id]["y"]`
  is latitude and `["x"]` is longitude in EPSG:4326.
- Directed edges preserve permitted driving direction, including one-way roads.
  Multiple road segments can connect the same pair of nodes with different keys.
- Each edge has a numeric, nonnegative `length` in **meters**. BFS/DFS do not use
  this weight to choose the node path; it measures the discovered route afterward.
  UCS and A* use this same length as their search cost.
- OSMnx simplifies intermediate geometry points while preserving junctions,
  road geometry, lengths, and useful road tags such as `osmid` and `oneway`.
  The largest weakly connected component is kept; disconnected fragments may
  be omitted. Weak connectivity does not guarantee a drivable path between
  every pair of nodes.
- Saved graph metadata identifies the selected area, source, and preparation
  time. Validation checks every node's coordinates, every edge's length, graph
  direction/type, and the selected-area identity. Invalid weights are rejected.

For later Python work, use:

```python
from road_network import load_config, load_graph

graph = load_graph(load_config())  # Local GraphML only; no download
print(graph.number_of_nodes(), graph.number_of_edges())
```

### Repair and test graph storage

If GraphML is corrupt, `check` and `prepare` report a clear error instead of
silently replacing it. Rebuild explicitly:

```powershell
.\.venv\Scripts\python.exe road_network.py prepare --rebuild
.\.venv\Scripts\python.exe road_network.py check
```

`--rebuild` bypasses GraphML but still reuses OSMnx's cached Overpass response
when available. It does not guarantee a fresh OSM snapshot. A failed download
or save leaves any previous GraphML file intact. GraphML is written to a temporary
file and loaded/validated before replacing the final file.

Run the automated tests without downloading any data:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

These tests use clearly synthetic fixtures in temporary directories, never as
application road data. They cover coordinate/weight validation, ID and direction
preservation, parallel edges, missing/invalid files, download failure, failed
saves, and cache reuse. The `check` command validates the actual saved OSM graph.

Source: © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright),
licensed under ODbL. See the official [OSMnx documentation](https://osmnx.readthedocs.io/en/stable/user-reference.html)
for graph construction and GraphML storage details.

## Start the application

From the project folder, run:

```powershell
.\.venv\Scripts\python.exe app.py
```

Leave the terminal open. In your browser, visit:

**http://127.0.0.1:5000/**

You should see the **Smart Route Finder** dashboard, including the route form,
interactive Karachi map, and route result placeholders. JavaScript must be
enabled. An internet connection is needed for Leaflet's CDN files and map tiles.

Press **Ctrl+C** in the terminal to stop the server. The development server now
restarts automatically after backend changes. Templates reload on refresh, and
changed CSS/JavaScript URLs are versioned to avoid stale browser files.

**After updating from the older version, restart Flask once**, then press
**Ctrl+Shift+R** in the browser. A previously running server may still be serving
an older cached page without the coordinate script, which prevents map markers
from appearing. Automatic reload takes effect after this one-time restart.

Flask's built-in server is for local development. It is sufficient for this
stage of the project.

### Optional: activate the environment

You can use shorter commands after activating the environment in your current
PowerShell terminal:

```powershell
.\.venv\Scripts\Activate.ps1
python app.py
```

If PowerShell blocks the activation script, use the direct command in
**Start the application** instead. To leave an activated environment, run
`deactivate`.

## Test the frontend

1. Start the app and open **http://127.0.0.1:5000/**. The initial form should
   contain empty starting and final locations, one empty optional intermediate
   stop, and **BFS** selected.
2. Click **Add Stop** several times. Each new stop should have a numbered label
   and receive keyboard focus.
3. Enter different text in the stops. Click a stop's **X** button to remove that
   row. The remaining stop labels should be renumbered and keep their values.
   You can remove all stops or add more afterward.
4. Open **Search algorithm** and choose **BFS**, **DFS**, **UCS**, or **A***.
   All four choices are enabled and connected to the backend.
5. Click **Calculate Complete Route** with empty required locations to see validation. Plain
   typed text is insufficient: select a Search result or pick a map point for
   each entered location. A start and destination without filled stops runs a
   real single-leg search. Selected stops add individual legs in their entered order.
6. Add and fill several stops, choose a different algorithm, and click **Reset**.
   All locations should clear, the list should return to one optional stop,
   **BFS** should be selected, and the informational message should disappear.
   All map markers should clear and the map should return to Karachi.
7. Resize your browser or use its device preview to try desktop, tablet, and
   mobile widths. The panels should stack on smaller screens without horizontal
   scrolling. The navigation links should jump to their matching sections.
8. Use **Tab** and **Shift+Tab** to move through the controls. The focused control
   should have a visible outline; remove buttons have accessible stop names.

## Steps 5–7: location search and four route-search algorithms

### Live suggestions with Photon

Type at least **3 characters**, pause for about **700 ms**, and choose a location
from the dropdown. Live suggestions use [Photon](https://github.com/komoot/photon),
an OpenStreetMap geocoder designed for search-as-you-type. No account or API key
is required for the default public demo service. Searches prefer Karachi and
are restricted to the local bounding box and Pakistan.

The **Search** button and an explicit **Enter** search still use Nominatim for
full place-name searches. This provides another search option if a name does
not appear in live suggestions. The
[public Nominatim usage policy](https://operations.osmfoundation.org/policies/nominatim/)
prohibits autocomplete, so typing never sends automatic requests to that service.

The backend identifies this application with a custom User-Agent, limits all
local fields/users/processes to at most one upstream request every 1.1 seconds,
and caches successful searches (including no-result searches) for seven days in
`data/geocoding_cache.sqlite3`. Search results show OpenStreetMap attribution.
Names, addresses, and coordinates come from actual provider responses; no fake
suggestions are provided. Photon and Nominatim use separate cache keys while
sharing the application-wide request limit. Use public place names rather than
confidential information. Photon's public demo is best-effort and may throttle
heavy use; production deployments should choose an appropriate hosted or private
service. `PHOTON_URL` can change its endpoint without editing source code.

For a self-hosted or approved Nominatim-compatible service that permits
autocomplete, set these environment variables **before** starting Flask:

```powershell
$env:NOMINATIM_URL = "http://localhost:8080/search"
$env:GEOCODING_AUTOCOMPLETE = "1"
```

That example requires a separately running provider at that address; this
project does not install one. A permitted custom Nominatim provider takes over
live suggestions with the same 700 ms debounce. The backend always disables
autocomplete on the public Nominatim host and uses Photon instead. Clear these
variables or open a new terminal to return to the defaults.

### Test selecting real locations

1. Type **Sadd** in Starting Location, pause, and look for Karachi suggestions
   such as **Saddar**. No Search click is needed. **Denso** is another tested
   prefix. While loading, the dropdown shows a searching message. You can also
   type **Denso Hall** and press Search for a full Nominatim search.
2. Choose a result using a click, or **Arrow Down / Arrow Up** and **Enter**.
   **Escape** closes the dropdown. The name stays in the input, its coordinates
   appear below it, and its marker appears on the map.
3. Repeat for a destination or stop. Each field stores its own coordinates.
   A selection in one field must not alter another field's location.
4. Search for a term with no match to see the no-results message. If a request
   fails, the dropdown shows an error with a retry instruction.
5. Edit a selected name. Its draft coordinates and draft marker are cleared.
   The last successful route/results remain visible with a previous-journey
   notice. Select a fresh result or use the map before calculating again.
6. Add and remove stops, or Reset while a search is pending. Deleted/edited fields
   must not receive a late response, and Reset must restore the original form.

### Test all four algorithms on the real graph

1. Leave optional stops empty. Select **Denso Hall** as the start, then choose
   the destination using **Pick on map**, or choose **Saddar** from suggestions
   to test locations outside the original pilot area.
2. Select **BFS** and press **Calculate Complete Route**. A discovered path is drawn using its
   saved road geometry. Results show actual road distance, explored-node count,
   and measured search execution time. Travel time stays unestimated.
3. Select **DFS**, **UCS**, and **A*** in turn and repeat with the same locations.
   The badge identifies the selected algorithm. UCS and A* should report the
   same optimal road distance, though equal-cost paths may differ. BFS and DFS
   can return longer routes. Explored-node counts and execution times can differ.
4. Choose a location outside the pilot area and calculate again. The app should
   reuse covering data or automatically load a new area, not ask you to prepare
   central Karachi manually. A genuine missing road connection is still handled:
   points more than **250 meters** from a suitable road junction are rejected
   rather than silently snapped to a distant, unrelated road.
5. Edit a field, move a marker, or add/remove a stop. The previous successful
   route and metrics remain together with a clear notice. A new complete
   success replaces them together. **Reset** clears everything.
6. Add a selected stop and press **Calculate Complete Route**. The backend
   calculates Start → Stop 1 → … → Destination in your order. Results include
   the complete route, each leg, nearest node IDs, and offsets. Stops are never
   automatically reordered.

**BFS** uses a queue: it checks nodes one edge away, then two edges away, and so
on. It finds the fewest edges, which may be a longer physical distance.
**DFS** uses a stack: it follows a branch before returning to other branches.
It finds a path when one exists but does not guarantee the shortest route.
Both implementations are written manually in `routing.py`.

**UCS (Uniform Cost Search)** keeps a priority queue of candidates and always
expands the node with the smallest total road distance from the start. A cost
dictionary remembers the best distance found so far, and a parent dictionary
records how to reconstruct the route. Because road lengths are nonnegative,
the destination's first expansion gives a shortest-distance route.

**A* (A-Star Search)** also keeps a priority queue. It ranks a candidate by
`f = g + h`: the actual distance already traveled (`g`), plus an estimated
remaining distance (`h`). Its g-score, f-score, and parent dictionaries track
these values and reconstruct the route. It can explore fewer nodes than UCS.

All four algorithms track explored nodes, respect directed roads, and return
a clear no-path result. None uses NetworkX's built-in pathfinding functions or
an external routing API. Optimality means shortest distance within the loaded
road graph, not guaranteed best travel time or coverage of roads outside it.

### How A* estimates the remaining distance

The **Haversine formula** calculates the direct geographic distance between a
node's latitude/longitude and the destination, in meters. It uses Earth's mean
radius of 6,371,009 meters, matching OSMnx's distance convention. A road usually
cannot be shorter than the direct distance between its endpoints, so this is a
useful lower bound on how much driving remains.

`geographic_heuristic()` checks every edge against its geographic distance. If
rounding or imported weights make an edge shorter than that distance, it scales
all estimates down by a common factor. This keeps the heuristic a consistent
lower bound and preserves A*'s optimality with the same weights UCS uses. A
zero-cost edge between different geographic positions can reduce the heuristic
to zero; A* then safely behaves like UCS. Missing coordinates or invalid lengths
produce a clear error rather than a misleading result.

UCS and A* return the node path, distance in meters, explored nodes and count,
and measured execution time. The Flask response also includes the selected
algorithm and real route coordinates for Leaflet. A* includes `heuristic_scale`
for inspection. Search timing includes weight validation and, for A*, heuristic
preparation. It excludes road downloads, location snapping, and map drawing.
Fewer explored nodes do not necessarily mean a shorter execution time.

Distance is measured along the chosen graph path. When parallel edges connect
the same nodes, the shortest such edge is used for measurement and drawing.
UCS and A* use that same minimum edge length during the search; BFS and DFS
choose their node path without using weights.
Selected points are connected to suitable nearby graph nodes for calculation;
offset distances are reported, but access between the point and node is not
included in the road distance. Turn restrictions and actual driving safety are
not fully represented by this educational graph.

Run all offline checks (including all four searches, optimal weighted paths,
parallel edges, zero-cost cycles, no-path and same-node cases, malformed
coordinates, heuristic consistency, snapping, caching, and Flask integration):

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

These tests use clearly labeled fixtures; they never insert artificial results
into the application or call a live geocoding service.

`tests/test_weighted_search.py` includes a known graph where the correct
weighted route is **360 meters**, while BFS and DFS discover a **700-meter**
route. It also compares UCS and A* with independently enumerated paths on 30
small directed graphs. No ready-made shortest-path solver is used as an oracle.
For a quick focused check, run:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_weighted_search.py -v
```

To test a zero-length route in the browser, select the same road-junction point
for start and destination and run each algorithm. If both selections snap to
the same suitable node, the distance is zero and one node is explored. For a
missing selection, type a name without choosing a result; the form should ask
you to select coordinates before calculating. Unreachable directed-node pairs
and invalid API coordinates are covered by the automated tests.

## Step 7: complete multi-stop journeys and map view controls

### How the journey is calculated

The form supports up to **20 intermediate stops**. Each field keeps its own
selected coordinates. Blank optional stop rows are ignored; an entered name
must be selected from search results or the map before calculating.

`plan_route()` first connects every selected location to a suitable road node.
It then calls the chosen custom BFS, DFS, UCS, or A* for each consecutive pair:

```text
Start → Stop 1 → Stop 2 → Stop 3 → Destination
  leg 1     leg 2     leg 3          leg 4
```

The same directed road graph and algorithm are used for every leg. Stops are
never optimized or automatically reordered. **Move up** and **Move down** let
you change their order manually without losing names, coordinates, or markers.
Adding, removing, moving, or editing a stop marks the previous successful route
and totals as belonging to previous inputs. Recalculate to replace them together.

Successful node paths are joined with the shared boundary node included once.
Intentional revisits to a node elsewhere in the journey remain in the path.
Consecutive locations at the same snapped node form a valid zero-distance leg.
Road lines use the actual chosen graph edges and their saved geometry; there
are no invented direct connections between selected places.

Results show the journey order, each segment's distance, explored count, and
execution time, plus totals. **Explored Nodes** is the sum of expansions across
leg searches, so a node explored in two legs counts twice. `unique_explored_count`
is also available in the JSON response. Execution time is the sum of measured
search times, including weighted-search setup, and excludes road downloads,
location snapping, geometry assembly, and browser rendering.

If a leg has no path, its number and endpoint labels are identified. Other leg
results remain available for inspection, but the top-level `path` and
`distance_m` are `null` and `geometry` is empty. No partial journey is drawn or
labeled complete. The last successful journey, if any, remains displayed with
a clear notice; the failed request's legs appear under Latest unsuccessful
attempt. Invalid locations are rejected before searches begin.

### Test a journey with three intermediate stops

1. Start Flask using the command above and hard-refresh the browser with
   **Ctrl+Shift+R** after an update.
2. Type **Sadd** in Starting Location and select the **Saddar** suggestion.
3. In Final Destination, enter **Denso Hall**, press **Search**, and select
   the real result. Coordinates and distinct S/D markers should appear.
4. Select **UCS** and calculate once without stops to see a road route.
5. The initial stop row is **Stop 1**. Click **Add Stop** twice for **Stop 2**
   and **Stop 3**. For each row, use **Pick on map**, zoom in, and choose a road
   junction along the displayed journey. Each stop gets its own numbered marker.
   The original route remains for reference while outlined draft markers show
   new selections. You can also choose named places from each field's suggestions.
6. Click **Calculate Complete Route**. There should be **five locations** in
   Journey order and **four segments** in Segment results, plus real totals.
7. Repeat with **BFS**, **DFS**, **UCS**, and **A***. UCS and A* should agree
   on total optimal distance for the same ordered stops and loaded graph. BFS
   and DFS can be much longer. Execution times and explored counts can differ.
8. Use **Move up / Move down** to exchange two stops. Their coordinates should
   stay with their selected locations, labels/markers should renumber, and the
   old route is labeled as previous. Recalculate to follow the new order.
9. Remove a stop with **X**, add another, and try an entered name without
   selecting a suggestion. The latter must be rejected without calculating.
10. Click **Reset**. Fields, road lines, journey/current-location markers, and
    results clear; one blank optional stop and BFS are restored.

For repeatable offline tests of disconnected legs, invalid/outside-coverage
stops, zero/one/three stops, repeated nodes, manual ordering, and totals, run:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_multistop.py -v
```

The real saved Karachi graph was also checked with three intermediate road
junctions using all four algorithms. Those checks reuse cached road data;
synthetic disconnected graphs are used only in tests, never as application data.

### Show Full Route

The original button is above the map. It calls Leaflet `fitBounds` with padding
around the **last successful complete journey's markers and calculated roads**.
Before any success, it fits selected draft markers alone. It never includes the
independent current-location marker. Step 8 also adds a floating **Relocate to
Route** control, which always targets the last successful journey.

To test, manually drag the map elsewhere and zoom in, then press **Show Full
Route**. All journey locations and the full road line should return to view.
Repeat before calculation and after moving/removing a stop. With no selections,
the button shows a helpful message. A late location response cannot undo this
recenter action.

### My Location

Click **My Location** to make one browser `getCurrentPosition()` request. Your
browser asks for permission when needed. On success, a distinct **blue dot**
marks the browser-provided coordinates and centers the map at street zoom.
The message reports coordinates and the device's estimated accuracy.

This does not set the start, a stop, or destination; it does not calculate a
route or send the coordinates to the Flask routing endpoint. No request runs
on page load and there is no continuous tracking. Browser permission already
granted for the site may mean there is no new prompt on the next click.

Test the controls independently:

1. Calculate a journey, then click **My Location** and choose **Allow**. The
   view should move to your reported position while all journey fields and
   calculated results remain unchanged.
2. Click **Show Full Route**. The journey should return to view, regardless of
   where your current-location marker is. Click **My Location** again to center
   on the current position instead.
3. In the browser's site permissions, block Location and click **My Location**.
   A clear permission-denied message should appear. Restore permission to retry.
4. A device/location-service failure shows an unavailable message. A request
   that exceeds its location-acquisition timeout shows a timeout message; the
   app requests a 15-second acquisition timeout and always restores the button.
5. For deterministic browser testing, Chrome DevTools **More tools → Sensors**
   can override the position or choose **Location unavailable**. These are test
   fixtures; turn the override off afterward. Permission and failure states
   were checked in an isolated browser during implementation.

Geolocation needs a secure browser context: use **http://127.0.0.1:5000/** or
**localhost** on this computer, or HTTPS when hosting elsewhere. Opening the
development server through another device's plain HTTP LAN address can block
geolocation. Accuracy depends on the device and can be approximate. See
[MDN's browser geolocation documentation](https://developer.mozilla.org/en-US/docs/Web/API/Geolocation/getCurrentPosition).

## Use and test the map

1. Open the dashboard while connected to the internet. The map should show
   Karachi, Pakistan, with visible **Leaflet** and **OpenStreetMap** attribution.
2. Use **+** and **−** on the map to zoom. Drag the background to explore. On a
   touch device, drag to pan and pinch to zoom.
3. Focus **Starting Location**, click its **Pick on map** button, or choose that
   field in the map's **Select location for** dropdown. The instruction above
   the map identifies the active field. Click or tap the map. An **S**
   marker should appear, the field should contain `latitude, longitude`, and
   labeled coordinates should appear below the input and below the map.
4. Choose **Stop 1** and click another point. It gets a numbered stop marker.
   Choose **Final Destination** to place a **D** marker. Hover over or focus a
   marker to see its label. Clicking a marker selects its associated field.
5. To change a location, select its field and click a different point, or drag
   its existing marker. To remove it, select the field and click **Clear marker**;
   its draft coordinates and input value should clear. The calculated journey's
   snapshot marker remains until a new success or Reset, with a previous-journey
   notice. Other selections are unaffected.
6. Add more stops. They should become available in the map dropdown. Removing a
   stop should remove only its marker and renumber the remaining stop markers.
7. Edit a mapped input by typing. Its draft marker and coordinate hint should
   disappear; an existing calculated journey is labeled as previous. Typing
   alone does not select a coordinate: choose a real Photon suggestion, press
   Search and choose a Nominatim result, or select a map point.
8. Click **Reset**. All fields and markers should clear, one optional stop should
   remain, BFS should be selected, and the map should return to its initial view.
9. Resize the browser between desktop and mobile widths. The map should fit the
   panel, redraw correctly, and retain visible attribution and working controls.
10. For keyboard selection, use **Pick on map** to focus the map, use arrow keys
    to pan, then press **Enter** to select the center. Use **+** / **−** to zoom.

### How the map is organized

- `templates/index.html` loads pinned **Leaflet 1.9.4** CSS and JavaScript from
  the unpkg CDN, followed by the local scripts. Integrity hashes verify the CDN
  files. The map container has an explicit responsive height.
- `static/js/map.js` initializes Leaflet after the page is parsed. It manages
  one marker per selected form field and observes map size changes so Leaflet
  can refresh its layout.
- The tile URL is `https://tile.openstreetmap.org/{z}/{x}/{y}.png`. Tiles are
  requested by the browser as you view the map, using normal browser caching.
  Display tiles are separate from the OSMnx graph. No offline basemap is provided.
- Selections stay in browser memory until reset or page reload. Map picks fill
  coordinate values; Search selections fill the returned place name and retain
  its coordinates. Marker dragging changes a selection to explicit coordinates.
  Reverse geocoding is not implemented.
- If Leaflet cannot load, a message is shown and the route form remains usable.
  Tile download failures also display a message; marker interaction can still
  work when Leaflet itself loaded successfully.

See the official [Leaflet 1.9.4 documentation](https://leafletjs.com/reference-1.9.4.html)
and [OpenStreetMap tile usage policy](https://operations.osmfoundation.org/policies/tiles/)
for the map library and tile service details.

## Step 8: results dashboard, comparisons, and reliable map navigation

### Results and metrics

After a complete success, the dashboard displays the algorithm, total distance
in **km**, explored nodes, execution time in **ms**, selected intermediate-stop
count, and calculated segment count. Zero is displayed as zero; missing values
are unavailable. Travel time is **Not estimated** because no valid road-speed
model is configured. No average speed or travel time is invented.

Segment results identify the actual starting/ending locations, status, distance,
explored nodes, and execution time. Total distance sums edge traversals once per
leg; joining nodes add no distance. Repeated travel along a road in different
legs is real travel and remains included. Explored counts sum independent leg
searches, including repeat expansions across different legs. Search execution
time sums the measured searches and their weight/heuristic preparation; it
excludes geocoding, road downloads, snapping, and browser display time.

The form is an editable **draft**, separate from the displayed successful
journey. Editing locations or the algorithm keeps the last successful map and
metrics together and shows a previous-journey notice. Outlined markers identify
changed draft points; filled S/number/D markers belong to the calculated journey.
Dragging a calculated marker edits a draft point while preserving that previous
calculated journey. **Reset** clears both states and the comparison.

Failed, incomplete, malformed, or outdated responses cannot replace a successful
journey. A failed attempt gets its own labeled section with its location names
and segment failures. Coordinates, response/request identities, leg endpoints,
combined geometry/path, distance totals, explored counts, and timing totals are
checked before committing the new dashboard and map together. Endpoint checks
also detect latitude/longitude reversal. Canceled and late replies are ignored.

### Algorithm comparison and charts

**Compare Algorithms** is a separate action. `POST /api/comparisons` loads one
road graph, snaps the locations once, and passes identical ordered waypoints to
each available manual BFS, DFS, UCS, and A*. `comparison.py` handles this logic;
the existing algorithms are unchanged. Each algorithm calculates all legs.
An unavailable or failing algorithm gets its own status with no substitution.

The comparison table shows actual distance, explored nodes, execution time, and
status. Three responsive, dependency-free bar charts show **distance (km)**,
**explored nodes**, and **execution time (ms)**. Each chart uses its own linear
scale starting at zero. Exact formatted values remain readable beside the bars.
Only complete successful routes get bars; no-path, failed, and unavailable rows
remain in the table without misleading zero-length bars. An all-zero distance
comparison displays zero-width bars, not fabricated positive distances.

Times are from one sequential measured run per algorithm, not benchmark averages
or a universal fastest-algorithm ranking. A* can explore fewer nodes while taking
longer overall because heuristic preparation also costs time. UCS and A* should
agree on optimal distance for the same loaded graph and ordered stops.

Comparison does not change the current route or its metrics. **Show Route** in
a successful row explicitly displays that measured result and selects its
algorithm. If inputs change, the comparison keeps its original journey labels
and becomes **Previous journey**. Its Show Route buttons are disabled until a
comparison for the current inputs is run. Failed comparison requests preserve
the prior table with an explanation.

### Viewport root cause and fitting sequence

The previous code fitted a route once, then only called `invalidateSize()` when
the panel resized. This updates Leaflet's dimensions without changing the zoom
to fit the new viewport. Browser testing reproduced a fully visible desktop
route becoming clipped after resizing to **320 px** width.

The map now stores the latest successful journey's complete road geometry bounds
and selected waypoint positions, independently of draft edits and My Location.
It prepares valid replacement road layers and markers, installs them, and fits
after layout using `requestAnimationFrame`, `invalidateSize()`, and `fitBounds()`.
Padding leaves room for markers and the floating control; maximum zoom is 16.
The resulting bounds are checked. `ResizeObserver` refits when the fitted view's
container changes size. Hidden/zero-size panels wait for usable dimensions
instead of using a long delay. After manual navigation the view stays where you
put it until another success or explicit route relocation.

### Map navigation controls

- **Relocate to Route:** floating above the map, always returns to the latest
  successful complete geometry and all of that journey's markers. It excludes
  draft changes and current location. With no successful route it explains that
  calculation is needed. It still works after panning/zooming far away.
- **Go to Starting Point / Go to Destination:** center the currently selected
  draft start/end at street zoom without changing fields, algorithms, road
  layers, or results. Missing selections produce a helpful message.
- **Show Full Route:** preserves the earlier control; fits a successful journey
  when present, or selected draft markers before any successful calculation.
- **My Location:** retains one-shot browser permission, a separate blue marker,
  and independent centering. It never changes journey coordinates. A late
  location response cannot undo an explicit route/navigation view choice.

### Step-by-step manual verification

1. Run `.\.venv\Scripts\python.exe app.py`, open **http://127.0.0.1:5000/**,
   and press **Ctrl+Shift+R** after updating.
2. Select **Saddar** and **Denso Hall**, choose UCS, and calculate. Check the
   full road route is fitted and all seven dashboard metrics are meaningful.
   Travel time must say Not estimated. Repeat with two nearby road junctions.
3. Add three intermediate stops using suggestions or map junctions. Calculate
   and check five journey locations, four segment results, and matching totals.
   Move stops manually and recalculate to verify the entered order is preserved.
4. Pan far away and zoom in. Press **Relocate to Route** and check the entire
   road line and every calculated marker are visible. Repeat after calculating
   a different journey; relocation must use the new successful result.
5. Use **Go to Starting Point**, **Go to Destination**, then **My Location**.
   Fields, algorithm, route, and metrics must remain intact. Relocate again to
   return to the calculated journey. Try denying location permission as well.
6. Resize to desktop, tablet, and 320/390 px mobile widths after fitting. The
   entire fitted journey must remain visible. Manually navigated views should
   remain under your control. The comparison table scrolls inside its panel.
7. Click **Compare Algorithms**. Check four labeled rows and three charts, with
   matching table/chart values. The selected map route must remain unchanged.
   UCS and A* should agree on distance, while timings can differ between runs.
8. Click **Show Route** on a successful comparison row. Check the dashboard,
   dropdown, road line, and automatic fit now represent that specific result.
9. Edit a location without recalculating. The previous successful route and
   results must remain labeled as previous; the comparison retains its original
   journey and disables Show Route until refreshed.
10. Try a name without selecting a suggestion, remove required coordinates,
    or choose a disconnected road point. Validation or a failed-attempt section
    must explain the problem, preserving any previous successful journey.
11. Select the same suitable road junction for every field. A complete route
    should show **0.000 km**, with zero-width distance bars when compared.
12. Reset: clear fields, layers, both location marker types, metrics, and charts.

Offline comparison checks:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_comparison.py -v
```

The full suite includes **65 tests**. Browser verification covered resizing,
hidden/revealed panels, navigation, comparison display, previous-success state,
reordered/repeated stops, stale replies, malformed/reversed geometry, and
failed/unavailable comparison fixtures. Geolocation uses isolated browser test
coordinates during QA. Actual saved Karachi graphs were also checked for nearby
and distant locations and three-stop journeys, without redownloading roads.

### Current limitations

- Live autocomplete uses Photon; explicit searches use Nominatim. Both public
  services require internet and can be temporarily unavailable or rate-limited.
- BFS, DFS, UCS, and A* calculate complete journeys through stops in your entered
  order. Automatic stop optimization, live traffic, and travel-time estimation
  are not implemented.
- My Location depends on browser permission and device availability, and can be
  approximate. It requires HTTPS or a locally trusted origin such as localhost.
- Leaflet and tiles require internet access and availability of unpkg and
  OpenStreetMap. This project does not provide offline maps.
- Markers show the actual selected points. Routing uses nearest suitable road
  nodes; the selected points themselves are not moved onto the road. Geocoding
  results are location matches, not a guarantee that an address is verified.
- Driving graphs expand automatically to cover selected locations. Connectivity
  still depends on real OpenStreetMap roads. Detailed turn restrictions
  and time-dependent access rules are not fully modeled by this simple graph.
- No path may exist because of road directions or incomplete data. No-path and
  error responses do not display an invented route or distance. Travel time is
  always left unestimated in this step.

## Common setup issues

- **No suggestions or no marker after a project update:** Stop the running
  Flask server with Ctrl+C, start it again, then hard-refresh with Ctrl+Shift+R.
  The older server can retain an outdated page without the necessary scripts.
- **Map point goes into the wrong field:** Focus the intended input or choose
  its name above the map. The active field is shown in the map instructions.
- **OSMnx or NetworkX cannot be imported:** Install the updated requirements into
  `.venv` using the dependency installation command above.
- **Road-network download fails:** Check your connection and try again later if
  the Overpass server is unavailable or rate-limiting. A saved valid graph can
  still be checked and loaded without internet. The browser map uses a separate
  service and can remain usable during an Overpass outage.
- **Road network shows On demand:** Select locations and click Calculate Complete Route. No
  manual area download is required.
- **New locations take longer:** Their roads may not be cached yet. Keep the
  page open while loading; future requests can reuse the saved area.
- **Road network shows Unavailable:** Run `road_network.py check` to see the
  actual error. Fix the JSON configuration or use `prepare --rebuild` to repair
  invalid GraphML. The command exits with a nonzero status when an error occurs.
- **No module named flask:** Run the dependency installation command above,
  then start the app using `.\.venv\Scripts\python.exe app.py`.
- **Cannot find app.py or requirements.txt:** Make sure your terminal is in the
  project folder before running commands.
- **Cannot find .venv\Scripts\python.exe:** Create the virtual environment with
  `python -m venv .venv`, then install the dependencies.
- **Port 5000 is already in use:** Stop any previous copy of the app with
  **Ctrl+C**. Alternatively, run
  `.\.venv\Scripts\python.exe -m flask --app app run --port 5001`
  and open **http://127.0.0.1:5001/**.

For more about virtual environments and installation, see the official
[Flask installation guide](https://flask.palletsprojects.com/en/stable/installation/).
