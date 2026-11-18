# Local road-network data

`python road_network.py prepare` creates this directory if needed and saves a
validated `karachi_drive_<area-id>.graphml` file here. The area ID comes from the
configured center, distance, and driving-network model, so changing the selected
area does not overwrite a different area's graph.

Clicking **Calculate Complete Route** or **Compare Algorithms** can also generate
`route_drive_<west>_<south>_<east>_<north>.graphml`.
These files cover the selected start, stops, and destination plus surrounding
roads. Existing covering areas are reused; the optional pilot file is preserved.

`osmnx_cache/` stores OSMnx's downloaded Overpass responses. Reusing GraphML or
these cached responses avoids repeated downloads. Graph files and this cache are
generated locally and excluded from Git.

The geocoding SQLite database also stays local because it contains previous
place-search queries and results. A fresh clone needs only this README in the
data directory; road data and search caches are created automatically when used.
Do not commit downloaded graphs, provider responses, or personal search history.

Source: © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright),
available under the Open Database License (ODbL). This is graph data for a limited
selected area, separate from the Leaflet display tiles. It does not provide an
offline basemap, routing results, traffic information, or automatic updates.
