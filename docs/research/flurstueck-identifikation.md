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

## 16. What is still unverified ⚠️

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
