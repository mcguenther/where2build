/**
 * The neighbourhood, per building — against what ALKIS really answered.
 *
 * `neighbours-moelkau-alkis.json` holds the 71 outlines `ave:GebaeudeBauwerk`
 * returned around Mölkau, Flurstück 204 (Lessingweg 44); the street edge is
 * read off the recorded traffic parcels the way the app reads it. The
 * reference values are the ones the approved mock-up
 * (`docs/strategie/ui-nachbarschaft.html`) was computed with, on a 3 cm grid.
 */
import { describe, it, expect } from "vitest";
import { plotFromCadastre } from "../src/lib/plots.js";
import { streetFront } from "../src/lib/streetFront.js";
import {
  buildableArea, polygonArea, alignmentToEdge, findPlacement, polygonEdges, pointInPolygon
} from "../src/lib/geometry.js";
import {
  analyseNeighbourhood, localBuildings, checkHouse, useKind, ringGap,
  READING_BOUNDARY, READING_SETBACK, HOUSE_INSIDE, HOUSE_ZONE, HOUSE_OUTSIDE
} from "../src/lib/neighbourhood.js";
import { neighbourhoodFindings, houseCheckFinding, bandFinding } from "../src/lib/findings.js";
import parcel204 from "./fixtures/parcel-moelkau.json";
import parcel205 from "./fixtures/parcel-moelkau-205.json";
import parcelBoth from "./fixtures/parcel-moelkau-zwei.json";
import manyCorners from "./fixtures/parcel-many-corners.json";
import streets204 from "./fixtures/verkehr-moelkau.json";
import streets205 from "./fixtures/verkehr-moelkau-205.json";
import streetsBoth from "./fixtures/verkehr-moelkau-zwei.json";
import cadastre from "./fixtures/neighbours-moelkau-alkis.json";
import osm from "./fixtures/neighbours-moelkau.json";
import elk from "./fixtures/housetype-elk.json";

/** A plot as the app holds it once the street front has been settled. */
function settled(parcel, streets) {
  const plot = plotFromCadastre(parcel);
  const front = streetFront(plot.polygon, plot.anchor, streets.features, plot.lagebezeichnung);
  plot.streetEdge = front.edge;
  plot.streetFront = { street: front.street, length: front.length };
  return plot;
}

const plot = settled(parcel204, streets204);
const buildings = localBuildings(cadastre.gebaeude, plot.anchor);
const analysis = analyseNeighbourhood(plot, buildings);
const byAddress = (a, address) => a.buildings.find(b => b.address === address);
const shed = a => a.buildings.find(b => b.class === "accessory" && b.facing?.boundary === "rear");

describe("Das Bebauungsfenster bleibt, was § 6 sagt", () => {
  it("ist 312,9 m² groß, mit und ohne Nachbarn, in beiden Lesarten", () => {
    const own = polygonArea(buildableArea(plot.polygon, plot.setbacks));
    expect(own).toBeCloseTo(312.9, 1);
    expect(analysis.envelope.area).toBeCloseTo(own, 6);
    expect(analyseNeighbourhood(plot, buildings, { reading: READING_BOUNDARY }).envelope.area).toBeCloseTo(own, 6);
    expect(analyseNeighbourhood(plot, []).envelope.area).toBeCloseTo(own, 6);
  });
});

describe("Jedes Gebäude wird eingeordnet, nicht jede Kante", () => {
  it("liest die Nutzung aus der ALKIS-Funktion", () => {
    expect(useKind("Wohngebäude")).toBe("residential");
    expect(useKind("Gebäude für Wirtschaft oder Gewerbe")).toBe("accessory");
    expect(useKind("Gebäude für öffentliche Zwecke")).toBe("other");
    expect(useKind(null)).toBe("unknown");
  });

  it("ordnet die Gebäude um Lessingweg 44 so ein wie der Entwurf", () => {
    expect(byAddress(analysis, "Lessingweg 44").class).toBe("own");
    const n42 = byAddress(analysis, "Lessingweg 42");
    expect(n42.class).toBe("boundary");
    expect(n42.gap).toBeCloseTo(0.04, 2);
    const n46 = byAddress(analysis, "Lessingweg 46");
    expect(n46.class).toBe("overlap");
    expect(n46.gap).toBeCloseTo(2.33, 2);
    const garage = shed(analysis);
    expect(garage.use).toBe("Gebäude für Wirtschaft oder Gewerbe");
    expect(garage.area).toBeCloseTo(30.8, 1);
    expect(garage.gap).toBeCloseTo(0.96, 2);
    expect(analysis.counts).toEqual({ own: 2, accessory: 1, boundary: 1, overlap: 1, clear: 66 });
    // The shed on our own plot is Bestand, not a neighbour.
    expect(analysis.buildings.filter(b => b.class === "own").map(b => b.useKind).sort())
      .toEqual(["accessory", "residential"]);
  });

  it("misst, an welcher Grenze und auf welcher Länge ein Nachbar steht", () => {
    const n42 = byAddress(analysis, "Lessingweg 42").facing;
    expect(n42.boundary).toBe("right");
    expect(n42.face.from).toBeCloseTo(12.3, 1);
    expect(n42.face.to).toBeCloseTo(28.1, 1);
    const n46 = byAddress(analysis, "Lessingweg 46").facing;
    expect(n46.boundary).toBe("left");
    expect(n46.face.from).toBeCloseTo(37.6, 1);
    expect(n46.face.to).toBeCloseTo(45.0, 1);
  });

  it("lässt ein Gebäude hinter der Ecke nichts an den Seiten anrichten", () => {
    // The old whole-edge rule let this shed deepen three edges at once.
    const garage = shed(analysis);
    expect(garage.facing.boundary).toBe("rear");
    expect(garage.facing.span.from).toBeLessThan(0);           // it starts behind our corner
    expect(garage.facing.beyond).toBeCloseTo(1.3, 1);
    expect(garage.zone).toBeNull();
    expect(garage.reach).toBeNull();
    const sides = analysis.boundaries.filter(g => g.kind === "left" || g.kind === "right");
    expect(sides.flatMap(g => g.facing.map(f => f.buildingId))).not.toContain(garage.id);
    expect(analysis.zones.map(z => z.buildingId).sort())
      .toEqual([byAddress(analysis, "Lessingweg 42").id, byAddress(analysis, "Lessingweg 46").id].sort());
  });
});

describe("Was ein Nachbar bei uns bedeutet, dort, wo er steht", () => {
  it("Lessingweg 46: 3 m reichen 0,67 m herüber, die 6-m-Zone ist 5,7 m²", () => {
    const n46 = byAddress(analysis, "Lessingweg 46");
    expect(n46.reach.area).toBeCloseTo(6.1, 1);
    expect(n46.reach.depth).toBeCloseTo(0.67, 2);
    expect(n46.zone.area).toBeGreaterThan(5.65);
    expect(n46.zone.area).toBeLessThan(5.78);
    expect(n46.zone.depth).toBeCloseTo(0.67, 2);
    expect(n46.zone.depthFromBoundary).toBeCloseTo(3.67, 2);
  });

  it("Lessingweg 42, „Abstand nötig“: 68,2 m², bis 2,96 m ins Fenster", () => {
    // The mock-up said 68,1: its 3 cm trace was simplified a little inward. A
    // 1 cm trace gives 68,19 m², this one 68,15.
    const n42 = byAddress(analysis, "Lessingweg 42");
    expect(n42.reading).toBe(READING_SETBACK);
    expect(n42.zoneApplies).toBe(true);
    expect(n42.zone.area).toBeGreaterThan(68.0);
    expect(n42.zone.area).toBeLessThan(68.25);
    // The mock-up's 2,95 m was the deepest grid cell; this is exact.
    expect(n42.zone.depth).toBeCloseTo(2.96, 2);
    expect(n42.zone.depthFromBoundary).toBeCloseTo(5.96, 2);
  });

  it("Lessingweg 42, „an die Grenze“: 47,4 m² möglicherweise bebaubar auf 15,8 m, keine Zone", () => {
    const read = analyseNeighbourhood(plot, buildings, { reading: READING_BOUNDARY });
    const n42 = byAddress(read, "Lessingweg 42");
    expect(n42.zoneApplies).toBe(false);
    expect(read.zones.map(z => z.address)).toEqual(["Lessingweg 46"]);
    expect(read.maybeBuildable).toHaveLength(1);
    expect(read.maybeBuildable[0].area).toBeCloseTo(47.4, 1);
    expect(read.maybeBuildable[0].length).toBeCloseTo(15.8, 1);
    // Per building works as well as for all at once.
    const perBuilding = analyseNeighbourhood(plot, buildings, { reading: { [n42.id]: READING_BOUNDARY } });
    expect(perBuilding.maybeBuildable[0].area).toBeCloseTo(47.4, 1);
  });

  it("zeichnet die Zone rund um das Haus, nie über die ganze Kante", () => {
    const n42 = byAddress(analysis, "Lessingweg 42");
    for (const ring of n42.zone.rings) {
      for (const p of ring) {
        expect(ringGap([p, { x: p.x + 1e-6, y: p.y }, { x: p.x, y: p.y + 1e-6 }], n42.ring)).toBeLessThan(6.05);
      }
    }
    // The strip stays within the stretch 42 stands along.
    const edge = polygonEdges(plot.polygon)[n42.facing.edge];
    const along = byAddress(analyseNeighbourhood(plot, buildings, { reading: READING_BOUNDARY }), "Lessingweg 42")
      .maybeBuildable.ring.map(p => ((p.x - edge.a.x) * edge.dx + (p.y - edge.a.y) * edge.dy) / edge.length);
    expect(Math.max(...along) - Math.min(...along)).toBeCloseTo(15.8, 1);
  });

  it("schaltet die Lesart um, ohne die Geometrie neu zu rechnen", () => {
    const again = analyseNeighbourhood(plot, buildings);
    expect(again).toBe(analysis);
    const other = analyseNeighbourhood(plot, buildings, { reading: READING_BOUNDARY });
    expect(byAddress(other, "Lessingweg 42").zone).toBe(byAddress(analysis, "Lessingweg 42").zone);
  });
});

describe("Grenze für Grenze", () => {
  it("fasst die fünf Kanten zu Straße, zwei Seiten und Rückseite zusammen", () => {
    const kinds = Object.fromEntries(analysis.boundaries.map(g => [g.kind, g]));
    expect(Object.keys(kinds).sort()).toEqual(["left", "rear", "right", "street"]);
    expect(kinds.street.edges).toEqual([plot.streetEdge]);
    expect(kinds.street.length).toBeCloseTo(13.5, 1);
    expect(kinds.right.length).toBeCloseTo(47.69, 1);
    expect(kinds.left.length).toBeCloseTo(47.92, 1);
    expect(kinds.rear.edges).toHaveLength(2);
    expect(kinds.rear.length).toBeCloseTo(13.46, 1);
    expect(kinds.street.status).toBe("clear");
    expect(kinds.right.status).toBe("boundary");
    expect(kinds.left.status).toBe("overlap");
    expect(kinds.rear.status).toBe("accessory");
    expect(kinds.right.facing).toHaveLength(1);
    expect(kinds.right.facing[0].gap).toBeCloseTo(0.04, 2);
  });

  it("gruppiert auch zwei Flurstücke: zwei Straßenkanten, vier hinten", () => {
    const both = settled(parcelBoth, streetsBoth);
    const a = analyseNeighbourhood(both, localBuildings(cadastre.gebaeude, both.anchor));
    const kinds = Object.fromEntries(a.boundaries.map(g => [g.kind, g]));
    expect(kinds.street.edges).toHaveLength(2);
    expect(kinds.street.length).toBeCloseTo(27.0, 1);
    expect(kinds.rear.edges).toHaveLength(4);
    expect(byAddress(a, "Lessingweg 44").class).toBe("own");
    expect(byAddress(a, "Lessingweg 46").class).toBe("own");
    expect(byAddress(a, "Lessingweg 42").class).toBe("boundary");
    expect(byAddress(a, "Lessingweg 48").class).toBe("overlap");
  });
});

describe("Im Schnitt", () => {
  it("schneidet quer durch das Grundstück in der Mitte von Nr. 42, ohne Höhen", () => {
    const n42 = byAddress(analysis, "Lessingweg 42");
    const cut = analysis.sections.find(s => s.buildingId === n42.id);
    expect(cut.ourBoundary).toBe(0);
    expect(cut.at).toBeCloseTo(20.2, 1);
    expect(cut.neighbourWall).toBeLessThanOrEqual(0);
    expect(cut.neighbourWall).toBeGreaterThan(-0.2);
    expect(cut.envelope).toHaveLength(1);
    expect(cut.envelope[0][0]).toBeCloseTo(3, 1);
    expect(cut.envelope[0][1]).toBeCloseTo(10.49, 1);
    expect(cut.zone[0][0]).toBeCloseTo(3, 1);
    expect(cut.zone[0][1]).toBeCloseTo(5.95, 1);
    expect(cut.reach[0][1]).toBeCloseTo(2.95, 1);
    expect(cut.maybeBuildable[0][1]).toBeCloseTo(3, 1);
    expect(cut.oppositeBoundary).toBeCloseTo(13.49, 1);
    expect(JSON.stringify(cut)).not.toMatch(/height|hoehe|höhe/i);
  });

  it("zeigt bei Nr. 46 die Zone erst hinter unserem 3-m-Streifen", () => {
    const cut = analysis.sections.find(s => s.buildingId === byAddress(analysis, "Lessingweg 46").id);
    expect(cut.boundary).toBe("left");
    expect(cut.neighbourWall).toBeCloseTo(-2.37, 1);
    expect(cut.zone[0][0]).toBeCloseTo(3, 1);
    expect(cut.zone[0][1]).toBeCloseTo(3.63, 1);
    expect(cut.maybeBuildable).toEqual([]);
  });
});

describe("Band nach § 34 BauGB", () => {
  it("nimmt die sechs Wohnhäuser auf unserer Straßenseite, geometrisch und am Straßennamen", () => {
    const band = analysis.band;
    expect(band.houses.map(h => h.address)).toEqual(
      ["Lessingweg 40", "Lessingweg 42", "Lessingweg 46", "Lessingweg 48", "Lessingweg 50", "Lessingweg 50a"]);
    expect(band.front.min).toBeCloseTo(5.19, 1);
    expect(band.front.max).toBeCloseTo(37.62, 1);
    expect(band.rear.max).toBeCloseTo(45.04, 1);
    const n48 = band.houses.find(h => h.address === "Lessingweg 48");
    expect(n48.front).toBeCloseTo(19.41, 1);
    expect(n48.rear).toBeCloseTo(36.55, 1);
    // Our own house is shown beside the band, never in it.
    expect(band.own.map(o => o.address)).toContain("Lessingweg 44");
    expect(band.envelope.front).toBeCloseTo(3, 1);
  });

  it("sagt das in einem Satz, als Anhalt und nicht als Grenze", () => {
    const f = bandFinding(analysis.band);
    expect(f.sentences[0]).toBe("Die 6 Nachbarhäuser auf unserer Straßenseite (bis 60 m entlang der Straße) "
      + "stehen 5,2–37,6 m hinter der Straße und reichen bis 45,0 m tief.");
    expect(f.sentences[1]).toContain("keine Grenze");
  });
});

describe("Das Haus im Plan", () => {
  const builtArea = elk.felder.bebaute_flaeche_m2.wert;
  const width = Math.sqrt(builtArea * 1.75), depth = builtArea / width;
  const left = analysis.boundaries.find(g => g.kind === "left").edges[0];
  const rotation = alignmentToEdge(plot.polygon, left);
  const envelope = analysis.envelope.ring;
  const n46 = byAddress(analysis, "Lessingweg 46");
  const street = polygonEdges(plot.polygon)[plot.streetEdge];
  const streetMiddle = { x: (street.a.x + street.b.x) / 2, y: (street.a.y + street.b.y) / 2 };

  it("reicht hinten in beide Zonen – amber, mit beiden Tiefen", () => {
    const rear = findPlacement(envelope, width, depth, { rotation, near: n46.centre, step: 0.1 });
    const check = checkHouse(analysis, rear);
    expect(check.status).toBe(HOUSE_ZONE);
    expect(check.cornersOutside).toBe(0);
    const into46 = check.zones.find(z => z.address === "Lessingweg 46");
    expect(into46.intrusion).toBeGreaterThan(0);
    expect(into46.intrusion).toBeLessThanOrEqual(n46.zone.depth + 1e-6);
    expect(check.zones.map(z => z.address)).toContain("Lessingweg 42");
    const text = houseCheckFinding(check).sentences[0];
    expect(text).toMatch(/^Baukörper liegt im Bebauungsfenster, reicht aber \d+,\d\d m in die 6-m-Zone zu Lessingweg/);
    expect(text).toContain("eine Frage an die Bauaufsicht");
  });

  it("steht vorn ohne Zone, wenn an die Grenze gebaut werden darf – grün", () => {
    const read = analyseNeighbourhood(plot, buildings, { reading: READING_BOUNDARY });
    const front = findPlacement(envelope, width, depth, { rotation, near: streetMiddle, step: 0.1 });
    expect(checkHouse(read, front).status).toBe(HOUSE_INSIDE);
    // The same spot under the cautious reading reaches into the zone at 42.
    const cautious = checkHouse(analysis, front);
    expect(cautious.status).toBe(HOUSE_ZONE);
    expect(cautious.zones.map(z => z.address)).toEqual(["Lessingweg 42"]);
    expect(houseCheckFinding(checkHouse(read, front)).sentences[0]).toBe("Baukörper liegt im Bebauungsfenster.");
  });

  it("meldet rot, sobald eine Ecke das Fenster verlässt", () => {
    const front = findPlacement(envelope, width, depth, { rotation, near: streetMiddle, step: 0.1 });
    const out = { ...front, cx: front.cx + (streetMiddle.x - front.cx) * 0.6, cy: front.cy + (streetMiddle.y - front.cy) * 0.6 };
    const check = checkHouse(analysis, out);
    expect(check.status).toBe(HOUSE_OUTSIDE);
    expect(check.cornersOutside).toBeGreaterThan(0);
    expect(houseCheckFinding(check).sentences[0]).toMatch(/Gebäudeecken? (liegt|liegen) außerhalb des Bebauungsfensters\./);
  });

  it("ist billig genug für jede Mausbewegung", () => {
    const rear = findPlacement(envelope, width, depth, { rotation, near: n46.centre, step: 0.1 });
    const started = performance.now();
    for (let i = 0; i < 2000; i++) checkHouse(analysis, { ...rear, cx: rear.cx + i * 1e-4 });
    expect(performance.now() - started).toBeLessThan(500);
    // The same placement twice is the same answer object.
    expect(checkHouse(analysis, rear)).toBe(checkHouse(analysis, rear));
  });
});

describe("Befunde", () => {
  const findings = neighbourhoodFindings(analysis);
  const numbered = findings.filter(f => f.marker);

  it("nummeriert nach Dringlichkeit: Grenzbebauung, Überdeckung, Nebengebäude, Bestand", () => {
    expect(numbered.map(f => [f.marker, f.status, f.title])).toEqual([
      [1, "boundary", "Lessingweg 42"],
      [2, "overlap", "Lessingweg 46"],
      [3, "accessory", "Nebengebäude"],
      [4, "own", "Lessingweg 44 (Bestand)"]
    ]);
    expect(numbered[0].statusLabel).toBe("an der Grenze");
    expect(findings.filter(f => !f.marker).map(f => f.id)).toEqual(["band", "clear", "heights"]);
  });

  it("gibt Nr. 42 beide Lesarten, die vorsichtige zuerst", () => {
    const n42 = numbered[0];
    expect(n42.sentences[0]).toBe("Wohngebäude, 0,04 m vor unserer Grenze, auf 15,8 m Länge 12,3–28,1 m hinter der Straße.");
    expect(n42.reading).toBe(READING_SETBACK);
    expect(n42.sentences[2]).toBe(n42.readingSentences.setback);
    expect(n42.readingSentences.setback).toBe("Abstand nötig: Die 6-m-Zone reicht hier bis 5,96 m von der Grenze, "
      + "2,96 m ins Bebauungsfenster (68,2 m²). Hier stünden die Häuser näher als 6 m – das klärt die Bauaufsicht.");
    expect(n42.readingSentences.boundary).toContain("§ 6 Abs. 1 Satz 3 SächsBO");
    expect(n42.readingSentences.boundary).toContain("Der 3-m-Streifen auf diesen 15,8 m wäre möglicherweise bebaubar (47,4 m²)");
  });

  it("beschreibt Nr. 46 als Überdeckung, nicht als Pflicht", () => {
    const [first, reach, zone] = numbered[1].sentences;
    expect(first).toBe("Wohngebäude, 2,33 m vor unserer Grenze, 37,6–45,0 m hinter der Straße.");
    expect(reach).toBe("Der Mindestabstand dieses Gebäudes von 3 m reicht 0,67 m auf unser Grundstück (6,1 m²).");
    expect(zone).toContain("die 6-m-Zone, 5,7 m², bis 0,67 m tief");
    expect(zone).toContain("§ 6 Abs. 3 SächsBO");
  });

  it("nennt beim Nebengebäude § 6 Abs. 8 Nr. 1 und die fehlende Wandhöhe", () => {
    const text = numbered[2].sentences.join(" ");
    expect(text).toContain("Laut Kataster Gebäude für Wirtschaft oder Gewerbe, 30,8 m²");
    expect(text).toContain("davon 1,3 m hinter unserer Ecke");
    expect(text).toContain("§ 6 Abs. 8 Nr. 1 SächsBO");
    expect(text).toContain("die Wandhöhe führt das Kataster nicht");
  });

  it("fasst den Rest in einer Zeile zusammen", () => {
    expect(findings.find(f => f.id === "clear").sentences[0]).toBe(
      "Die übrigen 13 Gebäude bis 25 m stehen mindestens 3 m von unseren Grenzen entfernt, das nächste 9,9 m.");
  });

  it("macht die 6 m nie zur Pflicht und erfindet keine Wandhöhe", () => {
    const all = [neighbourhoodFindings(analysis),
      neighbourhoodFindings(analyseNeighbourhood(plot, buildings, { reading: READING_BOUNDARY }))]
      .flat().flatMap(f => [...f.sentences, ...Object.values(f.readingSentences ?? {})]).join(" ");
    expect(all).not.toMatch(/\bmüssen\b|\bmuss\b|Pflicht|einzuhalten|verboten|6-m-Regel/);
    expect(all).not.toMatch(/Wandhöhe von \d|\d+(,\d+)? m hoch/);
    expect(all).not.toContain("NaN");
    expect(all).not.toContain("undefined");
  });
});

describe("Andere Grundstücke, andere Quellen", () => {
  it("Lessingweg 46: Nr. 44 an der Grenze, zwei Garagen zählen nicht, bei Nr. 48 keine Zone", () => {
    const p = settled(parcel205, streets205);
    const a = analyseNeighbourhood(p, localBuildings(cadastre.gebaeude, p.anchor));
    expect(byAddress(a, "Lessingweg 46").class).toBe("own");
    expect(byAddress(a, "Lessingweg 44").class).toBe("boundary");
    expect(a.buildings.filter(b => b.class === "accessory")).toHaveLength(2);
    const n48 = byAddress(a, "Lessingweg 48");
    expect(n48.class).toBe("overlap");
    // 2,94 m before the boundary, but the envelope recedes there: over 6 m.
    expect(n48.zone).toBeNull();
    const text = neighbourhoodFindings(a).find(f => f.buildingId === n48.id).sentences.join(" ");
    expect(text).toContain("eine 6-m-Zone entsteht nicht");
    expect(a.band.houses.map(h => h.address)).toContain("Lessingweg 44");
    expect(a.band.houses.map(h => h.address)).not.toContain("Lessingweg 46");
  });

  it("OSM ohne Funktion: nichts wird zum Nebengebäude erklärt", () => {
    const both = settled(parcelBoth, streetsBoth);
    const a = analyseNeighbourhood(both, localBuildings(osm.gebaeude, both.anchor));
    expect(a.buildings.every(b => b.useKind === "unknown")).toBe(true);
    expect(a.counts.accessory).toBe(0);
    expect(byAddress(a, "Lessingweg 42").class).toBe("boundary");
    const text = neighbourhoodFindings(a).flatMap(f => f.sentences).join(" ");
    expect(text).toContain("Gebäude, 0,46 m vor unserer Grenze");
  });
});

describe("Ohne Nachbarn", () => {
  it("antwortet leer, aber wohldefiniert", () => {
    const a = analyseNeighbourhood(plot, []);
    expect(a.empty).toBe(false);
    expect(a.buildings).toEqual([]);
    expect(a.zones).toEqual([]);
    expect(a.maybeBuildable).toEqual([]);
    expect(a.sections).toEqual([]);
    expect(a.boundaries.every(g => g.status === "clear" && !g.facing.length)).toBe(true);
    expect(a.band.houses).toEqual([]);
    expect(a.clear).toEqual({ count: 0, nearest: null, reach: 25 });
    expect(neighbourhoodFindings(a)).toEqual([]);
    expect(checkHouse(a, { ...plot.house, width: 8, depth: 10 }).zones).toEqual([]);
  });

  it("ohne Grundstück oder ohne Anker gibt es nichts zu rechnen", () => {
    expect(analyseNeighbourhood(null, buildings).empty).toBe(true);
    expect(analyseNeighbourhood({ polygon: [] }, buildings).buildings).toEqual([]);
    expect(localBuildings(cadastre.gebaeude, null)).toEqual([]);
    expect(neighbourhoodFindings(analyseNeighbourhood(null, buildings))).toEqual([]);
    expect(houseCheckFinding(null)).toBeNull();
  });

  it("bleibt auf dem 1,6 km langen Feld schnell", () => {
    const field = plotFromCadastre(manyCorners);
    const started = performance.now();
    const a = analyseNeighbourhood(field, localBuildings(cadastre.gebaeude, field.anchor));
    expect(performance.now() - started).toBeLessThan(3000);
    expect(a.envelope.area).toBeGreaterThan(0);
    expect(a.buildings.every(b => b.class === "clear")).toBe(true);
  });
});
