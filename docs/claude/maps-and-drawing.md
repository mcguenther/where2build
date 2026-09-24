# Maps, the site plan, and the geometry it draws

`SitePlan` is an SVG the app draws itself, sitting on a MapLibre instance that
supplies the ground. All geometry runs in the browser. Most of what follows is
about the seam between those two -- a drawing and a map that have to agree on
where north is and how many metres a pixel covers -- and about the geometry
routines under it.

---

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

- **MapLibre zoom is defined against 512-pixel tiles.** The widely quoted
  156543.034 metres-per-pixel constant assumes 256, and putting it in the
  camera renders the basemap at exactly twice the drawing's scale.

- **Cap the grid, do not fix the step.** A district address resolves to a field:
  its axis-aligned box is 1583 x 198 m with 159 boundary points, which is two
  million cells at 0.4 m. The step now grows to hold the cell count, which stays
  safe because the inward bias is derived from the step — a coarser grid gives a
  smaller envelope, never a more permissive one.
  Use the **minimum rotated rectangle**, not the bounding box, to describe a
  shape: that same parcel is a 1594 x 30 m ribbon running diagonally, and the
  axis-aligned box hides exactly the elongation you are looking for.

- **`SitePlan` draws no streets at all.** What makes its map look right is a
  MapLibre instance underneath carrying OpenFreeMap's `liberty` vector style,
  while the SVG holds its own parcel fill to `fill-opacity: .42`. The two map
  tokens `--w2b-map-street-surface` and `--w2b-map-existing` are declared and
  never used. Any new map component should take the same backdrop rather than
  hand-drawing streets — and copy the two techniques that do the work: a halo
  stroke under every line (6 px `--w2b-map-halo` beneath 2,2 px
  `--w2b-map-boundary`) and `paint-order: stroke fill` with a 3,4 px halo on
  every label.

- **A chosen parcel is drawn with no fill, and the drawing above it swallowed
  the click.** The picker's polygons sat *under* the plot's own fill, so taking a
  parcel back out never worked: the press landed on the plot, not on the parcel.
  The group is drawn above the plot now (visually identical — the chosen ones
  are transparent, the others do not overlap it) and carries
  `pointer-events: all`, which hit-tests an unpainted area.

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

- **A raster style needs no network, and that is what starts a MapLibre
  instance where none can run.** The vector style is a `fetch`, so in jsdom it
  failed and the map was never built; the orthophoto ground is assembled
  locally, so `new MapLibreMap` ran, half-initialised without WebGL, and only
  said so on the way out — `remove()` throwing inside the library, reported as
  an unhandled rejection against whichever test file happened to be running.
  `canRenderMap()` is asked first now. It is not only a test concern: a browser
  with WebGL switched off did the same thing.

- **„Straßenparallel" put the street on top for half the plots.**
  `alignmentToEdge` normalises to (-90°, 90°] so a *house* is never turned more
  than a quarter; used for the drawing, it made the street edge horizontal and
  left whether the street sat above or below to the winding of the cadastral
  ring. The fixture plot `plot-concave` came out exactly 180° wrong and the old
  test passed, because it compared against the same function.
  `streetDownRotation` turns the edge's own direction to east on a
  counter-clockwise ring (the interior is on its left, so above) and returns
  (-180°, 180°]. Keep `alignmentToEdge` for the footprint.

- **Fit the turned box, not the north-up one.** The drawing rotates about the
  frame's centre, so the fit has to measure the outline *as turned*
  (`turnedBox`): framing the unturned box let a long plot at 45° run off a
  thumbnail once it lay flat along its street, and gave a diamond the frame of
  a square half again as wide.

- **A thumbnail's ground is `<image>` tiles, and one component draws it.**
  `PlotThumbnail` is the only small plan — cards and the comparison both use
  it — and it takes the `umgebung` layer (the web atlas without its lettering)
  through `SitePlan`'s `tileGround` prop, the same way route cards do, so a list
  of twenty plots starts no WebGL context. Measured over Liebertwolkwitz at z18:
  the ALKIS render draws parcel numbers and boundary points at full size, and
  the plain web atlas writes street names, which stand on their heads once the
  thumbnail is turned by more than a quarter. The tile cover is asked for the
  frame's diagonal on every side, since a turned drawing shows ground from past
  the unturned frame's corners. Local metres and Web Mercator share one scale
  factor around the anchor, so the placement is linear.

- **A thumbnail's tiles are in the backend's cache before anything draws
  them.** Measured 24.09.2026: the GeoSN web atlas takes 1–1,4 s per tile and
  caches nothing of its own (the same GetMap twice, both slow); our disk cache
  answers in 4 ms. So the delay was only ever the *first* sight of a plot — and
  that is every new plot, because the wizard's preview is another ground at
  another zoom and warms none of them. `App.vue` watches `wantedThumbnailTiles`
  (every card at `CARD_FRAME`, the ticked plots at the comparison's shared
  scale) and names new tiles to `POST /api/tiles/warm`, which answers 202 in
  ~12 ms and fetches the missing ones afterwards, four at a time. The browser
  downloads nothing for it and its HTTP cache is not part of the plan: a first
  attempt warmed with `new Image()`, and it was rejected for exactly that. The
  warm-up pays one tile of the map budget per tile it sends *outward*, and a
  warm-up over the budget is refused whole. A watch, not a call in `addPlot`:
  the street front settles after the plot is stored and turns the drawing, and
  ticking a plot changes the scale all compared drawings share. Tiles are
  claimed before the first `await`, so the list's warm-up and the comparison's
  a moment later do not both fetch one — claiming inside the task let both
  through, and a test caught it. The layout lives in `lib/tileGround.js` so
  drawing and warm-up name the same tiles; the test compares against the
  mounted thumbnails *with positions*, because the cover is the frame's
  diagonal on every side and a centre metres off still asks for the same tiles
  — a URL-only check passed with the rotation deleted. Measured after: two new
  plots, then the list and the comparison opened in a *fresh* browser with no
  HTTP cache — 21 of 21 tiles `HIT`, slowest 118 ms. Storing a stitched ground
  with the plot was weighed and left: ~8 KB each, but the disk cache is shared
  by everyone for 30 days and already answers in milliseconds.

- **The street side was the longest edge, and that was wrong on seven of eight
  real plots.** Measured 23.09.2026 on every parcel fixture: only the 1 594 m
  strip at the Tauchaer Straße fronts its street with its longest side. A deep
  plot fronts it with its narrow end (Lessingweg 44: 13,5 m, not 47,9 m), and
  Kirchstraße 4 with a short side — so the turned thumbnail showed some other
  road at the bottom, correctly turned to the wrong edge. The side is now read
  off the cadastre (`lib/streetFront.js`): a street is a parcel of its own in
  ALKIS, so the front is the boundary the plot shares with traffic land, and the
  street of the plot's own address wins at a corner. Plots stored before this
  carry `streetFront` unset and are asked once on load; `null` means asked and
  nothing borders a street, and the guess stays.

- **A navigable plan in the middle of a long page takes the page's scroll.**
  `onWheel` calls `preventDefault` on every wheel event over a navigable plan,
  and `.site-plan` carries `touch-action: none` — right for the plan somebody
  drags a house on, a trap for the small location map halfway down the plot
  page: the cursor passes over it on the way down and the page stops. That map
  is `cooperative`: the wheel zooms only with Ctrl or ⌘ (a trackpad pinch
  arrives as exactly that), and `touch-action: pan-y` lets a vertical swipe
  scroll the page while a sideways drag still pans.

- **`data-map-ready` is per map, and a page can have three.** The plot page
  carries the plan, the location map and the surroundings map, so a bare
  `[data-map-ready="true"]` returns for whichever finished first.
  `mapSettled()` in the screenshot run takes a scope for that reason.

- **The surroundings map framed the plot, not the surroundings, whenever the
  nearby answer was slower than the map style.** `frame()` ran once, on
  `load`; with the stops not yet there it fitted the bare parcel at zoom 17,
  and the `located` watcher only drew markers. Lessingweg 44 showed one of
  seven stops. The watcher reframes now, unless the user has already panned or
  zoomed (a `movestart` with an `originalEvent`). Reproduced by delaying
  `/api/nearby` 5 s in Playwright: 1 of 7 markers in view before, 7 of 7 after.
  A warm backend cache hides it — the answer then beats the style.

- **The search map's cadastre was yellow, from zoom 15, and it buried the
  answer.** The ground used the oversampled `flurstuecke` layer in the
  service's „Gelb“ style, so over a district every hedge carried a yellow line
  and an ambiguous run's two candidates were two outlines among a few hundred —
  in a colour nothing else in the app uses. The ground now takes the site
  plan's own `liegenschaftskarte` (default style, black line work) from
  `PARCEL_OUTLINE_MIN_ZOOM = 17`; the numbers get legible at 18. Measured over
  Mölkau on 23.09.2026: at 17 a plot is some forty pixels wide and its number
  three pixels high. The backend's `flurstuecke` layer is no longer asked for.

- **`focusOn` cannot close in on one candidate.** It frames the whole candidate
  set around the evidence, which is right for a clue and does nothing for a
  candidate — the set already contains it. The table's row click and „Zeigen"
  go through `focusCandidate`, which frames that parcel with ~55 m around it.
  The row numbers are drawn on the map as DOM markers, not a symbol layer: the
  aerial ground is raster only and carries no glyphs. And a marker is
  positioned through its own inline `transform`, so a CSS `transform` on it
  (a scale for „shown") throws it off its parcel — the highlight grows the
  badge's box instead.

- **Two badges on one pixel read as one candidate.** At district scale 134/m
  and 97/4 in Großbothen, 500 m apart, landed on the same spot and the „1" sat
  under the „2" — the map said one, the table two. Badges that would come
  within `MERGE_DISTANCE_PX` of each other are merged into one labelled with
  what it holds („1, 2", „1–5", „1, 2, 4–7"; `lib/badges.js`), regrouped once a
  frame while zooming, and a click on a merged badge zooms in until they part.

- **Every frame the search map fitted ignored the HUD.** From 1000 px up the
  verdict and the Verlauf float over the map's right 40 %, and `fitBounds`
  with a plain 36 px padding centred the answer under them: after zooming in
  on „1, 2", candidate 2 was behind the panel. `ParcelSearch` measures how much
  of the map the HUD covers and `EvidenceMap.padding()` adds it on the right.
  Measured rather than derived from the breakpoint, because whether the HUD
  floats is the stylesheet's decision. jsdom has no `ResizeObserver`, so the
  measurement is skipped there — without that guard thirty tests failed on
  mount.

- **An ambiguous result is cards, and each card's picture is not a map.** The
  point of the picture is recognition — a roof or a hedge from the listing's
  photographs — so it is fixed: `lib/candidateSketch.js` frames the parcel with
  at least 60 m either side and draws the orthophoto and, from zoom 17, the
  Liegenschaftskarte as `<image>` tiles in an SVG, the way the route cards do.
  A MapLibre instance per card would run into the WebGL context limit at a
  dozen candidates, and the maps past it go blank without a word. Twelve cards
  are drawn before „Alle zeigen"; each is some six tiles of each layer from
  the authority's WMS. The candidate's outline is drawn wider (3,6 over an 8 px
  halo) than on the big map: among the cadastre's own lines at this size, a
  contour of the same weight is one boundary more.

- **„Is the map on screen" has to mean most of it.** The cards sit right under
  the map, so after a click the map's lower edge was usually in view and the
  check passed — while the pan happened in a strip at the top of the screen.
  It scrolls unless 60 % of the map is visible.
