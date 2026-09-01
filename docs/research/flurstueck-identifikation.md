# From a listing to the parcel — what the evidence actually supports

**Research date: 2026-09-01.** Written in English: this is developer
documentation, only the user interface is German.

> **Legend**
> ✅ **VERIFIED LIVE (2026-09-01)** — a request was made from this shell, or a
> command run here, and its answer read.
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

## 8. What is still unverified ⚠️

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
