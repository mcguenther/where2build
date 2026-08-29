/**
 * The plan must stay responsive on the parcels the cadastre really returns.
 *
 * Two defects together froze the tab for 35 seconds — long enough that Firefox
 * offered to stop the script — when a district address from a listing resolved
 * to a field instead of a building plot:
 *
 *   1. The clearance field ran at a fixed 0.4 m step. On a 1583 x 198 m strip
 *      that is two million cells against 159 boundary segments: 314 million
 *      distance computations.
 *   2. Vue hands a component its props as reactive proxies, and every property
 *      read in that loop paid a proxy trap — measured 23.5x slower than the
 *      same maths on plain objects.
 *
 * These tests hold both fixes in place. The thresholds are deliberately loose:
 * the point is the bound, not the number.
 */
import { describe, it, expect } from "vitest";
import { reactive } from "vue";
import { mount } from "@vue/test-utils";
import SitePlan from "../src/components/SitePlan.vue";
import { buildableArea, distanceToBoundary, pointInPolygon, polygonArea } from "../src/lib/geometry.js";
import { placement } from "../src/lib/store.js";
import { realPlot } from "./helpers.js";

/* Real ALKIS answers. "large" is 34 799 m² in Moritzburg with 65 boundary
   points; "many-corners" is the 21 585 m² strip along Tauchaer Straße with 159. */
const BIG_PARCELS = ["large", "many-corners"];

describe("Rechenzeit auf echten Flurstücken", () => {
  for (const shape of BIG_PARCELS) {
    it(`${shape}: das Bebauungsfenster steht in unter einer Sekunde`, () => {
      const plot = realPlot(shape);
      const started = Date.now();
      const envelope = buildableArea(plot.polygon, plot.setbacks, { step: 0.4 + Math.random() * 1e-6 });
      expect(Date.now() - started).toBeLessThan(1000);
      expect(envelope.length).toBeGreaterThanOrEqual(3);
    });

    it(`${shape}: ein reaktives Polygon kostet nicht wesentlich mehr als ein rohes`, () => {
      // A proxy must not multiply the cost. Fresh cache keys on both sides, so
      // neither run can be answered from the memo.
      const proxied = reactive(realPlot(shape));
      let t = Date.now();
      buildableArea(proxied.polygon, proxied.setbacks, { step: 0.4 + Math.random() * 1e-6 });
      const withProxy = Date.now() - t;

      const plain = realPlot(shape);
      t = Date.now();
      buildableArea(plain.polygon, plain.setbacks, { step: 0.4 + Math.random() * 1e-6 });
      const withoutProxy = Date.now() - t;

      expect(withProxy).toBeLessThan(Math.max(withoutProxy, 20) * 4);
    });

    it(`${shape}: der Lageplan montiert in vertretbarer Zeit`, () => {
      // Through the props, so the plot really is reactive, as in the app.
      const plot = reactive(realPlot(shape));
      const started = Date.now();
      const w = mount(SitePlan, { props: { plot, building: placement(plot) } });
      expect(Date.now() - started).toBeLessThan(3000);
      w.unmount();
    });
  }
});

describe("Das gröbere Raster bleibt auf der sicheren Seite", () => {
  for (const shape of BIG_PARCELS) {
    it(`${shape}: kein Punkt des Fensters unterschreitet den Abstand`, () => {
      const plot = realPlot(shape);
      const envelope = buildableArea(plot.polygon, plot.setbacks);
      const required = Math.min(...plot.setbacks);
      envelope.forEach(corner => {
        expect(distanceToBoundary(corner, plot.polygon)).toBeGreaterThanOrEqual(required);
        expect(pointInPolygon(corner, plot.polygon)).toBe(true);
      });
    });
  }

  it("ein normales Grundstück verliert durch den Deckel nichts", () => {
    // The cap only bites on land nobody plans a house on to the decimetre.
    const ordinary = realPlot("concave");
    const envelope = buildableArea(ordinary.polygon, ordinary.setbacks);
    expect(polygonArea(envelope)).toBeGreaterThan(polygonArea(ordinary.polygon) * 0.6);
  });
});
