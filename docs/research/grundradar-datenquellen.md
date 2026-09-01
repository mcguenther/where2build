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
