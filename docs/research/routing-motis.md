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
- **Self-Hosting ist für Sachsen realistisch machbar**: ein `sachsen-latest.osm.pbf` von Geofabrik plus ein GTFS-Datensatz (ganz Deutschland von DELFI/opendata-oepnv.de, oder ein Sachsen-Ausschnitt) reichen. RAM-Bedarf für eine Region der Größe Sachsens dürfte im niedrigen einstelligen GB-Bereich liegen (⚠️ nicht live verifiziert, siehe Abschnitt 4.4).
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

## 5. Self-Hosting einer eigenen MOTIS-Instanz für Sachsen

### 5.1 Docker-Image

📘 Offizielles Image: **`ghcr.io/motis-project/motis:master`** (aus dem produktiv genutzten `docker-compose.yml` des MOTIS-eigenen "prima"-Projekts, `motis-project/prima`). Es gibt zusätzlich versionierte GitHub-Releases zum direkten Download (`motis-linux-amd64.tar.bz2` etc., ohne Docker), falls kein Container gewünscht ist.

### 5.2 Nötige Eingabedaten

1. **OSM-Extrakt:** `sachsen-latest.osm.pbf` von Geofabrik (`https://download.geofabrik.de/europe/germany/sachsen-latest.osm.pbf`). ⚠️ Diese URL konnte in dieser Session **nicht live erreicht werden** (Verbindungsabbruch über den Recherche-Proxy) — Existenz und exakte Dateigröße sind daher **nicht live verifiziert**, aber Geofabrik-Sachsen-Extrakte sind ein seit Jahren etabliertes, öffentlich bekanntes Angebot; die URL-Struktur ist Standard für alle deutschen Bundesländer bei Geofabrik.
2. **GTFS-Fahrplandaten:** DELFI-Datensatz "Deutschlandweite Sollfahrplandaten (GTFS)" über `opendata-oepnv.de` (Menüpunkt DELFI). 📘 Laut Portal ist der Download **registrierungspflichtig** (kostenlos, aber Account nötig), Updates i. d. R. **montags**. Es gibt keinen von DELFI selbst bereitgestellten Sachsen-Only-Ausschnitt — man lädt entweder den Deutschland-GTFS komplett (funktioniert mit MOTIS problemlos, auch bei einem kleineren OSM-Extrakt, da MOTIS Haltestellen außerhalb des OSM-Bereichs zwar für ÖPNV nutzt, aber ohne Straßen-Routing/Zubringer dorthin) oder filtert selbst z. B. mit `gtfs-filter`/eigenen Skripten auf Sachsen-Haltestellen.
3. Optional Echtzeitdaten (GTFS-RT): z. B. `https://stc.traines.eu/mirror/german-delfi-gtfs-rt/latest.gtfs-rt.pbf` (📘 wörtlich als Community-Mirror-Beispiel in der offiziellen MOTIS-Doku genannt, für ganz Deutschland).

### 5.3 Lauffähiges Beispiel: `docker-compose.yml` + `config.yml`

📘 Basierend auf dem offiziell dokumentierten Workflow (`./motis config` → `./motis import` → `./motis server`) und dem echten `docker-compose.yml`-Muster aus `motis-project/prima`, angepasst auf Sachsen:

**`docker-compose.yml`:**
```yaml
version: "3"
services:
  motis-import:
    image: ghcr.io/motis-project/motis:master
    volumes:
      - ./sachsen-latest.osm.pbf:/data-input/sachsen-latest.osm.pbf:ro
      - ./gtfs-deutschland.zip:/data-input/gtfs-deutschland.zip:ro
      - ./config.yml:/data-input/config.yml:ro
      - motis-data:/data:rw
    working_dir: /data
    command: /bin/sh -c "/motis import -c /data-input/config.yml"

  motis-server:
    image: ghcr.io/motis-project/motis:master
    depends_on:
      motis-import:
        condition: service_completed_successfully
    volumes:
      - motis-data:/data:rw
    working_dir: /data
    ports:
      - "8080:8080"
    command: /bin/sh -c "/motis server -c /data-input/config.yml"
    restart: unless-stopped

volumes:
  motis-data:
```

**`config.yml`** (📘 zusammengesetzt aus den offiziell dokumentierten Config-Keys, `docs/setup.md`):
```yaml
server:
  host: 0.0.0.0
  port: 8080
  web_folder: ui
  data_attribution_link: https://www.opendata-oepnv.de/ht/de/organisation/delfi/startseite

osm: /data-input/sachsen-latest.osm.pbf   # benötigt für Straßenrouting, Geocoding, Reverse-Geocoding

timetable:
  first_day: TODAY
  num_days: 365
  railviz: true
  with_shapes: true
  datasets:
    de:
      path: /data-input/gtfs-deutschland.zip
      # rt:
      #   - url: https://stc.traines.eu/mirror/german-delfi-gtfs-rt/latest.gtfs-rt.pbf

street_routing: true          # aktiviert BIKE/CAR/WALK-Routing über OSM
osr_footpath: true            # Fußwege/Umstiege über OSM statt reiner GTFS-Transferzeiten
geocoding: true
reverse_geocoding: true

limits:
  plan_max_results: 20
  onetoall_max_travel_minutes: 60
  routing_max_timeout_seconds: 30

logging:
  log_level: info
```

**Ablauf:**
```bash
docker compose run --rm motis-import
docker compose up -d motis-server
# API danach lokal erreichbar unter http://localhost:8080/api/v6/plan?...
```

### 5.4 RAM-/Disk-Bedarf und Import-Dauer

⚠️ **Hier gibt es keine belastbare, live verifizierte Zahl speziell für Sachsen** — weder die offizielle MOTIS-Doku noch das README nennen konkrete GB-Angaben für eine Region dieser Größe. Was recherchierbar war:

- 📘 MOTIS-README wörtlich: *"MOTIS is optimized for **high performance** with **low memory usage**"*, *"Loading one year of timetable doesn't take much more RAM than loading one month"* — keine absoluten Zahlen.
- ⚠️ Aus dem Transitous-eigenen (älteren, ggf. nicht mehr voll zutreffenden) Betriebs-Wiki: ein **Import von 6 Ländern** (deutlich größer als Sachsen) lief innerhalb weniger Stunden mit **≤ 64 GB RAM** durch; ein Versuch, **ganz Europa** auf einmal zu importieren, scheiterte selbst mit 100 GB RAM am Adress-Indexierungsschritt. Diese Notizen stammen aber erkennbar aus einer älteren MOTIS-Architektur-Generation (vor dem heutigen `nigiri`-Routing-Kern) und sind nicht 1:1 auf die aktuelle v2/v6-API übertragbar — nur als grobe Größenordnung zu verstehen.
- **Eigene Einschätzung (nicht verifiziert):** Sachsen hat ca. 3–4 % der Fläche/Bevölkerung Deutschlands. Ein `sachsen-latest.osm.pbf` dürfte im Bereich von einigen hundert MB liegen (zum Vergleich: `germany-latest.osm.pbf` ist mehrere GB groß), der deutschlandweite DELFI-GTFS-Datensatz ist unabhängig vom OSM-Ausschnitt komplett zu laden und dürfte je nach Kompression im Bereich von ~1–2 GB liegen. Für einen Import mit Sachsen-OSM + Deutschland-GTFS ist ein Rechner mit **8–16 GB RAM** und **~20–30 GB freiem Diskspeicher** (Rohdaten + verarbeitete `data/`-Verzeichnisstruktur + evtl. Shape-Cache) als realistischer Startwert zu erwarten; die Import-Dauer dürfte im Bereich **Minuten bis niedrige einstellige Stunden** liegen. **Diese Zahlen sind Schätzungen und sollten vor einem produktiven Self-Hosting-Entscheid durch einen eigenen Test-Import bestätigt werden.**
- Empfehlung: Vor einem Sachsen-Self-Hosting einen echten Test-Import auf einer Testmaschine fahren und dabei `docker stats`/`time` mitschneiden, statt sich auf diese Schätzung zu verlassen.

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
11. **Geofabrik-Erreichbarkeit in dieser Recherche-Umgebung fehlgeschlagen** — die Sachsen-OSM-URL konnte hier nicht per `curl` erreicht werden (Verbindungsabbruch); das war ein Umgebungsproblem dieser Recherche-Session (Proxy), keine Aussage über die tatsächliche Verfügbarkeit des Dienstes. Vor dem produktiven Self-Hosting-Setup sollte der Download in der Zielumgebung erneut geprüft werden.

---

## 8. Quellenübersicht

- MOTIS OpenAPI-Spec, Tag `v2.10.2`: `https://raw.githubusercontent.com/motis-project/motis/refs/tags/v2.10.2/openapi.yaml` (📘, Rohdatei direkt geparst)
- MOTIS README: `https://raw.githubusercontent.com/motis-project/motis/master/README.md` (📘)
- MOTIS Setup-Doku: `https://raw.githubusercontent.com/motis-project/motis/master/docs/setup.md` (📘, Rohdatei direkt geparst)
- MOTIS/prima Docker-Compose-Beispiel: `https://raw.githubusercontent.com/motis-project/prima/master/docker-compose.yml` (📘, Rohdatei direkt geparst)
- Transitous API/Policy-Seite: `https://transitous.org/api/` (🟢 live abgerufen 29.08.2026, Text direkt aus HTML extrahiert)
- Transitous/MOTIS-Notes-Wiki (⚠️ ältere Architektur-Generation, mit Vorsicht zu lesen): `https://github.com/public-transport/transitous/wiki/MOTIS-Notes`
- Alle Live-Requests aus Abschnitt 3: direkt gegen `https://api.transitous.org` am 29.08.2026, Rohantworten lokal im Scratchpad gespeichert und mit Python nachgeprüft (u. a. Polyline-Dekodierung).
