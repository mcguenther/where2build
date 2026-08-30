/**
 * The surroundings view: the house where it is planned, enough map around it
 * to recognise the place, and what was found nearby — on real recorded data.
 */
import { describe, it, expect, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { nextTick } from "vue";
import SurroundingsMap from "../src/components/SurroundingsMap.vue";
import SurroundingsView from "../src/views/SurroundingsView.vue";
import { state, placement, plotById } from "../src/lib/store.js";
import { realState, realPlot, realRoutes, realDestinations, testRouter } from "./helpers.js";
import { toLocal } from "../src/lib/projection.js";
import recorded from "./fixtures/nearby-liebertwolkwitz.json";

beforeEach(() => {
  localStorage.clear();
  state.data = realState();
});

const plot = () => plotById("plot-concave");

/** Mount with the network refused: jsdom has no WebGL and no route out, so the
 *  map itself never comes up. What is under test is the geometry handed to it. */
function buildMap(props = {}) {
  const asked = [];
  const original = globalThis.fetch;
  globalThis.fetch = url => {
    asked.push(String(url));
    return asked.length > 4 ? new Promise(() => {}) : Promise.reject(new Error("kein Netz"));
  };
  const w = mount(SurroundingsMap, {
    props: { plot: plot(), building: placement(plot()), ...props },
    attachTo: document.body
  });
  return { w, asked, restore: () => { globalThis.fetch = original; } };
}

describe("Umgebungskarte", () => {
  it("legt Grundstück und Baukörper an ihre echten Koordinaten", () => {
    const { w, restore } = buildMap();
    try {
      const site = plot();
      const outline = w.vm.plotOutline;
      expect(outline).toHaveLength(site.polygon.length);

      // Back through the projection: the same metres we started from.
      toLocal(outline, site.anchor).forEach((point, i) => {
        expect(point.x).toBeCloseTo(site.polygon[i].x, 6);
        expect(point.y).toBeCloseTo(site.polygon[i].y, 6);
      });

      // The house is a rectangle, and it sits on the plot rather than beside it.
      expect(w.vm.houseOutline).toHaveLength(4);
      const lons = w.vm.houseOutline.map(c => c[0]);
      expect(Math.min(...lons)).toBeGreaterThan(Math.min(...outline.map(c => c[0])));
      expect(Math.max(...lons)).toBeLessThan(Math.max(...outline.map(c => c[0])));
    } finally {
      restore();
    }
  });

  it("nimmt nur mit, was eine Koordinate hat", () => {
    const { w, restore } = buildMap({
      hits: [...recorded.treffer, { kategorie: "schule", name: "Ohne Koordinate", erreichbar: false }],
      destinations: [
        { id: "a", name: "Arbeit", lat: 51.34, lon: 12.38, line: [[12.4, 51.3], [12.38, 51.34]] },
        { id: "b", name: "Ohne Koordinate" }
      ]
    });
    try {
      expect(w.vm.located).toHaveLength(recorded.treffer.length);
      expect(w.vm.routedDestinations).toHaveLength(1);
      // A destination without a computed route is still a place, just no line.
      expect(w.vm.routeLines).toHaveLength(1);
    } finally {
      restore();
    }
  });

  it("versucht einen Kartenstil, der nicht lädt, nicht endlos erneut", async () => {
    const { w, asked, restore } = buildMap();
    try {
      for (let i = 0; i < 12; i++) await nextTick();
      expect(asked.length).toBeLessThanOrEqual(1);
      // And says so in German rather than leaving an empty rectangle.
      expect(w.vm.unavailable).toBeTruthy();
      expect(w.text()).toContain("Die Karte lässt sich gerade nicht laden");
    } finally {
      restore();
    }
  });

  it("bietet den weiteren Ausschnitt erst an, wenn es Ziele gibt", async () => {
    const { w, restore } = buildMap();
    try {
      await flushPromises();
      expect(w.find(".surroundings__tools").exists()).toBe(false);

      await w.setProps({ destinations: [{ id: "a", name: "Arbeit", lat: 51.34, lon: 12.38 }] });
      // Only once the map is up; a failed style leaves nothing to reframe.
      expect(w.vm.routedDestinations).toHaveLength(1);
    } finally {
      restore();
    }
  });
});

describe("Umgebungsansicht", () => {
  const openView = (id = "plot-concave") =>
    mount(SurroundingsView, {
      props: { id },
      global: { plugins: [testRouter()], stubs: { SurroundingsMap: true, NearbyPanel: true } }
    });

  it("sagt es, wenn das Grundstück keine Koordinate hat", () => {
    const site = realPlot("concave");
    delete site.anchor;
    state.data.plots = [site];

    expect(openView().text()).toContain("keine Koordinate hinterlegt");
  });

  it("erklärt ein Grundstück, das es hier nicht gibt", () => {
    expect(openView("plot-gibtsnicht").text()).toContain("Dieses Grundstück liegt nicht in diesem Browser");
  });

  it("nimmt zu jedem Ziel die schnellste gerechnete Verbindung mit", () => {
    const site = plotById("plot-concave");
    site.routes = realRoutes();
    state.data.destinations = realDestinations();

    const goals = openView().vm.destinations;
    expect(goals).toHaveLength(realDestinations().length);

    const hbf = goals.find(g => g.id === "zl-hbf");
    // A drawn line, not a straight one: the recorded route has many points.
    expect(hbf.line.length).toBeGreaterThan(2);
    expect(hbf.note).toMatch(/^(Auto|Rad|ÖPNV) · /);
  });

  it("nennt ein Ziel ohne gerechneten Weg beim Namen, statt es zu verschweigen", () => {
    state.data.destinations = realDestinations();
    plotById("plot-concave").routes = {};

    const goals = openView().vm.destinations;
    expect(goals).toHaveLength(2);
    expect(goals.every(g => g.line === null)).toBe(true);
    expect(openView().text()).toContain("Weg noch nicht gerechnet");
  });
});
