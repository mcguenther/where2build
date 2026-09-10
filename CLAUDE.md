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
backend/     FastAPI. Proxy and disk cache in front of ALKIS, BORIS, GeoSN
             WMS, MOTIS and the LLM. Owns no geometry maths and no database —
             PostGIS is in the plan, not in the code.
             `app/search/` is the exception in one direction only: it asks the
             cadastre a series of narrow questions and answers NDJSON, so the
             map can grow while it runs. Still no geometry maths.
frontend/    Vite + Vue 3, Options API. Owns ALL geometry.
docs/        Spec, service research, screenshots. `strategie/` holds the four
             interactive strategy pages for parcel identification.
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
  Union the polygons, sum the official areas. The search follows the same rule:
  several parcel numbers from *one* source („790/11 sowie 238/3“) are that set
  and are never put to the user as a question, while numbers from *different*
  sources — an image against the body text — are rival readings and are.
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
- **A contradiction is shown, never resolved quietly.** Two Gemarkungen in one
  listing, or a number on an image that the location field disagrees with, are
  a `Konflikt`: the search follows the most trustworthy reading, says which and
  why, carries the *Beleg* for each option, and lets the user pick another —
  which re-runs the search. A contradiction nobody can look up is one nobody
  can resolve.
- **The sentence under a check is composed, not written.** Every finding comes
  from a template in `frontend/src/lib/findings.js`: structured input from one
  service, fixed German text out. No model writes UI copy. That keeps the
  wording reviewable, keeps the same plot reading the same way twice, and makes
  it impossible for a missing input to turn into a sentence that sounds
  confident. The templates take the data's shape seriously — noise is a band so
  the text says a range, a designation is a yes or no so the text is a yes or a
  no.
- **The search field reads what was typed before it looks anything up**
  (`frontend/src/lib/queryInput.js`). Three signals settle almost everything: a
  German address never begins with a digit, so a leading digit rules the address
  index out; a coordinate is two numbers that land inside Germany; a parcel
  denominator (`85/1`) cannot occur in an address. Where two readings stay
  plausible — "Lessingweg 44" and "Mölkau 204" are the same shape — the answer
  says so and both local indexes are asked, rather than one being guessed.
- **The search decides with hard filters and orders with weights.**
  „Bestätigt“ means an *official* statement left exactly one parcel standing —
  a parcel number resolved against ALKIS, the Gemarkung, `ave:flaeche` when the
  listing's figure is exact — and nothing contradicted it. A single survivor
  reached only through a chosen tolerance is `mehrdeutig`. Everything
  inferential (a rounded area, a street, land use, a broker's distance) may
  only order the list, which is why the weights can ship uncalibrated: they
  can produce an unhelpful ordering, never a wrong answer. See
  `backend/app/search/`.
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
  tested. Its adapter goes straight to the paste field. Re-measured 09.09.2026:
  it is an AWS WAF challenge at the CloudFront edge (`x-cache: Error from
  cloudfront`), so the request never reaches an origin — a full browser header
  set, HTTP/1.1, a `ClaudeBot` UA and Anthropic's own fetch all answer 401
  alike, while `robots.txt` (200) explicitly *allows* `ClaudeBot` and the two
  exposé sitemaps it advertises answer 401. There is no header to fix. There
  *is* a documented API (`api.immobilienscout24.de`, search over two-legged
  OAuth, 2 000 req/min), but it is content-partner only, "not for data delivery
  use cases", and its terms forbid own databases and analyses and cap storage
  at 24 hours — so it is not a gate we could pass with paperwork, it is the
  wrong shape. The way in is the user's own browser.
  See `docs/research/immobilienscout24-zugang.md`.
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
- **A local MOTIS answers exactly what Transitous answers — once three things
  in its config are right.** Measured 01.09.2026 against
  `ghcr.io/motis-project/motis:2.11.2`: geocode, `/plan`, `one-to-many` and
  `map/stops` agree to the last decimal, and `/api/reachability` comes back
  character for character identical. The three: the dataset tag must be
  `de-DELFI`, because it is the prefix of every stop and trip id and the
  recorded fixtures carry it; `timetable.route_shapes` must be on, because the
  DELFI feed has no `shapes.txt` and without it every **transit** leg is a
  straight line between stops (67 points where Transitous returns 303 — street
  legs were always fine); and `preprocess_max_matching_distance` keeps stops
  outside the OSM extract from being dropped. Costs, measured: 6 min of import
  at 5,6 GiB peak RSS, a 3,4 GB graph, 1,7 GiB to serve.
  See `docs/research/routing-motis.md` § 5.
- **A cache key that does not name what produced the answer outlives the fix.**
  Twice now. The MOTIS cache was keyed on the request parameters alone, so
  changing `MOTIS_BASE_URL` kept serving the other instance's answers until
  `/cache/motis*` was deleted — reporting a difference between the two that was
  not there and, worse, an agreement that was not there either. The extracted
  listing was keyed on the URL alone *and* never expires (`ttl_s=None`), so an
  answer written before the price parser existed was still being served after
  it shipped, and the field stayed empty on exactly the listings the fix was
  written for. Both now carry it in the key: `MotisService.instance` is a hash
  of the base URL, `EXTRACTION_VERSION` is a number to bump whenever the
  reader's *output* changes.
- **The listing pin is the municipality, not the plot.** Measured on a real
  Kleinanzeigen ad (3499632623, 01.09.2026): `og:latitude/longitude` sat
  **6 235 m** from the parcel actually offered, because the platform geocodes
  its own location field ("04668 Sachsen – Grimma"). Resolving that point gives
  Gemarkung Grimma 2537 at 38 284 m² instead of Großbothen 790/11 at 502 m² —
  an answer that looks exactly as official as the right one. So there is no
  radius to search: the *Ortsteil* named in the body text is the usable
  statement, and the pin is only good for rejecting things.
- **`ave:flaeche` can be filtered server-side** with `PropertyIsEqualTo` and
  `PropertyIsBetween`, and it is the strongest cheap filter there is. Gemarkung
  Großbothen holds 1 131 parcels; adding `flaeche = 502` leaves **one**, and it
  is the right one. The whole of Stadt Grimma (32 544 parcels, 66 Gemarkungen)
  leaves 15. Two requests, no model call. Only use the exact value when the
  listing's number is exact — "ca. 500 m²" has to widen into a band.
- **`ave:lagebeztxt` is often `"ohne Lage"`**, so a street name cannot be matched
  against ALKIS as an attribute. Take the way from OSM and buffer it instead: a
  40 m buffer around Wiesenstraße catches 790/11 at 3 m, and an 80 m buffer cuts
  the 25 area candidates to 5 — better than the distance rings, which cut them
  only to 8.
- **Tesseract reads a Geoportal print's title block, and nothing else on it.**
  `-l deu --psm 6` on the ad's cadastral extract returned "Flurstück 790/11" and
  "Wiesenstraße - Großbothen" in 491 ms; the small in-map labels came out as
  garbage and the orthophoto yielded nothing. The two site photographs produced
  **no** false parcel numbers, which is why the right design is to OCR every
  image and filter by pattern rather than classify images first. Watch the
  footer: `Olbrichtplatz` is the GeoSN's own address, printed on every sheet.
- **`ave:tntxt` carries the actual land use, with the area share per kind** —
  790/11 is `Wohnbaufläche;502`, a carriageway parcel is `Straßenverkehr;1062`.
  It rides along with every feature, and `PropertyIsLike` filters it
  server-side: in Gemarkung Großbothen the ±5 % area band plus Wohnbaufläche
  goes 25 → 16. Use it as a *soft* signal only — an unbuilt building plot can
  legitimately be Landwirtschaft or Gartenland, so "Baugrundstück ⇒
  Wohnbaufläche" is an inference, not an official fact. The same field is where
  street surfaces come from: no OSM request needed to draw a carriageway.
- **For OCR, upscaling beats rotation handling.** Measured on the ad's Geoportal
  print: a 2x Lanczos upscale (long edge ≥ 1500 px) fixed `--psm 1`'s blindness
  to a 180° flip, fixed a 7° tilt with no deskewing at all, and lifted the
  orientation detector's confidence from ~1,0 to ~3,0. So: **upscale, then
  `--psm 6`, and only if no pattern matched `--psm 1`** (~780 ms + ~910 ms).
  An OSD pre-pass costs the same on *every* image and adds three failure modes —
  it reports the *complement* for ±90 at native size, it exits with "Too few
  characters" on an orthophoto, and it claimed `Rotate: 180` at confidence 0,72
  on one of the site photographs. Do not build deskewing: below 10° it is
  unnecessary after upscaling, above 15° it did not help even with the exact
  angle given.
- **A garbled parcel number is worse than none.** At 7° and native size the
  reader returned `Flurstück 790717` — it found the word and corrupted the
  digits. An empty answer is harmless; a plausible wrong number resolves to a
  real but foreign parcel, and that is precisely the error validating against
  ALKIS does **not** catch.
- **`SitePlan` draws no streets at all.** What makes its map look right is a
  MapLibre instance underneath carrying OpenFreeMap's `liberty` vector style,
  while the SVG holds its own parcel fill to `fill-opacity: .42`. The two map
  tokens `--w2b-map-street-surface` and `--w2b-map-existing` are declared and
  never used. Any new map component should take the same backdrop rather than
  hand-drawing streets — and copy the two techniques that do the work: a halo
  stroke under every line (6 px `--w2b-map-halo` beneath 2,2 px
  `--w2b-map-boundary`) and `paint-order: stroke fill` with a 3,4 px halo on
  every label.
- **A search map must never frame tighter than its own doubt.** The first
  Indizienkarte zoomed to whatever had just been found and thereby hid the other
  parcels that still matched the stated area. The camera is derived from the
  *live candidate set* plus the new indicium, with 35 % slack and a 120 m
  minimum half-width, so even a confirmed parcel is never shown without its
  neighbours. And a layer whose extent dwarfs the frame stops informing and
  starts tinting: the district wash and the street buffer fade out on the way in.
- **Counting place-name mentions picks the wrong place.** Against the 5 339
  names in `gemarkungen-sachsen.json`, this ad scores Grimma 3× and Großbothen
  3× — Grimma appears so often precisely because the plot is 6 km *away* from
  it. Extract the relation (`liegt_in`, `entfernt_von`), never the frequency.
- **A landmark named in a listing is usually somewhere to visit, not a
  neighbour.** The Grimma ad names Kloster Nimbschen and Schiffsmühle Höfgen; a
  1 km ring around either contains **0 %** of Gemarkung Großbothen, where the
  plot actually is — both are ~1,9 km from the nearest Gemarkung edge, and they
  only cover it at ~5 km, i.e. once they constrain nothing. As a hard filter
  either would have deleted the right answer. Point-like landmarks (under ~200 m:
  monastery, mill, station) are worth ranking with, but only when the text states
  a distance; extended ones (lake, forest, Bundesstraße) can only ever *refute*.
  A 1 km buffer round the Cospudener See polygon is 17,4 km² against 5,9 km² for
  a whole Gemarkung, and the B 107 corridor is 68,8 km².
- **Distance to an extended feature is measured from its boundary.** A 1 km disc
  about the Cospudener See's centroid covers 3,14 km² and does not even reach the
  4 km long lake's own ends — it is not a coarser version of the buffer, it is a
  different place. The constraint is an annulus, `buffer(geom, r) \ geom`.
- **`fes:BBOX` works on `ave:geometrie`.** Verified: a 2 x 2 km box round Kloster
  Nimbschen returns `numberMatched="407"`. That is the cheap way to combine a
  spatial claim with the WFS without putting geometry maths in the backend —
  pre-filter server-side, then test exactly on what comes back.
- **A street name without a containing area is a 1-in-500 shot.** Saxony holds
  2 918 OSM ways named `Bahnhofstraße` and 4 043 named `Dorfstraße` — roughly
  400 to 970 distinct streets each, spread over 220 km. Inside one Gemarkung a
  street name is essentially unique; on its own it is nothing. The same trap
  catches landmarks: 8 of 46 objects around Nimbschen are a hotel, a chapel, a
  ferry terminal and a viewpoint named after it.
- **The geocoder answers with far-away namesakes.** Transitous returns
  `Großbeeren, Bahnhof` — 134 km away — as the sixth hit for "Großbothen
  Bahnhof". Discard any geocoder result outside the already-narrowed area before
  it becomes a search constraint.
- **Rank by walking time, never air distance.** Detour ratios reach 2.88x, and
  the nearest thing by air can be unwalkable altogether.
- **The surroundings service ranks *within* a category, not across them.** Its
  answer is category by category, so the panel's own order was the category
  list's — a bus stop one minute away sat below a tram stop half an hour away.
  `NearbyPanel.found` sorts by walking time and puts what has no walk last.
- **Let the hard filters decide and the weights only order.** "Bestätigt" means
  plausibility raised no objection *and* exactly one candidate survives the
  filters that are official facts — a parcel key resolved against ALKIS, the
  Gemarkung, `ave:flaeche` when the listing's figure is exact. Everything
  inferential (a rounded area, a street buffer, land use, distance claims) only
  ranks. That removes the lead threshold entirely and means uncalibrated weights
  can never produce a wrong answer, only an unhelpful ordering — which is why
  this can ship without a corpus of solved listings.
- **A wrong Gemarkung anchor returns nothing, as long as the area is exact.**
  Measured on the three district names the Grimma ad contains: with
  `flaeche = 502` Großbothen gives 1, Grimma 0, Höfgen 0 — so run the staircase
  against every place candidate and let the area pick. One rung wider it inverts:
  at ±0,5 % Grimma yields **26** against Großbothen's 2, because it is the bigger
  district. The place named most often is also the one that manufactures the most
  false candidates, so from that rung on the relation has to be right.
- **The anchor's size is not a reason to give up.** A proposed "refuse anchors
  over 60 000 parcels" rule was refuted by measuring it: **Stadt Leipzig has
  112 588 Flurstücke and Dresden 108 558**, and Leipzig plus an exact 502 m²
  still leaves 78 — a scoreable set. Cap the *candidate set after the hard
  filters*, never the anchor.
- **When no single parcel can be named, name the common envelope.** The smallest
  unit every surviving candidate shares is a real answer: the 25 area candidates
  share Gemarkung Großbothen, the 5 that survive the street buffer share
  *Wiesenstraße in Großbothen*. It must never be drawn like a hit, though — halo
  and drawn contour stay reserved for a confirmed parcel.
- **An address is not a plot.** A district address ("Plaußig-Portitz, 04349
  Leipzig") geocodes to a point in a field, and the parcel under it is not the
  one in the listing. `/api/parcels/resolve` takes `expected_area_m2` and
  answers with a `plausibility` block; MOTIS's `type: PLACE` versus `ADDRESS`
  is the sharpest of the three signals, and works even with no listing area.
- **A geocoded house number is not the parcel that carries it.** "Lessingweg 44
  Leipzig" geocodes to a point that lies *inside* Flurstück 205, whose
  Lagebezeichnung is "Lessingweg 46" — 0,3 m on the wrong side of the boundary
  of 204, which is the one actually named "Lessingweg 44". No radius and no
  nearest-neighbour rule fixes that; the parcel's own `lagebeztxt` does, when it
  matches exactly one candidate, and the user's click does when it does not.
  `/api/parcels/nearby` therefore answers with all 37 parcels within 60 m and
  the wizard draws them on the cadastral ground, each with its number.
- **The set of parcels is the user's to assemble, and the register does the
  arithmetic.** The picker asks `/api/parcels/resolve` with the `kennzeichen` of
  the whole set, so the union and the summed official areas come from the same
  code every other way in uses — no polygon union in the browser. Two clicks on
  Lessingweg 44 and 46 give one plot of 1 299 m² with 8 boundary points, and the
  plot page, the checks and the print sheet take it unchanged. At least one
  parcel always stays: a plot with none is not a plot.
- **A click has two meanings, and the common one is replacing.** Correcting the
  parcel the coordinate landed on is what nearly every user does; assembling a
  plot out of several is the rarer case and would otherwise happen by accident.
  So the default click switches the plot to the parcel clicked, and a switch in
  the map's toolbar turns on composing, where the same click adds and removes.
- **A chosen parcel is drawn with no fill, and the drawing above it swallowed
  the click.** The picker's polygons sat *under* the plot's own fill, so taking a
  parcel back out never worked: the press landed on the plot, not on the parcel.
  The group is drawn above the plot now (visually identical — the chosen ones
  are transparent, the others do not overlap it) and carries
  `pointer-events: all`, which hit-tests an unpainted area.
- **A split selection is marked, not refused.** Parcels that do not touch union
  into a MultiPolygon, which one outline cannot hold — but refusing the click
  closes the only way back: to drop the middle parcel of three you have to pass
  through a split plot. So the drawn outline is the piece around the parcel the
  selection started from (`outerRing` takes `near`, else the largest part), the
  ones outside it are drawn in red, and "Anlegen und öffnen" is disabled with the
  reason until they are gone.
- **The 3 m line's arc at an inward corner is the rule, not decoration.** Where
  two parcels of unequal depth meet, the plot has a reflex vertex, and "at least
  3 m from every boundary" means "at least 3 m from that point" — the envelope's
  own vertices sit at r = 3,00 m from it, measured. Squaring the corner would
  *remove* buildable land: 1,44 m² on the app's own L-shaped test case (9 − 9π/4
  = 1,93 m² in theory), and it would pull the corner 1,24 m further in along the
  diagonal.
- **`metrics.streetFrontage` measured edge 0, not the street edge.** Harmless
  on a single parcel whose ring starts at a corner, wrong the moment a plot is
  a union: the ring then starts where the two outlines meet, and Mölkau 204+205
  reported a 2,04 m stub as the frontage. It reads `plot.streetEdge` now — the
  edge the rest of the app already calls the street side.
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
- **A prevented `pointerdown` produces no `click` at all.** `SitePlan` captures
  the pointer and calls `preventDefault` so panning follows the hand, which
  silently kills every click handler under it — the parcels the picker offers
  looked inert. The press is remembered and the *release* decides: same spot
  within 4 px picks, further than that panned.
- **The picker frames the plot and a band, not every candidate.** 33 parcels
  come back within 60 m of an address; framing all of them made each one a
  speck and floated the labels over paper. `CHOICE_BAND_M = 18` — about one
  plot's width — keeps the neighbour either side clickable and the drawing
  legible.
- **Two parcel numbers in the same spot read as a third.** "292/2" over "293/5"
  came out as "29293/5". The labels are culled against each other — the chosen
  parcel first, then the larger ones — so what gets dropped is the sliver at
  the edge, not the plot in the middle.
- **The ground's camera hangs off the drawing's *rendered* width.** The SVG is
  640 units wide and renders at 776 CSS px inside the panel; `setCamera` divides
  by that ratio, so a measurement taken before the layout settles — or a window
  resize afterwards — leaves the backdrop at a different scale than the drawing,
  and the outline stops sitting on its own parcel with nothing in the console.
  A `ResizeObserver` on the svg re-sets the camera; measured after a resize, the
  drawing's metres per pixel and the map's agree to nine decimal places.
- **A MapLibre map that never finished starting cannot always be removed.**
  Without WebGL the constructor succeeds and the first frame does not, and
  `remove()` then throws on internals it never created — which took a component
  down on unmount. Teardown swallows that, and `setCamera` catches too: it runs
  on every pan, where a throw would freeze the drawing rather than the backdrop.
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
- **One destination the router cannot answer must not cost the page.**
  `reachability()` asked for every destination and mode in one `asyncio.gather`,
  so a single upstream failure raised out of the whole endpoint and every other
  row was lost with it — which is the 500 an outage produces. It gathers with
  `return_exceptions=True` now and turns an `AppError` into a row that is not
  reachable and carries the German sentence in `hinweis`; anything else still
  raises, because a bug is not a routing result. The way-out sentence therefore
  travels *in the row*, and the endpoint answers 200.
- **A single 5xx from an upstream is worth one retry, and only one.**
  Transitous answers 500/502 now and then under load, and the request that
  follows 600 ms later succeeds. `upstream.py` retries once on 500, 502, 503,
  504 and on a transport error; a second failure is believed. More attempts
  would turn a real outage into a minute of waiting per row.
- **A placeholder has to have the shape of what is coming.** The route
  placeholder was a row of thin bars and what arrived was a card as tall as its
  map, so the page jumped by that height when the answer landed. It lives in
  `RouteCards` now, behind a `busy` prop, next to the layout it imitates — and
  the same pulse (`.skeleton*` in `base.css`, since a scoped style reaches
  exactly one component) serves the check list, the route cards and the two
  routed columns of the surroundings table.
- **A dimension chain hangs a fixed number of *pixels* outside the outline, so
  the frame it needs is a pixel margin.** Reserving it in metres needs a scale,
  which the reservation then changes, and the two chase each other — a 35 m plot
  ended up at a third of its frame. `SitePlan.margin` is a pixel constant and
  the fit runs once against it.
- **Above ~16 boundary segments, a label per edge is not information.** The
  field a district address resolves to has 159 and every chain drawn turned the
  plan into a black band. The overall size (minimum rotated rectangle) is what
  survives; the setback table lists the individual lengths anyway.
- **A route card's drawing is shaped by the route, and its frame is also the
  zoom.** One fixed 300 x 150 box gave a commute due north two empty margins and
  a run along the B6 a strip of nothing. The frame's proportions now come from
  the projected bounds, clamped by how many cards share the row — and because
  `tileCover` reads its zoom off the frame, the frame's *width in user units*
  has to follow the row too: a 300-unit drawing stretched over 1300 px fetches
  its ground four zoom steps too shallow and shows it blurred, with nothing in
  the console. The scale caption measures the fitted frame, not the route's own
  box: a route due north spans almost no longitude and was labelled ten metres
  wide.
- **A watched computed is evaluated whether or not the template reached it.**
  `PlotView`'s computeds all read `this.plot`, and a `v-if="plot"` had kept them
  from ever seeing `null`. Adding one watcher was enough to crash the page whose
  whole job is to explain that the id in the URL names no plot here.
- **The basemap has a palette, and it is not a preference.** A drawing sits *on*
  the backdrop, so a near-white ground under a dark page loses the plot outline
  in its own glare. OpenFreeMap serves `styles/dark` (neutral near-black) and
  `styles/fiord` (blue-grey); `dark` is the one that sits next to this app's
  warm near-black paper. The variant travels in the URL
  (`/api/basemap/style.json?variant=dark`) so the two documents cache
  separately, and the *browser* decides which one, because only the browser
  knows what `system` resolved to. MapLibre also draws its own controls and
  ships them white — restyled through the palette tokens in `base.css`, with
  the icons reached by a filter because they are background images.
- **The POI index's filename is a default, not a claim.** `poi-sachsen.json`
  built from a Leipzig-region BBBike box is still called that; the extract it
  really came from is in the file's own `quelle`, and its `datenstand` is the
  extract's timestamp. Read those. Scope itself is a command-line argument
  (`--url`, `--out`) — see README, "Reach of the POI index", and
  `docs/research/poi.md` § 12.
- **"Something is selected" is not a signal that anybody selected anything.**
  `addPlot` puts every new plot into `state.data.selection`, so opening the
  overview's comparison mode when the selection is non-empty means opening it
  always — the state that button exists to get out of.
- **`luis.sachsen.de` and `geodienste.sachsen.de` are two different worlds.**
  Cadastre and base maps (ALKIS-WFS, DOP, WebAtlas) sit on the second; every
  environmental layer — noise, flood, water protection, soil, boreholes, radon
  — sits on the first, as an open ArcGIS REST server. A guessed `wms_smul_*`
  name on `geodienste` answers 403, which reads like a block and is a wrong
  path: the documented ALKIS-WFS on that same host answers 200. And the
  service inventory is worth enumerating in full before concluding something
  is missing — `luft/radonvorsorgegebiete` sits in the `luft` folder, not
  under any name containing "strahl", and was missed twice by a partial listing.
  See `docs/research/grundradar-datenquellen.md`.
- **ArcGIS `identify` measures its tolerance in *pixels*, so it is the wrong
  tool for a factual answer.** It also demands `mapExtent` and `imageDisplay`,
  which the query is not geometrically about, and returns zero hits rather
  than an error when either is missing. Worse: at `tolerance=3` and a plausible
  extent, 3 px was about 7 m, and the service reported a neighbouring polygon
  as a hit — which put a wrong noise band in the first draft of the research.
  Use `/<layer>/query` with `esriSpatialRelIntersects`; it intersects the real
  geometry and knows no scale.
- **Ask the noise map with the parcel outline, never with a point.** A plot
  straddles isophones: Mölkau 204 is `Lden5054` at the building point and
  `Lden5054` + `Lden5559` across its 650 m². The ALKIS ring we already fetch
  goes straight in as `esriGeometryPolygon`. And the levels are 5 dB **bands**
  (`Lden5559` → "55–59 dB(A)"), never a single figure — "57 dB" would be
  invented.
- **"No noise value" is not "quiet".** Umgebungslärm mapping is limited to
  agglomerations and major routes: road-noise polygons within 300 m number 109
  in Leipzig and 94 in Dresden, but **0 in Geithain** (6 000 inhabitants) and 0
  in a village. So three outcomes, not two — a hit gives the range; no hit but
  polygons within 2 km means below the lowest mapped band (< 45 dB(A)); nothing
  within 2 km means "not mapped here", with no value and no colour. The
  `Kartierungsgebiet` layer cannot serve as that mask: it is a polyline of
  4 637 mapped road segments carrying traffic counts, so a point query never
  hits it.
- **A `minScale` layer returns an empty image, not an error** — and the scale
  is computed, so it can be steered. The noise layer carries `minScale: 50000`
  and draws nothing above 1:50 000. ArcGIS derives the scale as
  `(bbox_width_m / image_width_px) * dpi / 0.0254`, verified exactly: at a
  10 km box and 512 px, `dpi=65` gives 1:49 982 and draws, `dpi=66` gives
  1:50 750 and returns a blank 2 231-byte PNG. So clamp `dpi` to
  `minScale * 0.0254 * width_px / bbox_width_m` and the layer never silently
  disappears.
- **The noise WMS cannot do Web Mercator.** It offers EPSG:4326 and 25833 but
  not 3857, so MapLibre's `{bbox-epsg-3857}` raster source gets nothing. The
  ArcGIS `export` endpoint with `bboxSR=3857&imageSR=3857` reprojects
  server-side and sends CORS headers — that is the path for the overlay.
- **The BfN protected-areas WMS filters on User-Agent.** No UA: 403. Any UA:
  200 with full capabilities. An empty User-Agent is a rule here, not a
  network problem.
- **The UBA air-quality API is not on `umweltbundesamt.de`,** and its nearest
  station is not the one to use. The documented path is a 301 to
  `luftdaten.umweltbundesamt.de`, where it spells `air-data`, not `air_data`.
  And the station list mixes in historic and research sites whose "active to"
  field is empty anyway: the three nearest to Mölkau (1,9–3,0 km, prefixed
  `z_GUAN` and `zDDR_`) return no measurements at all, while Leipzig-Mitte at
  4,6 km returns all four pollutants. Pick the nearest station that actually
  answers with values, not the nearest on the map.
- **A parcel number is a hard filter that can be run against a *set* of
  anchors, and that is what dissolves a contested Gemarkung.** Measured
  05.09.2026 on the Grimma ad: 790/11 exists in Großbothen and in **none** of
  Grimma, Höfgen (144245) or Höfgen (146132). Four `resultType=hits` requests
  and the contest is over — no relation extraction, no model call, no question
  to the user. So never *choose* one anchor: ask them all, and let the cadastre
  answer. An ambiguous name contributes **all** its districts; dropping it for
  being ambiguous throws away the case the search exists for.
- **The short circuit has to check, not just resolve.** Gemarkung plus
  Flurstück is not a verdict on its own: a misread number resolves to a real
  but foreign parcel, and validating against ALKIS is exactly what does *not*
  catch that. The cross-check is free — `flaeche` and `gemeinde` arrive **with**
  the parcel — so the official area is compared against the listing's, and the
  municipality against the location field, before anything says „bestätigt“.
  The one string test worth having is the AdV key's own widths: five digits of
  numerator, four of denominator, so `790717` is not a parcel number at all.
- **`ave:lagebeztxt` *is* filterable with `PropertyIsLike` — and must never
  filter.** The earlier note ("a street cannot be matched as an attribute") is
  too strong: in Gemarkung Großbothen 71 of 1 131 parcels carry `Wiesenstr*`.
  But 577 carry `"ohne Lage"` and **790/11 is one of them**, so a hard street
  filter deletes the right answer. Use it to promote, never to demote: a
  missing address is missing data, not a contradiction. Costs nothing — the
  field rides along with every feature, so no Overpass request for the common
  case.
- **„OT von X“ names the Gemeinde, not the Gemarkung.** „am Ortsrand von
  Großbothen, einem OT von Grimma“ places the plot in Großbothen and says
  Grimma is the municipality above it. Read that way the two names stop
  competing and the frequency trap disappears without a parser or a weight —
  and the second mention („die ca. 6 km entfernte Kreisstadt Grimma“) turns
  Grimma into evidence *against* itself. Extract the **level**, not just the
  place.
- **`resultType=hits` is what makes the staircase affordable, and ALKIS cannot
  be asked for attributes without geometry.** A count is a few hundred bytes
  whatever the number; features are ~1,4 kB each (25 parcels = 35,6 kB in
  1,5 s, measured). So: count every rung, every anchor and every number probe,
  and fetch features only once the count is small enough to draw. The abort
  belongs on the **candidate set after the hard filters** (~500), never on the
  anchor — Stadt Leipzig has 112 588 Flurstücke and an exact area still leaves
  78.
- **`ave:KatasterBezirk` by `schluessel` is one request and 16,5 kB** (637
  boundary points for Großbothen). That is where the search map's district wash
  comes from: the committed `gemarkungen-sachsen.json` drops the geometry on
  purpose, so the outline is fetched on demand rather than added to the file.
- **`ave:tntxt` splits on the semicolon, not the comma.** The kind and its area
  share are separated by `;`, but the *name* can contain a comma —
  „Sport-, Freizeit- und Erholungsfläche;500“. Splitting on both puts „Sport-“
  in the table as if that were a land use.
- **A search map must show its candidates at the scale it is standing at.**
  Twenty-two parcels spread over two Gemarkungen are a few pixels each; the
  outlines are drawn and nothing is visible. `EvidenceMap` therefore gives
  every candidate a dot that fades in below zoom 17 and out again once the real
  outline can be seen.
- **What the queue paces is the camera, not the reading.** The dwell exists
  because three camera flights started in one frame is a twitch — and the first
  two versions of it slowed down *every* line instead, which is the wrong thing
  in both directions: a phase line, a street, a land use and an area statement
  all land on a map that stays exactly where it was, so holding each for two
  seconds is a long wait in front of nothing moving, and the flights that do
  happen were no calmer for it. `movesTheMap` names the four lines the camera
  follows — `gebiete`, `kandidaten`, `ergebnis` and the `pin` Indiz — those get
  the dwell and share the budget, everything else gets `QUICK_MS = 250`.
  Measured on the recorded Großbothen run: 16 lines, **3** of them camera
  moves, 21,2 s before and **7,3 s** after, with each flight still getting its
  full two seconds. Weighed off the event rather than measured off the map,
  because the queue asks it of lines it has not applied yet — so the frame may
  still turn out identical and the step waits for a flight that never happens.
  That way round is a calm camera; the other way round is the twitch.
  `prefers-reduced-motion` skips it all.
- **A sentence that changes every step must not be set as the heading.** The
  status box above the map put the phase text in its `<h2>` at `text-xl`, and
  those texts run from four words („Angaben aus dem Inserat lesen") to four
  lines („Gegenprobe eine Stufe weiter (499.49 bis 504.51 m²): 1 weitere
  Flurstücke ähnlicher Größe. Sie erfüllen …") — so the box resized under
  itself sixteen times a run and shoved the whole stage, map included, down and
  up with it. The heading is the phase's one-word *label* now (the same
  vocabulary the Verlauf marks its rows with), the wording moved to the body
  line where two lines are reserved and the running text is clamped to two, and
  the „Abfragen ans Kataster" slot is kept in the layout while the number is
  still unknown, because below 700 px it wraps onto its own line. Measured
  against the live cadastre before and after: **one** box height for the whole
  run at 1440 px (123 px) and at 390 px (155 px), with the stage's top edge
  fixed. It still grows once when the answer lands — the verdict sentence and
  the hint are real content — and clamping *those* to save that one change
  would be the wrong trade.
  The pulse along the bottom edge exists because something has to say the run
  is alive, and what used to say it was the wording jumping about. A bar of a
  fixed height cannot move the layout, and it needs the faint rail behind it:
  without one the travelling segment reads as a broken border.
- **The protocol follows the run, and stops following the moment somebody
  scrolls up.** The list is the one place the order of a run can be checked, and
  it grew past its 560 px box with the newest line always out of sight.
  `record` asks whether the box was at its end *before* the entry is added and
  only then scrolls — a list that jumps out from under someone reading an
  earlier clue is worse than one that does not follow at all. The tolerance is
  about one row, because a browser rounds a scroll position by a fraction of a
  pixel and an exact comparison reports "scrolled up" on a list nobody touched.
  And the panel head had to become `position: sticky`: „Rest zeigen" is the
  only control that matters while a run plays, and it was the first thing to
  disappear upwards.
- **`this.timer = setTimeout` and then `this.timer(…)` throws „Illegal
  invocation“.** The native function ends up with the queue as its receiver.
  Nothing else fails: the run simply stops after its first line, with the map
  still showing the whole of Saxony and one entry in the protocol. Wrap the
  timers (`(fn, ms) => setTimeout(fn, ms)`), do not reference them.
- **The directory's `gemeinde` column is the key nothing was using.** There are
  two Gemarkungen called Plagwitz — 140427 in Leipzig, 148642 in Machern — and
  „Ortsteil Plagwitz von Machern“ picks one with a directory lookup and no
  request. The same column removes Gemarkung Leipzig as an anchor when the
  location field says Neukieritzsch, which is what stopped a listing's two
  false 1 025 m² candidates. Used as a filter *with a fallback*: nothing
  matching means the whole anchor set stands.
- **The location field's *municipality* is reliable even though its coordinate
  is not.** That reads like a contradiction of the 6 235 m pin and is not: the
  pin is that far out *because* it is the municipality's geocode, so the name
  it was geocoded from is exactly the part that holds. True on all four
  adverts measured — Grimma/Großbothen, Machern/Plagwitz,
  Neukieritzsch/Lobstädt, Bad Lausick/Etzoldshain.
- **Widen the *place* before the *number*.** „1.076 m² in Bad Lausick“ has **0**
  matches in Gemarkung Bad Lausick and exactly **1** in the Gemeinde — Flurstück
  502/47 in Gemarkung *Etzoldshain*, `lagebeztxt` „Am Kurpark“, and the advert
  is titled „Naturnah wohnen am Kurpark“. An exactly stated area is an official
  fact; a Gemarkung read out of prose is not, so opening the tolerance to keep
  the guess throws away the better of the two.
- **German capitalises every noun, so a capital letter finds nothing.** „geprägt
  von Wiesen und Feldern“ made Gemarkung Wiesen (148950) an anchor; „Ihr Platz
  zum Träumen“ and „einen befahrbaren Feldweg“ were read as streets. Only a
  place with a *positional* relation is searched — a bare mention stays in the
  protocol as weak evidence and costs no request. And „Anbindung **an**
  Leipzig“ is connectivity, not location.
- **„Ortsteil <A> von <B>“ — the district comes first, and both matter.**
  „Ortsteil Plagwitz von Machern“, „Ortsteil Lobstädt bei Neukieritzsch“,
  „Ortsteil Plagwitz der Gemeinde Machern“: A is the Gemarkung, B the Gemeinde.
  „Großbothen, einem OT von Grimma“ is the same statement with the name in
  front. Reading the *level* is what makes the municipality usable.
- **Reading a listing's images concurrently is slower, not faster.** Tesseract
  is CPU-bound; seven at once pushed every process past a 30 s timeout on this
  machine, where sequentially each takes 0,9–5 s. Read them one at a time and
  stop at the first parcel number — the drafted algorithm said so and the
  concurrency was an unmeasured optimisation that made it worse.
- **A timed-out reader looks exactly like a photograph of a lawn.** Both
  produce no text, and reporting both as „kein Katasterauszug dabei“ is a claim
  about the listing that was never checked. `ocr.read()` returns the failure
  next to the text, and the search says how many images it could not read.
- **What a portal *serves* is smaller than the reader wants.** Kleinanzeigen's
  largest variant is 678 x 960 for a cadastral print and 960 x 720 for a
  photograph, whatever the camera produced — so the 1 500 px upscale runs on
  every image in production, not on the odd small one.
- **Kleinanzeigen answers the first request with 403 and the second with the
  page.** Reproduced on three adverts, exactly once each. Not a block, a
  warm-up: `fetch_page` retries once.
- **The whole page is not the listing.** `html_to_text` returns navigation,
  cookie banner and category tree, and the search read all of it as evidence.
  The description sits in `#viewad-description-text`, and the attribute list
  beside it carries the *authoritative* area — a title may hedge („ca.
  1.025qm“) where the field states 1.025 m², and the tolerance staircase starts
  from the wording.
- **Verify a "not affected" against a control point.** A layer that answers
  zero features looks the same whether the plot is clear or the layer is
  empty. `luft/radonvorsorgegebiete` holds 107 municipalities and answers "no"
  for Leipzig but "yes" for Johanngeorgenstadt and Schneeberg — only that
  second query turns silence into a statement. The same check on the other
  designations: flood HQ100 is empty at Mölkau and names "Vereinigte Mulde" at
  Grimma, drinking-water protection is empty at Mölkau and names a zone on the
  Dresden Elbwiese. Every layer in `services/luis.py` has one.
- **The flood *risk* map is not the flood *extent*.** `wasser/hochwasserrisikokarte`
  carries affected inhabitants per municipality and cultural sites, and
  `wasser/hochwasserrisikogebiete` layer 0 is a **polyline** of 4 637
  watercourses — the same trap as `Kartierungsgebiet` in the noise service, and
  an area query never hits it. The extents are `wasser/hochwassergefaehrdung`
  layers 6 to 10, HQ20/25 through Extremhochwasser. `hochwassergefahrenkarte`,
  without the "-gefaehrdung", answers `Token Required`.
- **The noise layer's data and its own legend disagree at the bottom band.**
  `returnDistinctValues` on layer 4 gives seven categories including
  `Lden4549`; the renderer of that same layer has six, starting at
  `Lden5054`. So the survey has measured 45 to 49 dB(A) and draws nothing for
  it. The check text therefore reads the *data* ("below 45 dB(A)" is provable
  inside a mapped area) and the map key shows the *drawn* bands from 50, saying
  so. The six colours come from the renderer, not from taste.
- **The `minScale` dpi clamp holds at every zoom, so the noise layer needs no
  minimum zoom.** Measured on real 256 px tiles over Mölkau:
  `dpi = min(96, floor(minScale · 0,0254 · px / bbox_m))` draws at z10 (dpi 8,
  1:48 149, 59 kB) as well as at z18. Floor, not round — the threshold
  excludes: at 10 km over 512 px, dpi 65 draws and 66 returns the blank
  2 231-byte image.
- **The ALKIS WMS has twelve layers, and its groups are not the
  Liegenschaftskarte.** `adv_alkis_tatsaechliche_nutzung`, `…_siedlung`,
  `…_verkehr` draw *land use* — blocks of Wohnbaufläche and Grünfläche that run
  straight across parcel boundaries, which is what a ground called "Kataster"
  showed until the layer list was read properly. The cadastral ground is
  `adv_alkis_flurstuecke` (boundaries and their numbers) plus
  `adv_alkis_gebaeude`. The capabilities list twelve layers, not the six in the
  old note.
- **The cadastral layers have a scale limit of their own, and it is the same
  trap as the noise layer's `minScale`:** Flurstücke draw *below* 1:2000 and
  answer a 2 646-byte empty PNG from 1:2000 on, buildings from 1:5000 — no
  error, nothing in a log. A WMS derives the scale from the standard 0,28 mm
  pixel, and `MAP_RESOLUTION` says the pixel is a different size, so the same
  clamp works: on a z18 tile (1:2133) `MAP_RESOLUTION=85` draws and 86 comes
  back blank, exactly where `bbox · res / (px · 0,0254)` reaches 2000. `DPI=85`
  answers byte for byte the same; a nonsense parameter changes nothing, which
  is how you know it is the parameter and not the extra argument.
  `services/tiles.py` sends it only when the standard pixel would cross the
  line, so z19 is untouched and z16 still shows the parcel fabric.
- **There are two cadastral overlays, and they are not spellings of each
  other.** `adv_alkis_flurstuecke` stops drawing at 1:2000 either way, and the
  two ways round it produce different pictures. `flurstuecke` renders the tile
  oversized and scales it back, so its outlines still draw across a district
  (down to z15) — and its *labels* shrink with the render: measured at z18 over
  Liebertwolkwitz, the numbers come back as unreadable smudges. That is the
  search map's ground, where the outlines are the point. `liegenschaftskarte`
  asks for a plain 256 px tile and moves the limit with `MAP_RESOLUTION`
  instead, so the same z18 tile carries 101/2, 85/1, the boundary points and
  „Wiesengasse“ legibly. That is the picker's ground, where the numbers are the
  point — and `SitePlan.groundNamesParcels` stops drawing its own labels only
  for that one.
- **A tile cache keyed by the layer's *name* serves the previous
  configuration.** `alkis` stood for the land-use layers and then for the
  parcels, and every cached tile kept the old picture — which looks exactly like
  a change that did not work, on the reviewer's machine as much as here. The key
  now carries a digest of what the layer actually asks for (url, layer list,
  kind, minimum scale), so a changed configuration simply misses.
- **The picker's ground is the photograph with the cadastre's line work over
  it.** `adv_alkis_flurstuecke` alone draws boundaries, parcel numbers, boundary
  points *and street names* on transparent ground — measured over
  Liebertwolkwitz, no second layer needed — while `adv_alkis_gebaeude` would
  cover the roofs the photo is there to show. The overlay is drawn at 0,95: the
  noise veil's 45 % is for areas, and a boundary at that strength is a smudge.
- **Picking another parcel must not move the camera.** Re-centring on the new
  outline makes the step look identical before and after the click, and puts the
  neighbours the user was comparing somewhere else. `SitePlan.holdFrame` keeps
  the frame across the change — in WGS84, because the local metres are measured
  from each plot's own anchor, so the same numbers would be a different place.
  A double click still resets to the plot's own framing.
- **ArcGIS `query` answers "is anything within r?", never "how far".** So a
  distance to the nearest protected area is a *band*, and it comes from a
  binary search over a ladder of radii — three requests, not seven. Mölkau 204
  has nothing at 300 m and one at 400 m, so the answer is "300–400 m". A single
  figure out of that would be a measurement nobody made.
- **The neighbours' outlines need no OpenStreetMap at all.** The simplified
  ALKIS WFS — the one the parcels come from — carries `ave:GebaeudeBauwerk`, and
  it was in `docs/research/geodaten-sachsen.md` § 1.1 from the first survey while
  the feature reached for Overpass and demanded `OVERPASS_ENABLED`. Measured
  06.09.2026 over Mölkau 204: 146 outlines in a 240 m box, with `funktion`
  („Wohngebäude"), `lagebeztxt` and `aktualit` per object, through the proxy and
  its disk cache. Same gap as OSM, though: **no wall height and no storeys**, so
  § 6's 3 m floor stays the only computable depth. Overpass remains the
  fallback — it maps garden sheds the cadastre leaves out and is the only source
  of storeys at all.
- **A shared class in a scoped `<style>` is styled in exactly one view.**
  Vue's `[data-v-…]` attribute is per component, so the app's page furniture —
  `.breadcrumb`, `.page-head`, `.page-head__sub`, `.plan-bar`, `.button-group`,
  `.toggle`, `.plan-foot`, `.value-list`, `.missing` — was declared in
  `PlotView.vue` and *copied* into six other views. The views that never copied
  it rendered the same markup unstyled: the surroundings map and the location
  record had a breadcrumb without separators, a page head whose buttons dropped
  under the text, and raw browser buttons in the map toolbar. They now live in
  `base.css` once; a view that wants another measure overrides the one
  declaration it cares about. Anything a second view uses belongs there.
- **ALKIS delivers counter-clockwise rings, and ArcGIS reads one as a *hole*.**
  A polygon that is nothing but a hole has no area to buffer, so every
  `distance` query on it answers `{"code": 400, "message": ""}` — an empty
  message that says nothing about why. Measured 05.09.2026: Flurstück 263/7
  (86 m², 5 points) failed that way on the borehole and protected-area layers at
  *every* radius from 50 m up, and the same ring reversed returned 114
  boreholes; Flurstück 204 (650 m²) answered either way, which is what kept it
  hidden. `services/luis.py` orients every ring clockwise before it goes out.
- **A template reference to a computed that does not exist crashes the view,
  and Vue then renders nothing at all.** `WizardView` read `draftBuilding.width`
  in the branch that says the footprint fits nowhere, and nothing ever defined
  `draftBuilding` — so the one plot that needed the message got an empty page
  under the header instead. A `v-if` around the branch is what let it survive:
  it only ever ran for a parcel too small for the default footprint.
- **A suggestion row is read left to right, so the address goes first.** The
  category sat in the left-hand column and the hit in the right one, which made
  every row read "Adresse … Lessingweg 44": the useful half last, and furthest
  from where the caret is. Name first, category small and grey on the right,
  context underneath.
- **An absolutely positioned dropdown inside a `.panel` is clipped.** `.panel`
  carries `overflow: hidden` to keep map canvases off its rounded corners, so
  the search suggestions were cut after the first row. The list is in the flow
  instead — it pushes the hint down, and no ancestor can cut it.
  The same `overflow: hidden` eats a table that grew a column: at 390 px the
  surroundings table was 438 px wide inside a 340 px panel, so „Strecke“ was
  simply gone — with no scrollbar, and with the page's own `scrollWidth`
  reporting no overflow at all. A wide table goes in the `.table-scroll`
  wrapper `base.css` already has, and gives up its cell padding below 620 px so
  it fits without needing one.
- **Chromium hides a closed `<details>` through `::details-content`.** Forcing
  `display: block` on the children is not enough for print; the pseudo-element
  needs `content-visibility: visible`. Both spellings are in `print.css`, since
  older builds hide the children directly.
- **A German thousands stripper eats a coordinate.** Removing every `.` turned
  `51.189265` into `51189265`, and every Kleinanzeigen listing answered 422
  („Der Wert darf höchstens 90.0 betragen") before the search asked the
  cadastre anything. A dot separates thousands **only in groups of three**, and
  a comma settles it outright: `1.025` is 1025, `51.189265` is a coordinate,
  `1.025,50` is 1025,5. One reader for both — `parseGermanNumber` in
  `frontend/src/lib/format.js`; the helper that broke this was a local copy in
  the wizard, which is how it survived.
- **The price is in the markup three times and never needs a model.**
  `<meta itemprop="price">`, the JSON-LD `offers.price` and `#viewad-price` —
  the first hit answered all four measured adverts (60 000 / 165 000 / 80 000 /
  195 000 €). It had been left to the LLM, so the field stayed empty on exactly
  the pages that have a known adapter.
- **The clipboard carries `text/html` next to `text/plain`, and it carries the
  body and nothing else.** The paste field keeps the HTML flavour (`@paste`,
  capped at 400 000 characters), which is right — but `Strg+A` selects the
  *body*, so every `<meta>` and every `<script type="application/ld+json">`
  stays behind. Measured in Chromium: `og:latitude`, `og:longitude`, a head
  `itemprop="price"` and JSON-LD are all absent; `#viewad-price`,
  `.addetailslist--detail`, `<img src>` with its `?rule=$_59` variant and a
  body-level `itemprop` all survive. So a pasted Kleinanzeigen page loses the
  coordinates a fetched one gets for free, and a pasted ImmoScout page loses
  every deterministic field at once — which is why it reads as having no
  address, no coordinate and no parcel number, a fact about the clipboard and
  not about the portal. The fix is not more prose parsing: it is getting the
  real DOM out of the browser that already has it, which is what
  `lib/bookmarklet.js` does — one click on the listing page hands over
  `document.documentElement.outerHTML` through `postMessage`, so no CORS, no
  request to the portal and nothing circumvented. Verified end to end across
  two origins by `scripts/bookmarklet.mjs`. **The coordinate is not what is
  gained**, though the first version of this note said so: a portal's
  coordinate is the municipality's or the quarter's, never the plot's — that is
  the 6 235 m measurement two notes above — so losing it costs almost nothing.
  What the whole document actually adds is the portal's **own structured
  fields**: on ImmoScout, `obj_lotArea: "742"` where the prose hedges „ca.
  742 m²", plus `geo_bln`, `geo_krs` and the Ortsteil as separate values. An
  exactly stated area is a hard filter; a hedged one only ranks. Emptying the
  paste field has to clear the kept HTML, or the next read silently ships the
  page pasted before. See `docs/research/immobilienscout24-zugang.md` § 4.
- **Read a listing by the German word and the value's unit, not by the
  markup.** Three portals were recorded and they agree about nothing else:
  ImmoScout writes `<dt>Grundstücksfläche ca.</dt><dd>742  m²</dd>`,
  Kleinanzeigen `<li>Grundstücksfläche 1.025 m²</li>`, and ohne-makler.net
  `<span>5.366 m²</span><span>Grundstücksfläche</span>` — the **value before its
  label**, in Tailwind spans with no semantic hook, no `<dt>`, no `<th>`, no
  price meta tag and no coordinate anywhere. So `services/portal_fields.py`
  flattens the document to text (tags become `|`), finds the label and takes
  the nearest value of the right *shape* within 60 characters on either side.
  That reads all three, and it read the third one before anybody looked at it.
  Four guards, each measured: „370,62 €/m²" one element from the price is a
  rate, not the price; bare „Fläche" must not match „Wohnfläche", so the label
  boundary excludes German letters; „Die großzügige Grundstücksfläche bietet
  ideale Voraussetzungen" has no value near it and must contribute nothing; and
  the first postcode on an ImmoScout page sits in the analytics block, so the
  first postcode *followed by a name* wins. It is the floor under the
  portal-specific blocks, never above them — a structured field is a statement,
  this is a reading.
- **ohne-makler's JSON-LD describes the portal, not the listing.** Its
  `Organization` node carries the company's own address in Reinbek,
  Schleswig-Holstein, 400 km from the Saxon plot on the page. So a schema.org
  address may only be read from a listing-ish node, never from whatever node
  comes first — the „600 m² in Brehna" lesson, one channel further along.
- **A Stadtteil is not a Gemarkung, and one BBOX request settles it.**
  `AlkisService.districts_around` asks `ave:KatasterBezirk` which districts meet
  a box around a point. Measured 09.09.2026: around Grünau-Siedlung it answers
  7 against Stadt Leipzig's 76, and with the listing's exact 742 m² those leave
  3 candidates where the Gemeinde alone leaves 24 — the right one, Lausen 8/a
  „Staffelsteinstraße 4", first. The seed is the **platform's own pin**, which
  the `Anchor` docstring used to rule out entirely: it is still never *the*
  container, but it may say which containers get asked. That is safe in one
  direction only, and that is what lets the radius be picked without a corpus —
  a box too small to hold the right district makes every count zero and the run
  reports nothing found, so a bad pin can produce no parcel but never a wrong
  one. `PIN_RADIUS_M = 1500`: measured against the pin sitting 6 235 m from the
  Lobstädt parcel, ±1500 m returns 8 districts with Lobstädt among them, ±3000 m
  returns 23, ±7000 m returns 69. Runs only when nothing else named a container,
  never outside Saxony, and the verdict can never be „bestätigt" off it.
  **On that same exposé it no longer runs**, and the note above was written
  before the reason existed: the coordinate sits next to `isFullAddress: false`,
  so it is the quarter's point and is refused outright, which leaves that
  listing „nicht eingrenzbar". Honest, and not fixable from the name — Grünau-
  Siedlung sits on Gemarkung Lausen and nothing in the directory says so. The
  pin path still earns its place where a portal states a complete address.
- **The location field is not one string, and its Ortsteil is in front of the
  postcode.** Five digits are the only fixed point in a German location line,
  and the three recorded portals put everything else in three orders around
  them: „Burghausen-Rückmarsdorf, 04178 Leipzig, Sachsen" (ImmoScout),
  „04668 Sachsen – Grimma" (Kleinanzeigen), „Maschinenhausstraße, 01587 Riesa,
  Sachsen" (ohne-makler). Behind the digits stands the Gemeinde — unless that
  slot holds the Bundesland, and then it is behind the dash; in front of them
  stands the Ortsteil, which is ImmoScout's own `obj_regio4`. Reading the line
  as one opaque `ort` Indiz threw both away, and that is what cost advert
  170438443 (09.09.2026) its answer: with no district anchor the run fell back
  on Stadt Leipzig, where 112 589 Flurstücke hold **31** of exactly 866 m². The
  Ortsteil holds two. A street stands in that slot on one portal in three, so
  the head only counts when the Gemarkungsverzeichnis knows it.
- **A compound Ortsteil is two Gemarkungen, and the Gemeinde is what makes
  splitting it safe.** „Burghausen-Rückmarsdorf" is no Gemarkung; Burghausen
  145507 and Rückmarsdorf 145614 both are, both in Stadt Leipzig, and the plot
  may be in either — so the answer is *two* candidates, not one. Reading half
  the name as the whole location is how „Baugrund in Rückmarsdorf" in the title
  confirmed Rückmarsdorf 250/38 („ohne Lage", Weg) while Burghausen 286/a — the
  same 866 m², official Lagebezeichnung „Neuburghausener Weg", which the
  listing names, and „Sport-, Freizeit- und Erholungsfläche", which is the
  „bisher als Wochenend- bzw. Gartengrundstück genutzt" the listing describes —
  was never looked at. A part is a *derived* reading, so it only stands when its
  own Gemeinde is the one the listing names: „Grünau-Siedlung" splits to a
  Gemarkung Grünau that exists twice, in Großolbersdorf and Langenweißbach,
  80 km away, and that guard drops both. Measured against all **63** Leipzig
  Ortsteile: every compound resolves to its own Gemarkungen, every namesake
  elsewhere is dropped, „Lausen-Grünau" keeps Lausen and drops Grünau in one
  breath, and the five „Grünau-…" names contribute nothing rather than anchoring
  wrong. Costs no request.
- **A Gemeinde named next to a district is not a rival reading of it — but only
  then.** „in Leipzig – Stadtteil Burghausen-Rückmarsdorf" names both levels in
  one sentence, and Gemarkung Leipzig holds parcels of every size, so leaving it
  as an anchor is a third of the 31. Demoting it needs the condition, though:
  „Sachsen - Bad Lausick" names one place that is a Gemarkung *and* a Gemeinde,
  and demoting it there leaves the run with no anchor at all — which is the
  advert whose area has no match in Gemarkung Bad Lausick and exactly one in the
  municipality. So the rule is: demote the Gemeinde's name only while some
  *other* district is on the table.
- **The two halves of one Ortsteil are a set, not a contradiction.** Once
  „Burghausen-Rückmarsdorf" resolved to both its Gemarkungen the run put them
  up as a `Konflikt` — „Welche Gemarkung ist gemeint? Die Angaben widersprechen
  sich" — above a listing in which nothing contradicts. It is the same rule
  that already covers „790/11 sowie 238/3": readings that came out of **one**
  source are a set, and only readings from *different* sources are rival. So
  `Indiz.teil_von` carries the compound a district was taken out of, it survives
  the dedupe onto whichever reading is kept (a title's „in Rückmarsdorf" is the
  same statement as the prose's „Stadtteil Burghausen-Rückmarsdorf"), and
  `halves_of_one_ortsteil` suppresses the question. Both are searched, both
  survivors are in the answer, and the user picks a *parcel* — which is the
  choice that was worth offering all along.
- **The deterministic reader must not be gated on „`<`" being in the paste.**
  It was, and that was true of the parsers when the gate was written: they read
  markup. `portal_fields` goes by the German word and the value's unit, so it
  reads a *rendered* page as well as a marked-up one — „Grundstücksfläche ca.
  866 m²" and „199.000 €" are right there in the text. The gate answered every
  field empty for the plainest paste there is, and „Gelesene Werte" showed
  nothing on exactly the input the reader was written for.
- **A portal's own field names are worth more than any prose, and they are one
  block to maintain.** Measured on a recorded ImmoScout exposé (167953918,
  09.09.2026, `fixtures/inserat-immoscout.html`): the page carries
  `obj_lotArea: "742"`, `obj_purchasePrice: "275000"`, `geo_bln: "sachsen"`,
  `geo_krs: "leipzig"` and `obj_regio4: "Grünau_Siedlung"` as separate values —
  twice, in `keyValues` and in `<s24-ad-targeting>` — while its prose only says
  „eine Fläche von ca. 742 m²". Exact is a hard filter, hedged only ranks. The
  clipboard shape gets the same numbers as rendered text out of the portal's
  `is24qa-*` elements, and neither the Bundesland nor the pictures. So the
  per-portal patterns live in one delimited block in `services/portals.py` with
  the recording named, and a rename shows up as a failing test naming the field.
  Two traps in those patterns: every `is24qa-*` value has a `…-label` sibling
  carrying the same class plus a suffix and it comes *first*, so a pattern
  without `(?![-\w])` reads „Grundstücksfläche ca. 742 m²"; and the agent's
  „Wir machen die obigen Angaben nach bestem Wissen …" sits in the same element
  class as the description, so short blocks are dropped.
- **A portal coordinate next to `isFullAddress: false` must not be taken at
  all.** ImmoScout's `exposeMap` gives 51.30595, 12.27605 for this advert with
  `showFullAddress: false`: that is the *quarter's* point. The app resolves the
  parcel under a coordinate, so a quarter centroid is not a coarse locator but
  a wrong one — the same shape as the 6 235 m Kleinanzeigen pin. Read it only
  when the portal says the address is complete.
- **„Grünau-Siedlung" is not a Gemarkung, and the two called „Grünau" are 80 km
  away.** Measured 09.09.2026 against `gemarkungen-sachsen.json`: Gemarkung
  Grünau exists exactly twice, in Großolbersdorf and Langenweißbach, both in
  the Erzgebirge or Vogtland — so reading a Leipzig Stadtteil as a Gemarkung
  anchors the search 80 km wrong, and `collect_indicia` is right to refuse a
  bare mention. Stadt Leipzig has 76 Gemarkungen and Grünau sits on the old
  villages beneath it: Schönau, Lausen, Groß- and Kleinmiltitz, Knauthain. What
  the portal's structured fields do give is the **Gemeinde**, and that is
  enough: Stadt Leipzig holds 112 589 Flurstücke, `flaeche = 742` leaves **24**
  — a scoreable set — and adding Gemarkung Lausen leaves exactly **one**,
  Flurstück 8/a, 742 m², „Staffelsteinstraße 4", `Wohnbaufläche;742`. So a
  Stadtteil is worth resolving to the Gemarkungen under it; it is never one.
- **An optional dependency has to be optional in one place only.** The backend
  image installed `.[poi]` and never `tesseract-ocr`, so every Compose
  deployment reported „keine Bilderkennung eingerichtet“ while the code, the
  tests and the README all said it was wired up. `apt-get install tesseract-ocr
  tesseract-ocr-deu` plus `.[poi,ocr]`; the German data is not optional either,
  because the patterns key on the words around the number.
- **`adv_alkis_flurstuecke` carries `MaxScaleDenominator: 2000` and answers 200
  with a transparent PNG above it — and a scale limit is *steerable*.** Same
  shape as the ArcGIS `minScale` trap, different service. At 256 px the layer
  draws only from z19 (z18 is 1:2133 and empty). But the denominator is
  `(bbox_width / image_width) / 0,00028`, so asking for a **larger image over
  the same box** puts it back under the limit: z18 at 512 px, z17 at 768,
  z16 at 1280, z15 at 2304 — all measured against the live service, all
  drawing. The proxy scales the render back to a tile, so the browser still
  gets 10–39 kB. It runs out at z14, which would need 4368 px against the
  service's `MaxWidth` of **4000**; that is where the floor comes from.
  Every style behaves the same — it is the scale, not `STYLES` — and
  `STYLES=default` is rejected outright while `STYLES=` (empty) is accepted.
  Sibling layers are unaffected: `tatsaechliche_nutzung` and `gebaeude` draw at
  z18 in the same request. The service's own overlay style is **`Gelb`**, whose
  abstract says „keine Flaechen sondern nur Konturen“ — that is the one for an
  orthophoto. Streets and their names come from the WebAtlas as
  `Verkehr,Beschriftung`, transparent at every zoom from 13 to 19.
- **A raster style needs no network, and that is what starts a MapLibre
  instance where none can run.** The vector style is a `fetch`, so in jsdom it
  failed and the map was never built; the orthophoto ground is assembled
  locally, so `new MapLibreMap` ran, half-initialised without WebGL, and only
  said so on the way out — `remove()` throwing inside the library, reported as
  an unhandled rejection against whichever test file happened to be running.
  `canRenderMap()` is asked first now. It is not only a test concern: a browser
  with WebGL switched off did the same thing.
- **Sorting the clues by confidence destroys the one thing the list is for.**
  `ParcelSearch` re-sorted `indicia` on every event and kept the phase lines in
  a separate `<ol>` underneath, so afterwards nobody could tell what came
  first — which is what makes a run checkable at all. There is one numbered
  `Verlauf` now, in arrival order, and every row that stands for something on
  the map flies to it. The geometry is resolved when a row is *clicked*, not
  when it was recorded: a clue arrives several steps before the outline it
  names is fetched, so anything captured at the time is null for exactly the
  rows worth clicking.
- **A palette tuned for paper disappears on a photograph.** The evidence layers
  were 0,1 fills and 1,2 px hairlines — right over the app's near-white ground,
  invisible over an orthophoto, which is mostly green, grey and dark with detail
  everywhere. Over the photo every fill is stronger and every line carries the
  halo the site plan has always drawn under its own. The ground is a prop, so
  the paint follows it rather than being chosen once.
- **The frame comes before the narration.** The clues play one at a time so a
  run can be followed, and the district outlines were emitted *after* all of
  them — so for the first seconds the map sat on the whole of Saxony while the
  list already named a village, which reads as a map that is broken rather than
  one that is waiting. Emitting the same request one step earlier fixes it, and
  costs nothing: the wash under a confirmed parcel is that same document, so
  `fetch_outline` reuses it instead of asking again.
- **Reading the images is the rescue, not the route.** OCR was phase 0, so
  every run began with up to a few seconds an image before the first thing the
  map could draw — for a channel most listings do not have. The text and the
  metadata are what the search runs on; the images are read afterwards, and
  only when the text did not confirm. When they then name a parcel, the
  narrowing runs again rather than the reading being noted and ignored.
- **A locator is what a stored plot needs, not what the search needs.** The
  paste path refused any page without an address, a coordinate or a parcel
  number — which is every ImmoScout page, the one portal that field exists for.
  The search reads a district, a street and an area out of prose; the gate now
  asks `collect_indicia` whether the text yields an *anchor* (a Gemarkung, a
  Gemeinde, a place or a parcel number). An area alone is not one — every
  parcel in Saxony of that size is not a candidate set — so „Baugrundstück
  688 m²“ still gets the message that says what to paste instead.
- **A test that mocks by call order breaks when the run gets better.** Six
  tests pinned an ordered `side_effect` list, so fetching the district outline
  one step earlier failed them all — for a change that made the product better
  and cost no extra request. `_cadastre()` exists for exactly this and its
  docstring says so; the ordered lists are gone.
- **The reader garbles the label, not only the digits.** On the Borna advert's
  Liegenschaftskarte Tesseract returns „**Fiurstück**: 107/60“ — the l as an i —
  so the one number on the sheet that means anything was thrown away, while
  „Gemarkung Thräna“ beside it was read correctly. The pattern tolerates
  `[li1|]` in that position now; the rest of the word carries the specificity,
  so it costs no precision (`Fust`, `First`, `Furst`, „die Flur ist 12 ha“ all
  still match nothing). The district needs no such help: it comes back as
  „Thrana“ and the directory folds diacritics.
- **A plot can be advertised that has no Flurstück at all.** „eine noch zu
  vermessende Teilfläche“ (advert 2418686487, 748,50 m²): the parcel will be cut
  out at sale, so no existing parcel has that area. Used as a hard filter the
  figure finds *some other* parcel of that size and confirms it — the one kind
  of wrong answer this search exists to refuse. `describes_part_area` reads the
  sentence, `AreaStatement.exact` goes false, and `verdict()` can never say
  „bestätigt“: the listing itself is the contradiction, and no filter can catch
  it. The answer names the parcel it will be cut *from* — here 107/60 in
  Gemarkung Thräna, 2 994 m², in two requests — and says why that is not the
  plot. The area mismatch is then not reported as an objection either; it is the
  situation, and „bitte die Flurstücksnummer prüfen“ would send someone looking
  for a mistake that is not there.
- **A Beleg read off a picture is the least checkable evidence in the search.**
  So an Indiz from an image carries `bild_url` and the conflict block shows the
  sheet: the choice is made against the document rather than against a
  transcription of it. A Geoportal print carries dozens of neighbouring numbers
  on the map body — only the labelled one in the title block is ever read, which
  is what keeps that safe.
- **A jump that only moves the camera does not say what it jumped to.** The
  map arrived somewhere and left the reader to guess which of the things on it
  was the reason. The entry being followed is marked (`gezeigt`, drawn over
  everything) and its row is marked in the list, so the two refer to each other.
- **jsdom does not submit a form from a dispatched click.** Wrapping the
  wizard's first step in a `<form>` (so Enter submits, as it does everywhere
  else) broke two tests that click the button, with no change to the component's
  logic. The button's click carries `.prevent` so a real browser does not submit
  twice, and the two paths — `trigger("click")` on the button, `trigger("submit")`
  on the form — are tested separately.
- **The listing states its Bundesland, and that is the cheapest hard filter
  there is.** Kleinanzeigen's location field is „PLZ Bundesland – Ort" on all
  six recorded adverts. ALKIS is state-specific, so a plot in Sachsen-Anhalt has
  no Saxon Flurstück — and its village usually *does* have a Saxon namesake:
  „600 m² in Brehna" (advert 3381469778) resolved to Flurstück 50 in Gemarkung
  Roitzsch near Wurzen, 100 km away and exactly 600 m². Eleven requests spent on
  an answer no request could have got right. Read the state first, before
  anything is asked: „Sachsen-Anhalt" contains „Sachsen", so match whole words
  and longest first. Out of *prose* the same name may only **explain** a run
  that already found nothing — „gute Anbindung nach Sachsen-Anhalt" is a
  sentence about a Saxon plot.
- **A bare „in" before a place is the same trap as „Anbindung an".**
  „weiterführende Schulen in Roitzsch oder Bitterfeld sind in 10 bis 15
  Autominuten" put the plot in Roitzsch. An amenity is somewhere to go, never
  where the thing is; the guard is the noun in front of the preposition, the
  way `an` has been guarded since Leipzig.
- **A choice that changes nothing is worse than no choice.** The conflict block
  offered „Brehna" — a name in no Saxon Gemarkung, so it contributed no anchor
  and picking it re-ran the search to the same answer, which reads as a button
  that does not work. An option has to be something the cadastre can be asked
  about; the Indiz stays in the Verlauf, struck through, with the reason.
- **Two reasons for one outcome contradict each other.** `verdictSentence` said
  „die Angaben reichen nicht aus, um die Lage einzugrenzen" directly above the
  run explaining that the details are complete and point at another state. A
  template may only supply a reason when the run supplied none.
- **A longer camera flight alone is not a calmer camera.** The flight is capped
  at `queuePace * 1.6`, so doubling `FLIGHT_MS` without doubling `BUDGET_MS` and
  `MIN_DWELL_MS` just interrupts the same movement more often. All three move
  together — and the flight is derived from `pace` (what a *camera* step is
  getting) rather than from `step` (what the step being played is getting), or a
  run of 250 ms lines in between would shrink the next flight to the floor.
  `BUDGET_MS` is a divisor, not a total: it is recomputed against the remaining
  backlog each step, so the pace grows back towards two seconds as the queue
  empties. The screenshot script's wait after the verdict has to outlast the
  whole of it, or it photographs a map still in flight.
- **`page.fill` with 171 kB of markup takes ~27 s** — Playwright inserts it
  through the input pipeline — which sits just under the 30 s default and fails
  whenever the machine is busy. Measured identical before and after the change
  that appeared to break it. Dispatch a `paste` with a `DataTransfer` instead:
  instant, and it is the action the product is actually built around.
## Docker builds in the Claude Code cloud sandbox

`docker compose build` fails here out of the box, and it is not a pip
problem: the sandbox re-terminates outbound HTTPS through its own CA
(`/root/.ccr/README.md`), which a fresh build container does not trust.
`pip install` fails against pypi.org with "self-signed certificate in
certificate chain"; `npm ci` fails the same way against the npm registry,
just with different error text ("Exit handler never called!"). `--network
host` alone does not fix it — both registries are already reachable without
going through the local proxy, so this is a trust problem, not a routing one.

Trusting the sandbox's CA bundle from inside the container fixes both:
`PIP_CERT` / `REQUESTS_CA_BUNDLE` / `SSL_CERT_FILE` for pip, and
`NODE_EXTRA_CA_CERTS` for npm — Node ships its own CA list and ignores the
system trust store exactly the way pip does.

`scripts/docker-build-sandbox.sh build|up` applies that in a temporary,
`sed`-patched copy of each Dockerfile only — via BuildKit's
`--build-context`, so neither committed Dockerfile is touched — and falls
back to a plain `docker compose` call wherever `/root/.ccr/ca-bundle.crt`
does not exist, i.e. everywhere but here. On a real machine with direct
internet access, `docker compose up --build` needs none of this and the
script is a no-op passthrough.

## Commands

```bash
# backend
python3 -m venv backend/.venv
backend/.venv/bin/pip install -e "backend[dev]"
backend/.venv/bin/python -m pytest backend/tests -q
backend/.venv/bin/python -m uvicorn app.main:app --reload --app-dir backend

# the whole thing in containers: nginx serves the build and proxies /api,
# so there is one origin and no CORS. No database is involved.
docker compose up --build      # http://localhost:8080

# same thing, but in the Claude Code cloud sandbox -- see "Docker builds in
# the Claude Code cloud sandbox" for why a plain `docker compose build` fails
# there.
scripts/docker-build-sandbox.sh up -d

# routing on this machine instead of Transitous -- opt-in, off by default.
# fetch-data.sh pulls the OSM extract and the DELFI GTFS; the first start
# imports for ~3.5 min into the motis-graph volume, after that it is seconds.
./motis/fetch-data.sh
docker compose -f docker-compose.yml -f docker-compose.local-routing.yml up --build

# reading a listing's attached cadastral extract -- optional, and the search
# says so in /api/health when it is missing
apt-get install -y tesseract-ocr tesseract-ocr-deu
backend/.venv/bin/pip install -e "backend[ocr]"

# frontend — needs Node >= 22.19: jsdom 30 pulls in undici 8, and on Node 20
# vitest dies before loading a test with `markAsUncloneable is not a function`.
cd frontend && npm install
npm run dev            # proxies /api to 127.0.0.1:8000
npm run test           # vitest
npm run build

# screenshots of every view, light and dark
node scripts/screenshots.mjs

# the bookmarklet's handover, across two real origins (needs the build and :8000)
node scripts/bookmarklet.mjs
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

- `pytest`: 563 passed, 8 skipped — one of those needs pyosmium, which only the
  index builder wants; the other seven need Tesseract and skip without it.
- `vitest`: 560 passed — plus the integration file, excluded by `npm run test`
  and 8 passed / 2 skipped when a backend is up on :8000
- `scripts/bookmarklet.mjs`: the handover across two origins, against the built
  app and a backend on :8000. It asserts the coordinate, which is the field
  that separates a handed-over document from a pasted one.
- `scripts/screenshots.mjs`: 62 images plus two print PDFs. It fails on console
  errors, on horizontal overflow, and if not a single vector tile arrived. It
  also drives the live geocoder, which is slow often enough to blow the 60 s
  wait on the destinations step — two runs failed there and the third passed
  with nothing changed. Re-run once before going looking for the bug.
  The `suche-*` images run a **real** search against ALKIS, so they need a
  backend on :8000 like every other picture here; without one the step reports
  "die Suche kam zu keinem Ergebnis" rather than passing quietly. The three
  `assistent-werte-*` images paste a saved advert
  (`backend/tests/fixtures/inserat-kleinanzeigen.html`) through
  `/api/listings/extract`, which needs the same backend and no LLM key, and
  then open the „Gelesene Werte" fold inside the search step — that list is no
  longer a step of its own.
