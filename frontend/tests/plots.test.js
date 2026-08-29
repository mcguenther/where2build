/**
 * Builds plots from the answers the services really gave.
 *
 * The fixtures in `tests/fixtures/` are recorded responses, not hand-written
 * examples — re-record them with the script in the README when a service
 * changes. That is the point: a test built on invented data proves nothing
 * about a service that has moved on.
 */
import { describe, it, expect } from "vitest";
import konvex from "./fixtures/parcel-konvex.json";
import konkav from "./fixtures/parcel-konkav.json";
import elk from "./fixtures/housetype-elk.json";
import { plotAusKataster, outerRing, tidyRing, guessStreetEdge } from "../src/lib/plots.js";
import { haustypAusAntwort } from "../src/lib/houseTypes.js";
import { polygonArea, buildableArea, isConvex, polygonEdges, distanceToBoundary } from "../src/lib/geometry.js";
import { toLocal, anchorOf } from "../src/lib/projection.js";

describe("Flurstück aus dem Kataster", () => {
  it("übernimmt Kennzeichen, Gemarkung und Lage aus der Antwort", () => {
    const plot = plotAusKataster(konkav);
    expect(plot.gemarkung).toBe("Liebertwolkwitz");
    expect(plot.flurstuecke).toEqual(["85/1"]);
    expect(plot.kennzeichen).toMatch(/^\d{6}/);
    expect(plot.lagebezeichnung).toContain("Kirchstraße");
  });

  it("nimmt die amtliche Fläche, nicht die gerechnete", () => {
    const plot = plotAusKataster(konkav);
    expect(plot.flaecheAmtlich).toBe(1685);
    const gerechnet = polygonArea(plot.polygon);
    expect(gerechnet).toBeGreaterThan(1600);
    expect(gerechnet).toBeLessThan(1700);
    // Sie dürfen nicht identisch sein — sonst wurde die falsche Zahl übernommen.
    expect(Math.abs(plot.flaecheAmtlich - gerechnet)).toBeGreaterThan(0.5);
    expect(Math.abs(plot.flaecheAmtlich - gerechnet)).toBeLessThan(20);
  });

  it("georeferenziert das Grundstück nach Sachsen", () => {
    for (const antwort of [konvex, konkav]) {
      const plot = plotAusKataster(antwort);
      expect(plot.anker.lat).toBeGreaterThan(50);
      expect(plot.anker.lat).toBeLessThan(53);
      expect(plot.anker.lon).toBeGreaterThan(11.5);
      expect(plot.anker.lon).toBeLessThan(15.5);
    }
  });

  it("räumt den Ring auf: kein doppelter Schlusspunkt, keine Zwillinge", () => {
    const plot = plotAusKataster(konkav);
    const erster = plot.polygon[0], letzter = plot.polygon[plot.polygon.length - 1];
    expect(Math.hypot(erster.x - letzter.x, erster.y - letzter.y)).toBeGreaterThan(0.1);
    polygonEdges(plot.polygon).forEach(k => expect(k.length).toBeGreaterThan(0.09));
  });

  it("erfindet nichts, was das Kataster nicht liefert", () => {
    const plot = plotAusKataster(konkav);
    expect(plot.kaufpreis).toBeNull();
    expect(plot.bodenrichtwert).toBeNull();
    expect(plot.wege).toEqual({});
  });

  it("übernimmt, was der Aufrufer beisteuert", () => {
    const plot = plotAusKataster(konkav, { kaufpreis: 349000, bodenrichtwert: 210, name: "Testfall" });
    expect(plot.kaufpreis).toBe(349000);
    expect(plot.bodenrichtwert).toBe(210);
    expect(plot.name).toBe("Testfall");
  });

  it("wehrt sich gegen eine Antwort ohne Geometrie", () => {
    expect(() => plotAusKataster({ features: [] })).toThrow(/Geometrie/);
    expect(() => plotAusKataster(null)).toThrow();
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
    expect(isConvex(plotAusKataster(konvex).polygon)).toBe(true);
    expect(isConvex(plotAusKataster(konkav).polygon)).toBe(false);
  });

  it("liefert auch für das konkave Flurstück ein Bebauungsfenster", () => {
    const plot = plotAusKataster(konkav);
    const fenster = buildableArea(plot.polygon, plot.tiefen);
    expect(fenster.length).toBeGreaterThan(3);
    expect(polygonArea(fenster)).toBeGreaterThan(100);
  });

  it("ist bei der Näherung nie großzügiger als die Vorschrift", () => {
    for (const antwort of [konvex, konkav]) {
      const plot = plotAusKataster(antwort);
      const fenster = buildableArea(plot.polygon, plot.tiefen);
      for (const p of fenster) {
        expect(distanceToBoundary(p, plot.polygon)).toBeGreaterThanOrEqual(3 - 1e-6);
      }
    }
  });
});

describe("Haustyp aus der Herstellerseite", () => {
  it("trennt bebaute Fläche und Wohnfläche", () => {
    const typ = haustypAusAntwort(elk);
    expect(typ.bebauteFlaeche).toBe(96.88);
    expect(typ.wohnflaeche).toBe(159.21);
    // Der teuerste Fehler des Projekts: die Wohnfläche auf die Karte legen.
    expect(typ.bebauteFlaeche).toBeLessThan(typ.wohnflaeche);
  });

  it("führt Hersteller, Bezeichnung und Quelle mit", () => {
    const typ = haustypAusAntwort(elk);
    expect(typ.hersteller).toBe("ELK");
    expect(typ.name).toBe("All in One 159");
    expect(typ.quelle).toMatch(/^https?:\/\//);
    expect(typ.gelesenAm).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it("erfindet keine Außenmaße, wenn das Datenblatt keine nennt", () => {
    const typ = haustypAusAntwort(elk);
    expect(typ.laenge).toBeNull();
    expect(typ.breite).toBeNull();
    expect(typ.verhaeltnis).toBe(1.35);   // Schätzverhältnis, im Lageplan korrigierbar
  });

  it("weist eine Antwort ohne bebaute Fläche zurück, statt zu raten", () => {
    expect(() => haustypAusAntwort({ felder: { hersteller: { wert: "X" } } })).toThrow(/bebaute Fläche/);
    expect(() => haustypAusAntwort({})).toThrow();
  });

  it("macht aus den Dachformen einen lesbaren Text", () => {
    expect(haustypAusAntwort(elk).dachform).toBe("Walmdach oder Satteldach");
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
    const wgs = outerRing(konkav.grundstueck.geometry);
    const anker = anchorOf(wgs);
    const lokal = tidyRing(toLocal(wgs, anker));
    expect(lokal.length).toBeGreaterThan(3);
    expect(lokal.every(p => Number.isFinite(p.x) && Number.isFinite(p.y))).toBe(true);
  });
});
