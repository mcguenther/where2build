# Grundstücks-Check Sachsen — Backend

FastAPI service behind the Vue frontend. It serves data only: every geometry
operation (buffer, rotation, collision check) happens in the browser with
Turf.js. What lives here is the part a browser cannot do — talking to the
authority services, caching their answers, and turning listing and
manufacturer pages into structured, unconfirmed suggestions.

Data sources: ALKIS (parcels), BORIS (land reference values), GeoSN WMS
(orthophoto, topographic map, cadastral map), OpenFreeMap (vector basemap),
MOTIS/Transitous (multimodal routing and public-transport stops), a locally
built OpenStreetMap index for everyday destinations, and one OpenAI-compatible
provider for page extraction.

The browser talks to this API and to nothing else. Every authority service,
and the basemap along with them, is proxied here -- that is what makes the app
work in a sealed network and behind a corporate firewall.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"      # or: pip install fastapi uvicorn[standard] pydantic pydantic-settings httpx pyproj shapely pytest pytest-asyncio respx
cp .env.example .env                    # fill in LLM_API_KEY if you want extraction
```

Run every command below from this `backend/` directory.

## Run

```bash
.venv/bin/python -m uvicorn app.main:app --reload --port 8000
```

* API docs: <http://127.0.0.1:8000/docs>
* Health: <http://127.0.0.1:8000/api/health> — reports which services are configured

## Test

```bash
.venv/bin/python -m pytest
```

No test touches the network. External services are stubbed with `respx`
against fixtures in `tests/fixtures/` that follow the response shapes recorded
in `../docs/research/`.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/parcels/resolve` | Address, coordinate, or `gemarkung` + `flurstuecksnummer` (or `zaehler`/`nenner`) → parcels as GeoJSON (EPSG:4326), their union, and a plausibility verdict |
| POST | `/api/listings/extract` | `{url}` or `{text}` → listing fields as suggestions |
| POST | `/api/housetypes/extract` | `{url}` → house-type fields as suggestions |
| GET | `/api/landvalue?lat=&lon=` | Land reference value, zone, reference date, source |
| POST | `/api/geocode` | Free text → up to 5 coordinate candidates with the labels that were matched |
| POST | `/api/reachability` | Origin + destinations + modes → duration and route geometry per pair |
| POST | `/api/nearby` | Origin → nearest school, park, tram/S-Bahn/bus stop … per category, ranked by walking time |
| GET | `/api/tiles/{layer}/{z}/{x}/{y}.png` | Cached proxy for the GeoSN WMS (`dop`, `webatlas`, `alkis`) |
| GET | `/api/basemap/style.json` | MapLibre style, every URL in it rewritten onto this API |
| GET | `/api/basemap/{path}` | Everything the style then asks for: TileJSON, vector tiles, glyphs, sprites |
| GET | `/api/health` | Which services are configured |

### Notes that matter when using the API

* **A plot is a set of parcels.** `/api/parcels/resolve` always answers with the
  individual parcels *and* their union. The union's `flaeche_amtlich_m2` is the
  sum of the official ALKIS `flaeche` attributes, never the polygon area;
  `flaeche_berechnet_m2` travels alongside for shape analysis only.
* **Extracted values are suggestions.** Every field arrives as
  `{wert, quelle_url, bestaetigt: false}` and needs a human confirmation before
  it should be planned with. Contact details are not extracted at all.
* **Coordinates.** Answers are WGS84; lengths and areas are computed in
  EPSG:25833 before reprojection.
* **Portals.** `immobilienscout24.de` is not requested at all (server-side
  retrieval answers 401) and the API replies with a hint to use the paste
  field. `kleinanzeigen.de` is read from its `og:latitude`/`og:longitude` meta
  tags, which saves both the model call and the geocoding step.
* **Extraction takes two provider calls**, not one: fetching and structuring
  cannot share a request, see `app/services/llm.py`.
* **Errors carry a German sentence in `detail`**, and that sentence says what
  the user can do now -- "Der Katasterdienst … ist derzeit nicht erreichbar.
  Das Flurstück lässt sich auch von Hand eintragen: …". The frontend shows
  `detail` and nothing else, so nothing else may be needed to act. A 422 also
  carries `felder[]` with the machine-readable paths.

## Resolving a parcel by its number

The official geoportal prints one **Flurstücksnummer** per parcel -- `476`,
`85/1`, `41/e` -- while ALKIS stores it in two attributes. Both spellings go in:

```jsonc
{ "gemarkung": "140415", "flurstuecksnummer": "604/2" }   // as printed
{ "gemarkung": "140415", "zaehler": 604, "nenner": "2" }  // as ALKIS stores it
```

`gemarkung` is the district name or its number; the same parcel number exists
in every district, so it is required. Sending both spellings at once is a 422,
as is a number that does not parse -- with a German message that shows what a
valid one looks like.

### The Gemarkungsschlüssel has two spellings, and only one is in ALKIS

The Geoportal prints the same district two different ways depending on the
layer being queried. For Moritzburg, parcel 1:

| Kartenebene | Gemarkungsschlüssel |
|---|---|
| `Flurstueck` | `3044` |
| `Gemarkung` | `143044`, Gemarkungsname Moritzburg |

ALKIS only knows the second. **A four-digit key is therefore expanded to six
before the request goes out** — `14` is Saxony's Land prefix — and the answer
says so in `hinweis`. Verified against `ave:KatasterBezirk` on 29.08.2026: all
**5 339** Saxon Gemarkungen have a six-digit `schluessel`, every single one
begins with `14`, and their four-digit tails are all distinct, so the expansion
is unambiguous and is done up front rather than as a retry after an empty
result.

Keys **shorter** than four digits do not occur officially — the service pads
them (Borna is `0101`, and 183 of the 5 339 districts start with a zero) — but
a key that has been through a spreadsheet or a number field has lost the
padding, so one to three digits are zero-padded as well. No valid
Gemarkungsnummer is below `0101`, so padding can only ever turn a dead input
into the right one. Five or more digits, and anything non-numeric, are passed
through untouched.

```jsonc
{ "gemarkung": "3044",       "flurstuecksnummer": "1" }  // -> 143044, 34 799 m²
{ "gemarkung": "101",        "flurstuecksnummer": "1/3" } // -> 140101, Borna
{ "gemarkung": "Moritzburg", "flurstuecksnummer": "1" }  // name, never expanded
```

A wrong key still 404s, and the German sentence names the key that was actually
searched plus the six-digit rule, so the next attempt is an informed one.

**The denominator is text, not a number.** Letter denominators are in regular
use: Gemarkung 140415, number 604 answers with `604/1`, `604/2`, `604/3`,
`604/b` and `604/c` (live, 29.08.2026). `nenner` therefore accepts a string; an
integer is accepted too and normalised.

A number **without** a denominator does not filter on one, so `604` finds all
five of those parcels and unions them. That union is real -- a plot is a set of
parcels -- but here it is an artefact of an incomplete key, so the answer
carries a `hinweis` naming the parcels it found and asking for the full number.


## An address alone is not a plot

Resolving an address hands ALKIS one point and keeps whatever parcel covers it.
For a street address that parcel is the plot. For a **district** address it is
whatever the geocoder's point fell on, and the answer looks exactly as official
either way:

```console
$ curl -s -X POST http://127.0.0.1:8000/api/parcels/resolve \
    -H 'content-type: application/json' \
    -d '{"address":"Plaußig-Portitz, 04349 Leipzig"}'
```

lands on parcel `140428___00165000101`: 21 609 m², 163 boundary points, a
1 594 × 30 m strip along Tauchaer Straße. The listing that address came from
describes a **908 m²** building plot.

`/api/parcels/resolve` therefore takes an optional **`expected_area_m2`** — the
plot area the listing states — and every answer carries a `plausibility` block.
It is never an error and never a filter: a caller who really wants that parcel
still gets it, in full.

```jsonc
{ "address": "Plaußig-Portitz, 04349 Leipzig", "expected_area_m2": 908 }
```

```jsonc
"plausibility": {
  "plausible": false,
  "issues": ["area_too_large", "shape_atypical", "address_is_not_a_street_address"],
  "expected_area_m2": 908,
  "flaeche_amtlich_m2": 21609.0,
  "area_factor": 23.8,
  "longest_extent_m": 1594.4,
  "shortest_extent_m": 30.3,
  "elongation": 52.67,
  "warning": "Das gefundene Flurstück ist mit 21.609 m² rund 24-mal so groß wie …"
}
```

`issues` is what the frontend switches on; `warning` is the same finding as one
German sentence to show prominently. `plausible: true` with an empty `issues`
is the "this is your plot" case. Nothing is derived from a missing input:
without `expected_area_m2`, `area_factor` stays `null` — the shape and the kind
of geocoder match still answer on their own, which is what catches a district
address that arrives without a listing area.

### The three checks and where their thresholds come from

Not from taste: from a live ALKIS sample of **14 286 parcels** across six Saxon
places (Plaußig-Portitz, Moritzburg, Leipzig-Holzhausen, Wurzen, Radebeul,
Freiberg), each joined to its official land use from `ave:NutzungFlurstueck`,
taken 29.08.2026. 7 947 of them are used purely as `Wohnbaufläche` — building
land.

| Check | Fires when | Grounding |
|---|---|---|
| `area_too_large` | official area ≥ **4 ×** `expected_area_m2` | Real building parcels: median 572 m², 95 % under 1 790 m², 99 % under 4 384 m². Against a 908 m² listing the rule fires on 1.5 % of them but on 65 % of the parcels a random point hits. |
| `area_too_small` | official area ≤ **0.5 ×** `expected_area_m2` | Weaker evidence on purpose: a plot is a set of parcels, so an address resolving to one of several is normal. Worded as "parcels may be missing", not as "wrong land". |
| `shape_atypical` | longest extent > **200 m** *and* > **5 ×** the width | Building parcels have a median longest extent of 36 m, a 99th percentile of 111 m, and **none of the 7 947 exceeds 464 m**. Only 4 (0.05 %) meet both conditions, three of them 440–520 m² slivers along a street. |
| `address_is_not_a_street_address` | the geocoder matched a place or a stop, not a house number | MOTIS answers "Plaußig-Portitz, 04349 Leipzig" with `type: PLACE`. An Ortsteil is not a plot, and this needs no listing area to say so. |

The extents are the sides of the **minimum rotated rectangle**, not of the
axis-aligned envelope: the Portitz field runs diagonally and measures
1 583 × 198 m as an envelope, which hides the strip, against 1 594 × 30 m
rotated. A result in several pieces is measured on its largest piece.

Why a district address lands on a field at all: in the same sample, a point
dropped at random hits a parcel of **9 631 m² median** area — fifteen times the
unweighted median of 630 m². What a coordinate hits is decided by area, not by
count.


## The basemap proxy

MapLibre would otherwise load its style, tiles, glyphs and sprites straight
from `tiles.openfreemap.org`. That fails wherever the browser has no route to
the internet, so the frontend points at `/api/basemap/style.json` instead:

```js
const KARTENSTIL = "/api/basemap/style.json";
```

What the endpoint does:

* fetches `${BASEMAP_UPSTREAM_URL}/${BASEMAP_STYLE_PATH}` and rewrites every
  absolute upstream URL in the document onto `BASEMAP_PUBLIC_PREFIX` --
  `sources[*].url`, `sources[*].tiles[]`, `glyphs` and `sprite` in both of its
  spellings (a string, or a list of `{id, url}`);
* the same rewrite runs on every JSON answer of the passthrough, because the
  TileJSON behind `sources[*].url` names its tile URLs absolutely too;
* URLs inside prose stay put -- the `attribution` HTML keeps its links to
  openfreemap.org and openstreetmap.org, which is where they belong.

Everything the map then asks for goes through `GET /api/basemap/{path}`, which
hands the upstream's `Content-Type` and `Content-Encoding` on unchanged. Vector
tiles and glyph ranges arrive gzip-compressed and are **not** decompressed on
the way through; the raw byte stream travels with its encoding header, so the
browser does the one decompression there is. Every answer is cached on disk
under `${APP_CACHE_DIR}/basemap` for `BASEMAP_CACHE_TTL_S` (7 days); tile
requests are far too numerous for the cache to be optional.

Only paths below the configured upstream are ever fetched: an absolute target,
a protocol-relative one and any `..` segment are refused with a German 400, so
this is a proxy and not an open redirect.

Live check, 29.08.2026 (`curl` against a local instance):

| Request | Result |
|---|---|
| `/api/basemap/style.json` | 200, valid JSON, 43 kB, **no** `tiles.openfreemap.org` left in it |
| `/api/basemap/planet` | 200, TileJSON, `tiles[]` rewritten to `/api/basemap/planet/…/{z}/{x}/{y}.pbf` |
| `/api/basemap/planet/20260823_080002_pt/14/8798/5484.pbf` | 200, 14 065 bytes, `content-encoding: gzip`, 19 166 bytes decompressed |
| the same tile again | 200, `X-Cache: HIT`, 0.47 s → 0.002 s |
| `/api/basemap/fonts/Noto%20Sans%20Regular/0-255.pbf` | 200, `application/x-protobuf`, gzip |
| `/api/basemap/sprites/ofm_f384/ofm.json` / `.png` / `@2x.png` | 200 (18 kB / 49 kB / 119 kB) |

One thing to know: OpenFreeMap labels vector tiles
`application/vnd.mapbox-vector-tile`, not `application/x-protobuf`. Both are in
use for MVT and MapLibre reads the body either way; the header is passed
through as received rather than rewritten.

## Geocoding: text to coordinate

`POST /api/geocode` turns a typed destination ("Arbeit: Bahnhof Wurzen") into
coordinates for `/api/reachability`.

```jsonc
// Request
{
  "text": "Alte Dorfstraße 12, 04808 Wurzen",
  "lat": 51.36, "lon": 12.73        // optional: rank hits near this point higher
}
```

```jsonc
// Answer (200), at most five candidates, best first
{
  "treffer": [
    { "lat": 51.350145, "lon": 12.7335395, "name": "Alte Dorfstraße 12",
      "beschreibung": "04808 Wurzen, Dehnitz, Sachsen", "art": "adresse" },
    { "lat": 51.333421, "lon": 12.8552319, "name": "Dorfstraße 12",
      "beschreibung": "04808 Wurzen, Kühren-Burkartshain, Sachsen", "art": "adresse" }
  ],
  "hinweis": "Die Koordinaten stammen aus dem Routing-Geocoder …",
  "quelle": "MOTIS / Transitous (DELFI-GTFS, OpenStreetMap)"
}
```

* `art` is `adresse`, `haltestelle`, `ort` or `sonstiges`.
* `beschreibung` carries postcode, municipality, part of the municipality and
  **federal state**. The state is in there on purpose: this geocoder's most
  common failure is answering a Saxon street name with a village in Bavaria,
  and that is only visible if the state is on screen.
* `lat`/`lon` in the request are a bias, not a filter. Live: "Am Kirschberg"
  alone ranks Moosthenning (Bayern) first; with the plot's coordinate it ranks
  "Leipzig, Am Kirschberg" first.
* A missing half of the bias is a 422.

**The geocoder practically never answers "nothing found".** Nonsense input
comes back as five unrelated stops all over Germany with a 200, so the 404 is
rare in practice. Treat `treffer` as candidates to be confirmed, never as a
match -- show the picker, and offer setting the point on the map instead. The
coordinate is not an official Hauskoordinate either way; that is what `hinweis`
says.

### This is also the picker for a listing address

The listing flow needs nothing beyond this endpoint. `POST /api/geocode` with
the listing's address, show the five candidates, then
`POST /api/parcels/resolve` with `{lat, lon, expected_area_m2}` for the one the
user picks. `art` already separates a house number (`adresse`) from an Ortsteil
(`ort`) or a stop (`haltestelle`), which is exactly the distinction a district
address turns on, and `beschreibung` carries the federal state.

Resolving the parcels under all five candidates up front was considered and
dropped: it costs five ALKIS requests to throw four of them away, and the
parcel under a candidate does not help pick between candidates -- the label and
the state do. The plausibility block on the one chosen candidate is where the
parcel gets judged.

Live check against Transitous, 29.08.2026 (cold cache):

| Query | Time | First hit |
|---|---|---|
| `Bahnhof Wurzen` | 0.94 s | Wurzen, Bahnhof (Bus) — 04808 Wurzen, Sachsen |
| `Alte Dorfstraße 12, 04808 Wurzen` | 1.95 s | Alte Dorfstraße 12 — 04808 Wurzen, Dehnitz, Sachsen |
| `Am Kirschberg` | 1.08 s | Am Kirschberg — 84164 Moosthenning, **Bayern** |
| `Am Kirschberg` + bias 51.34/12.37 | 1.07 s | Leipzig, Am Kirschberg — 04209 West, Sachsen |


## Reachability: the exact request and answer

`POST /api/reachability`. Modes are `car`, `bike`, `walk`, `transit` and
`bike_transit` (bike to the first stop, public transport from there). Every
destination is crossed with every mode, so the answer has
`len(destinations) × len(modes)` entries, each keyed by `destination_id` and
`mode`. `time` is the departure time and may be left out, in which case MOTIS
routes from now.

```jsonc
// Request
{
  "origin":       { "lat": 51.2829, "lon": 12.4628 },
  "destinations": [
    { "id": "zentrum", "name": "Leipzig, Innenstadt", "lat": 51.3397, "lon": 12.3731 }
  ],
  "modes": ["car", "bike", "transit", "bike_transit"],
  "time": "2026-08-31T08:00:00+02:00"        // optional
}
```

```jsonc
// Answer (200), one entry per destination × mode
{
  "ergebnisse": [
    {
      "destination_id": "zentrum",
      "mode": "car",
      "erreichbar": true,
      "duration_s": 771,
      "umstiege": 0,
      "startzeit":    "2026-08-29T20:14:00Z",
      "ankunftszeit": "2026-08-29T20:26:00Z",
      "geometry": { "type": "LineString", "coordinates": [[12.46316, 51.2831], "…"] },
      "teilstrecken": [ { "mode": "CAR", "duration_s": 771, "von": "START", "nach": "END" } ],
      "hinweis": null
    },
    {
      "destination_id": "zentrum",
      "mode": "transit",
      "erreichbar": true,
      "duration_s": 2100,
      "umstiege": 1,
      "geometry": { "type": "LineString", "coordinates": [[12.462983, 51.282633], "…"] },
      "teilstrecken": [
        { "mode": "WALK", "duration_s": 180,  "von": "START",                   "nach": "Leipzig, Schwarzes Ross" },
        { "mode": "BUS",  "duration_s": 1080, "von": "Leipzig, Schwarzes Ross", "nach": "Leipzig, Johannisplatz" },
        { "mode": "TRAM", "duration_s": 120,  "von": "Leipzig, Johannisplatz",  "nach": "Leipzig, Augustusplatz" },
        { "mode": "WALK", "duration_s": 540,  "von": "Leipzig, Augustusplatz",  "nach": "END" }
      ]
    }
  ],
  "quelle": "MOTIS / Transitous (DELFI-GTFS, OpenStreetMap)"
}
```

Notes for the caller:

* `geometry` is GeoJSON, so `[lon, lat]` -- the reverse of `origin`/`destinations`.
* A destination with no connection comes back as `erreichbar: false` with
  `duration_s: null` and a German `hinweis`. That is a normal answer, not an
  error: the other pairs in the same call still carry their result.
* `teilstrecken[].mode` is MOTIS' own vocabulary (`WALK`, `BUS`, `TRAM`,
  `CAR`, `BIKE`), upper case and not the same set as the request's `modes`.
* `umstiege` is 0 for direct modes and for a `bike_transit` leg without a
  change.

Live check against Transitous, 29.08.2026, 51.2829/12.4628 → 51.3397/12.3731
(Leipzig-Paunsdorf to the city centre), cold cache, one request per mode:

| Mode | Response time | Travel time | Legs |
|---|---|---|---|
| `car` | 2.72 s | 12.8 min | 1 |
| `bike` | 1.43 s | 41.1 min | 1 |
| `transit` | 1.24 s | 35.0 min | 5 (walk, bus, walk, tram, walk), 1 change |
| `bike_transit` | 1.46 s | 37.0 min | 3 |

All four modes in one request: 6.30 s cold (`MOTIS_MAX_CONCURRENCY=2` keeps the
load on the volunteer instance low), 0.013 s from the cache. The decoded route
geometry lands between 12.371–12.464 E and 51.282–51.340 N, i.e. on Leipzig --
the check that `legGeometry` was read with precision 6.


## "Wie weit ist die nächste Schule?" — `POST /api/nearby`

One coordinate in, the nearest one or two of each category out, **ranked by
walking time and never by air distance**. The two orders disagree from the
first position: at the Liebertwolkwitz test plot the Oberschule is 254 m away
as the crow flies and a 6-minute walk, while the Grundschule is 300 m away and
an 11-minute walk — 843 m of footpath for 300 m of air. In
Dresden-Johannstadt the nearest
playground by air, 172 m off, cannot be walked to at all, because the Elbe is
in between and the crossing there is a ferry.

```jsonc
// Request — every field but `origin` has a default
{
  "origin": { "lat": 51.2828, "lon": 12.4630 },
  "kategorien": ["schule", "park", "tram", "sbahn", "bus", "bahnhof"],  // default: all ten
  "modus": "walk",                 // walk | bike
  "umkreis_m": 2000,               // air-distance pre-filter, 200…15000
  "treffer_je_kategorie": 2,       // 1…10
  "linien": false                  // also ask which lines call at each stop
}
```

```jsonc
// Answer (200)
{
  "treffer": [
    { "kategorie": "schule", "name": "Geschwister Scholl Schule Liebertwolkwitz — Oberschule …",
      "art": "Oberschule", "lat": 51.284419, "lon": 12.460414, "erreichbar": true,
      "duration_s": 362, "distance_m": 393, "luftlinie_m": 254,
      "quelle": "osm", "osm_id": "N10985287011", "stop_id": null, "linien": null },
    { "kategorie": "bahnhof", "name": "Leipzig-Liebertwolkwitz", "art": "Regionalbahn, Bus",
      "lat": 51.283970, "lon": 12.469248, "erreichbar": true,
      "duration_s": 630, "distance_m": 742, "luftlinie_m": 454,
      "quelle": "motis", "osm_id": null, "stop_id": "de-DELFI_de:14713:8012228", "linien": null }
  ],
  "kategorien": [
    { "kategorie": "schule", "verfuegbar": true,  "anzahl": 2, "hinweis": null },
    { "kategorie": "sbahn",  "verfuegbar": true,  "anzahl": 0,
      "hinweis": "Im Umkreis von 2.000 m wurde nichts gefunden." },
    { "kategorie": "park",   "verfuegbar": false, "anzahl": 0,
      "hinweis": "Für diese Kategorie ist auf dem Server kein Datenbestand eingerichtet — …" }
  ],
  "datenstand": "2026-08-22T20:21:02Z",
  "quelle": "OpenStreetMap (ODbL) und MOTIS / Transitous (DELFI-GTFS)",
  "hinweis": "Die Gehzeiten stammen aus dem Fußwegenetz von OpenStreetMap …"
}
```

### The ten categories, and where each one comes from

| Kategorie | Source | Note |
|---|---|---|
| `tram`, `sbahn`, `bus`, `bahnhof` | **MOTIS timetable**, live | Works with no local data at all |
| `schule`, `kindergarten`, `park`, `spielplatz`, `supermarkt`, `arzt` | **Local OSM index**, built offline | Answers "kein Datenbestand" until the index is built |

The stop categories are split on each stop's own `modes` array, which MOTIS
derives from the GTFS feeds. That is the whole reason the transit half does not
use OpenStreetMap: **there is no S-Bahn tag in Saxony** — `service=suburban` has
zero objects statewide, `station=light_rail` zero, and the S-Bahn platforms of
the Leipzig City-Tunnel are indistinguishable from any other railway halt. MOTIS
hands it over as `"modes": ["SUBURBAN"]` and separates `Leipzig Markt`
(S-Bahn) from `Leipzig, Markt (Bus)` in one field.

`bahnhof` is `REGIONAL_RAIL`, `REGIONAL_FAST_RAIL`, `LONG_DISTANCE`,
`HIGHSPEED_RAIL` or `NIGHT_RAIL`. Ferries, funiculars and the aerial lifts are
deliberately not their own category, although the data carries them.

### `kategorien[]` is the point of the answer, not decoration

`treffer` alone cannot say why a category is empty, and the two reasons are
opposite statements:

* `verfuegbar: false` — **this server holds no such data.** The index has not
  been built here. Never render that as "es gibt hier keine Schule".
* `verfuegbar: true, anzahl: 0` — the data was searched and the radius really
  is empty.

`/api/health` reports the same thing under the service name `poi`, so the
frontend can tell the two apart before it asks anything.

### Building the POI index

```bash
cd backend
.venv/bin/pip install -e ".[poi]"                    # pyosmium, only for this step
.venv/bin/python scripts/build_poi_index.py --download
```

That fetches `sachsen-latest.osm.pbf` from Geofabrik (~450 MB), verifies it
against the published MD5, converts it and writes `data/poi-sachsen.json`
(≈ 22 600 places, 2–3 MB; `.json.gz` also works). An extract already on disk is
used directly:

```bash
.venv/bin/python scripts/build_poi_index.py sachsen-latest.osm.pbf
```

The output is a build artefact — `data/` is git-ignored — and wants refreshing
on the order of once a quarter. `datenstand` in the answer is the extract's own
replication timestamp, so the UI can say how old the data is.

**Why offline and not a query per request.** The Overpass manual names "setting
up an app for more than just OSM mappers and relying on the public instances as
backend" as problematic behaviour in so many words, and rate-limits per IP —
ours, shared by every user of the app. A build job that runs quarterly is inside
that policy; a request-time dependency is not, and caching does not change the
shape of the usage. The full argument, with the measurements, is in
`../docs/research/poi.md` § 2.2.

### The tag decisions, and why they are not obvious

| Included | Left out on purpose |
|---|---|
| `amenity=school` | `driving_school`, `music_school`, `language_school`, `college`, `university` |
| `leisure=park`, `nature_reserve`, `landuse=recreation_ground`, `village_green` | **`leisure=garden`** and `landuse=allotments` |
| `leisure=playground` | playgrounds with `access` = `private`/`no`/`customers`/`permit` |
| `shop=supermarket`, `shop=convenience` | `shop=bakery`, `shop=greengrocer` |
| `amenity=doctors`, `amenity=clinic` | `healthcare=doctor`, `amenity=hospital` |
| `amenity=kindergarten`, `amenity=childcare` | — |

`leisure=garden` is Saxony's most common green tag — 12 583 objects, more than
parks and recreation grounds together — and its `garden:type` values are
`residential` 3 689, `private` 3 049 and `public` **26**. These are the front
gardens of terraced houses. `healthcare=doctor` is a second tag on the same node
as `amenity=doctors`, not a second surgery, so unioning the two double-counts
every practice.

**The school type is read off the name**, because nothing else carries it:
`school:DE` has zero objects in Saxony and `isced:level` covers under a fifth of
schools in two incompatible spellings (`2;3` and `2-3` both occur, and one
object has value `9`). `art` is therefore a hint next to the name, not a fact,
and the note in `hinweis` says so.

**One school is often three objects** — the named Grundschule node, the named
Oberschule node, and the unnamed way of the shared grounds. Entries of the same
category within 60 m are collapsed, keeping the named one; two *differently*
named schools at one address stay two schools.

### What one answer costs

Two upstream requests for all ten categories, whatever the number of hits:

1. `GET /api/v6/map/stops?min=lat,lon&max=lat,lon&grouped=true` — one box.
2. `POST /api/v1/one-to-many` — every candidate of every category in **one**
   body, capped at the server's own limit of 128.

`one-to-many` costs the same for 128 destinations as for one (~150 ms both,
measured), while eight separate `/api/v6/plan` calls at `MOTIS_MAX_CONCURRENCY=2`
take 1 523 ms and cost Transitous eight requests instead of one. The candidate
budget is filled round-robin across the requested categories, so a category with
two candidates hands its unused places back rather than starving one with
twenty.

Live against Transitous, 29.08.2026, plot 51.2828/12.4630, `umkreis_m: 2000`,
two hits per category:

| Request | Cold | Warm |
|---|---|---|
| all ten categories, index present | **1.70 s** | 0.005 s |
| all ten categories, no index (four transit categories answer) | 3.35 s | 0.005 s |
| four transit categories, `linien: true`, Leipzig centre | 5.89 s | — |

`linien` is opt-in for that last row's reason: it is one extra request per stop,
against a volunteer service that asks to be treated lightly. A hit whose lines
were not asked for carries `linien: null`, never `[]` — an empty list would
claim that nothing calls there.

### Traps that are already handled here

* **`one-to-many` needs a POST.** Repeated `many=` parameters on a GET are
  silently collapsed: three of them come back as one duration, and reordering
  them turns the same request into `{"error":"missing parameter"}`. The POST
  body takes a JSON array and answers all of them, positionally aligned.
* **The coordinate separator is a semicolon**, `lat;lon`. A comma is rejected
  with "is not a valid geo coordinate".
* **`maxMatchingDistance` is required** in that body — leaving it out is
  answered with `key maxMatchingDistance not found`.
* **An unreachable destination is `{}`**, not an error and not a null duration.
  It comes back as `erreichbar: false` with its air distance and a German note,
  because "die nächste Schule liegt jenseits des Flusses" is worth showing.
* **`map/stops` takes lat,lon** in `min`/`max`, and `grouped=true` is not
  optional: without it the same physical stop appears once per GTFS feed — 115
  entries instead of 27 over Leipzig centre.
* **The `modes` query parameter of `map/stops` is parsed and then ignored.**
  It validates the enum (`modes=NONSENSE` is an error) and returns the same
  stops either way, so the filtering happens on each stop's own `modes` array.


## Environment variables

All settings have defaults; see `.env.example` for the full list with comments.

| Prefix | Variables | Purpose |
|---|---|---|
| `APP_` | `CORS_ORIGINS`, `CACHE_DIR`, `USER_AGENT`, `PORTAL_USER_AGENT`, `HTTP_TIMEOUT_S` | Process-wide settings. `USER_AGENT` must carry a real contact address — the Transitous usage policy requires it. |
| `ALKIS_` | `WFS_URL`, `VERSION`, `SRID`, `MAX_FEATURES`, `POINT_BUFFER_M`, `CACHE_TTL_S` | ALKIS WFS of the GeoSN |
| `BORIS_` | `WMS_URL`, `LAYER`, `PORTAL_URL`, `CACHE_TTL_S` | BORIS WMS. The URL carries the reference year (`boris_2026`) — check it once a year. |
| `MOTIS_` | `BASE_URL`, `TIMEOUT_S`, `MAX_CONCURRENCY`, `MAX_DIRECT_TIME_S`, `MAX_PRE_TRANSIT_TIME_S`, `CACHE_TTL_S`, `STOPS_CACHE_TTL_S`, `MATRIX_CACHE_TTL_S` | Routing, geocoding, stops and walking-time matrices |
| `NEARBY_` | `POI_INDEX_PATH`, `MAX_CANDIDATES`, `MAX_TIME_S`, `MAX_MATCHING_DISTANCE_M`, `BBOX_GRID_DEG`, `MAX_LINE_LOOKUPS` | `/api/nearby`. Only the POI index needs configuring; stops come from the MOTIS above. |
| `TILES_` | `DOP_URL`, `DOP_LAYERS`, `WEBATLAS_URL`, `WEBATLAS_LAYERS`, `ALKIS_URL`, `ALKIS_LAYERS`, `CRS`, `IMAGE_FORMAT`, `TILE_SIZE`, `TRANSPARENT`, `CACHE_TTL_S`, `MAX_ZOOM` | WMS proxy |
| `BASEMAP_` | `UPSTREAM_URL`, `STYLE_PATH`, `PUBLIC_PREFIX`, `REWRITE_HOSTS`, `CACHE_TTL_S`, `TIMEOUT_S` | Vector basemap proxy. Point `UPSTREAM_URL` at your own tile server to drop OpenFreeMap. |
| `LLM_` | `BASE_URL`, `API_KEY`, `MODEL`, `FETCH_ENGINE`, `TIMEOUT_S`, `MAX_CONTENT_TOKENS` | Extraction provider. No provider is hard-wired; switching one is a line in `.env`. Without `API_KEY` the extraction endpoints answer 503 and the rest of the API keeps working. |

## Caches

Everything lands under `APP_CACHE_DIR` (default `.cache/`), one subdirectory per
service. The POI index is **not** among them: it is a build artefact under
`data/`, read once at startup, and nothing about `/api/nearby` reaches
OpenStreetMap at request time. Parcel, land-value, tile, basemap and routing
entries expire after their `CACHE_TTL_S`; LLM extractions are keyed by normalised URL and kept
indefinitely, because a house type does not change from one week to the next
and every fetch costs money. Deleting the directory is safe.

## Licence and attribution

Official data: © GeoSN, dl-de/by-2-0. Routing, stops and lines via
Transitous/MOTIS (DELFI-GTFS, OpenStreetMap) — link to
<https://transitous.org/sources/> in the UI. The POI index behind `/api/nearby`
is derived from OpenStreetMap and carries the same ODbL as the basemap, so
"© OpenStreetMap-Mitwirkende" belongs wherever those hits are shown, not only
on the map. Basemap via OpenFreeMap and OpenMapTiles from OpenStreetMap data
(ODbL); the attribution must stay visible on the map even though the tiles arrive
through our own proxy. Nothing here is legal advice or a building-code assessment.
