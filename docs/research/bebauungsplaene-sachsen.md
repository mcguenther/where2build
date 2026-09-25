# Bebauungspläne, § 34 and Baulasten in Saxony — what data exists

**Research date: 2026-09-25.** Written in English: this is developer
documentation, only the user interface is German.

> **Legend**
> ✅ **VERIFIED LIVE (2026-09-25)** — a request was made from this shell and its
> answer read.
> 📘 **FROM THE STATUTE / OFFICIAL PAGE** — quoted from gesetze-im-internet.de,
> revosax.sachsen.de or the authority's own page, fetched on the research date.
> ⚠️ **NOT VERIFIED** — stated as an open question, not as a fact. Includes
> hosts this sandbox could not reach.

This is not legal advice. It records which services answer, what they carry,
and what the answers mean for drawing a buildable area.

Reference plot throughout: **Lessingweg 44, Gemarkung Mölkau, Flurstück 204**
(`frontend/tests/fixtures/parcel-moelkau.json`). WGS84 51.33653 N, 12.44180 E;
EPSG:25833 E 321 806.7, N 5 690 356.5. The fixture ring, projected to
EPSG:25833, measures 645.57 m², exactly the fixture's `flaeche_berechnet_m2`,
so the geometry sent to the services below is the right one.

---

## 1. The short answer

- **Is a point inside a B-Plan, and which one: yes, answerable statewide.**
  The Landesdirektion's RAPIS runs an open ArcGIS REST server
  (`rapis.ipm-gis.de/arcgis/rest/services`) with plan areas for all of Saxony:
  7 276 in force, 417 of them in Leipzig. It also carries plans in procedure,
  the §§ 34/35 statutes and the FNP. `query` with the parcel outline gives an
  exact intersection. ✅
- **The plan's *content* as vectors (Baugrenze, Baulinie, Bauweise, GRZ/GFZ,
  Vollgeschosse): no.** Nothing found for Leipzig or statewide in XPlanung, as
  INSPIRE PLU, or in any other vector form. RAPIS stores the plan area and the
  *Art* of use (WA, MI, GE, ...), plus a free-text label ("WA 3"). Leipzig
  publishes each plan as one scanned raster PDF with no text layer and no
  georeference. ✅
- **Lessingweg 44 is in no B-Plan that RAPIS or Leipzig's own list knows of.**
  The nearest plan in force is 863 m away, the nearest plan in procedure 590 m
  away, and no § 34(4) statute is nearer than 2.3 km. The FNP shows
  *Wohnbaufläche*. The plot sits among housing: 146 ALKIS outlines in a 240 m
  box (`services.md`). **§ 34 BauGB (unbeplanter Innenbereich) is therefore
  very likely**, with the caveats in § 3.4. ✅ for the data; the legal verdict
  is the Stadtplanungsamt's to give.
- **Baulasten: no data, only on request.** The register is kept by the untere
  Bauaufsichtsbehörde (Leipzig: Amt für Bauordnung und Denkmalpflege) and is
  open to anyone who shows a berechtigtes Interesse. Leipzig charges 22–70 € per
  plot and takes about four weeks. Leipzig also offers a free, non-binding map
  pre-check, which its own page currently calls unreliable, and whose host this
  sandbox cannot reach. 📘 / ⚠️
- **Official dataset of Innenbereichssatzungen: yes, inside RAPIS.** The layer
  "Satzungsbereiche" / "Satzungen §§ 34,35 BauGB" holds 9 records for Leipzig,
  all Ergänzungs-, Abrundungs- or Außenbereichssatzungen on the city edge.
  There is no Klarstellungssatzung for Mölkau, and no dataset of the
  Innenbereich itself exists. ✅

---

## 2. RAPIS / DIGROK — the statewide source that works

### 2.1 Endpoint and discovery ✅

The dataset record "RAPIS: Bebauungspläne im Freistaat Sachsen (freier
WMS-Dienst)" was found through the data.europa.eu API. The GDI-DE catalogue
(`gdk.gdi-de.org`) cut the connection from this sandbox, and answered 503
through WebFetch.

```
GET https://data.europa.eu/api/hub/search/datasets/b974d0cd-8d49-4060-8ee9-f1ef384d9403
```

> "freier WMS-Dienst für Bebauungsplanung (B-Pläne, VEP, Satzungen §§34,35
> BauGB) aller Kommunen im Freistaat Sachsen nach Kenntnisstand in den
> Referaten Raumordnung der Landesdirektion Sachsen"

Its distribution is
`https://rapis.ipm-gis.de/arcgis/services/WMS_BPLAN/MapServer/WMSServer`
(WMS 1.3.0, "Sachsen BPLAN"). All five layers are `queryable="1"`, and
GetFeatureInfo offers `application/geo+json`.

**The REST face of the same server is open**, and that is the one to use.
Following `services.md`, ArcGIS `identify` measures its tolerance in pixels,
while `query` intersects real geometry:

```
GET https://rapis.ipm-gis.de/arcgis/rest/services?f=json
```

ArcGIS 11.5. Services of interest: `WMS_BPLAN`, `WFS_BPLAN`, `PL_BPLAN`,
`RO_BPLAN_in_Kraft`, `RO_BPLAN_Planung`, `RO_Satzungen_BauGB`, `RO_FNP_wirksam`,
`WMS_FNP`, `RO_ergaenzende_Bauleitplanung` (Sanierungs- and
Stadtentwicklungsgebiete), `RO_sonstige_Baufl`.

| Service / layer | Content | Features statewide | in Leipzig |
|---|---|---|---|
| `WMS_BPLAN/3` | BPLAN Geltungsbereich – in Kraft | 7 276 (all `rechtskräftig`) | 417 |
| `WMS_BPLAN/1` | BPLAN Geltungsbereich – Planung | 3 997 (genehmigt, im Verfahren, RO …) | 45 |
| `WMS_BPLAN/2` | BPLAN Nutzungsarten – in Kraft | — | 2 815 |
| `WMS_BPLAN/5` | Satzungsbereiche (§§ 34, 35) | 3 632 | 9 |
| `RO_FNP_wirksam/1`, `WMS_FNP/2` | FNP wirksam | — | 3 955 |

Fields on the plan-area layer: `NAME, STATUS, KREIS, GEMEINDE, STANDORT,
RECHTSGRL, THEMA, PLAN, DAT_PLAN, DAT_GENEHM, DAT_SATZ, DAT_BEKANN, DAT_QUELLE,
ROK_NR, AKTE, DAT_RAPIS, AENDERUNG, INFO_VG, PLANTYP`. Native CRS is
EPSG:25833, and `maxRecordCount` is 10 000. `DAT_RAPIS` on the returned
records reads "LD Sachsen, ROK 21.09.2026, letzter RAPIS-Upload", so the data
is current to the week.

**Traps, measured:**

- **`WFS_BPLAN` is mislabelled.** Its layers 2 and 3 ("in Kraft") return
  `count: 0`. Its layer 4 ("Planung") returns 11 273, and grouping by `STATUS`
  shows that is *every* status: the 7 276 `rechtskräftig` plus all procedures.
  Use `WMS_BPLAN/3` for plans in force, or filter layer 4 on
  `STATUS='rechtskräftig'`.
- **`WMS_BPLAN/4` does not exist over REST** (`404 Layer not found`). The WMS
  layer "4 Satzungsbereiche" is REST layer **5**.
- The FNP layers spell their fields in lower case (`name`, `thema_det`,
  `dat_bekann`); the B-Plan layers use upper case.
- `GEMEINDE` for Leipzig is spelt `'Leipzig, Stadt'`.

### 2.2 The query at Mölkau 204 ✅

The parcel ring goes out as Esri JSON in EPSG:25833, oriented clockwise (the
ArcGIS hole trap in `services.md`):

```
GET https://rapis.ipm-gis.de/arcgis/rest/services/WMS_BPLAN/MapServer/{0,1,2,3,5}/query
    ?geometry={"rings":[[[321825.817,5690340.701],[321782.682,5690361.222],
               [321788.505,5690373.404],[321831.824,5690352.745],
               [321826.751,5690342.515],[321825.817,5690340.701]]],
               "spatialReference":{"wkid":25833}}
    &geometryType=esriGeometryPolygon&inSR=25833
    &spatialRel=esriSpatialRelIntersects&outFields=*&returnGeometry=false&f=json
```

**0 features on every layer**: plans in force, plans in procedure, both use
layers, and the statutes. The same holds for all of `WFS_BPLAN` 2–8, among them
"Gebiete ohne baurechtl. Festsetzungen" and "Einzelbauvorhaben nach SächsBO".

**Control, same request shape.** A point inside plan E-215, 322 026.6 /
5 689 299.3:

```
{'NAME': 'B-Pl. E-215 Wohngebiet Zweinaundf.Str.', 'STATUS': 'rechtskräftig',
 'GEMEINDE': 'Leipzig, Stadt', 'STANDORT': 'Mölkau', 'DAT_GENEHM': 1995-03-07,
 'DAT_BEKANN': 1995-05-04, 'ROK_NR': 3940008, 'PLANTYP': 'W',
 'INFO_VG': 'Teile von 1.Änderung überplant (2014)'}
```

Layer 2 at the same point returns `THEMA_DET: 'Wohnbaufläche (W)'`, so the
silence at Mölkau 204 is a statement, not an empty layer.

**Distance ladder**, with `distance=25…800&units=esriSRUnit_Meter`:

| Layer | 25 m | 50 | 100 | 200 | 400 | 800 m |
|---|---|---|---|---|---|---|
| in force (3) | 0 | 0 | 0 | 0 | 0 | 0 |
| in procedure (1) | 0 | 0 | 0 | 0 | 0 | 1 |
| statutes (5) | 0 | 0 | 0 | 0 | 0 | 0 |

The one hit is *V-BPlan Nr. 424 Handels- und Dienstleistungszentrum
Mölkau-Mitte* (§ 12 BauGB, im Verfahren), measured at **590 m**. The nearest
plans in force are *B-Pl. E-217* at 863 m, *E-215* at 885 m and *B-Pl. 81 Alte
Ortslage Paunsdorf* at 895 m.

**FNP at the parcel** (`RO_FNP_wirksam/1`, the same polygon query): 1 feature.

```
name: 'FNP der Stadt Leipzig, Fortschreibung', thema_det: 'Wohnbaufläche',
info_vg: 'wirksam 16.05.2015, letzte Änd.Verfahren 2023'
```

`RO_ergaenzende_Bauleitplanung/3` also hits: "INSEK Leipzig 2030,
Stadtentwicklungsgebiet", 297 km², meaning the whole city. That is not a
planning-law designation for the plot.

### 2.3 What the use layer carries, and what it does not ✅

`WMS_BPLAN/2`, grouped by `THEMA_DET` statewide, holds the Art der baulichen
Nutzung: *Allgemeines Wohngebiet (WA)* 5 320, *Gewerbegebiet (GE)* 2 251,
*Mischgebiet (MI)* 997, *Reines Wohngebiet (WR)* 416, *Dorfgebiet (MD)* 501, and
so on. There are also 35 *"überbaubare Grundstücksfläche nach §12 (3) BauGB"*,
which belong to VEPs. `INFO_OBJ` is free text such as "WA 3", "MK 3", or once
"WA, 1.Änd. westliche Baugrenze auf Flst.552".

There is **no field for GRZ, GFZ, Vollgeschosse or Bauweise, and no Baugrenze
or Baulinie geometry.** The RAPIS theme sheet (PDF, fetched from
`rapis.sachsen.de/anlagen/?ID=10638&art_param=766`) says the detailed "BPLAN
Detail" theme is "vollständig" only for Direktionsbezirk Leipzig, "Erfassung
in ROK Leipzig seit 2008", at 1:500–5 000. It is still land-use polygons.

### 2.4 Legal standing and licence 📘

From the same theme sheet:

> "Sie dienen der Erstinformation über raumrelevante Sachverhalte,
> rechtsverbindliche Auskünfte können daraus nicht abgeleitet werden. […] Das
> RAPIS dient nicht dem Vertrieb bzw. der Weitergabe der Daten."

From the Nutzungshinweise (`rapis.sachsen.de/?ID=10572&art_param=765`):

> "Für die Richtigkeit, Vollständigkeit, Vollzähligkeit, Konsistenz und
> Genauigkeit der zur Verfügung gestellten Informationen im Einzelnen wird keine
> Gewähr übernommen." — Licence dl-de/by-2-0, source credit „RAPIS Sachsen
> [Monat / Jahr]", linked to https://rapis.sachsen.de.

A download exists only on request. The record "DIGROK: Bauleitplanung (B-Pläne,
VEP, Satzungen §§34,35 BauGB) im Freistaat Sachsen (Shape-Format)" (data.europa.eu
`7cf3780a-…`) says: "Abgabe im Shape-Format bei direkter Anforderung per eMail".

### 2.5 RAPIS is not complete — measured ✅

Leipzig's own list, filtered to Ortsteil Mölkau (§ 3.1), names eight plans.
Two of them are **not in RAPIS** under any spelling tried: *E-211 Hotelkomplex
auf Flst. 102/3 Gem. Zweinaundorf* and *E-258 Kleingewerbe Flst. 512
Handwerkerhof*. Their parcels were resolved through the ALKIS WFS
(`gemaschl` 145593 / `flstnrzae` 102, and 145592 or 145593 / 512). They lie
845–909 m and 1 092–1 470 m from Flurstück 204, so they cannot cover it. But
"nach Kenntnisstand" in the record means just that. A RAPIS miss says "no
known plan", never "no plan".

All 14 plans Leipzig lists for the neighbouring Ortsteile Sellerhausen-Stünz
(whose boundary is 99.5 m from the plot) and Paunsdorf *were* found in RAPIS.
The nearest is 895 m away.

---

## 3. Stadt Leipzig

### 3.1 The B-Plan list on leipzig.de ✅ (the page) / ⚠️ (the map)

```
GET https://www.leipzig.de/rathaus/buergerbeteiligung/buergerbeteiligung-und-planinformation/bebauungsplaene
    ?tx_lepurpose[filter][91][]=59&tx_lepurpose[filtered]=1      # 59 = Ost / Mölkau
```

This is a server-rendered TYPO3 list with a filter by Ortsteil (the
`tx_lepurpose[filter][91][]` ids are in the page's own checkboxes). The page
says:

> "In der Listenansicht sind derzeit alle rechtskräftigen Bebauungspläne mit
> Stand 31.12.2024 hinterlegt. Bebauungspläne aus dem Jahr 2025 und die derzeit
> noch im Verfahren befindlichen Bebauungspläne werden nach und nach in die
> Liste eingearbeitet. […] Maßgeblich sind ausschließlich die Originalurkunden."

For Mölkau it lists eight plans: E-211, E-214, E-215 (and its 1. Änderung),
E-216, E-217, E-218 and E-258. None of them is on the Lessingweg. Each detail
page links PDFs under
`https://geodaten.leipzig.de/public/projekte/bebauungsplaene/pdf/`. Measured on
E-215: `BP_E_215.pdf` (the Planzeichnung, 6.4 MB) is **one raster image,
12 992 × 6 081 px, with no text layer, no fonts and no PDF georeference**
(no `/LGIDict`, `/Measure` or `/GPTS`; producer "Adobe Acrobat 9.0 Image
Conversion Plug-in"). Getting Baugrenzen out of it would need georeferencing
and vectorising by hand.

The page's map view and the "Karte im Vollbildmodus" link point to an ArcGIS
Experience Builder app on `geo.leipzig.de`
(`…/experience/?id=94bfdcb289be48a3b65ae846d50cc609`, webmap
`6f91bc48a17e47e4b83af840773d47e1`). ⚠️ **`geo.leipzig.de`,
`geoportal.leipzig.de`, `stadtplan.leipzig.de` and `wms.leipzig.de` could not
be reached from this sandbox.** The egress tunnel closed after about 7 s every
time, and WebFetch got 503 on `geo.leipzig.de`. The feature service behind that
map, which per the GDI-DE record for "Bebauungspläne der Stadt Leipzig,
Übersicht der Geltungsbereiche" (`096d4002-…`, dl-de/by-2-0) is an area
overview, may well be queryable. It is **not verified**, and from what the
record says it would carry areas, not content. The record's only distribution
is the WebOffice viewer
`https://stadtplan.leipzig.de/WebOffice/synserver?project=Stadtplan&client=core&user=guest`.

### 3.2 geodienste.leipzig.de ✅

- `l3/OpenData` (GeoServer). WFS GetCapabilities lists **83 feature types, none
  of them planning law**: land values 2010–2026, trees, `flurstuecke`,
  `gebaeude_alkis`, `ortsteil`, … The open-data CKAN
  (`opendata.leipzig.de/api/3/action/package_search`) has 0 hits for
  "bebauungsplan" and "xplanung". The only planning dataset there is the FNP.
- `l2/Anwendungsfaelle/flaechennutzungsplan/MapServer/WMSServer`, the FNP WMS
  from the open-data portal. Capabilities: 228 kB, about 100 layers, **none
  queryable**. `GetFeatureInfo` answers HTTP 200 with a `RequestNotAllowed`
  exception, and the REST face answers 400/403. GetMap works: at the plot the
  pixel is RGB (255, 208, 191), which is the legend's "Wohnbauflaeche" entry.
  That agrees with RAPIS.
- Guessing service names on `l2` tells nothing: a nonsense name answers the
  same 499 "Token Required" as a plausible one.

`Ortsteil` at the plot, from `l3/OpenData` `ortsteil` with a geometry test
rather than the bbox: **Mölkau** (Stadtbezirk Ost).

### 3.3 Städtebauliche Auskunft 📘

`https://www.leipzig.de/rathaus/buergerbeteiligung/buergerbeteiligung-und-planinformation/auskuenfte-und-beratung`
offers "Auskünfte über […] die planungsrechtliche Einordnung einzelner
Grundstücke" and "schriftliche Auskünfte (kostenpflichtig) zur baulichen
Nutzung von Grundstücken (städtebauliche Auskünfte)". Plans adopted after
01.09.2004 are in the Ratsinformationssystem. ⚠️ The fee (reported by a search
engine as "at least 30 €") and the address `staedtebauliche-auskunft@leipzig.de`
were not read on an official page.

### 3.4 Verdict for Lessingweg 44

- **Not in any B-Plan known to RAPIS** (plans in force or in procedure, with a
  working control) **or to Leipzig's own list** for Mölkau and the two
  neighbouring Ortsteile. The nearest plan in force is 863 m away, the nearest
  in procedure 590 m.
- **No § 34(4) or § 35(6) statute** covers it or lies within 2.3 km.
- **FNP: Wohnbaufläche.** The surroundings are continuously built up.

So § 34 BauGB is the likely regime, with **high but not binding confidence**.
The residual risks, none of which can be checked from here:

1. **A plan missing from both lists.** RAPIS demonstrably misses plans (§ 2.5),
   and Leipzig's list stops at 31.12.2024. ⚠️
2. **A pre-1990 plan still in force** (an old Baufluchtlinien- or
   Ortsbauplan): neither source would show it. ⚠️ Not researched.
3. **§ 35 instead of § 34**: whether the plot belongs to a "im Zusammenhang
   bebauter Ortsteil" is a legal judgement, not a data lookup. The outlines make
   § 35 implausible here.

Only the written städtebauliche Auskunft settles it.

---

## 4. Statewide and national XPlanung / INSPIRE PLU

### 4.1 Nothing for Saxony ✅ (as far as the catalogues show)

data.europa.eu search API (`/api/hub/search/search?q=…&filter=dataset`, country
DE), queried for "XPlanung Sachsen", "XPlanGML Sachsen", "Planned Land Use
Sachsen", "geplante Bodennutzung Sachsen", "Bodennutzung Sachsen INSPIRE",
"Bauleitplanung Sachsen" and "RAPIS":

- **No XPlanung or INSPIRE-PLU service from a Saxon body.** Hundreds exist for
  Baden-Württemberg, Brandenburg, Saarland, Schleswig-Holstein and Berlin.
- **False friends:** "WFS INSPIRE BPL Sachsen I" is the plan *Sachsen I* in
  Biberach an der Riß (served from `geodienste.komm.one`). "Sachsenäcker" and
  "Sachsenheim" are in Baden-Württemberg.
- **"INSPIRE SN Bodennutzung"** (GeoSN, `…/aaa/public_inspire/alkis/elu/dls/wfs`)
  is *existing* land use from ALKIS, classified by HILUCS. It is not planned
  land use.
- RAPIS lists 33 datasets there, and all of them are WMS or shapefiles on
  request (§ 2).

There is also no XPlanung download on the **Zentrales Landesportal
Bauleitplanung** (`buergerbeteiligung.sachsen.de/portal/bplan`, ✅ 200). It
lists *running* participation procedures with PDF documents and a JPEG teaser
(checked on the Kubschütz procedure 1068475), and nothing on plans in force.

⚠️ What a search engine reported, not read at the source: XPlanung is a
funding condition under the Saxon FRL RegioPlan. That would make new plans
exist as XPlanGML *somewhere* (at the municipality or its planning office),
but no service publishing them was found.

### 4.2 Other Saxon cities ⚠️

Chemnitz lists "Bebauungspläne Chemnitz" (DL-DE-BY-2.0, modified 2026-01-26)
on `portal-chemnitz.opendata.arcgis.com`. The hub's search API returned 0 items
and the dataset page is a client-side app, so no feature-service URL was
resolved. Dresden: nothing found in the catalogue. Neither was pursued, since
RAPIS covers both cities for plan areas anyway.

---

## 5. Baulasten

📘 § 83 Abs. 4 and 5 SächsBO (revosax, Fassung vom 11.05.2016, zuletzt geändert
01.03.2024):

> "Das Baulastenverzeichnis wird von der Bauaufsichtsbehörde geführt. […] Wer
> ein berechtigtes Interesse darlegt, kann in das Baulastenverzeichnis Einsicht
> nehmen oder sich einen Auszug erstellen lassen."

📘 Stadt Leipzig, "Baulasteintragung/-auskünfte"
(`https://www.leipzig.de/service-portal/dienstleistung/baulasteintragung-beantragen-539835c3403f4`):

- Auskunft by online application or form (`…/formular/auskunft-baulastenverzeichnis/download`),
  **22,00–70,00 € per plot**, "Bearbeitungszeit … circa vier Wochen".
- "**Kostenfreie, unverbindliche Vorinformation** — Eine Vorabauskunft darüber,
  ob eine Baulast eingetragen ist, erhalten Sie online kostenfrei. […] Wenn das
  Grundstück grün unterlegt ist, liegt eine Baulasteintragung vor. […] die zur
  Verfügung stehenden Datensätze [sind] nicht tagesaktuell."
- And directly below: "**ACHTUNG: Aufgrund einer Softwareumstellung des
  Geodaten-Service Leipzig, ist eine Auskunft über die Online-Abfrage derzeit
  nicht zuverlässig möglich. Die Baulastdaten können derzeit nicht aktualisiert
  werden.**"
- The pre-check is again a `geo.leipzig.de` Experience Builder app
  (`id=96c09f5d5e0c4ccc8f89dd909159abe9`). ⚠️ It could not be reached from this
  sandbox, so whether it sits on a queryable layer, and what that layer carries
  (a yes/no per parcel, presumably, not the content), is **not verified**.
- The page names the Abstandsflächen-Baulast (§ 6 Abs. 2 SächsBO) explicitly
  among the kinds of Baulast.

Nothing statewide was found: no Saxon Baulasten dataset in the catalogues, and
Baulasten are not part of ALKIS. Outside Leipzig the Landkreis is the
authority, on request (Landkreis Leipzig publishes a request form).

---

## 6. The statute that ties it together 📘

- § 30 Abs. 1 BauGB: a *qualified* plan fixes at least "Art und […] Maß der
  baulichen Nutzung, die überbaubaren Grundstücksflächen und die örtlichen
  Verkehrsflächen". Abs. 3: a *simple* plan falls back on § 34 or § 35 for the
  rest.
- § 34 Abs. 1 BauGB: in the Innenbereich a project must fit in "nach Art und
  Maß der baulichen Nutzung, der Bauweise und der Grundstücksfläche, die
  überbaut werden soll". So here, **the neighbours *are* the plan**: where on
  the plot a house may stand follows the surrounding buildings, and no dataset
  holds that verdict.
- § 34 Abs. 4 BauGB: statutes that fix (Nr. 1, Klarstellung), include (Nr. 2)
  or round off (Nr. 3, Ergänzung) the Innenbereich. RAPIS counts these
  statewide: § 34(4) Nr. 3: 3 029, Nr. 1: 118, Nr. 2: 29, § 35(6): 353.
  They are optional, so where none exists nothing follows.
- § 23 BauNVO: "Ist eine Baugrenze festgesetzt, so dürfen Gebäude und
  Gebäudeteile diese nicht überschreiten"; a Baulinie must be built *on*.
- § 22 BauNVO: offene Bauweise means "mit seitlichem Grenzabstand",
  geschlossene means "ohne seitlichen Grenzabstand"; a plan may also fix
  "inwieweit an die […] Grundstücksgrenzen herangebaut werden darf oder muss".
- § 6 Abs. 1 Satz 3 SächsBO: "Eine Abstandsfläche ist nicht erforderlich vor
  Außenwänden, die an Grundstücksgrenzen errichtet werden, wenn nach
  planungsrechtlichen Vorschriften an die Grenze gebaut werden muss oder
  gebaut werden darf." This is where planning law (Bauweise) switches the 3 m
  setback off, and it is the only route by which Grenzbebauung enters § 6.

---

## 7. What this means for the neighbour feature

**Can we draw real Baugrenzen from a B-Plan? No, not in Saxony today.** No
service delivers Baugrenze, Baulinie, überbaubare Grundstücksfläche (except 35
VEP areas statewide), GRZ, GFZ or storeys as data. Leipzig's plans are raster
scans without georeference. The envelope must stay the § 6 construction it is,
and must not be presented as the buildable area of a plan.

**Can we say "inside B-Plan X / probably § 34"? Yes, with care.** One request
per plot against RAPIS gives a reviewable, structured input for a
`findings.js` template:

```
GET https://rapis.ipm-gis.de/arcgis/rest/services/WMS_BPLAN/MapServer/3/query
    ?geometry=<parcel ring, EPSG:25833, clockwise>&geometryType=esriGeometryPolygon
    &inSR=25833&spatialRel=esriSpatialRelIntersects
    &outFields=NAME,STATUS,PLANTYP,RECHTSGRL,DAT_BEKANN,DAT_RAPIS&returnGeometry=false&f=json
```

Then the same against layer 1 (in procedure, which is worth a line: a plan can
be coming), layer 5 (statutes) and `RO_FNP_wirksam/1`. The honest wordings are:

- A hit: "Liegt im Geltungsbereich von <NAME> (rechtskräftig seit
  <DAT_BEKANN>, laut RAPIS Sachsen)", with the name linking to the plan where
  the municipality publishes one. For Leipzig the list page is searchable by
  name, but there is no stable ID mapping from RAPIS to leipzig.de.
- No hit: "In RAPIS ist hier kein Bebauungsplan verzeichnet. Wahrscheinlich
  gilt § 34 BauGB (Einfügen in die Umgebung) — verbindlich klärt das eine
  städtebauliche Auskunft der Gemeinde." Never "kein B-Plan": § 2.5 measured
  that RAPIS misses plans. Add the FNP designation as context, not as a
  permission.
- This is a *designation* in the CLAUDE.md sense: a yes/no, so the text is a
  yes or a no, qualified by its source. It also needs the control-point test
  `services.md` asks for; the E-215 point in § 2.2 serves.
- Cost: one small JSON request per layer. The server sends no `Retry-After` and
  has no documented quota. It is the Landesdirektion's own public service under
  dl-de/by-2-0, and the credit „RAPIS Sachsen [Monat/Jahr]" must be shown.
  ⚠️ CORS headers were not checked; go through the backend proxy and disk cache
  like every other authority service.

**Can we say anything about Bauweise / Grenzbebauung? Only in words, never
computed.** Inside a plan, the plan decides (§ 22 BauNVO), and we cannot read
it. Under § 34 the surroundings decide. The ALKIS outlines we already fetch
could *describe* the street ("die Nachbargebäude stehen überwiegend mit
seitlichem Abstand"), and that would be an observation, not a Bauweise.
§ 6 Abs. 1 Satz 3 means a permitted Grenzbebauung *removes* the 3 m strip on
that side, and nothing available tells us when it applies. So the setback
drawing should keep its "vereinfacht, Bauaufsicht entscheidet" wording and gain
the plan line above, rather than a Bauweise claim.

**Baulasten: not automatable.** There is no dataset. Leipzig's free map
pre-check exists, is flagged unreliable by the city itself, and sits on a host
this sandbox cannot reach. The feature can say that a Baulast (for example an
Abstandsflächen-Baulast under § 6 Abs. 2) may encumber the plot and is only
visible in the Baulastenverzeichnis: Leipzig, Amt für Bauordnung und
Denkmalpflege, 22–70 €, about four weeks, berechtigtes Interesse required. It
can link the city's service page. A green/grey answer from the pre-check would
need a second look once `geo.leipzig.de` is reachable, and even then only as
"laut unverbindlicher Vorabauskunft".

**Open, worth an hour from a network that reaches `geo.leipzig.de`:** the
feature services behind the B-Plan map (webmap `6f91bc48…`) and the Baulast
pre-check (`96c09f5d…`). The first could replace RAPIS for Leipzig with the
city's own, more complete areas. The second could give a per-parcel yes/no.
