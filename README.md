# Smart Route Finder

**AI-Based Multi-Stop Route Planning System**

A practical, beginner-friendly route planner built with Python and Flask. Explore
Karachi on an interactive OpenStreetMap map, choose locations, and calculate
journeys through intermediate stops using custom BFS, DFS, UCS, and A* searches.
Compare the actual distances, explored nodes, and execution times of all four
algorithms on the same road graph and ordered journey.

The algorithms are written manually. The application does not call an external
routing API or use NetworkX's built-in shortest-path functions.

## Features

- Responsive navy, white, light grey, and teal dashboard.
- Leaflet map with OpenStreetMap tiles, independent location markers, and actual
  calculated road geometry.
- Live place suggestions through Photon, with explicit Nominatim searches.
  Public Nominatim is never used for search-as-you-type.
- Add, remove, and manually move intermediate stops while retaining coordinates.
  Stops are visited in the entered order; there is no automatic reordering.
- Real, directed driving networks from OpenStreetMap through OSMnx. Covering
  GraphML files are loaded locally or downloaded and cached on demand.
- Manual BFS, DFS, UCS, and A* route calculations for every journey segment.
- Results dashboard with algorithm, distance, explored nodes, execution time,
  stop count, segment count, and individual segment results.
- Explicit algorithm comparison with a measured table and three bar charts.
- Automatic full-route fitting, floating Relocate to Route, endpoint navigation,
  and a separate, one-shot My Location control.
- Previous successful routes remain clearly labeled when inputs change or a new
  calculation fails. Stale replies and invalid route responses are rejected.
- Offline unit and integration tests, plus GitHub Actions test automation.

## Technologies

| Layer | Technologies |
| --- | --- |
| Backend | Python, Flask |
| Road graph | OSMnx, NetworkX directed multigraphs |
| Location search | Photon, Nominatim, Requests, local SQLite cache |
| Map | Leaflet 1.9.4, OpenStreetMap tiles |
| Interface | HTML/Jinja templates, CSS, vanilla JavaScript |
| Testing | Python unittest, GitHub Actions |

No Node.js build, paid map API, or API key is required for local use.

## Project structure

```text
smart-route-finder/
├── app.py                    # Flask homepage and JSON APIs
├── routing.py                # Custom searches, snapping, ordered journeys
├── comparison.py             # Compare searches on shared graph/waypoints
├── road_network.py           # Download, validate, save, load road graphs
├── road_network_config.json  # Pilot area and automatic coverage settings
├── geocoding.py              # Provider requests, caching, request limits
├── requirements.txt          # Python application dependencies
├── templates/index.html      # Dashboard rendered by Flask
├── static/
│   ├── css/style.css
│   └── js/                   # Form, locations, map, search, results, comparison
├── data/README.md            # Instructions; generated data stays local
├── tests/                    # Offline algorithm and Flask regression tests
├── docs/DEVELOPMENT.md        # Detailed setup, implementation and testing guide
├── .github/workflows/tests.yml
├── .gitattributes
├── .gitignore
└── README.md
```

## Install and run locally

Install Git and Python first. Python **3.12** is the version selected for CI and
the recommended starting point for a new hosting environment. An internet
connection is needed for dependency installation, map assets, place searches,
and the initial road-data download for an area.

Clone the repository:

```bash
git clone https://github.com/codewithtahafaisal/smart-route-finder.git
cd smart-route-finder
```

### Windows PowerShell

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Activation is optional; the commands above use the virtual environment directly.

### macOS or Linux

```bash
python3 --version
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py
```

Open **http://127.0.0.1:5000/** and keep the terminal running. Press **Ctrl+C** to
stop. After updating project files, hard-refresh the browser with **Ctrl+Shift+R**.
The included Flask development server is for local development.

### Plan a journey

1. Select a Starting Location and Final Destination from suggestions or the map.
2. Add optional intermediate stops. Choose a real suggestion or map point for
   every entered field; typed text alone does not select coordinates.
3. Choose BFS, DFS, UCS, or A* and click **Calculate Complete Route**.
4. The app reuses covering road data or downloads and saves the required area.
   The first request for an uncached area may take a few minutes.
5. Inspect the full route, totals, and segment results. Use **Compare Algorithms**
   to measure the same journey with all algorithms; **Show Route** explicitly
   displays a chosen comparison result.

**Relocate to Route** always uses the last successful complete journey. Endpoint
buttons use the currently selected start or destination. **My Location** asks
the browser for a position only when clicked; its separate marker never changes
the journey. Browser permission and localhost or HTTPS are required.

## How the algorithms work

| Algorithm | Implementation | What it guarantees |
| --- | --- | --- |
| BFS | FIFO queue | Fewest road edges; not necessarily shortest distance |
| DFS | LIFO stack | A discovered path; no shortest-route guarantee |
| UCS | heapq priority queue, accumulated edge length | Minimum distance with nonnegative road lengths |
| A* | heapq, g-score plus geographic heuristic | Minimum distance with the consistent lower bound used here |

Road edges are directed and weighted by length in **meters**. UCS and A* use the
same weights and minimum-length parallel edges. A* estimates remaining distance
with the Haversine formula and scales the estimate down when necessary to keep
it a valid lower bound. Every leg runs independently in the specified order.
Paths are joined without duplicating connecting nodes, and leg distances are
summed once. Optimality is within the loaded road graph.

Explored-node totals count expansions across leg searches, so a node explored in
two different legs counts twice. Timing measures searches and their setup,
excluding road downloads, geocoding, snapping, and browser rendering. Charts
show one measured run, not a universal fastest-algorithm ranking. Failed and
unavailable routes do not get misleading zero-value bars.

Travel time is **Not estimated** because no road-speed model is configured.
There is no live traffic, automatic stop optimization, or turn-by-turn navigation.

## Road data and configuration

Edit `road_network_config.json` to configure the optional Karachi pilot area,
automatic route buffer, maximum requested area, Overpass endpoint, and timeout.
Normal route requests and comparisons prepare their coverage automatically.

The optional pilot can be downloaded or checked explicitly:

```powershell
.\.venv\Scripts\python.exe road_network.py prepare
.\.venv\Scripts\python.exe road_network.py check
```

On macOS/Linux, use `.venv/bin/python` instead. Generated GraphML, Overpass
responses, and the geocoding SQLite database are intentionally **not** included
in Git. They are regenerated locally; your existing local data is not deleted.
See [data documentation](data/README.md) for storage and attribution.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Or on macOS/Linux:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

The offline suite covers known-cost graphs, all four searches, no-path and
same-node cases, multiple stops, graph persistence, search policies, request
validation, and shared-input algorithm comparison. It does not download live
road graphs or call public geocoding services. GitHub Actions runs the tests on
pushes and pull requests to `main`.

See the [detailed development guide](docs/DEVELOPMENT.md) for manual frontend,
map, permission, routing, comparison, and responsive-layout checks.

## Deployment

**Publishing this repository does not deploy a running Flask application.**

### GitHub Pages compatibility

GitHub Pages hosts static files; it cannot run this Flask/Python application.
The frontend is a Flask-rendered Jinja template and depends on these backend APIs:

- `POST /api/locations/search`: geocoding, caching, request limits.
- `POST /api/routes`: graph loading, snapping, custom route searches.
- `POST /api/comparisons`: shared-graph algorithm comparison.

Copying `templates/` or `static/` to Pages would not provide a working route
planner. No Pages deployment workflow is supplied, and there is no Pages app URL.
The GitHub Actions workflow runs **tests**, not a website deployment.

### Full Flask hosting option: Render

[Render's Flask guide](https://render.com/docs/deploy-flask) supports hosting the
backend and frontend together, preserving their current same-origin API paths.
Create a Python Web Service connected to this repository and its `main` branch.
Use Python 3.12 and these Linux hosting commands:

```bash
# Build command: installs the app plus a production WSGI server on the host.
pip install -r requirements.txt gunicorn

# Start command: PORT is provided by the hosting service.
gunicorn --workers 1 --threads 2 --timeout 300 --bind 0.0.0.0:$PORT app:app
```

Gunicorn is an optional hosting dependency, not needed for Windows local use.
Start with one worker to avoid duplicating large in-memory road graphs. Choose
enough memory for OSMnx and the selected road area, and configure persistent
storage for `data/` if supported by the hosting plan. Ephemeral storage can lose
saved graphs after redeployment. Initial downloads and large comparisons can
also exceed a host's request limits; test a small area first.

No Render service or other backend deployment is created by these instructions.
The full application needs a separately configured Python host before it has a
public application URL.

## Attribution and external services

Map and road data: © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright),
with road data under ODbL. Map rendering uses [Leaflet](https://leafletjs.com/).
Live suggestions use [Photon](https://github.com/komoot/photon); explicit searches
use [Nominatim](https://nominatim.org/). Public services require internet access
and may be unavailable or rate-limited. Public Nominatim's
[usage policy](https://operations.osmfoundation.org/policies/nominatim/) prohibits
autocomplete, which is why the default typing provider is Photon.

Keep `.env` files, credentials, virtual environments, generated data, and search
history out of commits. `.gitignore` excludes these local files by default.
