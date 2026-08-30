# "How far is the nearest X" — points of interest for Saxony

**Research date: 2026-08-29.** Written in English: this is developer
documentation, only the user interface is German.

> **Legend**
> ✅ **VERIFIED LIVE (2026-08-29)** — a request was made from this shell and its
> answer read. Exact URL and measured timing are given.
> 📘 **FROM SPEC/DOCS** — taken from an official OpenAPI document, manual or
> policy page that was itself fetched, but the behaviour was not exercised.
> ⚠️ **NOT VERIFIED** — stated as an open question, not as a fact.

All timings were measured through this sandbox's HTTPS proxy. The floor is
`GET https://api.transitous.org/api/v1/health` at a **median of 148 ms** (n=5),
so read every number below as "148 ms of transport plus the service's own work".

---

## 1. Recommendation

**Use two sources, not one, and rank by walking time, not by air distance.**

| What the user asks | Source | Why |
|---|---|---|
| nearest tram / S-Bahn / bus stop / station | **MOTIS `/api/v6/map/stops?grouped=true`** | It knows which stops are *served*, and by what mode, from the timetable. OSM cannot answer this in Saxony at all (§ 4.3). |
| lines serving that stop | **MOTIS `/api/v6/stop?stopId=…`** | Returns the actual routes with short name, mode and operator. |
| nearest school / kindergarten / park / playground / supermarket / doctor | **A Saxony OSM extract held by our backend** | The public Overpass instances forbid exactly our use (§ 2.2); the reachable OSM geocoders index by name or address, and only 11.8 % of Saxon playgrounds have a name — Photon found 5 of the 33 that exist within 1 km of a Dresden test point (§ 5). |
| how far is it, really | **MOTIS `/api/v1/one-to-many`, one call** | Walking time to up to **128** destinations in **one** round trip, ~148 ms, identical numbers to `/plan` (§ 7). |

**How many candidates to route to: all of them, up to 128.** This is the
finding that reorganises the design. Routing to 128 candidates costs the same
as routing to one — 148 ms median, both — because `one-to-many` is a single
request. There is no reason to pre-filter to "the 3 nearest by air" and then
route: take the 15–20 nearest by air *per category*, pool every category into
one request, and rank the answers by walking time. Air distance is used only to
cut the candidate list down to 128, never shown to the user.

Do **not** implement this as N calls to `/api/v6/plan`. Measured: 8 `/plan`
calls at the project's current `max_concurrency = 2` take **1523 ms** and cost
Transitous 8 requests; the equivalent `one-to-many` call takes **148 ms** and
costs 1. Transitous asks us to be "light on our resources" (§ 8) — this is the
difference between honouring that and not.

Keep `/api/v6/plan` for exactly one thing: after the user picks a winner, one
call to draw its route geometry. `one-to-many` returns duration and distance but
no geometry.

### What this costs to build

- Transit: no new data, no new dependency. Two MOTIS endpoints we do not use yet.
- POIs: a build step that turns a Saxony OSM extract into a point file, plus an
  in-process spatial index. **22 622 features** for the whole tag set below in
  all of Saxony (§ 4, counted from taginfo) — roughly 2–3 MB of JSON. It fits in
  memory; it does not need PostGIS. (Worth noting: `CLAUDE.md` says the backend
  is "FastAPI + PostGIS", but `backend/pyproject.toml` declares no database
  driver and no module imports one. There is no database today, and this feature
  does not require introducing one.)

---

## 2. Overpass API — the obvious candidate, and why it is the wrong one

### 2.1 Which public instances exist, and which answered ✅

Every request below used `-A "where2build-research/0.1 (+https://github.com/;
kontakt@example.org)"`.

| Instance | Result |
|---|---|
| `https://overpass-api.de/api/status` | ❌ TLS tunnel closed after 6–9 s, 5 attempts, `curl` and `httpx` alike |
| `https://lz4.overpass-api.de/api/status` | ❌ same |
| `https://z.overpass-api.de/api/status` | ❌ same |
| `https://overpass.kumi.systems/api/status` | ❌ timeout, 0 bytes, 25–40 s, 4 attempts |
| `https://overpass.private.coffee/api/status` | ❌ HTTP 502 from the gateway once, then timeouts |
| `https://overpass.openstreetmap.fr/api/status` | ✅ **HTTP 403** in 0.49 s, body: `This service is only available to white-listed usages` |
| `https://overpass.osm.ch/api/interpreter` | ✅ HTTP 200 — but a **Switzerland-only** extract |
| `https://overpass.osm.jp/api/status` | ❌ `SSL certificate problem: certificate has expired` |

The `overpass-api.de` failures are **this sandbox, not the service**. The proxy's
own log names the cause and the signature is identical to hosts that are known
good:

```
2026-08-29T21:52:47.090Z ws_closed_mid_exchange | overpass-api.de:443 |
  tunnel closed (code 1006, Connection ended) after 9s; 517 B sent, 39 B received
2026-08-29T19:34:19.202Z ws_closed_mid_exchange | tiles.openfreemap.org:443 | …
2026-08-29T20:33:47.550Z ws_closed_mid_exchange | cdn.jsdelivr.net:443       | …
```

`CLAUDE.md` already records that tile hosts are unreachable here. Overpass is
in the same bucket. **So: I could not run a Saxon Overpass query, and I say so
rather than pretending otherwise.** What I could do is verify the query *shape*
against the one instance that answered — with a Swiss coordinate, because that
is the only data it holds:

```bash
curl -sS -A "$UA" -X POST \
  -d 'data=[out:json][timeout:25];nwr["amenity"="school"](around:2000,46.9480,7.4474);out center;' \
  https://overpass.osm.ch/api/interpreter
# HTTP 200, 1.63 s, 51 521 bytes, 77 elements
```

```json
{"version": 0.6, "generator": "Overpass API 0.7.59.1 2a9d9642",
 "elements": [
   {"type":"node","id":429232021,"lat":46.9567601,"lon":7.4454367,"tags":{"name":"denk:mal",…}},
   {"type":"node","id":892826804,"lat":46.9520798,"lon":7.4385874,"tags":{"name":"Didac",…}},
   {"type":"node","id":1059571394,…,"tags":{"name":"Musikschule Konservatorium",…}}]}
```

`nwr[…](around:R,lat,lon); out center;` is the right form: `out center` gives
ways and relations a single representative coordinate, which is what a
"how far" query needs. Note the first three hits already show the noise problem
— a music school and two adult-education outfits under `amenity=school`. The
same query against Leipzig on that instance returns `"elements": []`, which is
how you can tell it is a Swiss-only extract and not a broken query.

### 2.2 What the usage policy actually says ✅

Fetched from `https://dev.overpass-api.de/overpass-doc/en/preface/commons.html`
(HTTP 200, 0.87 s). Verbatim:

> "The computational power currently has to be shared between the roundabout
> 30'000 daily users. […] Each of the Overpass API servers can fulfill about
> 1 million requests per day, and two servers listen on the address
> overpass-api.de."

> "Examples of problematic behaviour: […] **Setting up an app for more than just
> OSM mappers and relying on the public instances as backend.**"

> "In the last cast [*sic*], **only running your own instance sustainably serves
> your mission.**"

> "As a broad guideline to stay within safety margins, users are expected to send
> a maximum of about **10000 requests per day** and keep their download volume
> below about **1 GB per day**."

On rate limiting:

> "Requests usually are assigned by taking the IP address as the user. […] Every
> execution of a request occupies one of the slots available to the user, in
> particular for the full actual execution time plus a cool down time. […] during
> moments of high load the cool down time can be a multiple of the execution
> time." — "Requests stay enqueued up to 15 seconds on the server if not yet a
> slot is available to them."

**What that means for us — revised 2026-08-30.** The paragraph below read this
policy as a prohibition and concluded Overpass was out. That was too broad, and
the project owner said so: this is a prototype with a single user, and the same
policy page is explicit that occasional manual requests are fine. The line the
manual draws is around *relying on the public instances as the backend of a
deployed app* — which a one-user prototype is not. Overpass is therefore
available as a configurable source, with a self-hosted instance or the local
extract as the production answer. What follows is the original reasoning, kept
because the load argument is still the reason not to ship it that way.

Our tool would, once deployed, be "an app for more than just OSM
mappers relying on the public instances as backend". The manual names it as
problematic in so many words. A caching proxy does not fix this: it reduces the
count, but the shape of the usage is the thing the policy objects to, and the
rate limit is per *IP* — our server's single IP, shared by every user, is the
worst possible arrangement under a slot-and-cooldown scheme. It also makes the
service a hard dependency of a page load, on an endpoint whose documented
behaviour under load is to enqueue for 15 s and then shed.

The same page is, however, explicit that occasional manual requests are fine
("It is extremely unlikely that you will ever cause problems with manually put
requests"). **A quarterly build job that issues one query per category to
populate our own extract is squarely within the policy; a request-time
dependency is not.** That distinction is the whole basis of the recommendation.

No `User-Agent` requirement is stated in the Overpass manual, unlike Transitous
and the OSM API. Send a real one anyway.

### 2.3 The OSM main API is not an alternative ✅

`https://api.openstreetmap.org/api/0.6/map?bbox=…` does work from here and I used
it as ground truth (§ 4). It is not a candidate for production, on two counts.

Its policy (`https://operations.osmfoundation.org/policies/api/`, HTTP 200) says:

> "The editing API is provided in order to **edit** the map data, **not for
> read-only purposes or projects**. Clients may be blocked without notice […]"
> "Large or frequent data users must use the download service 'planet.osm'."
> "Valid User-Agent identifying application and version. […] Maximum of 2
> download threads."

And it has a hard size cap, verified:

```
GET …/map?bbox=12.3600,51.3300,12.3900,51.3500   → HTTP 400, 2.84 s
You requested too many nodes (limit is 50000). Either request a smaller area, or use planet.osm
```

A 3.3 × 2.2 km box over Leipzig city centre already exceeds it.

---

## 3. MOTIS / Transitous can answer the transit half directly ✅

This is the happiest finding of the research: the service we already route with
answers "nearest stop" better than OSM can, and it was not in
`docs/research/routing-motis.md` because that document's endpoint table predates
`/api/v6/stop`.

Spec source: `https://raw.githubusercontent.com/motis-project/motis/master/openapi.yaml`
(HTTP 200, 214 336 bytes). Note `api.transitous.org/openapi.yaml` is a 404 — the
spec only lives in the repo.

### 3.1 `/api/v6/map/stops` — stops in a box, with their modes ✅

```
GET https://api.transitous.org/api/v6/map/stops
      ?min=51.2648,12.4343&max=51.3008,12.4917&grouped=true
→ HTTP 200, 0.63 s, 16 stops
```

Around the plot at **51.2828, 12.4630** (Leipzig-Liebertwolkwitz — the address
`/api/v1/reverse-geocode` gives back is "Kirchstraße 2, 04288 Leipzig"), sorted
by air distance computed locally:

```
       61 m  Leipzig, Liebertwolkwitzer Markt           ['BUS']
      149 m  Leipzig, Schwarzes Ross                    ['BUS']
      245 m  Leipzig, Zur alten Sandgrube               ['BUS']
      406 m  Leipzig, Roßstr.                           ['BUS']
      454 m  Leipzig-Liebertwolkwitz                    ['REGIONAL_RAIL', 'BUS']
      …
     2016 m  Leipzig, Meusdorf                          ['TRAM', 'BUS']
     2536 m  Großpösna                                  ['REGIONAL_RAIL']
```

One object per stop, each carrying `stopId`, `name`, `lat`, `lon`, `importance`,
`tz` and **`modes`**. The mode list is derived from the GTFS feeds, so it says
what actually stops there. In Dresden the same call distinguishes correctly, and
even finds the Elbe ferry:

```
GET …/map/stops?min=51.0420,13.7520&max=51.0690,13.7880&grouped=true  → 0.90 s, 36 stops
      336 m  Dresden Trinitatisplatz         ['TRAM']
      643 m  DD Blasewitzer/Fetscherstraße   ['TRAM', 'BUS']
      751 m  Dresden Fährstelle Johannstadt  ['FERRY']
```

In Leipzig centre it separates the City-Tunnel S-Bahn stations from the tram
stops that share their name — something no OSM tag in Saxony can do (§ 4.3):

```
  Leipzig Markt                          ['REGIONAL_RAIL', 'SUBURBAN']
  Leipzig, Markt (Bus)                   ['BUS']
  Leipzig Wilhelm-Leuschner-Platz        ['REGIONAL_RAIL', 'SUBURBAN']
  Leipzig, Wilhelm-Leuschner-Platz (Tram/Bus)  ['TRAM', 'BUS']
  Leipzig Hbf   ['HIGHSPEED_RAIL','LONG_DISTANCE','COACH','REGIONAL_RAIL','SUBURBAN','TRAM','BUS']
```

**Two traps, both verified.**

1. **`grouped=true` is not optional in practice.** Without it the same Leipzig
   centre box returns **115** stops instead of **27** — the same physical stop
   appears once per GTFS feed with a different id:
   `de-DELFI_de:14713:10983::07`, `de-VBB_000000607101`,
   `eu-flixbus_206a3e42-…`, `pl-Polish-Trains_148445`, `al-ShowMeBus_station-267`.
   Deduplicating that yourself is a mistake you do not need to make.

2. **The `modes` query parameter is parsed but has no effect.** All of these
   return the identical 115 stops:

   ```
   …&modes=TRAM               → 115
   …&modes=TRAM&modes=SUBURBAN → 115
   …&modes=TRAM%2CSUBURBAN    → 115
   (no modes parameter)       → 115
   …&modes=NONSENSE           → {"error":"enum ModeEnum: unknown value NONSENSE"}
   ```

   It validates the enum and then ignores it. **Filter on the per-stop `modes`
   array yourself.** ⚠️ Whether this is a bug in the deployed version or intended
   behaviour, I could not establish.

### 3.2 `/api/v6/stop` — the lines serving a stop ✅

```
GET https://api.transitous.org/api/v6/stop?stopId=de-DELFI_de%3A14713%3A8010205
→ HTTP 200, 0.81 s, 30 679 bytes
```

```json
{"place": {"name":"Leipzig Hbf","stopId":"de-DELFI_de:14713:8010205","lat":51.34547,…},
 "routes": [
   {"routeId":"…|Bus|143:LVB_3","routeShortName":"143","routeLongName":"","mode":"BUS",
    "agencyId":"8872","agencyName":"Leipziger Verkehrsbetriebe","routeType":3}, …]}
```

133 routes at Leipzig Hbf: `BUS` 33, `COACH` 25, `TRAM` 21, `SUBURBAN` 18,
`REGIONAL_RAIL` 15, `LONG_DISTANCE` 14, `HIGHSPEED_RAIL` 7. `routeShortName` is
the line number a user recognises ("1", "11", "15"), `routeColor` /
`routeTextColor` are in the schema for the line badge. This is the answer to
"and which lines run there".

The endpoint also takes `center` + `radius` instead of `stopId`, but that form
is less useful than it looks: the response's `place` is only the echoed centre
(`{"name":"center","lat":51.2828,"lon":12.463,"vertexType":"NORMAL"}`) and the
`routes` array is a flat union over the radius, with no mapping back to
individual stops. **Use `map/stops` to find stops, then `stop?stopId=` per stop
the user expands.**

---

## 4. The OSM tag mapping, and where it fails in Saxony

Two independent sources of evidence, both fetched live:

- **taginfo, Saxony-only regional database** —
  `https://taginfo.geofabrik.de/europe:germany:sachsen/api/4/…` ✅
  Confirmed to be Saxony and nothing else:
  `{"name":"OpenStreetMap Taginfo Sachsen","description":"This is a <b>regional
  taginfo database</b> with data only for <b>Sachsen.</b>","area":"Sachsen"}`.
  This is the authoritative count for the whole state.
- **Raw OSM for nine Saxon boxes** via `api.openstreetmap.org/api/0.6/map` ✅ —
  Leipzig-Liebertwolkwitz, Leipzig centre, Leipzig-Grünau, Dresden
  Johannstadt/Neustadt, Dresden Neustadt, Chemnitz, Zwickau, Görlitz, and Göda
  in the rural Lausitz. Used for name coverage and duplication checks.

### 4.1 Proposed mapping

| Category (UI) | Include | Exclude, deliberately | Saxony count |
|---|---|---|---|
| `schule` | `amenity=school` | `amenity=driving_school` (347), `music_school` (123), `language_school` (30), `college` (123), `university` (132), `prep_school` (45) | 1 984 |
| `kindergarten` | `amenity=kindergarten`, `amenity=childcare` | — | 2 200 + 171 |
| `park` | `leisure=park`, `landuse=recreation_ground`, `landuse=village_green`, `leisure=nature_reserve` | **`leisure=garden`**, `landuse=allotments`, `landuse=forest` — see below | 3 517 + 684 + 546 + 389 |
| `spielplatz` | `leisure=playground` with `access` not in `private`/`customers`/`no` | — | 7 045 |
| `supermarkt` | `shop=supermarket`, `shop=convenience` | `shop=bakery` (a bakery is not a food shop for this purpose), `shop=greengrocer` | 1 798 + 640 |
| `arzt` | `amenity=doctors`, `amenity=clinic`; optionally `amenity=pharmacy` as its own category | `amenity=hospital` (a different question), `healthcare=doctor` **as a separate feature** — see below | 2 467 + 265 (+ 916) |
| `tram`, `sbahn`, `bus`, `bahnhof` | **not OSM at all** — MOTIS, § 3 | | |

**Total for the tag set: 22 622 features in all of Saxony.**

### 4.2 Where Saxon tagging is unreliable — measured, not assumed

**`leisure=garden` is not a park. Exclude it.** ✅ It is the single most common
"green" tag (12 583 in Saxony, more than parks and recreation grounds combined),
and the values of `garden:type` say what it actually is:

```
residential 3689 · private 3049 · community 281 · flowerbed 33 · public 26
```

`public` is 26 objects statewide. In the Leipzig centre box there are 62
`leisure=garden` ways and **one** carries a name. These are the front gardens of
terraced houses. Ranking them as "nearest park" would be absurd, and it is the
default outcome of the naive `leisure=park OR leisure=garden` query.
`landuse=allotments` (7 912 — this is Leipzig, birthplace of the Schrebergarten)
is the same trap with a different tag.

**You cannot tell a Grundschule from a Gymnasium in Saxony from OSM tags.** ✅
This is the sharpest negative result of the research.

| Key | Objects in Saxony | Note |
|---|---|---|
| `amenity=school` | 1 984 | |
| `school:DE` | **0** | The tag does not exist in Saxony. Anyone designing around it gets nothing. |
| `isced:level` | 524 total | and 191 of those are value `0`, i.e. pre-school |
| `grades` | 370 | |
| `education` | 619 | value `school` 316, `kindergarten` 220, `driving_school` 19 … |

So at most ~17 % of Saxon schools carry any level tag, and the values are not
clean: `0` 191, `1` 157, `2` 67, `2;3` 40, `3` 23, `1;2` 18, `1;2;3` 6, `4` 6,
`0;1` 4, `2;3;4` 2, **`1-2` 2**, **`2-3` 2**, **`9` 1**, `1;3` 1, **`1-3` 1** —
two separator conventions and a value that is not an ISCED level at all.

The taginfo co-occurrence list for `amenity=school` confirms it from the other
side: `name` 85.0 %, `addr:street` 52.8 %, `operator` 38.8 %, `operator:type`
23.0 %, `wheelchair` 21.7 % — the list runs down to 8.2 % without
`isced:level`, `school:DE` or `grades` appearing at all.

The only signal that is actually present is **the name string**. In the sample of
14 schools I pulled raw from four boxes, the type is in the name every time and
nowhere else:

```
"Geschwister Scholl Schule Liebertwolkwitz - Oberschule der Stadt Leipzig"  grades=5-10
"Schule Liebertwolkwitz - Grundschule der Stadt Leipzig"                    grades=1-4
"102. Grundschule „Johanna“"          "101. Oberschule Dresden „Johannes Gutenberg“"
"Gymnasium Dresden-Johannstadt"       "Bertolt-Brecht-Gymnasium"
"Berufliches Schulzentrum für Technik \"Gustav Anton Zeuner\""
"Grundschule Göda"                    grades=1-4
```

**Recommendation:** classify by matching `Grundschule|Oberschule|Gymnasium|
Förderschule|Berufliche[sn]? Schulzentrum|Berufsschule|Gemeinschaftsschule`
against `name`, fall back to `isced:level`/`grades` where present, and show the
school's **name** in the UI so the user can see the type themselves. Do not
present the derived class as a fact. Saxony publishes the authoritative
classification (§ 6) — it is just not joinable to a coordinate.

**One school is often three objects.** ✅ At Am Angerteich in Liebertwolkwitz,
OSM has two `amenity=school` nodes (the Grundschule and the Oberschule sharing a
site) plus the `amenity=school` way of the grounds with no name. Any "nearest
school" that does not deduplicate by proximity + address will report three
schools 250–310 m away where a human sees one campus.

**`amenity=doctors` and `healthcare=doctor` are the same objects.** ✅ Leipzig
centre: 17 and 17, Dresden Johannstadt: 21 and 19 — `healthcare=doctor` is a
second tag on the same node, not a second surgery. Saxony-wide: 2 467 vs 2 263.
Match on `amenity`, treat `healthcare` as a refinement, never union the two.

**Playgrounds and parks are mostly unnamed.** ✅ Saxony-wide, from taginfo
co-occurrence: `leisure=playground` carries a `name` on **11.8 %** (833 of
7 045); `leisure=park` on **31.2 %** (1 097 of 3 517). Per box: Leipzig centre
10 playgrounds / 0 named; Dresden Johannstadt 39 / 3; Göda 2 / 0. This number
is what rules out every name-indexed geocoder (§ 5). The most common companion
tag on playgrounds is `access` (58.7 %), which is worth filtering on — some are
private or kindergarten-internal.

### 4.3 There is no S-Bahn tag in Saxony ✅

The question "how do you tell an S-Bahn station from a regional one" has a flat
answer for this region: **you cannot, from OSM.**

| Candidate | Objects in Saxony |
|---|---|
| `station=light_rail` / `station=subway` | 0 — the only `station` values are `miniature` 18, `funicular` 6, `train` 1 |
| `service=suburban` | **0** |
| `service=commuter` | 37 |
| `light_rail=yes` | 13 |
| `subway=*` | 1 (`no`) |
| `train=yes` | 2 748 (marks anything rail-served, S-Bahn and RE alike) |

S-Bahn lines do exist as `route=train` relations (227 statewide), so in principle
you could walk every route relation through a stop and read its `name`/`ref`.
That is a heavy recursive Overpass query, run per user, to reconstruct something
MOTIS hands over as `"modes": ["SUBURBAN"]` in a single response field. Do not
do it.

The stop-position scheme is a second reason to stay away. Each physical stop is
tagged two or three times in parallel:

| Tag | Liebertwolkwitz | Leipzig centre | Dresden Johannstadt | Göda | Saxony |
|---|---|---|---|---|---|
| `public_transport=stop_position` | 22 | 99 | 47 | 9 | 20 171 |
| `public_transport=platform` | 22 | 83 | 47 | 14 | 27 777 |
| `highway=bus_stop` | 20 | 31 | 24 | 14 | 23 690 |
| `railway=tram_stop` | 0 | 39 | 27 | 0 | 1 683 |
| `railway=station` / `halt` | 1 / 0 | 3 / 0 | 0 / 0 | 0 / 0 | 283 / 426 |

Both the legacy scheme (`highway=bus_stop`, `railway=tram_stop`) and the modern
one (`public_transport=*`) are in use simultaneously, and in Göda there are more
platforms than stop positions. Grouping those into "stops a person would name"
is exactly the work `grouped=true` already did for us in § 3.1 — and it does it
knowing whether anything actually calls there, which OSM does not.

---

## 5. Photon — reachable, and not good enough ✅

Photon (`https://photon.komoot.io`) is an OSM-backed geocoder with a reverse mode
and tag filtering, it answered every request in ~0.7 s, and it is the obvious
"just use a geocoder" shortcut. It is measurably unfit for this.

```
GET https://photon.komoot.io/reverse?lat=51.2828&lon=12.4630&radius=3&limit=5
      &osm_tag=amenity:school&lang=de
→ HTTP 200, 0.76 s
```

```
 254 m  N10985287011  amenity=school   Geschwister Scholl Schule Liebertwolkwitz - Oberschule …
 300 m  N10985287012  amenity=school   Schule Liebertwolkwitz - Grundschule der Stadt Leipzig
 308 m  W1068011411   amenity=school   (no name)
1841 m  W649704869    amenity=school   Umweltschule der Stadt Leipzig
2433 m  W363097550    amenity=school   Schule Holzhausen - Grundschule der Stadt Leipzig
```

`osm_tag` works as documented (`key:value`, `key`, `!key:value`, per
`docs/api-v1.md` in the repo), `radius` is **in kilometres** (0–5000), and
results come back distance-ordered as GeoJSON. So far so good.

**The problem is what it does not index.** Photon's index is built for
search-as-you-type, so it holds objects with a name or a house number. Measured
against ground truth from the OSM API for the same point:

```
Origin 51.0555, 13.7700 (Käthe-Kollwitz-Ufer, Dresden-Johannstadt)
  OSM, within 1 km:            33 playgrounds, of which 3 carry a name
  Photon, radius=1, limit=20:   5 results
```

Two of Photon's five are indexed under a street address ("Käthe-Kollwitz-Ufer",
"Fetscherstraße 49-51") rather than a name. Photon sees roughly **15 %** of the
playgrounds that are actually mapped there. For parks the ceiling is 31 %
statewide (§ 4.2). For a question whose whole point is "the nearest one", showing
the fourth-nearest because the three nearer ones have no name is a wrong answer,
not a degraded one.

Its terms, verbatim from `https://photon.komoot.io/` (HTTP 200):

> "You can use the API for your project, but please be fair - extensive usage
> will be throttled. We do not guarantee for the availability and usage might be
> subject of change in the future."

and from `README.md` in the repo:

> "Extensive usage will be throttled or completely banned. […] *If you have a
> larger number of requests to make, please consider setting up your own private
> instance.*"

No numbers, no `User-Agent` requirement stated. Same shape as Overpass: fine for
occasional use, explicitly not a backend.

**Where Photon is still useful:** as a name lookup when the user types a
destination, which is what `/api/geocode` already does through MOTIS. Not for
"nearest X".

---

## 6. The Saxon authority services — one real find, and an honest "no"

### 6.1 ✅ There is a statewide school service, and it is on a host we already proxy

`https://geodienste.sachsen.de/wms_smr_bildungkultur/guest` — "Verwaltungsatlas
Bildung und Kultur", GetCapabilities HTTP 200, 121 905 bytes. Its abstract:

> "Der Dienst stellt Daten des Verwaltungsatlas Sachsen dar. Er umfasst die
> Standorte von allgemeinbildenden Schulen (inklusive Förderschulen), Schulen des
> Zweiten Bildungsweges in öffentlicher und freier Trägerschaft in Sachsen und
> **beruht auf Daten der Sächsischen Schuldatenbank**."

Every layer is `queryable="1"`, and the layer names are exactly the
classification OSM cannot give us:

```
grundschulen · oberschulen · gymnasien · gemeinschaftsschulen · schulebildung2
berufsschulzentrum · berufsschule · berufsfachschule · fachschule · fachoberschule
berufgymnasium · berufsfoerderschule · ergaenzungsschule · klinikschule · hochschulen
foerderschule{lernen,geistig,sozial,koerperlich,sehen,hoeren,sprache}
```

GetFeatureInfo offers `application/geo+json`, and it returns real records:

```
GET …/guest?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetFeatureInfo
    &LAYERS=grundschulen&QUERY_LAYERS=grundschulen&CRS=EPSG:4326
    &BBOX=51.2728,12.4480,51.2928,12.4780&WIDTH=5&HEIGHT=5&I=2&J=2
    &INFO_FORMAT=application/geo%2Bjson&FEATURE_COUNT=100
→ HTTP 200, 1.24 s, 153 features
```

```json
{"type":"Feature","geometry": null,
 "properties":{"objectid":"106","Name":"Freie Waldorfschule Leipzig (Schule in freier Trägerschaft)",
   "Straße":"Berthastraße 15","PLZ":"04357","Ort":"Leipzig","Telefonnummer":"0341-4229891",
   "Webseite":"https://www.waldorfschule-leipzig.de","Rechtsstatus":"Einrichtung in freier Trägerschaft",
   "Shape":"Point"},
 "layerName":"grundschulen"}
```

**Two blockers, both verified, and together they are fatal for a "nearest"
query.**

1. **`geometry` is `null`.** The "geo+json" carries no coordinate. `"Shape":
   "Point"` is a literal string, not a geometry. I checked every other offered
   `INFO_FORMAT` — `text/xml` (a GeoBAK `Sachdatenabfrage`),
   `application/vnd.esri.wms_raw_xml`, `text/plain` — and none of them carries a
   coordinate either. You get name, street, postcode, town, phone, e-mail,
   website and legal status. To place a school on a map you would have to geocode
   its address yourself, which reintroduces every error you were trying to avoid.

2. **The spatial filter is a query-pixel tolerance, not a radius, and it is
   enormous.** A 2 km box around the Liebertwolkwitz plot returned a school in
   Leipzig-Mockau, **9.9 km away**. A 2 km box over Dresden returned schools in
   Radebeul (7.3 km), Freital (7.4 km), Kreischa (11.7 km), Moritzburg (12.9 km)
   and Ottendorf-Okrilla (**16.1 km**), truncated at `FEATURE_COUNT`. There is no
   sensible way to ask it "within 2 km of this point".

There is **no WFS** counterpart: `wfs_smr_bildungkultur` returns the generic
sachsen.de 404 page, and `wms_smr_bildungkultur/guest?service=wfs` answers
`<ServiceException code="ServiceError">Could not process client request`.

**Verdict:** worth keeping as an *overlay layer* in the existing WMS tile proxy —
"amtliche Schulstandorte" drawn over the map is genuinely valuable and costs
almost nothing, since `backend/app/services/tiles.py` already speaks to this
exact host. It is **not** usable as the nearest-X data source. Also note it
carries per-school phone and e-mail; the project's "no contact details are
stored" rule means we should not persist those fields even though they are
institutional rather than personal.

### 6.2 ✅ Municipal open data is excellent — and only municipal

Searched via the GovData CKAN API (`https://ckan.govdata.de/api/3/action/package_search`,
HTTP 200). Leipzig publishes a real WFS with 83 feature types:

```
GET https://geodienste.leipzig.de/l3/OpenData/wfs?SERVICE=WFS&REQUEST=GetCapabilities&VERSION=2.0.0
→ HTTP 200, 140 960 bytes
POI-relevant types: OpenData:schulstandort · OpenData:kita · OpenData:hort
                    OpenData:spielplaetze · OpenData:gruenflaechen_amt66/67
                    OpenData:bus_haltestellen
```

Chemnitz publishes kitas through an ArcGIS Hub (GeoJSON, KML, CSV, GPKG). Dresden
has its own portal. These are better than OSM inside their city limits.

They are also three different schemas, three different refresh cadences, three
different licences, and they stop at the city boundary. Our tool must answer for
a plot in Göda as confidently as for one in Leipzig. **Stitching three cities'
portals is more work than the OSM extract and covers less of Saxony.** Revisit
only if a "amtliche Daten, wo verfügbar" badge becomes a product requirement.

### 6.3 ⚠️ What I could not get out of the metadata catalogue

`https://geoportal.sachsen.de/md/csw` 302-redirects to
`https://registry.gdi-de.org/id/de.sn/csw`. That endpoint answers GetRecords
(HTTP 200, `application/xml`), but my CQL constraint returned
`numberOfRecordsMatched="0"` for **every** term including `Bodenrichtwert`,
which certainly is in the Saxon catalogue. So my query form was wrong, not the
catalogue empty. I could not confirm by catalogue search that no statewide
kindergarten/playground/park dataset exists — only that GovData, the GeoSN
service list and the Saxon open-data portal do not surface one.

**Honest summary for § 6: for schools there is real authority and it is not
joinable to a coordinate; for kindergartens, playgrounds, parks, doctors and
supermarkets there is nothing statewide and usable. OSM is the only source that
covers all of Saxony for all of these categories.**

---

## 7. Air distance versus walking — measured, and it matters more than expected

### 7.1 The measurement ✅

Origin **51.0555, 13.7700** (Käthe-Kollwitz-Ufer, Dresden-Johannstadt, on the
south bank of the Elbe). The 20 nearest playgrounds and named parks were taken
from raw OSM and routed in **one** `one-to-many` call (841 ms on a cold
connection; 148 ms warm, § 7.2):

```
  air m   walk m  walk min  ratio  kind        name
    172        —  unreachable       Park        Vietnamesischer Garten
    307      404       5.7   1.31  Spielplatz  Spielplatz Johannes-Kindergarten
    329      809      11.4   2.46  Park        Quartiersgarten Johanngarten
    355      887      12.6   2.50  Spielplatz  (ohne Namen)
    372     1074      15.2   2.88  Spielplatz  (ohne Namen)
    408      960      15.6   2.36  Spielplatz  (ohne Namen)
    430      698      10.3   1.62  Spielplatz  (ohne Namen)
    545     1340      20.8   2.46  Spielplatz  (ohne Namen)
    579        —  unreachable       Spielplatz  (ohne Namen)
```

- **The nearest thing by air, 172 m away, cannot be walked to at all.** MOTIS
  returns `{}` for it — the Elbe is in the way and the crossing at that point is
  a ferry (`Dresden Fährstelle Johannstadt`, § 3.1), not a bridge. Air distance
  would have put it first.
- Detour ratios reach **2.88** — 372 m of air is 1074 m and 15 minutes of walking.
- Ranking by air and ranking by walking disagree from position 1.

Even without a river the effect is real. At Liebertwolkwitz, ranking 16 transit
stops by air and by walking gives different answers from position 4 onwards, with
detour ratios of 1.08–1.71. **One extra request buys a number that is simply
correct instead of plausibly wrong.**

Two notes on reading the response:

- An unreachable destination is `{}`, not an error and not a null duration —
  verified: `[{"duration":6.25E2,"distance":5.85E2},{}]`. Render that as
  "nicht zu Fuß erreichbar", not as distance 0.
- **`duration` is a routing cost, not `distance / walking speed`.** Leipzig,
  Roßstr.: 478 m in 603 s = 0.79 m/s, because MOTIS charges for crossings and
  turns. `/api/v6/plan` gives the same duration for the same pair — 603 s
  against `one-to-many`'s 603 s, distance 477 m against 478 m —
  so this is the engine's pedestrian model, not a `one-to-many` artefact. Show
  the duration; do not derive a speed from it, and do not show both in a way that
  invites the user to divide them.

### 7.2 What routing N candidates actually costs ✅

`GET /api/v1/one-to-many`, `mode=WALK`, `withDistance=true`, 3 repeats each:

| N destinations | median | min | max | ms per destination |
|---|---|---|---|---|
| 1 | 150 ms | 149 | 152 | 150.1 |
| 5 | 149 ms | 149 | 150 | 29.8 |
| 10 | 150 ms | 150 | 153 | 15.0 |
| 20 | 151 ms | 150 | 155 | 7.6 |
| 40 | 153 ms | 152 | 158 | 3.8 |
| 80 | 161 ms | 158 | 280 | 2.0 |

`POST` with a JSON body, 4 repeats each: N=32 **151 ms**, N=64 **147 ms**,
N=100 **150 ms**, N=128 **148 ms**.

Against the 148 ms transport floor, 128 walking routes cost the server on the
order of **10 ms**. The cost of this feature is one round trip, full stop.

**Hard limit: 128 destinations per call**, found by binary search, with the
server naming its own config key:

```
POST /api/v1/one-to-many  (many: 150 entries)  → HTTP 422
{"error":"number of many locations too high (150 > 128). The server admin can
 change this limit in config.yml with 'onetomany_max_many'. See documentation for details."}
```

n=128 → 200, n=129 → 422. Exactly 128.

**The alternative, for comparison** — what a naive implementation would do:

| Approach | Wall time | Upstream requests |
|---|---|---|
| `one-to-many`, 8 destinations, 1 call | **148 ms** | **1** |
| `one-to-many`, 128 destinations, 1 call | **148 ms** | **1** |
| 8 × `/api/v6/plan` WALK, `max_concurrency=2` (today's setting) | 1523 ms | 8 |
| 8 × `/api/v6/plan` WALK, concurrency 8 | 1086 ms | 8 |
| 1 × `/api/v6/plan` WALK | 172 ms (5 233 bytes) | 1 |
| 1 × `/api/v6/plan` TRANSIT | 194 ms (51 015 bytes) | 1 |

`one-to-many` supports `WALK`, `BIKE` and `CAR` (verified: 478 m is 603 s
walking, 137 s by bike, 44 s by car). It does **not** do public transport — for
POIs that is the right restriction anyway; you walk to the nearest playground.
For a transit-based "nearest", `/api/experimental/one-to-many-intermodal` exists
📘 but is experimental and, being routing, falls under the "contact us first"
clause. ⚠️ Not tested.

**So: 15–20 candidates per category, all categories pooled into one call, capped
at 128.** Seven categories × 18 = 126 fits in a single request.

---

## 8. Rate limits and usage policies, and what they mean for our proxy

| Service | The binding sentence | What our proxy must do |
|---|---|---|
| **Overpass** public instances | "Setting up an app for more than just OSM mappers and relying on the public instances as backend" is listed as problematic behaviour; "only running your own instance sustainably serves your mission"; ~10 000 req/day and 1 GB/day guideline; rate limit per IP with slots and cooldown | **Do not call it at request time.** Use it, if at all, only from an offline build job that runs on the order of once a quarter. Caching does not make request-time use compliant, and a shared server IP is the worst case under a per-IP slot scheme. |
| **OSM main API** | "The editing API is provided in order to edit the map data, **not for read-only purposes or projects**"; max 2 download threads; 50 000-node bbox cap (verified) | Never in production. It was used here as research ground truth only. |
| **Photon** (komoot) | "You can use the API for your project, but please be fair - extensive usage will be throttled. We do not guarantee for the availability"; README adds "or completely banned" | Not a backend. If used at all, only behind a long TTL, and never on the critical path of a page. |
| **Transitous / MOTIS** | "Please contact us before using any potentially resource-intensive API endpoints (**such as routing**, isochrones) or doing **many requests** (also from different users)"; open-source only; **"commercial use is not allowed"**; `User-Agent` must carry app name, version and a contact | Already the project's position (`docs/research/routing-motis.md` § 6). This feature *adds* routing load, so it strengthens the case for the Matrix contact before real traffic. Choosing `one-to-many` over N × `/plan` cuts the added load by a factor of 8–128 and is the single most policy-respectful decision available here. |
| **taginfo** (Geofabrik regional) | ⚠️ No policy page located | Research-time only. Not called at runtime by anything proposed here. |
| **OSM data itself** | ODbL. Every response we saw carries `"copyright": "…made available under ODbL."` | Attribution for OpenStreetMap must appear in the UI, alongside the existing `transitous.org/sources/` link the Transitous policy requires. |

**Cache design for the proposed endpoint.** The existing `DiskCache` pattern in
`backend/app/cache.py` fits without change:

- **POI candidates: not cached, because they are not fetched.** They come from
  our own extract, in memory. This is the whole point — the request-time
  dependency disappears.
- **`map/stops`: cache on the rounded bbox**, TTL ~24 h. Timetable feeds change
  daily at most, and stop positions far less often. Rounding the bbox to a fixed
  grid (say 0.02°) turns per-plot boxes into a small set of shared keys.
- **`stop?stopId=`: cache on the stop id**, TTL ~24 h. Lines serving a stop are
  stable.
- **`one-to-many`: cache on (origin rounded to ~5 decimal places, sorted
  destination list, mode)**, TTL ~7 days. The street network changes slowly.
  Round the origin: two plots on the same parcel must not miss the cache.
- Keep the existing `max_concurrency = 2` semaphore. With this design a full
  "nearest everything" answer is **2–3 upstream requests**, not 20.

---

## 9. Endpoint sketch — a design, not an implementation

One endpoint, following the shape of `POST /api/reachability`
(`backend/app/routers/reachability.py`) and the naming convention already in
`backend/app/schemas.py`: English for structure, German for the domain words a
user reads.

### `POST /api/nearby` → "Was ist in der Nähe?"

```python
# schemas.py
Kategorie = Literal[
    "schule", "kindergarten", "park", "spielplatz", "supermarkt", "arzt",
    "tram", "sbahn", "bus", "bahnhof",
]
Umgebungsmodus = Literal["walk", "bike"]          # one-to-many street modes only


class NearbyRequest(BaseModel):
    origin: Koordinate
    kategorien: list[Kategorie] = Field(min_length=1, max_length=10)
    modus: Umgebungsmodus = "walk"
    # Air-distance cut-off for building the candidate list. Not shown to the user.
    umkreis_m: int = Field(default=3000, ge=200, le=15000)
    # How many hits per category to return, best first.
    treffer_je_kategorie: int = Field(default=3, ge=1, le=10)


class UmgebungTreffer(BaseModel):
    kategorie: Kategorie
    name: str | None                 # None is normal: 88% of Saxon playgrounds
    art: str | None                  # "Grundschule", "Gymnasium", "Straßenbahn" …
    lat: float
    lon: float
    erreichbar: bool
    duration_s: int | None = None    # MOTIS routing cost, NOT distance/speed
    distance_m: int | None = None    # network distance, not air distance
    luftlinie_m: int                 # kept for the "unreachable" case
    linien: list[str] = []           # transit only: ["11", "S1", "RB113"]
    quelle: Literal["osm", "motis"]
    osm_id: str | None = None        # "N10985287011" — lets a user check the source
    hinweis: str | None = None


class NearbyResponse(BaseModel):
    treffer: list[UmgebungTreffer]
    quelle: str = "OpenStreetMap (ODbL) und MOTIS / Transitous (DELFI-GTFS)"
    hinweis: str = UMGEBUNG_HINWEIS
```

`UMGEBUNG_HINWEIS` should say, in German, what the numbers are and are not: that
the walking times come from OpenStreetMap's footpath network and are an
estimate, that a school's type is derived from its name and should be checked,
and that the categories reflect what volunteers have mapped rather than an
official register.

### Flow inside the service

```
1. For each requested POI category (schule, kindergarten, park, spielplatz,
   supermarkt, arzt):
       query the in-process index → the `treffer_je_kategorie * 6` nearest
       by air within `umkreis_m`, deduplicated by proximity + address
                                                        [0 upstream requests]

2. If any transit category was requested:
       GET /api/v6/map/stops?min=…&max=…&grouped=true   [1 upstream request]
       (bbox = umkreis_m around origin, rounded to a cache grid)
       filter on the per-stop `modes` array — the `modes` query parameter
       does not work (§ 3.1):
           tram     → "TRAM" in modes
           sbahn    → "SUBURBAN" in modes
           bus      → "BUS" in modes
           bahnhof  → modes & {REGIONAL_RAIL, LONG_DISTANCE, HIGHSPEED_RAIL}

3. Pool every candidate from steps 1 and 2 into ONE list, cap at 128,
   keeping the nearest by air per category:
       POST /api/v1/one-to-many {one, many, mode, max, maxMatchingDistance,
                                 arriveBy: false, withDistance: true}
                                                        [1 upstream request]
       An empty object {} in the response means unreachable → erreichbar=false

4. Sort each category by duration_s, keep `treffer_je_kategorie`.

5. Only for the transit hits that survived:
       GET /api/v6/stop?stopId=…  per stop                [<= 3 requests, cached]
       → linien = sorted({r.routeShortName for r in routes if r.mode matches})
```

**Total: 2–5 upstream requests, ~300–600 ms cold, ~150 ms with a warm cache**,
for every category at once. Compare with the naive design's 20+ requests and
several seconds.

### The POI index

- `NearbySettings` in `settings.py` (env prefix `NEARBY_`): `data_path`,
  `max_candidates` (128), `umkreis_m` default, `cache_ttl_s`.
- A build script, `scripts/build-poi-index.py`, that reads
  `sachsen-latest.osm.pbf` with `pyosmium` (PyPI `osmium` 4.3.1, requires_python
  `>=3.8`, 53 wheels for the current release ✅) and writes a flat
  `{kategorie, name, art, lat, lon, osm_id}` file. Ways and relations collapse
  to their centroid, exactly like Overpass's `out center`.
- At startup the service loads that file into a simple lat/lon grid — 22 622
  points needs nothing cleverer, and no PostGIS.
- The file is a build artefact, refreshed on a cadence (quarterly is plenty for
  schools; playgrounds change faster but not by much). Version it with the
  extract's timestamp so the UI can say how old the data is.
- Frontend: this endpoint returns coordinates and times, no geometry. The
  existing rule that geometry lives in the browser is untouched; drawing the
  route to a chosen hit is the existing `/api/reachability` call with that hit
  as a `Ziel`.

---

## 10. What I could not verify

Stated plainly, because the project rule is verify-don't-relay and these are the
gaps.

1. **No Overpass query against Saxon data.** Every general-purpose instance was
   unreachable from this sandbox (§ 2.1) with a failure signature the proxy log
   attributes to the relay, not the service. I verified the query syntax and
   response shape against `overpass.osm.ch` with a Swiss coordinate, and I
   verified the policy text from the manual — but I did not measure a real Saxon
   Overpass response time or payload size. The recommendation does not depend on
   those numbers (it is a policy argument, not a performance one), but the claim
   "Overpass is fast enough" is one I cannot make from evidence.

2. **Geofabrik is unreachable here.** `download.geofabrik.de/europe/germany/
   sachsen-latest.osm.pbf` fails the same way — CONNECT succeeds, transfer resets
   after ~7 s. `docs/research/routing-motis.md` § 7.11 recorded the same in the
   earlier session, so this is a stable property of this environment. I therefore
   cannot state the extract's current size or timestamp. What I *can* confirm is
   that `download.bbbike.org` is reachable and holds city extracts —
   `Dresden.osm.pbf` is **63 855 594 bytes, Last-Modified Sat, 22 Aug 2026** —
   and that `download.openstreetmap.fr/extracts/europe/germany/` is reachable but
   carries **only Nordrhein-Westfalen**, no Saxony. **Re-check the Geofabrik
   download in the target environment before committing to the build script.**

3. **`/api/experimental/one-to-many-intermodal` was not tested.** It is the
   transit-aware sibling of `one-to-many` and would matter if the user ever wants
   "nearest school by bus". It is experimental and, being routing, sits under the
   Transitous "contact us first" clause, so I left it alone.

4. **`/api/v6/one-to-all` (isochrones) was not tested,** for the same reason and
   on the same grounds as the earlier MOTIS research.

5. **Whether the broken `modes` parameter on `/api/v6/map/stops` is a bug or by
   design.** It validates the enum and ignores the value (§ 3.1). Filtering
   client-side works, so this is a note, not a blocker.

6. **The Saxon CSW catalogue search.** My CQL constraint returned 0 matches for
   every term including `Bodenrichtwert`, which is certainly catalogued, so the
   query form was wrong. I cannot say from the catalogue that no statewide
   kindergarten or playground dataset exists — only that GovData, the GeoSN
   service listing and `opendata.sachsen.de` do not surface one.

7. **No taginfo usage policy found.** taginfo was used for research only and
   nothing proposed here calls it at runtime, but if that ever changes, find the
   policy first.

8. **All timings include this sandbox's HTTPS proxy** (148 ms floor). Relative
   comparisons hold; absolute latencies will be lower from a normal host.

9. **The name-based school classifier is untested at scale.** I read 14 Saxon
   schools' names and the pattern held in all 14. That is a strong hint, not a
   measured hit rate.

---

## 11. Sources

Fetched live on 2026-08-29, HTTP 200 unless noted.

- MOTIS OpenAPI: `https://raw.githubusercontent.com/motis-project/motis/master/openapi.yaml` (214 336 bytes). `api.transitous.org/openapi.yaml` → 404.
- Transitous usage policy: `https://transitous.org/api/`
- Overpass manual, "Commons": `https://dev.overpass-api.de/overpass-doc/en/preface/commons.html`
- Overpass instance list: `https://wiki.openstreetmap.org/wiki/Overpass_API`
- OSM API usage policy: `https://operations.osmfoundation.org/policies/api/`
- Photon terms: `https://photon.komoot.io/`; API docs and demo-server terms: `https://raw.githubusercontent.com/komoot/photon/master/docs/api-v1.md`, `…/README.md`
- taginfo Saxony: `https://taginfo.geofabrik.de/europe:germany:sachsen/api/4/…` (`site/info` confirms `"area":"Sachsen"`)
- Raw OSM ground truth: `https://api.openstreetmap.org/api/0.6/map?bbox=…` for nine Saxon boxes
- Saxon education WMS: `https://geodienste.sachsen.de/wms_smr_bildungkultur/guest`
- Leipzig open-data WFS: `https://geodienste.leipzig.de/l3/OpenData/wfs`
- GovData CKAN: `https://ckan.govdata.de/api/3/action/package_search`
- Saxon CSW (via 302 from `geoportal.sachsen.de/md/csw`): `https://registry.gdi-de.org/id/de.sn/csw`
- pyosmium: `https://pypi.org/pypi/osmium/json` (4.3.1)

Test locations used throughout: **51.2828, 12.4630** (Leipzig-Liebertwolkwitz,
the village edge — the coordinate in the brief), **51.0555, 13.7700** (Dresden
Johannstadt, on the Elbe), Leipzig centre, Leipzig-Grünau, Dresden Neustadt,
Chemnitz, Zwickau, Görlitz, and **Göda** in the rural Lausitz.
