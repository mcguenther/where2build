# grundradar.de als Vorbild — welche Daten, woher, und was davon lohnt

Recherchestand **01.09.2026**. Alle mit ✅/❌ markierten Zeilen sind an diesem
Tag per **GET** abgefragt und die Antwort gelesen worden (kein HEAD, kein
Zitat aus einer Dokumentation). Wo nichts geprüft werden konnte, steht das
ausdrücklich als „ungeprüft" da — nicht als Vermutung.

Ausgangspunkt sind zwei Screenshots von grundradar.de und dessen
Prüfkategorien: Lärm, Starkregen, Bebauungsplan, Schutzgebiet,
Trinkwasserschutz, Radon, Luftqualität, Erdbeben, Bodenbewegung, Altbergbau,
Hochwasser, Altlasten, Fluglärm, Hangneigung — dazu Grundsteuer-Hebesatz,
Bodenrichtwert und digitale Versorgung.

## 0. Das Wichtigste zuerst

1. **Die Adressvorschläge sind fast geschenkt.** `/api/geocode` liefert heute
   schon eine Kandidatenliste mit Labels — sie hängt nur an keinem Suchfeld.
   Verifiziert: MOTIS beantwortet „Lessingweg 44, Leipzig" mit
   `type: ADDRESS`, Hausnummer aufgelöst. Für die Beschriftung im Dropdown
   („04316 Leipzig · Mölkau, Sachsen") fehlen MOTIS aber PLZ, Ort und
   Bundesland; **Photon** liefert genau diese Felder.
2. **Ein einziger Server deckt fünf grundradar-Kategorien für Sachsen ab.**
   `luis.sachsen.de/arcgis` ist ein offener ArcGIS-REST-Server mit den Ordnern
   `laerm`, `wasser`, `natur`, `boden`, `geologie`, `luft`, `altlasten`.
   REST heißt: Punktabfrage gibt JSON zurück — kein GetFeatureInfo-Gebastel.
3. **Schutzgebiete gibt es bundesweit aus einer Hand** (BfN), Bodenrichtwerte
   und Kataster dagegen bleiben Ländersache. Der Sprung „deutschlandweit"
   scheitert nicht an den Risikodaten, sondern an ALKIS und BORIS.

## 1. Verifizierte Endpunkte

### 1.1 Adresssuche

| Dienst | Endpunkt | Status |
| --- | --- | --- |
| **Photon** (komoot, OSM) | `https://photon.komoot.io/api/?q=…&lang=de&layer=house` | ✅ 200, JSON. Für „Lessingweg 44 Leipzig": `housenumber 44`, `postcode 04316`, `city Leipzig`, `district Mölkau`, `state Sachsen`, `countrycode DE`, Koordinate `12.4418386, 51.3365567`. |
| **MOTIS** (bereits im Backend) | `…/api/v1/geocode?text=…&language=de` | ✅ 200. Erster Treffer `type: ADDRESS`, `Lessingweg 44` — aber `areas[0].name` ist nur „Deutschland", also ohne PLZ/Ort für das Label. |
| BKG Geokodierungsdienst | `sg.geodatenzentrum.de/gdz_geokodierung__<key>/…` | ❌ 400 ohne Lizenzschlüssel. Kostenpflichtig/registrierungspflichtig — als Abhängigkeit für ein Suchfeld ungeeignet. |

Die Photon-Koordinate liegt rund 15 m neben dem Punkt, den grundradar im
Screenshot ausweist (51.33652, 12.44176) — dasselbe Grundstück.

**Photon ist keine Behörde.** Der Betrieb liegt bei komoot, es gibt keine
zugesicherte Verfügbarkeit; die Software ist Open Source und lässt sich
selbst betreiben. Für die Produktion gilt dasselbe Argument wie bei Overpass:
eine öffentliche Instanz trägt kein fremdes Produkt.

### 1.2 Bundesweite Fachdaten

| Thema | Dienst | Endpunkt | Status |
| --- | --- | --- | --- |
| **Schutzgebiete** | BfN Geodienste WMS | `geodienste.bfn.de/ogc/wms/schutzgebiet` | ✅ 200 (**nur mit User-Agent** — ohne UA antwortet der Dienst 403). Layer: `Naturschutzgebiete`, `Landschaftsschutzgebiete`, `Naturparke`, `Nationalparke`, `Biosphaerenreservate`, `Biosphaerenreservate_Zonierung`, `Vogelschutzgebiete`, `Fauna_Flora_Habitat_Gebiete`, `Nationale_Naturmonumente`. |
| **Luftqualität** | UBA Luftdaten-API v3 | `luftdaten.umweltbundesamt.de/api/air-data/v3/stations/json` | ✅ 200, JSON. Achtung: der oft zitierte Pfad `www.umweltbundesamt.de/api/air_data/v3/…` ist ein 301 auf diesen Host — und der Pfad heißt dort `air-data` mit Bindestrich. |
| **Verwaltungsgrenzen** | BKG VG250 WFS | `sgx.geodatenzentrum.de/wfs_vg250` | ✅ 200, WFS 2.0. Offen, ohne Schlüssel. Liefert Gemeinde/Kreis für die Hebesatz-Zuordnung. |
| **Geländehöhe / Hangneigung** | BKG DGM200 WMS | `sgx.geodatenzentrum.de/wms_dgm200` | ✅ 200, WMS 1.3.0. **200 m Rasterweite** — für die Hangneigung eines 650-m²-Grundstücks zu grob. Feinere DGM liegen bei den Ländern (Sachsen: GeoSN). |
| **Starkregen** | DWD KOSTRA-DWD-2020 | `opendata.dwd.de/climate_environment/CDC/grids_germany/return_periods/precipitation/KOSTRA/KOSTRA_DWD_2020/` | ✅ 200, offenes Verzeichnis. Rasterdaten zum Herunterladen, kein Abfragedienst — muss importiert werden. |
| **Statistik / Hebesätze** | Destatis GENESIS REST | `www-genesis.destatis.de/genesisWS/rest/2020/helloworld/whoami` | ✅ 200, JSON. Die API antwortet; Tabellenabruf (71231 Realsteuern) verlangt einen kostenlosen Account — **ungeprüft**, weil kein Account vorliegt. |

### 1.3 Sachsen — `luis.sachsen.de/arcgis`

Offener ArcGIS-REST-Server, `?f=json` liefert überall JSON.

`https://luis.sachsen.de/arcgis/rest/services?f=json` ✅ 200. Ordner:
`altlasten`, `basis`, `boden`, `energie`, `geologie`, `gewaessernetz`,
`laerm`, `landwirtschaft`, `luft`, `natur`, `wasser` (+ intern/test/Utilities).

| Thema | Dienst | Status |
| --- | --- | --- |
| **Lärm** | `laerm/laermkartierung` (Map- + FeatureServer) | ✅ Layer u. a. `Hauptverkehrsstraßen Schallpegel LDEN (24 h)` (id 4), `… Ln nachts (22-6 Uhr)` (id 5), Straßenbahn (55/56), Flughafen (36/37), `Kartierungsgebiet` (52), `Hotspotanalyse` (64). |
| **Hochwasser** | `wasser/hochwasserrisikokarte` WFS | ✅ 200, WFS 2.0 Capabilities. |
| **Trinkwasserschutz** | `wasser/wasserschutzgebiete` WMS | ✅ 200, WMS 1.3.0. |
| **Schutzgebiete** | `natur/schutzgebiete`, `natur/natura2000`, `natur/gesetz_gesch_biotope` | ✅ im Ordnerverzeichnis vorhanden (Capabilities nicht einzeln geprüft). |
| **Boden / Baugrund** | `boden/bk50`, `boden/bodenempfindlichkeiten`, `geologie/bohrungen`, `geologie/gk25` | ✅ im Ordnerverzeichnis vorhanden. `geologie/bohrungen` ist der interessanteste — Bohrprofile am Standort. |
| **Altlasten** | Ordner `altlasten` | ⚠️ existiert, listet aber **keine öffentlichen Dienste** (`services: []`). Deckt sich mit grundradars „Für dieses Bundesland liegen keine flächendeckenden Altlastendaten vor". |
| `geodienste.sachsen.de/wms_smul_*` | — | ❌ 403. Diese Namen sind **geraten und falsch**; der Kontrollabruf des dokumentierten ALKIS-WFS auf demselben Host antwortet 200. Der Fachdaten-Weg führt über `luis.sachsen.de`, nicht über `geodienste.sachsen.de`. |

**Punktabfrage live geprüft** — die Koordinate aus dem grundradar-Screenshot
(Mölkau, Flurstück 204; 51.33652, 12.44176) gegen
`laerm/laermkartierung/MapServer/identify`:

```
geometry={"x":12.44176,"y":51.33652}&geometryType=esriGeometryPoint&sr=4326
&layers=all:4,5,37,36,55,56&tolerance=3&mapExtent=12.43,51.33,12.45,51.34
&imageDisplay=600,400,96&returnGeometry=false&f=json
```

Antwort: 3 Treffer —
`Hauptverkehrsstraßen Schallpegel LDEN (24 h)` mit `CATEGORY: Lden5559` und
`Lden5054`, sowie `… Ln nachts` mit `CATEGORY: Lnight4549`. Also
**L_DEN 55–59 dB(A), L_night 45–49 dB(A), Quelle Straßenverkehr** — genau die
Aussage, die grundradar für dasselbe Flurstück als „Lärm: ROT, Straßenlärm"
zeigt. Die Kategorien kommen als 5-dB-Bänder, nicht als Einzelwert.

### 1.4 Nicht erreichbar oder ohne offene Schnittstelle

| Thema | Was geprüft wurde | Ergebnis |
| --- | --- | --- |
| **Radon** | `imis.bfs.de/cgi-public/wms_inspire_rn` | ❌ 403 (auch mit User-Agent). `imis.bfs.de/ogc/opendata/wms` läuft in einen Timeout. Das BfS-Geoportal selbst antwortet 200, gibt aber keinen Dienst-Endpunkt preis. **Kein nutzbarer Endpunkt in diesem Durchgang gefunden.** |
| **Bodenbewegung** | `services.bgr.de/wms/boden/bbd/`, `…/bodenbewegungsdienst/` | ❌ 400 (ArcGIS-Fehlerseite). Beide Pfade geraten. `services.bgr.de/` selbst ✅ 200 mit einer Kurzlink-Übersicht — dort müsste der richtige Pfad stehen, **ungeprüft**. |
| **Schienenlärm bundesweit** | `geoportal.eba.bund.de/arcgis/…` | ❌ Verbindung über den Proxy abgebrochen (502). Nicht als „existiert nicht" zu lesen. |
| **Mobilfunk / Breitband** | `gigabitgrundbuch.bund.de` ✅ 200 (Portal), `/api/v1/breitbandatlas` ❌ 404; `breitband-monitor.de` ❌ TLS-Fehler | **Kein offener Endpunkt gefunden.** Das Gigabit-Grundbuch ist eine Portalanwendung; die von grundradar gezeigten Prozentwerte (Gigabit 89 %, Glasfaser 32 %) stammen der Größenordnung nach aus dem Breitbandatlas auf Gemeinde- oder Rasterebene. Woher genau, ist offen. |
| **Bebauungspläne** | XLeitstelle ✅ 200 (Portal) | XPlanung ist ein **Datenstandard**, kein bundesweiter Dienst. Pläne liegen bei den Gemeinden; Leipzig veröffentlicht eigene Dienste. Kein einheitlicher Zugang. |
| **Umgebungslärm bundesweit** | Recherche | Ländersache (BImSchG Teil 6, EU 2002/49/EG). Bundesweit einheitlich existieren nur die Meldungen an die EEA und die Schienenwege des EBA. Für ein Sachsen-Produkt irrelevant, für den Deutschlandsprung der teuerste Posten. |
| **Erdbeben, Altbergbau, Fluglärm** | — | In diesem Durchgang **nicht geprüft**. Erdbebenzonen nach DIN EN 1998-1/NA sind eine statische Karte; Altbergbau ist in Sachsen beim Oberbergamt; Fluglärmschutzbereiche sind Rechtsverordnungen je Flughafen. |

## 2. Was grundradar zeigt, das wir nicht haben

| grundradar | wir heute | Aufwand | Quelle steht? |
| --- | --- | --- | --- |
| Adressvorschläge beim Tippen | nur URL / Flurstück / Einfügen | **klein** — Endpunkt existiert | ✅ Photon + MOTIS |
| Karte groß, Infos als Box links | Karte als Beiwerk | **mittel** (Layout) | — |
| Lärm (Tag/Nacht) | — | klein | ✅ LUIS `laerm` |
| Trinkwasserschutz | — | klein | ✅ LUIS `wasser` |
| Schutzgebiet + Entfernung | — | klein | ✅ BfN bundesweit |
| Hochwasser HQ100 | — | mittel | ✅ LUIS WFS (grundradar hat hier **keine** Daten für Sachsen — ein Feld, in dem wir besser sein könnten) |
| Luftqualität nächste Station | — | klein | ✅ UBA-API |
| Starkregen (KOSTRA) | — | mittel (Import) | ✅ DWD-Raster |
| Baugrund / Bohrungen | — | mittel | ✅ LUIS `geologie/bohrungen` — **hat grundradar nicht** |
| Grundsteuer-Hebesatz | — | mittel | ⚠️ GENESIS, Account nötig |
| Radon | — | offen | ❌ kein Endpunkt gefunden |
| Altlasten | — | offen | ❌ keine Daten für Sachsen |
| Mobilfunk / Gigabit | — | offen | ❌ kein offener Endpunkt |
| Score-Ring „78/100" | — | klein | — (siehe unten) |

## 3. Zwei Dinge, die wir nicht übernehmen sollten

**Der GrundScore.** grundradar rechnet 14 Kategorien zu einer Zahl zusammen
und schreibt in denselben Tooltip „Datenabdeckung 58 % (niedrig)". Ein Wert,
der zu 42 % aus fehlenden Daten besteht, ist keine Aussage über das
Grundstück. Das ist genau der Fall, den `CLAUDE.md` unter „Never show example
data" verbietet: ein abgeleiteter Wert mit fehlender Eingabe bleibt `—`. Wenn
eine Zusammenfassung sein muss, dann als Ampelliste mit Zählern
(„2 zu klären, 5 ohne Befund, 4 ungeprüft") — die grundradar daneben ohnehin
schon zeigt und die ehrlicher ist als der Ring.

**Rohwerte durchreichen.** Im Screenshot steht „Klasse
between_20_and_44" — ein Feldwert aus der Quelle, unübersetzt in der
Oberfläche. Deutschsprachige UI heißt auch: Klassenschlüssel werden
übersetzt, oder das Feld bleibt leer.

## 4. Fallstricke aus diesem Durchgang

- **Der BfN-WMS antwortet 403 ohne User-Agent** und 200 mit. Ein leerer UA ist
  hier kein Netzwerkproblem, sondern eine Filterregel.
- **Die UBA-Luftdaten-API liegt nicht auf `umweltbundesamt.de`.** Der dort
  dokumentierte Pfad ist ein 301 auf `luftdaten.umweltbundesamt.de`, und der
  Pfad heißt `air-data`, nicht `air_data`. Wer dem 301 nicht folgt, hält die
  API für tot.
- **`geodienste.sachsen.de` und `luis.sachsen.de` sind zwei Welten.** Auf dem
  ersten liegen Kataster und Karten (ALKIS-WFS, DOP, WebAtlas), auf dem
  zweiten die Umweltfachdaten. Geratene `wms_smul_*`-Namen auf dem ersten
  Host geben 403 — was wie eine Sperre aussieht, aber ein falscher Pfad ist.
  Der Kontrollabruf des bekannten ALKIS-WFS auf demselben Host gibt 200.
- **ArcGIS `identify` braucht `mapExtent` und `imageDisplay`,** obwohl die
  Abfrage geometrisch nichts damit zu tun hat: die Toleranz wird in Pixeln
  gerechnet, und ohne Bildgröße gibt es keine Pixel. Fehlt eines von beiden,
  kommen null Treffer statt einer Fehlermeldung.
- **Lärmpegel kommen als 5-dB-Band,** nicht als Zahl (`Lden5559`). Ein Wert
  wie „57 dB" wäre erfunden; korrekt ist „55–59 dB(A)".

---

# Nachtrag 02.09.2026 — Adresssuche lokal, und wie der Lärmwert richtig entsteht

Zwei Rückfragen, beide mit Abrufen beantwortet. Der zweite Teil **korrigiert
eine Zahl aus dem ersten Durchgang**.

## 5. Adresssuche ohne fremden Dienst

### 5.1 Photon selbst betreiben — geht, lohnt für Sachsen aber nicht

| Prüfung | Ergebnis |
| --- | --- |
| Vorgebauter Deutschland-Index | ✅ `download1.graphhopper.com/public/extracts/by-country-code/de/photon-db-de-250720.tar.bz2` |
| Größe | **9,20 GB** (9 881 965 371 Bytes, per Range-Request ermittelt, kein Volldownload) |
| Datenstand | `Last-Modified: 21.07.2025` — zum Prüfzeitpunkt **über 13 Monate alt** |
| `photon-db-de-latest.tar.bz2` | ❌ **404** — der „latest"-Zeiger ist tot, obwohl das Verzeichnis ihn mit 81 Bytes listet. Wer darauf verlinkt, baut auf einen Link, der nicht auflöst. |

Dazu kommt eine OpenSearch-/Elasticsearch-Instanz als Laufzeitabhängigkeit.
Für ein Sachsen-Produkt ist das unverhältnismäßig: 9,2 GB und ein Suchcluster,
um 990 000 sächsische Adressen zu finden.

### 5.2 Die amtliche Alternative — 49 MB, und sie ist die bessere Quelle

**Hauskoordinaten Sachsen**, bereits in `geodaten-sachsen.md` dokumentiert,
hier auf Eignung für Tippvorschläge geprüft:

- Download ✅ **51 236 896 Bytes (48,9 MB)** in 3,9 s, entpackt
  `hk_sn_adressen_20260702.txt`, **206 MB**, **990 090 Datensätze**.
- Datenstand **02.07.2026**, quartalsweise — also aktueller als der
  Photon-Deutschlandindex.
- Die Felder decken das Dropdown vollständig ab: `str`, `hnr`, `adz`,
  `postplz`, `postonm`, `postott` (Ortsteil), `ostwert`/`nordwert` in
  EPSG:25833.

Die Adresse aus dem grundradar-Screenshot steht wörtlich drin:

```
…;140;Stadt Leipzig;0260;Mölkau;02642;Lessingweg;44;;33;321807.526;5690358.877;04316;Leipzig;;Mölkau
```

**Lagevergleich** (nach EPSG:4326 umgerechnet):

| Quelle | lat | lon | Abstand zur amtlichen Koordinate |
| --- | --- | --- | --- |
| Hauskoordinaten (amtlich) | 51.33655 | 12.44181 | — |
| Photon (OSM) | 51.33656 | 12.44184 | **2,1 m** |
| grundradar (Screenshot) | 51.33652 | 12.44176 | 4,9 m |

Die amtliche Quelle ist also nicht schlechter, sondern nur örtlich begrenzt.

**Tauglichkeit als Typeahead gemessen** — CSV nach SQLite, ein Index auf einer
zusammengesetzten Suchspalte, `LIKE 'präfix%'`:

| | |
| --- | --- |
| Aufbau | 15,4 s, 143 MB SQLite-Datei |
| „Bautzner" | **11,7 ms** |
| „Lessingw" | **43,9 ms** |
| „Prager Str" | **53,6 ms** |
| „Lessingweg 44" | **75,0 ms** |

Naiv, ohne FTS5 und ohne Optimierung. Für ein entprelltes Suchfeld
(150–200 ms) reicht das mit Abstand; mit FTS5-Präfixindex ginge es deutlich
schneller. **Kein externer Dienst im Anfragepfad, keine Rate-Limit-Frage,
keine fremde Verfügbarkeit.**

### 5.3 Empfehlung

Hauskoordinaten als Primärquelle für Sachsen, `/api/geocode` (MOTIS) als
Rückfall für alles, was keine sächsische Hausadresse ist — Ortsteile,
Flurstückslagen, Ziele außerhalb. Photon nur, falls das Produkt Sachsen
verlässt; dann als eigene Instanz, nicht gegen komoots Server.

## 6. Lärm — Anzeige, Abfrage und eine Korrektur

### 6.1 Korrektur des Mölkau-Werts

Im ersten Durchgang stand hier **„L_DEN 55–59 dB(A)"** für Flurstück 204,
ermittelt per ArcGIS `identify` mit `tolerance=3`. Das war falsch begründet
und in der Zahl irreführend.

`identify` rechnet die Toleranz in **Bildpunkten**. Bei dem gewählten
`mapExtent`/`imageDisplay` entsprachen 3 px rund **7 m** — der Treffer
`Lden5559` kam also von einem Nachbarpolygon, nicht vom Punkt. Die exakte
Punkt-in-Polygon-Abfrage über `…/4/query` mit
`spatialRel=esriSpatialRelIntersects` sagt:

| Abfragegeometrie | L_DEN | L_night |
| --- | --- | --- |
| **Punkt** (Adresskoordinate, liegt auf dem Gebäude) | `Lden5054` → **50–54 dB(A)** | `Lnight4549` → 45–49 dB(A) |
| **Flurstück 204** (650 m², Umring aus ALKIS) | `Lden5054` + `Lden5559` → **50–59 dB(A)** | `Lnight4549` → 45–49 dB(A) |

Das Grundstück liegt tatsächlich in zwei Bändern — der alte Wert war zufällig
in der Nähe der richtigen Antwort, aber aus dem falschen Grund und bei anderem
Zoom anders ausgefallen.

**Daraus folgt die Methode:** nicht den Punkt abfragen, sondern **den
Flurstücksumring**, den wir aus ALKIS ohnehin schon haben. Das ist fachlich
richtig (ein Grundstück hat keine Punktlage), reproduzierbar (kein
Maßstabsparameter) und liefert eine Spanne statt einer Scheingenauigkeit.

Verifiziert: ALKIS-BBOX-Abfrage am Screenshot-Punkt liefert 20 Flurstücke,
darunter `Nr 204 | 650 m² | Mölkau | Lessingweg 44` — identisch zu grundradars
Kopfzeile. Der Umring hat 6 Stützpunkte und geht unverändert als
`esriGeometryPolygon` in die Lärmabfrage.

### 6.2 Die vollständige Bänderskala

| Layer | Kategorien |
| --- | --- |
| Straße L_DEN (4) | `Lden4549`, `5054`, `5559`, `6064`, `6569`, `7074`, `LdenAb75` |
| Straße L_night (5) | `Lnight4549`, `5054`, `5559`, `6064`, `6569`, `LnightAb70` |
| Straßenbahn L_DEN (55) | ab `Lden5054` |
| Flughafen L_DEN (37) | ab `Lden5054` |

Unterste kartierte Stufe beim Straßenlärm ist **45–49 dB(A)**. „Kein Treffer,
aber im kartierten Gebiet" heißt also belegbar „unter 45 dB(A)".

### 6.3 Abdeckung — der eigentliche Fallstrick

Anzahl Straßenlärm-Polygone im Umkreis von 300 m:

| Ort | Straßenlärm | Bewertung |
| --- | --- | --- |
| Leipzig Zentrum | 109 | kartiert |
| Dresden Altmarkt | 94 | kartiert |
| Leipzig Mölkau | 68 | kartiert |
| Wurzen (16 000 Ew.) | 38 | kartiert |
| Chemnitz Zentrum | 9 | kartiert |
| **Geithain (6 000 Ew.)** | **0** | **nicht kartiert** |
| **Rechenberg-Bienenmühle (Dorf)** | **0** | **nicht kartiert** |

Die Umgebungslärmkartierung ist nach BImSchG Teil 6 auf Ballungsräume und
Hauptverkehrswege begrenzt. In Geithain gibt es **keine Daten** — und „keine
Daten" darf niemals als „leise" oder grün erscheinen.

**Regel, die daraus folgt** (zwei Abfragen statt einer):

1. Treffer auf dem Flurstück → Spanne ausgeben.
2. Kein Treffer, aber Polygone **innerhalb von 2 km** → „unter 45 dB(A)",
   belegbar leise.
3. Kein Treffer und nichts in 2 km → **„für diesen Ort nicht kartiert"**.
   Kein Wert, keine Farbe, keine Ampel.

⚠️ `Kartierungsgebiet` (Layer 52) taugt dafür **nicht**: es ist eine
`esriGeometryPolyline` mit 4 637 Objekten — das kartierte Straßennetz mit
Verkehrsmengen (`DTV_LK2022`), keine Flächenmaske. Eine Punktabfrage darauf
trifft nie.

### 6.4 Den Layer anzeigen — geht, mit zwei Fallstricken

Der Dienst meldet `supportedExtensions: FeatureServer, KmlServer, WFSServer,
WMSServer`, `maxRecordCount: 5000`, native SR **25833**.

| Prüfung | Ergebnis |
| --- | --- |
| WMS `GetCapabilities` | ✅ 200 |
| **CORS** | ✅ `Access-Control-Allow-Origin` spiegelt den Origin (`http://localhost:5173` getestet) — der Browser darf direkt zugreifen |
| GetFeatureInfo-Formate | u. a. `application/geo+json`, `text/plain`, `text/html` |
| **EPSG:3857** | ❌ **nicht unterstützt** (nur 4326, 25833 und exotische) |
| ArcGIS `export` mit `bboxSR=3857&imageSR=3857` | ✅ 200, `image/png`, 512×512, CORS-Header gesetzt — **der Server reprojiziert selbst** |

**Fallstrick 1:** MapLibres Raster-Quelle fordert Kacheln mit
`{bbox-epsg-3857}` an. Der WMS kann 3857 nicht — eine gewöhnliche
WMS-Rasterquelle scheitert also. Der Weg ist der **ArcGIS-`export`-Endpunkt**,
der serverseitig nach 3857 rechnet.

**Fallstrick 2:** Layer 4 hat `minScale: 50000` — oberhalb 1:50 000 liefert der
Dienst ein **leeres Bild ohne Fehlermeldung**. Die Umschaltfläche muss also
entweder erst ab der passenden Zoomstufe aktiv sein oder sagen, dass der Layer
erst näher dran erscheint.

### 6.5 Gibt es bessere Wege als die Lärmkarte?

Geprüft und verworfen:

- **Aus Verkehrsmengen rechnen.** `DTV_LK2022` liegt an Layer 52 vor, und
  RLS-19/DIN 18005 wären der Rechenweg. Das hieße, eine Zahl zu erfinden, wo
  keine gemessene steht — und es ersetzt keine Kartierung, weil Bebauung und
  Abschirmung fehlen. Nein.
- **Abstand zur nächsten Hauptstraße als Ersatzmaß.** Wäre eine Korrelation,
  keine Aussage. Nein.
- **Bundesweite Alternative.** Existiert nicht: die Kartierung ist Ländersache;
  bundesweit einheitlich gibt es nur die EEA-Meldungen und das Schienennetz des
  EBA (dessen Geoportal über den Proxy 502 gab — ungeprüft).

Die amtliche Kartierung ist die richtige und einzige belastbare Quelle. Was
sich verbessern lässt, ist **wie** wir sie abfragen — Flurstück statt Punkt —
und **wie ehrlich** wir über ihre Lücken sind.

---

# Nachtrag 02.09.2026 (2) — die drei Lücken, noch einmal angefasst

## 7. Radon: doch vorhanden

`luft/radonvorsorgegebiete` auf `luis.sachsen.de`. Beim ersten Durchgang
übersehen, weil ich den `luft`-Ordner nur bis zum vierzehnten Eintrag gelistet
und danach nach „strahl" gesucht hatte. **Erst die vollständige Inventur aller
173 Dienste hat ihn gefunden** — Lehre: Ordner ganz auslesen, nicht das
Stichwort raten.

| Prüfung | Ergebnis |
| --- | --- |
| Objekte | ✅ 107 Gemeinden, nach § 121 StrlSchG ausgewiesen |
| Mölkau 204 | „nein" — Leipzig ist kein Vorsorgegebiet |
| Kontrollpunkt Johanngeorgenstadt | „ja" (`NAME: Stadt Johanngeorgenstadt`) |
| Kontrollpunkt Schneeberg | „ja" (`NAME: Stadt Schneeberg`) |

Ohne die zwei Kontrollpunkte wäre „0 Treffer" nicht von „Layer leer" zu
unterscheiden gewesen. Das ist zugleich **besser als grundradar**: dort steht
eine modellierte Potenzialklasse (`between_20_and_44`), hier die
rechtsverbindliche Ausweisung.

## 8. Hangneigung: eine Kulisse, kein Neigungswert

`landwirtschaft/hangneigung_ausbringung`, Layer `HANGNEIGUNG_20PROZENT`,
224 631 Objekte. Flurstück 204 liegt nicht darin. Das ist eine
**Ja/Nein-Kulisse aus dem Düngerecht**, kein Geländemodell — „unter 20 %" ist
alles, was sie hergibt. Ein echter Neigungswert bräuchte das Landes-DGM.

## 9. Altlasten: belastbares Nein

Über alle 173 Fachdienste gesucht (`altlast`, `salka`, `schadstoff`,
`kontamin`, `verdacht`): **kein Treffer**. Der Ordner `altlasten` existiert und
listet `services: []`. Das SALKA ist nicht öffentlich. Auskunft gibt der
Landkreis.

## 10. Mobilfunk: Umgebungsgrenze, kein Befund

`mobilfunk-monitoring.de` → 502 beim CONNECT durch den Proxy,
`breitband-monitor.de` → TLS-Fehler (`unrecognized name`),
`gigabitgrundbuch.bund.de` → Portal 200, aber keine Datenschnittstelle.
**Das ist eine Grenze unserer Umgebung, kein Beleg, dass es nichts gibt.**

## 11. minScale ist rechenbar — und damit steuerbar

ArcGIS bildet den Maßstab als
`(bbox_breite_m / bild_breite_px) * dpi / 0,0254`. Bei 10 km Fenster und
512 px:

| dpi | Maßstab | Antwort |
| --- | --- | --- |
| 60 | 1:46 137 | zeichnet (130 168 B) |
| 64 | 1:49 213 | zeichnet |
| **65** | **1:49 982** | **zeichnet** |
| **66** | **1:50 750** | **leer (2 231 B)** |
| 96 | 1:73 819 | leer |

Die Schwelle liegt exakt bei `minScale`. Also:
`dpi = min(96, minScale * 0,0254 * breite_px / bbox_breite_m)` — dann
verschwindet der Layer nie stumm. `size` wirkt gleichwertig (2048 px zeichnet
bei dpi 96), kostet aber die vierfache Datenmenge.

## 12. Werte für Flurstück 204 — alle abgerufen

| Prüfung | Wert | Quelle |
| --- | --- | --- |
| Bodenrichtwert | **280 €/m²**, Stichtag 01.01.2026, Baureifes Land, Wohnbaufläche, EFH, Richtwertgrundstück **800 m²**, Zone 71300250 | BORIS Sachsen |
| Lärm | L_DEN **50–59 dB(A)** (Flurstück), 50–54 am Punkt; L_night 45–49; keine Straßenbahn, kein Fluglärm | LfULG |
| Trinkwasserschutz | kein Gebiet (4 Layer je 0) | LfULG |
| Schutzgebiet | LSG „Östliche Rietzschke – Stünz" zwischen **350 und 400 m** (grundradar: „etwa 380 m" — unabhängig bestätigt); zweites LSG ≤ 1 km; kein NSG | LfULG |
| Hochwasser | nicht betroffen (Gefährdung + Risikogebiete je 0) | LfULG |
| Radon | kein Vorsorgegebiet | LfULG |
| Hangneigung | nicht über 20 % | LfULG |
| Boden | „Hortisol über erodierter Parabraunerde aus gemischtem Schluff über tiefem periglaziärem Kies führendem Lehm" | BK50 |
| Bohrungen | 91 im Umkreis 500 m, 14 im Umkreis 300 m; nächste **82 m**, Endteufe 5,0 m; eine von 2019 in 147 m mit 21 m | Aufschlussdatenbank |
| Luft | Leipzig-Mitte, **4,6 km**: NO₂ 13,1 · PM10 11,8 · PM2,5 6,0 · O₃ 55,5 µg/m³ | UBA |

**Fallstrick UBA:** die drei nächstgelegenen Stationen (1,9–3,0 km, Präfixe
`z_GUAN` und `zDDR_`) liefern **keine Messwerte**, obwohl ihr Feld
„active to" leer ist. Erst Leipzig-Mitte in 4,6 km antwortet — dieselbe
Station und Entfernung, die grundradar nennt. Also: die nächste Station
wählen, **die tatsächlich Werte liefert**, nicht die nächste auf der Karte.

## 13. Der Bodenrichtwert kann mehr, als grundradar zeigt

Die GetFeatureInfo-Antwort führt `FLAECHE_TEXT = 'f800'` (das fiktive
Richtwertgrundstück misst 800 m²) und verlinkt die **Umrechnungstabelle** des
Gutachterausschusses. Unser Flurstück hat 650 m². grundradar zeigt nur die
280 €/m²; der Umrechnungsschritt auf die tatsächliche Fläche ist ein Feld, in
dem wir sachlich weiter sind.

---

# Nachtrag 02.09.2026 (3) — Einordnung statt Rohwert

## 14. Lärm: was 55–59 dB(A) für den Alltag heißt

Die Schwellen sind nicht erfunden, sondern aus dem **UBA-Positionspapier zu
den WHO-Leitlinien für Umgebungslärm (2019)** gelesen (PDF abgerufen und im
Text durchsucht):

| Quelle | L_DEN | L_night |
| --- | --- | --- |
| Straßenverkehr | **53 dB(A)** | **45 dB(A)** |
| Schienenverkehr | 54 dB(A) | 44 dB(A) |
| Luftverkehr | 45 dB(A) | 40 dB(A) |

Dazu im selben Papier: **ab 65 dB(A) L_DEN** steigt das
Herz-Kreislauf-Risiko nachweislich.

**Warum kein „so laut wie ein Staubsauger".** L_DEN ist ein über 24 Stunden
gemittelter Beurteilungspegel mit Zuschlägen für Abend und Nacht — kein
Geräusch, neben dem man stehen kann. Ein Gegenstandsvergleich wäre schlicht
falsch. Ehrlich sagen lässt sich, **was der Pegel kostet**: ob der Verkehr ein
Gespräch im Garten stört, ob ein Fenster nachts offen bleiben kann. Die
Stufen in `findings.js` sind deshalb so formuliert, und die Einordnung nennt
ihre Quelle mit.

Für das Grundstück maßgeblich ist das **lautere Ende der Spanne**: ein
Flurstück, das irgendwo 59 dB(A) erreicht, wird nicht von seiner leisen Ecke
beschrieben.

## 15. Baugrund: die Bodenkarte übersetzen

Der Satz aus der BK50 — „Hortisol ueber erodierter Parabraunerde aus
gemischtem Schluff ueber tiefem periglaziaerem Kies fuehrendem Lehm" — ist
korrekt und für einen Käufer wertlos. Die praktische Aussage steckt in den
**Korngrößen**, und die stehen dort im Klartext. Klassifiziert wird deshalb
aus dem deutschen Text, nicht aus dem KA5-Code daneben:

| Wort | Lesart |
| --- | --- |
| Ton, Lehm, Schluff | **bindig** — hält Wasser, gibt es langsam ab |
| Sand, Kies | **rollig** — Wasser läuft rasch ab |
| beides | **gemischt** |

Dazu kommt aus `boden/bodenkennwerte` die **Luftkapazität als Stufe**, deren
Klassengrenzen aus der Legende des Dienstes stammen (`/legend?f=json`, live
gelesen):

`LK I < 2` · `LK II 2–5` · `LK III 5–13` · `LK IV 13–26` · `LK V ab 26 Vol.-%`

Flurstück 204 hat **LK IV (hoch)** bei gemischtem Boden. Daraus wird kein
Versickerungsversprechen, sondern: *„Ob Regenwasser vor Ort versickern kann,
ist damit offen und muss geprüft werden."*

**Was nicht gesagt wird:** irgendetwas zur Tragfähigkeit. Jede Ausgabe endet
mit „Die Bodenkarte 1:50.000 ersetzt keine Baugrunduntersuchung."

## 16. Luftbild als Ebene

| Prüfung | Ergebnis |
| --- | --- |
| `geodienste.sachsen.de/wms_geosn_dop-rgb/guest` | ✅ 200, WMS 1.3.0 |
| Layer | `sn_dop_020` (20 cm Bodenauflösung) |
| CRS | ✅ **EPSG:3857**, 25833 und 4326 — anders als der Lärm-WMS |
| CORS | ✅ Origin wird gespiegelt |
| GetMap 2000×2000 px über 420 m | ✅ 1,08 MB JPEG |

In der Anwendung also eine gewöhnliche MapLibre-Rasterquelle. **Im Mockup
nicht** — die Artifact-CSP blockt fremde Bilder, deshalb liegt dort ein
einmal abgerufener Ausschnitt als `data:`-URI (Qualität 60, 501 kB).

Zwei Darstellungsregeln, die sich aus dem Bild ergeben: über dem Luftbild
werden die **Nutzungsflächen ausgeblendet** und die **Gebäude nur als Umriss**
gezeichnet, sonst verdeckt das Kataster genau das, was man sehen wollte. Und
der Lärmschleier geht auf halbe Deckkraft, sonst verschwindet das Foto.

## 17. Ein Prozessfehler, dreimal derselbe

Drei Korrekturen gingen verloren, weil ich sie in der **zusammengesetzten**
`standort-mockup.html` gemacht hatte und danach aus den Bausteinen neu
gebaut habe: die Reihenfolge der Media Query, die Höhe des
Maßstabsbalkens und die ganze Straßennamen-Logik.

Der Mockup wird jetzt aus `mockup/build/` mit `python3 mockup/build/bauen.py`
erzeugt, und die 832-kB-Ausgabe wird nicht mehr von Hand angefasst. Bei einer
Datei mit einem base64-Luftbild darin ist das keine Stilfrage.

---

# Nachtrag 05.09.2026 — beim Einbau gemessen

Die Prüfungen aus dem Vergleichsblatt sind gebaut (`POST /api/site-checks`,
`frontend/src/views/LocationView.vue`). Was dabei an Abrufen dazugekommen ist,
steht hier. Alle Werte per **GET/POST** an diesem Tag geholt, mit dem echten
Umring von Flurstück 204 aus dem ALKIS-WFS.

## 18. Die Ebenen, die tatsächlich abgefragt werden

| Prüfung | Dienst · Layer | Antwort für Mölkau 204 |
| --- | --- | --- |
| Lärm | `laerm/laermkartierung` 4 · 5 (Straße), 55 · 56 (Straßenbahn), 37 · 36 (Flughafen) | `Lden5559` + `Lden5054`, `Lnight4549`, Bahn und Flug je 0 |
| Trinkwasserschutz | `wasser/wasserschutzgebiete` 0–3 | 0 |
| Schutzgebiet | `natur/schutzgebiete` 0–5 | 0 am Flurstück, LSG „Östliche Rietzschke - Stünz" im Band 300–400 m, ein weiteres ≤ 1 km |
| Hochwasser | `wasser/hochwassergefaehrdung` 6–10 (HQ20/25 bis Extremhochwasser) | 0 |
| Radon | `luft/radonvorsorgegebiete` 0 | 0 |
| Hangneigung | `landwirtschaft/hangneigung_ausbringung` 0 | 0 |
| Baugrund | `boden/bk50` 0, `boden/bodenkennwerte` 5, `geologie/bohrungen` 0 | BK50-Text wie in § 15, `LK_STUFE = LK_IV`, 96 Bohrungen in 500 m, 16 in 300 m |

**`wasser/hochwasserrisikokarte` ist nicht der richtige Dienst.** Seine Layer
sind Risikokarten-Objekte (betroffene Einwohner je Gemeinde, Kulturgüter,
Wirtschaftstätigkeiten), und `wasser/hochwasserrisikogebiete` Layer 0 ist eine
**Polylinie** von 4 637 Gewässern — dieselbe Falle wie `Kartierungsgebiet` beim
Lärm: eine Flächenabfrage trifft sie nie. Die Überschwemmungsflächen liegen in
`wasser/hochwassergefaehrdung` 6–10. `wasser/hochwassergefahrenkarte` (ohne
„-gefaehrdung") antwortet `Token Required`.

## 19. Kontrollpunkte — ohne die ist „0 Treffer" keine Aussage

Für jede Ja/Nein-Ebene ein Ort, an dem sie **ja** sagt. Sonst ist eine leere
Antwort nicht von einer leeren Ebene zu unterscheiden.

| Ebene | Mölkau 204 | Kontrollpunkt |
| --- | --- | --- |
| Hochwasser HQ100 | 0 | Grimma an der Mulde: **1** — `NAME: Vereinigte Mulde` |
| Extremhochwasser | 0 | Grimma: **1** |
| Radonvorsorgegebiet | 0 | Johanngeorgenstadt: **1** — `Stadt Johanngeorgenstadt` |
| Trinkwasserschutz | 0 | Dresden Elbwiese: **1** — `WSG WW Albertstadt/Saloppe` |

## 20. Die Bänderskala und ihre Legende widersprechen sich

`returnDistinctValues=true` auf Layer 4 gibt **sieben** Kategorien, `Lden4549`
darunter. Der Renderer desselben Layers (`MapServer/4?f=json` →
`drawingInfo.renderer.uniqueValueInfos`) führt aber nur **sechs**, ab
`Lden5054`. Die Karte zeichnet also nichts zwischen 45 und 49 dB(A), obwohl der
Dienst dort gemessen hat.

Daraus folgt für die Oberfläche: der Prüftext liest die **Daten** (unterste
Stufe 45 dB(A), also heißt „im kartierten Gebiet und in keinem Band" belegbar
*unter 45*), die Legende zeigt die **gezeichneten** Bänder ab 50 — und sagt
dazu, dass 45–49 keine Farbe hat. Die sechs Farben stehen im Renderer und sind
von dort übernommen, nicht gewählt:
`Lden5054 rgb(184,214,209)`, `5559 rgb(226,242,191)`, `6064 rgb(243,198,131)`,
`6569 rgb(205,70,62)`, `7074 rgb(117,8,92)`, `Ab75 rgb(67,10,74)`.

## 21. Der dpi-Deckel funktioniert bis hinunter zu Zoom 10

§ 11 rechnet die Schwelle aus; hier ist sie an echten XYZ-Kacheln (256 px)
über Mölkau geprüft. `dpi = min(96, floor(minScale · 0,0254 · px / bbox_m))`:

| Zoom | Kachelbreite | dpi | Maßstab | Antwort |
| --- | --- | --- | --- | --- |
| 10 | 39 136 m | 8 | 1:48 149 | 59 347 B — zeichnet |
| 12 | 9 784 m | 33 | 1:49 654 | 60 947 B |
| 13 | 4 892 m | 66 | 1:49 654 | 32 816 B |
| 14 | 2 446 m | 96 | 1:36 112 | 17 264 B |
| 16 | 611 m | 96 | 1:9 028 | 4 013 B |
| 18 | 153 m | 96 | 1:2 257 | 1 945 B |

Der Layer verschwindet damit **auf keiner Zoomstufe** stumm — die im
Entscheidungsblatt erwogene Mindestzoomstufe für die Umschaltfläche ist nicht
nötig. Abgerundet, nicht gerundet: die Schwelle ist ausschließend (dpi 65
zeichnet, 66 nicht, bei 10 km über 512 px).

## 22. Die UBA-Stationsfalle, noch einmal bestätigt

Stundenwerte über zwei Tage, Komponente NO₂ (`component=5`, `scope=2`):

| Station | Entfernung | Antwort |
| --- | --- | --- |
| `z_GUAN Leipzig Eisenbahnstraße` (1690) | 2,6 km | **keine Daten** (`data` fehlt) |
| `zDDR_Leipzig-Stadt` (10427) | 3,2 km | **keine Daten** |
| `Leipzig-Mitte` (1613) | 4,6 km | **89 Stundenwerte** |

Das Feld „active to" ist bei allen dreien leer. Die Auswahl muss also über die
tatsächliche Antwort laufen, nicht über die Karte — und die Ausgabe sagt, wie
viele nähere Stationen übersprungen wurden, sonst sieht „4,6 km" nach
Nachlässigkeit aus.

## 23. Der Bodenrichtwert trägt das Richtwertgrundstück mit

Die GetFeatureInfo-Antwort für Mölkau 204 führt neben `BODENRICHTWERT_TEXT =
'280'` auch `FLAECHE_TEXT = 'f800'` und `UMRECHNUNGSTABELLEN` (ohne Schema,
also `https://` davor). Beides ist jetzt in `LandValue` und steht in der
Oberfläche: der Wert gilt für ein gedachtes Grundstück von 800 m², und das
Produkt aus Wert und tatsächlicher Fläche ist deshalb nicht der Bodenwert.

## 24. Der Abstand ist ein Band, kein Wert

Der ArcGIS-`query` beantwortet „liegt etwas innerhalb von r?", nicht „wie weit
ist es?". Die Entfernung zum nächsten Schutzgebiet entsteht deshalb aus einer
Leitersuche (100 · 200 · 300 · 400 · 500 · 750 · 1 000 m), binär durchsucht —
drei Abfragen statt sieben — und wird als Spanne ausgegeben. Für Mölkau 204:
bei 300 m null Treffer, bei 400 m einer, also **300–400 m**. Eine Einzelzahl
daraus wäre erfunden.
