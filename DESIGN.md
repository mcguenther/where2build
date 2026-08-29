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
- A4 quer für die Grundstücksseite, `break-after: page` je Kandidat im Vergleich
- Navigation, Umschalter, Regler und Schaltflächen verschwinden
- `print-color-adjust: exact`, sonst fallen die Flächenfarben weg
- Nordpfeil und Maßstabsleiste bleiben sichtbar — bei gedrehter Karte sind sie
  das Einzige, was die Orientierung rettet
- Quellenangabe und der Hinweis, dass dies keine bauordnungsrechtliche Prüfung
  ist, stehen in der Fußzeile jeder Seite

## Bewegung

Sparsam. Übergänge nur dort, wo sie einen Zustandswechsel erklären: das
Ausklappen eines Abschnitts, der Wechsel eines Assistentenschritts. Nichts
bewegt sich beim Laden. `prefers-reduced-motion` schaltet alles ab.

## Sprache in der Oberfläche

Deutsch, knapp, ohne Fachjargon aus der Technik. Der Nutzer verwaltet
*Grundstücke*, keine *Records*. Eine Schaltfläche sagt, was passiert
(„Grundstück hinzufügen“), und die Rückmeldung sagt, was passiert ist.

Fehlermeldungen nennen die Ursache und den nächsten Schritt, ohne Entschuldigung.
Nicht „Fehler beim Laden“, sondern „Der Katasterdienst antwortet nicht. Das
Flurstück lässt sich auch von Hand eintragen.“

Amtliche Begriffe bleiben amtlich: Flurstück, Gemarkung, Bodenrichtwert,
Abstandsfläche. Sie sind das Vokabular der Sache, nicht Jargon.

## Was extrahiert wurde, ist ein Vorschlag

Werte, die ein Modell aus einer Seite gelesen hat, erscheinen sichtbar anders
als bestätigte: gestrichelter Rahmen in Messing, die Marke „automatisch
gelesen“, und darunter die Quelle, aus der der Wert stammt. Erst nach
Bestätigung wechseln sie auf durchgezogene Linie in Neutral.

Findet das Modell nichts, bleibt das Feld leer und wird in Ziegelrot als „nicht
belegt“ markiert — geraten wird nicht.
