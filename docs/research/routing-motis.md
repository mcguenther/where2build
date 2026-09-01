# Multimodales Routing mit MOTIS / Transitous — Recherche

**Datum der Recherche:** 29.08.2026
**Autor:** Claude (Recherche-Agent) für Julian Dorn, Projekt "Grundstücks-Check Sachsen"

> **Legende:**
> 🟢 **LIVE VERIFIZIERT (29.08.2026)** — durch eigenen `curl`-Aufruf gegen `https://api.transitous.org` bestätigt, Rohdaten liegen vor.
> 📘 **AUS DOKU** — aus dem offiziellen OpenAPI-Spec (`motis-project/motis`, Tag `v2.10.2`) bzw. offizieller Doku entnommen, nicht selbst gegen den Live-Server getestet.
> ⚠️ **UNSICHER / NICHT VERIFIZIERT** — aus Sekundärquellen (Foren, Wiki, Allgemeinwissen), explizit als Schätzung markiert.

---

## 1. Zusammenfassung & Empfehlung

- **Transitous (`api.transitous.org`) ist die richtige Wahl für den Prototyp/MVP** des Grundstücks-Checks: kostenlos, deckt Sachsen vollständig ab (DELFI-Daten + OSM), unterstützt genau die gewünschte Kombination "ÖPNV + Rad/Fuß-Zubringer" nativ über einen einzigen `/api/v6/plan`-Call. Live gegen echte Sachsen-Koordinaten getestet, funktioniert einwandfrei (Leipzig → Dresden Hbf in ~1,1 s Antwortzeit).
- **Auto-Routing funktioniert ebenfalls** (`directModes=CAR` liefert eine echte Fahrstrecke mit Fahrzeit), ist aber laut Nutzungsrichtlinie nur für "leichte", nicht-kommerzielle Nutzung mit wenigen Requests gedacht — für produktiven Einsatz mit nennenswertem Traffic ist **vorherige Kontaktaufnahme über Matrix verpflichtend** (siehe Abschnitt 5).
- **`legGeometry.points` ist ein Google-Encoded-Polyline mit Präzision 6** (nicht 5!). Das Antwortobjekt nennt die Präzision sogar explizit im Feld `legGeometry.precision` — live nachgeprüft, mit Präzision 6 dekodiert liegen die Koordinaten exakt in Sachsen, mit Präzision 5 sind sie um Faktor 10 verschoben und unbrauchbar. Zum Dekodieren im Frontend: `@mapbox/polyline` (npm), Aufruf mit `precision: 6`.
- **MOTIS liefert selbst keine Kartenkacheln im klassischen Sinn** (kein `{z}/{x}/{y}`-Tile-Endpunkt bei Transitous aktiv). Es gibt zwar einen `tiles`-Feature-Zweig im MOTIS-Quellcode für Self-Hosting (Vektor-Tiles via `tiles.profile`), dieser ist aber bei `api.transitous.org` nicht Teil der öffentlich dokumentierten/getesteten Endpunkte gewesen; die `/api/*/map/*`-Endpunkte, die live erreichbar sind, liefern JSON (Stops, Trips, Routen-Metadaten fürs Debug-UI), keine Bild-/Vektor-Kacheln. Für eine Basiskarte wird also weiterhin ein separater Tile-Anbieter (z. B. OSM-Tiles, MapLibre + OpenMapTiles) benötigt.
- **Für Isochronen** gibt es `/api/v6/one-to-all` — das ist laut Nutzungsrichtlinie explizit ein "resource-intensive endpoint", **vor Nutzung ist Kontakt über Matrix Pflicht**. Wurde in dieser Recherche daher **nicht** live getestet, nur aus der Spec dokumentiert.
- **Self-Hosting ist machbar und wurde am 01.09.2026 durchgeführt** (Abschnitt 5): `ghcr.io/motis-project/motis:2.11.2` mit einem OSM-Extrakt und dem deutschlandweiten DELFI-GTFS. Import 3 min 30 s bei 5,34 GiB Spitzen-RSS, 2,8 GB Graph, Server danach 1,55 GiB RSS. Die lokale Instanz antwortet auf Geocoding, `/plan`, `one-to-many` und `map/stops` identisch zu Transitous; der einzige Unterschied ist die Geometrie der ÖPNV-Teilstrecke (Luftlinie statt nachgeroutetem Linienverlauf, weil der DELFI-GTFS keine `shapes.txt` hat).
- **Empfehlung für den Grundstücks-Check:** MVP direkt gegen `api.transitous.org` bauen (mit korrektem User-Agent-Header, Attribution-Link, wenigen Requests pro Nutzeraktion, kein serverseitiges Caching-Bypass-Scraping), und Self-Hosting als Fallback/Skalierungsoption für später vormerken, sobald Nutzerzahlen relevanten Traffic erzeugen.

---

## 2. API-Referenz (MOTIS 2 API)

Quelle: `openapi.yaml`, Tag `v2.10.2` (verlinkt von `transitous.org/api/` als maßgebliche Spec), Repo `motis-project/motis`. 📘 Die Pfade wurden zusätzlich 🟢 **live gegen `api.transitous.org` verifiziert**, soweit in Abschnitt 3 getestet.

### 2.1 Alle Endpunkte (📘 aus OpenAPI-Spec, Pfade exakt so im YAML)

| Pfad | Methode(n) | Zweck |
|---|---|---|
| `/api/v6/plan` | GET | Routenberechnung (Kern-Endpunkt) |
| `/api/v1/one-to-many` | GET, POST | Straßen-Routing von 1 Punkt zu vielen Zielen (Reisezeiten, Straße only) |
| `/api/experimental/one-to-many-intermodal` | GET, POST | Wie oben, aber intermodal (mit ÖPNV) |
| `/api/v6/one-to-all` | GET | **Isochronen**: alle in max. Reisezeit erreichbaren Orte ab einem Punkt |
| `/api/v1/reverse-geocode` | GET | Koordinate → nächstgelegene Adresse/Haltestelle/POI |
| `/api/v1/geocode` | GET | Adress-/Haltestellen-Autovervollständigung |
| `/api/v6/trip` | GET | Einzelne Trip-ID als Itinerary abrufen |
| `/api/v6/refresh-itinerary` | GET, POST | Itinerary anhand ihrer `id` neu berechnen (aktueller Fahrplan/Echtzeit) |
| `/api/v6/stoptimes` | GET | Nächste N Abfahrten/Ankünfte an einer Haltestelle |
| `/api/v6/map/trips` | GET | Fahrzeuge/Trips im Kartenausschnitt (für Live-Karten-UI) |
| `/api/v1/map/initial` | GET | Initialer Kartenmittelpunkt/-zoom + Server-Konfiguration (🟢 live getestet) |
| `/api/v6/map/stops` | GET | Haltestellen im Kartenausschnitt |
| `/api/v1/map/levels` | GET | Verfügbare Gebäude-/Indoor-Ebenen an einem Ort |
| `/api/experimental/map/routes` | GET | Liniennetz-Geometrien |
| `/api/experimental/map/route-details` | GET | Detail-Infos zu einer Linie |
| `/api/v1/rentals` | GET | GBFS-Sharing-Angebote (Räder/Scooter/Autos) im Gebiet |
| `/api/v1/health` | GET | Health-Check |
| `/api/debug/transfers` | GET | Debug: Umstiegsberechnung |

**Wichtig zur Versionierung:** Die URL-Pfade tragen ihre eigene API-Version (`v1`, `v6`, `experimental`) unabhängig von der Software-Release-Version des MOTIS-Servers (`v2.10.2`/`v2.11.1` etc.). `/plan`, `/trip`, `/one-to-all`, `/refresh-itinerary`, `/stoptimes`, `/map/trips`, `/map/stops` liegen aktuell alle unter `v6`; `/geocode`, `/reverse-geocode`, `/one-to-many`, `/map/initial`, `/map/levels`, `/rentals`, `/health` unter `v1`.

**Kartenkacheln:** Es existiert **kein** `/api/.../tiles/{z}/{x}/{y}`-Pfad in der Spec. MOTIS hat im Quellcode ein optionales `tiles`-Feature (`tiles.profile: tiles-profiles/full.lua` in der `config.yml`, siehe Abschnitt 4), das bei Self-Hosting Vektor-Kacheln erzeugen kann — dieses ist aber ein separates, konfigurierbares Modul und nicht Teil der oben gelisteten, bei Transitous öffentlich dokumentierten REST-Pfade. Für den Grundstücks-Check sollte man sich nicht auf MOTIS-Tiles verlassen, sondern eine eigenständige Basiskarte einbinden.

### 2.2 `/api/v6/plan` — vollständige Parameterliste (📘 aus OpenAPI-Spec)

**Pflichtparameter**

| Parameter | Typ | Beschreibung |
|---|---|---|
| `fromPlace` | string | `"latitude,longitude[,level]"` oder Stop-ID |
| `toPlace` | string | wie `fromPlace` |

**Zeit & Suchfenster**

| Parameter | Typ | Default | Beschreibung |
|---|---|---|---|
| `time` | date-time | jetzt | Abfahrts- oder Ankunftszeit |
| `arriveBy` | boolean | `false` | `true` = `time` ist Ankunftszeit, `false` = Abfahrtszeit |
| `timetableView` | boolean | `true` | Optimierung auf "später abfahren"/"früher ankommen" |
| `searchWindow` | integer (s) | `900` | Länge des Suchfensters in Sekunden |
| `numItineraries` | integer | `5` | Mindestanzahl zu berechnender Verbindungen |
| `maxItineraries` | integer | — | Maximalanzahl |
| `pageCursor` | string | — | Cursor für nächste/vorherige Seite (aus `nextPageCursor`/`previousPageCursor` der Response) |

**Modi — das Herzstück für "Rad + Bahn"**

| Parameter | Typ | Default | Beschreibung |
|---|---|---|---|
| `transitModes` | array[Mode] | `[TRANSIT]` | Erlaubte ÖPNV-Modi (z. B. `SUBURBAN`, `REGIONAL_RAIL`, `BUS`, `TRAM` einzeln einschränkbar) |
| `directModes` | array[Mode] | `[WALK]` | Modus für eine reine Direktverbindung **ohne** ÖPNV (z. B. `WALK`, `BIKE`, `CAR`) |
| `preTransitModes` | array[Mode] | `[WALK]` | Modus vom Startpunkt zur **ersten** Haltestelle (Zubringer) |
| `postTransitModes` | array[Mode] | `[WALK]` | Modus von der **letzten** Haltestelle zum Ziel (Abholer) |

**→ "Ein Stück Rad, dann Bahn" = `preTransitModes=BIKE` setzen** (zusätzlich `maxPreTransitTime` erhöhen, Default ist nur 900 s = 15 Min). 🟢 Live getestet, siehe Abschnitt 3.3 — funktioniert exakt so.

**Exakte `Mode`-Enum-Werte** (📘 wörtlich aus der Spec, `components.schemas.Mode`):

*Straßen-/Zubringer-Modi:*
- `WALK`
- `BIKE`
- `RENTAL` — *experimentell*, für Bike-/Scooter-Sharing (in Kombination mit `*RentalFormFactors`/`*RentalPropulsionTypes`/`*RentalProviders`)
- `CAR`
- `CAR_PARKING` — *experimentell*
- `CAR_DROPOFF` — *experimentell*
- `ODM` — On-Demand-Taxi (Prima+ÖV-Projekt), zählt sowohl als Transit- als auch Street-Modus
- `RIDE_SHARING` — Mitfahrgelegenheiten (Prima+ÖV), ebenfalls Transit|Street
- `FLEX` — flexible Transporte (GTFS-Flex)
- `DEBUG_BUS_ROUTE`, `DEBUG_RAILWAY_ROUTE`, `DEBUG_FERRY_ROUTE` — nur intern

*Transit-Modi (für `transitModes`):*
- `TRANSIT` — Sammelbegriff, übersetzt sich zu `TRAM,FERRY,AIRPLANE,BUS,COACH,RAIL,ODM,RIDE_SHARING,FUNICULAR,AERIAL_LIFT,OTHER`
- `TRAM`, `SUBWAY`, `FERRY`, `AIRPLANE`, `BUS` (Kurzstrecke), `COACH` (Fernbus)
- `RAIL` — Sammelbegriff für `HIGHSPEED_RAIL,LONG_DISTANCE,NIGHT_RAIL,REGIONAL_RAIL,SUBURBAN,SUBWAY`
- `HIGHSPEED_RAIL` (z. B. ICE/TGV), `LONG_DISTANCE` (IC), `NIGHT_RAIL`
- `REGIONAL_FAST_RAIL` (*deprecated*, wird zu `REGIONAL_RAIL`), `REGIONAL_RAIL`, `SUBURBAN` (S-Bahn)
- `FUNICULAR`, `AERIAL_LIFT`, `OTHER`
- `AREAL_LIFT`, `METRO`, `CABLE_CAR` — alle *deprecated*

Für Sachsen relevant sind praktisch: `WALK`, `BIKE`, `CAR`, `SUBURBAN` (S-Bahn Dresden/Leipzig), `REGIONAL_RAIL`, `TRAM`, `BUS`, `HIGHSPEED_RAIL`/`LONG_DISTANCE` (Fernverkehr über Leipzig/Dresden Hbf).

**Rental/Sharing-Parameter** (📘, alle experimentell): `directRentalFormFactors`, `preTransitRentalFormFactors`, `postTransitRentalFormFactors` (Werte u. a. `BICYCLE`, `SCOOTER_STANDING`), `directRentalPropulsionTypes`/`pre`/`post` (`HUMAN`, `ELECTRIC`, `ELECTRIC_ASSIST`), `directRentalProviders`/`pre`/`post`, `directRentalProviderGroups`/`pre`/`post`, `ignore*RentalReturnConstraints` (boolean).

**Zeitlimits für Zubringer/Direktverbindung**

| Parameter | Default | Beschreibung |
|---|---|---|
| `maxPreTransitTime` | 900 s | Max. Dauer Zubringer-Leg (Start → 1. Haltestelle) |
| `maxPostTransitTime` | 900 s | Max. Dauer Abholer-Leg |
| `maxDirectTime` | 1800 s | Max. Dauer für reine Direktverbindung (`directModes`) |
| `fastestDirectFactor` | 1,0 | Multiplikator auf schnellste Direktverbindung — >1 erlaubt langsamere ÖPNV-Alternativen |

**Umstiege & Fußwege**

| Parameter | Default | Beschreibung |
|---|---|---|
| `maxTransfers` | serverseitig | max. Umstiege; `0` = nur Direktverbindungen im ÖPNV |
| `maxTravelTime` | serverseitig | max. Gesamtreisezeit (Minuten) |
| `minTransferTime` | 0 | Mindest-Umstiegszeit (Minuten) |
| `additionalTransferTime` | 0 | Zusätzlicher Puffer je Umstieg |
| `transferTimeFactor` | 1,0 | Multiplikator auf Mindest-Umstiegszeiten |
| `via` | — | bis zu 2 Zwischenhalte (Stop-IDs) |
| `viaMinimumStay` | `[0,0]` | Mindestaufenthalt je Via-Stop (Minuten) |

**Fußgänger/Barrierefreiheit**

| Parameter | Werte/Default | Beschreibung |
|---|---|---|
| `pedestrianProfile` | `FOOT` (Default) \| `WHEELCHAIR` | **Das ist der "Rollstuhl"-Parameter**, es gibt kein separates `wheelchair`-Boolean-Feld — Barrierefreiheit wird über dieses Profil gesteuert |
| `pedestrianSpeed` | Objekt | Ø Gehgeschwindigkeit |
| `cyclingSpeed` | Objekt | Ø Radgeschwindigkeit |
| `elevationCosts` | `NONE` (Default) \| `LOW` \| `HIGH` | Bestrafung für Steigungen (wirkt v. a. auf `BIKE`) |
| `useRoutedTransfers` | `false` | OSM-geroutete statt GTFS-Umstiege verwenden |
| `maxMatchingDistance` | 25 m (im Setup-Beispiel; serverseitig gedeckelt über `max_max_matching_distance`, Default-Deckel 250 m) | max. Distanz Koordinate → Straßennetz |

**Ergebnis-Detailgrad**

| Parameter | Default | Beschreibung |
|---|---|---|
| `detailedLegs` | `true` | `legGeometry` + `steps` (Turn-by-Turn) für Legs zurückgeben |
| `detailedTransfers` | erbt von `detailedLegs` | dito für Umstiegs-Fußwege |
| `joinInterlinedLegs` | `true` | "Sitzenbleiber"-Umstiege (gleicher Zug, andere Linie) zu einem Leg zusammenfassen |
| `withFares` | `false`, *experimentell* | Fahrpreisinfo (GTFS-Fares v2) in Antwort aufnehmen |
| `withScheduledSkippedStops` | `false` | auch fahrplanmäßig nicht bedienbare Halte anzeigen |
| `numLegAlternatives` | 0 | Alternativ-Routen je Transit-Leg |
| `language` | array | Sprach-Tags (ISO 639) für Namen |
| `realtimeMode` | `REALTIME` (Default) \| `REALTIME_ANNOTATION_ONLY` \| `OFF` | Echtzeitdaten nutzen |
| `algorithm` | `PONG` (Default) \| `RAPTOR` \| `TB` | Routing-Algorithmus |
| `timeout` | — | Query-Timeout (s) |
| `passengers`, `luggage` | — | *experimentell* |
| `requireBikeTransport`, `requireCarTransport` | `false` | nur Trips mit Rad-/Auto-Mitnahme |
| `noCompulsoryReservation` | `false` | nur reservierungsfreie Trips |
| `radius` | — | Suchradius (m) um Koordinaten |

Es gibt **kein** eigenständiges `wheelchair`-Query-Parameter — anders als in der Aufgabenstellung vermutet, läuft Barrierefreiheit ausschließlich über `pedestrianProfile=WHEELCHAIR`.

### 2.3 Response-Schema (📘 aus OpenAPI-Spec)

**Wurzelobjekt (`PlanResponse`):**
```
{
  requestParameters: {...},   // die Anfrage, als Strings zurückgespiegelt
  debugOutput: {...},         // Debug-Statistiken
  from: Place,
  to: Place,
  direct: [Itinerary],        // reine Direktverbindungen (WALK/BIKE/CAR), zeitunabhängig
  itineraries: [Itinerary],   // die eigentlichen (ggf. ÖPNV-)Verbindungen
  previousPageCursor: string,
  nextPageCursor: string
}
```

**`Itinerary`** — Pflichtfelder: `duration` (int, Sekunden gesamt), `startTime`, `endTime` (ISO-8601 UTC), `transfers` (int, Anzahl Umstiege), `id` (string, *experimentell*, für `refresh-itinerary`), `legs` (array). Optional: `fareTransfers` (array, nur bei `withFares=true`).

**`Leg`** — Pflichtfelder: `mode`, `startTime`, `endTime`, `scheduledStartTime`, `scheduledEndTime`, `realTime` (bool), `scheduled` (bool), `duration`, `from`, `to`, `legGeometry`. Bei Transit-Legs zusätzlich (🟢 live in Abschnitt 3.2 bestätigt): `headsign`, `routeShortName`, `routeLongName`, `displayName`, `tripId`, `tripFrom`/`tripTo`, `agencyName`/`agencyUrl`, `routeColor`/`routeTextColor`, `intermediateStops`, `bikesAllowed`, `wheelchairAccessible`, `reservation`, `cancelled`, `interlineWithPreviousLeg`, `alternatives`. Bei Fuß-/Rad-/Auto-Legs: `distance`, `steps`.

**`legGeometry` (= `EncodedPolyline`)** (📘 Spec-Zitat, 🟢 live bestätigt):
```
EncodedPolyline:
  points:    string   # "The encoded points of the polyline using the Google polyline encoding."
  precision: integer  # "The precision of the returned polyline (7 for /v1, 6 for /v2)
                       #  Be aware that with precision 7, coordinates with |longitude| > 107.37 are undefined/will overflow."
  length:    integer  # Anzahl der Punkte
```
Änderungslog in der Spec-Datei wörtlich: *"/api/v2/{plan,trip} returns Google polylines with precision=6; since MOTIS 2.0.60"* bzw. *"/api/v1/{plan,trip} returns Google polylines with precision=7 (not defined for |longitude|>107)"*. Die aktuell deployten `v6`-Pfade verhalten sich wie `v2`: **Präzision 6** — 🟢 live nachgemessen (siehe 3.5).

**`Place`:** `id` (Stop-ID), `name`, `lat`, `lon`, ggf. `level`, Typ-Infos (`STOP`/`ADDRESS`/`PLACE`), bei Transit-Legs zusätzlich Track/Gleis-Infos.

**Fahrpreise (`withFares=true`):** Kein simples `fare: {amount, currency}`-Objekt (das wäre eine Vereinfachung) — MOTIS bildet das vollständige **GTFS-Fares-v2**-Modell ab: `Itinerary.fareTransfers` → Array von `FareTransfer` (mit `effectiveFareLegProducts`, `FareTransferRule` = `A_AB`/`A_AB_B`/`AB`) → `FareProduct` (`name`, `amount`, `currency` als ISO-4217, `FareMedia`). Jedes `Leg` referenziert per `fareTransferIndex`/`effectiveFareLegIndex`, zu welcher Fare-Gruppe es gehört. Insgesamt komplex und laut Spec **experimentell** — für den Grundstücks-Check vermutlich zunächst nicht relevant/nicht nötig.

### 2.4 Weitere Endpunkte im Detail (📘)

- **`/api/v1/geocode`**: Parameter `text` (Pflicht), `language` (array), `type` (array `LocationType`, z. B. nur `ADDRESS`+`STOP`), `mode` (array `Mode`, filtert Haltestellen nach bedienten Verkehrsmitteln), `place` (Koordinate zum Bias), `placeBias` (number, Default 1), `numResults` (Default 10, gedeckelt durch Server-Config `geocode_max_suggestions`).
- **`/api/v1/reverse-geocode`**: Parameter `place` (Pflicht, `"lat,lon"`), `type`, `numResults` (Default 5, gedeckelt durch `reverse_geocode_max_results`).
- **`/api/v1/one-to-many`**: reines **Straßen**-Routing (kein ÖPNV) von einem Punkt (`one`) zu mehreren Zielen (`many`), Parameter `mode`, `max` (Sekunden, gedeckelt durch `street_routing_max_direct_seconds`), `maxMatchingDistance`, `elevationCosts`, `arriveBy`, `withDistance`.
- **`/api/v6/one-to-all`**: **echter Isochronen-Endpunkt** — ein Startpunkt (`one`), `time`, `maxTravelTime`, `arriveBy`, plus dieselben Umstiegs-/Modi-Parameter wie `/plan` (`maxTransfers`, `transitModes`, `preTransitModes`, `postTransitModes`, `requireBikeTransport`/`CarTransport`, `maxPreTransitTime`, `maxPostTransitTime` etc.). ⚠️ Laut Nutzungsrichtlinie explizit als "resource-intensive" genannt → **vor Nutzung Matrix-Kontakt nötig**, deshalb hier **nicht live getestet**.
- **`/api/v6/stoptimes`**: `stopId`, `time`, `n` (Anzahl), Richtung (`arriveBy`), liefert Array `stopTimes[]` mit Ist-/Soll-Zeiten, Gleis, `tripFrom`/`tripTo`, `headsign`. 🟢 live getestet (Abschnitt 3.6).
- **`/api/v1/rentals`**: GBFS-Sharing-Fahrzeuge/Stationen im Gebiet (nur relevant, falls die Instanz GBFS-Feeds konfiguriert hat — bei Transitous für Sachsen vermutlich keine oder wenige lokale Anbieter eingebunden, nicht separat getestet).

---

## 3. Live-Beispiele gegen `https://api.transitous.org` — 🟢 alle am 29.08.2026 verifiziert

**Insgesamt 7 Requests** in dieser Recherche gestellt (Budget "max. ~10" eingehalten, mit 3–4 s Pause dazwischen). User-Agent bei jedem Request gesetzt (Policy-Pflicht): `GrundstuecksCheckSachsen-Research/0.1 (julian.dorn@schulverwalter.de; ...)`.

**Beobachtete Server-Version:** HTTP-Header `server: MOTIS v2.11.1` — leicht neuer als die auf `transitous.org/api/` verlinkte Referenz-Spec (Tag `v2.10.2`). Kein Grund zur Sorge, aber ein Hinweis, dass die verlinkte Spec-Version geringfügig hinter dem produktiv laufenden Server zurückliegt.

**Keine Rate-Limit-Header beobachtet** — in keiner der 7 Antworten erschien `X-RateLimit-*`, `Retry-After` o. ä. Es gibt serverseitige *Resultat*-Deckel (`geocode_max_suggestions`, `plan_max_results` etc., siehe Config-Referenz in Abschnitt 4), aber kein sichtbares HTTP-Rate-Limiting auf Protokollebene — die Beschränkung erfolgt stattdessen "sozial" über die Nutzungsrichtlinie (Abschnitt 5).

### 3.1 Geocoding-Test

```bash
curl -s -H "User-Agent: GrundstuecksCheckSachsen-Research/0.1 (julian.dorn@schulverwalter.de)" \
  "https://api.transitous.org/api/v1/geocode?text=Dresden%20Hauptbahnhof&language=de"
```
- **Status:** 200, **Antwortzeit:** 1,37 s
- Gekürzte Antwort:
```json
[{
  "type": "STOP",
  "name": "Dresden Hauptbahnhof",
  "id": "de-DELFI_de:14612:28_G",
  "lat": 51.03993, "lon": 13.732932,
  "country": "DE", "zip": "01069", "tz": "Europe/Berlin",
  "areas": [
    {"name": "Sachsen", "adminLevel": 4},
    {"name": "Dresden", "adminLevel": 6, "unique": true, "default": true}
  ],
  "modes": ["HIGHSPEED_RAIL","LONG_DISTANCE","COACH","NIGHT_RAIL","REGIONAL_RAIL","SUBURBAN","TRAM","BUS"]
}, { "type": "STOP", "name": "Dresden Hauptbahnhof Nord", "...": "..." },
   { "type": "PLACE", "category": "police_16", "name": "Bundespolizeirevier Dresden-Hauptbahnhof", "...": "..." }, "..." ]
```
Bestätigt: Stop-IDs folgen dem Schema `de-DELFI_de:<Gemeindeschlüssel>:<Nr>_G` — der DELFI-Datenherkunft entsprechend. Auch `areas` mit `adminLevel` liefert "Sachsen" korrekt als Bundesland.

### 3.2 Plan: TRANSIT + WALK, Leipzig → Dresden Hbf

```bash
curl -s -H "User-Agent: GrundstuecksCheckSachsen-Research/0.1 (julian.dorn@schulverwalter.de)" \
  --get "https://api.transitous.org/api/v6/plan" \
  --data-urlencode "fromPlace=51.3397,12.3731" \
  --data-urlencode "toPlace=51.0400,13.7322" \
  --data-urlencode "time=2026-08-31T08:00:00+02:00" \
  --data-urlencode "arriveBy=false" \
  --data-urlencode "transitModes=TRANSIT" \
  --data-urlencode "preTransitModes=WALK" \
  --data-urlencode "postTransitModes=WALK" \
  --data-urlencode "numItineraries=2"
```
- **Status:** 200, **Antwortzeit:** 1,08 s
- Gekürzte Antwort (1. Itinerary von 2):
```json
{
  "duration": 4860, "transfers": 1,
  "startTime": "2026-08-31T06:25:00Z", "endTime": "2026-08-31T07:46:00Z",
  "legs": [
    {"mode":"WALK","from":"START","to":"Leipzig Markt","duration":240},
    {"mode":"SUBURBAN","from":"Leipzig Markt","to":"Leipzig Hbf","duration":60},
    {"mode":"WALK","from":"Leipzig Hbf","to":"Leipzig Hbf","duration":300},
    {"mode":"HIGHSPEED_RAIL","from":"Leipzig Hbf","to":"Dresden Hauptbahnhof","duration":3960},
    {"mode":"WALK","from":"Dresden Hauptbahnhof","to":"END","duration":180}
  ]
}
```
(Zeiten sind UTC; 08:00 lokal = 06:00 UTC im Sommer, MOTIS hat die Abfahrt entsprechend passend im Suchfenster gefunden.) Gesamtreisezeit 81 Minuten, 1 Umstieg, Hauptleg ist der Fernverkehrszug (`HIGHSPEED_RAIL`) Leipzig Hbf → Dresden Hbf. Jedes Leg enthält `legGeometry` mit `precision: 6` (siehe 3.5).

### 3.3 Multimodal: Rad als Zubringer (`preTransitModes=BIKE`)

```bash
curl -s -H "User-Agent: ..." \
  --get "https://api.transitous.org/api/v6/plan" \
  --data-urlencode "fromPlace=51.3397,12.3731" \
  --data-urlencode "toPlace=51.0400,13.7322" \
  --data-urlencode "time=2026-08-31T08:00:00+02:00" \
  --data-urlencode "transitModes=TRANSIT" \
  --data-urlencode "preTransitModes=BIKE" \
  --data-urlencode "postTransitModes=WALK" \
  --data-urlencode "maxPreTransitTime=1800" \
  --data-urlencode "numItineraries=2"
```
- **Status:** 200, **Antwortzeit:** 1,93 s
- Ergebnis: 2 Itineraries geliefert; erste Route:
```json
[
  {"mode":"BIKE","from":"START","to":"Leipzig Hbf","duration":420},
  {"mode":"HIGHSPEED_RAIL","from":"Leipzig Hbf","to":"Dresden Hauptbahnhof","duration":3960},
  {"mode":"WALK","from":"Dresden Hauptbahnhof","to":"END","duration":180}
]
```
→ **Funktioniert genau wie in der Spec beschrieben:** Mit `preTransitModes=BIKE` fährt MOTIS statt zu Fuß mit dem Rad zur ersten Haltestelle (hier 7 Minuten statt vorher zu Fuß über Leipzig Markt + S-Bahn). Kein `directRentalFormFactors` o. ä. nötig, wenn es um das **eigene** Fahrrad geht (nicht Sharing).

### 3.4 Reine Auto-Route (`directModes=CAR`)

```bash
curl -s -H "User-Agent: ..." \
  --get "https://api.transitous.org/api/v6/plan" \
  --data-urlencode "fromPlace=51.3397,12.3731" \
  --data-urlencode "toPlace=51.0400,13.7322" \
  --data-urlencode "time=2026-08-31T08:00:00+02:00" \
  --data-urlencode "directModes=CAR" \
  --data-urlencode "transitModes=" \
  --data-urlencode "maxDirectTime=7200"
```
- **Status:** 200, **Antwortzeit:** 4,32 s (deutlich langsamer als die ÖPNV-Anfragen — Straßenrouting über ~130 km ist teurer)
- Ergebnis: `itineraries: []`, aber `direct: [{ duration: 4676, legs: [{mode: "CAR"}] }]`
- **→ Ja, Auto-Routing funktioniert auf Transitous.** 4676 s ≈ 78 Minuten für Leipzig → Dresden ist plausibel (reale Fahrzeit über A14 liegt bei knapp über 1 h). Wichtig: Auto-Routen erscheinen nicht in `itineraries`, sondern im separaten `direct`-Array, weil sie zeitunabhängig sind (keine Fahrplanbindung).

### 3.5 Reverse-Geocoding

```bash
curl -s -H "User-Agent: ..." --get "https://api.transitous.org/api/v1/reverse-geocode" \
  --data-urlencode "place=51.0400,13.7322"
```
- **Status:** 200, **Antwortzeit:** 1,48 s
- Erste Treffer: `DB Lounge` (Café am Bahnhof, `type: PLACE`), `Wiener Platz 4` (`type: ADDRESS`) — beide mit `Dresden`/`Sachsen` korrekt in `areas` erkannt.

### 3.6 Stoptimes Dresden Hbf

```bash
curl -s -H "User-Agent: ..." --get "https://api.transitous.org/api/v6/stoptimes" \
  --data-urlencode "stopId=de-DELFI_de:14612:28_G" \
  --data-urlencode "time=2026-08-31T08:00:00+02:00" --data-urlencode "n=3"
```
- **Status:** 200, **Antwortzeit:** 1,35 s. Liefert `stopTimes[]` mit realer Ankunft/Abfahrt (`arrival`, `departure`, `scheduledArrival`, `scheduledDeparture`), Gleis (`track: "Gl.14"`), `headsign`, `tripFrom`/`tripTo` — z. B. eine S-Bahn Richtung "Meißen S-Bf. Triebischtal".

### 3.7 `/api/v1/map/initial` — Kartentiles-Frage geklärt

```bash
curl -s -H "User-Agent: ..." "https://api.transitous.org/api/v1/map/initial"
```
- **Status:** 200, **Antwortzeit:** 1,25 s
- Antwort:
```json
{
  "lat": 45.176667, "lon": 12.932576, "zoom": 4,
  "serverConfig": {
    "motisVersion": "v2.11.1",
    "hasElevation": true, "hasRoutedTransfers": true, "hasStreetRouting": true,
    "maxOneToManySize": 128,
    "maxOneToAllTravelTimeLimit": 2880,
    "maxPrePostTransitTimeLimit": 7200,
    "maxDirectTimeLimit": 21600,
    "shapesDebugEnabled": true
  }
}
```
**Bestätigt: Kein Kartenkachel-Bild/-Vektor wird hier geliefert**, nur JSON-Metadaten (Default-Kartenmittelpunkt, Server-Limits). Nützlicher Nebenfund: die aktuell serverseitig gültigen Limits: `one-to-many` max. 128 Ziele, `one-to-all` max. 48 Min. Reisezeit (2880 s), Zubringer-Zeit max. 2 h (7200 s), Direktverbindung max. 6 h (21600 s).

---

## 4. Wie man `legGeometry` zu GeoJSON dekodiert

### 4.1 Bibliothek & Präzision

- **Format:** Google-Encoded-Polyline (dasselbe Verfahren wie bei Google Maps / OSRM), **nicht** GeoJSON direkt — Client-seitiges Dekodieren nötig.
- **Präzision: 6** (nicht der bei anderen Routing-APIs übliche Google-Standard 5!). Die Response nennt das sogar selbst im Feld `legGeometry.precision`, sodass man es nicht raten muss.
- 🟢 **Live verifiziert:** Aus Test 3.2 wurde die Geometrie des `HIGHSPEED_RAIL`-Legs (Leipzig Hbf → Dresden Hbf, String beginnt mit `_d{|`BisvrVsKqLqo@mr@...`, 8011 Zeichen, `precision: 6`, `length: 1766` Punkte) mit Python (`polyline`-Paket) dekodiert:
  - Mit `precision=6`: erster Punkt `(51.345488, 12.382021)`, letzter Punkt `(51.039875, 13.731396)` → **liegen exakt in Sachsen** (Leipzig-Umgebung → Dresden Hbf-Koordinate, deckt sich mit der Ziel-Koordinate `51.0400, 13.7322`).
  - Mit `precision=5` (falscher Wert): erster Punkt `(513.45488, 123.82021)` → **offensichtlich Faktor-10-Fehler**, weit außerhalb jeder gültigen Koordinate. Bestätigt eindeutig: **6 ist korrekt, 5 wäre falsch.**

### 4.2 Konkreter JS-Code fürs Frontend

npm-Paket: **`@mapbox/polyline`** (unterstützt konfigurierbare Präzision; das schlichte `polyline`-Paket auf npm tut dies teils auch, `@mapbox/polyline` ist der verbreitetste/gepflegteste Standard).

```js
import polyline from '@mapbox/polyline';

function legGeometryToGeoJSON(legGeometry) {
  // legGeometry = { points: "...", precision: 6, length: N }
  const coords = polyline.decode(legGeometry.points, legGeometry.precision); // [[lat, lon], ...]
  return {
    type: 'Feature',
    geometry: {
      type: 'LineString',
      coordinates: coords.map(([lat, lon]) => [lon, lat]) // GeoJSON = [lon, lat]!
    },
    properties: {}
  };
}
```

**Achtung Reihenfolge:** `polyline.decode()` gibt `[lat, lon]`-Paare zurück, GeoJSON verlangt `[lon, lat]` — das Vertauschen ist ein häufiger Bug-Quell.

**Achtung bei `numLegAlternatives`/Rentals/one-to-all:** auch dort tauchen `EncodedPolyline`-Objekte auf (z. B. `RentalStation`-Servicegebiete als Polygone aus mehreren Polylines mit Präzision 6, laut Spec-Zeile 4094 "encoded as polylines (with precision 6)") — überall dieselbe Dekodierlogik mit Präzision 6 verwenden, außer explizit anders im jeweiligen `precision`-Feld angegeben.

---

## 5. Self-Hosting einer eigenen MOTIS-Instanz — 🟢 am 01.09.2026 selbst gebaut und gemessen

Der ursprüngliche Abschnitt war eine Sammlung von Schätzungen. Er ist ersetzt
durch das, was ein tatsächlicher Import und ein tatsächlicher Serverlauf
ergeben haben. Alles hier Gemessene stammt von einer 4-Kern-Maschine mit 15 GiB
RAM, Docker 29.3.1, `overlayfs`.

### 5.1 Image

🟢 `ghcr.io/motis-project/motis` existiert; die Tag-Liste der Registry
(739 Tags, direkt über die OCI-API gelesen) endet bei **`2.11.2`**, und
`latest` zeigt auf denselben Index-Digest wie `2.11.2`
(`sha256:6055f51e…`) — `latest` ist also nicht `master`, sondern das jüngste
Release. Plattformen: `linux/amd64` und `linux/arm64`.

Das Image ist ein **Alpine 3.20** mit einem einzigen statischen Binary
`/motis` (68 MB entpackt), dazu `ui/` und `tiles-profiles/`. Busybox ist an
Bord (`wget`, `nc`), was für einen Healthcheck reicht. `ENTRYPOINT` ist leer,
`CMD` ist `/motis server /data`.

Verwendet wird ein **fester Tag** (`2.11.2`), nicht `latest` und nicht
`master`: ein Router, dessen Version sich beim nächsten `docker compose pull`
ändert, ändert auch seine Antworten.

### 5.2 CLI (v2 — anders als v1)

```
motis config <datei…>   erzeugt eine minimale config.yml aus den Eingabedateien
motis import -d DATA -c CONFIG   baut den Graphen
motis server -d DATA             serviert ihn; die Eingabedateien werden nicht mehr gelesen
```

`motis import --filter` kennt die einzelnen Teilschritte (`osr`, `adr`, `tt`,
`tbd`, `adr_extend`, `osr_footpath`, `matches`, `route_shapes`, `tiles`).

### 5.3 Eingabedaten — 🟢 gemessene Größen

| Datei | Quelle | Größe | Lizenz |
|---|---|---|---|
| OSM-Extrakt Sachsen | `https://download.geofabrik.de/europe/germany/sachsen-latest.osm.pbf` | ⚠️ in dieser Umgebung **nicht messbar**, s. u. | ODbL, © OpenStreetMap-Mitwirkende |
| OSM-Extrakt Leipzig (Ersatz für den Testlauf) | `https://download.bbbike.org/osm/bbbike/Leipzig/Leipzig.osm.pbf` | 🟢 **71 859 038 B (68,5 MiB)**, Stand 29.08.2026 | ODbL |
| DELFI-GTFS Deutschland | `https://api.transitous.org/gtfs/de_DELFI.gtfs.zip` | 🟢 **349 439 776 B (333 MiB)**, Stand 31.08.2026 | CC-BY 4.0, DELFI e. V. |

**Der GTFS-Fund ist der wichtigste dieses Abschnitts.** Der DELFI-Datensatz auf
`opendata-oepnv.de` ist registrierungspflichtig — aber Transitous stellt seinen
**gesamten Quelldatensatz** unter `https://api.transitous.org/gtfs/` bereit
(die Nutzungsrichtlinie verweist selbst darauf: *"There is no need to scrape
data using the API, you may download our entire source dataset here"*), und
darin liegt `de_DELFI.gtfs.zip` — dieselbe Datei, die die öffentliche Instanz
fährt. Ohne Account, und garantiert derselbe Fahrplanstand wie der Dienst,
gegen den verglichen wird. Dort liegt auch Transitous' eigene
`config.yml` (445 kB), aus der die Einstellungen unten übernommen sind.

Entpackt sind das 🟢 **3,3 GB**; `stop_times.txt` allein ist 2 975 462 191 B.
Was **fehlt**: eine `shapes.txt`. Der DELFI-Datensatz enthält keine
Linienverläufe (siehe 5.6).

⚠️ **Geofabrik war aus dieser Sandbox nicht erreichbar** — jede Verbindung zu
`download.geofabrik.de` wurde nach ~7 s vom Egress-Relay abgebrochen
(`Recv failure: Connection reset by peer`, drei Wiederholungen, auch für die
HTML-Seite). Das ist eine Eigenschaft dieser Umgebung, keine Aussage über den
Dienst. Größe und Prüfsumme von `sachsen-latest.osm.pbf` sind daher **nach wie
vor nicht selbst gemessen**. Für den Testlauf wurde stattdessen der
BBBike-Extrakt Leipzig genommen; er deckt das Testpaar
Liebertwolkwitz → Leipzig Hbf vollständig ab. Sachsen ist etwa dreimal so groß
wie dieser Ausschnitt, der Import-Anteil `osr`+`adr` (35 s von 3 min 30 s)
wächst entsprechend — der teure Teil ist der deutschlandweite Fahrplan, und der
ist vom OSM-Ausschnitt unabhängig.

### 5.4 Konfiguration — was tatsächlich lief

`motis/config.yml` im Repo. Die Punkte, die nicht offensichtlich sind:

- **`datasets:` muss den Tag `de-DELFI` tragen.** Der Tag ist das Präfix jeder
  Stop- und Trip-ID, die MOTIS herausgibt (`de-DELFI_de:14713:11559::01`).
  Transitous benutzt genau diesen, die aufgezeichneten Fixtures im Repo tragen
  ihn — mit einem anderen Tag antwortet die lokale Instanz mit anderen IDs.
- **`tiles:` bleibt weg.** Die App bringt ihre eigene Grundkarte mit, und der
  Tile-Import ist die teure Hälfte eines MOTIS-Builds.
- `preprocess_max_matching_distance: 250` — Haltestellen außerhalb des
  OSM-Ausschnitts behalten ihre Feed-Koordinaten, statt mangels Straße zu
  verschwinden.
- `limits.onetomany_max_many: 128` und `max_max_matching_distance: 250` sind
  die Serverseite dessen, was `backend/app/services/motis.py` sendet.

### 5.5 🟢 Gemessene Kosten

**Import** (Leipzig-OSM + deutschlandweiter DELFI-GTFS, 4 Kerne):

| | ohne `route_shapes` | mit `route_shapes` (so wie eingecheckt) |
|---|---|---|
| Wanduhr | **3 min 30 s** | **6 min 07 s** |
| Spitzen-RSS (Stichprobe alle 10 s) | **5,34 GiB** | **5,64 GiB** |
| Spitze inkl. Page-Cache | **5,85 GiB** | **5,88 GiB** |
| Ergebnis auf Platte | **2 905 221 798 B = 2,9 GB** | **3 432 193 576 B = 3,4 GB** |

Das Nachrouten der Linienverläufe kostet also rund **2 min 45 s** und **530 MB**
und ist der einzige Grund, warum der Import über sechs statt dreieinhalb
Minuten läuft. Mit einem Sachsen-Extrakt statt Leipzig wird dieser Posten
größer, weil mehr Linien im Ausschnitt liegen und damit überhaupt geroutet
werden können.

MOTIS schreibt selbst eine `timing.txt` in das Datenverzeichnis. Aufteilung:

```
osr           30,3 s   Straßennetz aus dem OSM-Extrakt
adr            5,0 s   Adressindex
tt           2 min 19  Fahrplan  (Read Stop Times 35,6 s, Read Frequencies 33,5 s,
                                  Read Trips 22,1 s, Finalizing 21,2 s)
adr_extend    13,0 s   Haltestellennamen in den Adressindex
matches        3,8 s   Haltestelle ↔ Straße
osr_footpath  34,7 s   Umstiegsfußwege über echte Wege
```

Der Fahrplan ist also zwei Drittel der Zeit und praktisch der gesamte
Speicherbedarf. `timetable_metrics.json` nach dem Import:
`507 292` Haltestellen, `2 684 560` Fahrten, `66 199 571` Fahrt×Tag.

Bemerkenswert: `first_day: TODAY`, `num_days: 365` ergibt
`"firstDay":"2026-08-29","lastDay":"2026-12-13"` — der DELFI-Kalender endet im
Dezember, MOTIS lädt nicht mehr, als der Feed hergibt. **Ein Fahrplan altert;**
ohne wöchentliche Aktualisierung liefert die Instanz ab Mitte Dezember keine
Fahrten mehr.

**Serverbetrieb:** `motis server` ist **wenige Sekunden** nach dem Start
ansprechbar (der Graph wird gemappt, nicht geladen). Nach den Testabfragen:
**1,70 GiB RSS**, Spitze 1,74 GiB (ohne die gerouteten Linienverläufe 1,55 GiB).
Zum Vergleich: das Backend daneben braucht 63 MiB.

**Platte insgesamt:** 0,42 GB Eingabedaten + 3,4 GB Graph + 68 MB Image
≈ **3,9 GB**. Mit einem Sachsen-Extrakt statt Leipzig eher 3,5 GB, mit einem
Deutschland-Extrakt (`germany-latest.osm.pbf`, 🟢 5 866 637 019 B bei
`download.openstreetmap.fr`) deutlich mehr.

### 5.6 🟢 Der lokale Router gegen Transitous — Abgleich

Verglichen wurde mit denselben Anfragen, die `backend/app/services/motis.py`
stellt, am 01.09.2026, Abfahrt 02.09.2026 08:00 UTC,
Liebertwolkwitz (51,2686/12,4726) → Leipzig Hbf (51,34547/12,38206):

| Endpunkt | Ergebnis |
|---|---|
| `/api/v1/geocode` | 🟢 **identisch** — dieselben zehn Treffer, dieselbe Reihenfolge, dieselben Koordinaten. Unterschiedlich nur der `score` (2. Nachkommastelle) und `areas[0].name` ("Leipzig" lokal, "Deutschland" bei Transitous — Folge des planetenweiten OSM dort). |
| `/api/v6/plan` (TRANSIT) | 🟢 **identisch** in Dauer, Umstiegen, Abfahrts- und Ankunftszeit, Linien und Halten: 62 min mit Bus 75 + Tram 15, bzw. 49 min mit RB113 ab Großpösna. |
| `/api/v1/one-to-many` | 🟢 **byte-identisch**, bis auf die letzte Stelle der Fließkomma-Distanzen (`2542.3024253845215`). |
| `/api/v6/map/stops` | 🟢 **identische Menge** — 21 Haltestellen im Testfenster, gleiche Namen, Koordinaten und `modes`. Transitous liefert zusätzlich `tz`; das Backend liest es nicht. |
| `/api/reachability` (die App selbst) | 🟢 Auto 16 min, Rad 51 min, `transit_auto` 30 min über Park-and-Ride an der Augustusplatz-Haltestelle — **Zeichen für Zeichen dieselbe Antwort** wie gegen Transitous, samt des deutschen `hinweis`-Textes der Zubringer-Automatik. |

**Der eine echte Unterschied: die Geometrie der ÖPNV-Teilstrecke.**

| Modus | Punkte lokal | Punkte Transitous | gleich? |
|---|---|---|---|
| Auto | 512 | 512 | ja |
| Rad | 501 | 501 | ja |
| ÖPNV | **67** | **303** | nein |

Ursache: der DELFI-GTFS hat keine `shapes.txt`, also zeichnet MOTIS die
Bahnstrecke als Luftlinie zwischen den Halten. Der Schalter dagegen ist
`timetable.route_shapes` (setzt `with_shapes`, `osm` und `street_routing`
voraus); in Transitous' veröffentlichter `config.yml` steht er nicht, ihre
Instanz verhält sich aber so, als stünde er dort.

🟢 **Mit `route_shapes: {mode: missing}` verschwindet der Unterschied
vollständig:** derselbe Lauf liefert für alle drei Teilstrecken exakt dieselbe
Polyline wie Transitous (Zeichen für Zeichen, 1 074 Zeichen für die
RB113-Strecke), und die komplette `/api/reachability`-Antwort der App ist
danach identisch — Auto 512 Punkte, Rad 501, ÖPNV 303, alle gleich. Deshalb
steht der Schalter in `motis/config.yml`. Fuß-, Rad- und Autostrecken waren
ohnehin nie betroffen; die kommen aus dem Straßengraphen.

### 5.7 Einbindung ins Repo

`docker-compose.yml`, Profil `local-routing`, zwei Dienste:

- `motis-import` — einmalig, `restart: "no"`, schreibt in das Volume
  `motis-graph` und legt danach `/data/meta/import_done` an; ein weiterer
  `up`-Aufruf überspringt den Import.
- `motis` — `motis server -d /data`, `depends_on: service_completed_successfully`,
  Healthcheck über den Geocoder (der antwortet erst, wenn der Adressindex
  gemappt ist).

Der Backend-Dienst bekommt `environment: - MOTIS_BASE_URL` **ohne Wert**:
Compose reicht die Variable nur durch, wenn sie gesetzt ist, und lässt sie
sonst ganz weg — `backend/.env` und der eingebaute Standard (Transitous)
behalten also das letzte Wort, solange niemand etwas anderes verlangt.

```bash
./motis/fetch-data.sh
MOTIS_BASE_URL=http://motis:8080 docker compose --profile local-routing up --build
```

`docker compose up` ohne Profil bleibt unverändert bei zwei Containern.

⚠️ **Der Plattencache des Backends kennt die Basis-URL nicht.** Sein
Schlüssel besteht nur aus den Anfrageparametern, also liefert ein Umschalten
von Transitous auf die eigene Instanz weiterhin die alten Antworten, bis
`/cache/motis*` gelöscht ist. Beim Vergleich der beiden Instanzen hat genau das
zunächst ein falsches Ergebnis vorgetäuscht.

---

## 6. Nutzungsrichtlinie von Transitous — wörtliche Zitate

Quelle: `https://transitous.org/api/` (🟢 am 29.08.2026 abgerufen, Text unten wortgetreu extrahiert).

> "Transitous is provided by a community of volunteers to fulfill the needs of Free and Open Source applications. We provide the service on a best-effort basis and reserve the right to stop providing it to any consumer at any time."

**Zulässigkeitskriterien** ("Can I use it? Go ahead if all of these points apply to your project"):
> "Your project is open-source" / "Your project is not commercial" / "Your project is light on our resources" / "Your project conforms to our usage policy below"

**Pflichten bei Nutzung:**
- **Quellcode veröffentlichen:** *"Make sure your source code is published under an appropriate open-source license (light prototype testing before that is fine)."*
- **Bei Unsicherheit über Last vorher fragen:** *"If you have any doubt about the load your requests will be causing (expensive requests, many users, etc.), please contact us in our Matrix Channel to make sure we can handle your expected resource usage."*
- **User-Agent-Pflicht:** *"Make sure you send HTTP User-Agent headers with every request, containing at least the following information: Name of the application / Version of the client / A way of contact (e-mail address or website URL)."* Bei Browser-Anwendungen ersetzt der `Referer`-Header dies, dann muss aber die Kontaktinfo auf der verlinkten Website stehen.
- **Attribution:** *"Link to https://transitous.org/sources/ in a visible place. [...] since Transitous uses OpenStreetMap data, you have to adhere to its attribution guidelines, too."*
- **Showcase (optional):** *"You may add your application to the Transitous website."*

**Ressourcen-Nutzung — die zentrale Einschränkung für dieses Projekt:**
> "Please contact us before using any potentially **resource-intensive API endpoints (such as routing, isochrones)** or doing **many requests** (also from different users) in your project."

> "There is no need to scrape data using the API, you may download our entire source dataset here."

**Kommerzielle Nutzung — verboten:**
> "Due to data source licences and resource prioritisation, **commercial use is not allowed**. If you are unsure whether your use is commercial, please contact us in advance."

**Sonstiges:**
- Basis-Endpunkt ausschließlich `https://api.transitous.org/api/` — interne/Ballast-Endpunkte (`*.motis-project.org`, `*.motis-project.de`, `*.spline.de`, `staging.api.transitous.org`) *"must not be used by applications"*.
- Es existiert eine **Staging-Instanz** (`https://staging.api.transitous.org/api/`) zum Testen neuer MOTIS-Releases, dort aber *"full planet-wide OpenStreetMap data is not available"*.

**Einordnung für den Grundstücks-Check:** Da das Projekt "Grundstücks-Check Sachsen" vermutlich früher oder später produktiv mit echten Nutzern läuft und regelmäßig `/plan`-Anfragen (per Definition "routing" = resource-intensive) stellt, greift die Pflicht *"please contact us before [...] doing many requests"* — spätestens beim Übergang vom Prototyp zu echtem Nutzerverkehr sollte das Transitous-Team über den Matrix-Channel kontaktiert werden. Kommerzielle Nutzung (falls das Projekt monetarisiert werden sollte) ist mit der aktuellen Policy **nicht vereinbar** und müsste separat geklärt werden (eigene Instanz oder Rücksprache mit dem Team).

---

## 7. Fallstricke

1. **Kein `wheelchair`-Parameter** — Barrierefreiheit läuft über `pedestrianProfile=WHEELCHAIR`, nicht über ein Boolean. Wer die Aufgabenstellung wörtlich nimmt und nach `wheelchair=true` sucht, findet nichts.
2. **`legGeometry`-Präzision ist 6, nicht der Google-Standard 5** — viele generische Polyline-Decoder (z. B. simple `google-polyline`-Ports) verwenden standardmäßig Präzision 5. Immer explizit `legGeometry.precision` aus der Response verwenden statt zu raten oder eine feste Präzision zu hardcoden.
3. **Auto-/Direktverbindungen (`directModes=CAR`/`BIKE`/`WALK`) landen in `direct[]`, nicht in `itineraries[]`** — wer nur `itineraries` auswertet, übersieht reine Fußweg-/Rad-/Auto-Ergebnisse komplett (in Test 3.4 war `itineraries: []`, aber `direct` enthielt die Route).
4. **`transitModes` leer lassen ≠ "kein ÖPNV"** — im CAR-Test wurde `transitModes=` (leerer Wert) übergeben; das Verhalten war korrekt (keine Transit-Itineraries), sollte aber in eigenen Implementierungen explizit getestet werden, da eine leere Modi-Liste je nach Client-Bibliothek anders serialisiert werden kann (z. B. Parameter ganz weglassen vs. leerer String vs. leeres Array).
5. **`/one-to-all` (Isochronen) ist laut Policy explizit "resource-intensive"** — nicht ungefragt in Produktion mit hoher Frequenz nutzen (z. B. nicht bei jedem Kartenklick neu berechnen); vorher Rücksprache mit dem Transitous-Team, oder für produktive Isochronen-Nutzung eine eigene MOTIS-Instanz betreiben.
6. **Server-Antwort-Version und Doku-Version können auseinanderlaufen** — live lief `v2.11.1`, die von `transitous.org/api/` verlinkte Referenz-Spec war zum Zeitpunkt der Recherche für `v2.10.2` getaggt. Bei Detailfragen zu neuen/geänderten Feldern lohnt sich ein Blick in den `server`-Header und ggf. das dazu passende Spec-Tag statt blind der verlinkten Version zu vertrauen.
7. **Zeiten sind durchgängig UTC (ISO-8601 mit `Z`)**, nicht Europe/Berlin — bei der Anzeige für Nutzer in Sachsen muss selbst nach `Europe/Berlin` konvertiert werden (Sommerzeit beachten). MOTIS gibt clientseitig keine Zeitzoneninformation zur Umrechnung mit, nur die `tz`-Angabe in `Place`/Haltestellen-Objekten (z. B. `"tz":"Europe/Berlin"` bei Dresden Hbf) kann dafür herangezogen werden.
8. **`maxPreTransitTime`/`maxPostTransitTime` sind standardmäßig nur 900 s (15 Min.)** — bei Rad-Zubringern (die typischerweise weiter fahren als zu Fuß möglich) muss dieser Wert aktiv erhöht werden (siehe Test 3.3, dort auf 1800 s gesetzt), sonst werden mögliche Rad-Routen mit längerer Zubringerstrecke fälschlich nicht gefunden.
9. **Keine Kartenkacheln von Transitous nutzbar** — für die Sachsen-Karte im Grundstücks-Check muss ein separater Kartenanbieter eingebunden werden (z. B. offizielle OSM-Tiles unter Beachtung von deren eigener Nutzungsrichtlinie, oder ein selbst gehosteter Vektor-Tile-Stack); MOTIS' `/map/*`-Endpunkte liefern nur Overlay-Daten (Stops, Trips, Routen), keine Grundkarte.
10. **Fahrpreisdaten (`withFares`) sind experimentell und komplex** (GTFS-Fares-v2-Modell mit `fareTransfers`/`FareTransferRule`) — für den MVP vermutlich zu aufwendig, ggf. erstmal ohne Fahrpreisanzeige starten.
11. **Geofabrik ist aus der Entwicklungsumgebung nicht erreichbar** — am 29.08.2026 und erneut am 01.09.2026 brach jede Verbindung zu `download.geofabrik.de` nach ~7 s ab, auch für die reine HTML-Seite. Das ist der Egress-Proxy dieser Umgebung, keine Aussage über den Dienst; auf einer normalen Maschine ist `sachsen-latest.osm.pbf` der richtige Extrakt. Für einen Testlauf hier tut es ein BBBike-Stadtextrakt (`https://download.bbbike.org/osm/bbbike/Leipzig/Leipzig.osm.pbf`, 68,5 MiB), der Deutschland-Extrakt von `download.openstreetmap.fr` (5,87 GB) wäre die Alternative mit voller Abdeckung.
12. **Der DELFI-GTFS enthält keine `shapes.txt`** — ohne `timetable.route_shapes` zeichnet eine eigene Instanz jede Bahn- und Busstrecke als Luftlinie zwischen den Halten. Straßenrouten (Fuß, Rad, Auto) sind davon nicht betroffen.
13. **Der Dataset-Tag ist Teil jeder ID** — `datasets: de-DELFI:` in der Config, sonst antwortet die eigene Instanz mit `de_…` statt `de-DELFI_…` und passt nicht mehr zu den aufgezeichneten Fixtures.

---

## 8. Quellenübersicht

- MOTIS OpenAPI-Spec, Tag `v2.10.2`: `https://raw.githubusercontent.com/motis-project/motis/refs/tags/v2.10.2/openapi.yaml` (📘, Rohdatei direkt geparst)
- MOTIS README: `https://raw.githubusercontent.com/motis-project/motis/master/README.md` (📘)
- MOTIS Setup-Doku: `https://raw.githubusercontent.com/motis-project/motis/master/docs/setup.md` (📘, Rohdatei direkt geparst)
- MOTIS/prima Docker-Compose-Beispiel: `https://raw.githubusercontent.com/motis-project/prima/master/docker-compose.yml` (📘, Rohdatei direkt geparst)
- Transitous API/Policy-Seite: `https://transitous.org/api/` (🟢 live abgerufen 29.08.2026, Text direkt aus HTML extrahiert)
- Transitous-Quelldatensatz und dessen MOTIS-`config.yml`: `https://api.transitous.org/gtfs/` (🟢 01.09.2026 abgerufen, `de_DELFI.gtfs.zip` heruntergeladen und importiert)
- GHCR-Tagliste `ghcr.io/motis-project/motis` über die OCI-Registry-API (🟢 01.09.2026, 739 Tags, `latest` = `2.11.2`)
- MOTIS-Setup-Doku `docs/setup.md`, Stand `master` (📘 01.09.2026 erneut gelesen — Shapes-Abschnitt)
- Transitous/MOTIS-Notes-Wiki (⚠️ ältere Architektur-Generation, mit Vorsicht zu lesen): `https://github.com/public-transport/transitous/wiki/MOTIS-Notes`
- Alle Live-Requests aus Abschnitt 3: direkt gegen `https://api.transitous.org` am 29.08.2026, Rohantworten lokal im Scratchpad gespeichert und mit Python nachgeprüft (u. a. Polyline-Dekodierung).

---

## 9. Zubringer und Abholer — Nachtrag vom 31.08.2026 🟢

Nachgetragen, weil die Anwendung ab jetzt nicht mehr nur `preTransitModes=BIKE`
kennt, sondern die Wahl des Zubringers pro Ziel trifft. **Alles hier ist live
gegen `https://api.transitous.org` geprüft** (Server-Header weiterhin
`MOTIS v2.11.1`), 14 Requests, User-Agent
`GrundstuecksCheckSachsen/0.1 (+https://github.com/mcguenther/where2build)`,
mindestens 4 s Pause dazwischen. Die Rohantworten liegen — auf die vom Code
gelesenen Felder gekürzt, Polylinien auf je fünf ihrer eigenen echten Punkte
ausgedünnt — als Fixtures unter `backend/tests/fixtures/motis_plan_*.json`.

### 9.1 Die Anfrage

```
GET /api/v6/plan
  ?fromPlace=<lat,lon>&toPlace=<lat,lon>
  &transitModes=TRANSIT
  &preTransitModes=WALK|BIKE|CAR_PARKING
  &postTransitModes=WALK
  &maxPreTransitTime=1800
  &numItineraries=2
  &time=2026-09-01T06:00:00Z
```

### 9.2 Was die drei Zubringer-Modi wirklich tun

| `preTransitModes` | Was in der Antwort steht |
|---|---|
| `WALK` | Fuß-Leg bis zur ersten Haltestelle. Der Standard. |
| `BIKE` | Rad-Leg bis zur Haltestelle. Das Rad bleibt dort: die Transit-Legs derselben Verbindung tragen `bikesAllowed: false`, es wird also nichts mitgenommen — Bike-and-Ride, nicht Radmitnahme. |
| `CAR_PARKING` | `CAR`-Leg auf einen Punkt ohne Namen, dann `WALK` zur Haltestelle. Das ist Park-and-Ride. In der Spec als *experimentell* geführt, antwortet aber zuverlässig. |
| `CAR` (verworfen) | Fährt **auf den Bahnsteig** und lässt das Auto dort stehen. Leipzig → Dresden: `CAR:240 → Leipzig Hbf`, kein Parkplatz, kein Fußweg. Gegenprobe mit `CAR_PARKING` an derselben Stelle: `CAR:120 + WALK:540`. `CAR` ist damit für „Auto zum ÖPNV“ die falsche Angabe. |

**`CAR_PARKING` liefert beide Formen.** In der Leipziger Antwort war die zweite
Verbindung ein blankes `CAR`-Leg bis zur Haltestelle — also eine Fahrt ohne
Abstellmöglichkeit. Der Code erkennt das an der Folge „CAR-Leg, dann WALK-Leg“
(`parks_the_car()` in `services/motis.py`) und schreibt es auf die Karte, statt
einen Parkplatz zu behaupten, den MOTIS nicht gefunden hat.

### 9.3 Warum der Abholer immer `WALK` bleibt

`postTransitModes=BIKE` **antwortet** — und erfindet dabei ein Rad am Zielbahnhof:

```
BIKE:240 + REGIONAL_RAIL:1020 + WALK:300 + HIGHSPEED_RAIL:3960 + BIKE:120
```

Beide Transit-Legs dieser Verbindung tragen `bikesAllowed: false`. Das Rad, mit
dem die letzten zwei Minuten gefahren werden, kann also gar nicht dort sein.
Aufgezeichnet als `motis_plan_rad_am_zielende.json`. Eine Reise, die niemand
antreten kann, ist schlechter als gar keine — deshalb ist der Abholer in allen
drei Spielarten `WALK`.

### 9.4 Die gemessenen Fälle (Grundlage der Automatik)

Alle nach Dresden Hbf (51.040684, 13.731863), Abfahrt 01.09.2026 06:00 UTC:

| Start | zu Fuß zum ÖPNV | mit dem Rad | mit dem Auto (P+R) |
|---|---|---|---|
| **Moritzburg** (51.16758, 13.67797 — das Flurstück aus `alkis_flurstueck_moritzburg.gml`) | Zubringer **660 s**, gesamt 2 940 s | Zubringer **420 s**, gesamt **2 700 s** | Zubringer 1 200 + 480 s, gesamt 2 040 s |
| **Hinterhermsdorf** (50.9539, 14.3676) | Zubringer **1 740 s**, gesamt 11 760 s | Zubringer **900 s**, gesamt **6 240 s** | Zubringer 1 200 + 360 s, gesamt 7 200 s |
| **Liebertwolkwitz** (51.282637, 12.463172) | Zubringer 300 s, gesamt 7 320 s | Zubringer 240 s, gesamt 6 240 s | Zubringer 840 + 480 s, gesamt 5 460 s |

Zum Vergleich durchgehend ab Moritzburg: Auto 1 320 s, Rad 4 524 s.

Zwei Beobachtungen, die die Regel geformt haben:

1. **Moritzburg ist der Lehrbuchfall der Nutzerregel.** 11 Minuten zu Fuß zur
   Haltestelle, 7 mit dem Rad: die Regel schaltet auf Rad, und weil der Radweg
   unter 10 Minuten bleibt, wird das Auto gar nicht erst geprüft — obwohl es
   mit 2 040 s schneller wäre. Genau das ist gewollt: 7 Minuten Radweg sind
   niemandes Grund, das Auto zu nehmen.
2. **Liebertwolkwitz zeigt, dass die Schwelle allein nicht reicht.** Der Fußweg
   zur ersten Haltestelle ist nur 5 Minuten — die Regel würde also beim Fuß
   bleiben und 7 320 s anzeigen, obwohl Rad + Bahn 6 240 s brauchen. Der kurze
   Weg führt hier zu einer Bushaltestelle, nicht zum Bahnhof. Deshalb hat die
   Automatik neben der Schwelle einen zweiten Auslöser: eine Ersparnis von
   mindestens 10 Minuten auf der **Gesamtreise**.
3. **Hinterhermsdorf zeigt, wo die Uhr die Regel überstimmt.** 15 Minuten
   Radzeit schalten das Auto frei — und Park-and-Ride kommt mit 7 200 s
   langsamer heraus als das Rad mit 6 240 s. Die Sprosse wird geprüft und
   verworfen, und die Karte sagt warum.

### 9.5 Die Regel, wie sie implementiert ist

`MotisService.transit_auto()` in `backend/app/services/motis.py`:

- **Ist am Ziel ein Zubringer festgelegt** (`zubringer` = `walk`/`bike`/`car`),
  wird genau der gefahren — ein Request, keine Automatik.
- **Sonst** werden Fuß und Rad gemeinsam angefragt (zwei Requests). Das Rad
  gewinnt, wenn es überhaupt schneller ist **und** entweder der Fußweg zur
  ersten Haltestelle ≥ 10 Minuten dauert **oder** die Gesamtreise um ≥ 10
  Minuten kürzer wird.
- **Das Auto wird nur angefragt**, wenn der Radzubringer ≥ 10 Minuten dauert
  (die Regel des Nutzers) oder weder zu Fuß noch mit dem Rad eine Haltestelle
  erreichbar war. Eine reine Zeitersparnis schaltet es nicht frei: hinfahren
  und den Tag über parken ist eine Festlegung, die Minuten allein nicht
  rechtfertigen.
- **Gewählt wird nie eine langsamere Sprosse.** Ist die höhere nicht schneller,
  bleibt die niedrigere stehen, und der Hinweistext nennt beide Zeiten.
- Der `hinweis` der Antwort trägt die Zahlen, auf denen entschieden wurde. Ein
  stillschweigend ersetztes Verkehrsmittel ist eine Zahl, die niemand prüfen
  kann.

Die Schwelle (`ACCESS_THRESHOLD_S`) und die Mindestersparnis (`MIN_SAVING_S`)
stehen beide auf 600 s — die zehn Minuten, die der Nutzer genannt hat.

### 9.6 Kosten gegenüber Transitous

Vorher ein Request je Ziel und Verkehrsmittel (3). Jetzt: Auto, Rad und für die
ÖPNV-Zeile zwei — also 4 statt 3, in seltenen Fällen 5. Ein Ziel mit
festgelegtem Zubringer kostet wieder 3. `max_concurrency` bleibt bei 2, der
Plattencache bleibt bei einer Stunde.
