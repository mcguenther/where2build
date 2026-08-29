# Grundstücks-Check Sachsen — Backend

FastAPI service behind the Vue frontend. It serves data only: every geometry
operation (buffer, rotation, collision check) happens in the browser with
Turf.js. What lives here is the part a browser cannot do — talking to the
authority services, caching their answers, and turning listing and
manufacturer pages into structured, unconfirmed suggestions.

Data sources: ALKIS (parcels), BORIS (land reference values), GeoSN WMS
(orthophoto, topographic map, cadastral map), MOTIS/Transitous (multimodal
routing), and one OpenAI-compatible provider for page extraction.

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
| POST | `/api/parcels/resolve` | Address, coordinate or `gemarkung`+`zaehler`+`nenner` → parcels as GeoJSON (EPSG:4326) plus their union |
| POST | `/api/listings/extract` | `{url}` or `{text}` → listing fields as suggestions |
| POST | `/api/housetypes/extract` | `{url}` → house-type fields as suggestions |
| GET | `/api/landvalue?lat=&lon=` | Land reference value, zone, reference date, source |
| POST | `/api/reachability` | Origin + destinations + modes → duration and route geometry per pair |
| GET | `/api/tiles/{layer}/{z}/{x}/{y}.png` | Cached proxy for the GeoSN WMS (`dop`, `webatlas`, `alkis`) |
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

## Environment variables

All settings have defaults; see `.env.example` for the full list with comments.

| Prefix | Variables | Purpose |
|---|---|---|
| `APP_` | `CORS_ORIGINS`, `CACHE_DIR`, `USER_AGENT`, `PORTAL_USER_AGENT`, `HTTP_TIMEOUT_S` | Process-wide settings. `USER_AGENT` must carry a real contact address — the Transitous usage policy requires it. |
| `ALKIS_` | `WFS_URL`, `VERSION`, `SRID`, `MAX_FEATURES`, `POINT_BUFFER_M`, `CACHE_TTL_S` | ALKIS WFS of the GeoSN |
| `BORIS_` | `WMS_URL`, `LAYER`, `PORTAL_URL`, `CACHE_TTL_S` | BORIS WMS. The URL carries the reference year (`boris_2026`) — check it once a year. |
| `MOTIS_` | `BASE_URL`, `TIMEOUT_S`, `MAX_CONCURRENCY`, `MAX_DIRECT_TIME_S`, `MAX_PRE_TRANSIT_TIME_S`, `CACHE_TTL_S` | Routing and geocoding |
| `TILES_` | `DOP_URL`, `DOP_LAYERS`, `WEBATLAS_URL`, `WEBATLAS_LAYERS`, `ALKIS_URL`, `ALKIS_LAYERS`, `CRS`, `IMAGE_FORMAT`, `TILE_SIZE`, `TRANSPARENT`, `CACHE_TTL_S`, `MAX_ZOOM` | WMS proxy |
| `LLM_` | `BASE_URL`, `API_KEY`, `MODEL`, `FETCH_ENGINE`, `TIMEOUT_S`, `MAX_CONTENT_TOKENS` | Extraction provider. No provider is hard-wired; switching one is a line in `.env`. Without `API_KEY` the extraction endpoints answer 503 and the rest of the API keeps working. |

## Caches

Everything lands under `APP_CACHE_DIR` (default `.cache/`), one subdirectory per
service. Parcel, land-value, tile and routing entries expire after their
`CACHE_TTL_S`; LLM extractions are keyed by normalised URL and kept
indefinitely, because a house type does not change from one week to the next
and every fetch costs money. Deleting the directory is safe.

## Licence and attribution

Official data: © GeoSN, dl-de/by-2-0. Routing via Transitous/MOTIS
(DELFI-GTFS, OpenStreetMap) — link to <https://transitous.org/sources/> in the
UI. Nothing here is legal advice or a building-code assessment.
