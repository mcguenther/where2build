/** Test helpers: real plots and house types, built from the recorded fixtures. */
import convex from "./fixtures/parcel-convex.json";
import concave from "./fixtures/parcel-concave.json";
import large from "./fixtures/parcel-large.json";
import manyCorners from "./fixtures/parcel-many-corners.json";
import moelkau from "./fixtures/parcel-moelkau.json";
import elk from "./fixtures/housetype-elk.json";
import reachability from "./fixtures/reachability-liebertwolkwitz.json";
import { mount } from "@vue/test-utils";
import { createMemoryHistory } from "vue-router";
import { createAppRouter } from "../src/router/index.js";
import { plotFromCadastre } from "../src/lib/plots.js";
import { houseTypeFromResponse } from "../src/lib/houseTypes.js";
import { SCHEMA_VERSION } from "../src/lib/sample.js";

export const realHouseType = () => ({ ...houseTypeFromResponse(elk), id: "ht-elk" });

/* Five parcels ALKIS really returned. "large" is 34 799 m² in Moritzburg;
   "manyCorners" is the 1583 x 198 m strip a district address resolves to;
   "moelkau" is Flurstück 204 in Mölkau, Lessingweg 44, 650 m² over five
   boundary points -- an ordinary building plot. */
const PARCELS = { convex, concave, large, "many-corners": manyCorners, moelkau };

export const realPlot = (shape = "convex", extra = {}) => ({
  ...plotFromCadastre(PARCELS[shape] ?? convex, {
    askingPrice: 349000, bodenrichtwert: 210, brwZone: "5417", brwReferenceDate: "2026-01-01", ...extra
  }),
  id: `plot-${shape}`,
  houseTypeId: "ht-elk"
});

/** The recorded MOTIS answer, reshaped the way PlotView stores it. */
export const realRoutes = () => {
  const byDestination = {};
  reachability.ergebnisse.forEach(e => {
    (byDestination[e.destination_id] ||= {})[e.mode] = {
      erreichbar: e.erreichbar,
      duration_s: e.duration_s,
      umstiege: e.umstiege,
      geometry: e.geometry,
      hinweis: e.hinweis
    };
  });
  return Object.fromEntries(Object.entries(byDestination).map(([id, modes]) => [
    id, { modes, calculatedAt: "2026-08-29T20:22:00.000Z", source: reachability.quelle }
  ]));
};

/** The two destinations the recorded routes actually lead to. */
export const realDestinations = () => ([
  { id: "zl-hbf", name: "Leipzig Hauptbahnhof", address: "Willy-Brandt-Platz 5, Leipzig",
    lat: 51.3459, lon: 12.3833, match: "Leipzig Hauptbahnhof" },
  { id: "zl-schule", name: "Grundschule Liebertwolkwitz", address: "Muldentalstraße 4, Leipzig",
    lat: 51.2846, lon: 12.4562, match: "Grundschule Liebertwolkwitz" }
]);

/** A state with two real parcels, one real house type and one destination. */
export const realState = () => ({
  version: SCHEMA_VERSION,
  plots: [realPlot("convex"), realPlot("concave")],
  houseTypes: [realHouseType()],
  destinations: [{ id: "zl-arbeit", name: "Arbeit", address: "Nonnenstraße 39, Leipzig" }],
  selection: ["plot-convex", "plot-concave"]
});

/**
 * The same state as a version-1 document, in the German field names the app
 * used to write. Built by translating the current shape back, so it cannot
 * drift away from what the migration has to accept.
 */
export const realStateV1 = () => {
  const current = realState();
  const backToV1 = (object, map) =>
    Object.fromEntries(Object.entries(object).map(([key, value]) => [map[key] ?? key, value]));

  const plotKeys = {
    municipality: "ort", anchor: "anker", northOffset: "nordVersatz", officialArea: "flaecheAmtlich",
    askingPrice: "kaufpreis", brwReferenceDate: "brwStichtag", divisionLine: "teilung",
    streetEdge: "strassenkante", houseTypeId: "haustypId", house: "haus", customSize: "eigenmass",
    ratio: "verhaeltnis", wallHeight: "wandhoehe", setbacks: "tiefen", source: "quelle",
    readAt: "gelesenAm", note: "notiz", routes: "wege"
  };
  const houseTypeKeys = {
    manufacturer: "hersteller", builtArea: "bebauteFlaeche", livingArea: "wohnflaeche",
    livingAreaGround: "wohnflaecheEg", livingAreaUpper: "wohnflaecheOg", length: "laenge",
    width: "breite", roofShape: "dachform", priceFrom: "preisAb", minimumPlotArea: "grundstueckAb",
    eavesHeight: "traufhoehe", ridgeHeight: "firsthoehe", ratio: "verhaeltnis", source: "quelle",
    readAt: "gelesenAm", note: "hinweis", custom: "eigen"
  };

  return {
    version: 1,
    grundstuecke: current.plots.map(p => {
      const out = backToV1(p, plotKeys);
      out.wege = Object.fromEntries(Object.entries(out.wege).map(([id, route]) => [
        id, { modi: route.modes, berechnet_am: route.calculatedAt, quelle: route.source }
      ]));
      return out;
    }),
    haustypen: current.houseTypes.map(h => backToV1(h, houseTypeKeys)),
    ziele: current.destinations.map(d => backToV1(d, { address: "adresse", match: "treffer" })),
    auswahl: current.selection
  };
};

/* ---------- Mounting a view ----------
 * Views navigate and draw links, so they need a router. A memory history keeps
 * it out of jsdom's one shared address bar, so every test gets its own. */
export function testRouter(path = "/") {
  const router = createAppRouter(createMemoryHistory());
  router.push(path);
  return router;
}

/** Mount one view with a live router. `props` are what the route would pass. */
export const mountWithRouter = (component, { path = "/", props, router = testRouter(path) } = {}) =>
  mount(component, { props, global: { plugins: [router] } });
