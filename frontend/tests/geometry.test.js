/** The maths every figure in the interface rests on. */
import { describe, it, expect } from "vitest";
import {
  polygonArea, polygonEdges, polygonPerimeter, asCounterClockwise, boundingBox,
  buildableArea, minimumRotatedRectangle, rectangularity, shapeClass,
  pointInPolygon, distanceToBoundary, closestBoundaryPoint,
  rectangleCorners, cornersOutside, smallestSetback, footprintFromArea,
  findPlacement, fitsAnywhere, alignmentToEdge, alignToEdge, edgeCompass
} from "../src/lib/geometry.js";

import { echtesGrundstueck } from "./hilfe.js";

const ring = pairs => pairs.map(([x, y]) => ({ x, y }));
const SQUARE = ring([[0, 0], [10, 0], [10, 10], [0, 10]]);
const LIEBERTWOLKWITZ = ring([[0, 0], [22.6, 0.9], [24.3, 34.9], [1.6, 36.2]]);

describe("Flächen und Kanten", () => {
  it("misst ein bekanntes Quadrat", () => {
    expect(polygonArea(SQUARE)).toBe(100);
    expect(polygonPerimeter(SQUARE)).toBe(40);
  });

  it("misst das Beispielflurstück und weicht plausibel von der amtlichen Fläche ab", () => {
    const gerechnet = polygonArea(LIEBERTWOLKWITZ);
    expect(gerechnet).toBeCloseTo(795.3, 1);
    const abweichung = Math.abs(802 - gerechnet);
    expect(abweichung).toBeGreaterThan(0);
    expect(abweichung).toBeLessThan(15);
  });

  it("liefert die Kantenlängen, die die Oberfläche anzeigt", () => {
    expect(polygonEdges(LIEBERTWOLKWITZ).map(k => +k.length.toFixed(2)))
      .toEqual([22.62, 34.04, 22.74, 36.24]);
  });

  it("dreht eine im Uhrzeigersinn gegebene Kontur um", () => {
    const cw = [...SQUARE].reverse();
    expect(polygonArea(asCounterClockwise(cw))).toBe(100);
    expect(asCounterClockwise(cw)[0]).not.toEqual(cw[0]);
  });

  it("bestimmt die Hüllbox", () => {
    expect(boundingBox(SQUARE)).toMatchObject({ minX: 0, maxX: 10, width: 10, height: 10 });
  });
});

describe("Bebauungsfenster", () => {
  it("setzt 3 m ringsum ein 10-m-Quadrat auf 4 × 4 m zurück", () => {
    const f = buildableArea(SQUARE, [3, 3, 3, 3]);
    expect(f).toHaveLength(4);
    expect(polygonArea(f)).toBeCloseTo(16, 9);
  });

  it("wirkt je Grenzsegment einzeln — § 6 SächsBO misst nach Wandhöhe", () => {
    expect(polygonArea(buildableArea(SQUARE, [5, 3, 3, 3]))).toBeCloseTo(8, 9);
    expect(polygonArea(buildableArea(SQUARE, [3, 3, 5, 3]))).toBeCloseTo(8, 9);
  });

  it("nimmt auch eine einzelne Zahl statt einer Liste", () => {
    expect(polygonArea(buildableArea(SQUARE, 3))).toBeCloseTo(16, 9);
  });

  it("liefert nichts, wenn die Abstände das Grundstück aufzehren", () => {
    expect(buildableArea(SQUARE, [6, 6, 6, 6])).toEqual([]);
  });

  it("hält überall den geforderten Abstand ein", () => {
    for (const p of buildableArea(LIEBERTWOLKWITZ, [3, 3, 3, 3])) {
      expect(distanceToBoundary(p, LIEBERTWOLKWITZ)).toBeGreaterThan(2.99);
    }
  });
});

describe("Form", () => {
  it("gibt dem Quadrat die Rechteckigkeit 1", () => {
    expect(rectangularity(SQUARE)).toBeCloseTo(1, 9);
  });

  it("stuft das Beispielflurstück ein", () => {
    expect(rectangularity(LIEBERTWOLKWITZ)).toBeCloseTo(0.965, 3);
    expect(shapeClass(rectangularity(LIEBERTWOLKWITZ))).toBe("rechteckig");
  });

  it("kennt die drei Stufen aus der Vorprojekt-Notiz", () => {
    expect(shapeClass(0.97)).toBe("rechteckig");
    expect(shapeClass(0.9)).toBe("fast rechteckig");
    expect(shapeClass(0.7)).toBe("komplex");
  });

  it("findet das kleinste gedrehte Umschließungsrechteck", () => {
    const schraeg = ring([[0, 0], [10, 10], [8, 12], [-2, 2]]);
    const mrr = minimumRotatedRectangle(schraeg);
    expect(mrr.area).toBeCloseTo(polygonArea(schraeg), 6);   // ein gedrehtes Rechteck ist sein eigenes MRR
  });
});

describe("Baukörper", () => {
  it("leitet aus 96,88 m² bei Verhältnis 1,35 rund 11,4 × 8,5 m ab", () => {
    const f = footprintFromArea(96.88, 1.35);
    expect(f.width).toBeCloseTo(11.44, 2);
    expect(f.depth).toBeCloseTo(8.47, 2);
    expect(f.width * f.depth).toBeCloseTo(96.88, 9);
  });

  it("erhält bei Drehung die Grundfläche", () => {
    const A = rot => polygonArea(rectangleCorners({ cx: 10, cy: 15, width: 11.4, depth: 8.5, rotation: rot }));
    expect(A(0)).toBeCloseTo(A(37), 9);
  });

  it("schlägt an, sobald eine Ecke aus dem Fenster rutscht", () => {
    const fenster = buildableArea(LIEBERTWOLKWITZ, [3, 3, 3, 3]);
    const drin = { cx: 10.8, cy: 15, width: 11.4, depth: 8.5, rotation: -4 };
    const raus = { cx: 10.8, cy: 32, width: 11.4, depth: 8.5, rotation: -4 };
    expect(cornersOutside(drin, fenster)).toBe(0);
    expect(cornersOutside(raus, fenster)).toBeGreaterThan(0);
  });

  it("misst den geringsten Grenzabstand", () => {
    const mitte = { cx: 5, cy: 5, width: 4, depth: 4, rotation: 0 };
    expect(smallestSetback(mitte, SQUARE)).toBeCloseTo(3, 9);
  });

  it("findet den nächsten Punkt auf der Grenze", () => {
    const nah = closestBoundaryPoint({ x: 5, y: 8 }, SQUARE);
    expect(nah.distance).toBeCloseTo(2, 9);
    expect(nah.point).toEqual({ x: 5, y: 10 });
  });
});

describe("Passt der Baukörper?", () => {
  const fenster = buildableArea(SQUARE, [1, 1, 1, 1]);   // 8 × 8 m

  it("findet eine zulässige Lage", () => {
    const lage = findPlacement(fenster, 7, 5);
    expect(lage).not.toBeNull();
    expect(cornersOutside({ ...lage, width: 7, depth: 5 }, fenster)).toBe(0);
  });

  it("meldet, wenn nichts passt", () => {
    expect(findPlacement(fenster, 9, 9)).toBeNull();
    expect(fitsAnywhere(fenster, 9, 9)).toBe(false);
  });

  it("nutzt die Drehung — quer passt, was längs nicht passt", () => {
    const schmal = buildableArea(ring([[0, 0], [9, 0], [9, 26], [0, 26]]), [0.5, 0.5, 0.5, 0.5]);
    expect(findPlacement(schmal, 20, 6)).not.toBeNull();
    expect(findPlacement(schmal, 20, 6, { rotation: 0 })).toBeNull();
  });

  it("bleibt mit „near“ in der Nähe der bisherigen Lage", () => {
    const nah = findPlacement(fenster, 3, 3, { near: { x: 3, y: 3 } });
    const fern = findPlacement(fenster, 3, 3, { near: { x: 8, y: 8 } });
    expect(Math.hypot(nah.cx - 3, nah.cy - 3)).toBeLessThan(Math.hypot(fern.cx - 3, fern.cy - 3));
  });
});

describe("An der Straße ausrichten", () => {
  it("liefert den Winkel der Straßenfront", () => {
    expect(alignmentToEdge(LIEBERTWOLKWITZ, 0)).toBeCloseTo(2.28, 2);
    expect(alignmentToEdge(SQUARE, 0)).toBeCloseTo(0, 9);
  });

  it("normiert auf (−90°, 90°]", () => {
    const nachOben = ring([[0, 0], [0, 10], [-10, 10], [-10, 0]]);
    const winkel = alignmentToEdge(nachOben, 0);
    expect(winkel).toBeGreaterThan(-90);
    expect(winkel).toBeLessThanOrEqual(90);
  });

  it("dreht den Baukörper parallel zur Front und lässt ihn im Fenster", () => {
    const fenster = buildableArea(LIEBERTWOLKWITZ, [3, 3, 3, 3]);
    const vorher = { cx: 10.8, cy: 15, width: 11.4, depth: 8.5, rotation: 40 };
    const nachher = alignToEdge(LIEBERTWOLKWITZ, fenster, vorher, 0);
    expect(nachher.rotation).toBeCloseTo(2.28, 2);
    expect(cornersOutside(nachher, fenster)).toBe(0);
  });

  it("schiebt zurück ins Fenster, wenn die Drehung herausführt", () => {
    const fenster = buildableArea(LIEBERTWOLKWITZ, [3, 3, 3, 3]);
    const amRand = { cx: 5.5, cy: 30, width: 11.4, depth: 8.5, rotation: 80 };
    const nachher = alignToEdge(LIEBERTWOLKWITZ, fenster, amRand, 0);
    expect(cornersOutside(nachher, fenster)).toBe(0);
    expect(nachher.cx === amRand.cx && nachher.cy === amRand.cy).toBe(false);
  });
});

describe("Himmelsrichtungen der Grenzen", () => {
  it("benennt die Grenzen statt sie durchzunummerieren", () => {
    const namen = LIEBERTWOLKWITZ.map((_, i) => edgeCompass(LIEBERTWOLKWITZ, i, 17));
    expect(namen).toEqual(["Süd", "Ost", "Nord", "West"]);
  });

  /* Der Nordversatz ist der Winkel, um den der Nordpfeil gegenüber "oben"
     gegen den Uhrzeigersinn gedreht ist — dieselbe Konvention wie in SitePlan.
     Bei 90° zeigt Nord nach links, die untere Kante also nach Westen. */
  it("dreht mit dem Nordversatz mit", () => {
    expect(edgeCompass(SQUARE, 0, 0)).toBe("Süd");
    expect(edgeCompass(SQUARE, 0, 90)).toBe("West");
    expect(edgeCompass(SQUARE, 0, 180)).toBe("Nord");
    expect(edgeCompass(SQUARE, 0, 270)).toBe("Ost");
  });

  /* Die untere Kante des Quadrats bleibt liegen; gedreht wird nur der Nordpfeil.
     Läuft Nord gegen den Uhrzeigersinn, wandert der Name der Kante im
     Uhrzeigersinn durch die Windrose. Von Hand nachprüfbar: */
  it("wandert im Uhrzeigersinn durch die Windrose, wenn Nord sich dreht", () => {
    const erwartet = {
      0: "Süd", 45: "Südwest", 90: "West", 135: "Nordwest",
      180: "Nord", 225: "Nordost", 270: "Ost", 315: "Südost"
    };
    for (const [versatz, name] of Object.entries(erwartet)) {
      expect(edgeCompass(SQUARE, 0, Number(versatz))).toBe(name);
    }
  });
});

describe("Punkt im Polygon", () => {
  it("unterscheidet innen und außen", () => {
    expect(pointInPolygon({ x: 5, y: 5 }, SQUARE)).toBe(true);
    expect(pointInPolygon({ x: 15, y: 5 }, SQUARE)).toBe(false);
  });
});

describe("Große und vielgliedrige Flurstücke", () => {
  /**
   * Two parcels that ALKIS really returned. The strip is what a district
   * address resolves to — 21 585 m² and 159 boundary points across a
   * 1583 × 198 m ribbon. At a fixed 0.4 m grid that is two million cells and
   * 314 million distance computations: the tab locks up long enough for the
   * browser to offer to stop the script.
   */
  const parcels = {
    "Streifen, 159 Ecken": echtesGrundstueck("vielecken"),
    "Feld, 34 799 m²": echtesGrundstueck("gross")
  };

  for (const [name, plot] of Object.entries(parcels)) {
    it(`${name}: das Fenster steht in vertretbarer Zeit`, () => {
      const begonnen = Date.now();
      buildableArea(plot.polygon, plot.tiefen);
      // Well under a second on any machine that can run the app at all. The
      // point is the bound, not the number: uncapped this took 2.7 s in Node.
      expect(Date.now() - begonnen).toBeLessThan(900);
    });

    it(`${name}: das Fenster hält den Abstand trotz gröberem Raster`, () => {
      const fenster = buildableArea(plot.polygon, plot.tiefen);
      expect(fenster.length).toBeGreaterThanOrEqual(3);
      const soll = Math.min(...plot.tiefen);
      // Coarsening the grid must never buy area: every corner of the envelope
      // stays at least the required distance from the boundary.
      fenster.forEach(ecke => {
        expect(distanceToBoundary(ecke, plot.polygon)).toBeGreaterThanOrEqual(soll);
        expect(pointInPolygon(ecke, plot.polygon)).toBe(true);
      });
    });
  }

  it("lässt ein normales Grundstück beim feinen Raster", () => {
    // The cap must not cost precision where precision is what people plan on.
    const klein = echtesGrundstueck("konkav");
    const fein = buildableArea(klein.polygon, klein.tiefen, { step: 0.4 });
    expect(polygonArea(fein)).toBeGreaterThan(polygonArea(klein.polygon) * 0.6);
  });
});
