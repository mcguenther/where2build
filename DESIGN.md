# Gestaltung — where2build

Diese Datei hält fest, was gilt und warum. Sie ist die Fortschreibung von
`farben.css` und `farbschema.html`; wo die beiden etwas sagen, gilt deren Wert
unverändert. Was hier darüber hinaus steht, füllt Lücken, die dort offen blieben.

Sprachregelung im ganzen Projekt: **Quelltext auf Englisch, Oberfläche auf Deutsch.**
Diese Datei beschreibt die Oberfläche und ist deshalb deutsch; `README.md` und
`CLAUDE.md` richten sich an Entwickelnde und sind englisch.

---

## Die Idee in einem Satz

Loden und Messing auf Creme: die Farbwelt eines eingesessenen Maklerbüros mit
Eichenboden, ohne die Ornamente. Modern wird es durch Zurückhaltung — viel
Creme, wenig Farbe, klare Kanten, großzügige Abstände.

## Rollenlogik der Farbe

Das ist die wichtigste Regel des Schemas, und sie entscheidet jede Einzelfrage:

| Rolle | Farbe | Was damit gemeint ist |
|---|---|---|
| Neutral | Tinte, Graphit, Gedämpft | alles Amtliche — Flurstücksgrenzen, Bestandsgebäude, Katasterangaben |
| Loden | Primär | alles, was das Werkzeug **berechnet** — Bebauungsfenster, Kennzahlen, Schaltflächen |
| Messing | Sekundär | alles, was der Nutzer **selbst entwirft** — der Hauskörper, eigene Maße |
| Ziegelrot | Fehler | Abstandsverstoß, fehlende Pflichtangabe |

Wer eine Farbe wählen muss, fragt zuerst: Ist das amtlich, berechnet oder entworfen?

## Was ergänzt wurde

`farben.css` beschreibt den hellen Modus vollständig und den dunklen nur in
Auszügen. Ergänzt wurden:

**Dunkelmodus vollständig.** Der mitgelieferte Block setzt zehn Werte; die
übrigen — Messing, Salbei, alle Kartenebenen, Signalfarben, Schleier — fehlten
und hätten im Dunkeln ihre hellen Werte behalten. Sie sind jetzt gesetzt.
Messing wird dabei angehoben (`#D9A55E`), weil `#B5813C` auf dunklem Grund
absäuft; die Textvariante bleibt getrennt geführt.

**Zwei Wege in den Dunkelmodus.** `farben.css` schaltet nur über
`prefers-color-scheme`. Weil die Oberfläche einen eigenen Umschalter hat, sind
alle dunklen Werte zusätzlich unter `[data-theme="dark"]` definiert, und der
Medienblock ist als `:root:not([data-theme="light"])` abgesichert — sonst
gewinnt die Systemeinstellung gegen die ausdrückliche Wahl des Nutzers.
Keine Farbe ist ausschließlich hinter einer Medienabfrage definiert.

**Abstände und Schriftgrößen.** Eine Skala mit einem Schritt je Größenordnung,
keine Zwischenwerte — dieselbe Begründung wie bei den Eckenradien.

## Schrift

Drei Familien, über Fontsource aus npm gebündelt — nichts kommt von einem CDN.

| Rolle | Familie | Schnitte | Einsatz |
|---|---|---|---|
| Anzeige | Archivo | 400 · 600 · 700 | Überschriften, Schaltflächen, Spaltenköpfe, Marke |
| Fließtext | Public Sans | 400 · 500 · 600 | Absätze, Beschreibungen, Formularbeschriftungen |
| Daten | IBM Plex Mono | 400 · 500 | Zahlen, Koordinaten, Kennzeichen, Endpunkte |

Zwei Sonderfälle bei Archivo, beide aus `farbschema.html` übernommen:
Überschriften laufen mit **negativer** Laufweite (−0,028 em bei h1), kleine
Abschnittsmarken dagegen mit **weiter** Laufweite (+0,11 em) in Versalien.

Zahlen, die untereinander stehen, brauchen `font-variant-numeric: tabular-nums`.
Ohne das tanzen die Nachkommastellen in jeder Tabelle.

## Flächen und Kanten

Kein Karomuster im Hintergrund. Der Seitengrund ist ruhiges Creme
(`--w2b-papier`), Panels stehen eine Spur heller darauf (`--w2b-flaeche`),
getrennt durch eine warme Linie. Tiefe entsteht durch diese Staffelung, nicht
durch Schlagschatten — Schatten kommen nur dort vor, wo etwas wirklich über der
Seite schwebt.

Ein Radius je Größenordnung, wie in `farben.css` vorgegeben. Bei geschachtelten
Elementen gilt: innerer Radius = äußerer minus Innenabstand.

## Die Karte

Vier Gründe zur Wahl: **Ohne, Karte, Luftbild, Kataster.** „Ohne" zeichnet den
Plan auf leeres Papier — das ist kein Notbehelf, sondern die Ansicht, in der
nur zählt, was das Kataster sagt. Die drei anderen legen echte Daten darunter:
die Vektorkarte von OpenFreeMap, das Orthofoto und die Katasterdarstellung des
GeoSN. Ohne Koordinate sind sie gesperrt, denn es gibt nichts, worauf man den
Plan legen könnte, und ein Hintergrund, der nicht deckungsgleich ist, wäre
schlimmer als keiner.

Jeder Hintergrund läuft über das eigene Backend, nie direkt zum Kachelserver.
Das ist eine Gestaltungsentscheidung so gut wie eine technische: die Anwendung
funktioniert hinter einer Firewall, in der der Browser nur diesen einen Server
erreicht, und der Nutzer merkt keinen Unterschied.

Die Kartenfläche bleibt neutral (`--w2b-karte-grund: #E6E3DC`), nicht creme.
Warme Untergründe konkurrieren mit Luftbild und Katasterdarstellung und machen
Grenzen schlechter lesbar. Warm ist die Oberfläche drumherum.

Jede Linie auf der Karte trägt einen Halo in `--w2b-karte-halo`, 4–5 px. Ohne
ihn verschwinden Grenzen im Orthofoto.

**Abstandsflächen werden als Randstreifen markiert, nicht als bebaubarer
Bereich.** Der Streifen zwischen Flurstücksgrenze und Bebauungsfenster ist
eingefärbt; die Fläche, auf der gebaut werden darf, behält den normalen
Kartengrund. Technisch ein Pfad aus Außen- und Innenring mit
`fill-rule="evenodd"`. Das ist eine ausdrückliche Entscheidung: markiert wird,
was verboten ist, nicht was erlaubt ist.

## Druck

Es gibt **keine eigene Druckansicht**. Die Seite, die am Bildschirm steht, ist
die Seite, die gedruckt wird — `print.css` blendet aus, was auf Papier nicht
hingehört, und ordnet den Rest neu. So gibt es keinen zweiten Renderpfad, der
dieselben Maße noch einmal berechnen müsste.

Was im Druck gilt:
- **A4 hoch** für die Grundstücksseite — eine Seite, zwei sobald Wege gerechnet
  sind; `break-after: page` je Kandidat im Vergleich
- Navigation, Umschalter, Regler und Schaltflächen verschwinden
- `print-color-adjust: exact`, sonst fallen die Flächenfarben weg
- Nordpfeil und Maßstabsleiste bleiben sichtbar — bei gedrehter Karte sind sie
  das Einzige, was die Orientierung rettet
- Quellenangabe und der Hinweis, dass dies keine bauordnungsrechtliche Prüfung
  ist, stehen in der Fußzeile
- Formularschmuck verschwindet: keine Zahlenfeld-Pfeile, keine Rahmen, keine
  Fokusringe. Die Abstandstiefen lesen sich als Werte in einer Tabelle, mit
  ihrer Einheit — nicht als Bedienelemente, die auf Papier nichts tun
- Kein Panel bricht mitten durch: jede Tafel, Tabellenzeile und Wegekarte trägt
  `break-inside: avoid`, damit die Seite an einer Kante umbricht, nicht im Satz

Zwei Fallen, die das gekostet hat: Komponentenstile sind **scoped** und tragen
darum ein `[data-v-…]`-Attribut — eine nackte Klasse in `print.css` verliert
gegen sie, weshalb dort jede Layoutregel `!important` braucht. Und die Hülle ist
eine `100vh`-Flexspalte; auf Papier ist `100vh` genau ein Blatt, und die Fußzeile
landete auf einem eigenen.

## Bewegung

Sparsam. Übergänge nur dort, wo sie einen Zustandswechsel erklären: das
Ausklappen eines Abschnitts, der Wechsel eines Assistentenschritts. Beim Laden
bewegt sich nur eines: ein Platzhalter an der Stelle des Kommenden pulsiert
ruhig (`w2b-pulse`), damit das Warten nicht wie ein leerer Rahmen aussieht —
in der Prüfliste, bei den Wegekarten und in den Vorschaubildern der
Grundstücke. Was fertig ist, erscheint in einem Zug, nie Stück für Stück.
`prefers-reduced-motion` schaltet alles ab.

## Sprache in der Oberfläche

Deutsch, knapp, ohne Fachjargon aus der Technik. Der Nutzer verwaltet
*Grundstücke*, keine *Records*. Eine Schaltfläche sagt, was passiert
(„Grundstück hinzufügen“), und die Rückmeldung sagt, was passiert ist.

Fehlermeldungen nennen die Ursache und den nächsten Schritt, ohne Entschuldigung.
Nicht „Fehler beim Laden“, sondern „Der Katasterdienst antwortet nicht. Das
Flurstück lässt sich auch von Hand eintragen.“

Amtliche Begriffe bleiben amtlich: Flurstück, Gemarkung, Bodenrichtwert,
Abstandsfläche. Sie sind das Vokabular der Sache, nicht Jargon.

Wo der Nutzer eine amtliche Angabe eintippen soll, steht daneben, wie sie
aussieht — die Flurstücksnummer „so, wie sie im Geoportal steht: 85/1, 476
oder 41/e". Das Geoportal zeigt denselben Gemarkungsschlüssel je nach Ebene
vier- oder sechsstellig; beide werden angenommen, ohne dass jemand den
Unterschied kennen muss.

**Der Quelltext dagegen ist durchgehend Englisch** — Bezeichner, Funktionsnamen,
Kommentare. Deutsch ist die Oberfläche, nicht der Code. Die einzige Ausnahme
sind die Feldnamen der Schnittstellen (`gemarkung`, `flaeche_amtlich_m2`,
`bodenrichtwert`): sie sind das Vokabular der Ämter und damit Daten, keine
selbstgewählten Namen.

## Nie erfundene Daten

Die härteste Regel im Projekt, und die, gegen die am leichtesten verstoßen wird.

Es gibt **keine Beispieldaten** — keinen Startzustand mit vier hübschen
Grundstücken, keine Rückfallebene, wenn ein Dienst schweigt. Wer die Anwendung
zum ersten Mal öffnet, sieht einen leeren Zustand mit genau einer Handlung.
Antwortet ein Dienst nicht, steht dort seine Fehlermeldung und ein Weg weiter,
nicht ein Platzhalter, der wie ein Ergebnis aussieht.

Das gilt auch für Zeichnungen. Die Wegekarten zeigten einmal ein aus IDs
gesätes Straßennetz mit einer erfundenen Route darin — hübsch und vollständig
gelogen. Sie zeigen jetzt die Geometrie, die der Routendienst liefert, oder
gar nichts.

**Eine abgeleitete Größe mit fehlender Eingabe bleibt ein Gedankenstrich.**
Ein Grundstück aus ALKIS hat Fläche und Grenzen, aber keinen Angebotspreis —
den kennt nur das Inserat. Wird trotzdem gerechnet, kommt „0,00 €" und
„−100 % unter dem Bodenrichtwert" heraus, und das liest sich wie ein Befund,
nicht wie eine Lücke.

## Wo ein Dienst unscharf ist, entscheidet der Mensch

Der Routing-Geocoder findet zu „Bahnhof Wurzen" auch Würenlos im Aargau, und zu
„Am Kirschberg" ein Dorf in Niederbayern. Solche Dienste liefern keinen Treffer,
sondern Kandidaten — also zeigt die Oberfläche Kandidaten: bis zu fünf, jeder
mit Postleitzahl, Ort **und Bundesland**, denn genau daran erkennt man den
Fehlgriff. Der beste Vorschlag steht oben, ausgewählt wird er nicht von selbst.

Dasselbe gilt für ein Flurstück, das über eine Adresse gefunden wurde: eine
Stadtteiladresse landet auf dem Feld nebenan. Was nicht sicher ist, wird als
unsicher gezeigt.

## Antwortzeit ist Gestaltung

Ein Plan, der beim Öffnen eine halbe Minute steht, ist kein langsamer Plan,
sondern ein kaputter — der Browser bietet an, das Skript anzuhalten, und der
Nutzer glaubt, die Anwendung sei abgestürzt. Echte Flurstücke sind mitunter
34 000 m² groß und haben 159 Grenzpunkte; die Zeichnung muss auch dann in
Sekundenbruchteilen stehen.

Wo eine Näherung nötig wird, um das zu halten, geht sie immer zur strengeren
Seite: das Bebauungsfenster darf kleiner ausfallen als das Gesetz erlaubt,
niemals größer.

## Kurz, wo es eng ist

Eine Wegekarte ist 292 px breit. „Für dieses Ziel wurde keine Verbindung
gefunden." bricht dort auf vier Zeilen und schiebt die Fahrzeiten aus dem Bild.
In der Karte steht „keine Verbindung"; der ganze Satz bleibt im `title`. Text
wird für seinen Platz geschrieben, nicht einmal für alle Plätze.

## Zwei Arten von Schweigen

Eine leere Liste kann zweierlei heißen, und die zu verwechseln wäre gelogen:
*hier gibt es nichts* oder *danach wurde gar nicht gesucht*. Die Umgebungstafel
sagt beides getrennt — „Nichts gefunden für S-Bahn" gegen „Kein Datenbestand
für Schule, Kita, Park … Das heißt nicht, dass es dort nichts gibt."

Das gilt überall, wo ein Dienst nur teilweise antwortet: was nicht abgefragt
wurde, ist `null`, nicht `[]`.

## Entfernung heißt Fußweg

In der Umgebungstafel steht die Gehzeit vorn und die Weglänge daneben, die
Luftlinie nur im `title`. Eine Schule 400 m entfernt, aber jenseits der
Bahnlinie, ist ein Kilometer Weg — und an einem Ufergrundstück ist das nach
Luftlinie Nächstgelegene mitunter überhaupt nicht zu Fuß erreichbar. Sortiert
wird deshalb nach dem, was man geht, nicht nach dem, was man misst.

## Eine Haltestelle ist ihre Linie

„Bus" ist eine Kategorie, „143" ist das, womit jemand tatsächlich fährt. Unter
jedem Halt stehen deshalb die Liniennummern aus dem Fahrplan als kleine Marken
in der Schreibmaschinenschrift der Tafel — und zwar nur die der Verkehrsmittel,
für die der Halt überhaupt in der Liste steht: Die Buslinien an einer
Straßenbahnhaltestelle machen sie nicht zur Bushaltestelle.

Auf der Umgebungskarte erscheinen die Linien erst beim Überfahren, neben Namen
und Gehzeit. Immer sichtbar bleibt allein die Kategorie — sechs Halte in einem
Dorf würden mit ihren Nummern genau das zudecken, wofür die Karte da ist.

Wurden die Linien nicht abgefragt — der Server hört nach einer festen Zahl von
Halten damit auf —, steht das an der Zeile. Eine leere Zeile sähe aus wie „hier
fährt nichts", und das ist die eine Aussage, die niemand treffen darf.

## Was extrahiert wurde, ist ein Vorschlag

Werte, die ein Modell aus einer Seite gelesen hat, erscheinen sichtbar anders
als bestätigte: gestrichelter Rahmen in Messing, die Marke „automatisch
gelesen“, und darunter die Quelle, aus der der Wert stammt. Erst nach
Bestätigung wechseln sie auf durchgezogene Linie in Neutral.

Findet das Modell nichts, bleibt das Feld leer und wird in Ziegelrot als „nicht
belegt“ markiert — geraten wird nicht.
