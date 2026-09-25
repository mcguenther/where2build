# The services this app talks to

Everything here was measured against the live service, not read off a
specification. `docs/research/` holds the long form; this file holds the parts
that cost time when they were not known.

The services are the Saxon cadastre (ALKIS-WFS), the land values (BORIS), the
GeoSN map layers, the sixteen Länder's orthophoto WMS and the BKG's web map and
Sentinel-2 mosaic, the Saxon environmental server (LUIS, ArcGIS REST), the
federal air-quality API (UBA), routing (MOTIS/Transitous), OpenStreetMap by way
of Overpass or a local extract, the listing portals, and the extraction model.

---

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

- **`ave:Nutzung` is where the built-up area of a town comes from, and a POST
  can carry a BBOX and a filter at once.** Measured 16.09.2026: a 2 km box
  around Grimma holds 486 `Wohnbaufläche` polygons, 674 kB in 1.8 s; union them
  with a 25 m closing and the largest connected piece is the town, 1.91 km²,
  2.9 x 2.3 km. That is what „6 km bis Grimma" is measured *from* when the
  reading is "to the edge": 5.32 km from Flurstück 790/11, against 6.25 km to
  its middle — and the advert's „ca. 6 km" sits between them. Three parameters,
  all measured: **Wohnbaufläche alone** (adding mixed and industrial use drags
  the outline along the works and moves the near edge to 3.16 km, outside the
  advert's own figure), a **25 m closing** (without one the union is 484
  fragments; at 50 m neighbouring hamlets start merging and the edge jumps
  0.7 km) and a **2 km radius** (Grimma 2.9 x 2.3 km, Borna 3.0 x 2.6 km, Bad
  Lausick 3.2 x 2.3 km). `AlkisService.built_up_area`. The response puts its
  features in the *default* namespace, so `nutzart` arrives without the `ave:`
  prefix the filter needs — which is why it has its own parser.

- **Streets are parcels, and `tntxt` says so — filter at the service.** Each
  entry of `ave:tntxt` is „Art;Fläche", several joined by „|": the Kirchstraße in
  Liebertwolkwitz is „Straßenverkehr;1316", a works on a kerb „Industrie- und
  Gewerbefläche …;2164|Straßenverkehr;0.00" — so the *dominant* use decides.
  Measured 23.09.2026: the unfiltered box over the Tauchaer Straße strip came
  back at exactly 200 parcels and said nothing about the rest; a POST with
  `fes:BBOX` and `fes:Or` of `PropertyIsLike` on `tntxt` returns 235 traffic
  parcels in the same box. `AlkisService.streets_around`, `/api/parcels/streets`.

- **That query needs a count of its own, and the largest piece rather than the
  one under the seed.** Two things the note above got right by measuring
  outside the service and wrong inside it, both found on 16.09.2026 when the
  band was built on top of it. The service-wide `max_features` of 200
  **truncates** the land-use query and nothing says so: 200 of Grimma's 431
  polygons close into a 0.35 km² fragment instead of the town, and the near
  edge then reads 5.4 km — a plausible number out of a tenth of the place.
  Hence `BUILT_UP_MAX_FEATURES = 1500`. And seeded from Grimma's market square,
  the piece *covering* the seed is a 0.48 km² island of housing inside a centre
  the cadastre records as mixed use, while the town is the 1.65 km² belt around
  it; the island reads 4.6–5.1 km from Flurstück 790/11 and the belt 5.3–6.0,
  and it is the belt „ca. 6 km" is about. So a named reference asks for
  `largest=True`. Taking *every* piece in the box instead pulls the near edge
  to 2.9 km, because the box also holds the hamlets — the same failure as the
  stop cloud below.

- **The cadastral district is not the town.** Measured on the same parcel:
  Gemarkung Grimma is 21.50 km² of which most is field, and its boundary
  reaches to within **1.22 km** of a plot that is 5 km from the town. Neither
  is the stop cloud: 65 stops carry „Grimma" in their name and span 5.89 km,
  because the municipality's villages are named after it. Both were candidates
  for "the edge of the town" and both are refuted.

- **immowelt.de answers server-side fetches with 403,** and it is DataDome at
  the CloudFront edge: `x-datadome: protected`, a 771-byte JavaScript challenge
  („Please enable JS and disable any ad blocker"), `x-cache:
  LambdaGeneratedResponse from cloudfront`. Measured 15.09.2026 with the
  project agent and with a full browser header set — identical. `robots.txt`
  allows `/expose/` and names ClaudeBot explicitly; the refusal happens before
  the server. Same shape as immobilienscout24.de, different vendor, same way
  in: the user's own browser, so the bookmarklet.

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

- **Rank by walking time, never air distance.** Detour ratios reach 2.88x, and
  the nearest thing by air can be unwalkable altogether.

- **The surroundings service ranks *within* a category, not across them.** Its
  answer is category by category, so the panel's own order was the category
  list's — a bus stop one minute away sat below a tram stop half an hour away.
  `NearbyPanel.found` sorts by walking time and puts what has no walk last.

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

- **The POI index's filename is a default, not a claim.** `poi-sachsen.json`
  built from a Leipzig-region BBBike box is still called that; the extract it
  really came from is in the file's own `quelle`, and its `datenstand` is the
  extract's timestamp. Read those. Scope itself is a command-line argument
  (`--url`, `--out`) — see README, "Reach of the POI index", and
  `docs/research/poi.md` § 12.

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

- **"No noise value" is not "quiet" — not even with mapped roads nearby.**
  The state survey is `Hauptverkehrsstraßen` (layer 3/4/5), the tram in
  Leipzig, Dresden and Chemnitz, and the two airports; side streets are in none
  of it. Road-noise polygons within 300 m number 109 in Leipzig and 94 in
  Dresden, but 0 in Geithain, and the Bahnhofstraße in Naunhof has none within
  300 m and 30 within 2 km — which the first version read as "below the lowest
  band, 45 dB(A)" and showed in green. That was wrong twice: the plot's own
  street is not surveyed, and `Lden4549` exists only around Zwickau (4 266
  polygons inside 12.42–12.57 E, 50.65–50.80 N); everywhere else the lowest
  band is 50–54. So a plot in no band is `note`, "keine Lärmdaten", mapped
  surroundings or not, and the location map greys out and says so. The
  `Kartierungsgebiet` layer cannot serve as a mask either: it is a polyline of
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
  `Lden5054`. The 45–49 band is Zwickau's alone (see above), so it is read
  when a plot sits in it and never used to promise a floor anywhere else. The
  map key shows the *drawn* bands from 50, saying so. The six colours come from
  the renderer, not from taste.

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

- **ALKIS delivers counter-clockwise rings, and ArcGIS reads one as a *hole*.**
  A polygon that is nothing but a hole has no area to buffer, so every
  `distance` query on it answers `{"code": 400, "message": ""}` — an empty
  message that says nothing about why. Measured 05.09.2026: Flurstück 263/7
  (86 m², 5 points) failed that way on the borehole and protected-area layers at
  *every* radius from 50 m up, and the same ring reversed returned 114
  boreholes; Flurstück 204 (650 m²) answered either way, which is what kept it
  hidden. `services/luis.py` orients every ring clockwise before it goes out.

- **Every Land's DOP is an open WMS, and each answers *transparent* outside
  its own border — which is what makes one Germany-wide photograph a stack
  rather than a mosaic with cut lines.** Measured 25.09.2026: GetCapabilities
  of all sixteen read, a z17 tile over each capital drawn, a tile over Leipzig
  (Halle for Saxony) fully transparent, EPSG:3857 offered by all. The GeoSN
  layers do the same, so the beige around Saxony on the search map was never
  the service — it was our own `--w2b-map-ground` showing through. The
  Bund's own DOP (`sgx.geodatenzentrum.de/wms_dop`) answers 403 without an
  account; EOX's s2cloudless is sharp but CC BY-NC-SA from 2018 on; Esri's
  imagery wants an ArcGIS account. The BKG's `wms_sen2europe` (layer `rgb`)
  covers Europe at 10 m under the Copernicus notice, commercial use included,
  and is the ground: under every Land, and alone below z12. It has no data
  over open sea — the North Sea stays paper at z7.
  `services/tiles.py` asks only the Länder whose capabilities box touches a
  tile (one inland, two or three along a border) and lays them over one
  another, first at the bottom.
- **Thüringen paints opaque white past its border, in whole map sheets.** A
  scan of every z9 tile of every Land's box found it the only one of sixteen:
  up to 99 % of a tile, reaching well into Saxony and Saxony-Anhalt. On top of
  the stack it covered Saxony in white rectangles; `white_outside` puts it at
  the bottom, where each neighbour's own survey covers the white.
- **The Länder's services each have one trap of their own.** Bremen's
  top layer „DOP Luftbilder Land Bremen" draws a black-and-white historic
  flight — the current survey is `dop10_2025_HB`. Hamburg's is a time series
  (`TIME`, default 2024) whose Fees name closed satellite licences for some
  years, so the year is pinned. Mecklenburg-Vorpommern stamps „© GeoBasis-DE/M-V"
  into every tile. Niedersachsen reset 9 of 64 connections under eight parallel
  requests. Berlin's certificate chains to „Telekom Security TLS RSA Root 2023",
  which certifi carries and this sandbox's system bundle does not — `curl`
  fails, the backend's httpx does not. And Thüringen's `th_dop20rgb` does not
  exist; the colour layer is the group `th_dop`.
- **One silent Land must not blank its neighbour's half of a border tile.** A
  failure drops that Land from the stack and the tile is served *uncached*, so
  the next request asks again; only a tile nothing could be drawn for is a 502.
- **A response header is Latin-1.** `X-Attribution` with „Länder" in it made
  Starlette's test client raise `UnicodeDecodeError` on every aerial tile. The
  header is ASCII; the full credit, per Land, is the map's own attribution.

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

- **Four providers, two wire formats — and the second one is not a variant of
  the first.** OpenRouter, OpenAI, Ollama and any other OpenAI-compatible host
  answer `POST /chat/completions`, take `Authorization: Bearer` and put the
  schema in `response_format`. Anthropic answers `POST /v1/messages`, takes
  `x-api-key` plus a dated `anthropic-version` header, puts the schema in
  `output_config.format`, **requires** `max_tokens`, and returns `content` as a
  list of blocks rather than one message string — so `content[0]` reads
  whichever block came first, and a thinking block can be that one. It gets its
  own adapter in `services/llm.py`, never a translation layer: a shim that
  pretends one API is the other is exactly the shape that answers wrongly but
  successfully the first time either side changes.

- **A refusal is HTTP 200 with no text.** `stop_reason: "refusal"` and an empty
  or text-free `content`. Read as „leere Antwort" it is true and useless; the
  client says „hat die Anfrage abgelehnt" instead.

- **The fetch tool is per provider, and two of the four have none.** OpenRouter
  has `openrouter:web_fetch` with its `parameters` block; Anthropic has
  `web_fetch_20260209` (dated types are that API's own versioning — an older
  model wants `web_fetch_20250910` and answers 400 to the newer one) declared
  flat on the tool. OpenAI's endpoint, a local Ollama and an unknown compatible
  host have none, and `can_fetch_pages` says so *before* spending a request —
  the paste field is this app's own way in anyway, and it is what the two
  blocked portals need regardless. Neither provider reports a failed fetch as
  an HTTP error: OpenRouter says so in `usage.server_tool_use_details`,
  Anthropic by whether a `web_fetch_tool_result` block is in the answer at all.

- **`localhost:11434` carries the word „ollama" nowhere.** The provider is read
  off the endpoint when it is not named, and Ollama's own default URL is the
  one case where the host name gives nothing — the port is the only signal. A
  compose file that names the service `ollama` is caught by the name.

- **The OpenRouter default is `google/gemini-2.5-flash-lite`, and it was
  measured.** 18.09.2026, the 16 recorded adverts through the real extraction
  path — `_ask_the_model`, the Beleg gate, the divergence log — against six
  models with `structured_outputs` in OpenRouter's own model list. $0,28 for
  the whole exercise.

  | Modell | s/Inserat | $/Inserat | ok | einig | lücke | verworfen |
  |---|---|---|---|---|---|---|
  | `mistralai/mistral-small-24b` | 6,1 | 0,00015 | 16/16 | 26 | 19 | 8 |
  | `google/gemini-2.5-flash-lite` | 2,5 | 0,00054 | 16/16 | 25 | 22 | 6 |
  | `deepseek/deepseek-v4-flash` | 84 | 0,0011 | 16/16 | 26 | 39 | 3 |
  | `z-ai/glm-4.7-flash` | 67 | 0,0014 | 13/16 | 21 | 30 | 9 |
  | `openai/gpt-5-nano` | 53 | 0,0028 | 16/16 | 28 | 23 | 6 |
  | `qwen/qwen3.5-flash` | — | — | 1/16 | — | — | — |

  Three things the table is: **`qwen/qwen3.5-flash` is broken, not weak** — to a
  `response_format` request it answers `"-0.5749816320421072"`, a bare number,
  and fails 15 of 16. `z-ai/glm-4.7-flash` returns an empty or unparseable
  answer three times. And the three slow ones are *reasoning* models: deepseek
  emits 5 232 output tokens per advert, gpt-5-nano 6 546, glm 3 187, against
  Flash Lite's 706. That is where both the seconds and the dollars go, and
  `/api/listings/extract` is a call the assistant makes while somebody waits.

  What the table is not is a quality verdict. It says every working model got
  the hard case right — advert 2418686487 names only „Kaufpreis pro m²:
  92,00 €", and all five left `kaufpreis_eur` null while the pattern reader
  returns 92. `mistralai/mistral-small-24b` is the one that found no area
  there, which is why the cheapest option is not the default.

- **A local Ollama needs no key, and demanding one would make the only free
  provider the only one nobody can try.** `needs_key` is false there, and
  `configured` then asks for an endpoint instead.

- **The official `anthropic` SDK is deliberately not used.** Every outbound
  call in this backend goes through `upstream.request`, which owns the user
  agent, the timeout, the single retry, the content-type check and the German
  sentence a failure turns into. The SDK would be the one call that bypasses
  all of it. This is not an OpenAI shim — it is a first-class Messages adapter
  written against the documented wire shape.

- **A system prompt and a user message, not one blob.** The instructions are
  the same on every listing and the listing is not, so the stable half goes in
  the field both APIs have for it — a top-level `system` on Anthropic, a
  message with `role: "system"` on the OpenAI-compatible side. Sent as one
  string, as it was, every advert paid for the instructions again and neither
  API could cache the prefix.

- **The prompt names the vocabulary, because an enum conveys nothing.** The
  schema says `liegt_in` is an allowed value; it does not say that „die ca.
  6 km entfernte Kreisstadt Grimma" is the *opposite* of it. So
  `services/prompts.py` states the five levels and the four relations with the
  traps this project measured and got wrong first — the same ones the patterns
  in `search/indicia.py` carry, written as examples instead of as regular
  expressions: the relation standing behind the name (Thräna), the two levels
  in one sentence (Großbothen/Grimma), „Anbindung an Leipzig" as a statement
  about transport, „Schulen in Roitzsch" as a statement about schools.

- **The listing is fenced, and the fence is derived from the listing.** An
  advert is prose with headings, colons and its own „Hinweis:" lines, and it
  arrives after a hint of ours in the same message; without a delimiter the
  boundary between our sentences and the seller's is a matter of
  interpretation. `prompts.fence_for` returns a line of percent signs — four,
  and one more for as long as the text still contains it, which terminates
  because a text of *n* characters cannot contain a fence of *n* + 1. The rule
  („zwischen zwei Zeilen, die nur aus Prozentzeichen bestehen") goes in the
  system prompt, so it stays cacheable while the fence itself varies; the
  announcement sentence goes with the text. The fence is *added* around the
  text and never written into it: the Beleg gate checks against the raw
  listing, so a model that quotes a fence line fails that check rather than
  smuggling our own words in as evidence.

- **A strict schema rejects a wrong shape and states nothing.** Both wire
  formats carry the JSON schema — `response_format` there, `output_config.
  format` here — and Pydantic's dump of `InseratBefund` is names and types with
  no descriptions at all. It does not say that a value the advert lacks is
  `null` rather than an omitted key, that `wortlaut` keeps the rounding while
  `wert` drops the unit and the thousands separator, or that a denominator can
  be a letter. `RÜCKGABE` demands a JSON object and nothing else — no sentence
  before, none after, no code fences, no extra fields — and `prompts.SHAPE`
  states the rest.

- **The shape is a commented skeleton, not a worked example.** The first draft
  of that section carried a filled Befund from a real advert. It read well and
  it brings what a worked example always brings: values to copy, out of a
  listing that is not the one being read, in the one channel whose whole point
  is that it read *this* text. The skeleton has nothing to copy. Each field
  instead carries the one line the schema cannot: what it means, and when it is
  `null` — a price per square metre is not a purchase price, minutes are not
  kilometres, a parcel is never derived from an address. `test_prompts` strips
  the `//` lines, parses what is left, and holds its key set against
  `InseratBefund` plus the two enumerations against `Ortsebene` and
  `Ortsbeziehung`, so a field added to the schema — or invented in the prompt —
  fails a test rather than travelling unexplained.

  `vorbehalte` used to be asked for here and is gone. It was in the schema and
  in the prompt and read by nothing — „teilflaeche" should suppress the area's
  tolerance staircase and „mehrere-grundstuecke" should say so on the result,
  and until one of them is built, asking for it is tokens spent on a promise
  nobody keeps.

- **The model gets our material and never our findings.** The Saxon district
  register is data about Saxony and travels: the names in this text that the
  register actually carries, as a closed list, so a model can say which of them
  the advert means rather than invent one. What our own readers *concluded*
  does not travel, and that is the rule worth stating twice — a teacher shown
  the student's answers is not a teacher, and the divergence log in
  `services/lehrbuch.py` would then measure nothing at all. `_known_districts`
  therefore reads the register and never `collect_indicia`.

- **The fetch prompt is told about the page and not about the fields.** Naming
  a field there is an invitation to summarise instead of quote — and a
  summarised page is one whose every Beleg the gate then refuses.


## Transitous antwortet 403 ohne Kontakt im User-Agent

Gemessen 19.09.2026, und es sah aus wie eine Sperre: dreißig
`one-to-many`-Anfragen in Folge kamen als `403 Forbidden` zurück, dieselbe
Anfrage mit
`User-Agent: GrundstuecksCheckSachsen/0.1 (+https://github.com/…)` sofort mit
`200`. Die Nutzungsregeln des Dienstes verlangen genau das („Name of the
application / Version of the client / A way of contact"), und
`AppSettings.contact_user_agent` setzt es für jeden Aufruf aus der App. Ein
Skript, das für eine Messung schnell `urllib` nimmt, umgeht das — und belastet
dabei einen ehrenamtlich betriebenen Dienst.

## `one-to-many` kennt keine Tageszeit

Das war die offene Frage F4: wie stark streuen Fahrzeit und Verkehrsmodell
über den Tag. Die Antwort steht in der Schnittstellenbeschreibung
(`motis-project/motis`, `openapi.yaml`): die Operation nimmt `one`, `many`,
`mode`, `max`, `maxMatchingDistance` und die Fahrzeugmaße — **keinen
Zeitparameter**. Ein trotzdem mitgeschicktes `time` ändert die Antwort nicht;
verifiziert an zwei identischen Antworten für dieselbe Strecke. Es ist eine
Berechnung auf dem Straßennetz ohne Fahrplan und ohne Verkehrsmodell, also
kann die Tageszeit nicht streuen. Die geplante Messung zu drei Tageszeiten
wäre dreimal dieselbe Zahl gewesen.

Verwertbar war die andere Hälfte: **die Geschwindigkeiten selbst.** Drei
Strecken je Modus, aus den aufgezeichneten Flurstücken heraus — zu Fuß 70, 71,
70 m/min, Rad 245, 244, 243, Auto 908 und 924 (eine Strecke war für CAR nicht
routbar). Die Streuung zwischen Strecken ist winzig, die geratenen Konstanten
in `search/distance.py` lagen bei Fuß und Rad um 7 % und 2 % daneben und beim
Auto um **31 %**: 700 gegen 915 m/min. „ca. 7 min mit dem Auto" zog damit ein
Band um 4,9 km, wo der Dienst 6,4 km sagt.
