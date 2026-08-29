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
import { echtesGrundstueck, echteWege, echteZiele } from "./hilfe.js";

const HBF = "zl-hbf";
const SCHULE = "zl-schule";

const standMitWegen = () => {
  const plot = { ...echtesGrundstueck("konvex"), wege: echteWege() };
  return validate({ version: 1, grundstuecke: [plot], haustypen: [], ziele: echteZiele(), auswahl: [] });
};

beforeEach(() => { state.daten = standMitWegen(); });

const plot = () => state.daten.grundstuecke[0];

describe("Aufbereitung echter MOTIS-Geometrie", () => {
  it("übersteht die Prüfung des Speichers unbeschädigt", () => {
    const weg = plot().wege[HBF];
    expect(Object.keys(weg.modi).sort()).toEqual(["bike", "car", "transit"]);
    expect(weg.modi.car.duration_s).toBe(754);
    expect(weg.modi.car.geometry.coordinates.length).toBe(455);
  });

  it("hält die Fahrzeiten in der Reihenfolge, die die Strecke erwarten lässt", () => {
    const m = plot().wege[HBF].modi;
    // 10 km in die Stadt: mit dem Auto am schnellsten, mit dem Rad am längsten.
    expect(m.car.duration_s).toBeLessThan(m.transit.duration_s);
    expect(m.transit.duration_s).toBeLessThan(m.bike.duration_s);
    expect(fastestMode(plot().wege[HBF])).toBe("car");
  });

  it("erkennt ein Ziel ohne Verbindung als solches", () => {
    const transit = plot().wege[SCHULE].modi.transit;
    expect(transit.erreichbar).toBe(false);
    expect(transit.duration_s).toBeUndefined();
    expect(transit.geometry).toBeUndefined();
    expect(fastestMode(plot().wege[SCHULE])).toBe("car");
  });

  it("liest Koordinaten nur aus einer echten Linie", () => {
    expect(coordinatesOf(null)).toBeNull();
    expect(coordinatesOf({ type: "Point", coordinates: [12, 51] })).toBeNull();
    expect(coordinatesOf({ type: "LineString", coordinates: [[12, 51]] })).toBeNull();
    expect(coordinatesOf(plot().wege[HBF].modi.car.geometry)).toHaveLength(455);
  });
});

describe("Einpassen in die Kartenfläche", () => {
  const linien = () => ["car", "bike", "transit"]
    .map(a => coordinatesOf(state.daten.grundstuecke[0].wege[HBF].modi[a]?.geometry))
    .filter(Boolean);

  it("umfasst jeden Punkt jeder Linie", () => {
    const b = routeBounds(linien());
    linien().flat().forEach(([lon, lat]) => {
      expect(lon).toBeGreaterThanOrEqual(b.minLon - 1e-9);
      expect(lon).toBeLessThanOrEqual(b.maxLon + 1e-9);
      expect(lat).toBeGreaterThanOrEqual(b.minLat - 1e-9);
      expect(lat).toBeLessThanOrEqual(b.maxLat + 1e-9);
    });
  });

  it("bleibt im Bild und hält den Rand ein", () => {
    const fit = fitBounds(routeBounds(linien()), 300, 150, 12);
    linien().flat().forEach(c => {
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
    const fit = fitBounds(routeBounds(linien()), 300, 150, 12);
    const b = routeBounds(linien());
    const mitte = [(b.minLon + b.maxLon) / 2, (b.minLat + b.maxLat) / 2];
    const a = toScreen(mitte, fit);
    const ost = toScreen([mitte[0] + 0.001, mitte[1]], fit);
    const nord = toScreen([mitte[0], mitte[1] + 0.001 * Math.cos(mitte[1] * Math.PI / 180)], fit);
    expect(Math.abs(ost.x - a.x)).toBeCloseTo(Math.abs(nord.y - a.y), 3);
  });

  it("misst die Bildbreite in echten Metern", () => {
    // Liebertwolkwitz to the Hauptbahnhof spans about 5.5 km east-west.
    const m = groundWidth(routeBounds(linien()));
    expect(m).toBeGreaterThan(4500);
    expect(m).toBeLessThan(7000);
  });

  it("macht aus einer Linie einen zeichenbaren Punktzug", () => {
    const fit = fitBounds(routeBounds(linien()), 300, 150, 12);
    const punkte = toPolyline(linien()[0], fit);
    expect(punkte.split(" ")).toHaveLength(455);
    expect(punkte).toMatch(/^[\d.,\s-]+$/);
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

  it("sagt beim Verkehrsmittel ohne Verbindung, dass keine gefunden wurde", () => {
    const t = mount(RouteCards, { props: { plot: plot() } }).text();
    expect(t).toContain("keine Verbindung gefunden");
  });

  it("hebt das schnellste Verkehrsmittel hervor und zeichnet es zuletzt", () => {
    const w = mount(RouteCards, { props: { plot: plot() } });
    const ersteKarte = w.findAll("article")[0].findAll("polyline");
    const dickste = ersteKarte[ersteKarte.length - 1];
    expect(dickste.attributes("stroke-width")).toBe("3.4");
    expect(dickste.attributes("opacity")).toBe("1");
  });

  it("nennt den Stand der Berechnung und die Quelle", () => {
    const t = mount(RouteCards, { props: { plot: plot() } }).text();
    expect(t).toContain("29.08.2026");
    expect(t).toContain("MOTIS");
  });

  it("wirft erfundene Wege aus dem Mockup beim Laden weg", () => {
    // The mockup stored an array of made-up minutes under the same key.
    const stand = validate({
      version: 1,
      grundstuecke: [{ ...echtesGrundstueck("konvex"), wege: { [HBF]: [14, 38, 29, 31, "a", "b", "c"] } }],
      haustypen: [], ziele: echteZiele(), auswahl: []
    });
    expect(stand.grundstuecke[0].wege).toEqual({});
    const t = mount(RouteCards, { props: { plot: stand.grundstuecke[0] } }).text();
    expect(t).toContain("Noch nicht berechnet");
    expect(t).not.toMatch(/\d+ min/);
  });

  it("vergisst Wege zu einem Ziel, das es nicht mehr gibt", () => {
    const stand = validate({
      version: 1,
      grundstuecke: [{ ...echtesGrundstueck("konvex"), wege: echteWege() }],
      haustypen: [], ziele: [echteZiele()[0]], auswahl: []
    });
    expect(Object.keys(stand.grundstuecke[0].wege)).toEqual([HBF]);
  });
});
