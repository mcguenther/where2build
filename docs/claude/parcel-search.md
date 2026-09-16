# Finding the parcel a listing is selling

`backend/app/search/` asks the cadastre a series of narrow questions and
answers NDJSON so the map can grow while it runs. What is here is what those
questions have to be, and the readings of German prose that make them work --
almost all of it measured against real adverts.

The rule the whole thing rests on: hard filters decide, weights only order. See
also "Decisions that are settled" in `CLAUDE.md`.

---

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

- **A location field with no postcode carries two levels in one slot, and the
  directory can tell them apart.** „Leipzig - Knautkleeberg-Knauthain": the
  half in front of the dash is usually the federal state, but a city writes its
  own name there. „Sachsen - Schönwölkau-Hohenroda": the state is in front and
  the municipality behind it has its Ortsteil hyphenated on. Both are read only
  when the directory confirms them — the head as a municipality it knows, the
  tail's right half as a district inside that municipality — which is what
  keeps „Sandersdorf-Brehna" in one piece. Fixing this is what ended the one
  false confirmation in the corpus: advert 3508042470 now searches all three
  districts and answers „mehrdeutig" instead of confirming a parcel its own
  location field contradicts.

- **„Bestätigt" means nothing contradicts, not that one candidate is left.**
  The shape is the contradiction the area cannot see: two parcels of 577 m²
  can be 14 x 40 m and 22 x 27, and only one is the plot with the 14 m
  frontage. `read_dimensions` takes the measures out of the text where a word
  says what was measured, and over sixteen adverts it finds exactly the two
  that state any — „einen Abstand von 15 m" out of a Bebauungsplan is not one.
  Two guards, both measured: a **frontage on its own may not object** (advert
  3375124391 states 26 m and its correct parcel sits in a 39,8 x 71,5 m
  rectangle, because the plot is a wedge), and a parcel whose rectangle is more
  than **1,3 times its own area** is not rectangular enough to be checked
  against one at all.

- **248 districts cannot be found under their own name.** The directory files
  2 105 of its 5 339 entries with a Flur suffix — „Kitzen Flur 1" to „Kitzen
  Flur 11" — and `_district_matches` compares names for equality, which it has
  to: a substring search turns „Grimma" into a match for „Grimmaischer".
  Behind those entries stand 295 base names and **248 have no plain twin**.
  Measured 16.09.2026 over six freshly recorded adverts: Pehritzsch (7 Flure),
  Hohenroda (3), Krostitz (8), Doberschütz (5), Sprotta (6), Jesewitz (6) and
  Eilenburg (**48**) are all unreachable by name, so five of those six runs
  reported „die Anzeige nennt keine Gemarkung", fell back on the platform's pin
  with 12 to 14 districts, and cost **24 to 40 requests** each where the right
  anchor costs two. The fix is measured and cheap: match on the base name and
  send the Flur keys as one `fes:Or` — „Kitzen" then resolves to 2 062 parcels
  in a single request, and with the advert's exact area exactly one remains.

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

- **A search map must never frame tighter than its own doubt.** The first
  Indizienkarte zoomed to whatever had just been found and thereby hid the other
  parcels that still matched the stated area. The camera is derived from the
  *live candidate set* plus the new indicium, with 35 % slack and a 120 m
  minimum half-width, so even a confirmed parcel is never shown without its
  neighbours. And a layer whose extent dwarfs the frame stops informing and
  starts tinting: the district wash and the street buffer fade out on the way in.

- **A dependency parser reads the relation a regular expression cannot — on a
  sentence.** spaCy's German model takes „Thräna ist … ein Ortsteil der
  Kreisstadt Borna" apart correctly, and four rules cover every phrasing in the
  corpus, the distance-to-place binding included. On the real text it falls
  apart: a markdown heading without a full stop becomes the subject of the next
  sentence, and the bullet lists bind „ca. 300 m" to Leipzig instead of Kitzen,
  four times in one advert. The cause is format, not language, so the first
  step is splitting a listing into headings, paragraphs, bullets and „Label:
  Wert" lines — which helps the regular expressions and the model just as much.
  Measured 15.09.2026, with what it would cost: `docs/research/nlp-spacy.md`.

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

- **Two seconds per Indiz is the pace for evidence arriving live, and the wrong
  pace for a finished run.** Most runs complete in a few seconds while sixteen
  events at two seconds is half a minute of watching. `StepQueue` therefore
  spends a fixed budget over whatever is queued (≥ 240 ms per step), and the
  camera flight follows that pace — a 900 ms flight started every 240 ms is the
  twitch the queue exists to prevent. `prefers-reduced-motion` skips it all.

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

- **The price is in the markup three times and never needs a model.**
  `<meta itemprop="price">`, the JSON-LD `offers.price` and `#viewad-price` —
  the first hit answered all four measured adverts (60 000 / 165 000 / 80 000 /
  195 000 €). It had been left to the LLM, so the field stayed empty on exactly
  the pages that have a known adapter.

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
