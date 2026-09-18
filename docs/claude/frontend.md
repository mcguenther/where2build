# The Vue app, its styles and its forms

Options API, no `<script setup>`. Most of these are things that failed
silently: a style that reached one view, a computed nobody defined, a layout
that collapsed at 390 px. None of them threw.

---

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

- **A Vue prop is a reactive proxy, and a proxy charges per property read.**
  The clearance field reads two numbers per grid cell per boundary segment —
  hundreds of millions on a real parcel — and measured **23.5x slower** through
  a proxy than on plain objects: 26 seconds against one. `buildableArea` and
  `findPlacement` copy their input once at the door. Any new hot loop over
  geometry must do the same; the symptom is a frozen tab with no error.

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

- **A split selection is marked, not refused.** Parcels that do not touch union
  into a MultiPolygon, which one outline cannot hold — but refusing the click
  closes the only way back: to drop the middle parcel of three you have to pass
  through a split plot. So the drawn outline is the piece around the parcel the
  selection started from (`outerRing` takes `near`, else the largest part), the
  ones outside it are drawn in red, and "Anlegen und öffnen" is disabled with the
  reason until they are gone.

- **A placeholder has to have the shape of what is coming.** The route
  placeholder was a row of thin bars and what arrived was a card as tall as its
  map, so the page jumped by that height when the answer landed. It lives in
  `RouteCards` now, behind a `busy` prop, next to the layout it imitates — and
  the same pulse (`.skeleton*` in `base.css`, since a scoped style reaches
  exactly one component) serves the check list, the route cards and the two
  routed columns of the surroundings table.

- **A watched computed is evaluated whether or not the template reached it.**
  `PlotView`'s computeds all read `this.plot`, and a `v-if="plot"` had kept them
  from ever seeing `null`. Adding one watcher was enough to crash the page whose
  whole job is to explain that the id in the URL names no plot here.

- **"Something is selected" is not a signal that anybody selected anything.**
  `addPlot` puts every new plot into `state.data.selection`, so opening the
  overview's comparison mode when the selection is non-empty means opening it
  always — the state that button exists to get out of.

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

- **The clipboard carries `text/html` next to `text/plain`, and a `<textarea>`
  shows only the second.** `Strg+A, Strg+C` on a portal page therefore has
  everything the extraction wants — meta tags, JSON-LD, price, pictures — and
  the paste field keeps it (`@paste`, capped at 400 000 characters) and sends
  that instead. So the paste path needs no `LLM_API_KEY`: a model is asked only
  when no address, no coordinate and no parcel number could be read at all.
  Emptying the field has to clear the kept HTML, or the next read silently
  ships the page pasted before.

- **A hover rule on the base class fills every variant, including the quiet
  one.** `.btn:hover:not(:disabled)` paints Loden, and `.btn--quiet:hover`
  only reset the text and the border, so every still button in the app went
  solid green under the pointer with dark ink on it. It survived because a
  screenshot never hovers; it showed up the moment a browser run happened to
  leave the pointer on one. A variant that changes the resting background has
  to name the hover background too.

- **A field that is emptied has to empty what it filled.** `QueryBox` unfolds
  the district beside a bare parcel number and copies the number into it —
  and kept it there when the search field was cleared. Type „85/1", clear,
  type „204", and the cadastre was asked for 85/1 while the field read 204:
  a real parcel, a wrong answer, and nothing on screen to show the
  difference. Clearing now resets the number, the district and the insisted
  reading together.

- **A button passed into another component's slot is not a flex child of your
  own box.** `QueryBox` puts its button into `PlotSearch`'s field through a
  slot, so the container query that was supposed to drop it below the input at
  narrow widths wrapped the wrong element: the button stayed beside the input
  and squeezed it to zero width, with the placeholder simply gone. What has to
  wrap is the row the button actually sits in — `:deep(.search__field)`.

- **"Has a plot" is not "has been used", and the difference is what greets
  somebody.** The start page keyed its whole reception on `plots.length`, so
  after adding plots and destinations and then deleting the plots, the section
  bar stood there with every counter at zero -- furniture around an empty app
  instead of a greeting. `isFresh()` reads all three lists *and* the account,
  because a destination means the app is in use and an account is a stand of
  its own even while it is empty. The bar is dropped only on the start page:
  from anywhere else the sections are the way back, and hiding them there is a
  dead end.

- **A header that steps back must not take the sign-in with it.** The reduced
  header keeps the brand, the palette and the way into an account, because the
  sections are the only part of it that leads nowhere in a fresh state. And
  where no provider is configured the header could show nothing at all while
  the page said nothing either -- so a sign-in that simply does not exist in
  this deployment looked exactly like one that is broken. The start page now
  names both cases in words: the link where there is a provider, the reason
  where there is not. Verified by walking a real browser through five states
  against a throwaway provider (fresh, signed in, signed out again, one
  destination, everything deleted).

- **A sentence that names a place nobody can reach from there is a dead end.**
  The storage note said "unter „Daten“" as plain text, which was fine while the
  header always carried the sections and wrong the moment it did not. It is a
  `RouterLink` now. The same note also still claimed "der Serverspeicher ist
  noch nicht gebaut" long after it shipped -- stale copy that reports a
  finished feature as missing, which is worse than saying nothing. It reads
  `state.sync.active` instead of asserting anything.

- **On a phone a radial veil cannot rescue a backdrop, because the text fills
  the box in both directions.** The reception's quiet core is a
  `radial-gradient` at 34% of the width, which works on a desktop where the
  field sits in the middle of a wide drawing. At 390 px the headline and the
  sentence take nearly the whole width and the field, the three lines and the
  account note take the whole height: widened enough to clear the type it
  wipes the drawing out entirely, and anywhere it fades the fabric runs
  straight through a line of text — the route crossed one, which is where a
  backdrop stops being one. So the *drawing* steps back there
  (`.hero__art svg{ opacity: .42 }`) and the core only softens the middle.
  The opacity goes on the svg, never on `.hero__art`: the veil is that
  element's own `::after` and would fade with it.

- **`handoff` and `handover` are one letter apart and different things.**
  `lib/handoff.js` is what the start page leaves behind for the wizard — an
  input already typed somewhere else. The *handover* is a whole page arriving
  from another tab because somebody clicked the bookmarklet on a portal. They
  meet in `WizardView`, so both names are spelled out where they are declared;
  do not shorten either.
- **Two folds with the same class, one step apart, make a wait match the wrong
  one.** The entry step grew a `details.gelesen` for the bookmarklet while the
  search step has had one for the read values. `scripts/bookmarklet.mjs` waits
  for the fold to know the page was read — and would have matched the entry
  step's immediately, then waited out its timeout on a list one step away. The
  bookmarklet's carries `gelesen--lesezeichen` and the script asks for
  `:not(.gelesen--lesezeichen)`; a test asserts the entry step has no plain
  one.


- **A full-bleed section inside `.container` bleeds to 1360 px, not to the
  window.** The reception's negative margins only took back the container's own
  padding, so on anything wider than about 1440 px the drawing sat as a panel
  in the middle of bare `--w2b-paper` — while the header and the footer, which
  are outside the container, went edge to edge. Nothing failed; it simply read
  as a card on the one screen that is supposed to read as a place. Reaching the
  window needs `width: 100vw; margin-inline: calc(50% - 50vw)`, and `100vw`
  counts the classic scrollbar the page does not have, so `.shell` carries
  `overflow-x: clip` to swallow those few pixels. **`clip`, never `hidden`:**
  `hidden` makes the shell a scroll container and every `position: sticky`
  inside it — the site plan, the two maps, the parcel list's header — silently
  stops sticking.

- **The backdrop's box decides how big a parcel looks, and `slice` is what
  couples them.** The drawing is a lattice rotated by the street's gradient in
  a `0 0 3840 1200` box with `xMidYMin slice`, so the scale is
  `max(width/3840, 1300/1200)`: below 4160 px the height wins, a parcel is the
  same size on every monitor, and a wider window shows more fabric instead of a
  magnified piece of it. Two things follow from the box being centred. The plot
  keeps a fixed offset from the middle, which is a fixed offset on screen — and
  the quiet core in the middle must be a fixed size too, because it exists to
  back an 860 px column of type and to stop short of that plot. Left as a bare
  `34%` it grew with the window until it washed the plot out.

- **Widening the box moves the street up, because the street is not level.**
  Its gradient is about −0.105, so translating the plot 1200 units right along
  it lifts it 126 units out of the frame; the fabric has to come down by the
  same amount for the composition to survive. And the reception is
  `clamp(600px, 82vh, 940px)` tall while the drawing is anchored to its top, so
  a tall window moves the type down over a street that stayed put: the route
  ran through the sentence under the headline. The street now crosses where the
  search panel is, which is opaque at every height the reception takes.

- **Two rows of parcels between two streets cannot be drawn independently.**
  The first version gave the row on the kerb a depth from one set and the row
  behind it a depth from another, which is how the drawing it was read out of
  had done it — and in a 1360 px window the mismatch mostly fell outside the
  frame. Full width it is everywhere: the block is 469 units kerb to kerb, the
  two depths summed to anything between 420 and 550, so the rows overlapped by
  up to 80 units in one place and left a strip of bare paper in the next. The
  block is now cut into superblocks along the street first; a superblock has
  one rear boundary at one depth, and each row subdivides that same run with
  widths of its own. Both rows then share their outer edges and the boundary
  between them, and nothing else can happen. The generator asserts it — it
  walks every rectangle a block emits and fails the build on a cell covered
  twice or not at all — because neither a 40-unit overlap nor a 40-unit gap
  announces itself in a backdrop; it just looks slightly wrong.

- **Eine Seite, die beim Aufbau `state.account` liest, liest sie zu früh.**
  `AccountView.created()` rief `load()`, und `load()` steigt aus, solange
  niemand angemeldet ist — die Antwort auf „wer ist angemeldet" kommt aber erst
  danach, weil `App.created()` sie erst holt. Über den Kopf angeklickt
  funktionierte die Seite deshalb immer, beim **direkten** Aufruf von `/konto`
  blieb der Kasten „Gespeichert ist" leer: kein Fehler, keine Meldung, nichts.
  Aufgefallen ist es erst, als die Seite ein eigenes Bild im Screenshot-Lauf
  bekam — ein Zustand, den kein Test traf, weil jeder Test den Zustand vorher
  setzt. Ein `watch` auf `state.account.angemeldet` zieht den Stand nach; das
  deckt zugleich die Anmeldung im zweiten Fenster ab.
  Preis davon: eine Seite, die auf einen globalen Zustand hört, wirkt in
  vitest über das Testende hinaus — die Instanz bleibt montiert und lädt beim
  nächsten Zustandswechsel nach, was dort als unerwarteter `fetch` auftaucht.
  `open()` in `account-view.test.js` baut die vorige Seite deshalb ab.

- **Zwei Dinge in der Oberfläche „Kennung" zu nennen, kostet genau dann etwas,
  wenn jemand eines davon abtippt.** Die Kontoseite zeigte als „Kennung" das
  *Subject des Anbieters*, während `/api/auth/me`, das Anfragebudget und
  `ADMIN_ACCOUNTS` mit „Kennung" den Kontoschlüssel meinen. Wer sich zum
  Verwalter machen wollte, trug den falschen Wert ein und bekam keinen Zugang
  und keine Erklärung. Jetzt heißen sie „Kennung beim Anbieter" und „Kennung
  dieses Kontos", beide stehen da, und darunter steht, welche der Betreiber
  braucht.
