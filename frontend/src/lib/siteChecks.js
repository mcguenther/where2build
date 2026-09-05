/**
 * From what the authorities answered to what the page says.
 *
 * `/api/site-checks` hands back the services' own vocabulary — `Lden5559`,
 * `LK_IV`, a name and a distance bracket. This module is the one place that
 * turns that into the input the templates in `findings.js` expect, and it does
 * nothing else: it composes no sentence of its own, so every word on the check
 * list still comes from one reviewable list of templates.
 *
 * Three rules it keeps:
 *
 * - **A check that failed is open, never green.** A block that came back with
 *   `fehler` says so, in the backend's own German, and counts as unanswered.
 * - **A check with no service behind it says why.** Heavy rain, contaminated
 *   sites and mobile coverage have no open endpoint; each carries the reason
 *   rather than being quietly left out, because a list that silently omits
 *   what it cannot answer reads as a complete one.
 * - **No score.** The summary is a counter — "6 ohne Befund · 2 zu beachten ·
 *   3 offen". A single number over eleven checks, three of which have no data,
 *   would describe the data situation while looking like a statement about the
 *   plot.
 */

import {
  noiseFinding, designationFinding, airQualityFinding, groundFinding,
  unavailableFinding, tallyFindings, tallyText, GOOD, NOTE, OPEN
} from "./findings.js";

/** The survey's source keys, in the wording the templates know. */
const NOISE_SOURCES = { strasse: "road", strassenbahn: "tram", flughafen: "air" };

const rename = (bands, map) =>
  Object.fromEntries(Object.entries(bands ?? {}).map(([key, value]) => [map[key] ?? key, value]));

/** What the section under a check names as its origin. */
const source = block => block?.quelle ?? null;

/**
 * The checks that have no service behind them.
 *
 * Each says what is missing and where an answer would come from. They are not
 * a promise of a future feature — they are the honest shape of a list whose
 * last three rows nobody can fill today.
 */
const WITHOUT_SOURCE = [
  {
    id: "starkregen",
    name: "Starkregen",
    value: "—",
    text: "KOSTRA-DWD-2020 liegt beim Deutschen Wetterdienst als Raster zum Herunterladen "
      + "vor, nicht als Abfragedienst. Ohne diesen Import gibt es hier keine Aussage.",
    quelle: "DWD KOSTRA-2020 — noch nicht eingebunden"
  },
  {
    id: "altlasten",
    name: "Altlasten",
    value: "keine Daten",
    text: "Für Sachsen ist kein flächendeckender Altlastendienst öffentlich; das "
      + "Sächsische Altlastenkataster (SALKA) ist nicht offen abrufbar.",
    quelle: "Auskunft erteilt der Landkreis"
  },
  {
    id: "mobilfunk",
    name: "Mobilfunk und Breitband",
    value: "ungeprüft",
    text: "Das Gigabit-Grundbuch und der Breitband-Monitor sind Portalanwendungen ohne "
      + "offene Schnittstelle. Was dort steht, lässt sich nur von Hand nachsehen.",
    quelle: "gigabitgrundbuch.bund.de — kein Abfragedienst"
  }
];

/** Was this block answered at all? A failure is open, never "not affected". */
const failed = block => Boolean(block?.fehler);

const radiusText = metres =>
  metres === 1000 ? "eines Kilometers" : `${Math.round(metres)} m`;

/**
 * One designation, as the templates want it.
 *
 * `subject` is the bare noun the sentence is built around — the category the
 * nearest area was actually designated under, so a Landschaftsschutzgebiet is
 * not reported as a "Schutzgebiet".
 */
function designation(block, { subject, absent = null, absentValue = null }) {
  if (failed(block)) return unavailableFinding({ text: block.fehler });
  const inside = block?.gebiete?.[0] ?? null;
  return designationFinding({
    hit: Boolean(block?.betroffen),
    name: block?.betroffen ? inside?.name : block?.naechstes?.name ?? null,
    subject: (block?.betroffen ? inside?.kategorie : block?.naechstes?.kategorie) || subject,
    distanceFrom: block?.abstand_von_m ?? null,
    distanceTo: block?.abstand_bis_m ?? null,
    alsoNearby: block?.weitere_im_umkreis ?? 0,
    nearbyRadius: radiusText(block?.umkreis_m ?? 1000),
    absent,
    absentValue
  });
}

/**
 * Every check for one plot, in the order the page shows them.
 *
 * Sorted by what needs attention: findings first, then the checks that raised
 * none, then the ones nobody could answer. Within a group the declared order
 * stands, so the list does not reshuffle itself between two plots.
 */
export function siteFindings(answer) {
  if (!answer) return [];

  const noise = failed(answer.laerm)
    ? unavailableFinding({ text: answer.laerm.fehler })
    : noiseFinding({
        day: rename(answer.laerm?.tag, NOISE_SOURCES),
        night: rename(answer.laerm?.nacht, NOISE_SOURCES),
        mappedNearby: Boolean(answer.laerm?.kartiert_umkreis),
        lowestBand: answer.laerm?.unterste_stufe_db ?? 45
      });

  const ground = failed(answer.baugrund)
    ? unavailableFinding({ text: answer.baugrund.fehler })
    : groundFinding({
        soilText: answer.baugrund?.bodenart_text ?? null,
        airCapacityClass: answer.baugrund?.luftkapazitaet_stufe ?? null,
        boreholes: answer.baugrund?.bohrungen_naher_umkreis ?? 0,
        boreholesAsked: answer.baugrund?.bohrungen_gefragt !== false,
        radiusM: answer.baugrund?.naher_umkreis_m ?? 300,
        nearestM: answer.baugrund?.naechste?.entfernung_m ?? null,
        nearestDepthM: answer.baugrund?.naechste?.endteufe_m ?? null,
        deepest: answer.baugrund?.tiefste
          ? { depthM: answer.baugrund.tiefste.endteufe_m, year: answer.baugrund.tiefste.jahr }
          : null
      });

  const air = failed(answer.luftqualitaet)
    ? unavailableFinding({ text: answer.luftqualitaet.fehler })
    : airQualityFinding({
        station: answer.luftqualitaet?.station ?? null,
        distanceKm: answer.luftqualitaet?.entfernung_km ?? null,
        values: answer.luftqualitaet?.werte ?? {},
        hours: answer.luftqualitaet?.stunden ?? null,
        skipped: answer.luftqualitaet?.uebersprungen ?? 0
      });

  const checks = [
    { id: "laerm", name: "Lärm", finding: noise, quelle: source(answer.laerm) },
    {
      id: "baugrund", name: "Baugrund", finding: ground, quelle: source(answer.baugrund),
      // The soil map's own wording, kept behind a disclosure: it is the
      // evidence for the sentence above it, and unreadable as a headline.
      detail: answer.baugrund?.bodenart_text ?? null,
      detailLabel: "Wortlaut der Bodenkarte"
    },
    {
      id: "hochwasser", name: "Hochwasser", quelle: source(answer.hochwasser),
      finding: designation(answer.hochwasser, {
        subject: "Überschwemmungsgebiet",
        absent: "Kein Überschwemmungsgebiet am Grundstück — geprüft von HQ20 bis "
          + "zum Extremhochwasser."
      })
    },
    {
      id: "radon", name: "Radon", quelle: source(answer.radon),
      finding: designation(answer.radon, {
        subject: "Radonvorsorgegebiet",
        absent: "Die Gemeinde ist kein Radonvorsorgegebiet nach § 121 StrlSchG. Das ist "
          + "eine rechtsverbindliche Ausweisung, keine modellierte Potenzialklasse."
      })
    },
    {
      id: "trinkwasserschutz", name: "Trinkwasserschutz", quelle: source(answer.trinkwasserschutz),
      finding: designation(answer.trinkwasserschutz, {
        subject: "Wasserschutzgebiet",
        absent: "Kein Trinkwasser- oder Heilquellenschutzgebiet am Grundstück."
      })
    },
    {
      id: "schutzgebiet", name: "Schutzgebiet", quelle: source(answer.schutzgebiet),
      finding: designation(answer.schutzgebiet, { subject: "Schutzgebiet" })
    },
    { id: "luftqualitaet", name: "Luftqualität", finding: air, quelle: source(answer.luftqualitaet) },
    {
      id: "hangneigung", name: "Hangneigung", quelle: source(answer.hangneigung),
      finding: designation(answer.hangneigung, {
        subject: "Hangneigungsgebiet",
        absentValue: "unter 20 %",
        absent: "Das Grundstück liegt nicht in der Kulisse der Flächen über 20 % Neigung. "
          + "Ein genauer Neigungswert bräuchte das Landeshöhenmodell — diese Kulisse "
          + "stammt aus dem Düngerecht und kennt nur ja und nein."
      })
    },
    ...WITHOUT_SOURCE.map(({ id, name, quelle, ...reason }) => ({
      id, name, quelle, finding: unavailableFinding(reason)
    }))
  ];

  const rank = { [NOTE]: 0, [GOOD]: 1, [OPEN]: 2 };
  return checks
    .map((check, index) => ({ ...check, index }))
    .sort((a, b) => rank[a.finding.status] - rank[b.finding.status] || a.index - b.index);
}

/** The counters that stand in for a score, and their sentence. */
export function siteTally(checks) {
  const counts = tallyFindings((checks ?? []).map(check => check.finding));
  return { counts, text: tallyText(counts) };
}

/* Re-exported so a view can colour a row without importing the templates. */
export { GOOD, NOTE, OPEN };
