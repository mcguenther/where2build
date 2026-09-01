/** The maths every figure in the interface rests on. */
import { describe, it, expect } from "vitest";
import {
  polygonArea, polygonEdges, polygonPerimeter, asCounterClockwise, boundingBox,
  buildableArea, minimumRotatedRectangle, rectangularity, shapeClass,
  pointInPolygon, distanceToBoundary, closestBoundaryPoint,
  rectangleCorners, cornersOutside, smallestSetback, footprintFromArea,
  findPlacement, fitsAnywhere, alignmentToEdge, alignToEdge, edgeCompass,
  constrainToEnvelope, neighbourDistances, neighbourSetbackDepths, hasNeighbourHint
} from "../src/lib/geometry.js";
import { toLocal } from "../src/lib/projection.js";
import neighbourAnswer from "./fixtures/neighbours-moelkau.json";

import { realPlot } from "./helpers.js";

const ring = pairs => pairs.map(([x, y]) => ({ x, y }));
const SQUARE = ring([[0, 0], [10, 0], [10, 10], [0, 10]]);
const LIEBERTWOLKWITZ = ring([[0, 0], [22.6, 0.9], [24.3, 34.9], [1.6, 36.2]]);

describe("Flächen und Kanten", () => {
  it("misst ein bekanntes Quadrat", () => {
    expect(polygonArea(SQUARE)).toBe(100);
    expect(polygonPerimeter(SQUARE)).toBe(40);
  });

  it("misst das Beispielflurstück und weicht plausibel von der amtlichen Fläche ab", () => {
    const computed = polygonArea(LIEBERTWOLKWITZ);
    expect(computed).toBeCloseTo(795.3, 1);
    const deviation = Math.abs(802 - computed);
    expect(deviation).toBeGreaterThan(0);
    expect(deviation).toBeLessThan(15);
  });

  it("liefert die Kantenlängen, die die Oberfläche anzeigt", () => {
    expect(polygonEdges(LIEBERTWOLKWITZ).map(e => +e.length.toFixed(2)))
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
    const tilted = ring([[0, 0], [10, 10], [8, 12], [-2, 2]]);
    const mrr = minimumRotatedRectangle(tilted);
    expect(mrr.area).toBeCloseTo(polygonArea(tilted), 6);   // ein gedrehtes Rechteck ist sein eigenes MRR
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
    const envelope = buildableArea(LIEBERTWOLKWITZ, [3, 3, 3, 3]);
    const inside = { cx: 10.8, cy: 15, width: 11.4, depth: 8.5, rotation: -4 };
    const outside = { cx: 10.8, cy: 32, width: 11.4, depth: 8.5, rotation: -4 };
    expect(cornersOutside(inside, envelope)).toBe(0);
    expect(cornersOutside(outside, envelope)).toBeGreaterThan(0);
  });

  it("misst den geringsten Grenzabstand", () => {
    const centred = { cx: 5, cy: 5, width: 4, depth: 4, rotation: 0 };
    expect(smallestSetback(centred, SQUARE)).toBeCloseTo(3, 9);
  });

  it("findet den nächsten Punkt auf der Grenze", () => {
    const near = closestBoundaryPoint({ x: 5, y: 8 }, SQUARE);
    expect(near.distance).toBeCloseTo(2, 9);
    expect(near.point).toEqual({ x: 5, y: 10 });
  });
});

describe("Passt der Baukörper?", () => {
  const envelope = buildableArea(SQUARE, [1, 1, 1, 1]);   // 8 × 8 m

  it("findet eine zulässige Lage", () => {
    const found = findPlacement(envelope, 7, 5);
    expect(found).not.toBeNull();
    expect(cornersOutside({ ...found, width: 7, depth: 5 }, envelope)).toBe(0);
  });

  it("meldet, wenn nichts passt", () => {
    expect(findPlacement(envelope, 9, 9)).toBeNull();
    expect(fitsAnywhere(envelope, 9, 9)).toBe(false);
  });

  it("nutzt die Drehung — quer passt, was längs nicht passt", () => {
    const narrow = buildableArea(ring([[0, 0], [9, 0], [9, 26], [0, 26]]), [0.5, 0.5, 0.5, 0.5]);
    expect(findPlacement(narrow, 20, 6)).not.toBeNull();
    expect(findPlacement(narrow, 20, 6, { rotation: 0 })).toBeNull();
  });

  it("bleibt mit „near“ in der Nähe der bisherigen Lage", () => {
    const near = findPlacement(envelope, 3, 3, { near: { x: 3, y: 3 } });
    const far = findPlacement(envelope, 3, 3, { near: { x: 8, y: 8 } });
    expect(Math.hypot(near.cx - 3, near.cy - 3)).toBeLessThan(Math.hypot(far.cx - 3, far.cy - 3));
  });
});

describe("An der Straße ausrichten", () => {
  it("liefert den Winkel der Straßenfront", () => {
    expect(alignmentToEdge(LIEBERTWOLKWITZ, 0)).toBeCloseTo(2.28, 2);
    expect(alignmentToEdge(SQUARE, 0)).toBeCloseTo(0, 9);
  });

  it("normiert auf (−90°, 90°]", () => {
    const upward = ring([[0, 0], [0, 10], [-10, 10], [-10, 0]]);
    const angle = alignmentToEdge(upward, 0);
    expect(angle).toBeGreaterThan(-90);
    expect(angle).toBeLessThanOrEqual(90);
  });

  it("dreht den Baukörper parallel zur Front und lässt ihn im Fenster", () => {
    const envelope = buildableArea(LIEBERTWOLKWITZ, [3, 3, 3, 3]);
    const before = { cx: 10.8, cy: 15, width: 11.4, depth: 8.5, rotation: 40 };
    const after = alignToEdge(LIEBERTWOLKWITZ, envelope, before, 0);
    expect(after.rotation).toBeCloseTo(2.28, 2);
    expect(cornersOutside(after, envelope)).toBe(0);
  });

  it("schiebt zurück ins Fenster, wenn die Drehung herausführt", () => {
    const envelope = buildableArea(LIEBERTWOLKWITZ, [3, 3, 3, 3]);
    const atEdge = { cx: 5.5, cy: 30, width: 11.4, depth: 8.5, rotation: 80 };
    const after = alignToEdge(LIEBERTWOLKWITZ, envelope, atEdge, 0);
    expect(cornersOutside(after, envelope)).toBe(0);
    expect(after.cx === atEdge.cx && after.cy === atEdge.cy).toBe(false);
  });
});

describe("Himmelsrichtungen der Grenzen", () => {
  it("benennt die Grenzen statt sie durchzunummerieren", () => {
    const names = LIEBERTWOLKWITZ.map((_, i) => edgeCompass(LIEBERTWOLKWITZ, i, 17));
    expect(names).toEqual(["Süd", "Ost", "Nord", "West"]);
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
    const expected = {
      0: "Süd", 45: "Südwest", 90: "West", 135: "Nordwest",
      180: "Nord", 225: "Nordost", 270: "Ost", 315: "Südost"
    };
    for (const [offset, name] of Object.entries(expected)) {
      expect(edgeCompass(SQUARE, 0, Number(offset))).toBe(name);
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
    "Streifen, 159 Ecken": realPlot("many-corners"),
    "Feld, 34 799 m²": realPlot("large")
  };

  for (const [name, plot] of Object.entries(parcels)) {
    it(`${name}: das Fenster steht in vertretbarer Zeit`, () => {
      const started = Date.now();
      buildableArea(plot.polygon, plot.setbacks);
      // Well under a second on any machine that can run the app at all. The
      // point is the bound, not the number: uncapped this took 2.7 s in Node.
      expect(Date.now() - started).toBeLessThan(900);
    });

    it(`${name}: das Fenster hält den Abstand trotz gröberem Raster`, () => {
      const envelope = buildableArea(plot.polygon, plot.setbacks);
      expect(envelope.length).toBeGreaterThanOrEqual(3);
      const required = Math.min(...plot.setbacks);
      // Coarsening the grid must never buy area: every corner of the envelope
      // stays at least the required distance from the boundary.
      envelope.forEach(corner => {
        expect(distanceToBoundary(corner, plot.polygon)).toBeGreaterThanOrEqual(required);
        expect(pointInPolygon(corner, plot.polygon)).toBe(true);
      });
    });
  }

  it("lässt ein normales Grundstück beim feinen Raster", () => {
    // The cap must not cost precision where precision is what people plan on.
    const ordinary = realPlot("concave");
    const fine = buildableArea(ordinary.polygon, ordinary.setbacks, { step: 0.4 });
    expect(polygonArea(fine)).toBeGreaterThan(polygonArea(ordinary.polygon) * 0.6);
  });
});


/* Mölkau, Flurstück 204 (Lessingweg 44, 650 m²) is the plot this was written
   against: an ordinary five-cornered building plot rather than a test shape. */
describe("Den Baukörper im Bebauungsfenster halten", () => {
  const plot = realPlot("moelkau");
  const envelope = buildableArea(plot.polygon, plot.setbacks);
  // 8 x 6 m: the plot is a 47.9 x 13.5 m ribbon, so the window is barely
  // 7.5 m across and a 10 x 8 m house does not fit into it at any angle.
  const seat = findPlacement(envelope, 8, 6);
  const inside = placement => cornersOutside(placement, envelope) === 0;

  it("findet für dieses Flurstück überhaupt ein Fenster und einen Platz darin", () => {
    expect(envelope.length).toBeGreaterThan(2);
    expect(seat).not.toBeNull();
    expect(inside(seat)).toBe(true);
  });

  it("lässt eine Bewegung, die drinnen bleibt, unangetastet", () => {
    const wanted = { cx: seat.cx + 0.2, cy: seat.cy + 0.2 };
    expect(constrainToEnvelope(envelope, seat, wanted)).toEqual(wanted);
  });

  it("hält weit über die Grenze hinaus gezogen an der Grenze, statt zurückzuspringen", () => {
    const wanted = { cx: seat.cx + 500, cy: seat.cy };
    const stop = constrainToEnvelope(envelope, seat, wanted);
    expect(inside({ ...seat, ...stop })).toBe(true);
    expect(stop.cx).toBeGreaterThan(seat.cx);
    expect(stop.cx).toBeLessThan(wanted.cx);
  });

  it("gleitet an der Grenze entlang, statt stehen zu bleiben", () => {
    // Diagonal, so far that the full move cannot be legal: the free axis must
    // still advance -- that is the difference between sliding and blocking.
    const wanted = { cx: seat.cx + 60, cy: seat.cy + 4 };
    const stop = constrainToEnvelope(envelope, seat, wanted);
    expect(inside({ ...seat, ...stop })).toBe(true);
    expect(stop.cx !== seat.cx || stop.cy !== seat.cy).toBe(true);
  });

  it("greift nicht, wo es gar kein Fenster gibt", () => {
    const wanted = { cx: seat.cx + 500, cy: seat.cy + 500 };
    expect(constrainToEnvelope([], seat, wanted)).toEqual(wanted);
  });

  it("greift nicht, wenn der Baukörper nirgends hineinpasst", () => {
    const giant = { ...seat, width: 400, depth: 400 };
    const wanted = { cx: seat.cx + 500, cy: seat.cy };
    expect(constrainToEnvelope(envelope, giant, wanted)).toEqual(wanted);
  });

  it("hält auch auf einem konkaven Flurstück, wo das Fenster einspringt", () => {
    const concave = realPlot("concave");
    const window_ = buildableArea(concave.polygon, concave.setbacks);
    const start = findPlacement(window_, 8, 6);
    expect(start).not.toBeNull();
    for (const [dx, dy] of [[300, 0], [-300, 0], [0, 300], [0, -300], [200, 200]]) {
      const stop = constrainToEnvelope(window_, start, { cx: start.cx + dx, cy: start.cy + dy });
      expect(cornersOutside({ ...start, ...stop }, window_)).toBe(0);
    }
  });
});


/* The neighbour hint. Not a legal requirement -- § 6 Abs. 2 SächsBO puts each
   building's setback area on its own plot -- but the strip where the two would
   overlap is worth showing. See
   docs/research/abstandsflaechen-nachbargebaeude.md.

   The outlines are the 59 buildings Overpass really returned within 125 m of
   Mölkau, Flurstück 204. */
describe("Wo die Abstandsfläche des Nachbarn herüberreicht", () => {
  const plot = realPlot("moelkau");
  const outlines = neighbourAnswer.gebaeude.map(b => toLocal(b.umriss, plot.anchor));

  it("misst je Grenzabschnitt, wie nah das nächste Gebäude steht", () => {
    const distances = neighbourDistances(plot.polygon, outlines);

    expect(distances).toHaveLength(plot.polygon.length);
    expect(distances.every(d => d >= 0)).toBe(true);
    // Two of the five boundaries have a neighbour inside the 3 m minimum:
    // 1,74 m and 0,46 m on the recorded data.
    expect(distances.filter(d => d < 3)).toHaveLength(2);
  });

  it("vertieft genau die Abschnitte, an denen ein Nachbar zu nah steht", () => {
    const depths = neighbourSetbackDepths(plot.polygon, plot.setbacks, outlines);

    expect(hasNeighbourHint(plot.setbacks, depths)).toBe(true);
    const deepened = depths.filter((d, i) => d > plot.setbacks[i] + 1e-9);
    expect(deepened).toHaveLength(2);
    // depth + (3 - distance): the neighbour's own minimum, as far as it reaches.
    depths.forEach(d => expect(d).toBeLessThanOrEqual(3 + 3));
    expect(polygonArea(buildableArea(plot.polygon, depths)))
      .toBeLessThan(polygonArea(buildableArea(plot.polygon, plot.setbacks)));
  });

  it("lässt ohne Nachbarn alles, wie es ist", () => {
    const depths = neighbourSetbackDepths(plot.polygon, plot.setbacks, []);

    expect(depths).toEqual(plot.setbacks);
    expect(hasNeighbourHint(plot.setbacks, depths)).toBe(false);
  });

  it("zählt ein Gebäude auf dem eigenen Flurstück nicht als Nachbarn", () => {
    const box = boundingBox(plot.polygon);
    const cx = (box.minX + box.maxX) / 2, cy = (box.minY + box.maxY) / 2;
    const own = [{ x: cx - 1, y: cy - 1 }, { x: cx + 1, y: cy - 1 },
                 { x: cx + 1, y: cy + 1 }, { x: cx - 1, y: cy + 1 }];

    expect(neighbourDistances(plot.polygon, [own]).every(d => d === Infinity)).toBe(true);
  });

  it("sieht weit entfernte Gebäude gar nicht erst an", () => {
    const far = [[{ x: 900, y: 900 }, { x: 910, y: 900 }, { x: 910, y: 910 }, { x: 900, y: 910 }]];

    expect(neighbourDistances(plot.polygon, far).every(d => d === Infinity)).toBe(true);
  });
});
