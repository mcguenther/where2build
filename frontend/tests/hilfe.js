/** Test helpers: real plots and house types, built from the recorded fixtures. */
import konvex from "./fixtures/parcel-konvex.json";
import konkav from "./fixtures/parcel-konkav.json";
import elk from "./fixtures/housetype-elk.json";
import wege from "./fixtures/reachability-liebertwolkwitz.json";
import { plotAusKataster } from "../src/lib/plots.js";
import { haustypAusAntwort } from "../src/lib/houseTypes.js";

export const echterHaustyp = () => ({ ...haustypAusAntwort(elk), id: "ht-elk" });

export const echtesGrundstueck = (form = "konvex", zusatz = {}) => ({
  ...plotAusKataster(form === "konvex" ? konvex : konkav, {
    kaufpreis: 349000, bodenrichtwert: 210, brwZone: "5417", brwStichtag: "2026-01-01", ...zusatz
  }),
  id: `gs-${form}`,
  haustypId: "ht-elk"
});

/** The recorded MOTIS answer, reshaped the way PlotView stores it. */
export const echteWege = () => {
  const nach = {};
  wege.ergebnisse.forEach(e => {
    (nach[e.destination_id] ||= {})[e.mode] = {
      erreichbar: e.erreichbar,
      duration_s: e.duration_s,
      umstiege: e.umstiege,
      geometry: e.geometry,
      hinweis: e.hinweis
    };
  });
  return Object.fromEntries(Object.entries(nach).map(([id, modi]) => [
    id, { modi, berechnet_am: "2026-08-29T20:22:00.000Z", quelle: wege.quelle }
  ]));
};

/** The two destinations the recorded routes actually lead to. */
export const echteZiele = () => ([
  { id: "zl-hbf", name: "Leipzig Hauptbahnhof", adresse: "Willy-Brandt-Platz 5, Leipzig",
    lat: 51.3459, lon: 12.3833, treffer: "Leipzig Hauptbahnhof" },
  { id: "zl-schule", name: "Grundschule Liebertwolkwitz", adresse: "Muldentalstraße 4, Leipzig",
    lat: 51.2846, lon: 12.4562, treffer: "Grundschule Liebertwolkwitz" }
]);

/** A state with two real parcels, one real house type and one destination. */
export const echterStand = () => ({
  version: 1,
  grundstuecke: [echtesGrundstueck("konvex"), echtesGrundstueck("konkav")],
  haustypen: [echterHaustyp()],
  ziele: [{ id: "zl-arbeit", name: "Arbeit", adresse: "Nonnenstraße 39, Leipzig" }],
  auswahl: ["gs-konvex", "gs-konkav"]
});
