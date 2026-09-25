# Routing über Sachsen hinaus

Stand 25.09.2026. **Offen, nicht gebaut.** Die Karten reichen seit
`claude/optimistic-bohr-6ozgjt` über ganz Deutschland (Luftbild der Länder,
basemap.de unter den Routenkarten). Das Routing selbst endet weiterhin an der
Landesgrenze. Diese Notiz hält fest, warum, und wie es zu lösen wäre.

---

## 1 · Was heute gilt (gemessen bzw. im Code nachgelesen)

| Baustein | Quelle | Reicht bis |
|---|---|---|
| Straßennetz des eigenen MOTIS | `sachsen-latest.osm.pbf` von Geofabrik (`backend/scripts/fetch_routing_data.py`, `DEFAULT_OSM_URL`) | Sachsen |
| Fahrplan | DELFI-GTFS über Transitous, `de_DELFI.gtfs.zip`, **317 325 802 Byte** (am 25.09.2026 per Range-Request gemessen) | Deutschland |
| Geocoding der Ziele | 1. amtliche Hauskoordinaten des GeoSN, 2. MOTIS-Geocoder (`backend/app/routers/geocode.py`) | Sachsen; der MOTIS-Geocoder kennt nur, was im OSM-Auszug steht |
| POI-Index „In der Umgebung“ | derselbe Sachsen-Auszug (`build_poi_index.py`) | Sachsen |
| Transitous-Variante | `docker-compose.transitous.yml`, setzt `MOTIS_BASE_URL=https://api.transitous.org` | Europa |

Für ein Ziel außerhalb Sachsens folgt daraus beim eigenen MOTIS:

- Auto, Rad und Fußweg finden keinen Weg, weil das Straßennetz fehlt.
- ÖPNV findet Haltestellen und Fahrten, aber keinen Weg von der letzten Haltestelle zum Ziel.
- Eine Adresse außerhalb Sachsens wird gar nicht erst gefunden: Beide Geocoder kennen nur Sachsen.

Der Kommentar in `fetch_routing_data.py` („the app never routes beyond the
state“) beschreibt diese Grenze als Absicht. Mit dieser Aufgabe würde sie
aufgehoben.

## 2 · Wege

**A · Transitous für alles.** Das gibt es schon, nur eine Compose-Datei mehr.
Transitous ist aber ein Freiwilligendienst: Die Nutzungsrichtlinie schließt
kommerzielle Nutzung aus und stuft Routing als ressourcenintensiv ein
(`docs/research/routing-motis.md` § 6). Zum Ausprobieren gut, als Standard für
andere Leute nicht.

**B · Deutschland-Auszug im eigenen MOTIS.** Den Download-Pfad kann man schon
heute per `W2B_OSM_URL=https://download.geofabrik.de/europe/germany-latest.osm.pbf`
umstellen, Code ist dafür nicht nötig. Der Haken sind die Kosten. Für Sachsen
sind gemessen: ~7 min Import, 5,6 GiB Spitze und 3,4 GB Graph (CLAUDE.md,
`docker-compose.yml`). Der Deutschland-Auszug ist grob fünfzehnmal so groß; das
ist **geschätzt, nicht gemessen**, weil Geofabrik aus der Sandbox nicht
erreichbar war. Zu rechnen ist mit einem Vielfachen an Arbeitsspeicher, Platte
und Importzeit, `with_shapes` (Linienverläufe über OSM) kostet zusätzlich.

**C · Sachsen plus Randstreifen.** Aus dem Deutschland-Auszug schneidet
`osmium extract` Sachsen mit etwa 50–80 km Rand heraus (Halle, Gera, Cottbus,
Hof), das Ergebnis ist `osm.pbf`. Das deckt die realistischen Pendelziele, und
der Import bleibt nahe an den heutigen Zahlen. Die Grenze wandert damit nur
nach außen und verschwindet nicht.

**D · Hybrid: eigener MOTIS innen, Transitous außen.** Das Backend entscheidet
pro Anfrage anhand der Ausdehnung des Auszugs: Liegt ein Ziel außerhalb, geht
die Anfrage an Transitous. Der Cache ist schon heute nach Instanz geschlüsselt
(`docker-compose.transitous.yml`, letzter Absatz), deshalb vermischen sich die
Antworten nicht. Die meisten Anfragen bleiben lokal, für die wenigen
Fernziele gelten die Transitous-Bedingungen.

## 3 · Wie ich es lösen würde

1. **Erst messen, dann entscheiden.** Auf einer Maschine mit genug Speicher
   einmal den Deutschland-Import fahren und Spitzen-RSS, Dauer, Graphgröße und
   den Aufschlag für `with_shapes` ablesen, genau wie am 01.09.2026 für Sachsen
   (`docs/research/routing-motis.md` § 5). Parallel C mit `osmium extract`
   messen. Die Zahlen gehören in die Recherche-Notiz, nicht in eine Schätzung.
2. **Wahl nach den Zahlen:**
   - Passt B auf die Zielmaschine, dann B. Das ist eine Konfigurationsänderung:
     Standard-URL in `fetch_routing_data.py` und `build_poi_index.py`, Kommentar
     und die Speicherangaben in `CLAUDE.md`, `README.md` und `docker-compose.yml`
     anpassen.
   - Passt B nicht, dann C als Standard und D für den Rest.
3. **Für D:**
   - Die Ausdehnung des Auszugs wird eine Einstellung (`MOTIS_EXTRACT_BBOX`,
     beim Import aus dem Auszug gelesen, nicht von Hand gepflegt).
   - `services/motis.py` wählt die Instanz pro Ziel.
   - Die Routenkarte nennt, wer gerechnet hat. Die Zeile „Berechnet … · MOTIS /
     Transitous“ gibt es schon, sie muss dann die tatsächliche Instanz angeben.
   - Ohne `APP_CONTACT` geht nichts an Transitous. Das Ziel bekommt dann einen
     deutschen Hinweis statt einer stillen Lücke.
4. **Geocoding mitziehen.** Mit B oder C findet der eigene MOTIS-Geocoder auch
   Adressen außerhalb Sachsens. Bei D muss auch der Geocoder für ein Ziel
   außerhalb Transitous fragen, sonst kommt man gar nicht bis zur Route. Der
   amtliche Adressindex bleibt Sachsen.
5. **Tests:** eine aufgezeichnete echte Antwort für eine Route Leipzig → Halle
   (Saale) in `backend/tests/fixtures/`, dazu je ein Test pro Fall: Ziel innen,
   Ziel außen, Ziel außen ohne `APP_CONTACT`. Keine erfundenen Zahlen.
6. **Nicht vergessen:**
   - Der POI-Index („In der Umgebung“) kann in Sachsen bleiben. Er beschreibt
     die Umgebung eines sächsischen Grundstücks und hängt nicht am Routing.
   - Die Routenkarten zeichnen ihren Grund schon deutschlandweit, dort ist
     nichts zu tun.

## 4 · Offene Fragen an den Betreiber

- Wie viel Speicher und Platte hat die Zielmaschine? Davon hängt ab, ob B geht.
- Ist die Instanz nicht kommerziell? Nur dann kommen A oder D überhaupt in
  Frage.
