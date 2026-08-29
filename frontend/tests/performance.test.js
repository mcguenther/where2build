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
import { echtesGrundstueck } from "./hilfe.js";

/* Real ALKIS answers. "gross" is 34 799 m² in Moritzburg with 65 boundary
   points; "vielecken" is the 21 585 m² strip along Tauchaer Straße with 159. */
const GROSSE = ["gross", "vielecken"];

describe("Rechenzeit auf echten Flurstücken", () => {
  for (const form of GROSSE) {
    it(`${form}: das Bebauungsfenster steht in unter einer Sekunde`, () => {
      const plot = echtesGrundstueck(form);
      const begonnen = Date.now();
      const fenster = buildableArea(plot.polygon, plot.tiefen, { step: 0.4 + Math.random() * 1e-6 });
      expect(Date.now() - begonnen).toBeLessThan(1000);
      expect(fenster.length).toBeGreaterThanOrEqual(3);
    });

    it(`${form}: ein reaktives Polygon kostet nicht wesentlich mehr als ein rohes`, () => {
      // A proxy must not multiply the cost. Fresh cache keys on both sides, so
      // neither run can be answered from the memo.
      const reaktiv = reactive(echtesGrundstueck(form));
      let t = Date.now();
      buildableArea(reaktiv.polygon, reaktiv.tiefen, { step: 0.4 + Math.random() * 1e-6 });
      const mitProxy = Date.now() - t;

      const roh = echtesGrundstueck(form);
      t = Date.now();
      buildableArea(roh.polygon, roh.tiefen, { step: 0.4 + Math.random() * 1e-6 });
      const ohneProxy = Date.now() - t;

      expect(mitProxy).toBeLessThan(Math.max(ohneProxy, 20) * 4);
    });

    it(`${form}: der Lageplan montiert in vertretbarer Zeit`, () => {
      // Through the props, so the plot really is reactive, as in the app.
      const plot = reactive(echtesGrundstueck(form));
      const begonnen = Date.now();
      const w = mount(SitePlan, { props: { plot, koerper: placement(plot) } });
      expect(Date.now() - begonnen).toBeLessThan(3000);
      w.unmount();
    });
  }
});

describe("Das gröbere Raster bleibt auf der sicheren Seite", () => {
  for (const form of GROSSE) {
    it(`${form}: kein Punkt des Fensters unterschreitet den Abstand`, () => {
      const plot = echtesGrundstueck(form);
      const fenster = buildableArea(plot.polygon, plot.tiefen);
      const soll = Math.min(...plot.tiefen);
      fenster.forEach(ecke => {
        expect(distanceToBoundary(ecke, plot.polygon)).toBeGreaterThanOrEqual(soll);
        expect(pointInPolygon(ecke, plot.polygon)).toBe(true);
      });
    });
  }

  it("ein normales Grundstück verliert durch den Deckel nichts", () => {
    // The cap only bites on land nobody plans a house on to the decimetre.
    const klein = echtesGrundstueck("konkav");
    const fenster = buildableArea(klein.polygon, klein.tiefen);
    expect(polygonArea(fenster)).toBeGreaterThan(polygonArea(klein.polygon) * 0.6);
  });
});
