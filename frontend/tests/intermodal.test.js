/**
 * Intermodal journeys and the ground under the sketch.
 *
 * The routes come from `fixtures/reachability-moritzburg.json`: the real
 * `/api/reachability` answer for the Moritzburg parcel (51.16758, 13.67797, the
 * parcel of the ALKIS fixture of the same name) to Dresden Hbf, produced by
 * replaying MOTIS answers recorded live on 31.08.2026 through the backend.
 * Every minute below is one the service returned.
 *
 * The tile maths is checked against the canonical slippy-map formula rather
 * than against itself — the sandbox browser has no route to the internet, so a
 * basemap cannot be verified by screenshot here and the arithmetic has to carry
 * the proof, exactly as `projection.test.js` does for the site plan.
 */
import { describe, it, expect, beforeEach } from "vitest";
import { mount } from "@vue/test-utils";
import RouteCards from "../src/components/RouteCards.vue";
import { state, validate } from "../src/lib/store.js";
import {
  MODES, ZUBRINGER, zubringerOf, routeBounds, fitBounds, toScreen,
  coordinatesOf, tileCover, tileUrl
} from "../src/lib/routes.js";
import { realPlot } from "./helpers.js";
import answer from "./fixtures/reachability-moritzburg.json";

const HBF = "mb-hbf";
const PINNED = "mb-uba";

/** The recorded answer in the shape the store keeps, keyed by the mode that was
 *  actually routed — which for "transit_auto" is the variant it chose. */
const recordedRoutes = () => {
  const byDestination = {};
  answer.ergebnisse.forEach(e => {
    (byDestination[e.destination_id] ||= {})[e.mode] = {
      erreichbar: e.erreichbar,
      duration_s: e.duration_s,
      umstiege: e.umstiege,
      geometry: e.geometry,
      hinweis: e.hinweis
    };
  });
  return Object.fromEntries(Object.entries(byDestination).map(([id, modes]) => [
    id, { modes, calculatedAt: "2026-08-31T21:00:00.000Z", source: answer.quelle }
  ]));
};

const destinations = () => ([
  { id: HBF, name: "Dresden Hbf", address: "Wiener Platz 4", lat: 51.040684, lon: 13.731863 },
  { id: PINNED, name: "Umweltbundesamt", address: "Wörlitzer Platz 1", lat: 51.040684,
    lon: 13.731863, zubringer: "walk" }
]);

beforeEach(() => {
  state.data = validate({
    version: 2,
    plots: [{ ...realPlot("convex"), routes: recordedRoutes() }],
    houseTypes: [],
    destinations: destinations(),
    selection: []
  });
});

const plot = () => state.data.plots[0];

describe("Der Zubringer als Angabe am Ziel", () => {
  it("nimmt „Automatisch“ an, solange nichts festgelegt ist", () => {
    // Every destination stored before the field existed carries no such key.
    expect(zubringerOf({ id: "alt", name: "Arbeit" })).toBe("automatic");
    expect(zubringerOf(undefined)).toBe("automatic");
  });

  it("verwirft einen Wert, den es nicht gibt, statt ihn weiterzureichen", () => {
    expect(zubringerOf({ zubringer: "hubschrauber" })).toBe("automatic");
    expect(zubringerOf({ zubringer: "bike" })).toBe("bike");
  });

  it("kennt genau die vier Werte, die auch das Backend kennt", () => {
    expect(ZUBRINGER.map(z => z.wert)).toEqual(["automatic", "walk", "bike", "car"]);
    ZUBRINGER.forEach(z => expect(z.name.length).toBeGreaterThan(0));
  });

  it("hat für jede vom Backend gewählte Spielart einen deutschen Namen", () => {
    const named = MODES.map(m => m.mode);
    expect(named).toContain("bike_transit");
    expect(named).toContain("car_transit");
    expect(MODES.find(m => m.mode === "bike_transit").name).toBe("Rad + ÖPNV");
  });
});

describe("Wegekarte mit gewähltem Zubringer", () => {
  it("schreibt die gewählte Spielart in die Zeile, nicht bloß „ÖPNV“", () => {
    const text = mount(RouteCards, { props: { plot: plot() } }).text();
    // 2700 s über Rad + Bus + Zug — die Automatik hat den Fußweg ersetzt.
    expect(text).toContain("Rad + ÖPNV");
    expect(text).toContain("45 min");
  });

  it("nennt die Zahlen, auf denen die Automatik entschieden hat", () => {
    const reason = mount(RouteCards, { props: { plot: plot() } })
      .findAll(".route-card__choice").map(p => p.text());
    expect(reason.some(t => t.includes("11 Min."))).toBe(true);   // Fußweg zur Haltestelle
    expect(reason.some(t => t.includes("7 Min."))).toBe(true);    // mit dem Rad
    expect(reason.some(t => t.includes("49 Min."))).toBe(true);   // wäre es zu Fuß geworden
  });

  it("sagt es, wenn der Zubringer am Ziel festgelegt ist", () => {
    const card = mount(RouteCards, { props: { plot: plot() } }).findAll("article")[1];
    expect(card.text()).toContain("fest auf");
    expect(card.text()).toContain("ÖPNV");
    expect(card.text()).toContain("49 min");    // 2940 s zu Fuß zur Haltestelle
  });

  it("verschweigt nicht, dass das Auto durchgehend schneller ist", () => {
    // 22 Minuten mit dem Auto gegen 45 mit Rad und Bahn — die Kombination ist
    // die langsamere, und das steht auf der Karte statt in der Subtraktion.
    const text = mount(RouteCards, { props: { plot: plot() } }).text();
    expect(text).toContain("Durchgehend mit dem Auto");
    expect(text).toContain("22 min");
  });

  it("hält die Begründung aus der schmalen Spalte heraus", () => {
    // Die Spalte ist 292 px breit; ein ganzer Satz darin schiebt die Zeiten
    // aus dem Bild. Das war schon einmal ein Fehler und bleibt einer.
    mount(RouteCards, { props: { plot: plot() } })
      .findAll(".route-card__note").forEach(n => expect(n.text().length).toBeLessThan(28));
  });

  it("erfindet keine Begründung, wo der Dienst keine geliefert hat", () => {
    const bare = { ...plot(), routes: { [HBF]: { modes: { transit: { erreichbar: true, duration_s: 600 } } } } };
    const w = mount(RouteCards, { props: { plot: bare } });
    expect(w.findAll(".route-card__choice")).toHaveLength(0);
  });
});

describe("Grund unter der Wegskizze", () => {
  const lines = () => ["car", "bike", "bike_transit"]
    .map(m => coordinatesOf(plot().routes[HBF].modes[m]?.geometry))
    .filter(Boolean);
  const fit = () => fitBounds(routeBounds(lines()), 300, 150, 12);

  /** The slippy-map formula, written out independently of the code under test. */
  const canonicalTile = ([lon, lat], zoom) => {
    const n = 2 ** zoom;
    const rad = (lat * Math.PI) / 180;
    return {
      x: Math.floor(((lon + 180) / 360) * n),
      y: Math.floor(((1 - Math.log(Math.tan(rad) + 1 / Math.cos(rad)) / Math.PI) / 2) * n)
    };
  };

  it("legt jede Kachel dorthin, wo die Slippy-Map-Formel sie erwartet", () => {
    const f = fit();
    const cover = tileCover(f, 300, 150);
    expect(cover.tiles.length).toBeGreaterThan(0);

    lines().flat().forEach(coordinate => {
      const wanted = canonicalTile(coordinate, cover.zoom);
      const tile = cover.tiles.find(t => t.x === wanted.x && t.y === wanted.y);
      if (!tile) return;   // the point sits outside the drawn frame's cover
      const p = toScreen(coordinate, f);
      expect(p.x).toBeGreaterThanOrEqual(tile.left - 1e-6);
      expect(p.x).toBeLessThanOrEqual(tile.left + tile.size + 1e-6);
      expect(p.y).toBeGreaterThanOrEqual(tile.top - 1e-6);
      expect(p.y).toBeLessThanOrEqual(tile.top + tile.size + 1e-6);
    });
  });

  it("deckt die ganze gezeichnete Fläche ab, ohne Loch am Rand", () => {
    const cover = tileCover(fit(), 300, 150);
    const left = Math.min(...cover.tiles.map(t => t.left));
    const top = Math.min(...cover.tiles.map(t => t.top));
    const right = Math.max(...cover.tiles.map(t => t.left + t.size));
    const bottom = Math.max(...cover.tiles.map(t => t.top + t.size));
    expect(left).toBeLessThanOrEqual(0);
    expect(top).toBeLessThanOrEqual(0);
    expect(right).toBeGreaterThanOrEqual(300);
    expect(bottom).toBeGreaterThanOrEqual(150);
  });

  it("wählt einen Zoom, dessen Auflösung zur Zeichnung passt", () => {
    // A tile is 256 pixels. Drawn much smaller it is wasted traffic, much
    // larger it is a blurred smear — rounding the exponent keeps it inside a
    // factor of the square root of two either way.
    const cover = tileCover(fit(), 300, 150);
    expect(cover.size).toBeGreaterThan(256 / Math.SQRT2 - 1e-6);
    expect(cover.size).toBeLessThan(256 * Math.SQRT2 + 1e-6);
  });

  it("bleibt innerhalb des Kachelrasters, auch wenn der Rahmen darüber hinausreicht", () => {
    const cover = tileCover(fit(), 300, 150);
    const limit = 2 ** cover.zoom;
    cover.tiles.forEach(t => {
      expect(t.x).toBeGreaterThanOrEqual(0);
      expect(t.y).toBeGreaterThanOrEqual(0);
      expect(t.x).toBeLessThan(limit);
      expect(t.y).toBeLessThan(limit);
    });
  });

  it("verzichtet lieber auf den Grund, als hundert Kacheln zu holen", () => {
    expect(tileCover(fit(), 300, 150, 1)).toBeNull();
    expect(tileCover(null, 300, 150)).toBeNull();
    expect(tileCover({ scale: 0, dx: 0, dy: 0 }, 300, 150)).toBeNull();
  });

  it("holt die Kacheln über den eigenen Proxy, nicht von einem fremden Server", () => {
    const [tile] = tileCover(fit(), 300, 150).tiles;
    expect(tileUrl(tile)).toBe(`/api/tiles/webatlas/${tile.z}/${tile.x}/${tile.y}.png`);
  });

  it("zeichnet den Grund in die Skizze und nennt die Quelle", () => {
    const w = mount(RouteCards, { props: { plot: plot() } });
    expect(w.findAll("image").length).toBeGreaterThan(0);
    // Deutschlandweit, weil ein Ziel außerhalb Sachsens liegen kann.
    expect(w.find("image").attributes("href")).toContain("/api/tiles/deutschland/");
    expect(w.text()).toContain("GeoBasis-DE / BKG");
  });

  it("lässt sich abschalten, ohne die Skizze mitzunehmen", () => {
    const w = mount(RouteCards, { props: { plot: plot(), backdrop: false } });
    expect(w.findAll("image")).toHaveLength(0);
    expect(w.findAll("polyline").length).toBeGreaterThan(0);
  });

  it("legt keinen Grund unter eine Karte ohne Geometrie", () => {
    const bare = { ...plot(), routes: {} };
    expect(mount(RouteCards, { props: { plot: bare } }).findAll("image")).toHaveLength(0);
  });
});
