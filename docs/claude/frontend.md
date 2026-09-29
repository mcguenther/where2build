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

- **An absolutely positioned dropdown inside a `.panel` is clipped — and one in
  the flow makes the page jump.** `.panel` carries `overflow: hidden` to keep
  map canvases off its rounded corners, so the search suggestions were first
  cut after the first row, then moved into the flow, where they pushed
  everything below the field down with every hit that arrived. The user ruled
  that out on 26.09.2026: nothing may move while someone types. The list and
  the reading menu now open in the browser's top layer (`popover="manual"`,
  placed with fixed coordinates by `lib/floating.js`), which no ancestor clips —
  the start page's reception has an `overflow: hidden` of its own. Without the
  Popover API (jsdom) they fall back to absolute placement, and `QueryBox` sets
  `overflow: visible` on itself for that case. What *stays* after an action — the
  coordinate's map preview — may push the page, because it follows a paste or
  an Enter somebody did on purpose.
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

- **Text becomes a block only on an unmistakable signal.** `QueryBox` turns a
  paste, a chosen suggestion, an Enter, or a space after a number at the very
  start into a pill — never a space after a word, never an exact match while
  typing. Measured in `backend/data/gemarkungen-sachsen.json`: 2 165 of the
  5 339 Saxon Gemarkung names contain a space, and „Altstadt" is the start of
  „Altstadt Borna", „Altstadt I" and „Altstadt II"; „Mölkau" can still become
  „Mölkauer Straße". A number without a denominator waits for the letter after
  the space: „3044 85/1" is a district key and a number.

- **A value that goes "" → "x" → "" inside one flush never reaches a child's
  watcher.** `QueryBox` cut the number off the text in the same watcher run in
  which the text arrived, so `PlotSearch` saw its `modelValue` stay "" and kept
  showing „85/1 " — and Backspace, which only acts on an empty field, did
  nothing. The replacement text is set a tick later.

- **A scoped `:global(a) b` compiles to just `a`.** The coordinate preview's
  first dark-mode rule was written that way and inverted the whole page instead
  of the map tiles; only a screenshot showed it.

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

- **A backdrop anchored to the window loses whatever it anchors off-centre.**
  The reception's plot was part of a drawing centred on the window, 664 px
  left of the middle: cut off below 1330 px of width, gone below 940, never
  seen on a phone. And the drawing hung from the top while the type was
  centred vertically, so a taller window pushed the headline away from it.
  The drawing now hangs off `.hero__headline` and is sized in its `em`, so it
  shrinks with the type and the room beside a 20ch headline always holds it;
  below 700 px it moves into the top right corner, cut off by the upper edge.
  The plot is a second svg above the veil, so the fabric can fade around it
  without the one parcel that matters fading too.

- **Chromium drops a `radial-gradient` whose size mixes a percentage with a
  length** -- `min(34%, 470px)`, `calc(30% + 10px)` -- and with it the whole
  `background` declaration. Nothing in the console. The reception's veil was
  written that way and never painted on a desktop, which is why the fabric ran
  straight through the headline. `min(40vw, 580px)` is accepted; test a
  gradient with `el.style.backgroundImage = …` and read it back, an empty
  string means it was rejected.

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

- **Zwei Seiten, die dasselbe zeigen, driften — und die schlechtere gewinnt
  nicht.** Die Dienstliste stand in „Übersicht" *und* in „Betrieb", und die im
  Betrieb war die bessere (Karten statt Zeilen, deutsche Namen, Endpunkt).
  Die Übersicht fasst jetzt zusammen („11 von 15 eingerichtet; ohne: …") und
  verlinkt dorthin, wo die Einzelheiten stehen. Was eine erste Seite sonst
  trägt: eine Zeile je Sache, die Aufmerksamkeit braucht, mit dem Weg dorthin,
  wo sich etwas daran tun lässt — und die Zahlen, für die sonst jemand
  navigieren müsste.

- **Eine Antwort ohne das erwartete Feld nimmt die ganze Seite mit.**
  `held.caches.length` und `day.summe.fehler` werfen beim Rendern, sobald die
  Antwort ein Objekt *ohne* dieses Feld ist — und ein geworfenes Render bricht
  nicht diese eine Zeile ab, sondern alles, was danach käme: die Seite zeigte
  „Wird geladen …" in Kästen, deren Daten längst da waren. `Array.isArray(…)
  ? … : []` in einem computed kostet eine Zeile und hält die Seite zusammen.
  Aufgefallen an einer Test-Attrappe, die für unbekannte Pfade `{}` liefert —
  also genau an dem Fall, den ein echter Server nach einem Teil-Ausfall auch
  liefert.

- **Two keys of the same name in one `watch` object are one watcher, and the
  last one wins without a word.** `PlotView` had `"plot.id"()` twice — one
  that routed the next plot, one that fetched its neighbour outlines — and an
  object literal keeps only the second. Stepping with „Nächstes ›" therefore
  never routed the plot it arrived at; nothing threw, the route cards simply
  stayed empty until somebody pressed „Neu berechnen". Found while adding a
  third thing that has to happen on the same change. One watcher now does all
  of it; a linter's `no-dupe-keys` would have said so on day one.

- **The location record is a section of the plot page, not a page.** It
  repeated the parcel and the land value from the plot page next to it, and
  its one own figure — the note that the Bodenrichtwert applies to a notional
  reference plot — now sits in the Preis panel. `/grundstueck/:id/standort`
  redirects to `#standort`, and `scrollBehavior` follows a hash. The checks
  open with the gravest group that has a member (`zu beachten`, else `ohne
  Befund`, else `offen`) and fold the rest behind a button that says how many;
  the folded groups are rendered and only hidden, so the print sheet opens
  them all. A second `SitePlan` on the page is fine — its SVG ids carry a
  per-instance `uid` — but its ground and noise switches have their own names
  (`aria-label="Hintergrund der Standortkarte"`), because the screenshot run
  finds buttons by name and Playwright refuses a name that matches twice.

- **A panel that is only needed for the odd plot starts folded, and its
  summary line still answers the first question.** Form and Abstandsflächen
  are `details.fold` with the verdict or the depths beside the title
  („rechteckig · 1 : 1,42", „3,0 m ringsum"), so a closed one is not a blank.
  `print.css` opens them through `::details-content`, like the soil wording.

- **The plot and the house laid on it are two tabs, and the plan decides
  which one shows.** The column beside the plan held the plot's figures, and
  the building body stood below it at the same size as the setback table, so
  what the cadastre says and what the user tried out read as one thing. Now
  „Grundstück" and „Bebauung" share the column; a *click* on the footprint
  opens „Bebauung" and draws the selection frame, a click anywhere else on the
  plan goes back. `SitePlan` emits `select` ("house" or null) from the release,
  within the same 4 px that separate a pick from a pan, so a drag moves the
  house and switches nothing. The panes are `v-show`, never `v-if`: the tests
  and the half-typed edge lengths need the fields to exist, and `print.css`
  dissolves the column (`display: contents`) to print both — the plot's
  figures beside the plan, the building body under it. That grid needs
  `grid-template-rows: auto 1fr`, or the first row grows to the height of the
  column that spans both and the building body prints a hand's width below
  the drawing. The column is 336 px, and a `details.fold` head with a summary
  *and* a chip overflows it; the setback fold lost its § 6 chip to the
  caveat inside it, which is where the paragraph is explained.

- **An explanation is read once; a state is read every time.** The plot page
  carried seventeen paragraphs that said how something is meant rather than
  what is true of this plot, and they were set as open footnotes under every
  panel. They now sit in `HintFold` — one fold per panel, at its end, with a
  count so a closed one still says there is something — and `print.css` opens
  every one of them. What changes with the plot stays open: „Ohne Kaufpreis
  …", „0,4 · H = 2,56 m", the estimated aspect ratio. A hint that only makes
  sense on screen (dragging, the map's controls) carries `no-print` inside
  the fold.

- **The price verdict has three stages, and they come from the band the panel
  already draws.** `priceStage` in `metrics.js` reads `PRICE_BAND` (± 15 %):
  below is green, above is red, inside is neutral „im Rahmen" — the chip in
  the panel head, the marker on the band and the coloured line all read the
  same stage, so they cannot disagree with the drawing they sit on. Plain
  green and red for any sign would call 4 % a bargain. The line says the
  magnitude without a sign: „−4,2 % unter" said the direction twice.
  `deviationClass`, which the plot cards and the comparison use, reads the
  same stage now; it used an older scale (± 5 % good, amber up to 15 %), and a
  plot 21 % under the land value was amber on its card and green on its page.
  The source chips in a panel head („ALKIS", „BORIS") read as a verdict next
  to one: „BORIS" beside „unter Richtwert" looked like a second finding. Both
  panels name their source as the first line of their hint fold instead. The
  shared view, the wizard and the parcel search still carry an „ALKIS" chip.

- **The asking price is edited on the plot page, in the price panel.** The
  wizard was the only place to enter it, yet the panel told people it „kann
  oben eingetragen werden" — there was nothing above to type into, and a plot
  picked by parcel number never passes that field. The field is text with
  `inputmode="decimal"`, not `type="number"`: „279.000 €" is how a listing
  writes it, and `parseGermanNumber` reads it (dots in groups of three are
  thousands). An empty field removes the price; 0 and non-numbers keep the
  field open with a sentence, because a stored 0 would read as a free plot.

- **Enter in the search field only ever took a row, so most inputs went
  nowhere.** `PlotSearch` handled Enter itself and took the highlighted row or
  a sole one; a link, a pasted page, a bare number with its district unfolded,
  or an address the geocoder answered with five rows (it does, even with the
  postcode) all ignored the key, and the start page needed the mouse. Enter now
  takes a highlighted row and otherwise hands on to the wrapper (`submit`),
  which does exactly what its button does. Two details carry it: Enter pressed
  before the lookup has answered waits for it instead of taking whatever row
  the reading alone produced — „Lessingweg 44" typed fast was otherwise asked
  for as a Gemarkung — and rows of *two* readings, parcel beside address, are
  highlighted rather than taken, so the ambiguity is still put to the user.
  The same rule reaches the other single-purpose forms (house type link and
  manual entry, a destination's address, the read values, the plot's name,
  price and note). Not the second confirmation of the red button, and not
  „Trotzdem anlegen": overriding a doubt takes a click on the words that say so.

- **A copied link carries markup, and the markup made it a page.** `QueryBox`
  lit „Eingefügte Anzeige“ whenever the paste event had `text/html` — and a
  link copied out of Firefox, a mail or a chat has `<a href="…">` there. So the
  Kleinanzeigen link went to `/api/listings/extract` as `{text: …}`, the server
  read the address itself as the advert, found nothing and answered **503**
  with the „weder eine Adresse noch eine Koordinate …“ sentence (559 bytes in
  the nginx log, which is how it was told apart from the two other 503s), while
  the same URL sent as `{url: …}` answered 200. Reported on 24.09.2026 from a
  local compose stack; the container fetched the page fine. A text that reads
  as a bare link now stays a link whatever markup came with it — a whole
  pasted page never reads as one, so no real paste loses its markup.
