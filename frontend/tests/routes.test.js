/**
 * The route cards, checked against a recorded MOTIS answer.
 *
 * Liebertwolkwitz → Leipzig Hbf and → the local primary school, fetched live
 * on 2026-08-29 and stored in tests/fixtures/. Every number below is one the
 * service actually returned; none was chosen to make an assertion pass.
 */
import { describe, it, expect, beforeEach } from "vitest";
import { mount } from "@vue/test-utils";
import RouteCards from "../src/components/RouteCards.vue";
import { state, validate } from "../src/lib/store.js";
import {
  routeBounds, fitBounds, toScreen, toPolyline, coordinatesOf, fastestMode, groundWidth
} from "../src/lib/routes.js";
import { realPlot, realRoutes, realDestinations } from "./helpers.js";

const HBF = "zl-hbf";
const SCHOOL = "zl-schule";

const stateWithRoutes = () => {
  const plot = { ...realPlot("convex"), routes: realRoutes() };
  return validate({ version: 2, plots: [plot], houseTypes: [], destinations: realDestinations(), selection: [] });
};

beforeEach(() => { state.data = stateWithRoutes(); });

const plot = () => state.data.plots[0];

describe("Aufbereitung echter MOTIS-Geometrie", () => {
  it("übersteht die Prüfung des Speichers unbeschädigt", () => {
    const route = plot().routes[HBF];
    expect(Object.keys(route.modes).sort()).toEqual(["bike", "car", "transit"]);
    expect(route.modes.car.duration_s).toBe(754);
    expect(route.modes.car.geometry.coordinates.length).toBe(455);
  });

  it("hält die Fahrzeiten in der Reihenfolge, die die Strecke erwarten lässt", () => {
    const m = plot().routes[HBF].modes;
    // 10 km in die Stadt: mit dem Auto am schnellsten, mit dem Rad am längsten.
    expect(m.car.duration_s).toBeLessThan(m.transit.duration_s);
    expect(m.transit.duration_s).toBeLessThan(m.bike.duration_s);
    expect(fastestMode(plot().routes[HBF])).toBe("car");
  });

  it("erkennt ein Ziel ohne Verbindung als solches", () => {
    const transit = plot().routes[SCHOOL].modes.transit;
    expect(transit.erreichbar).toBe(false);
    expect(transit.duration_s).toBeUndefined();
    expect(transit.geometry).toBeUndefined();
    expect(fastestMode(plot().routes[SCHOOL])).toBe("car");
  });

  it("liest Koordinaten nur aus einer echten Linie", () => {
    expect(coordinatesOf(null)).toBeNull();
    expect(coordinatesOf({ type: "Point", coordinates: [12, 51] })).toBeNull();
    expect(coordinatesOf({ type: "LineString", coordinates: [[12, 51]] })).toBeNull();
    expect(coordinatesOf(plot().routes[HBF].modes.car.geometry)).toHaveLength(455);
  });
});

describe("Einpassen in die Kartenfläche", () => {
  const lines = () => ["car", "bike", "transit"]
    .map(m => coordinatesOf(state.data.plots[0].routes[HBF].modes[m]?.geometry))
    .filter(Boolean);

  it("umfasst jeden Punkt jeder Linie", () => {
    const b = routeBounds(lines());
    lines().flat().forEach(([lon, lat]) => {
      expect(lon).toBeGreaterThanOrEqual(b.minLon - 1e-9);
      expect(lon).toBeLessThanOrEqual(b.maxLon + 1e-9);
      expect(lat).toBeGreaterThanOrEqual(b.minLat - 1e-9);
      expect(lat).toBeLessThanOrEqual(b.maxLat + 1e-9);
    });
  });

  it("bleibt im Bild und hält den Rand ein", () => {
    const fit = fitBounds(routeBounds(lines()), 300, 150, 12);
    lines().flat().forEach(c => {
      const p = toScreen(c, fit);
      expect(p.x).toBeGreaterThanOrEqual(-0.01);
      expect(p.x).toBeLessThanOrEqual(300.01);
      expect(p.y).toBeGreaterThanOrEqual(-0.01);
      expect(p.y).toBeLessThanOrEqual(150.01);
    });
  });

  it("verzerrt nicht: gleiche Strecke in Ost und Nord wird gleich lang gezeichnet", () => {
    // A square in Mercator units must stay square on screen, otherwise a
    // detour to the north would look longer than the same detour eastward.
    const fit = fitBounds(routeBounds(lines()), 300, 150, 12);
    const b = routeBounds(lines());
    const centre = [(b.minLon + b.maxLon) / 2, (b.minLat + b.maxLat) / 2];
    const a = toScreen(centre, fit);
    const east = toScreen([centre[0] + 0.001, centre[1]], fit);
    const north = toScreen([centre[0], centre[1] + 0.001 * Math.cos(centre[1] * Math.PI / 180)], fit);
    expect(Math.abs(east.x - a.x)).toBeCloseTo(Math.abs(north.y - a.y), 3);
  });

  it("misst die Bildbreite in echten Metern", () => {
    // Liebertwolkwitz to the Hauptbahnhof spans about 5.5 km east-west.
    const m = groundWidth(routeBounds(lines()));
    expect(m).toBeGreaterThan(4500);
    expect(m).toBeLessThan(7000);
  });

  it("macht aus einer Linie einen zeichenbaren Punktzug", () => {
    const fit = fitBounds(routeBounds(lines()), 300, 150, 12);
    const points = toPolyline(lines()[0], fit);
    expect(points.split(" ")).toHaveLength(455);
    expect(points).toMatch(/^[\d.,\s-]+$/);
    expect(toPolyline([[12, 51]], fit)).toBe("");
  });
});

describe("Wegekarten mit echten Daten", () => {
  it("zeichnet je erreichbarem Verkehrsmittel genau eine Linie", () => {
    const w = mount(RouteCards, { props: { plot: plot() } });
    // Hbf: three modes with geometry. School: car and bike, no transit.
    expect(w.findAll("polyline")).toHaveLength(5);
  });

  it("nennt die gemessenen Zeiten, nicht gerundete Wunschwerte", () => {
    const t = mount(RouteCards, { props: { plot: plot() } }).text();
    expect(t).toContain("13 min");     // Auto 754 s
    expect(t).toContain("32 min");     // ÖPNV 1920 s
    expect(t).toContain("41 min");     // Rad 2489 s
  });

  it("sagt beim Verkehrsmittel ohne Verbindung kurz, dass keine gefunden wurde", () => {
    const w = mount(RouteCards, { props: { plot: plot() } });
    expect(w.text()).toContain("keine Verbindung");
    // A 292 px card has no room for the service's full sentence; it wrapped to
    // four lines and pushed the times out of view. The long form lives in the
    // title attribute instead, so nothing is lost.
    const notes = w.findAll(".route-card__note").map(n => n.text());
    notes.forEach(n => expect(n.length).toBeLessThan(28));
    const long = w.findAll(".route-card__note").map(n => n.attributes("title")).filter(Boolean);
    expect(long.some(t => t.includes("keine Verbindung gefunden"))).toBe(true);
  });

  it("hebt das schnellste Verkehrsmittel hervor und zeichnet es zuletzt", () => {
    const w = mount(RouteCards, { props: { plot: plot() } });
    const firstCard = w.findAll("article")[0].findAll("polyline");
    const thickest = firstCard[firstCard.length - 1];
    expect(thickest.attributes("stroke-width")).toBe("3.4");
    expect(thickest.attributes("opacity")).toBe("1");
  });

  it("nennt den Stand der Berechnung und die Quelle", () => {
    const t = mount(RouteCards, { props: { plot: plot() } }).text();
    expect(t).toContain("29.08.2026");
    expect(t).toContain("MOTIS");
  });

  it("wirft erfundene Wege aus dem Mockup beim Laden weg", () => {
    // The mockup stored an array of made-up minutes under the same key.
    const restored = validate({
      version: 2,
      plots: [{ ...realPlot("convex"), routes: { [HBF]: [14, 38, 29, 31, "a", "b", "c"] } }],
      houseTypes: [], destinations: realDestinations(), selection: []
    });
    expect(restored.plots[0].routes).toEqual({});
    const t = mount(RouteCards, { props: { plot: restored.plots[0] } }).text();
    expect(t).toContain("Noch nicht berechnet");
    expect(t).not.toMatch(/\d+ min/);
  });

  it("vergisst Wege zu einem Ziel, das es nicht mehr gibt", () => {
    const restored = validate({
      version: 2,
      plots: [{ ...realPlot("convex"), routes: realRoutes() }],
      houseTypes: [], destinations: [realDestinations()[0]], selection: []
    });
    expect(Object.keys(restored.plots[0].routes)).toEqual([HBF]);
  });
});

describe("Nachprüfbarkeit und Begründung", () => {
  it("nennt bei jedem nicht erreichbaren Verkehrsmittel den Grund im Klartext", () => {
    // The reason used to live in a title attribute — invisible on a touch
    // screen, in print, and to anyone who does not hover.
    const w = mount(RouteCards, { props: { plot: plot() } });
    const reasons = w.findAll(".route-card__why").map(p => p.text());
    expect(reasons.length).toBeGreaterThan(0);
    expect(reasons.some(t => t.includes("ÖPNV"))).toBe(true);
    expect(reasons.some(t => /keine Verbindung/i.test(t))).toBe(true);
  });

  it("schreibt keinen Grund hin, wo alles erreichbar war", () => {
    const w = mount(RouteCards, { props: { plot: plot() } });
    const cards = w.findAll("article");
    // Hbf: every mode routed. School: no transit.
    expect(cards[0].findAll(".route-card__why")).toHaveLength(0);
    expect(cards[1].findAll(".route-card__why").length).toBeGreaterThan(0);
  });

  it("verlinkt jede Route nach OpenStreetMap und Google Maps", () => {
    const w = mount(RouteCards, { props: { plot: plot() } });
    const links = w.findAll(".route-card__links a").map(a => a.attributes("href"));
    expect(links.some(h => h.startsWith("https://www.openstreetmap.org/directions"))).toBe(true);
    expect(links.some(h => h.startsWith("https://www.google.com/maps/dir/"))).toBe(true);
    // Both ends of the route must be in the URL, or the link is decoration.
    // Both ends, taken from the data rather than hard-coded, so the assertion
    // cannot drift away from the fixture.
    const osm = links.find(h => h.includes("openstreetmap"));
    expect(osm).toContain(plot().anchor.lat.toFixed(6));
    expect(osm).toContain(realDestinations()[0].lat.toFixed(6));
    w.findAll(".route-card__links a").forEach(a => {
      expect(a.attributes("rel")).toContain("noopener");
      expect(a.attributes("target")).toBe("_blank");
    });
  });

  it("sagt dazu, wenn OpenStreetMap den schnellsten Modus nicht kann", () => {
    // In the recorded data the car is fastest everywhere, so the note stays
    // away. Make transit the fastest and it has to appear — OSM has no public
    // transport engine and would silently route by car instead.
    const p = plot();
    const hbf = p.routes[HBF].modes;
    hbf.transit.duration_s = 60;
    expect(mount(RouteCards, { props: { plot: p } }).text()).toContain("kennt keinen ÖPNV");

    hbf.transit.duration_s = 1920;
    expect(mount(RouteCards, { props: { plot: p } }).text()).not.toContain("kennt keinen ÖPNV");
  });

  it("verlinkt nichts ohne Koordinaten", () => {
    const withoutAnchor = { ...plot() };
    delete withoutAnchor.anchor;
    const w = mount(RouteCards, { props: { plot: withoutAnchor } });
    expect(w.findAll(".route-card__links")).toHaveLength(0);
  });

  it("die Links verschwinden im Druck", () => {
    const w = mount(RouteCards, { props: { plot: plot() } });
    // Paper cannot be clicked; the class print.css hides must be on them.
    w.findAll(".route-card__links").forEach(p => {
      expect(p.classes()).toContain("no-print");
    });
  });
});
