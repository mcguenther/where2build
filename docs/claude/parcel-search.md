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
  at `queueStep * 1.6`, so doubling `FLIGHT_MS` without doubling `BUDGET_MS` and
  `MIN_DWELL_MS` just interrupts the same movement more often. All three move
  together; sixteen clues now play over twelve seconds instead of six — and the
  screenshot script's wait after the verdict has to outlast the budget, or it
  photographs a map still in flight.
