/**
 * What the site plan says about size.
 *
 * The complaint these pin down: a five-point parcel showed two of its five
 * sides — a 47,69 m front and a 2,04 m sliver — and nowhere its overall size,
 * so the drawing named a corner and left the plot itself unmeasured.
 */
import { describe, it, expect, beforeEach } from "vitest";
import { mount } from "@vue/test-utils";
import SitePlan from "../src/components/SitePlan.vue";
import { state, placement } from "../src/lib/store.js";
import { realState, realPlot } from "./helpers.js";
import { minimumRotatedRectangle, minimumRotatedRectangleCorners, polygonEdges } from "../src/lib/geometry.js";
import { num } from "../src/lib/format.js";

beforeEach(() => { state.data = realState(); });

/* The wizard's own frame, which is where the missing measurements were noticed.
   "none": mounting must not reach for a basemap. */
const plan = (shape, props = {}) => {
  const plot = realPlot(shape);
  return mount(SitePlan, {
    props: { plot, building: placement(plot), width: 640, height: 440, backdrop: "none", northUp: true, ...props }
  });
};

const labels = w => w.findAll("text.site-plan__dimension").map(t => t.text());
const overall = w => labels(w).filter(t => t.startsWith("gesamt"));

describe("Bemaßung der Grenzen", () => {
  it("beschriftet jede einzelne Grenze, nicht zwei davon", () => {
    const plot = realPlot("convex");
    const w = plan("convex");
    const drawn = labels(w);
    polygonEdges(plot.polygon).forEach(edge => {
      expect(drawn).toContain(`${num(edge.length)} m`);
    });
  });

  it("beschriftet auch die kurze Grenze, die keinen Platz für ihren Text hat", () => {
    const plot = realPlot("convex");
    const shortest = Math.min(...polygonEdges(plot.polygon).map(e => e.length));
    expect(shortest).toBeLessThan(4);
    const w = plan("convex");
    expect(labels(w)).toContain(`${num(shortest)} m`);
    // On a leader, because it does not fit between its own witness lines.
    expect(w.findAll("line").length).toBeGreaterThan(polygonEdges(plot.polygon).length * 3);
  });

  it("beschriftet auch das einspringende Flurstück rundum", () => {
    const plot = realPlot("concave");
    const drawn = labels(plan("concave"));
    polygonEdges(plot.polygon).forEach(edge => {
      expect(drawn).toContain(`${num(edge.length)} m`);
    });
  });
});

describe("Gesamtmaß", () => {
  it("nennt Länge und Breite des umschließenden Rechtecks", () => {
    const mrr = minimumRotatedRectangle(realPlot("convex").polygon);
    const drawn = overall(plan("convex"));
    expect(drawn).toHaveLength(2);
    expect(drawn.join(" ")).toContain(num(mrr.width, 1));
    expect(drawn.join(" ")).toContain(num(mrr.height, 1));
  });

  /* The 1583 x 198 m axis-aligned box the district address resolves to is a
     1594 x 30 m ribbon; the overall chain has to report the ribbon. */
  it("misst das Feld als Band, nicht als Kasten", () => {
    const mrr = minimumRotatedRectangle(realPlot("many-corners").polygon);
    const drawn = overall(plan("many-corners")).join(" ");
    expect(drawn).toContain(num(Math.max(mrr.width, mrr.height), 1));
    expect(drawn).toContain(num(Math.min(mrr.width, mrr.height), 1));
  });

  it("bleibt stehen, wenn die Einzelgrenzen zu zahlreich zum Beschriften sind", () => {
    const w = plan("many-corners");
    expect(realPlot("many-corners").polygon.length).toBeGreaterThan(16);
    expect(overall(w)).toHaveLength(2);
    // Every remaining label belongs to the overall chain or to the house.
    expect(labels(w).length).toBeLessThan(8);
  });
});

describe("Was die Bemaßung nicht tut", () => {
  it("zeichnet im Kartenbild auf einer Karte gar keine Maße", () => {
    expect(labels(plan("convex", { compact: true }))).toHaveLength(0);
  });

  it("schaltet sich mit showDimensions ab", () => {
    expect(labels(plan("convex", { showDimensions: false }))).toHaveLength(0);
  });

  it("bleibt mit allem, was es zeichnet, im Bildausschnitt", () => {
    for (const shape of ["convex", "concave", "large", "many-corners"]) {
      const w = plan(shape);
      w.findAll("text.site-plan__dimension").forEach(t => {
        const x = Number(t.attributes("x")), y = Number(t.attributes("y"));
        expect(x, `${shape} x`).toBeGreaterThanOrEqual(0);
        expect(x, `${shape} x`).toBeLessThanOrEqual(640);
        expect(y, `${shape} y`).toBeGreaterThanOrEqual(0);
        expect(y, `${shape} y`).toBeLessThanOrEqual(440);
      });
      w.unmount();
    }
  });
});

describe("Maßstabsleiste", () => {
  it("wählt eine runde Schrittweite statt fester zehn Meter", () => {
    // A kilometre-long parcel wrote "0 10 20 m" on top of itself.
    const bar = plan("many-corners").findAll("text.site-plan__scale-bar").map(t => t.text());
    expect(bar[0]).toBe("0");
    expect(bar[1]).not.toBe("10");
    expect(bar[2]).toMatch(/ m$/);
  });

  it("bleibt auf einem gewöhnlichen Flurstück bei zehn Metern", () => {
    const bar = plan("convex").findAll("text.site-plan__scale-bar").map(t => t.text());
    expect(bar[1]).toBe("10");
    expect(bar[2]).toBe("20 m");
  });
});

describe("Eckpunkte des umschließenden Rechtecks", () => {
  it("liefert vier Ecken, deren Seiten die gemessenen Längen haben", () => {
    const ring = realPlot("concave").polygon;
    const mrr = minimumRotatedRectangle(ring);
    const { corners } = minimumRotatedRectangleCorners(ring);
    expect(corners).toHaveLength(4);
    const side = (a, b) => Math.hypot(b.x - a.x, b.y - a.y);
    expect(side(corners[0], corners[1])).toBeCloseTo(mrr.width, 6);
    expect(side(corners[1], corners[2])).toBeCloseTo(mrr.height, 6);
  });

  it("antwortet mit null auf einen entarteten Ring", () => {
    expect(minimumRotatedRectangleCorners([{ x: 0, y: 0 }])).toBeNull();
  });
});
