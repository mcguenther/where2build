/**
 * Sample data for a first run: four candidate plots around Leipzig, three house
 * types and four everyday destinations.
 *
 * The Liebertwolkwitz figures come from the pre-project note (a real listing:
 * "802 m² (Flurstück 790 sowie 706)"), as does the ELK house type. The other
 * house types are explicit placeholders — inventing specifications and
 * attributing them to real manufacturers would be worse than admitting they
 * are stand-ins until a real product page is read.
 */

const ring = pairs => pairs.map(([x, y]) => ({ x, y }));

export const sampleHouseTypes = () => [
  {
    id: "ht-elk159", hersteller: "ELK", name: "All in One 159",
    bebauteFlaeche: 96.88, wohnflaeche: 159.21, wohnflaecheEg: 79.6, wohnflaecheOg: 79.61,
    laenge: null, breite: null, dachform: "Satteldach", preisAb: 289900, verhaeltnis: 1.35,
    quelle: "https://www.elk.de/haeuser/elk-all-in-one-159", gelesenAm: "2026-08-29", eigen: false
  },
  {
    id: "ht-stadt134", hersteller: "Beispielkatalog", name: "Stadthaus 134",
    bebauteFlaeche: 78.2, wohnflaeche: 134, wohnflaecheEg: 67, wohnflaecheOg: 67,
    laenge: 10.4, breite: 7.5, dachform: "Satteldach", preisAb: 238500, verhaeltnis: 1.39,
    quelle: null, gelesenAm: "2026-08-29", eigen: false
  },
  {
    id: "ht-land196", hersteller: "Beispielkatalog", name: "Landhaus 196",
    bebauteFlaeche: 196, wohnflaeche: 284, wohnflaecheEg: 142, wohnflaecheOg: 142,
    laenge: 14, breite: 14, dachform: "Walmdach", preisAb: 449000, verhaeltnis: 1,
    quelle: null, gelesenAm: "2026-08-29", eigen: false
  }
];

export const sampleDestinations = () => [
  { id: "zl-arbeit", name: "Arbeit", adresse: "Nonnenstraße 39, Leipzig" },
  { id: "zl-schule", name: "Grundschule", adresse: "Muldentalstraße 5, Liebertwolkwitz" },
  { id: "zl-kita", name: "Kita Kolibri", adresse: "Am Kirschberg 2, Holzhausen" },
  { id: "zl-bahnhof", name: "Leipzig Hbf", adresse: "Willy-Brandt-Platz 7" }
];

/** Travel times keyed by destination: [car, bike, transit, combined, note, transitNote, distance]. */
export const samplePlots = () => [
  {
    id: "gs-liebertwolkwitz", name: "Muldentalstraße", ort: "04288 Leipzig-Liebertwolkwitz",
    gemarkung: "Liebertwolkwitz", flurstuecke: ["790", "706"],
    flaecheAmtlich: 802, kaufpreis: 189000,
    bodenrichtwert: 210, brwZone: "5417", brwStichtag: "2026-01-01", nordVersatz: 17,
    polygon: ring([[0, 0], [22.6, 0.9], [24.3, 34.9], [1.6, 36.2]]),
    teilung: [[11.6, 0.45], [12.95, 35.55]],
    haustypId: "ht-elk159", haus: { cx: 10.8, cy: 15, rotation: -4 },
    verhaeltnis: 1.35, wandhoehe: 6.4, tiefen: [3, 3, 3, 3],
    quelle: "https://www.kleinanzeigen.de/s-anzeige/baugrundstueck-leipzig/2947103821",
    notiz: "Unbeplanter Innenbereich, Beurteilung nach § 34 BauGB.",
    wege: {
      "zl-arbeit": [24, 51, 48, 42, "Rad bis Stötteritz", "3× umsteigen", "18,4 km"],
      "zl-schule": [4, 8, 19, 17, "zu Fuß", "1× umsteigen", "1,4 km"],
      "zl-kita": [9, 18, 34, 27, "Rad bis Holzhausen", "2× umsteigen", "5,1 km"],
      "zl-bahnhof": [21, 44, 38, 31, "Rad bis Stötteritz", "1× umsteigen", "14,8 km"]
    }
  },
  {
    id: "gs-holzhausen", name: "Am Kirschberg", ort: "04288 Leipzig-Holzhausen",
    gemarkung: "Holzhausen", flurstuecke: ["214/7"],
    flaecheAmtlich: 641, kaufpreis: 198000,
    bodenrichtwert: 252, brwZone: "5402", brwStichtag: "2026-01-01", nordVersatz: -8,
    polygon: ring([[0, 0], [19.4, 0], [19.4, 33], [0, 33]]),
    teilung: null,
    haustypId: "ht-elk159", haus: { cx: 9.7, cy: 14.5, rotation: 0 },
    verhaeltnis: 1.35, wandhoehe: 6.4, tiefen: [3, 3, 3, 3],
    quelle: "https://www.kleinanzeigen.de/s-anzeige/grundstueck-holzhausen/2938441207",
    notiz: "Ecklage, zwei Straßenfronten.",
    wege: {
      "zl-arbeit": [19, 38, 29, 26, "Rad bis Paunsdorf", "2× umsteigen", "13,1 km"],
      "zl-schule": [7, 12, 24, 22, "Rad", "1× umsteigen", "2,6 km"],
      "zl-kita": [2, 4, 11, 9, "zu Fuß", "direkt", "0,6 km"],
      "zl-bahnhof": [17, 33, 26, 24, "Rad bis Paunsdorf", "direkt", "11,2 km"]
    }
  },
  {
    id: "gs-baalsdorf", name: "Sommerfelder Weg", ort: "04316 Leipzig-Baalsdorf",
    gemarkung: "Baalsdorf", flurstuecke: ["61/3", "61/4", "62"],
    flaecheAmtlich: 1104, kaufpreis: 212000,
    bodenrichtwert: 200, brwZone: "5388", brwStichtag: "2026-01-01", nordVersatz: 31,
    polygon: ring([[0, 0], [28.5, 2.6], [37.3, 24.2], [23.1, 41.7], [4.4, 34]]),
    teilung: [[14.4, 1.3], [13.7, 37.8]],
    haustypId: "ht-land196", haus: { cx: 18.5, cy: 19, rotation: 8 },
    verhaeltnis: 1, wandhoehe: 3.4, tiefen: [3, 3, 3, 3, 3],
    quelle: "Aus der Zwischenablage eingefügt",
    notiz: "Drei Flurstücke, gemeinsam angeboten.",
    wege: {
      "zl-arbeit": [26, 57, 51, 46, "Rad bis Engelsdorf", "3× umsteigen", "19,8 km"],
      "zl-schule": [11, 15, 32, 29, "Rad", "2× umsteigen", "3,9 km"],
      "zl-kita": [13, 21, 38, 33, "Rad bis Holzhausen", "2× umsteigen", "6,4 km"],
      "zl-bahnhof": [23, 49, 43, 36, "Rad bis Engelsdorf", "1× umsteigen", "16,1 km"]
    }
  },
  {
    id: "gs-zuckelhausen", name: "Hoher Weg", ort: "04288 Leipzig-Zuckelhausen",
    gemarkung: "Zuckelhausen", flurstuecke: ["118"],
    flaecheAmtlich: 733, kaufpreis: 165000,
    bodenrichtwert: 220, brwZone: "5411", brwStichtag: "2026-01-01", nordVersatz: -23,
    polygon: ring([[0, 0], [21.5, -1.4], [23.4, 34.1], [11.9, 30.4], [1.4, 35.8]]),
    teilung: null,
    haustypId: "ht-stadt134", haus: { cx: 10.5, cy: 13.5, rotation: -2 },
    verhaeltnis: 1.39, wandhoehe: 6.4, tiefen: [3, 3, 3, 3, 3],
    quelle: "https://www.kleinanzeigen.de/s-anzeige/bauplatz-zuckelhausen/2951882630",
    notiz: "Zuschnitt mit Knick an der Nordwestgrenze.",
    wege: {
      "zl-arbeit": [22, 47, 38, 35, "Rad bis Stötteritz", "2× umsteigen", "16,2 km"],
      "zl-schule": [6, 10, 21, 18, "Rad", "1× umsteigen", "2,1 km"],
      "zl-kita": [8, 14, 26, 23, "Rad", "2× umsteigen", "3,8 km"],
      "zl-bahnhof": [19, 40, 33, 29, "Rad bis Stötteritz", "1× umsteigen", "13,4 km"]
    }
  }
];

export const sampleState = () => ({
  version: 1,
  grundstuecke: samplePlots(),
  haustypen: sampleHouseTypes(),
  ziele: sampleDestinations(),
  auswahl: ["gs-liebertwolkwitz", "gs-holzhausen", "gs-baalsdorf", "gs-zuckelhausen"]
});
