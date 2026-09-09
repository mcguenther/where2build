# From a listing to the parcel — what the evidence actually supports

**Research date: 2026-09-01, re-verified and extended 2026-09-05.** Written in
English: this is developer documentation, only the user interface is German.

> **Legend**
> ✅ **VERIFIED LIVE** — a request was made from this shell, or a command run
> here, and its answer read. §§ 2-14 on 2026-09-01, all of them re-run on
> 2026-09-05 before the algorithm was built; § 15 is new on that date.
> ⚠️ **NOT VERIFIED** — stated as a design decision or an open question, not as
> a fact.

Everything below was measured against one real listing:
`kleinanzeigen.de/s-anzeige/…/3499632623-207-3929`, a 502 m² building plot in
Großbothen for 60 000 €. It resolves to **Flurstück 790/11, Gemarkung
Großbothen (144241)**, parcel key `144241___00790001100`, official area 502 m².

The four strategy documents built on this are in `docs/strategie/`.

---

## 1. Recommendation

**Do not start from the coordinate. Start from the district name in the body
text and the area in the attribute list.** Two requests, no model call, no
image recognition, and on this listing it is already unique.

Everything else — OCR, triangulation, a language model — is a fallback for
listings that do not carry both.

---

## 2. The pin is not noise, it is the wrong thing ✅

| | Gemarkung | Flurstück | Official area |
|---|---|---|---|
| `og:latitude/longitude` → ALKIS by point | Grimma | 2537 | 38 284 m² |
| Actually offered | Großbothen | 790/11 | 502 m² |

The pin sits at 51.244012 / 12.721705; the parcel centroid is at
51.189265 / 12.741058. **6 235 m apart.**

The offset is not Gaussian jitter around the plot — it is the geocode of the
*municipality* named in the platform's location field ("04668 Sachsen –
Grimma"). So there is no radius to search: a buffer large enough to contain the
truth contains most of the municipality. The body text names the
*Ortsteil* ("Großbothen, einem OT von Grimma"), and that is the usable
statement.

`plausibility.assess` already catches the failure — 38 284 / 502 is far past
`AREA_FACTOR_TOO_LARGE` — but catching it is not solving it.

---

## 3. `ave:flaeche` is filterable server-side ✅

Not previously used in the code. `PropertyIsEqualTo` and `PropertyIsBetween`
against `ave:flaeche` both work in an ad-hoc `fes:Filter`, so the area filter
costs nothing to apply and returns only the hit.

Measured with `resultType=hits`:

| Constraint | Parcels |
|---|---|
| `gmdschl = 14729160` (Stadt Grimma) | 32 544 |
| … + `flaeche = 502` | 15 |
| `gemaschl = 144241` (Gemarkung Großbothen) | 1 131 |
| … + `flaeche` between 477 and 527 (±5 %) | 25 |
| … + `flaeche` between 497 and 507 | 5 |
| … + `flaeche = 502` | **1** — and it is 790/11 |

Stadt Grimma has **66 Gemarkungen**. That is the whole value of reading the
Ortsteil out of the body text: it divides the search space by roughly the same
factor before any other filter runs.

The listing's stated area and the official one are **identical** here (502 =
502). That is what makes the exact filter legitimate; a "ca. 500 m²" would have
to widen into the band.

### Trap: the POST has to be right on the first try ✅

A `GetFeature` POST with `Content-Type: text/xml` and
`srsName=urn:ogc:def:crs:EPSG::4326` comes back as the generic Geoportal
HTML 400 page — the same page every other malformed request returns, with no
usable error. The same body with `Content-Type: application/xml` and
`EPSG::25833` returns 200. This matches what `services/alkis.py` already does;
it is recorded here because the failure mode gives no clue.

---

## 4. Tesseract reads the answer off the listing's own image ✅

One of the four images is a Geoportal Sachsen print at 1:500, headed
"Titel: Wiesenstraße - Großbothen / Untertitel: Flurstück 790/11", with the
sold parcel outlined in red.

`tesseract 5.3.4 -l deu --psm 6`, no preprocessing:

| Image | Kind | ms | Pattern hits |
|---|---|---|---|
| 743×1052 | Geoportal map print | 491 | `flurstueck=790/11`, `strasse=Wiesenstraße`, `strasse=Olbrichtplatz` |
| 1005×598 | Geoportal orthophoto + boundaries | 399 | none |
| 1600×1200 | site photograph | 4 085 | none |
| 1600×1200 | site photograph | 4 567 | none |

Two things follow:

* **OCR every image and filter by pattern; do not classify first.** The three
  images without a cadastral extract produced **zero** false parcel numbers, so
  the filter carries the safety and the classifier is not needed. Stop at the
  first `flurstueck` hit.
* **Only the title block is reliable.** The small in-map parcel labels come out
  as garbage (`388112`, `79212`, `79314`), and the orthophoto yields nothing at
  all. Anything that needs those labels is a job for a vision model, not for
  Tesseract.

### Trap: the authority signs with its own address ✅

`Olbrichtplatz` is the GeoSN's office address in the sheet's footer, not a
street near the plot. Drop the footer band, or reject street hits adjacent to
"Landesamt", "Dresden" or a phone number.

---

## 5. Frequency picks the wrong place ✅

Matching the 5 339 names in `backend/data/gemarkungen-sachsen.json` against the
description, whole words only:

```
Grimma      3x   144236
Großbothen  3x   144241
Höfgen      2x   144245, 146132
```

A tie — and "Grimma" is named three times precisely *because the plot is 6 km
away from it* ("in die ca. 6 km entfernte Kreisstadt Grimma"). Counting
mentions cannot work. What is needed is the **relation** between the plot and
each named place, which is why the extraction prompt asks for
`liegt_in / liegt_an / entfernt_von / erwaehnt` rather than for a location.

---

## 6. The street is a geometric filter, not an attribute one ✅

`ave:lagebeztxt` for 790/11 is **`"ohne Lage"`** — ALKIS carries no address for
this parcel, so a street name read off the image cannot be matched against the
cadastre directly.

OSM does have it: `Wiesenstraße` in Großbothen is three `highway=residential`
ways (22 + 6 + 6 nodes). Buffering them and intersecting:

| Buffer | Against | Survivors |
|---|---|---|
| 40 m | the 83 parcels in the local extract | 65 |
| 80 m | the 25 area-band candidates | **5**, 790/11 among them |

790/11 lies 3 m from the centre line. So the street filter is stronger than the
distance rings below (25 → 5 versus 25 → 8), and it costs one Overpass request.

---

## 7. Broker distances narrow, they do not decide ✅

The listing states "Fernbahnhof 1,6 km" and "Bus 0,3 km". Measured as air lines
from the parcel centroid:

| Claim | Actual | Deviation |
|---|---|---|
| Fernbahnhof 1,6 km | Bahnhof Großbothen at 1 415 m | −12 % |
| Bus 0,3 km | nearest served stop at 396 m | +32 % |

Both rings at ±35 % cut the 25 area candidates to **8** — and three of the
survivors (792/3, 793/4, 794/4) are 790/11's own neighbours. Triangulation on
these numbers converges on the right *block*, never on the right parcel.

Consequences for the scoring:

* Use a **trapezoid membership with a floor**, not a hard cut. A hard ±0 %
  cut removes every candidate including the true one, and nothing downstream
  can recover it.
* Do **not** multiply the memberships. Station, bus and school all sit in the
  village centre, so their errors are correlated; a product counts one error
  three times.
* Hard exclusion is legitimate only for official values — the existing
  `AREA_FACTOR_TOO_LARGE` rule. Claims stay soft.

⚠️ The weights proposed in `docs/strategie/suche-triangulation.html` are a
reasoned setting, not a measurement. They need calibrating once a dozen
listings with known answers exist.

### Trap: the geocoder reaches out of the state ✅

`api.transitous.org/api/v1/geocode?text=Großbothen Bahnhof` returns
**`Großbeeren, Bahnhof`** — 134 km away, in Brandenburg — as its sixth result.
Any geocoder hit outside the already-narrowed area has to be discarded before
it becomes a ring.

---

## 8. The tolerance staircase ✅

Rather than choosing one area tolerance, start hard and open up only when a rung
comes back empty. Each rung is one `resultType=hits` request. Measured against
Gemarkung 144241 around the listing's 502 m²:

| Rung | Band | Candidates |
|---|---|---|
| ±0 % | 502–502 | **1** |
| ±0,5 % | 500–504 | 2 |
| ±1 % | 497–507 | 5 |
| ±2 % | 492–512 | 12 |
| ±5 % | 477–527 | 25 |
| ±10 % | 452–552 | 46 |
| ±20 % | 402–602 | 83 |

Two rules follow.

**The rungs come from the wording, not from a constant.** "502 m²" is exact and
starts at ±0 %; "ca. 500 m²" starts at ±1 %; "ab 450 m²" is a one-sided bound and
never a band at all.

**Confirm one rung wider.** The loop stops at the first rung that returns
anything, which risks stopping on a coincidence. So after the stop, open the next
rung and score the extra candidates. Here ±0 % yields 790/11 alone; ±0,5 % adds
`238/3` at 500 m², 1 730 m away and not on the Wiesenstraße — it loses clearly, so
the stop holds. One extra request buys the difference between "a hit" and "a hit
that survived a challenge". ⚠️ It only catches the neighbouring-rung case; if the
right parcel were far outside the band, it would not help.

---

## 9. `ave:tntxt` is a free land-use filter ✅

Every `ave:Flurstueck` carries `tntxt` — the actual land use with the area share
per kind. 790/11 is `Wohnbaufläche;502`; a carriageway parcel is
`Straßenverkehr;1062`. `PropertyIsLike` filters it server-side:

| Filter in Gemarkung 144241 | Parcels |
|---|---|
| none | 1 131 |
| Wohnbaufläche only | 446 |
| area band ±5 % | 25 |
| area band ±5 % **+ Wohnbaufläche** | **16** |

**Use it soft, not hard.** That 790/11 happens to be recorded as Wohnbaufläche is
luck: an unbuilt building plot can just as legitimately be Landwirtschaft or
Gartenland. The value is official; the inference "Baugrundstück ⇒ Wohnbaufläche"
is not, and only official *facts* may exclude.

The same field also hands over the street surfaces — the parcels whose use is
`Straßenverkehr` are the carriageway, authoritative and as polygons, with no OSM
request.

---

## 10. OCR and rotation: upscale first ✅

Listing images are rotated and tilted. Measured on the same Geoportal print
(Tesseract 5.3.4, Pillow Lanczos, medians of three runs including process start;
"found" = the parcel number read correctly):

| Rotation | `--psm 6` | `--psm 1` | 2× then `--psm 6` | 2× then `--psm 1` |
|---|---|---|---|---|
| 0° | ✅ 460 ms | ✅ 651 ms | ✅ 780 ms | ✅ 909 ms |
| 3° tilt | ✅ 470 ms | ✅ 678 ms | ✅ 778 ms | ✅ 948 ms |
| 7° tilt | ❌ | ❌ | ✅ 769 ms | ❌ |
| 90° | ❌ | ✅ 576 ms | ❌ | ✅ 910 ms |
| 180° | ❌ | ❌ 682 ms | ❌ | ✅ 1 003 ms |
| 270° | ❌ | ✅ 526 ms | ❌ | ✅ 1 003 ms |
| 15° tilt | ❌ | ❌ | ❌ | ❌ |

**Upscaling is the fix, not orientation detection.** A 2× Lanczos upscale (long
edge ≥ 1500 px) repaired `--psm 1`'s blindness to a 180° flip, repaired the 7°
tilt with no deskewing, and raised OSD's confidence from ~1,0 to ~3,0. Real phone
photos already exceed 1500 px, so the 2× columns are the honest proxy for
production input.

**The ladder: upscale → `--psm 6` → `--psm 1` only if no pattern matched.**
Worst case ~1,7 s, and the second pass runs only when the first came back empty.

**An OSD pre-pass does not earn its cost.** Same total time, on *every* image,
plus three failure modes: at native size it reports the *complement* for ±90
(r090 → `Rotate: 270`), so a wrong sign silently flips the page; it exits
`rc=1` "Too few characters" on the orthophoto; and it claimed `Rotate: 180` at
confidence 0,72 on one of the site photographs, which a blanket pre-pass would
have acted on. If used anyway: apply `rotate(-R)`, gate on Latin script and
confidence ≥ 1,5, treat a non-zero exit as "no opinion", and never lower
`min_characters_to_try`.

**Do not build deskewing.** Below 10° it is unnecessary after upscaling; at 15°
it did not help even when given the exact angle.

### Trap: a garbled number is worse than none ✅

At 7° and native size the reader returned `Flurstück 790717` — it found the word
and corrupted the digits. An empty answer is harmless; a plausible wrong number
resolves to a real but foreign parcel, and that is exactly the error that
validating against ALKIS cannot catch. This is the real reason to upscale.

⚠️ Untested: `--dpi 300` as a hint (every run logged "Invalid resolution 0 dpi.
Using 70 instead"), Leptonica/OpenCV deskewing (neither available in this
sandbox), and whether the script-plus-confidence gate generalises beyond this
one image.

---

## 11. Named landmarks: a ranker, never a filter ✅

Listings name excursion destinations. Turning those into distance rings is the
most dangerous idea in the design, and the same listing settles it.

⚠️ **Verification note:** `overpass-api.de` was unreachable from this sandbox
(the agent proxy dropped the tunnel mid-exchange, reproduced 8×). The Overpass
figures below come from the `maps.mail.ru/osm/tools/overpass` mirror, a
full-planet 0.7.62.4 instance whose `timestamp_osm_base` was current. The ALKIS
WFS and the Transitous geocoder were reached directly.

### The measurement that decides it

The listing names **Kloster Nimbschen** and **Schiffsmühle Höfgen**. The parcel
is in Gemarkung Großbothen.

| Landmark | To nearest Gemarkung edge | 1 km disc ∩ Gemarkung | 2 km disc ∩ Gemarkung |
|---|---|---|---|
| Kloster Nimbschen | 1.92 km | **0 %** | 1 % |
| Schiffmühle Höfgen | 1.81 km | **0 %** | 2 % |
| Cospudener See | 28.27 km | 0 % | 0 % |

**As a hard filter, either landmark would have eliminated the correct answer.**
They only cover the Gemarkung at ~5 km — the radius at which they stop
constraining anything. The listing named them as places to visit, and nothing in
the sentence structure separates that from "adjacent to". That is the
frequency trap one level up, and the reason prompt P1 asks for the relation.

### How much each kind constrains

Reference: Gemarkung Großbothen is **5.928 km²** with 1 131 parcels (191/km²),
measured from its `ave:KatasterBezirk` outline.

| Evidence | Kind | Extent | Search area at 1 km | vs Gemarkung |
|---|---|---|---|---|
| Gemarkung Großbothen | area, official | 2 522 × 3 980 m | 5.93 km² | 1× |
| Kloster Nimbschen (`way/54111480`) | point-like | 26 × 50 m | 3.14 km² | 0.5× |
| Schiffmühle (`way/307571618`) | point-like | 15 × 11 m | 3.14 km² | 0.5× |
| Cospudener See (`relation/285950`) | extended | 1 688 × 3 932 m | 17.40 km² | 2.9× |
| B 107 | line, 247 ways | 34.4 km in one bbox | 68.83 km² | 11.6× |

Cross-checked against real parcel counts with `fes:BBOX` on `ave:geometrie`
(which works — a useful mechanism in its own right): a 2 × 2 km box around
Kloster Nimbschen holds **407** parcels, a 4 × 4 km box **2 888**.

So a point landmark *with a stated distance* is genuinely tighter than a
Gemarkung. A point landmark with only "in der Nähe" is not evidence of location
at all, as the table above shows.

### Distance is to the boundary, not the centroid

Buffering the Cospudener See polygon by 1 km gives 17.40 km² (13.01 km² of it
land, once the water is subtracted); a 1 km disc about its centroid gives
3.14 km² **and does not reach the lake's own north and south ends** — it is a
4 km long lake. The two sets barely overlap: the centroid is not a coarser
answer, it is a different place. The constraint is an annulus,
`buffer(geom, r) \ geom`, and for a line it is a corridor whose area grows
linearly with length.

The backend owns no geometry maths today. Two honest routes: Shapely in the
backend for this one path, or a `fes:BBOX` pre-filter plus an exact test on the
returned candidates — the same shape as the existing `ave:flaeche` filtering.

### A bare name is a 1-in-500 shot

Across Saxony: `Bahnhofstraße` appears in **2 918** OSM ways, `Dorfstraße` in
**4 043** — roughly 400–970 distinct streets each, spread over 220 × 170 km.
Neither occurs in Gemarkung Großbothen at all. **Gemarkung plus street name is
essentially unique; a street name alone is worthless.** The same holds for
landmarks: 8 of the 46 objects returned around Nimbschen are a hotel, a
guesthouse, a chapel, a ferry terminal and a viewpoint named *after* the
landmark, and the geocoder's top hit for "Schiffsmühle Höfgen" is the restaurant.

### What the existing code cannot do

`POI_CATEGORIES` is `schule, kindergarten, park, spielplatz, supermarkt, arzt` —
no `natural=water`, no `historic=*`, no `highway` with `ref`, so none of these
landmarks is representable. Beyond the category list there are three deeper gaps:
there is no name lookup at all (`PoiIndex.nearest` goes from a point to a
category, never from a name to a place, and `PoiEntry.name` is stored but never
searched); `entries_from_elements` reduces every way and relation to `out center`,
so extent is discarded and a 4.4 km² lake would enter the index as one point; and
the backend owns no buffer or intersection.

⚠️ Not verified: the exact position of 790/11 relative to the landmarks — the
1.8/1.9 km figures are to the nearest edge of the whole Gemarkung, so the true
miss is at least that and probably larger. Overpass counts come from a Saxony
bounding box, which clips in a little of Brandenburg, Thuringia and Bohemia.

---

## 12. The verdict rests on hard filters, not on weights ✅

There is no corpus of solved listings to calibrate against, and it turns out one
is not needed to ship — provided the responsibilities are split:

* **Hard filters decide.** Only official *facts*: a parcel key resolved against
  ALKIS, the Gemarkung, and `ave:flaeche` when the listing's figure is exact.
* **Soft scoring orders.** Everything inferential: a rounded area, the street
  buffer, land use, distance claims, landmarks.

`bestaetigt` therefore means "plausibility raised no objection **and** exactly
one candidate survives the hard filters", not "the leader is far enough ahead".
The lead threshold disappears, and uncalibrated weights can no longer produce a
wrong answer — only a list in a slightly unhelpful order.

### Wrong anchors return nothing — at an exact area ✅

The anchor is a hard filter, so a mis-read relation ("Grimma" instead of
"Großbothen") would be the one route to a confidently wrong answer. Measured
against all three Gemarkung names the listing text contains:

| Area constraint | Großbothen | Grimma | Höfgen |
|---|---|---|---|
| **exact (502 m²)** | **1** | 0 | 0 |
| ±0,5 % | 2 | **26** | 0 |
| ±1 % | 5 | **45** | 0 |
| ±5 % | 25 | **206** | 2 |

**At an exact area the relation extraction is unnecessary** — run the staircase
against every place candidate and the area picks the right one; the wrong
anchors come back empty.

**One rung out, that inverts.** Gemarkung Grimma is much larger and yields 26
against Großbothen's 2 — so the place that is named more often *and* is bigger
produces the most false candidates. From here the relation has to be right, which
is exactly where spaCy or prompt P1 earn their cost, and nowhere earlier.

### The anchor's size is not an abort criterion ✅

A proposed rule — refuse an anchor holding more than 60 000 parcels — was
refuted by measuring it:

| Anchor | Parcels | + `flaeche = 502` |
|---|---|---|
| Gemarkung Großbothen | 1 131 | 1 |
| Stadt Grimma | 32 544 | 15 |
| **Stadt Leipzig** | **112 588** | **78** |
| Stadt Dresden | 108 558 | not measured |

Leipzig and Dresden both sit far above the cap and would have been rejected —
yet Leipzig plus the exact area leaves 78 candidates, a perfectly scoreable set.
So the abort belongs on the **candidate set after the hard filters** (~500), not
on the anchor.

---

## 13. The common envelope ✅

"Ambiguous" is not a failure as long as the answer says what *is* settled. Take
the smallest unit every surviving candidate shares and show that:

| After | Candidates | Common envelope |
|---|---|---|
| area band ±5 % | 25 | Gemarkung Großbothen |
| + both rings | 8 | Gemarkung Großbothen (3 of the 8 are not on the Wiesenstraße) |
| + street buffer | 5 | **Wiesenstraße, Gemarkung Großbothen** |
| + exact area | 1 | Flurstück 790/11 |

For the land value and for travel times the envelope is often enough — the
Bodenrichtwert is zonal, and routes from one street differ by metres. Only the
area and the boundaries genuinely need the individual parcel.

The envelope must never look like a hit: no halo, no drawn contour. Those stay
reserved for a confirmed parcel.

---

## 14. Streaming: NDJSON, because there is no database ✅

The map has to grow while the search runs. Server-Sent Events would need the
indicia posted first and fetched back under an id — server-side job state that
nothing would clean up. Polling has the same problem. **NDJSON over a chunked
POST response** keeps one endpoint, one call, no state:
`StreamingResponse` on the FastAPI side, `fetch` plus `body.getReader()` in the
browser, one JSON object per line.

It is already provisioned: `frontend/nginx.conf` sets `proxy_buffering off` and
a 300 s timeout on `/api/`, put there for the listing extraction. A stream from
the same place needs no configuration change.

---

---

## 15. Second pass, 05.09.2026: what the review changed ✅

Everything in §§ 2-15 was re-run against the live WFS before the algorithm was
built. The tolerance staircase, the land-use filter and the wrong-anchor table
all reproduce **exactly**. Five things did not survive the second look, and
four of them make the search cheaper.

### 15.1 A parcel number settles a contested district by itself ✅

The drafted algorithm chose *one* anchor and filtered inside it, which made a
misread relation the single route to a confidently wrong answer. It does not
have to choose. Testing the number against every district the text names:

| Anchor | + Flurstück 790/11 |
|---|---|
| Gemarkung Großbothen (144241) | **1** |
| Gemarkung Grimma (144236) | 0 |
| Gemarkung Höfgen (144245) | 0 |
| Gemarkung Höfgen (146132) | 0 |

Four count requests, and the contest is over — no relation extraction, no
model call, and no question to the user. The same shape as the exact-area
result in § 12, one signal further along: **a hard filter run against a *set*
of anchors is a disambiguator, not just a filter.**

A district name that is not unique contributes *all* of its districts. Two
Höfgen are two cheap questions; dropping the name because it is ambiguous
throws away exactly the case this search exists for.

### 15.2 How far a number goes with no district at all ✅

| Query, whole of Saxony | Parcels |
|---|---|
| `flstnrzae=790` and `flstnrnen=11` | **5** |
| `flstnrzae=85` and `flstnrnen=1` | 672 |

So a distinctive number is nearly an anchor on its own and a low one is
nothing — and one `resultType=hits` request is enough to tell which. Worth
spending as a last resort; not worth guessing about.

### 15.3 `gmdschl` is a working anchor ✅

| Constraint | Parcels |
|---|---|
| `gmdschl = 14729160` (Stadt Grimma) | 32 544 |
| … + `flstnrzae=790`, `flstnrnen=11` | **1** |
| … + `flstnrzae=790` (no denominator) | 13 |

A municipality is a legitimate container when no Gemarkung is known — and the
denominator is what makes it decisive.

### 15.4 `ave:lagebeztxt` is filterable after all — and must never filter ✅

§ 6 concluded that a street "cannot be matched against ALKIS as an attribute"
because 790/11 carries `"ohne Lage"`. That is too strong: the field *is*
matchable server-side with `PropertyIsLike`, and in Großbothen it covers a
sixth of the district.

| Filter in Gemarkung 144241 | Parcels |
|---|---|
| `lagebeztxt` like `*Wiesenstr*` | **71** |
| `lagebeztxt` like `*ohne Lage*` | 577 |
| Gemarkung Mölkau (143156), total | 250 |
| … `"ohne Lage"` | 227 |

Two conclusions, and the second is the important one. It is free — the field
rides along with every feature, so no Overpass request is needed for the
common case. And it may only ever **promote**: 790/11 is one of the 577, so a
hard street filter would have deleted the right answer. A missing address is
missing data, not a contradiction.

### 15.5 „OT von X“ names the municipality, not the cadastral district ✅

§ 5 showed that counting mentions picks Grimma, and § 12 showed that one rung
out Grimma manufactures 26 false candidates against Großbothen's 2. Both are
consequences of reading one sentence wrongly:

> „am Ortsrand von **Großbothen**, einem OT von **Grimma**“

Großbothen is where the plot is; Grimma is the *municipality Großbothen
belongs to*. Read that way the two names stop competing, and the second
mention — „die ca. 6 km entfernte Kreisstadt Grimma“ — turns Grimma into
evidence against itself rather than for itself. The frequency trap disappears
without a model, a parser or a weight. What the extractor needs is not
"which place" but "which *level*".

### 15.6 The costs, measured ✅

| | |
|---|---|
| `ave:KatasterBezirk` for one district | **16.5 kB**, 637 boundary points, one request |
| 25 parcels with geometry | 35.6 kB, ~1.4 kB each, 1.5 s |
| `fes:BBOX` 2 × 2 km on `ave:geometrie` | 785 parcels |

The first is what makes the search map possible: the committed directory drops
the geometry on purpose, so the district wash is one request, on demand, and
not 28 MB in the repository.

The second sets the cap. ALKIS cannot be asked for attributes without
geometry, so the split is: `resultType=hits` for every rung and every probe,
and the features fetched only once the count is small enough to draw.

### 15.7 What the drafted algorithm got wrong

* **The short circuit did not check.** It jumped from "district and number
  present" straight to the verdict. But § 10 records a misreading that
  produced `Flurstück 790717` — a plausible wrong number resolves to a real
  but foreign parcel, and that is exactly the error validating against ALKIS
  does *not* catch. The check costs nothing: the official area and the
  municipality arrive **with** the parcel, so comparing them to what the
  listing says is a rule, not a request. This also answers the open question
  the strategy page left ("is the short circuit safe when the image names a
  district the location field contradicts?" — no, and now it says so).
* **A five-digit numerator is the only string test worth having.** The AdV
  parcel key gives the numerator five characters and the denominator four, so
  `790717` is not a parcel number at all and can be rejected before a request
  is spent. Nothing beyond that width is detectable from the string; the rest
  is the cross-check above.
* **„bestätigt“ was defined twice.** The outcomes section still said "and the
  runner-up is far enough behind" after the lead threshold had been abolished
  in favour of the hard filters. The hard-filter definition is the one that
  holds — and it needs one addition the draft did not have: a single survivor
  reached only through a *chosen tolerance* is `mehrdeutig`, not
  `bestätigt`, because nothing official picked it.
* **The model call sat in phase 0.** The detail text gates it correctly
  ("only when the area is not exact"), the pseudo-code did not. It belongs
  after the staircase, which is measurably where it stops being needed.
* **The anchor tie was undefined.** When several anchors survive, the draft
  did not say whose candidates win. They are unioned, and the fact that more
  than one anchor survived *is itself* the thing to show the user.

---

## 16. Third pass, 05.09.2026: four listings that did not work ✅

Four adverts the author reported as failing. All four now resolve to a single
confirmed parcel in six or seven cadastre requests. Each failure was a
different bug, and three of them were mistakes in the *reading*, not in the
search.

| Advert | Reported | Now |
|---|---|---|
| 3423861748, "Ortsteil Lobstädt bei Neukieritzsch", 1 025 m² | 3 candidates, ambiguous | **51/3, Gemarkung Lobstädt**, Dora-Helene-Straße 5 |
| 3375124391, "Ortsteil Plagwitz von Machern", 1 489 m² | 2 candidates, ambiguous | **309/6, Gemarkung Plagwitz** |
| 3503721553, "in Bad Lausick", 1 076 m² | 9 candidates, ambiguous | **502/47, Gemarkung Etzoldshain**, "Am Kurpark" |
| 3499632623 (the reference), parcel number on an attached print | text only | **790/11 in 2 requests**, read off the image |

### 16.1 The municipality is the missing key, and it was already in the file ✅

`gemarkungen-sachsen.json` carries `gemeinde` per district and nothing used it.

    Plagwitz   140427 → Stadt Leipzig
    Plagwitz   148642 → Machern

Two districts of that name, and the listing says "Ortsteil Plagwitz **von
Machern**". One line of directory lookup turns an ambiguity into an answer —
and the same field removes the false candidates in the Lobstädt advert, where
"gute Anbindung **an Leipzig**" had made Gemarkung Leipzig an anchor and Leipzig
holds two parcels of exactly 1 025 m².

**The location field's municipality is reliable even though its coordinate is
not.** That looks like a contradiction of § 2 and is not: the pin is 6 km out
*because* it is the municipality's geocode, so the name it was geocoded from is
exactly the part that holds. True on all four adverts:

| Location field | Parcel's district | Its municipality |
|---|---|---|
| 04668 Sachsen – Grimma | Großbothen | Stadt Grimma |
| 04827 Sachsen - Machern | Plagwitz | Machern |
| 04575 Sachsen - Neukieritzsch | Lobstädt | Neukieritzsch |
| 04651 Sachsen - Bad Lausick | Etzoldshain | Stadt Bad Lausick |

Used as a filter *with a fallback*: when nothing matches, the whole anchor set
stands. It is a strong hint, not an official fact about this plot.

### 16.2 Widen the *place* before the *number* ✅

"1.076 m² in Bad Lausick" has **no** match in Gemarkung Bad Lausick. The
drafted staircase would open the tolerance; that is the wrong thing to give up.

| Constraint | Parcels |
|---|---|
| Gemarkung Bad Lausick + `flaeche = 1076` | **0** |
| Gemarkung Bad Lausick + ±0,5 % | 5 |
| **Gemeinde** Stadt Bad Lausick + `flaeche = 1076` | **1** |

The one is Flurstück 502/47 in Gemarkung **Etzoldshain**, `lagebeztxt`
"Am Kurpark" — and the advert is titled "Naturnah wohnen am Kurpark". The
Gemarkung named in the prose was simply the wrong level.

An exactly stated area is an official fact; a Gemarkung read out of prose is
not. Widening the number to keep the guess throws away the better of the two.
Stadt Bad Lausick has 14 Gemarkungen and 11 156 parcels, so this stays a hard
filter — it is the *place* that got looser, not the test.

### 16.3 German capitalises every noun ✅

A bare directory match is not evidence. The Machern advert reads "geprägt von
**Wiesen** und Feldern", and Wiesen is a real Gemarkung (148950, Stadt
Wildenfels); "**Leipzig**" and "**Püchau**" arrive the same way. Each cost a
count request and one produced false candidates.

Only a place with a *positional* relation is searched now — `liegt_in` or
`liegt_an`. A bare mention stays in the protocol as weak evidence, where it
belongs. Same reason "Ihr Platz zum Träumen" and "einen befahrbaren Feldweg"
were being read as streets.

And the relation itself needs care: "Anbindung **an** Leipzig", "Nähe **zu**
Leipzig" are connectivity, not location.

### 16.4 „Ortsteil <A> von <B>" — the district comes first ✅

The second pass handled "Großbothen, einem OT von Grimma" and missed the more
common ordering:

    Ortsteil Plagwitz von Machern
    Ortsteil Lobstädt bei Neukieritzsch
    Ortsteil Plagwitz der Gemeinde Machern

All three name the district *and* the municipality, one level apart. Reading
that pair is what makes § 16.1 possible.

### 16.5 Tesseract, wired up and measured ✅

Now built, not just designed. Against the reference advert's seven images:

| | |
|---|---|
| Image 4 (Geoportal print, 678 x 960) | `Flurstück 790/11`, **862 ms**, first pass |
| The other six (site photographs, orthophoto) | nothing, both passes |
| Whole advert, text first then images | **2** cadastre requests, 15,6 s |

Across 14 further images from the three other adverts: **no false parcel
number and no false Gemarkung.** That is the property the design rests on, and
it now has 21 real images behind it rather than four.

**Two things the design got wrong, both found by running it:**

* **Reading the images concurrently is slower, not faster.** Tesseract is
  CPU-bound; seven at once pushed every process past a 30 s timeout on this
  machine, where sequentially each takes 0,9–5 s. The drafted "stop at the
  first hit" was right and the concurrency was an unmeasured optimisation.
* **A timed-out reader looked exactly like a photograph of a lawn.** Both
  produce no text, and the code reported both as "no cadastral extract
  attached" — a claim about the listing that it had never checked. `read()`
  now returns the failure alongside the text, and the search says "n of m
  images could not be read" rather than answering for them.

**What a portal serves is smaller than the reader wants.** Kleinanzeigen's
largest variant is 678 x 960 for the print and 960 x 720 for a photograph, so
the upscale is not the exception the earlier measurement implied — it runs on
every image.

### 16.6 Traps in getting the pages at all ✅

* **Kleinanzeigen answers the first request with 403 and the second with the
  page.** Reproduced on three adverts, exactly once each. Not a block, a
  warm-up; one retry is the difference between "the portal refuses us" and a
  working read.
* **The whole page is not the listing.** `html_to_text` returns navigation,
  cookie banner and category tree, and the search read all of it as evidence.
  The description sits in one findable element (`#viewad-description-text`);
  the structured attribute list next to it carries the *authoritative* area,
  which may be exact where the title hedges ("ca. 1.025qm" against
  "1.025 m²").
* **immobilienscout24.de still answers 401**, re-confirmed. Its images
  therefore have to come through the paste field, which is why image
  extraction falls back to ordinary `<img>` URLs for pages whose markup is not
  known here.

## 17. Fourth pass, 05.09.2026: three failures on the way in ✅

Reported from a running `docker compose`, all three before the search had asked
the cadastre anything at all. None is about parcels; all three are about the
step in front of it.

### 17.1 A German thousands stripper eats a coordinate ✅

Every Kleinanzeigen listing answered:

```
POST /api/parcels/search HTTP/1.0 422 Unprocessable Entity
„lat": Der Wert darf höchstens 90.0 betragen.
„lon": Der Wert darf höchstens 180.0 betragen.
```

The wizard read its fields with a helper that removed every `.` as a German
thousands separator. `51.189265` became `51189265`; the endpoint's `le=90` was
right to refuse it. The listing was never wrong — the number was destroyed one
step before the request.

A dot is a thousands separator **only in groups of three**, and a comma settles
the question outright:

| Input | Read as | Why |
| --- | --- | --- |
| `51.189265` | 51.189265 | six digits after the dot — not a group of three |
| `1.025` | 1025 | exactly three, no comma |
| `1.025,50` | 1025.5 | a comma is present, so the dot is a separator |
| `80.000 €` | 80000 | three digits, no comma |
| `auf Anfrage` | `null` | no digits, and no `NaN` either |

`parseGermanNumber` in `frontend/src/lib/format.js` is the single reader, and
`queryFromFields` is covered by a test that asserts the coordinate arrives
unchanged. The old helper was local to the wizard, which is how it survived.

### 17.2 The price was never found, and did not need a model ✅

The "Gelesene Werte" step showed *Kaufpreis* empty on all four adverts, because
the price only ever came from the model, and the model was only asked for pages
without a known adapter.

Measured on the four saved pages: the price is in the markup three times over —
`<meta itemprop="price">`, the JSON-LD `offers.price`, and the boxed figure in
the page body. Parsing them in that order:

| Advert | Price found | Source |
| --- | --- | --- |
| 3423861748 Lobstädt | 80 000 € | meta |
| 3375124391 Plagwitz | 165 000 € | meta |
| 3503721553 Etzoldshain | 195 000 € | meta |
| 3499632623 Großbothen | 60 000 € | meta |

Four out of four, no model call, and the same reader works on a pasted page
because the meta tags travel with it.

### 17.3 The paste field required a model it did not need ✅

Pasting an ImmoScout24 page answered „Das Auswerten eingefügter Texte ist nicht
konfiguriert (LLM_API_KEY fehlt)" — the one portal the paste field exists for.

Two things fix it and neither needs a provider:

* **Read the pasted text with the same deterministic parsers as a fetched
  page.** A copied page carries its price and its attribute list — but not its
  meta tags and not its JSON-LD, which the note below corrects. The model is only asked when *no locator at all* — no
  address, no coordinate, no parcel number — could be read, and the refusal
  then says what to paste instead rather than only naming the missing key.
* **Take the clipboard's HTML flavour.** `Strg+A, Strg+C` in a browser puts
  **both** `text/plain` and `text/html` on the clipboard; a `<textarea>` shows
  only the first. The paste handler keeps the second (capped at 400 000
  characters) and sends it instead. Emptying the field clears it, or the next
  read silently ships the page pasted before.

  **Corrected 09.09.2026:** the parenthesis above said "the head of the
  document is where every locator sits", and that is exactly what does *not*
  arrive. `Strg+A` selects the body, so no `<meta>` and no JSON-LD is in the
  clipboard at all — measured in Chromium. Body markup survives. See
  `immobilienscout24-zugang.md` § 4; § 20.5 below is a consequence of this and
  not of ImmoScout's markup.

### 17.4 Enter has to submit ✅

The URL field swallowed the Enter key: there was no `<form>`, so there was no
implicit submission. Wrapping the step in one fixes it — and then the submit
button submits **twice** in a real browser, once through its own activation and
once through the handler. The click carries `.prevent`, so there is one way in.

Worth knowing for the tests: **jsdom does not run a form's submission from a
dispatched click**, so a test that clicks the button never exercises the form,
and a test that only triggers `submit` never exercises the button. Both paths
are tested separately.

## 18. Fifth pass, 06.09.2026: what a deployment reported ✅

Three of these came back from a running `docker compose`, and none of them was
visible from the tests.

### 18.1 The image had no reader in it ✅

The search said „keine Bilderkennung eingerichtet“ on every Compose
deployment, while the code, the suite and the README all said Tesseract was
wired up. The image installed `.[poi]` and no system packages beyond
`libexpat1`: `ocr.available()` is `shutil.which("tesseract")`, and there was
none. Both packages are needed — `tesseract-ocr` for the binary and
`tesseract-ocr-deu` for the language data, because the patterns key on the
words around the number.

### 18.2 A cache with no expiry outlives the code that filled it ✅

Reported as „bei den Kleinanzeigen-Links wird immer noch nicht zuverlässig
Preis sowie Flurstückgröße gefunden“, with one advert named. Fetched live on
06.09.2026, that page parses cleanly:

| | |
| --- | --- |
| `itemprop="price"` | `165000.00` |
| `#viewad-price` | `165.000 €` |
| Attribute list | `Grundstücksfläche: 1.489 m²`, `Grundstücksart: Baugrundstück` |
| `og:latitude` / `og:longitude` | 51.3677848 / 12.6086485 |

So the reader was right and the *cache* was wrong: `POST /api/listings/extract`
keys on `inserat:<normalised url>` and the LLM cache has `ttl_s=None`. An
answer written before the price parser existed is therefore served for ever —
and only for the listings someone had already opened, which is exactly what
„nicht zuverlässig“ looks like from outside. The key now carries
`EXTRACTION_VERSION`.

The same fault was already documented for MOTIS and had never been fixed: its
cache key was the request parameters alone, so pointing `MOTIS_BASE_URL` at a
local router kept serving Transitous's answers. That key now carries a hash of
the base URL.

### 18.3 Local routing was one forgettable variable away from silence ✅

`docker compose --profile local-routing up` brought the router up and left the
backend talking to Transitous, because `MOTIS_BASE_URL=http://motis:8080` had
to be typed alongside it. Nothing showed: the two instances agree to the last
decimal (§ 5 of `routing-motis.md`), so the only sign was whose bandwidth was
being spent. The services moved into `docker-compose.local-routing.yml`, which
also sets the variable — naming the file is now the whole opt-in.

`profiles: []` in an override file does **not** clear a profile inherited from
the base file; `docker compose config` then refuses with „service backend
depends on undefined service motis“. Moving the services is the way to do it,
not overriding them.

## 19. The orthophoto with the cadastre on it ✅

A listing shows photographs of the plot, so the ground under the search map
should be something those can be compared against. Measured against the GeoSN
services at Flurstück 790/11, all through one 256 px tile at the parcel:

| Layer | z17 | z18 | z19 |
| --- | --- | --- | --- |
| `sn_dop_020` (orthophoto) | draws | draws | draws |
| `adv_alkis_tatsaechliche_nutzung` | — | draws | — |
| `adv_alkis_gebaeude` | — | draws | — |
| **`adv_alkis_flurstuecke`** | **empty** | **empty** | **draws** |
| WebAtlas `Verkehr,Beschriftung` | draws | draws | draws |

**`adv_alkis_flurstuecke` carries `MaxScaleDenominator: 2000`** and answers
HTTP 200 with a fully transparent 854-byte PNG above it — the same shape as the
ArcGIS `minScale` trap, on a different service and a different protocol. The
computed denominators: z17 1:4265, z18 1:2133, z19 1:1066. It is the scale and
not the style — `Farbe`, `SW`, `Gelb` and the empty string all come back empty
at z18 — and `STYLES=default` is rejected outright with a
`ServiceExceptionReport`, so the empty string is the only way to ask for the
default.

The style to use over a photo is **`Gelb`**, which the layer's own abstract
describes: „In der Gelb-Darstellung werden keine Flaechen sondern nur Konturen
dargestellt.“

So the search map's ground is three raster layers in this order — photo,
streets with their names, parcel outlines from zoom 19 — and the outline layer
carries that floor as `minzoom`, or the map asks for hundreds of blank tiles on
the way in and looks like a broken layer rather than a scale.

## 20. Sixth pass, 06.09.2026: a scale limit is steerable ✅

### 20.1 Oversampling the cadastre ✅

§ 19 stopped at „the outlines only draw from z19“, which is too deep to be
useful — the search map spends its time between z14 and z18. The limit is a
*scale*, and the WMS computes it from what it is handed:

    denominator = (bbox_width / image_width) / 0,00028

So a larger image over the same box falls under it. Measured against the live
service at Flurstück 790/11, one tile each, then scaled back to 256 px:

| Zoom | render | denominator | upstream | tile it becomes |
| --- | --- | --- | --- | --- |
| z19 | 256 px | 1:1066 | 10,7 kB | 10,7 kB |
| z18 | 512 px | 1:1066 | 27,9 kB | 14,7 kB |
| z17 | 768 px | 1:1422 | 68,2 kB | 21,4 kB |
| z16 | 1280 px | 1:1706 | 246 kB | 39,1 kB |
| z15 | 2304 px | 1:1896 | 499 kB | 33,7 kB |
| z14 | — | — | — | **impossible** |

z14 would need 4368 px for one tile and the service's `MaxWidth`/`MaxHeight`
is **4000**, so that is where the floor is — a measured fact, not a
preference. The upstream cost is paid once and cached for 30 days; the browser
never sees it.

Rounding up to whole tiles rather than doubling matters: z15 needs 2184 px and
the next power of two is 4096, over the cap.

### 20.2 What a photograph does to a palette ✅

The evidence layers were built for the app's near-white paper — 0,1 fills,
1,2 px hairlines. Over an orthophoto, which is mostly green, grey and dark with
detail everywhere, they are not there. Over the photo the fills go to 0,24–0,5
and every line gets the halo the site plan has always drawn under its own.

### 20.3 The frame before the narration ✅

The clues are paced so a run can be followed. The district outlines were
emitted after all of them, so for the first seconds the map sat on the whole
state while the list already named a village. The same request, one step
earlier, fixes it — and costs nothing, because the wash under a confirmed
parcel is that same document and `fetch_outline` now reuses it. The happy case
is still two requests.

### 20.4 Images last ✅

Reading them was phase 0: up to a few seconds an image in front of the first
thing the map could draw, for a channel most listings do not have. They are
read after the text now, and only when the text did not confirm. A number
found then re-runs the narrowing rather than being noted and ignored.

### 20.5 The paste gate was asking the wrong question ✅

A dropped ImmoScout page was refused for having no address, no coordinate and
no parcel number — which is every ImmoScout page *as the clipboard delivers
it*, the one portal that field exists for. (The reason was found on 09.09.2026
and is not the portal: the clipboard drops `<head>`, so the meta tags and
JSON-LD carrying all three never arrive. See `immobilienscout24-zugang.md`
§ 4. The gate below is still the right gate.) None of the three is what the search needs: it reads a district, a
street and an area out of prose. The gate now asks `collect_indicia` whether
the text yields an *anchor* — a Gemarkung, a Gemeinde, a place or a parcel
number. An area alone is not one, so „Baugrundstück 688 m²“ is still refused,
with the message that says what to paste instead.

## 21. Seventh pass, 06.09.2026: an advert with no Flurstück ✅

Advert 2418686487, „Baugrundstück bei Borna“, reported as finding the wrong
parcel. Three separate things, and the third is the interesting one.

### 21.1 The reader garbles the label, not only the digits ✅

Its Liegenschaftskarte's title block reads, verbatim from Tesseract:

    Fiurstück: 107/60   Gemeinde: Stadt Boma
    Gemarkung Thrana (1922)

So the **l became an i** and the pattern — which requires the word — threw the
one number on the sheet that means anything away, while the Gemarkung beside it
came through. § 10's rule that a garbled *number* is worse than none still
holds; this is the label, and losing it costs a whole channel.

`[li1|]` in that position now. The rest of the word carries the specificity:
`Fust 12/3`, `First 12`, `Furst 40` and „die Flur ist 12 ha groß“ all still
match nothing.

„Thrana“ needs no help — the directory folds diacritics and resolves it to
Thräna (141922, Stadt Borna). The four-digit `1922` on the sheet is the short
form of that key.

### 21.2 The sheet's other numbers ✅

That map body carries **dozens**: 107/61, 107/13, 107/4, 105/6, 106/3, 74/3,
68/8, 110/9, 54/45… Only the title block is labelled, and only a labelled
number is ever taken, which is what makes reading every image safe. Where a
sheet does yield more than one, the reading is a `Konflikt` like any other —
and the Indiz now carries `bild_url`, so the choice is made against the sheet
rather than against a line of OCR text.

### 21.3 The plot has no Flurstück ✅

The description says it outright:

> Bei dem Grundstück handelt es sich derzeit um eine **noch zu vermessende
> Teilfläche**, die im Rahmen des Verkaufsprozesses exakt abgegrenzt und im
> Grundbuch eingetragen wird.

748,50 m² is therefore the size of a parcel that **does not exist yet**. As a
hard filter it finds some other parcel of that size and confirms it — exactly
the confidently wrong answer § 12 is built to refuse, and no cross-check can
catch it, because the found parcel is perfectly real.

`describes_part_area` reads the sentence (worded as *pending*, so „die
Vermessung ist erfolgt“ does not match), `AreaStatement.exact` goes false, and
`verdict()` can never say „bestätigt“ for such a listing. The run then answers
what is actually true:

| | |
| --- | --- |
| Read off the image | Flurstück 107/60, Gemarkung Thräna |
| Resolved in | **2 requests** |
| Official area of 107/60 | 2 994 m² |
| Verdict | `mehrdeutig`, with the sentence that says why |

And the area mismatch is *not* reported as an objection: it is the situation,
and „bitte die Flurstücksnummer prüfen“ would send someone looking for a
mistake that is not there.

## 22. What is still unverified ⚠️

* The three prompts in `docs/strategie/extraktion-prompting.html` are drafted
  but have not been run against a model — this listing did not need them.
* The land-use filter (`ave:NutzungFlurstueck` = Wohnbaufläche) and the
  "unbuilt parcel" filter are proposed, not measured.
* Whether pre-sorting images is worth it. Four images cost 9.5 s of OCR in
  total; stopping at the first hit removes most of that, provided the map
  extract is not the last image.
* Walking times. Every distance here is an air line. The project's own rule is
  to rank by walking time via `one-to-many`; the air lines above are therefore
  a lower bound, and the deviations from the broker's claims can only grow.
