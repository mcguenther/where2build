/**
 * The picture on a candidate's card, on the parcels a real ambiguous run
 * returned (Großbothen, 23.09.2026).
 */
import { describe, expect, it } from "vitest";
import AMBIGUOUS from "./fixtures/suche-grossbothen-mehrdeutig.ndjson?raw";
import { MIN_HALF_WIDTH_M, candidateSketch, sketchCaption } from "../src/lib/candidateSketch.js";

const [garden, house] = JSON.parse(AMBIGUOUS.trim()).kandidaten;

describe("Das Bild eines Vorschlags", () => {
  it("zeigt das Flurstück mit Umgebung, nicht randvoll", () => {
    const sketch = candidateSketch(garden.geometry);

    // A plot and a neighbour either side, at the least.
    expect(sketch.groundWidthM).toBeGreaterThanOrEqual(2 * MIN_HALF_WIDTH_M - 1);
    expect(sketch.path).toMatch(/^M[\d.]+ [\d.]+ L/);
    // Every point of the outline inside the frame, with room to spare.
    const numbers = sketch.path.match(/[\d.]+/g).map(Number);
    const xs = numbers.filter((_, i) => i % 2 === 0);
    const ys = numbers.filter((_, i) => i % 2 === 1);
    expect(Math.min(...xs)).toBeGreaterThan(20);
    expect(Math.max(...xs)).toBeLessThan(sketch.width - 20);
    expect(Math.min(...ys)).toBeGreaterThan(10);
    expect(Math.max(...ys)).toBeLessThan(sketch.height - 10);
  });

  it("legt die Katastergrenzen über das Luftbild, weil es nah genug ist", () => {
    const sketch = candidateSketch(house.geometry);

    expect(sketch.photo.length).toBeGreaterThan(0);
    expect(sketch.photo[0].href).toMatch(/^\/api\/tiles\/luftbild\/1[89]\//);
    expect(sketch.cadastre.map(t => t.key)).toEqual(sketch.photo.map(t => t.key));
    expect(sketch.cadastre[0].href).toContain("/api/tiles/liegenschaftskarte/");
  });

  it("zeichnet ohne Umring nichts", () => {
    expect(candidateSketch(null)).toBeNull();
    expect(candidateSketch({ type: "Point", coordinates: [12.7, 51.2] })).toBeNull();
  });

  it("nennt die Bildbreite", () => {
    expect(sketchCaption(123)).toBe("Bildbreite rund 120 m");
    expect(sketchCaption(1540)).toBe("Bildbreite rund 1,5 km");
    expect(sketchCaption(0)).toBe("");
  });
});
