/**
 * The street front, read off the cadastre instead of guessed.
 *
 * The traffic parcels are real `/api/parcels/streets` answers, recorded on
 * 23.09.2026 around each fixture plot. The longest-edge guess was wrong on
 * seven of these eight plots; the cases below are the ones it got wrong.
 */
import { describe, it, expect } from "vitest";
import { plotFromCadastre, guessStreetEdge } from "../src/lib/plots.js";
import { streetFront, streetNames, settleStreetFront } from "../src/lib/streetFront.js";
import { polygonEdges, streetDownRotation } from "../src/lib/geometry.js";
import { toWgs84 } from "../src/lib/projection.js";
import concave from "./fixtures/parcel-concave.json";
import convex from "./fixtures/parcel-convex.json";
import large from "./fixtures/parcel-large.json";
import moelkau from "./fixtures/parcel-moelkau.json";
import moelkau205 from "./fixtures/parcel-moelkau-205.json";
import moelkauZwei from "./fixtures/parcel-moelkau-zwei.json";
import streetsConcave from "./fixtures/verkehr-concave.json";
import streetsConvex from "./fixtures/verkehr-convex.json";
import streetsLarge from "./fixtures/verkehr-large.json";
import streetsMoelkau from "./fixtures/verkehr-moelkau.json";
import streetsMoelkau205 from "./fixtures/verkehr-moelkau-205.json";
import streetsMoelkauZwei from "./fixtures/verkehr-moelkau-zwei.json";

const front = (parcel, streets) => {
  const plot = plotFromCadastre(parcel);
  return { plot, found: streetFront(plot.polygon, plot.anchor, streets.features, plot.lagebezeichnung) };
};

describe("Straßenseite aus dem Kataster", () => {
  it("findet die Kirchstraße an der kurzen Westseite, nicht die längste Kante", () => {
    const { plot, found } = front(concave, streetsConcave);
    expect(found.street).toBe("Kirchstraße");
    expect(found.edge).not.toBe(guessStreetEdge(plot.polygon));
    // Almost the whole edge lies along the street, less the corners left out.
    expect(found.length).toBeGreaterThan(0.9 * (polygonEdges(plot.polygon)[found.edge].length - 2));
  });

  it.each([
    ["Lessingweg 44", moelkau, streetsMoelkau],
    ["Lessingweg 46", moelkau205, streetsMoelkau205],
    ["Lessingweg 44 aus zwei Flurstücken", moelkauZwei, streetsMoelkauZwei],
    ["Sommerfelder Straße 125", convex, streetsConvex]
  ])("nimmt bei %s die schmale Straßenseite eines tiefen Grundstücks", (_, parcel, streets) => {
    const { plot, found } = front(parcel, streets);
    const edges = polygonEdges(plot.polygon);
    expect(found).not.toBeNull();
    expect(found.edge).not.toBe(guessStreetEdge(plot.polygon));
    expect(edges[found.edge].length).toBeLessThan(edges[guessStreetEdge(plot.polygon)].length / 2);
    expect(plot.lagebezeichnung.toLowerCase()).toContain(found.street.toLowerCase());
  });

  it("findet auch ohne Adresse die Straße, an der das Grundstück liegt", () => {
    const { found } = front(large, streetsLarge);
    expect(found?.street).toBe("Radeburger Straße");
  });

  it("dreht das Grundstück so, dass die gefundene Straße unten liegt", () => {
    const { plot, found } = front(concave, streetsConcave);
    const r = (streetDownRotation(plot.polygon, found.edge) * Math.PI) / 180;
    const turned = plot.polygon.map(p => ({ x: p.x * Math.cos(r) + p.y * Math.sin(r), y: -p.x * Math.sin(r) + p.y * Math.cos(r) }));
    const edge = polygonEdges(turned)[found.edge];
    expect(Math.abs(edge.dy)).toBeLessThan(1e-9);
    const middle = turned.reduce((s, p) => s + p.y, 0) / turned.length;
    expect(edge.a.y).toBeLessThan(middle);
  });

  it("antwortet nichts, wenn keine Grenze an eine Verkehrsfläche stößt", () => {
    const plot = plotFromCadastre(concave);
    expect(streetFront(plot.polygon, plot.anchor, [], plot.lagebezeichnung)).toBeNull();
    // The Mölkau street is a few kilometres away.
    expect(streetFront(plot.polygon, plot.anchor, streetsMoelkau.features, plot.lagebezeichnung)).toBeNull();
  });

  it("zieht an der Ecke die Straße der eigenen Adresse der längeren vor", () => {
    // A 20 x 40 m plot with a street along its long east side and one along
    // its short south side; the address is on the short one.
    const anchor = { lat: 51.3, lon: 12.4 };
    const plot = [{ x: -10, y: -20 }, { x: 10, y: -20 }, { x: 10, y: 20 }, { x: -10, y: 20 }];
    const parcel = (name, ring) => ({
      properties: { lagebezeichnung: name },
      geometry: { type: "Polygon", coordinates: [toWgs84([...ring, ring[0]], anchor)] }
    });
    const south = parcel("Kurze Gasse", [{ x: -30, y: -28 }, { x: 30, y: -28 }, { x: 30, y: -20 }, { x: -30, y: -20 }]);
    const east = parcel("Lange Straße", [{ x: 10, y: -40 }, { x: 18, y: -40 }, { x: 18, y: 40 }, { x: 10, y: 40 }]);
    expect(streetFront(plot, anchor, [south, east], "Kurze Gasse 3").edge).toBe(0);
    expect(streetFront(plot, anchor, [south, east], "Lange Straße 3").edge).toBe(1);
    // No address to go by: the longer front wins.
    expect(streetFront(plot, anchor, [south, east], "ohne Lage").edge).toBe(1);
  });

  it("liest den Straßennamen aus der Lagebezeichnung", () => {
    expect(streetNames("Kirchstraße; Kirchstraße 4")).toEqual(["kirchstraße", "kirchstraße"]);
    expect(streetNames("Kirchstraße 8, 8a")).toEqual(["kirchstraße"]);
    expect(streetNames("Radeburger Straße, Ortsteil Moritzburg")).toEqual(["radeburger straße"]);
    expect(streetNames("Hauptstr. 12-14")).toEqual(["hauptstraße"]);
    expect(streetNames("ohne Lage")).toEqual([]);
  });

  it("schreibt die Antwort auf das Grundstück und merkt sich eine leere", async () => {
    const plot = plotFromCadastre(concave);
    let asked = null;
    await settleStreetFront(plot, async (lat, lon, box) => { asked = { lat, lon, box }; return streetsConcave; });
    expect(plot.streetFront.street).toBe("Kirchstraße");
    expect(plot.streetEdge).toBe(streetFront(plot.polygon, plot.anchor, streetsConcave.features, plot.lagebezeichnung).edge);
    // The box holds the whole plot and its street.
    expect(asked.box).toBeGreaterThan(Math.max(...plot.polygon.map(v => Math.abs(v.x))) + 10);

    const lonely = plotFromCadastre(concave);
    const guess = lonely.streetEdge;
    await settleStreetFront(lonely, async () => ({ features: [] }));
    expect(lonely.streetFront).toBeNull();
    expect(lonely.streetEdge).toBe(guess);

    const failing = plotFromCadastre(concave);
    await expect(settleStreetFront(failing, async () => { throw new Error("502"); })).rejects.toThrow();
    expect(failing.streetFront).toBeUndefined();
  });
});
