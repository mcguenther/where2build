# where2build

Plot appraisal for Saxony. Paste a listing, get the official cadastral parcels
behind it, measure them, hold the asking price against the official land value,
place a prefabricated house inside the setback envelope, and see how long it
takes to get to work, school and the station.

> Interface language is German throughout; source code, comments and this file
> are English. See [`CLAUDE.md`](CLAUDE.md) for the rule and
> [`DESIGN.md`](DESIGN.md) for the visual system.

> **How this was built.** Spec-driven development with Claude. The requirements
> were written first — as a pre-project note and then a clickable mock that was
> reviewed and approved before any application code existed — and the
> implementation was carried out by [Claude](https://claude.ai/code) working
> against that specification, under review at every step. `CLAUDE.md` is the
> working agreement that fell out of it: the decisions that are settled, the
> traps that already cost time, and what has to be true before a change counts
> as done. Statements in this repository about an external service are there
> because a request was made and its answer read, not because a model believed
> them.

![Plot page](docs/screenshots/grundstueck-hell.png)

## What it does

| | |
|---|---|
| **Take a plot in** | From a listing URL, from a pasted page, or straight from *Gemarkung* + parcel numbers. A four-step wizard shows what the model read, where each value came from, and what it could not find. |
| **Resolve the parcels** | ALKIS gives the outline, the official area and the parcel identifier. A plot is a *set* of parcels — the normal case, not the exception — so geometries are unioned and official areas summed. |
| **Judge the shape** | Rectangularity as polygon area over the area of its smallest rotated bounding rectangle, plus street frontage and vertex count. |
| **Judge the price** | €/m² against the BORIS land value for the zone, as a percentage rather than a hunch. |
| **Draw the setbacks** | The strip that may *not* be built on is the part that gets colour. Depth is adjustable **per boundary segment**, because § 6 SächsBO measures from wall height and treats 3 m as a floor. |
| **Place a house** | From the catalogue or from dimensions you type yourself. Drag it, rotate it, or align it to the street front in one click; corners leaving the envelope are flagged. |
| **Check reachability** | Car, bike, transit and the best combination to each saved destination, via MOTIS. |
| **Compare and print** | Several candidates side by side at one scale. There is no separate print view — the page on screen is the page that prints. |

## Running it

Requires Node 22+ and Python 3.11+.

On Windows, use PowerShell paths and the Python launcher:

```powershell
# Backend — FastAPI, proxy and cache in front of the official services
py -m venv backend\.venv
backend\.venv\Scripts\python -m pip install -e "backend[dev]"
Copy-Item backend\.env.example backend\.env    # then fill in LLM_API_KEY
backend\.venv\Scripts\python -m uvicorn app.main:app --reload --app-dir backend

# Frontend — Vite + Vue 3, Options API
Set-Location frontend
npm install
npm run dev                                    # proxies /api to 127.0.0.1:8000
```

If venv creation was interrupted and `backend\.venv` only contains a partial
environment, remove it first with `Remove-Item -Recurse -Force backend\.venv`.

On Linux and macOS:

```bash
# Backend — FastAPI, proxy and cache in front of the official services
python3 -m venv backend/.venv
backend/.venv/bin/pip install -e "backend[dev]"
cp backend/.env.example backend/.env          # then fill in LLM_API_KEY
backend/.venv/bin/python -m uvicorn app.main:app --reload --app-dir backend

# Frontend — Vite + Vue 3, Options API
cd frontend
npm install
npm run dev                                   # proxies /api to 127.0.0.1:8000
```

The frontend runs without the backend: extraction falls back to a worked
example and says so on screen, naming the reason. Everything the user enters
lives in `localStorage`; **Daten** exports and imports it as JSON.

## Tests

```bash
backend/.venv/bin/python -m pytest backend/tests -q   # 315 tests
cd frontend && npm run test                           # 214 tests
cd frontend && npm run test:integration               # 10, against a running backend
node scripts/screenshots.mjs                          # 37 images and a print PDF
```

The backend suite touches no network: ALKIS, BORIS, MOTIS, OpenFreeMap and the
model are stubbed with `respx` against fixtures whose shapes come from the
research in [`docs/research/`](docs/research/).

The frontend suite mounts the real components against **recorded real service
responses** in `frontend/tests/fixtures/`: two parcels (one convex, one
markedly concave), the ELK house-type sheet, and a MOTIS answer for
Liebertwolkwitz → Leipzig Hbf and → the local primary school. Nothing in a
test is a number someone chose to make an assertion pass. `test:integration`
is the same questions asked of a backend that is actually running.

`scripts/screenshots.mjs` writes to `docs/screenshots/`. It builds its state
through the real add flow — ALKIS, Liebertwolkwitz 85/1 — and fails on a
console error, on horizontal overflow, and if not a single vector tile
arrived. Look at the images: tests do not catch a collapsed layout.

## Layout

```
backend/          FastAPI. Proxy, cache and schema validation. Owns no geometry.
  app/services/   alkis, boris, llm, motis, tiles
  app/routers/    one per endpoint group
frontend/
  src/lib/        geometry, projection, routes, store, api, formatting
  src/components/ SitePlan (the drawing), PlotCard, RouteCards
  src/views/      Plots, Plot, Wizard, Compare, HouseTypes, Destinations, Data
  src/styles/     tokens, base, print
docs/             Spec, service research, screenshots
mockup/           The approved UI mock. Reference, not built.
```

**All geometry runs in the browser.** Buffering, rotation and collision happen
while the user drags, with no round trip; the binding numbers come from ALKIS
anyway. The backend owns network access, caching and schema validation, and
nothing else.

## Endpoints

| Method | Path | |
|---|---|---|
| `POST` | `/api/parcels/resolve` | address, coordinate or *Gemarkung* + numerator/denominator → GeoJSON in EPSG:4326 with the official area |
| `POST` | `/api/listings/extract` | `{url}` or `{text}` → listing fields, each with its source |
| `POST` | `/api/housetypes/extract` | `{url}` → house type, fetch restricted to the manufacturer's domain |
| `GET` | `/api/landvalue` | `?lat=&lon=` → €/m², zone, reference date |
| `POST` | `/api/reachability` | origin + destinations + modes → durations and route geometry |
| `GET` | `/api/tiles/{layer}/{z}/{x}/{y}.png` | cached proxy for the GeoSN WMS layers |
| `POST` | `/api/nearby` | one coordinate → the nearest school, park, tram stop and so on, ranked by walking time; `linien: true` also names the lines calling at each stop |
| `GET` | `/api/health` | which services are configured |

## Configuration

`backend/.env`, all optional except the model key:

```
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_API_KEY=sk-or-v1-...
LLM_MODEL=anthropic/claude-sonnet-4.6
LLM_FETCH_ENGINE=openrouter        # openrouter | exa | parallel | native
APP_USER_AGENT=where2build/0.1 (contact@example.org)
```

No provider is wired in. The client is OpenAI-compatible, so switching is a
change to `LLM_BASE_URL` and nothing else. `APP_USER_AGENT` must carry a real
contact address before any real use of Transitous.

## Things that already cost time

Each of these is verified, not assumed — the details are in
[`docs/research/`](docs/research/).

- **`response_format: json_schema, strict: true` is not honoured while
  `tools: [web_fetch]` is active in the same call.** Reproduced across three
  models. Extraction is therefore two calls: fetch, then structure.
- **MOTIS is `/api/v6/plan`**, not `v1`, and `legGeometry` uses **precision 6**.
  Decoding at precision 5 puts the route a factor of ten away.
- **BORIS `INFO_FORMAT=application/json` returns UTFGrid**, not GeoJSON, and
  fails outright on the combined layer. Use `text/plain` or GML.
- **immobilienscout24.de answers server-side fetches with 401** on every route
  tested, so its adapter goes straight to the paste field.
- **kleinanzeigen.de carries `og:latitude`/`og:longitude`** in its meta tags —
  parse those and skip both the geocoder and the model call.
- **ALKIS stored queries need the `CRS` parameter**; without it the service
  answers HTTP 400 with a generic HTML page rather than an OGC error. Ad-hoc
  `fes:Filter` expressions need the `ave:` namespace prefix.
- **Use the official area** for anything price-related. The area computed from
  the polygon differs by a few square metres; both are shown side by side.
- **MapLibre's worker must be pointed at explicitly.** It resolves
  `./maplibre-gl-worker.mjs` next to its own module, which after bundling is
  the app chunk — a file the bundler never emits. The request 404s, vector
  tiles are never parsed, and the map stays blank **without one error
  anywhere**, while raster layers keep working. `frontend/src/main.js` imports
  the worker with `?worker&url` and calls `setWorkerUrl`.
- **MapLibre rejects a relative `sprite` URL** while accepting relative glyph
  and tile URLs, and it does not resolve the relative `tiles[]` inside a
  TileJSON against the source URL. The proxy answers relative — only the
  browser knows which origin it reached the API on — and the frontend expands
  them and inlines the TileJSON.
- **Never show example data.** There is no sample state and no fallback. A
  derived figure whose input is missing stays a dash; computing it anyway is
  where "0,00 €" and "−100 % under the land value" came from.

## Not done yet

- **No persistence on the server.** Plots live in the browser. PostGIS and the
  ALKIS/Hauskoordinaten import (step 1 of the plan) are still open, so address
  lookup currently borrows the MOTIS geocoder and says so in its response.
- **The basemap cache has no size limit.** Vector tiles are up to ~1 MB and the
  TTL is seven days; real traffic would need a sweeper.
- **The vector style is a light one, in dark mode too.**

## Attribution

Official data © Staatsbetrieb Geobasisinformation und Vermessung Sachsen
(GeoSN), [Datenlizenz Deutschland – Namensnennung 2.0](https://www.govdata.de/dl-de/by-2-0).
Land values from the responsible *Gutachterausschuss*. Timetable data from
DELFI via [opendata-oepnv.de](https://www.opendata-oepnv.de/), road network
from OpenStreetMap contributors.

**This is not a building-law assessment and not legal advice.** Setback depth
under § 6 SächsBO follows wall height, party-wall garages are privileged, and a
development plan can set different building lines. Under § 15 (2) ImmoWertV an
individual plot inside a land-value zone may have a different permitted use, in
which case the zone value does not apply to it.
