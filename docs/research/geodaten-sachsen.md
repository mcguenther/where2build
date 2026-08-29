# Amtliche Geodatendienste Sachsen — Recherche für "Grundstücks-Check Sachsen"

**Stand der Recherche: 29.08.2026** (alle mit ✅ markierten Ergebnisse wurden in dieser Sitzung live per `curl` gegen die produktiven Endpunkte verifiziert; ⚠️ kennzeichnet Angaben, die nur aus Dokumentation/Webseiten stammen und nicht live gegengetestet wurden).

---

## 0. Zusammenfassung — Was funktioniert, was nicht (29.08.2026)

| Dienst | Status | Bemerkung |
|---|---|---|
| **ALKIS-WFS (vereinfacht)** `geodienste.sachsen.de/aaa/public_alkis/vereinf/wfs` | ✅ **Voll funktionsfähig** | GetCapabilities, DescribeFeatureType, alle 5 Stored Queries, BBOX-Filter und ad-hoc `fes:Filter` (AND-Verknüpfung Gemarkung+Zähler+Nenner) live getestet und funktionierend. **Zwei Fallstricke identifiziert** (siehe unten), die zunächst zu HTTP 400 führten, aber lösbar sind. |
| **BORIS Sachsen WMS** (Bodenrichtwerte) `landesvermessung.sachsen.de/fp/httpproxy/svcdep/wms/boris_2026` | ✅ **Funktioniert**, mit Einschränkung | GetCapabilities, GetFeatureInfo in `text/plain`, `text/html` und GML live getestet — liefert reale Bodenrichtwerte. **`INFO_FORMAT=application/json` ist KEIN GeoJSON**, sondern UTFGrid (siehe Fallstrick unten) — für den Gesamt-Layer `brw_2026` schlägt es sogar mit Fehler fehl. Kein WFS/Vektor-Download (explizit deaktiviert, live geprüft). |
| **GeoSN WMS: WebAtlas Sachsen** (Topografische Karte) `geodienste.sachsen.de/wms_geosn_webatlas-sn/guest` | ✅ Erreichbar | Layer: Vegetation, Siedlung, Gewaesser, Verkehr, Administrative_Einheiten, Beschriftung |
| **GeoSN WMS: DOP (Luftbild)** `geodienste.sachsen.de/wms_geosn_dop-rgb/guest` | ✅ Erreichbar | Layer `sn_dop_020` (20 cm Bodenauflösung) |
| **GeoSN WMS: ALKIS-Darstellung** `geodienste.sachsen.de/wms_geosn_alkis-adv/guest` | ✅ Erreichbar | Layer u. a. `adv_alkis_tatsaechliche_nutzung`, `adv_alkis_gewaesser`, `adv_alkis_vegetation`, `adv_alkis_verkehr`, `adv_alkis_siedlung`, `adv_alkis_gesetzl_festlegungen` |
| **Hauskoordinaten** (ZIP, CSV) `geocloud.landesvermessung.sachsen.de/.../hk_sn_ascii.zip` | ✅ Download funktioniert | ~48,9 MB, Datenstand 02.07.2026, quartalsweise Aktualisierung |
| **Hausumringe** (ZIP, Shapefile) `geocloud.landesvermessung.sachsen.de/.../hu_sn_shape.zip` | ✅ Download funktioniert (Struktur per Range-Request geprüft, nicht komplett heruntergeladen — 210 MB) | Datenstand 02.07.2026, 2.541.856 Gebäude, quartalsweise Aktualisierung |
| CORS auf allen o. g. Diensten | ✅ Erlaubt | `Access-Control-Allow-Origin` wird auf allen getesteten Endpunkten gesetzt (ALKIS-WFS, BORIS-WMS, WebAtlas, DOP, ALKIS-WMS) — clientseitiger Zugriff per `fetch()` aus dem Browser ist möglich, ohne eigenen Proxy-Server. |
| GeoJSON-Output beim ALKIS-WFS | ❌ **Nicht verfügbar** | Live getestet: `OUTPUTFORMAT=application/json` liefert HTTP 400. Nur GML (3.1.1/3.2.1) und Shapefile-ZIP. |

**Wichtigste zwei Fallstricke, die zu (leicht behebbaren) HTTP-400-Fehlern führen — unbedingt in der Implementierung beachten:**

1. **Stored Queries des ALKIS-WFS verlangen den Parameter `CRS` als Pflichtparameter**, auch wenn man nur einen anderen Parameter (z. B. `gemarkungsnummer` oder `kennzeichen`) übergibt. Fehlt `CRS`, liefert der Dienst keinen OGC-`ServiceExceptionReport`, sondern eine generische sachsen.de-Fehlerseite (HTML, kein maschinenlesbarer Fehlertext!) mit HTTP 400.
2. **Ad-hoc-Filter (`fes:Filter`, z. B. `PropertyIsEqualTo`) müssen die Attribute mit dem Namespace-Präfix `ave:` referenzieren** (`<fes:ValueReference>ave:gemaschl</fes:ValueReference>`), nicht ohne Präfix. Ohne Präfix ebenfalls HTTP 400 mit der gleichen generischen HTML-Fehlerseite.

Beide Fehler sehen identisch aus (dieselbe generische `geoportal.sachsen.de/400.html`-Seite, unabhängig vom eigentlichen Grund) — das macht Debugging ohne Referenzwissen schwer. Details und Lösung siehe Abschnitt 1.

---

## 1. ALKIS-WFS (vereinfachtes AdV-Schema), GeoSN

**Endpunkt:** `https://geodienste.sachsen.de/aaa/public_alkis/vereinf/wfs` ✅ live erreichbar (GET & POST)

- WFS-Version: 1.1.0 und 2.0.0 (getestet mit 2.0.0)
- Kostenfrei, Quellenvermerk "Landesamt für Geobasisinformation Sachsen (GeoSN)" bzw. "GeoSN" — Lizenz siehe Abschnitt 5
- **Max. Objektanzahl pro Antwort: 20.000** (`CountDefault=20000`, im Capabilities-Dokument bestätigt und in der Service-Beschreibung: "Direktzugriffs-Downloaddienst bis maximal 20.000 Objekte")

### 1.1 FeatureTypes (✅ live per GetCapabilities ermittelt)

Namespace-Präfix: `ave:` → `http://repository.gdi-de.org/schemas/adv/produkt/alkis-vereinfacht/2.0`

| FeatureType | Titel | Kurzbeschreibung |
|---|---|---|
| `ave:Flurstueck` | Flurstueck | Flurstücke inkl. Lagebezeichnung und tatsächlicher Nutzung |
| `ave:FlurstueckPunkt` | FlurstueckPunkt | Punktförmiger Repräsentant je Flurstück (Georeferenzierung) |
| `ave:GebaeudeBauwerk` | GebaeudeBauwerk | Gebäude/Bauwerke (Basis für Hausumringe) |
| `ave:KatasterBezirk` | KatasterBezirk | Gemarkungen/Fluren |
| `ave:Nutzung` | Nutzung | Tatsächliche Nutzung (die "Nutzungs-/Verkehrsflächen"-Objektart) |
| `ave:NutzungFlurstueck` | NutzungFlurstueck | Verschneidung Nutzung × Flurstück |
| `ave:VerwaltungsEinheit` | VerwaltungsEinheit | Verwaltungsgrenzen (Gemeinde, Kreis, Land …) |

Default-SRS: `EPSG:25833`, weitere unterstützte SRS: `EPSG:25832`, `EPSG:4258` (alle drei ✅ live in Capabilities bestätigt).

### 1.2 DescribeFeatureType — Attribute (✅ live abgerufen)

**`ave:Flurstueck`** (das für den Grundstücks-Check zentrale Objekt):

| Attribut | Typ | Pflicht | Bedeutung |
|---|---|---|---|
| `idflurst` | string | ✓ | interne ALKIS-ID des Flurstücks |
| `flstkennz` | string | ✓ | **Flurstückskennzeichen** (20-stelliger AdV-Schlüssel, z. B. `140415___00604000202`) |
| `land` | string | ✓ | Bundesland (Klartext) |
| `landschl` | string | ✓ | Länderschlüssel (`14` = Sachsen) |
| `gemarkung` | string | ✓ | **Gemarkungsname** (Klartext, z. B. "Leipzig") |
| `gemaschl` | string | ✓ | **Gemarkungsnummer/-schlüssel** (6-stellig, Länderpräfix + Gemarkung, z. B. `140415`) |
| `flur` | string | optional | Flurnummer |
| `flurschl` | string | optional | Flurschlüssel |
| `flstnrzae` | string | ✓ | **Flurstücksnummer Zähler** |
| `flstnrnen` | string | optional | **Flurstücksnummer Nenner** |
| `regbezirk` / `regbezschl` | string | optional | Regierungsbezirk (Klartext/Schlüssel) |
| `kreis` | string | optional | Landkreis (Klartext) |
| `kreisschl` | string | ✓ | Kreisschlüssel |
| `gemeinde` | string | ✓ | Gemeinde (Klartext) |
| `gmdschl` | string | ✓ | Gemeindeschlüssel (AGS) |
| `oid` | string | ✓ | Objekt-ID |
| `aktualit` | date | ✓ | Aktualitätsdatum |
| `geometrie` | `gml:MultiSurfacePropertyType` | ✓ | Flurstücksgeometrie (Polygon/MultiPolygon) |
| `flaeche` | **double** | ✓ | **Amtliche Fläche in m²** (im Live-Test z. B. `39`, `253`, `1170` — ganzzahlig dargestellt, Typ ist aber `double`) |
| `abwrecht` | string | optional | abweichender Rechtszustand |
| `lagebeztxt` | string | ✓ | Lagebezeichnung (Adresse, z. B. "Markt 11, 12; Thomasgasse 2, 4") |
| `tntxt` | string | optional | Text zur tatsächlichen Nutzung (optional, länderabhängig) |

→ **Das amtliche Flächen-Attribut heißt eindeutig `flaeche`** (double, m²).

**`ave:GebaeudeBauwerk`:**

| Attribut | Typ | Pflicht |
|---|---|---|
| `oid` | string | ✓ |
| `aktualit` | date | ✓ |
| `geometrie` | `gml:MultiSurfacePropertyType` | ✓ |
| `gebnutzbez` | string | ✓ | Gebäudenutzungsbezeichnung |
| `funktion` | string | ✓ | Gebäudefunktion (Schlüssel/Text) |
| `gfkzshh` | string | optional | Gebäudefunktionskennung ZSHH |
| `rellage` | string | optional | relative Lage |
| `name` | string | optional | |
| `anzahlgs` | integer | optional | Anzahl Geschosse |
| `gmdschl` | string | optional | Gemeindeschlüssel |
| `lagebeztxt` | string | optional | Lagebezeichnung |

**`ave:Nutzung`** (Nutzungs-/Verkehrsflächen-Objektart):

| Attribut | Typ | Pflicht |
|---|---|---|
| `oid` | string | ✓ |
| `aktualit` | date | ✓ |
| `geometrie` | `gml:MultiSurfacePropertyType` | ✓ |
| `nutzart` | string | ✓ | **Nutzungsart im Klartext** (Live-Beispiel: `"Straßenverkehr"`, `"Industrie- und Gewerbefläche / Handel und Dienstleistung"`) |
| `bez` | string | optional | Bezeichnung |
| `name` | string | optional | |

**`ave:NutzungFlurstueck`** (zusätzlich `flstkennz` string, verknüpft Nutzung mit Flurstück).

### 1.3 Stored Queries (✅ alle 5 live via `ListStoredQueries`/`DescribeStoredQueries` ermittelt und getestet)

| Query-ID (`STOREDQUERY_ID`) | Titel | Parameter (alle `xsd:String`) |
|---|---|---|
| `http://repository.gdi-de.org/query/adv/produkt/alkis-vereinfacht/2.0/ave-by-bbox` | ALKIS-vereinfacht anhand BoundingBox | `CRS`, `x1`, `y1`, `x2`, `y2` |
| `http://repository.gdi-de.org/query/adv/produkt/alkis-vereinfacht/2.0/flst-by-kennzeichen` | Flurstück anhand Kennzeichen | `CRS`, `kennzeichen` |
| `urn:x-ii:def:query:OGC-WFS::flst-by-kurzkennzeichen` | Flurstück anhand Kennzeichen, **Wildcards möglich** | `CRS`, `kennzeichen` (z. B. `140415___00604*`) |
| `http://repository.gdi-de.org/query/adv/produkt/alkis-vereinfacht/2.0/flst-by-gemarkung` | Flurstücke anhand Gemarkung | `CRS`, `gemarkungsnummer` |
| `urn:ogc:def:query:OGC-WFS::GetFeatureById` | Get feature by ID | `id` (kein `CRS` nötig) |

**Es gibt KEINE eigene Stored Query "Gemarkung + Zähler + Nenner"** — dafür muss ein **ad-hoc-Filter** verwendet werden (siehe 1.5b).

⚠️ **CRS ist bei allen Stored Queries außer `GetFeatureById` PFLICHT.** Ohne `CRS`-Parameter liefert der Dienst HTTP 400 mit einer generischen sachsen.de-HTML-Fehlerseite statt eines OGC-Fehlers — das sieht zunächst wie ein kaputter/gesperrter Endpunkt aus, ist aber nur ein fehlender Parameter. (✅ live reproduziert und gelöst.)

### 1.4 Ausprobierte Beispielabfragen (alle ✅ live getestet, HTTP 200, mit echten Daten)

**a) Räumlicher Filter — BBOX um den Leipziger Markt (EPSG:25833):**

```bash
curl -G "https://geodienste.sachsen.de/aaa/public_alkis/vereinf/wfs" \
  --data-urlencode "SERVICE=WFS" \
  --data-urlencode "VERSION=2.0.0" \
  --data-urlencode "REQUEST=GetFeature" \
  --data-urlencode "TYPENAMES=ave:Flurstueck" \
  --data-urlencode "BBOX=316980,5690830,317090,5690930,urn:ogc:def:crs:EPSG::25833" \
  --data-urlencode "COUNT=5"
```

Liefert u. a. dieses reale Flurstück (Leipzig, Markt 11/12):

```xml
<wfs:member>
<Flurstueck gml:id="DESNALK0v80000tjFL">
  <idflurst>DESNALK0v80000tj</idflurst>
  <flstkennz>140415___00604000202</flstkennz>
  <land>Freistaat Sachsen</land>
  <gemarkung>Leipzig</gemarkung>
  <gemaschl>140415</gemaschl>
  <flstnrzae>604</flstnrzae>
  <flstnrnen>2</flstnrnen>
  <kreis>Kreisfreie Stadt Leipzig</kreis>
  <kreisschl>14713</kreisschl>
  <gemeinde>Stadt Leipzig</gemeinde>
  <gmdschl>14713000</gmdschl>
  <aktualit>2019-07-18Z</aktualit>
  <geometrie>...MultiSurface EPSG:25833...</geometrie>
  <flaeche>39</flaeche>
  <abwrecht>Kein abweichender Rechtszustand</abwrecht>
  <lagebeztxt>Markt 11, 12; Thomasgasse 2, 4</lagebeztxt>
  <tntxt>Industrie- und Gewerbefläche / Handel und Dienstleistung;39</tntxt>
</Flurstueck>
</wfs:member>
```

Äquivalent per Stored Query `ave-by-bbox`:

```bash
curl -G "https://geodienste.sachsen.de/aaa/public_alkis/vereinf/wfs" \
  --data-urlencode "SERVICE=WFS" --data-urlencode "VERSION=2.0.0" \
  --data-urlencode "REQUEST=GetFeature" \
  --data-urlencode "STOREDQUERY_ID=http://repository.gdi-de.org/query/adv/produkt/alkis-vereinfacht/2.0/ave-by-bbox" \
  --data-urlencode "CRS=urn:ogc:def:crs:EPSG::25833" \
  --data-urlencode "x1=316980" --data-urlencode "y1=5690830" \
  --data-urlencode "x2=317090" --data-urlencode "y2=5690930" \
  --data-urlencode "COUNT=5"
```

**b) Filter über Gemarkung + Zähler + Nenner (ad-hoc `fes:Filter`, POST):**

Es gibt keine passende Stored Query dafür; funktioniert aber per ad-hoc-Filter — **wichtig: `ave:`-Präfix bei `ValueReference` und `srsName` an `wfs:Query`**:

```bash
curl -X POST -H "Content-Type: application/xml" \
  "https://geodienste.sachsen.de/aaa/public_alkis/vereinf/wfs" \
  -d '<?xml version="1.0" encoding="UTF-8"?>
<wfs:GetFeature xmlns:wfs="http://www.opengis.net/wfs/2.0"
                xmlns:fes="http://www.opengis.net/fes/2.0"
                xmlns:ave="http://repository.gdi-de.org/schemas/adv/produkt/alkis-vereinfacht/2.0"
                service="WFS" version="2.0.0">
  <wfs:Query typeNames="ave:Flurstueck" srsName="urn:ogc:def:crs:EPSG::25833">
    <fes:Filter>
      <fes:And>
        <fes:PropertyIsEqualTo>
          <fes:ValueReference>ave:gemaschl</fes:ValueReference>
          <fes:Literal>140415</fes:Literal>
        </fes:PropertyIsEqualTo>
        <fes:PropertyIsEqualTo>
          <fes:ValueReference>ave:flstnrzae</fes:ValueReference>
          <fes:Literal>604</fes:Literal>
        </fes:PropertyIsEqualTo>
        <fes:PropertyIsEqualTo>
          <fes:ValueReference>ave:flstnrnen</fes:ValueReference>
          <fes:Literal>2</fes:Literal>
        </fes:PropertyIsEqualTo>
      </fes:And>
    </fes:Filter>
  </wfs:Query>
</wfs:GetFeature>'
```

→ liefert exakt 1 Treffer, dasselbe Flurstück wie oben (`flstkennz=140415___00604000202`). ✅ live getestet.

Alternative über die Stored Query `flst-by-gemarkung` (liefert **alle** Flurstücke der Gemarkung, client-seitig nach Zähler/Nenner filtern):

```bash
curl -G "https://geodienste.sachsen.de/aaa/public_alkis/vereinf/wfs" \
  --data-urlencode "SERVICE=WFS" --data-urlencode "VERSION=2.0.0" \
  --data-urlencode "REQUEST=GetFeature" \
  --data-urlencode "STOREDQUERY_ID=http://repository.gdi-de.org/query/adv/produkt/alkis-vereinfacht/2.0/flst-by-gemarkung" \
  --data-urlencode "CRS=urn:ogc:def:crs:EPSG::25833" \
  --data-urlencode "gemarkungsnummer=140415"
```

**c) Flurstück per exaktem Flurstückskennzeichen (Stored Query):**

```bash
curl -G "https://geodienste.sachsen.de/aaa/public_alkis/vereinf/wfs" \
  --data-urlencode "SERVICE=WFS" --data-urlencode "VERSION=2.0.0" \
  --data-urlencode "REQUEST=GetFeature" \
  --data-urlencode "STOREDQUERY_ID=http://repository.gdi-de.org/query/adv/produkt/alkis-vereinfacht/2.0/flst-by-kennzeichen" \
  --data-urlencode "CRS=urn:ogc:def:crs:EPSG::25833" \
  --data-urlencode "kennzeichen=140415___00604000202"
```

→ ✅ genau 1 Treffer, identisch mit obigem Feature.

**d) Flurstück per Kennzeichen mit Wildcard:**

```bash
curl -G "https://geodienste.sachsen.de/aaa/public_alkis/vereinf/wfs" \
  --data-urlencode "SERVICE=WFS" --data-urlencode "VERSION=2.0.0" \
  --data-urlencode "REQUEST=GetFeature" \
  --data-urlencode "STOREDQUERY_ID=urn:x-ii:def:query:OGC-WFS::flst-by-kurzkennzeichen" \
  --data-urlencode "CRS=urn:ogc:def:crs:EPSG::25833" \
  --data-urlencode "kennzeichen=140415___00604*"
```

→ ✅ 5 Treffer (alle Flurstücke, deren Kennzeichen mit `140415___00604` beginnt).

### 1.5 Ausgabeformate (✅ live aus Capabilities + Test bestätigt)

- `text/xml; subtype=gml/3.1.1`
- `application/gml+xml; version=3.1`
- `text/xml; subtype=gml/3.2.1` (Standard bei GetFeature ohne Angabe)
- `application/gml+xml; version=3.2`
- `application/x-zip-shapefile` (nur bei `GetFeature`, nicht bei `DescribeFeatureType`)
- ❌ **KEIN GeoJSON** — `OUTPUTFORMAT=application/json` liefert HTTP 400 (✅ live getestet). Wer GeoJSON braucht, muss GML clientseitig konvertieren (z. B. mit ogr2ogr/Turf/togeojson).

### 1.6 CORS (✅ live geprüft)

```
Access-Control-Allow-Origin: <reflektierter Origin-Header>
Access-Control-Allow-Credentials: true
```
→ Der Dienst spiegelt den `Origin`-Header und erlaubt Cross-Origin-Requests direkt aus dem Browser (`fetch()`), kein eigener Backend-Proxy nötig.

### 1.7 Fallstricke ALKIS-WFS

1. **`CRS` ist Pflichtparameter bei jeder Stored Query außer `GetFeatureById`.** Ohne ihn: HTTP 400, generische HTML-Fehlerseite (`geoportal.sachsen.de/400.html`), **kein** OGC-`ServiceExceptionReport`. Das täuscht leicht einen kaputten Dienst oder eine WAF-Blockade vor.
2. **Ad-hoc-Filter (`fes:Filter`) brauchen den Namespace-Präfix `ave:`** bei `fes:ValueReference` (z. B. `ave:gemaschl`, nicht `gemaschl`). Ohne Präfix: derselbe generische HTTP-400-Fehler wie oben.
3. Jede Art von HTTP-400-Fehler dieses Dienstes (egal ob falscher Parameter, unbekannte Stored-Query-ID, fehlender Pflichtparameter, ungültiger TYPENAME) liefert **dieselbe generische sachsen.de-Fehlerseite** — es lohnt sich nicht, den Fehlertext zu parsen; man muss die eigene Anfrage anhand der Doku/DescribeStoredQueries prüfen.
4. `flaeche` wird im Live-Test als ganzzahliger String ausgegeben (z. B. `39`), obwohl der Typ laut Schema `double` ist — beim Parsen entsprechend robust behandeln (`parseFloat`).
5. `flstnrnen` (Nenner) ist optional — bei Flurstücken ohne Nenner fehlt das Element komplett (nicht leer).
6. Max. 20.000 Objekte je Antwort (`COUNT`/`CountDefault`) — bei landkreisweiten Abfragen ggf. paginieren (`STARTINDEX`, obwohl `ImplementsResultPaging=FALSE` im Capabilities-Dokument steht — ⚠️ nicht live gegengetestet, ob Paging trotzdem funktioniert).

---

## 2. BORIS Sachsen (Bodenrichtwerte)

**Hauptportal:** `https://www.boris.sachsen.de/` ✅ erreichbar (liefert allerdings nur Informationsseiten, keinen direkten Dienst-Link im HTML)

Der eigentliche Kartendienst/Viewer wird über `https://www.boris.sachsen.de/bodenrichtwertrecherche-4034.html` → verlinkt auf den map.apps-Viewer `https://geoviewer.sachsen.de/mapviewer/resources/apps/gaa/index.html`. Aus dessen Konfiguration (`app.json`, ✅ live abgerufen) wurde der tatsächliche WMS-Endpunkt extrahiert:

**WMS-Endpunkt:** `https://www.landesvermessung.sachsen.de/fp/httpproxy/svcdep/wms/boris_2026` ✅ live erreichbar (MapServer 7.6.4, WMS 1.3.0)

⚠️ Der Endpunktname enthält das Jahr (`boris_2026`) — es ist zu erwarten, dass GeoSN mit jedem neuen Bodenrichtwert-Stichtag den Endpunktnamen ändert (z. B. `boris_2027` im kommenden Jahr) oder ihn per Redirect weiterleitet. Das wurde **nicht** geprüft (⚠️ nur Vermutung basierend auf der Namenskonvention) — für eine produktive Integration empfiehlt es sich, die aktuelle URL bei jedem Deploy neu aus der `boris.sachsen.de`-Seite bzw. dem `gaa/app.json` zu ermitteln statt sie hart zu kodieren.

### 2.1 Layer (✅ live aus GetCapabilities)

Hauptlayer für die Auskunft: **`brw_2026`** ("Bodenrichtwerte Sachsen 2026"), queryable. Stichtags-Zeitraum laut Abstract: **02.01.2025 bis 01.01.2026**.

Weitere (teils gruppierte, ebenfalls queryable) Themenlayer:

| Layer-Name | Titel |
|---|---|
| `brw_2026` | Bodenrichtwerte Sachsen 2026 (Gesamtlayer, alle Nutzungsarten) |
| `brw_land_acker_2026` | Ackerland 2026 |
| `brw_land_gruenland_2026` | Grünland 2026 |
| `brw_land_forst_2026` | Forstwirtschaftliche Flächen 2026 |
| `brw_land_weitere_2026` | weitere land-/forstwirtschaftliche Flächen 2026 |
| `brw_sonstige_2026` | sonstige Flächen 2026 |
| `brw_bauland_2026` | Bauland 2026 |
| `brw_massnahme_2026` | städtebauliche Maßnahmegebiete 2026 |
| `brw_gutachterausschuesse_2026` | Zuständiger Gutachterausschuss |
| `beschriftung_2026` | Beschriftung |
| `brw_highlight` | Hervorhebungslayer (für Einzeldarstellung) |

### 2.2 GetFeatureInfo — Formate (✅ live getestet)

Laut Capabilities unterstützt: `text/plain`, `text/html`, `application/json`, `application/vnd.ogc.gml`, `gml`.

**⚠️/❗ Wichtiger Fallstrick: `application/json` ist NICHT GeoJSON, sondern UTFGrid!**

Test mit `INFO_FORMAT=application/json` auf dem Gesamtlayer `brw_2026`:
```
HTTP 200, aber ServiceExceptionReport:
"utfgridStartLayer(): MapServer does not support multiple UTFGrid layers rendering simultaneously."
```
Auf einem einzelnen Sub-Layer (z. B. `brw_bauland_2026`) liefert `application/json` tatsächlich ein UTFGrid-JSON (`{"grid": [...], "keys": [...], "data": {...}}`) — **kein** GeoJSON-FeatureCollection mit den Bodenrichtwert-Feldern. Für strukturierte, programmatisch nutzbare Daten müssen `text/plain` oder `application/vnd.ogc.gml` verwendet werden.

**Beispielabfrage (✅ echte Koordinate in Leipzig, EPSG:25833, X=317034.75 Y=5690878.12 nahe Markt):**

```bash
curl -G "https://www.landesvermessung.sachsen.de/fp/httpproxy/svcdep/wms/boris_2026" \
  --data-urlencode "SERVICE=WMS" --data-urlencode "VERSION=1.3.0" \
  --data-urlencode "REQUEST=GetFeatureInfo" \
  --data-urlencode "LAYERS=brw_2026" --data-urlencode "QUERY_LAYERS=brw_2026" \
  --data-urlencode "CRS=EPSG:25833" \
  --data-urlencode "BBOX=316984.75,5690828.12,317084.75,5690928.12" \
  --data-urlencode "WIDTH=101" --data-urlencode "HEIGHT=101" \
  --data-urlencode "I=50" --data-urlencode "J=50" \
  --data-urlencode "INFO_FORMAT=text/plain" --data-urlencode "FEATURE_COUNT=5"
```

**Reale Antwort (gekürzt, `text/plain`):**

```
GetFeatureInfo results:

Layer 'brw_bauland_2026'
  Feature 1367487:
    BODENRICHTWERT_TEXT = '2400'
    BODENRICHTWERTNUMMER = '71300402'
    ENTWICKLUNGSZUSTAND_K = 'B'
    ENTWICKLUNGSZUSTAND_TEXT = 'Baureifes Land'
    NUTZUNG = 'MK'
    NUTZUNG_TEXT = 'Kerngebiet'
    STICHTAG_TXT = '01.01.2026'
    BAUWEISE_K = 'g'
    BAUWEISE_TEXT = 'geschlossene Bauweise'
    WRGESCHOSSFLAECHENZAHL_TEXT = 'WGFZ5,0'
    GA_POST_NAME = 'Gutachterausschuss für Grundstückswerte in der Stadt Leipzig'
    GA_POST_ADRESSE = 'Burgplatz 1, 04109 Leipzig'
    GA_TELEFON = '+49341 1235072'
    GA_EMAIL = 'gutachterausschuss@leipzig.de'
    ...
```

Gleiche Abfrage mit `INFO_FORMAT=application/vnd.ogc.gml` liefert strukturiertes XML (`msGMLOutput`) mit denselben Feldern als XML-Elemente — für programmatische Weiterverarbeitung besser geeignet als `text/plain`.

### 2.3 Feldliste GetFeatureInfo (✅ live, vollständig aus obiger Testantwort)

| Feld | Beispielwert | Bedeutung |
|---|---|---|
| `BODENRICHTWERT_TEXT` | `2400` | **Bodenrichtwert in €/m²** |
| `BODENRICHTWERTNUMMER` | `71300402` | **Zonennummer/BRW-Zone** |
| `NUTZUNG` | `MK` | Nutzungsart-Kürzel |
| `NUTZUNG_TEXT` | `Kerngebiet` | **Nutzungsart im Klartext** |
| `ENTWICKLUNGSZUSTAND_K` / `_TEXT` | `B` / `Baureifes Land` | Entwicklungszustand |
| `STICHTAG_TXT` | `01.01.2026` | **Stichtag** |
| `BRZ_TEXT` / `BRZ_KURZTEXT` | `beitragsfrei` / `(frei)` | beitrags-/abgaberechtlicher Zustand |
| `BAUWEISE_K` / `_TEXT` | `g` / `geschlossene Bauweise` | nur Bauland |
| `WRGESCHOSSFLAECHENZAHL_TEXT` | `WGFZ5,0` | wertrelevante Geschossflächenzahl |
| `ACKERZAHL`, `GRUENLANDZAHL` | (leer bei Bauland) | nur Land-/Forstwirtschaftsflächen |
| `GA_POST_NAME`, `GA_POST_ADRESSE`, `GA_TELEFON`, `GA_TELEFAX`, `GA_EMAIL`, `GA_WWW` | siehe oben | zuständiger Gutachterausschuss |
| `GA_FACHINFO`, `UMRECHNUNGSTABELLEN` | URLs | Links zu PDF-Erläuterungen/Umrechnungstabellen |
| `BEMERKUNGEN` | `---` | Freitext |

### 2.4 Vektor-Download / WFS

❌ **Kein WFS.** Live-Test bestätigt:
```
msWFSDispatch(): WFS server error. WFS request not enabled. Check wfs/ows_enable_request settings.
```
BORIS Sachsen stellt Bodenrichtwerte **nur als WMS** bereit — kein maschinell durchsuchbarer Flächen-Download über einen offenen Dienst. (Für Bulk-Auswertungen müsste man rasterartig über die Fläche GetFeatureInfo-Anfragen stellen oder ggf. eine kommerzielle/andere Quelle nutzen — ⚠️ nicht weiter recherchiert.)

### 2.5 CORS (✅ live geprüft)

```
Access-Control-Allow-Origin: *
Access-Control-Expose-Headers: Content-Type
```
→ Uneingeschränkt für alle Origins freigegeben, direkter Browser-Zugriff möglich.

---

## 3. WMS-Dienste des GeoSN für den Ebenen-Umschalter

Alle drei folgenden Dienste wurden ✅ live per `GetCapabilities` (WMS 1.3.0) verifiziert.

### 3.1 Luftbild / Digitale Orthophotos (DOP)

**Endpunkt:** `https://geodienste.sachsen.de/wms_geosn_dop-rgb/guest`

| Layer | Bedeutung |
|---|---|
| `sn_dop_020` | Digitales Orthophoto, 20 cm Bodenauflösung, RGB |

- Formate: `image/png`, `image/png8`, `image/png24`, `image/png32`, `image/jpeg`, `image/tiff`, `image/gif`, `image/svg+xml`
- CRS: `CRS:84`, `EPSG:4326`, `EPSG:25833`, `EPSG:4258`, `EPSG:25832`, `EPSG:31469`, u. a.
- Fees laut Capabilities: `kostenfrei`
- Quellenvermerk: "GeoSN", Lizenz Datenlizenz Deutschland – Namensnennung – Version 2.0 (siehe Abschnitt 5)

Beispiel `GetMap` (✅ Endpunkt live erreichbar, Bild-URL nicht separat dekodiert):
```
https://geodienste.sachsen.de/wms_geosn_dop-rgb/guest?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&LAYERS=sn_dop_020&STYLES=&CRS=EPSG:25833&BBOX=316980,5690830,317090,5690930&WIDTH=800&HEIGHT=800&FORMAT=image/png
```

### 3.2 Topografische Karte (WebAtlas Sachsen)

**Endpunkt:** `https://geodienste.sachsen.de/wms_geosn_webatlas-sn/guest`

| Layer | Bedeutung |
|---|---|
| `Vegetation` | Vegetationsflächen |
| `Siedlung` | Siedlungsflächen/Gebäude |
| `Gewaesser` | Gewässer |
| `Verkehr` | Verkehrsnetz |
| `Administrative_Einheiten` | Verwaltungsgrenzen |
| `Beschriftung` | Kartenbeschriftung |

(jeweils mit Styles `palette_rgb_halbton`, `palette_grau`)

### 3.3 ALKIS-Darstellungsdienst (Liegenschaftskarte als Bild)

**Endpunkt:** `https://geodienste.sachsen.de/wms_geosn_alkis-adv/guest`

| Layer | Bedeutung |
|---|---|
| `adv_alkis_tatsaechliche_nutzung` | Tatsächliche Nutzung |
| `adv_alkis_gewaesser` | Gewässer |
| `adv_alkis_vegetation` | Vegetation |
| `adv_alkis_verkehr` | Verkehr |
| `adv_alkis_siedlung` | Siedlung |
| `adv_alkis_gesetzl_festlegungen` | Gesetzliche Festlegungen |
| (weitere: Gruppe "Weiteres" mit Bauwerken/Relief laut ⚠️ Websuche, nicht im Detail live durchgeprüft) |

- Formate: `image/png`, `image/jpeg`, `image/gif`
- CRS: `EPSG:25833`, `EPSG:4258`, `EPSG:4326`, `EPSG:25832`, `EPSG:31469`, `EPSG:31468`, `EPSG:31467`, `EPSG:31466`
- `Fees` verweist auf `https://www.landesvermessung.sachsen.de/wms-alkis-5394.html` (⚠️ Link bei Testabruf 404 — vermutlich umgezogen)
- `AccessConstraints: none`

### 3.4 CORS (✅ live geprüft, für alle drei Dienste identisch)

```
Access-Control-Allow-Origin: <reflektierter Origin>
Access-Control-Allow-Credentials: true
```

### 3.5 Nutzungsbedingungen/Quellenvermerk

Siehe Abschnitt 5 — gilt einheitlich für alle GeoSN-WMS-Dienste: **Datenlizenz Deutschland – Namensnennung – Version 2.0**, Quellenvermerk "GeoSN" (bzw. ausgeschrieben "Landesamt für Geobasisinformation Sachsen (GeoSN)").

---

## 4. Hauskoordinaten & Hausumringe Sachsen

Download-Seiten (✅ live abgerufen):
- Hauskoordinaten: `https://www.geodaten.sachsen.de/downloadbereich-hauskoordinaten-4172.html`
- Hausumringe: `https://www.geodaten.sachsen.de/downloadbereich-hausumringe-4174.html`

Beide Seiten geben an: **"Die Daten werden vierteljährlich aktualisiert."** (✅ Text live von der Seite gelesen)

### 4.1 Hauskoordinaten

**Direkter Download-Link (✅ live funktionsfähig, per `curl -r` verifiziert, Nextcloud-Freigabe):**
```
https://geocloud.landesvermessung.sachsen.de/public.php/dav/files/B3HnXbDDgAkw69a/hk_sn_ascii.zip
```
- Größe: **51.236.896 Bytes (≈ 48,9 MB)**, Format: ZIP mit einer CSV-Textdatei
- ZIP-Inhalt: `hk_sn_adressen_20260702.txt` (**Datenstand 02.07.2026**)
- Kodierung: UTF-8, Trennzeichen `;`, Zeilenende `\r\n`

⚠️ Fallstrick: `curl -I`/`HEAD` liefert auf diesem Nextcloud-Freigabelink **HTTP 401** (der Server verlangt offenbar einen initialen `GET`/Range-Request statt HEAD, um die anonyme Freigabe-Session zu erzeugen) — für Verfügbarkeits-/Health-Checks daher `GET` mit `Range: bytes=0-0` statt `HEAD` verwenden.

**Feldliste (✅ live aus der CSV-Kopfzeile + Beispieldatensätzen):**

| Feld | Beispielwert | Bedeutung |
|---|---|---|
| `nba` | `N` | Neubau-/Bearbeitungskennung (vermutlich Statuskennzeichen) |
| `oid` | `DESNALK0AUB0007U` | Objekt-ID |
| `qua` | `A` | Qualitätsstufe |
| `landschl` | `14` | Länderschlüssel |
| `land` | `Freistaat Sachsen` | Land |
| `regbezschl` / `regbez` | `7` / `NUTS 2-Region Leipzig` | Regierungsbezirk |
| `kreisschl` / `kreis` | `29` / `Landkreis Leipzig` | Kreis |
| `gmdschl` / `gmd` | `140` / `Stadt Frohburg` | Gemeinde |
| `ottschl` / `ott` | `0210` / `Dolsenhain` | Ortsteil |
| `strschl` / `str` | `59992` / `Dolsenhainer Straße` | Straße |
| `hnr` | `2` | Hausnummer |
| `adz` | `a` | Adresszusatz (Buchstabe) |
| `zone` | `33` | UTM-Zonenkennzahl (33 → EPSG:25833) |
| `ostwert` | `328618.634` | **Ostwert (X, EPSG:25833)** |
| `nordwert` | `5654060.693` | **Nordwert (Y, EPSG:25833)** |
| `postplz` | `04654` | PLZ |
| `postonm` | `Frohburg` | Post-Ortsname |
| `postonmzus` | (leer) | Post-Ortsnamenzusatz |
| `postott` | `Dolsenhain` | Post-Ortsteil |

### 4.2 Hausumringe

**Direkter Download-Link (✅ live funktionsfähig geprüft, ZIP-Struktur per HTTP-Range-Trick ohne Komplettdownload ausgelesen):**
```
https://geocloud.landesvermessung.sachsen.de/public.php/dav/files/AcAqRn4k9Sz8ZZx/hu_sn_shape.zip
```
- Größe: **226.794.989 Bytes (≈ 216 MB)**
- ZIP-Inhalt (Shapefile, 6 Dateien, alle mit Datenstand **02.07.2026**):
  - `hu_sn_gebaeude_20260702.shp` (442 MB unkomprimiert)
  - `hu_sn_gebaeude_20260702.shx`
  - `hu_sn_gebaeude_20260702.dbf` (89 MB unkomprimiert, **2.541.856 Datensätze**)
  - `hu_sn_gebaeude_20260702.prj`
  - `hu_sn_gebaeude_20260702.cpg`
  - `hu_sn_gebaeude_20260702.qix` (räumlicher Index)

**Feldliste DBF (✅ live per partiellem Download + Deflate-Streaming aus dem ZIP extrahiert, ohne die vollen 216 MB zu laden):**

| Feld | Typ | Länge | Beispielwert | Bedeutung |
|---|---|---|---|---|
| `AGS` | Character | 8 | `14522275` | Amtlicher Gemeindeschlüssel |
| `OI` | Character | 16 | `DESNALK0EQD0009u` | Objekt-Identifikator (ALKIS-OID) |
| `GFK` | Character | 10 | `31001_1000` | Gebäudefunktionskennung (Schlüssel_Wert) |

→ Die Hausumringe-Shapefiles enthalten **nur 3 Sachattribute** (AGS, Objekt-ID, Gebäudefunktion) — die Geometrie (Polygon-Umring) selbst steckt in `.shp`. Für weitere Attribute (Adresse etc.) muss über `OI`/räumliche Lage mit dem ALKIS-WFS (`ave:GebaeudeBauwerk`, verknüpft über `oid`) bzw. den Hauskoordinaten (räumlicher Join) verknüpft werden.

### 4.3 Format, Lizenz, Aktualisierung

- Format: Hauskoordinaten = CSV/Text, Hausumringe = Esri Shapefile (`.shp/.shx/.dbf/.prj/.cpg` + `.qix`-Spatialindex)
- Aktualisierungszyklus: **vierteljährlich** (✅ Text von den offiziellen Downloadseiten)
- Lizenz: Datenlizenz Deutschland – Namensnennung – Version 2.0, kostenfrei (siehe Abschnitt 5) — als Teil des "Offene Geodaten"-Downloadbereichs von sachsen.de
- Referenzsystem: EPSG:25833 (UTM Zone 33N, ETRS89) — aus dem Feld `zone=33` bei Hauskoordinaten sowie der amtlichen GeoSN-Konvention ableitbar (⚠️ `.prj`-Datei nicht inhaltlich ausgelesen, nur ihre Existenz/Größe bestätigt)

---

## 5. Lizenz / Nutzungsbedingungen (gilt für alle GeoSN-Dienste und -Downloads)

**Quelle:** `https://www.landesvermessung.sachsen.de/allgemeine-nutzungsbedingungen-8954.html` (✅ live abgerufen)

> "Die Erlaubnis entspricht dem Lizenzmuster der **Datenlizenz Deutschland – Namensnennung – Version 2.0** unter Angabe des Quellenvermerks 'Landesamt für Geobasisinformation Sachsen (GeoSN)' oder kurz 'GeoSN'. Der Download und die Nutzung der online bereitgestellten Daten sind nach der Sächsischen Vermessungskostenverordnung kostenfrei."

Empfohlene Quellenangabe (wörtlich von der Seite):
- Elektronische Medien: `Quelle: GeoSN, dl-de/by-2-0, [optional: URI des Datensatzes]`
- Druckmedien: `Quelle: GeoSN, dl-de/by-2-0, [optional: Produktname]`

⚠️ Ausnahme: Eigentümerdaten aus dem Liegenschaftskataster (in Replikationen/Präsentationsausgaben) dürfen laut derselben Seite **nicht veröffentlicht oder an Dritte weitergegeben werden** — betrifft "Grundstücks-Check Sachsen" nicht direkt, da der ALKIS-vereinfacht-WFS ohnehin keine Eigentümerdaten liefert (im Schema nicht enthalten, ✅ per DescribeFeatureType bestätigt).

---

## 6. Offene Punkte / nicht abschließend geklärt

- ⚠️ Ob `ImplementsResultPaging=FALSE` beim ALKIS-WFS bedeutet, dass `STARTINDEX` tatsächlich ignoriert wird (relevant bei > 20.000 Treffern), wurde nicht getestet.
- ⚠️ Die Langlebigkeit der BORIS-WMS-URL mit Jahreszahl im Pfad (`boris_2026`) — ob es eine stabile, jahreszahl-unabhängige Alias-URL gibt, wurde nicht gefunden; für Produktivbetrieb empfiehlt sich ein jährlicher Check bzw. dynamisches Nachschlagen über `boris.sachsen.de`.
- ⚠️ Die vollständige Layer-/Gruppenstruktur des ALKIS-Darstellungsdienstes (`wms_geosn_alkis-adv`) wurde nicht bis in die letzte Verschachtelungsebene ausgewertet (z. B. Gruppe "Weiteres" mit Bauwerken/Relief laut Websuche-Snippet).
- ⚠️ Kein Test, ob es für BORIS einen (evtl. kostenpflichtigen oder zugangsbeschränkten) Vektor-Download bei den einzelnen Gutachterausschüssen gibt — laut GetCapabilities-Text ist die WMS-Auskunft die vom GeoSN bereitgestellte Zugriffsart.
