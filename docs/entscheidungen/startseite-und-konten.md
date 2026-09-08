# Startseite und Konten

Stand 08.09.2026. Geplant, nicht gebaut. Vier Entscheidungen sind getroffen
(unten jeweils als **Entschieden** markiert), der Rest ist Vorschlag.

Heute ist die Startseite die Liste „Meine Grundstücke“ (`PlotsView`), alle
Daten liegen in `localStorage` unter `where2build.v1`, es gibt kein Konto und
keine Datenbank. Das Ziel: mehrere Nutzer mit Anmeldung, eine Suchmaske im
Vordergrund, und darunter für Angemeldete ein Bereich, der zum Fortsetzen
einlädt.

---

## 1 · Die Startseite

**Entschieden: eine Route, zwei Zustände.** `/` zeigt immer dasselbe Gerüst;
was darunter steht, hängt daran, ob jemand angemeldet ist.

```
┌───────────────────────────────────────────────┐
│  Wo soll gebaut werden?                       │   Titel + ein Satz
│  ┌─────────────────────────────────────────┐  │
│  │ 🔍  Adresse, Flurstück, Link, Anzeige … │  │   ein Feld
│  └─────────────────────────────────────────┘  │
│  [Adresse ×] Koordinate · Flurstück · Link …  │   Chips: erkannt / setzbar
│  Erkannt als Adresse. Bleiben zwei Lesarten … │   der Satz von heute
├───────────────────────────────────────────────┤
│  Weitermachen                    Alle ansehen │   nur angemeldet und
│  ┌────────┐ ┌────────┐ ┌────────┐             │   nur wenn es etwas gibt
│  │ Karte  │ │ Karte  │ │ Karte  │             │   3 zuletzt geänderte
│  └────────┘ └────────┘ └────────┘             │   PlotCard, unverändert
└───────────────────────────────────────────────┘
```

- **Abgemeldet gibt es keine Bereichsnavigation**, weil es nichts zu
  navigieren gibt: statt der Kopfzeile der App trägt der Empfang die Marke
  selbst, und die Seite oberhalb der Falz ist eine Begrüßung — ein Satz, das
  Feld, und daneben ein Lageplan, der zeigt, was am Ende herauskommt. Darunter
  der Erklärblock, den heute die `.empty-card` trägt, plus ein Satz dazu, was
  ein Konto bringt. Kein Zwang — ohne Anmeldung funktioniert alles weiter wie
  heute, lokal.
- **Der Plan steht dort, wo unten kein Bild folgt** — abgemeldet und im leeren
  Konto. Wer schon Grundstücke hat, sieht sie als Karten; ein zweites Blatt
  darüber wäre Doppelung, und verkleinert wird es unleserlich.
- **Eine angefangene Suche wird nicht angeboten.** Dafür gäbe es keinen
  gespeicherten Zustand, und ihn zu erfinden hieße, einen zu bauen.
- **Angemeldet und noch nichts gespeichert**: derselbe Erklärblock. Ein
  „Weitermachen“ mit null Karten wird nicht gezeigt, und schon gar nicht mit
  erfundenen (siehe „Never show example data“).
- **Die Liste „Meine Grundstücke“ zieht um** auf `/grundstuecke`
  (Route `plots`, `meta.section` unverändert, damit die Navigation weiter
  hervorhebt). `/` wird die neue Route `home`. Der Vergleichsmodus, die
  Auswahlleiste und `PlotCard` bleiben, wo sie sind.
- **Die Auswahl ist kein Signal.** „Weitermachen“ sortiert nach
  `updated_at`, nie nach `state.data.selection` — `addPlot` legt jedes neue
  Grundstück dort ab, das sagt über Absicht nichts aus.

## 2 · Das eine Feld mit Chips

**Entschieden: ein Feld, das seine Lesart anzeigt, und Chips, die sie
überschreiben.** Die fünf Radio-Knöpfe im Wizard-Schritt „Quelle“ verschwinden
als Vorab-Entscheidung.

`lib/queryInput.js` liest heute schon Adresse, Koordinate, Flurstücksnummer und
AdV-Schlüssel — ohne eine einzige Abfrage, und das bleibt die Regel: erst
lesen, dann nachschlagen. Dazu kommen drei Lesarten, alle ebenso billig:

| Lesart | Erkannt an | Chip |
|---|---|---|
| `address`, `coordinate`, `parcel` | wie heute | Adresse · Koordinate · Flurstück |
| `url` | beginnt mit `http://`/`https://` | Link zur Anzeige |
| `page` | Einfügen führt `text/html` mit (`@paste`) | Eingefügte Anzeige |
| `prose` | lang, mehrzeilig, keins der obigen | Beschreibungstext |

Zwei Dinge stehen nicht im Feld und bleiben deshalb Chips, die etwas
aufklappen:

- **Gemarkung + Flurstücksnummer** — zwei Felder, `CadastralDistrictPicker`
  unverändert. Wer „204“ tippt, bekommt den Chip ohnehin vorgeschlagen: eine
  nackte Nummer ist heute schon `kind: "parcel"` ohne Gemarkung, und der Satz
  darunter sagt bereits, welche Hälfte fehlt.
- **Beschreibungstext vs. eingefügte Anzeige** — unterscheidbar allein daran,
  ob die Zwischenablage HTML mitführte. Wer den Text aus einem PDF kopiert,
  landet bei `prose` und kann auf `page` nicht umstellen, weil es kein HTML
  gibt; umgekehrt schon.

Ein angeklickter Chip **setzt** die Lesart fest, bis das Feld geleert wird —
sichtbar am `×` im Chip. Das ist der Unterschied zur reinen Erkennung: „als
Beschreibungstext lesen“ muss möglich sein, ohne dass die nächste Eingabe die
Entscheidung erbt.

Technisch: eine neue Komponente `QueryBox.vue`, die Startseite und
Wizard-Schritt 1 gemeinsam nutzen. Sie gibt ein Ereignis mit
`{ kind, text, html, gemarkung, parcelNumber }` heraus; die Startseite legt das
in den Store und schickt in den Wizard, **nicht** in die URL — eine eingefügte
Seite sind bis zu 400 000 Zeichen. `PlotSearch.vue` bleibt darin als das
Vorschlagsfeld für Adressen erhalten; die Chips liegen darum herum.

Damit ist die heutige „Quelle“-Seite fast leer. Vorschlag: Schritt 1 des
Wizards *ist* die `QueryBox`, mit denselben Hinweistexten, und wer von der
Startseite kommt, sieht sie schon ausgefüllt und läuft direkt in die Suche.

## 3 · Anmeldung über OIDC

**Entschieden: OIDC.** Vorschlag für das Wie:

- **Das Backend spricht OIDC, der Provider ist Konfiguration.**
  `OIDC_ISSUER`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`. Damit ist es egal, ob
  dahinter ein selbst gehostetes Authentik steht, Keycloak, oder Google —
  entschieden wird beim Betreiben, nicht im Code. Für `docker compose` kommt
  Authentik als eigenes Profil dazu (wie `scheduled-jobs` heute), damit
  `docker compose up` weiterhin zwei Dienste bleibt.
- **Authorization Code mit PKCE, aber im Backend** (BFF-Muster). Der Browser
  bekommt nie ein Token, sondern ein `HttpOnly; Secure; SameSite=Lax`-Cookie.
  Access- und Refresh-Token liegen serverseitig in der Sitzungszeile. Das passt
  zur bestehenden Architektur: nginx bedient Frontend und `/api` unter einem
  Origin, es gibt also keine CORS-Frage und keinen Grund, ein Token in
  `localStorage` zu legen. `state` und `nonce` werden geprüft, `redirect_uri`
  ist fest.
- **Vier Endpunkte:** `GET /api/auth/login` (Weiterleitung),
  `GET /api/auth/callback`, `POST /api/auth/logout`, `GET /api/auth/me`.
- **Ohne konfigurierten Provider läuft alles weiter.** `/api/auth/me` antwortet
  dann „keine Anmeldung eingerichtet“, die Oberfläche bleibt im lokalen Modus,
  und `/api/health` sagt es — genau wie bei Tesseract heute. Sonst wäre jede
  Entwicklungsumgebung erst nach einem Identity-Provider benutzbar.
- **Gespeichert wird das Minimum:** `issuer`, `subject`, ein Anzeigename.
  Keine Adresse, keine Telefonnummer. Die E-Mail nur, wenn sie für etwas
  gebraucht wird — heute wird sie für nichts gebraucht.

## 4 · Server und lokal parallel

**Entschieden: beides, mit Übernahme beim ersten Login.**

- **Postgres** (PostGIS war ohnehin geplant). Eine Zeile *pro Grundstück*,
  nicht ein Dokument pro Nutzer: „zuletzt geändert“ braucht ein
  `ORDER BY updated_at`, und ein Konflikt soll ein Grundstück betreffen, nicht
  den ganzen Stand. Der Inhalt bleibt das heutige Schema als `jsonb`, mit
  `schema_version` daneben — dann gilt die vorhandene Validierung und Migration
  unverändert für beide Wege.
  Tabellen: `users`, `plots`, `house_types`, `destinations`, `sessions`.
- **`lib/store.js` bekommt zwei austauschbare Rücken:** `localStore` (wie
  heute) und `serverStore`. Alles außerhalb liest weiter `state.data` und ruft
  weiter `save()`. Der eigentliche Eingriff ist, dass `save()` asynchron wird
  und fehlschlagen kann — dafür braucht es einen sichtbaren Zustand
  („gespeichert“ / „nicht gespeichert, erneut versuchen“), keine stille
  Verwerfung.
- **Konflikte:** `updated_at` pro Grundstück wird mitgeschickt. Bei Abweichung
  keine automatische Zusammenführung, sondern die deutsche Meldung, dass dieses
  Grundstück anderswo geändert wurde, mit der Wahl. Kein CRDT.
- **Übernahme:** liegt beim ersten Login etwas im Browser, fragt ein Banner
  einmal — „In diesem Browser liegen 3 Grundstücke. Ins Konto übernehmen?“ —,
  kopiert bei Ja und löscht lokal nichts. Die Antwort wird gemerkt, damit die
  Frage nicht bei jedem Login wiederkommt.
- **Der Austausch als JSON unter „Daten“ bleibt**, und wird die Brücke: er
  funktioniert in beide Richtungen weiter und ist der Notausgang, wenn der
  Server einmal nicht da ist.

## 5 · Was sich sonst noch ändert, wenn es mehrere Nutzer gibt

Kein Teil der Startseite, aber Teil der Entscheidung:

- **Das Backend ist ein Proxy vor fremden Diensten.** Solange es ein
  Einzelplatz-Prototyp war, war das unstrittig. Ein Deployment mit Konten ist
  genau das, was die Overpass-Policy meint („relying on the public instances as
  backend“) — und dasselbe gilt für Transitous. Mit Konten wird der eigene
  MOTIS (`docker-compose.local-routing.yml`) und der eigene POI-Index von einer
  Option zur Voraussetzung, und pro Konto braucht es eine Obergrenze für
  Abrufe. Das gehört in denselben Schritt wie die Anmeldung, nicht danach.
- **Der Plattencache ist gemeinsam und muss es bleiben** — er hält Antworten
  von Behörden, nicht Nutzerdaten. Nichts Nutzerbezogenes darf hinein.

## 6 · Reihenfolge

1. **Mockup** der neuen Startseite als HTML — steht als
   `mockup/startseite.html`, heller Zustand, drei Fälle über die Leiste oben
   umschaltbar (angemeldet · angemeldet und leer · nicht angemeldet),
   auf 390 px ohne Überlauf geprüft.
2. **Nur Frontend, kein Backend:** `QueryBox` mit Chips, neue Route `/`,
   Liste nach `/grundstuecke`, „Weitermachen“ aus dem lokalen Stand. Danach ist
   die neue Startseite fertig und angemeldet ist noch niemand.
3. **Anmeldung:** OIDC-BFF im Backend, `/api/auth/me`, Anmeldezustand im
   Kopfbereich. Daten bleiben lokal.
4. **Server als Speicher:** Postgres, `plots`-API, Store-Abstraktion,
   Übernahme-Banner, Grenzen pro Konto.

## 7 · Offen

- Sollen Grundstücke zwischen Konten **geteilt** werden können (zwei Leute
  prüfen dasselbe Grundstück), oder gehört jedes genau einem? Ändert das
  Datenmodell, deshalb besser vor Schritt 4 entschieden.
- Läuft das Ganze **öffentlich erreichbar** oder in einem geschlossenen Kreis?
  Davon hängt ab, wie streng die Grenzen aus § 5 sein müssen.
- Braucht die Startseite eine **Druckansicht**? Vermutlich nein — sie ist der
  Einstieg, nicht das Ergebnis.
