/**
 * The distance band as a shape — and above all as a shape with a hole.
 *
 * The numbers are the ones measured on 16.09.2026 against the live cadastre:
 * Grimma's built-up outline seen from Flurstück 790/11 reads 5,3 km at its edge
 * and 6,0 km at its middle, and the advert's „ca. 6 km" is the band 4,6 to
 * 7,5 km.
 */
import { describe, expect, it } from "vitest";
import { bandFeatures, bandPolygon, circle, convexHull, offsetConvex } from "../src/lib/bands.js";
import { anchorOf, toLocal } from "../src/lib/projection.js";

const GRIMMA = [12.7167, 51.2333];

/** A square kilometre around Grimma, as the outline stands in for a town. */
const town = {
  type: "Polygon",
  coordinates: [[
    [12.7100, 51.2300], [12.7240, 51.2300], [12.7240, 51.2370],
    [12.7100, 51.2370], [12.7100, 51.2300]
  ]]
};

const band = {
  meter: 6000, innen_m: 6000 / 1.3, aussen_m: 7500,
  bezug: "Grimma", modus: "strecke", aufgeloest: true,
  umriss: town,
  mitte: { type: "Point", coordinates: GRIMMA }
};

const metresFromMiddle = ([lon, lat]) => {
  const [point] = toLocal([[lon, lat]], anchorOf([GRIMMA]));
  return Math.hypot(point.x, point.y);
};

describe("bandPolygon", () => {
  it("draws a ring, not a disc", () => {
    const polygon = bandPolygon(band);
    expect(polygon.type).toBe("Polygon");
    expect(polygon.coordinates).toHaveLength(2);

    // The hole is the point: a candidate nearer the middle than the inner
    // bound fails the statement exactly as one beyond the outer bound does,
    // and a filled disc would say the opposite.
    const hole = polygon.coordinates[1].map(metresFromMiddle);
    expect(Math.min(...hole)).toBeCloseTo(band.innen_m, -1);
    expect(Math.max(...hole)).toBeCloseTo(band.innen_m, -1);
  });

  it("puts the outer edge a full außen_m beyond the outline", () => {
    const outer = bandPolygon(band).coordinates[0].map(metresFromMiddle);
    // The town is ~490 m from its middle to a corner, so the offset ring lies
    // between außen and außen + that.
    expect(Math.min(...outer)).toBeGreaterThan(band.aussen_m * 0.99);
    expect(Math.max(...outer)).toBeLessThan(band.aussen_m + 1000);
  });

  it("is nothing at all when the reference could not be resolved", () => {
    // „Bushaltestelle ca. 300 m“ — a kind of place has no outline.
    expect(bandPolygon({ ...band, aufgeloest: false })).toBeNull();
    expect(bandPolygon({ ...band, umriss: null })).toBeNull();
    expect(bandPolygon(null)).toBeNull();
  });
});

describe("bandFeatures", () => {
  it("takes only the distance Indizien that carry a drawable band", () => {
    const features = bandFeatures([
      { id: "e1", art: "entfernung", band },
      { id: "e2", art: "entfernung", band: { ...band, aufgeloest: false } },
      { id: "e0", art: "entfernung", band: null },
      { id: "i3", art: "gemarkung", wert: "Großbothen" },
      { id: "e4", art: "entfernung", band, verworfen: true }
    ]);
    expect(features.map(f => f.properties.id)).toEqual(["e1"]);
    expect(features[0].properties.bezug).toBe("Grimma");
  });
});

describe("offsetConvex", () => {
  it("rounds the corners instead of mitring them off to a spike", () => {
    const square = convexHull([
      { x: 0, y: 0 }, { x: 100, y: 0 }, { x: 100, y: 100 }, { x: 0, y: 100 }
    ]);
    const offset = offsetConvex(square, 50);
    const far = Math.max(...offset.map(p => Math.hypot(p.x - 50, p.y - 50)));
    // A mitre at the corner would reach 50·√2 ≈ 70,7 m past it; an arc reaches
    // exactly 50, which puts the furthest point at √(50²+50²) + 50.
    expect(far).toBeCloseTo(Math.hypot(50, 50) + 50, 0);
  });

  it("falls back to a circle when the outline is a single point", () => {
    expect(offsetConvex([{ x: 0, y: 0 }], 100)).toHaveLength(circle({ x: 0, y: 0 }, 100).length);
  });
});

describe("convexHull", () => {
  it("drops the points inside and keeps the ring counter-clockwise", () => {
    const hull = convexHull([
      { x: 0, y: 0 }, { x: 10, y: 0 }, { x: 10, y: 10 }, { x: 0, y: 10 }, { x: 5, y: 5 }
    ]);
    expect(hull).toHaveLength(4);
    const area = hull.reduce((sum, p, i) => {
      const q = hull[(i + 1) % hull.length];
      return sum + (p.x * q.y - q.x * p.y);
    }, 0);
    expect(area).toBeGreaterThan(0);
  });
});
