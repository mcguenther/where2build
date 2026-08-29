/**
 * Builds plots from the answers the services really gave.
 *
 * The fixtures in `tests/fixtures/` are recorded responses, not hand-written
 * examples — re-record them with the script in the README when a service
 * changes. That is the point: a test built on invented data proves nothing
 * about a service that has moved on.
 */
import { describe, it, expect } from "vitest";
import convex from "./fixtures/parcel-convex.json";
import concave from "./fixtures/parcel-concave.json";
import elk from "./fixtures/housetype-elk.json";
import { plotFromCadastre, outerRing, tidyRing, guessStreetEdge } from "../src/lib/plots.js";
import { houseTypeFromResponse } from "../src/lib/houseTypes.js";
import { polygonArea, buildableArea, isConvex, polygonEdges, distanceToBoundary } from "../src/lib/geometry.js";
import { toLocal, anchorOf } from "../src/lib/projection.js";

describe("Flurstück aus dem Kataster", () => {
  it("übernimmt Kennzeichen, Gemarkung und Lage aus der Antwort", () => {
    const plot = plotFromCadastre(concave);
    expect(plot.gemarkung).toBe("Liebertwolkwitz");
    expect(plot.flurstuecke).toEqual(["85/1"]);
    expect(plot.kennzeichen).toMatch(/^\d{6}/);
    expect(plot.lagebezeichnung).toContain("Kirchstraße");
  });

  it("nimmt die amtliche Fläche, nicht die gerechnete", () => {
    const plot = plotFromCadastre(concave);
    expect(plot.officialArea).toBe(1685);
    const computed = polygonArea(plot.polygon);
    expect(computed).toBeGreaterThan(1600);
    expect(computed).toBeLessThan(1700);
    // Sie dürfen nicht identisch sein — sonst wurde die falsche Zahl übernommen.
    expect(Math.abs(plot.officialArea - computed)).toBeGreaterThan(0.5);
    expect(Math.abs(plot.officialArea - computed)).toBeLessThan(20);
  });

  it("georeferenziert das Grundstück nach Sachsen", () => {
    for (const response of [convex, concave]) {
      const plot = plotFromCadastre(response);
      expect(plot.anchor.lat).toBeGreaterThan(50);
      expect(plot.anchor.lat).toBeLessThan(53);
      expect(plot.anchor.lon).toBeGreaterThan(11.5);
      expect(plot.anchor.lon).toBeLessThan(15.5);
    }
  });

  it("räumt den Ring auf: kein doppelter Schlusspunkt, keine Zwillinge", () => {
    const plot = plotFromCadastre(concave);
    const first = plot.polygon[0], last = plot.polygon[plot.polygon.length - 1];
    expect(Math.hypot(first.x - last.x, first.y - last.y)).toBeGreaterThan(0.1);
    polygonEdges(plot.polygon).forEach(e => expect(e.length).toBeGreaterThan(0.09));
  });

  it("erfindet nichts, was das Kataster nicht liefert", () => {
    const plot = plotFromCadastre(concave);
    expect(plot.askingPrice).toBeNull();
    expect(plot.bodenrichtwert).toBeNull();
    expect(plot.routes).toEqual({});
  });

  it("übernimmt, was der Aufrufer beisteuert", () => {
    const plot = plotFromCadastre(concave, { askingPrice: 349000, bodenrichtwert: 210, name: "Testfall" });
    expect(plot.askingPrice).toBe(349000);
    expect(plot.bodenrichtwert).toBe(210);
    expect(plot.name).toBe("Testfall");
  });

  it("wehrt sich gegen eine Antwort ohne Geometrie", () => {
    expect(() => plotFromCadastre({ features: [] })).toThrow(/Geometrie/);
    expect(() => plotFromCadastre(null)).toThrow();
  });

  it("hält den Ring in beiden Geometrietypen", () => {
    expect(outerRing({ type: "Polygon", coordinates: [[[1, 2], [3, 4]]] })).toHaveLength(2);
    expect(outerRing({ type: "MultiPolygon", coordinates: [[[[1, 2], [3, 4], [5, 6]]]] })).toHaveLength(3);
    expect(outerRing(null)).toEqual([]);
  });

  it("nimmt die längste Kante als Straßenfront an", () => {
    const ring = [{ x: 0, y: 0 }, { x: 30, y: 0 }, { x: 30, y: 10 }, { x: 0, y: 10 }];
    expect([0, 2]).toContain(guessStreetEdge(ring));
    expect(polygonEdges(ring)[guessStreetEdge(ring)].length).toBe(30);
  });
});

describe("Echte Flurstücke sind oft nicht konvex", () => {
  it("erkennt beide Fälle in den aufgezeichneten Antworten", () => {
    expect(isConvex(plotFromCadastre(convex).polygon)).toBe(true);
    expect(isConvex(plotFromCadastre(concave).polygon)).toBe(false);
  });

  it("liefert auch für das konkave Flurstück ein Bebauungsfenster", () => {
    const plot = plotFromCadastre(concave);
    const envelope = buildableArea(plot.polygon, plot.setbacks);
    expect(envelope.length).toBeGreaterThan(3);
    expect(polygonArea(envelope)).toBeGreaterThan(100);
  });

  it("ist bei der Näherung nie großzügiger als die Vorschrift", () => {
    for (const response of [convex, concave]) {
      const plot = plotFromCadastre(response);
      const envelope = buildableArea(plot.polygon, plot.setbacks);
      for (const p of envelope) {
        expect(distanceToBoundary(p, plot.polygon)).toBeGreaterThanOrEqual(3 - 1e-6);
      }
    }
  });
});

describe("Haustyp aus der Herstellerseite", () => {
  it("trennt bebaute Fläche und Wohnfläche", () => {
    const type = houseTypeFromResponse(elk);
    expect(type.builtArea).toBe(96.88);
    expect(type.livingArea).toBe(159.21);
    // Der teuerste Fehler des Projekts: die Wohnfläche auf die Karte legen.
    expect(type.builtArea).toBeLessThan(type.livingArea);
  });

  it("führt Hersteller, Bezeichnung und Quelle mit", () => {
    const type = houseTypeFromResponse(elk);
    expect(type.manufacturer).toBe("ELK");
    expect(type.name).toBe("All in One 159");
    expect(type.source).toMatch(/^https?:\/\//);
    expect(type.readAt).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it("erfindet keine Außenmaße, wenn das Datenblatt keine nennt", () => {
    const type = houseTypeFromResponse(elk);
    expect(type.length).toBeNull();
    expect(type.width).toBeNull();
    expect(type.ratio).toBe(1.35);   // Schätzverhältnis, im Lageplan korrigierbar
  });

  it("weist eine Antwort ohne bebaute Fläche zurück, statt zu raten", () => {
    expect(() => houseTypeFromResponse({ felder: { hersteller: { wert: "X" } } })).toThrow(/bebaute Fläche/);
    expect(() => houseTypeFromResponse({})).toThrow();
  });

  it("macht aus den Dachformen einen lesbaren Text", () => {
    expect(houseTypeFromResponse(elk).roofShape).toBe("Walmdach oder Satteldach");
  });
});

describe("Ring aufräumen", () => {
  it("wirft den doppelten Schlusspunkt weg", () => {
    const ring = [{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 10, y: 10 }, { x: 0, y: 0 }];
    expect(tidyRing(ring)).toHaveLength(3);
  });

  it("legt zu dicht beieinanderliegende Punkte zusammen", () => {
    const ring = [{ x: 0, y: 0 }, { x: 0.01, y: 0 }, { x: 10, y: 0 }, { x: 10, y: 10 }];
    expect(tidyRing(ring)).toHaveLength(3);
  });

  it("überträgt echte Koordinaten verlustfrei genug", () => {
    const wgs = outerRing(concave.grundstueck.geometry);
    const anchor = anchorOf(wgs);
    const local = tidyRing(toLocal(wgs, anchor));
    expect(local.length).toBeGreaterThan(3);
    expect(local.every(p => Number.isFinite(p.x) && Number.isFinite(p.y))).toBe(true);
  });
});
