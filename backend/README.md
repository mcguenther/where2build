# Grundstücks-Check Sachsen — Backend

FastAPI service behind the Vue frontend. It serves data only: every geometry
operation (buffer, rotation, collision check) happens in the browser with
Turf.js. What lives here is the part a browser cannot do — talking to the
authority services, caching their answers, and turning listing and
manufacturer pages into structured, unconfirmed suggestions.

Data sources: ALKIS (parcels), BORIS (land reference values), GeoSN WMS
(orthophoto, topographic map, cadastral map), OpenFreeMap (vector basemap),
MOTIS/Transitous (multimodal routing), and one OpenAI-compatible provider for
page extraction.

The browser talks to this API and to nothing else. Every authority service,
and the basemap along with them, is proxied here -- that is what makes the app
work in a sealed network and behind a corporate firewall.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"      # or: pip install fastapi uvicorn[standard] pydantic pydantic-settings httpx pyproj shapely pytest pytest-asyncio respx
cp .env.example .env                    # fill in LLM_API_KEY if you want extraction
```

Run every command below from this `backend/` directory.

## Run

```bash
.venv/bin/python -m uvicorn app.main:app --reload --port 8000
```

* API docs: <http://127.0.0.1:8000/docs>
* Health: <http://127.0.0.1:8000/api/health> — reports which services are configured

## Test

```bash
.venv/bin/python -m pytest
```

No test touches the network. External services are stubbed with `respx`
against fixtures in `tests/fixtures/` that follow the response shapes recorded
in `../docs/research/`.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/parcels/resolve` | Address, coordinate, or `gemarkung` + `flurstuecksnummer` (or `zaehler`/`nenner`) → parcels as GeoJSON (EPSG:4326) plus their union |
| POST | `/api/listings/extract` | `{url}` or `{text}` → listing fields as suggestions |
| POST | `/api/housetypes/extract` | `{url}` → house-type fields as suggestions |
| GET | `/api/landvalue?lat=&lon=` | Land reference value, zone, reference date, source |
| POST | `/api/geocode` | Free text → up to 5 coordinate candidates with the labels that were matched |
| POST | `/api/reachability` | Origin + destinations + modes → duration and route geometry per pair |
| GET | `/api/tiles/{layer}/{z}/{x}/{y}.png` | Cached proxy for the GeoSN WMS (`dop`, `webatlas`, `alkis`) |
| GET | `/api/basemap/style.json` | MapLibre style, every URL in it rewritten onto this API |
| GET | `/api/basemap/{path}` | Everything the style then asks for: TileJSON, vector tiles, glyphs, sprites |
| GET | `/api/health` | Which services are configured |

### Notes that matter when using the API

* **A plot is a set of parcels.** `/api/parcels/resolve` always answers with the
  individual parcels *and* their union. The union's `flaeche_amtlich_m2` is the
  sum of the official ALKIS `flaeche` attributes, never the polygon area;
  `flaeche_berechnet_m2` travels alongside for shape analysis only.
* **Extracted values are suggestions.** Every field arrives as
  `{wert, quelle_url, bestaetigt: false}` and needs a human confirmation before
  it should be planned with. Contact details are not extracted at all.
* **Coordinates.** Answers are WGS84; lengths and areas are computed in
  EPSG:25833 before reprojection.
* **Portals.** `immobilienscout24.de` is not requested at all (server-side
  retrieval answers 401) and the API replies with a hint to use the paste
  field. `kleinanzeigen.de` is read from its `og:latitude`/`og:longitude` meta
  tags, which saves both the model call and the geocoding step.
* **Extraction takes two provider calls**, not one: fetching and structuring
  cannot share a request, see `app/services/llm.py`.
* **Errors carry a German sentence in `detail`**, and that sentence says what
  the user can do now -- "Der Katasterdienst … ist derzeit nicht erreichbar.
  Das Flurstück lässt sich auch von Hand eintragen: …". The frontend shows
  `detail` and nothing else, so nothing else may be needed to act. A 422 also
  carries `felder[]` with the machine-readable paths.

## Resolving a parcel by its number

The official geoportal prints one **Flurstücksnummer** per parcel -- `476`,
`85/1`, `41/e` -- while ALKIS stores it in two attributes. Both spellings go in:

```jsonc
{ "gemarkung": "140415", "flurstuecksnummer": "604/2" }   // as printed
{ "gemarkung": "140415", "zaehler": 604, "nenner": "2" }  // as ALKIS stores it
```

`gemarkung` is the district name or its six-digit number; the same parcel
number exists in every district, so it is required. Sending both spellings at
once is a 422, as is a number that does not parse -- with a German message that
shows what a valid one looks like.

**The denominator is text, not a number.** Letter denominators are in regular
use: Gemarkung 140415, number 604 answers with `604/1`, `604/2`, `604/3`,
`604/b` and `604/c` (live, 29.08.2026). `nenner` therefore accepts a string; an
integer is accepted too and normalised.

A number **without** a denominator does not filter on one, so `604` finds all
five of those parcels and unions them. That union is real -- a plot is a set of
parcels -- but here it is an artefact of an incomplete key, so the answer
carries a `hinweis` naming the parcels it found and asking for the full number.


## The basemap proxy

MapLibre would otherwise load its style, tiles, glyphs and sprites straight
from `tiles.openfreemap.org`. That fails wherever the browser has no route to
the internet, so the frontend points at `/api/basemap/style.json` instead:

```js
const KARTENSTIL = "/api/basemap/style.json";
```

What the endpoint does:

* fetches `${BASEMAP_UPSTREAM_URL}/${BASEMAP_STYLE_PATH}` and rewrites every
  absolute upstream URL in the document onto `BASEMAP_PUBLIC_PREFIX` --
  `sources[*].url`, `sources[*].tiles[]`, `glyphs` and `sprite` in both of its
  spellings (a string, or a list of `{id, url}`);
* the same rewrite runs on every JSON answer of the passthrough, because the
  TileJSON behind `sources[*].url` names its tile URLs absolutely too;
* URLs inside prose stay put -- the `attribution` HTML keeps its links to
  openfreemap.org and openstreetmap.org, which is where they belong.

Everything the map then asks for goes through `GET /api/basemap/{path}`, which
hands the upstream's `Content-Type` and `Content-Encoding` on unchanged. Vector
tiles and glyph ranges arrive gzip-compressed and are **not** decompressed on
the way through; the raw byte stream travels with its encoding header, so the
browser does the one decompression there is. Every answer is cached on disk
under `${APP_CACHE_DIR}/basemap` for `BASEMAP_CACHE_TTL_S` (7 days); tile
requests are far too numerous for the cache to be optional.

Only paths below the configured upstream are ever fetched: an absolute target,
a protocol-relative one and any `..` segment are refused with a German 400, so
this is a proxy and not an open redirect.

Live check, 29.08.2026 (`curl` against a local instance):

| Request | Result |
|---|---|
| `/api/basemap/style.json` | 200, valid JSON, 43 kB, **no** `tiles.openfreemap.org` left in it |
| `/api/basemap/planet` | 200, TileJSON, `tiles[]` rewritten to `/api/basemap/planet/…/{z}/{x}/{y}.pbf` |
| `/api/basemap/planet/20260823_080002_pt/14/8798/5484.pbf` | 200, 14 065 bytes, `content-encoding: gzip`, 19 166 bytes decompressed |
| the same tile again | 200, `X-Cache: HIT`, 0.47 s → 0.002 s |
| `/api/basemap/fonts/Noto%20Sans%20Regular/0-255.pbf` | 200, `application/x-protobuf`, gzip |
| `/api/basemap/sprites/ofm_f384/ofm.json` / `.png` / `@2x.png` | 200 (18 kB / 49 kB / 119 kB) |

One thing to know: OpenFreeMap labels vector tiles
`application/vnd.mapbox-vector-tile`, not `application/x-protobuf`. Both are in
use for MVT and MapLibre reads the body either way; the header is passed
through as received rather than rewritten.

## Geocoding: text to coordinate

`POST /api/geocode` turns a typed destination ("Arbeit: Bahnhof Wurzen") into
coordinates for `/api/reachability`.

```jsonc
// Request
{
  "text": "Alte Dorfstraße 12, 04808 Wurzen",
  "lat": 51.36, "lon": 12.73        // optional: rank hits near this point higher
}
```

```jsonc
// Answer (200), at most five candidates, best first
{
  "treffer": [
    { "lat": 51.350145, "lon": 12.7335395, "name": "Alte Dorfstraße 12",
      "beschreibung": "04808 Wurzen, Dehnitz, Sachsen", "art": "adresse" },
    { "lat": 51.333421, "lon": 12.8552319, "name": "Dorfstraße 12",
      "beschreibung": "04808 Wurzen, Kühren-Burkartshain, Sachsen", "art": "adresse" }
  ],
  "hinweis": "Die Koordinaten stammen aus dem Routing-Geocoder …",
  "quelle": "MOTIS / Transitous (DELFI-GTFS, OpenStreetMap)"
}
```

* `art` is `adresse`, `haltestelle`, `ort` or `sonstiges`.
* `beschreibung` carries postcode, municipality, part of the municipality and
  **federal state**. The state is in there on purpose: this geocoder's most
  common failure is answering a Saxon street name with a village in Bavaria,
  and that is only visible if the state is on screen.
* `lat`/`lon` in the request are a bias, not a filter. Live: "Am Kirschberg"
  alone ranks Moosthenning (Bayern) first; with the plot's coordinate it ranks
  "Leipzig, Am Kirschberg" first.
* A missing half of the bias is a 422.

**The geocoder practically never answers "nothing found".** Nonsense input
comes back as five unrelated stops all over Germany with a 200, so the 404 is
rare in practice. Treat `treffer` as candidates to be confirmed, never as a
match -- show the picker, and offer setting the point on the map instead. The
coordinate is not an official Hauskoordinate either way; that is what `hinweis`
says.

Live check against Transitous, 29.08.2026 (cold cache):

| Query | Time | First hit |
|---|---|---|
| `Bahnhof Wurzen` | 0.94 s | Wurzen, Bahnhof (Bus) — 04808 Wurzen, Sachsen |
| `Alte Dorfstraße 12, 04808 Wurzen` | 1.95 s | Alte Dorfstraße 12 — 04808 Wurzen, Dehnitz, Sachsen |
| `Am Kirschberg` | 1.08 s | Am Kirschberg — 84164 Moosthenning, **Bayern** |
| `Am Kirschberg` + bias 51.34/12.37 | 1.07 s | Leipzig, Am Kirschberg — 04209 West, Sachsen |


## Reachability: the exact request and answer

`POST /api/reachability`. Modes are `car`, `bike`, `walk`, `transit` and
`bike_transit` (bike to the first stop, public transport from there). Every
destination is crossed with every mode, so the answer has
`len(destinations) × len(modes)` entries, each keyed by `destination_id` and
`mode`. `time` is the departure time and may be left out, in which case MOTIS
routes from now.

```jsonc
// Request
{
  "origin":       { "lat": 51.2829, "lon": 12.4628 },
  "destinations": [
    { "id": "zentrum", "name": "Leipzig, Innenstadt", "lat": 51.3397, "lon": 12.3731 }
  ],
  "modes": ["car", "bike", "transit", "bike_transit"],
  "time": "2026-08-31T08:00:00+02:00"        // optional
}
```

```jsonc
// Answer (200), one entry per destination × mode
{
  "ergebnisse": [
    {
      "destination_id": "zentrum",
      "mode": "car",
      "erreichbar": true,
      "duration_s": 771,
      "umstiege": 0,
      "startzeit":    "2026-08-29T20:14:00Z",
      "ankunftszeit": "2026-08-29T20:26:00Z",
      "geometry": { "type": "LineString", "coordinates": [[12.46316, 51.2831], "…"] },
      "teilstrecken": [ { "mode": "CAR", "duration_s": 771, "von": "START", "nach": "END" } ],
      "hinweis": null
    },
    {
      "destination_id": "zentrum",
      "mode": "transit",
      "erreichbar": true,
      "duration_s": 2100,
      "umstiege": 1,
      "geometry": { "type": "LineString", "coordinates": [[12.462983, 51.282633], "…"] },
      "teilstrecken": [
        { "mode": "WALK", "duration_s": 180,  "von": "START",                   "nach": "Leipzig, Schwarzes Ross" },
        { "mode": "BUS",  "duration_s": 1080, "von": "Leipzig, Schwarzes Ross", "nach": "Leipzig, Johannisplatz" },
        { "mode": "TRAM", "duration_s": 120,  "von": "Leipzig, Johannisplatz",  "nach": "Leipzig, Augustusplatz" },
        { "mode": "WALK", "duration_s": 540,  "von": "Leipzig, Augustusplatz",  "nach": "END" }
      ]
    }
  ],
  "quelle": "MOTIS / Transitous (DELFI-GTFS, OpenStreetMap)"
}
```

Notes for the caller:

* `geometry` is GeoJSON, so `[lon, lat]` -- the reverse of `origin`/`destinations`.
* A destination with no connection comes back as `erreichbar: false` with
  `duration_s: null` and a German `hinweis`. That is a normal answer, not an
  error: the other pairs in the same call still carry their result.
* `teilstrecken[].mode` is MOTIS' own vocabulary (`WALK`, `BUS`, `TRAM`,
  `CAR`, `BIKE`), upper case and not the same set as the request's `modes`.
* `umstiege` is 0 for direct modes and for a `bike_transit` leg without a
  change.

Live check against Transitous, 29.08.2026, 51.2829/12.4628 → 51.3397/12.3731
(Leipzig-Paunsdorf to the city centre), cold cache, one request per mode:

| Mode | Response time | Travel time | Legs |
|---|---|---|---|
| `car` | 2.72 s | 12.8 min | 1 |
| `bike` | 1.43 s | 41.1 min | 1 |
| `transit` | 1.24 s | 35.0 min | 5 (walk, bus, walk, tram, walk), 1 change |
| `bike_transit` | 1.46 s | 37.0 min | 3 |

All four modes in one request: 6.30 s cold (`MOTIS_MAX_CONCURRENCY=2` keeps the
load on the volunteer instance low), 0.013 s from the cache. The decoded route
geometry lands between 12.371–12.464 E and 51.282–51.340 N, i.e. on Leipzig --
the check that `legGeometry` was read with precision 6.


## Environment variables

All settings have defaults; see `.env.example` for the full list with comments.

| Prefix | Variables | Purpose |
|---|---|---|
| `APP_` | `CORS_ORIGINS`, `CACHE_DIR`, `USER_AGENT`, `PORTAL_USER_AGENT`, `HTTP_TIMEOUT_S` | Process-wide settings. `USER_AGENT` must carry a real contact address — the Transitous usage policy requires it. |
| `ALKIS_` | `WFS_URL`, `VERSION`, `SRID`, `MAX_FEATURES`, `POINT_BUFFER_M`, `CACHE_TTL_S` | ALKIS WFS of the GeoSN |
| `BORIS_` | `WMS_URL`, `LAYER`, `PORTAL_URL`, `CACHE_TTL_S` | BORIS WMS. The URL carries the reference year (`boris_2026`) — check it once a year. |
| `MOTIS_` | `BASE_URL`, `TIMEOUT_S`, `MAX_CONCURRENCY`, `MAX_DIRECT_TIME_S`, `MAX_PRE_TRANSIT_TIME_S`, `CACHE_TTL_S` | Routing and geocoding |
| `TILES_` | `DOP_URL`, `DOP_LAYERS`, `WEBATLAS_URL`, `WEBATLAS_LAYERS`, `ALKIS_URL`, `ALKIS_LAYERS`, `CRS`, `IMAGE_FORMAT`, `TILE_SIZE`, `TRANSPARENT`, `CACHE_TTL_S`, `MAX_ZOOM` | WMS proxy |
| `BASEMAP_` | `UPSTREAM_URL`, `STYLE_PATH`, `PUBLIC_PREFIX`, `REWRITE_HOSTS`, `CACHE_TTL_S`, `TIMEOUT_S` | Vector basemap proxy. Point `UPSTREAM_URL` at your own tile server to drop OpenFreeMap. |
| `LLM_` | `BASE_URL`, `API_KEY`, `MODEL`, `FETCH_ENGINE`, `TIMEOUT_S`, `MAX_CONTENT_TOKENS` | Extraction provider. No provider is hard-wired; switching one is a line in `.env`. Without `API_KEY` the extraction endpoints answer 503 and the rest of the API keeps working. |

## Caches

Everything lands under `APP_CACHE_DIR` (default `.cache/`), one subdirectory per
service. Parcel, land-value, tile, basemap and routing entries expire after
their `CACHE_TTL_S`; LLM extractions are keyed by normalised URL and kept
indefinitely, because a house type does not change from one week to the next
and every fetch costs money. Deleting the directory is safe.

## Licence and attribution

Official data: © GeoSN, dl-de/by-2-0. Routing via Transitous/MOTIS
(DELFI-GTFS, OpenStreetMap) — link to <https://transitous.org/sources/> in the
UI. Basemap via OpenFreeMap and OpenMapTiles from OpenStreetMap data (ODbL);
the attribution must stay visible on the map even though the tiles arrive
through our own proxy. Nothing here is legal advice or a building-code assessment.
