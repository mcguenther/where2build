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

- **The surroundings map framed the plot, not the surroundings, whenever the
  nearby answer was slower than the map style.** `frame()` ran once, on
  `load`; with the stops not yet there it fitted the bare parcel at zoom 17,
  and the `located` watcher only drew markers. Lessingweg 44 showed one of
  seven stops. The watcher reframes now, unless the user has already panned or
  zoomed (a `movestart` with an `originalEvent`). Reproduced by delaying
  `/api/nearby` 5 s in Playwright: 1 of 7 markers in view before, 7 of 7 after.
  A warm backend cache hides it — the answer then beats the style.
