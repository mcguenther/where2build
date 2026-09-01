# where2build — working notes for Claude

Plot-appraisal tool for Saxony: resolve a listing to its official cadastral
parcels, measure them, compare the asking price against the official land value,
place a prefabricated house inside the setback envelope, and route to everyday
destinations.

## Language rules — these are strict

- **Source code is English.** Comments, docstrings, identifiers, commit
  messages, `README.md`, this file.
- **The user interface is German.** Every string a user reads: labels, buttons,
  headings, error messages, chart captions, `DESIGN.md`.

A German identifier in the code or an English label in the UI is a bug. This is
strict: variables, parameters, functions, methods, computed properties, props,
constants and comments are English, always, including local variables nobody
else will read.

Two things are **data**, not identifiers, and stay German:

- **The field names of the API and of the stored document** — `gemarkung`,
  `flaeche_amtlich_m2`, `bodenrichtwert`, `flurstuecksnummer`. They mirror the
  German authorities' own schemas and are the wire format. Read them with an
  English variable name: `const officialArea = props.flaeche_amtlich_m2;`.
- **CSS class names** — `lageplan`, `tafel`, `nicht-drucken`, `weg-karte`. An
  established vocabulary shared with the stylesheets; renaming buys nothing.

Keep comments sparse and about *why*, not *what*.

## Layout

```
backend/     FastAPI + PostGIS. Proxy and cache in front of ALKIS, BORIS,
             GeoSN WMS, MOTIS and the LLM. Owns no geometry maths.
frontend/    Vite + Vue 3, Options API. Owns ALL geometry.
docs/        Spec, service research, screenshots.
mockup/      The approved UI mock. Historical reference, not built.
```

## Decisions that are settled — do not relitigate

These come from the pre-project note (`docs/vorprojekt-anforderungen.html`) and
from the user directly. Reopen only if the user asks.

- **Vue 3 with the Options API.** No `<script setup>`, no Composition API
  rewrite, no Nuxt.
- **Geometry runs in the browser**, not in Shapely. Buffering, rotation and
  collision run while the user drags, without a round trip. The binding numbers
  come from ALKIS anyway.
- **Use the official area** (`flaeche` attribute from ALKIS) for anything
  price-related. The area computed from the polygon differs by a few square
  metres and is for shape analysis only. Both are shown side by side.
- **A plot is a *set* of parcels.** Not the exception — the normal case.
  Union the polygons, sum the official areas.
- **No contact details are stored.** The extraction schema does not carry
  agent names or phone numbers, so no personal data reaches the database.
- **Fonts come from npm (Fontsource)**, never from a CDN.
- **No separate print view.** `print.css` restyles the live page.
- **There is no "6 m between buildings" rule in Saxony.** § 6 Abs. 5 SächsBO
  gives 0,4 H with a 3 m floor, Abs. 2 puts that area on one's own plot, Abs. 3
  forbids setback areas overlapping — so 6 m is the arithmetic of two minimal
  cases, not a norm, and a neighbour standing too close does **not** enlarge our
  setback. The hatched strip in the plan therefore says where the two areas
  would overlap and that this is a question for the Bauaufsicht; it must never
  be worded as an obligation. OSM has the outlines but almost no wall heights
  (11 of 59 around Mölkau 204 carry `building:levels`, none carries `height`),
  so only the 3 m floor is computable.
  See `docs/research/abstandsflaechen-nachbargebaeude.md`.
- Region is Saxony only; ALKIS and BORIS are state-specific.
- **Never show example data.** There is no sample state and no fallback: when a
  service fails, the German `detail` from the backend is shown instead. Tests
  run on recorded real responses in `frontend/tests/fixtures/`, not on invented
  numbers. A derived figure with a missing input stays `—`; it is never
  computed from `null` (that is where "0,00 €" and "−100 %" came from).

## Working rules

- **Keep the pull request description current.** After every push, the PR body
  must describe what is actually on the branch. A description that still talks
  about the previous step is worse than none.
- **Verify, do not relay.** Statements about an external service belong in the
  repo only after a request has been made and its answer read. `HEAD` is not a
  substitute for `GET` — several of these services answer 404 to a HEAD they
  serve happily on GET.

## Traps that already cost time

- **`response_format: json_schema, strict: true` is not honoured while
  `tools: [web_fetch]` is active in the same call.** Verified across three
  models. Extraction is therefore two calls: fetch, then structure. See
  `docs/research/openrouter.md`.
- **MOTIS is `/api/v6/plan`**, not `v1`, and `legGeometry` uses **precision 6**.
  Decoding with precision 5 puts the route a factor of ten away.
- **BORIS `INFO_FORMAT=application/json` returns UTFGrid**, not GeoJSON, and
  fails outright on the combined layer. Use `text/plain` or GML.
- **immobilienscout24.de answers server-side fetches with 401** on every route
  tested. Its adapter goes straight to the paste field.
- **kleinanzeigen.de carries `og:latitude`/`og:longitude`** in its meta tags —
  parse those instead of geocoding, and skip the model call entirely.
- **The authority services DO send CORS headers** — checked with `GET` and an
  `Origin` header on 2026-08-29: the ALKIS WFS, the GeoSN WMS layers and the
  BORIS WMS all answer with `Access-Control-Allow-Origin`. The pre-project note
  says otherwise. The proxy still earns its place — disk cache, one contract,
  no key in the browser — but not for the reason stated there.
- **MapLibre's worker must be pointed at explicitly.** It resolves
  `./maplibre-gl-worker.mjs` next to its own module, which after bundling is
  the app chunk — a file Vite never emits. The request 404s, vector tiles are
  never parsed, and the map stays blank **without one error anywhere**. Raster
  layers keep working, which makes it look like a style problem.
  `main.js` imports the worker with `?worker&url` and calls `setWorkerUrl`.
- **MapLibre rejects a relative `sprite` URL** ("must be absolute") but accepts
  relative glyph and tile URLs. It also does not resolve the relative `tiles[]`
  inside a TileJSON against the source URL. The proxy therefore answers with
  relative URLs — only the browser knows the origin it reached the API on —
  and `SitePlan.vektorStil()` expands them and inlines the TileJSON.
- **One failed sprite or tile must not tear the map down.** MapLibre's `error`
  event fires for missing icons; treating it as fatal removed the container and
  made the backdrop look permanently unavailable.
- **A backdrop is a MapLibre instance.** `SitePlan`'s `grund` defaults to
  `"ohne"` so the thumbnails on cards and in the comparison do not each start
  one — and so mounting in jsdom does not reach for the network.
- Setback depth is **per boundary segment**, not one global value. § 6 SächsBO
  measures it from wall height; 3 m is the floor, not the rule.
- **Scoped component styles outrank `print.css`.** A `<style scoped>` selector
  carries a `[data-v-…]` attribute, so a bare class in the print stylesheet
  loses to it and the print layout silently never applies. Every layout rule in
  `print.css` therefore carries `!important`.
- **`100vh` costs a sheet.** The shell is a `100vh` flex column; on paper that
  is exactly one page, and the footer gets pushed onto a page of its own.
- **Both dark-palette routes outrank a bare `:root` in the print block**
  (`:root[data-theme="dark"]` and the guarded media query are both specificity
  0,2,0). Printing from dark mode gave an invisible boundary line and a black
  halo round every stroke until the print block was made to win.
- **MapLibre zoom is defined against 512-pixel tiles.** The widely quoted
  156543.034 metres-per-pixel constant assumes 256, and putting it in the
  camera renders the basemap at exactly twice the drawing's scale.
- **A Vue prop is a reactive proxy, and a proxy charges per property read.**
  The clearance field reads two numbers per grid cell per boundary segment —
  hundreds of millions on a real parcel — and measured **23.5x slower** through
  a proxy than on plain objects: 26 seconds against one. `buildableArea` and
  `findPlacement` copy their input once at the door. Any new hot loop over
  geometry must do the same; the symptom is a frozen tab with no error.
- **Cap the grid, do not fix the step.** A district address resolves to a field:
  its axis-aligned box is 1583 x 198 m with 159 boundary points, which is two
  million cells at 0.4 m. The step now grows to hold the cell count, which stays
  safe because the inward bias is derived from the step — a coarser grid gives a
  smaller envelope, never a more permissive one.
  Use the **minimum rotated rectangle**, not the bounding box, to describe a
  shape: that same parcel is a 1594 x 30 m ribbon running diagonally, and the
  axis-aligned box hides exactly the elongation you are looking for.
- **`ave:KatasterBezirk` will not drop its geometry.** `PROPERTYNAME` without the
  `ave:` prefix is rejected outright (`ErrorInPropertyName`); with the prefix the
  request is accepted and the outline comes back anyway — about 5 kB per
  district, 28 MB for all 5 339. So the district list is *built once* by
  `backend/scripts/build_gemarkung_index.py` into a committed 490 kB file and
  served from there; `GET /api/gemarkungen` never touches the WFS.
- **The Geoportal shows the Gemarkungsschlüssel two ways.** The 'Flurstueck'
  layer prints the four-digit form (`3044`), the 'Gemarkung' layer the
  six-digit one (`143044`). Both resolve, and the name (`Moritzburg`) as well.
  Checked against all **5 339** Saxon Gemarkungen pulled from
  `ave:KatasterBezirk`: every key is six digits, every one starts with `14`,
  and all four-digit tails are distinct — so the short form expands uniquely.
  183 districts have a leading zero (`0101`), which a spreadsheet eats, and no
  valid number is below `0101`; padding a one-to-three-digit input can therefore
  only turn a dead input into the right one.
- **`one-to-many` is a POST.** On a GET, repeated `many=` parameters are
  silently collapsed — three destinations came back as one duration, and
  reordering the same three turned it into a missing-parameter error. A GET
  with a *single* destination looks like it works, which is how this survived
  a check. `maxMatchingDistance` is required in the body, not optional. The
  matrix takes 128 destinations and refuses the 129th.
- **No OSM tag identifies an S-Bahn stop in Saxony** (`service=suburban`: zero
  objects), and `school:DE` does not exist there either. So transit stops come
  from MOTIS, whose modes are derived from the actual timetable, and the school
  type is only derivable from the name string.
- **`REGIONAL_RAIL` is not a synonym for S-Bahn, and MOTIS does emit
  `SUBURBAN`.** Checked against the Leipzig city tunnel: Leipzig Markt,
  Wilhelm-Leuschner-Platz and Bayerischer Bahnhof all come back as
  `["REGIONAL_RAIL", "SUBURBAN"]` — a real S-Bahn stop carries *both*. And
  Leipzig-Liebertwolkwitz is `["REGIONAL_RAIL", "BUS"]` because the line that
  stops there is RB113 to Geithain, a Regionalbahn. Do not map REGIONAL_RAIL to
  S-Bahn; check the timetable at `/api/v6/stoptimes?stopId=…` when in doubt.
- **Overpass: read the policy for what it says, not for a verdict.** The manual
  lists "setting up an app for more than just OSM mappers and **relying on the
  public instances as backend**" under problematic behaviour, and puts the
  guideline at ~10 000 requests and 1 GB per day. The same page says occasional
  manual requests are fine. So a single-user prototype querying it now and then
  is within the guideline; *a deployed product* on a shared server IP is what
  the policy objects to. The endpoint therefore takes Overpass as a configurable
  source, and a self-hosted instance or the local extract
  (`backend/scripts/build_poi_index.py`) is the production answer — not because
  Overpass is forbidden, but because it does not carry someone else's product.
- **The feeder to the first stop is chosen, not assumed.** Foot and bike are
  both asked for; the bike wins if it is faster *and* either the walk to the
  first stop is ≥ 10 min or the whole journey gets ≥ 10 min shorter. The car is
  only asked once the bike feeder itself is ≥ 10 min, and never taken when it is
  slower — driving to a station and parking all day is not worth three minutes.
  A destination can pin the choice (`zubringer`); absent means automatic. The
  chosen variant is the mode the card names, and `hinweis` carries the numbers,
  so a substituted mode is never silent.
- **Rank by walking time, never air distance.** Detour ratios reach 2.88x, and
  the nearest thing by air can be unwalkable altogether.
- **An address is not a plot.** A district address ("Plaußig-Portitz, 04349
  Leipzig") geocodes to a point in a field, and the parcel under it is not the
  one in the listing. `/api/parcels/resolve` takes `expected_area_m2` and
  answers with a `plausibility` block; MOTIS's `type: PLACE` versus `ADDRESS`
  is the sharpest of the three signals, and works even with no listing area.
- **Real parcels are frequently concave.** Half-plane clipping is only a correct
  inward offset for convex rings; on an L-shaped plot it returns an empty
  envelope. `buildableArea` falls back to a grid contour, biased inward so an
  approximation is never more permissive than the law.
- **A failure flag must never be an input to the watcher that retries.**
  `SitePlan.hasBackdrop` contained `!mapUnavailable`, and its watcher rebuilt
  the map; the rebuild cleared the flag, which changed `hasBackdrop`, which
  fired the watcher. A basemap that would not load therefore re-fetched the
  style forever. Nothing was visible — the drawing looked right. And the loop
  is pure microtasks, so it starves every timer: no browser watchdog and no
  test timeout can end it, which is why the frontend suite took twenty minutes
  and reported a killed worker rather than a failure. What a thing *should be*
  is now separate from whether it *is*, and only the former drives a rebuild.
- **MapLibre never fires `idle` while a tile is still failing.** A 502 on one
  vector tile keeps `areTilesLoaded()` false indefinitely, so anything that
  waits for `idle` before photographing a map needs a bounded fallback that
  reports the incomplete render instead of hanging the whole run.
- **`node scripts/screenshots.mjs` serves `frontend/dist`, not the dev server.**
  Run `npm run build` first or the pictures show the previous code.
  Its Playwright import is an absolute sandbox path (`/opt/node22/...`), so the
  script only runs where that path exists — on a plain machine it fails before
  the first picture.
- **A dead upstream connection pool survives a container restart.** After the
  sandbox restarted, the running backend answered 502 for every Transitous call
  while the same request from `curl` returned 200. Restarting uvicorn fixed it;
  do not go looking for the bug in the code first.
- **The sandbox browser has no route to the internet**, only the shell has.
  Basemap tiles therefore cannot be verified by screenshot here; the camera
  maths is covered by `tests/projection.test.js` instead. Tiles that come
  through *our own* backend are a different matter — the browser reaches those,
  so the route cards' raster ground can be photographed here.
- **`postTransitModes=BIKE` fabricates a bike at the far end.** MOTIS answers
  with a `BIKE` egress leg while every transit leg says `bikesAllowed: false` —
  a bike no train carried. Egress is therefore always `WALK`. And
  **`preTransitModes=CAR` drives onto the platform** and abandons the car;
  park-and-ride is `CAR_PARKING`, which also returns bare-car itineraries, so
  the answer has to be checked for CAR-then-WALK. Both verified against
  Transitous; see § 9 of `docs/research/routing-motis.md`.
- **A dimension chain hangs a fixed number of *pixels* outside the outline, so
  the frame it needs is a pixel margin.** Reserving it in metres needs a scale,
  which the reservation then changes, and the two chase each other — a 35 m plot
  ended up at a third of its frame. `SitePlan.margin` is a pixel constant and
  the fit runs once against it.
- **Above ~16 boundary segments, a label per edge is not information.** The
  field a district address resolves to has 159 and every chain drawn turned the
  plan into a black band. The overall size (minimum rotated rectangle) is what
  survives; the setback table lists the individual lengths anyway.
- **A watched computed is evaluated whether or not the template reached it.**
  `PlotView`'s computeds all read `this.plot`, and a `v-if="plot"` had kept them
  from ever seeing `null`. Adding one watcher was enough to crash the page whose
  whole job is to explain that the id in the URL names no plot here.
- **"Something is selected" is not a signal that anybody selected anything.**
  `addPlot` puts every new plot into `state.data.selection`, so opening the
  overview's comparison mode when the selection is non-empty means opening it
  always — the state that button exists to get out of.

## Commands

```bash
# backend
python3 -m venv backend/.venv
backend/.venv/bin/pip install -e "backend[dev]"
backend/.venv/bin/python -m pytest backend/tests -q
backend/.venv/bin/python -m uvicorn app.main:app --reload --app-dir backend

# frontend — needs Node >= 22.19: jsdom 30 pulls in undici 8, and on Node 20
# vitest dies before loading a test with `markAsUncloneable is not a function`.
cd frontend && npm install
npm run dev            # proxies /api to 127.0.0.1:8000
npm run test           # vitest
npm run build

# screenshots of every view, light and dark
node scripts/screenshots.mjs
```

## Before calling a change done

1. `npm run test` and `pytest` both green — state the counts.
2. `node scripts/screenshots.mjs`, then **look at the images**. Tests do not
   catch a collapsed layout or an unreadable colour.
3. **Put the pictures of what changed in the chat**, not only the counts. A
   test count says a thing did not throw; it says nothing about whether the
   screen reads. Whoever asked for the change is the one who can see that, and
   they cannot if the images stay in `docs/screenshots/`. Send the views the
   change actually touched — a handful, not all thirty-seven.
4. Check both themes and a 390 px viewport. No horizontal overflow anywhere.
5. Print preview still sane if you touched layout.

Chromium is preinstalled at `/opt/pw-browsers`; never run `playwright install`.

## Test and screenshot counts at last check

- `pytest`: measured after the merge below
- `vitest`: measured after the merge below
- `scripts/screenshots.mjs`: measured after the merge below. It fails on console
  errors, on horizontal overflow, and if not a single vector tile arrived. It
  also drives the live geocoder, which is slow often enough to blow the 60 s
  wait on the destinations step — two runs failed there and the third passed
  with nothing changed. Re-run once before going looking for the bug.
