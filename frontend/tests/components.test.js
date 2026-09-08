/**
 * The interface, mounted for real, driven by real cadastral fixtures.
 * No sample data: if a service did not answer, the test says so too.
 */
import { describe, it, expect, beforeEach } from "vitest";
import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import SitePlan from "../src/components/SitePlan.vue";
import PlotCard from "../src/components/PlotCard.vue";
import RouteCards from "../src/components/RouteCards.vue";
import PlotsView from "../src/views/PlotsView.vue";
import PlotView from "../src/views/PlotView.vue";
import HouseTypesView from "../src/views/HouseTypesView.vue";
import CompareView from "../src/views/CompareView.vue";
import WizardView from "../src/views/WizardView.vue";
import { state, placement, plotById } from "../src/lib/store.js";
import { realState, realPlot, mountWithRouter, testRouter } from "./helpers.js";
import { buildableArea, cornersOutside, alignmentToEdge, polygonArea, findPlacement, polygonEdges } from "../src/lib/geometry.js";
import { area } from "../src/lib/format.js";
import { plotMetrics } from "../src/lib/metrics.js";
import { boundingBox } from "../src/lib/geometry.js";

beforeEach(() => {
  localStorage.clear();
  state.data = realState();
  // "none": mounting must not reach for a basemap. The backdrop is verified in
  // the browser by scripts/screenshots.mjs, which fails if no tile arrives.
  state.plan = { backdrop: "none", northUp: true, showDimensions: true, showSetbacks: true, measuring: false };
});

const plot = () => plotById("plot-concave");

/** One keystroke: `setValue` also fires `change`, which is the end of an entry
 *  and not what typing looks like. */
const typeInto = async (field, text) => {
  field.element.value = text;
  await field.trigger("input");
};

describe("Lageplan", () => {
  const build = (props = {}) =>
    mount(SitePlan, { props: { plot: plot(), building: placement(plot()), ...props } });

  /* A backdrop that cannot be fetched used to restart itself: the failure flag
     was part of `hasBackdrop`, whose watcher rebuilt the map, and the rebuild
     cleared the flag again. Nothing on screen showed it — the drawing looked
     fine while the tab burned a core and re-asked the backend for the style
     forever. The count is the whole test: one attempt, then silence. */
  it("versucht einen Kartenhintergrund, der nicht lädt, nicht endlos erneut", async () => {
    const asked = [];
    const original = globalThis.fetch;
    // The loop this guards against starves the microtask queue, so no timeout
    // can end it — not the browser's, not the runner's. The stub therefore has
    // to be the brake: past the cap it hands back a promise that never settles,
    // which parks the component and lets the assertion below actually run.
    globalThis.fetch = url => {
      asked.push(String(url));
      return asked.length > 4 ? new Promise(() => {}) : Promise.reject(new Error("kein Netz"));
    };
    try {
      const w = build({ backdrop: "map" });
      for (let i = 0; i < 12; i++) await nextTick();

      expect(asked.length).toBeLessThanOrEqual(1);
      // And it gives up visibly rather than pretending: plain paper, no container.
      expect(w.find(".site-plan__map").exists()).toBe(false);
      expect(w.vm.mapUnavailable).toBe(true);
    } finally {
      globalThis.fetch = original;
    }
  });

  it("zeichnet ohne NaN und ohne undefined", () => {
    const html = build().html();
    expect(html).not.toMatch(/NaN/);
    expect(html).not.toMatch(/undefined/);
  });

  it("färbt den Randstreifen, nicht den bebaubaren Bereich", () => {
    const w = build();
    const ring = w.find("path[fill-rule='evenodd']");
    expect(ring.exists()).toBe(true);
    expect(ring.attributes("fill")).toBe("var(--w2b-map-setback)");
    expect(ring.attributes("d").match(/M/g)).toHaveLength(2);
    expect(w.find("polygon[stroke-dasharray='6 4']").attributes("fill")).toBe("none");
  });

  it("lässt den Randstreifen abschalten", () => {
    expect(build({ showSetbacks: false }).find("path[fill-rule='evenodd']").exists()).toBe(false);
  });

  it("verzichtet in der Miniatur auf Maßketten und Maßstabsleiste", () => {
    const large = build(), small = build({ compact: true });
    expect(large.findAll("marker").length).toBeGreaterThan(0);
    expect(large.text()).toMatch(/\d+,\d\d m/);
    expect(small.text()).not.toMatch(/\d+,\d\d m/);
    expect(small.text()).not.toContain("20 m");
  });

  it("steht genordet gerade und dreht auf die Straßenfront", () => {
    expect(build({ northUp: true }).find("g[transform^='rotate']").attributes("transform")).toMatch(/^rotate\(0,/);
    const parallel = build({ northUp: false });
    const angle = Number(parallel.find("g[transform^='rotate']").attributes("transform").match(/rotate\(([-\d.]+),/)[1]);
    expect(angle).toBeCloseTo(alignmentToEdge(plot().polygon, plot().streetEdge ?? 0), 1);
  });

  it("markiert den Verstoß, sobald der Baukörper hinausragt", () => {
    const envelope = buildableArea(plot().polygon, plot().setbacks);
    const fitting = findPlacement(envelope, 11.44, 8.47);
    expect(fitting).not.toBeNull();
    const inside = build({ building: { ...fitting, width: 11.44, depth: 8.47 } });
    expect(inside.find("[data-house] polygon").attributes("stroke")).toBe("var(--w2b-map-design-edge)");
    const huge = { ...placement(plot()), width: 200, depth: 200 };
    const outside = build({ building: huge });
    expect(outside.find("[data-house] polygon").attributes("stroke")).toBe("var(--w2b-map-violation)");
    expect(outside.findAll("[data-house] circle").length).toBeGreaterThan(0);
  });

  it("meldet Verschiebungen per Pfeiltaste, grob und fein", async () => {
    const w = build({ interactive: true });
    await w.find("[data-house]").trigger("keydown", { key: "ArrowUp" });
    expect(w.emitted("move")[0][0].cy).toBeCloseTo(placement(plot()).cy + 0.25, 6);
    await w.find("[data-house]").trigger("keydown", { key: "ArrowRight", shiftKey: true });
    expect(w.emitted("move")[1][0].cx).toBeCloseTo(placement(plot()).cx + 1, 6);
  });

  it("ist ohne interaktiv nicht bedienbar", async () => {
    const w = build();
    await w.find("[data-house]").trigger("keydown", { key: "ArrowUp" });
    expect(w.emitted("move")).toBeUndefined();
  });

  /* Before a house is chosen there is nothing to draw, and drawing one anyway
     is what made the cadastral check look like a design step. */
  it("lässt den Baukörper samt seiner Maße weg, wenn keiner gezeigt wird", () => {
    const w = build({ showBuilding: false });
    expect(w.find("[data-house]").exists()).toBe(false);
    // The plot's own dimensions and the setback strip are the point of the view.
    expect(w.find("path[fill-rule='evenodd']").exists()).toBe(true);
    // One chain per boundary segment and not one more: the two the house would
    // have contributed are exactly what "no body shown" has to drop.
    expect(w.vm.dimensionChains).toHaveLength(w.vm.plot.polygon.length);
    expect(w.vm.narrowest).toBeNull();
    expect(w.find("svg").attributes("aria-label")).not.toContain("Baukörper");
    expect(w.html()).not.toMatch(/NaN|undefined/);
  });

  it("kommt ohne Baukörper aus, auch wenn keiner übergeben wird", () => {
    const w = mount(SitePlan, { props: { plot: plot() } });
    expect(w.find("[data-house]").exists()).toBe(false);
    expect(w.html()).not.toMatch(/NaN|undefined/);
  });
});

/* Pan and zoom are folded into `view`, which is also what the camera is
   derived from — so the basemap follows the drawing instead of drifting
   behind a CSS transform. */
describe("Ausschnitt bewegen", () => {
  const build = (props = {}) => mount(SitePlan, {
    props: { plot: plot(), building: placement(plot()), navigable: true, ...props },
    attachTo: document.body
  });

  /** jsdom measures nothing; the drawing is told it fills its own viewBox. */
  const framed = w => {
    const svg = w.vm.$refs.svg;
    svg.getBoundingClientRect = () => ({ left: 0, top: 0, width: w.props("width"), height: w.props("height") });
    svg.setPointerCapture = () => {};
    return svg;
  };

  it("zoomt mit dem Rad auf den Zeiger zu", async () => {
    const w = build();
    const svg = framed(w);
    const at = { clientX: 240, clientY: 180 };
    const before = w.vm.toMetres(at);
    const scaleBefore = w.vm.view.scale;

    svg.dispatchEvent(new WheelEvent("wheel", { bubbles: true, cancelable: true, ...at, deltaY: -240 }));
    await nextTick();

    expect(w.vm.view.scale).toBeGreaterThan(scaleBefore);
    // The metre under the cursor is the fixed point of the zoom.
    const after = w.vm.toMetres(at);
    expect(after.x).toBeCloseTo(before.x, 6);
    expect(after.y).toBeCloseTo(before.y, 6);
  });

  it("begrenzt den Zoom nach oben und unten", async () => {
    const w = build();
    const svg = framed(w);
    for (let i = 0; i < 60; i++) {
      svg.dispatchEvent(new WheelEvent("wheel", { bubbles: true, cancelable: true, clientX: 320, clientY: 220, deltaY: -240 }));
    }
    await nextTick();
    expect(w.vm.zoomFactor).toBe(8);
    for (let i = 0; i < 120; i++) {
      svg.dispatchEvent(new WheelEvent("wheel", { bubbles: true, cancelable: true, clientX: 320, clientY: 220, deltaY: 240 }));
    }
    await nextTick();
    expect(w.vm.zoomFactor).toBe(0.25);
  });

  it("verschiebt mit gedrückter Maustaste und hält den gegriffenen Punkt", async () => {
    const w = build();
    const svg = framed(w);
    const grabbed = w.vm.toMetres({ clientX: 300, clientY: 220 });
    const centreBefore = { x: w.vm.view.mx, y: w.vm.view.my };

    svg.dispatchEvent(new MouseEvent("pointerdown", { bubbles: true, clientX: 300, clientY: 220 }));
    await nextTick();
    svg.dispatchEvent(new MouseEvent("pointermove", { bubbles: true, clientX: 350, clientY: 260 }));
    await nextTick();

    expect(w.vm.view.mx).not.toBeCloseTo(centreBefore.x, 6);
    expect(w.vm.view.my).not.toBeCloseTo(centreBefore.y, 6);
    const held = w.vm.toMetres({ clientX: 350, clientY: 260 });
    expect(held.x).toBeCloseTo(grabbed.x, 6);
    expect(held.y).toBeCloseTo(grabbed.y, 6);

    // A double click puts the fitted framing back.
    svg.dispatchEvent(new MouseEvent("dblclick", { bubbles: true }));
    await nextTick();
    expect(w.vm.view.mx).toBeCloseTo(centreBefore.x, 6);
    expect(w.vm.zoomFactor).toBe(1);
  });

  it("rührt den Ausschnitt nicht an, solange er nicht bewegbar ist", async () => {
    const w = build({ navigable: false });
    const svg = framed(w);
    const before = { ...w.vm.view };
    svg.dispatchEvent(new WheelEvent("wheel", { bubbles: true, cancelable: true, clientX: 240, clientY: 180, deltaY: -240 }));
    svg.dispatchEvent(new MouseEvent("pointerdown", { bubbles: true, clientX: 300, clientY: 220 }));
    svg.dispatchEvent(new MouseEvent("pointermove", { bubbles: true, clientX: 350, clientY: 260 }));
    await nextTick();
    expect(w.vm.view).toEqual(before);
  });

  it("lässt dem Messen und dem Baukörper den Vortritt", async () => {
    const measuring = build({ measuring: true, interactive: true });
    const svg = framed(measuring);
    svg.dispatchEvent(new MouseEvent("pointerdown", { bubbles: true, clientX: 300, clientY: 220 }));
    await nextTick();
    expect(measuring.vm.panning).toBeNull();
    expect(measuring.vm.measurePoints).toHaveLength(1);

    const dragging = build({ interactive: true });
    framed(dragging);
    const house = dragging.find("[data-house]").element;
    house.dispatchEvent(new MouseEvent("pointerdown", { bubbles: true, clientX: 300, clientY: 220 }));
    await nextTick();
    expect(dragging.vm.panning).toBeNull();
    expect(dragging.vm.dragging).not.toBeNull();
  });

  it("stellt den Ausschnitt her, sobald ein anderes Flurstück gezeigt wird", async () => {
    const w = build();
    const svg = framed(w);
    svg.dispatchEvent(new WheelEvent("wheel", { bubbles: true, cancelable: true, clientX: 240, clientY: 180, deltaY: -240 }));
    await nextTick();
    expect(w.vm.zoomFactor).not.toBe(1);
    await w.setProps({ plot: plotById("plot-convex"), building: placement(plotById("plot-convex")) });
    expect(w.vm.zoomFactor).toBe(1);
    expect(w.vm.panMetres).toEqual({ x: 0, y: 0 });
  });
});

describe("Messwerkzeug", () => {
  const build = () => mount(SitePlan, {
    props: { plot: plot(), building: placement(plot()), interactive: true, measuring: true },
    attachTo: document.body
  });

  /** Dispatch a real pointer event: test-utils cannot set clientX on a MouseEvent. */
  const click = async (w, point) => {
    const svg = w.vm.$refs.svg;
    svg.getBoundingClientRect = () => ({ left: 0, top: 0, width: w.props("width"), height: w.props("height") });
    svg.setPointerCapture = () => {};
    svg.dispatchEvent(new MouseEvent("pointerdown", {
      bubbles: true, clientX: w.vm.px(point.x), clientY: w.vm.py(point.y)
    }));
    await w.vm.$nextTick();
  };

  it("misst die Strecke zwischen zwei angeklickten Punkten", async () => {
    const w = build();
    await click(w, { x: 0, y: 0 });
    await click(w, { x: 30, y: 40 });     // 3-4-5, also 50 m
    const [, second] = w.emitted("measured");
    expect(second[0].points).toHaveLength(2);
    expect(second[0].length).toBeCloseTo(50, 1);
    expect(w.text()).toContain("50,0");
  });

  it("summiert einen Streckenzug über mehrere Abschnitte", async () => {
    const w = build();
    for (const p of [{ x: 0, y: 0 }, { x: 30, y: 40 }, { x: 30, y: 0 }]) await click(w, p);
    const last = w.emitted("measured").at(-1)[0];
    expect(last.length).toBeCloseTo(90, 1);
    expect(w.text()).toContain("gesamt");
  });

  it("verschiebt beim Messen nicht den Baukörper", async () => {
    const w = build();
    await click(w, { x: 0, y: 0 });
    expect(w.emitted("move")).toBeUndefined();
  });

  it("räumt die Messung weg, sobald der Modus endet", async () => {
    const w = build();
    await click(w, { x: 0, y: 0 });
    expect(w.vm.measurePoints).toHaveLength(1);
    await w.setProps({ measuring: false });
    expect(w.vm.measurePoints).toEqual([]);
  });
});

describe("Grundstückskarte", () => {
  it("zeigt die amtlichen Zahlen des echten Flurstücks", () => {
    const w = mount(PlotCard, { props: { plot: plot(), selected: true } });
    expect(w.text()).toContain("1.685 m²");
    expect(w.text()).toMatch(/\d+,\d\d €/);
    expect(w.text()).toMatch(/komplex|rechteckig/);
  });

  it("meldet Öffnen, Entfernen und Auswahl", async () => {
    const w = mount(PlotCard, { props: { plot: plot(), selected: false } });
    await w.find(".plot-card__plan").trigger("click");
    expect(w.emitted("open")).toBeTruthy();
    await w.findAll(".plot-card__foot button")[1].trigger("click");
    expect(w.emitted("remove")).toBeTruthy();
    await w.find(".plot-card__select input").setValue(true);
    expect(w.emitted("select")[0]).toEqual([true]);
  });
});

describe("Leere Zustände", () => {
  it("bietet die Aufnahme an, wenn noch nichts da ist", () => {
    state.data = { version: 2, plots: [], houseTypes: [], destinations: [], selection: [] };
    const t = mountWithRouter(PlotsView, { path: "/grundstuecke" }).text();
    expect(t).toContain("Noch nichts in der Prüfung");
    expect(t).toContain("Grundstück hinzufügen");
  });

  it("sagt beim Haustyp-Katalog, dass er leer ist", () => {
    state.data.houseTypes = [];
    const t = mountWithRouter(HouseTypesView).text();
    expect(t).toContain("Noch kein Haustyp im Katalog");
  });

  it("verlangt erst eine Koordinate, bevor von Wegen die Rede ist", () => {
    // The recorded state has a destination with an address but no coordinate.
    const w = mount(RouteCards, { props: { plot: plot() } });
    expect(w.text()).toContain("noch nicht verortet");
    expect(w.text()).not.toMatch(/\d+ min/);
    expect(w.find("polyline").exists()).toBe(false);
  });

  it("zeigt keine erfundenen Wege, wenn das Ziel verortet, aber nichts gerechnet ist", () => {
    state.data.destinations[0].lat = 51.3397;
    state.data.destinations[0].lon = 12.3731;
    const w = mount(RouteCards, { props: { plot: plot() } });
    expect(w.text()).toContain("Noch nicht berechnet");
    expect(w.text()).not.toMatch(/\d+ min/);
    expect(w.find("polyline").exists()).toBe(false);
  });

  it("sagt es, wenn keine Ziele hinterlegt sind", () => {
    state.data.destinations = [];
    expect(mount(RouteCards, { props: { plot: plot() } }).text()).toContain("Noch keine Ziele");
  });
});

describe("Kartenhintergrund", () => {
  it("legt ohne ausgewählten Grund gar keine Karte an", () => {
    // Every backdrop is a MapLibre instance. The small plans on cards and in
    // the comparison must not each start one.
    const w = mount(SitePlan, { props: { plot: plot(), building: placement(plot()) } });
    expect(w.props("backdrop")).toBe("none");
    expect(w.find(".site-plan__map").exists()).toBe(false);
  });

  it("bietet alle Gründe an, sperrt sie aber ohne Koordinate", async () => {
    const withoutAnchor = { ...plot() };
    delete withoutAnchor.anchor;
    state.data.plots = [withoutAnchor];
    const buttons = mountWithRouter(PlotView, { props: { id: withoutAnchor.id } })
      .findAll('[aria-label="Kartenhintergrund"] button');
    expect(buttons.map(b => b.text())).toEqual(["Ohne", "Karte", "Luftbild", "Kataster"]);
    expect(buttons[0].attributes("disabled")).toBeUndefined();
    buttons.slice(1).forEach(b => expect(b.attributes("disabled")).toBeDefined());
  });

  it("gibt die Gründe frei, sobald eine Koordinate da ist", () => {
    const buttons = mountWithRouter(PlotView, { props: { id: "plot-concave" } }).findAll('[aria-label="Kartenhintergrund"] button');
    buttons.forEach(b => expect(b.attributes("disabled")).toBeUndefined());
  });
});

describe("Straßenfront", () => {
  it("misst die Kante, die das Grundstück selbst als Straßenkante führt", () => {
    // Nicht die erste Kante des Rings: die Vereinigung zweier Flurstücke
    // beginnt dort, wo ihre Umrisse sich treffen — bei 204 und 205 in Mölkau
    // ein 2,04-m-Stummel, der als Straßenfront ausgewiesen wurde.
    const p = { ...plot(), streetEdge: 2 };
    const edges = polygonEdges(p.polygon);

    expect(plotMetrics(p).streetFrontage).toBeCloseTo(edges[2].length, 6);
    expect(plotMetrics({ ...p, streetEdge: 0 }).streetFrontage).toBeCloseTo(edges[0].length, 6);
    // Eine Kante, die es nicht gibt, fällt auf die erste zurück statt zu werfen.
    expect(plotMetrics({ ...p, streetEdge: 99 }).streetFrontage).toBeCloseTo(edges[0].length, 6);
  });
});

describe("Preis ohne Kaufpreis", () => {
  it("rechnet nichts aus, was es nicht gibt", () => {
    // ALKIS knows the parcel; only the listing knows the asking price. Without
    // it the old code printed "0,00 €" and "-100 % under the land value".
    const withoutPrice = { ...plot(), askingPrice: null };
    const metrics = plotMetrics(withoutPrice);
    expect(metrics.pricePerSqm).toBeNull();
    expect(metrics.deviation).toBeNull();
    expect(metrics.deviationClass).toBe("unknown");
  });

  it("sagt auf der Seite, dass der Vergleich fehlt, statt −100 % zu zeigen", () => {
    plot().askingPrice = null;
    const t = mountWithRouter(PlotView, { props: { id: "plot-concave" } }).text();
    expect(t).toContain("Ohne Kaufpreis lässt sich das Angebot nicht");
    expect(t).toContain("Kaufpreis—");        // an em dash, not a number
    expect(t).toContain("Angebot je m²—");
    expect(t).not.toMatch(/−\d+,\d %/);       // no deviation invented from a gap
  });

  it("beschriftet die Karte des Grundstücks entsprechend", () => {
    plot().askingPrice = null;
    const t = mount(PlotCard, { props: { plot: plot(), selected: false } }).text();
    expect(t).toContain("kein Kaufpreis");
  });
});

describe("Grundstücksseite", () => {
  it("stellt amtliche und gerechnete Fläche nebeneinander", () => {
    const t = mountWithRouter(PlotView, { props: { id: "plot-concave" } }).text();
    expect(t).toContain("1.685 m²");
    expect(t).toContain(area(polygonArea(plot().polygon), 1));
  });

  it("benennt die Grenzen nach der Himmelsrichtung", () => {
    const t = mountWithRouter(PlotView, { props: { id: "plot-concave" } }).text();
    expect(t).toMatch(/(Nord|Ost|Süd|West|Nordost|Nordwest|Südost|Südwest) — zur Straße/);
    expect(t).not.toMatch(/Grenze \d/);
  });

  it("nennt keine Anforderungsnummern", () => {
    const t = mountWithRouter(PlotView, { props: { id: "plot-concave" } }).text();
    expect(t).not.toMatch(/\bF-\d\d\b/);
  });

  it("richtet den Baukörper an der Straße aus und lässt ihn im Fenster", async () => {
    const w = mountWithRouter(PlotView, { props: { id: "plot-concave" } });
    const p = plot();
    p.house.rotation = 40;
    await w.findAll("button").find(b => b.text().includes("An der Straße ausrichten")).trigger("click");
    expect(p.house.rotation).toBeCloseTo(alignmentToEdge(p.polygon, p.streetEdge ?? 0), 0);
    expect(cornersOutside(placement(p), buildableArea(p.polygon, p.setbacks))).toBe(0);
  });

  /* The house may not be dragged out of the buildable window -- unless there
     is no window to hold it in, which is the only case where the constraint
     would take away the ability to move the house at all. */
  it("hält den Baukörper im Fenster, solange es eines gibt", async () => {
    const w = mountWithRouter(PlotView, { props: { id: "plot-concave" } });
    const p = plot();
    const plan = w.findComponent(SitePlan);
    expect(plan.props("confineToEnvelope")).toBe(true);

    const far = { cx: p.house.cx + 400, cy: p.house.cy + 400 };
    const allowed = plan.vm.allowedMove(far);
    expect(allowed).not.toEqual(far);
    expect(cornersOutside({ ...placement(p), ...allowed },
                          buildableArea(p.polygon, p.setbacks))).toBe(0);
  });

  it("lässt den Baukörper frei, wenn die Begrenzung abgeschaltet ist", async () => {
    const w = mountWithRouter(PlotView, { props: { id: "plot-concave" } });
    const p = plot();
    const toggle = w.findAll("button").find(b => b.text().includes("Im Bebauungsfenster halten"));
    expect(toggle.attributes("aria-pressed")).toBe("true");

    await toggle.trigger("click");
    expect(p.confineHouse).toBe(false);
    expect(toggle.attributes("aria-pressed")).toBe("false");
    const far = { cx: p.house.cx + 400, cy: p.house.cy + 400 };
    expect(w.findComponent(SitePlan).vm.allowedMove(far)).toEqual(far);
  });

  /* Mölkau, Flurstück 204: a real 650 m² plot, and narrow enough that the
     window leaves little room -- exactly where a constraint has to hold. */
  it("hält den Baukörper auch auf dem Flurstück in Mölkau im Fenster", async () => {
    const moelkau = { ...realPlot("moelkau"), houseTypeId: "custom",
                      customSize: { length: 8, width: 6 } };
    const envelope = buildableArea(moelkau.polygon, moelkau.setbacks);
    /* The plot is a 47.9 x 13.5 m ribbon running diagonally: unrotated, no
       8 x 6 m house fits into its window at all. So it is seated first --
       held inside is a statement about a house that is inside to begin with. */
    const seat = findPlacement(envelope, 8, 6);
    expect(seat).not.toBeNull();
    moelkau.house = { cx: seat.cx, cy: seat.cy, rotation: seat.rotation };
    state.data.plots.push(moelkau);

    const w = mountWithRouter(PlotView, { props: { id: "plot-moelkau" } });
    const p = plotById("plot-moelkau");
    expect(cornersOutside(placement(p), envelope)).toBe(0);

    const plan = w.findComponent(SitePlan);
    for (const [dx, dy] of [[80, 0], [-80, 0], [0, 80], [0, -80]]) {
      const allowed = plan.vm.allowedMove({ cx: p.house.cx + dx, cy: p.house.cy + dy });
      expect(cornersOutside({ ...placement(p), ...allowed }, envelope)).toBe(0);
    }
  });

  /* Switching the constraint on with the house already outside would otherwise
     leave a violation that dragging can no longer undo. */
  it("setzt den Baukörper zurück ins Fenster, wenn die Begrenzung eingeschaltet wird", async () => {
    const p = plot();
    p.confineHouse = false;
    p.house.cx += 40;
    const w = mountWithRouter(PlotView, { props: { id: "plot-concave" } });
    expect(cornersOutside(placement(p), buildableArea(p.polygon, p.setbacks))).toBeGreaterThan(0);

    await w.findAll("button").find(b => b.text().includes("Im Bebauungsfenster halten")).trigger("click");
    expect(p.confineHouse).toBe(true);
    expect(cornersOutside(placement(p), buildableArea(p.polygon, p.setbacks))).toBe(0);
  });

  it("koppelt die Abstandstiefe an die Wandhöhe, mit 3 m als Mindestmaß", async () => {
    const w = mountWithRouter(PlotView, { props: { id: "plot-concave" } });
    const p = plot();
    await w.find("#wall-height").setValue("10");
    expect(p.setbacks.every(d => Math.abs(d - 4) < 0.05)).toBe(true);
    await w.find("#wall-height").setValue("4");
    expect(p.setbacks.every(d => d === 3)).toBe(true);
  });

  it("erlaubt eigene Maße und hält sie in den Grenzen", async () => {
    const w = mountWithRouter(PlotView, { props: { id: "plot-concave" } });
    await w.find("#house-type").setValue("custom");
    expect(plot().houseTypeId).toBe("custom");
    await w.find("#custom-length").setValue("13");
    expect(placement(plot()).width).toBe(13);
    await w.find("#custom-length").setValue("99");   // setValue ends the entry: input, then change
    expect(plot().customSize.length).toBe(30);
    await w.find("#custom-width").setValue("1");
    expect(plot().customSize.width).toBe(4);
  });

  /* Typing 14 goes through 1, and 1 is not a 4 m house — it is half a number.
     Clamping on every keystroke rewrote the field under the cursor, so the 1
     became a 4 and the field ended up on 44. Nothing is corrected until the
     field is left. */
  it("schreibt eigene Maße während des Tippens nicht um", async () => {
    const w = mountWithRouter(PlotView, { props: { id: "plot-concave" } });
    await w.find("#house-type").setValue("custom");
    const length = w.find("#custom-length");
    const stored = plot().customSize.length;

    await typeInto(length, "1");
    expect(length.element.value).toBe("1");
    expect(plot().customSize.length).toBe(stored);   // implausible, so not passed on
    await typeInto(length, "14");
    expect(length.element.value).toBe("14");
    expect(plot().customSize.length).toBe(14);

    await length.trigger("change");
    await nextTick();
    expect(length.element.value).toBe("14");
    expect(placement(plot()).width).toBe(14);
  });

  it("richtet ein endgültig ungültiges Maß erst beim Verlassen des Feldes, und nie auf null", async () => {
    const w = mountWithRouter(PlotView, { props: { id: "plot-concave" } });
    await w.find("#house-type").setValue("custom");
    const length = w.find("#custom-length");
    await length.setValue("14");

    await typeInto(length, "2");
    expect(plot().customSize.length).toBe(14);
    expect(w.text()).toContain("Kantenlängen unter 4 m oder über 30 m");
    await length.trigger("change");
    await nextTick();
    expect(plot().customSize.length).toBe(4);
    expect(length.element.value).toBe("4");

    // An empty field is no building either: the stored size stays as it was.
    await typeInto(length, "");
    await length.trigger("change");
    await nextTick();
    expect(plot().customSize.length).toBe(4);
    expect(Number.isFinite(plot().customSize.width)).toBe(true);
    expect(length.element.value).toBe("4");
  });

  it("schaltet das Messen ein und wieder aus", async () => {
    const w = mountWithRouter(PlotView, { props: { id: "plot-concave" } });
    const button = w.findAll("button").find(b => b.text().trim() === "Messen");
    await button.trigger("click");
    expect(state.plan.measuring).toBe(true);
    expect(w.text()).toContain("Auf den Plan klicken");
    await button.trigger("click");
    expect(state.plan.measuring).toBe(false);
  });
});

describe("Haustypen", () => {
  it("prüft je Grundstück, ob der Baukörper passt", () => {
    const w = mountWithRouter(HouseTypesView);
    const headings = w.findAll(".fits__head").map(n => n.text());
    expect(headings).toHaveLength(state.data.houseTypes.length);
    headings.forEach(h => expect(h).toMatch(/^Passt auf \d von 2 Grundstücken$/));
  });

  it("setzt einen Typ auf ein Grundstück und öffnet es zulässig", async () => {
    const router = testRouter();
    const w = mountWithRouter(HouseTypesView, { router });
    const button = w.findAll(".fits__button")[0];
    if (!button) return;                      // kein Typ passt auf ein Grundstück
    await button.trigger("click");
    await router.isReady();
    expect(router.currentRoute.value.name).toBe("plot");
    const p = plotById(router.currentRoute.value.params.id);
    expect(cornersOutside(placement(p), buildableArea(p.polygon, p.setbacks))).toBe(0);
  });

  it("nimmt von Hand eingetragene Maße auf", async () => {
    const w = mountWithRouter(HouseTypesView);
    const before = state.data.houseTypes.length;
    await w.findAll(".page-head .btn")[0].trigger("click");
    await w.find("#manual-length").setValue(12);
    await w.find("#manual-width").setValue(9);
    await w.findAll("button").find(b => b.text().trim() === "In den Katalog").trigger("click");
    expect(state.data.houseTypes).toHaveLength(before + 1);
    expect(state.data.houseTypes.at(-1).builtArea).toBe(108);
  });
});

describe("Vergleich", () => {
  it("zeichnet alle Grundrisse wirklich im selben Maßstab", () => {
    // Passing the same prop is not the same as using it: SitePlan used to
    // compute its own fit per plot and ignore the value, so the panel claimed
    // a shared scale it did not have and the "rund 1 : N" chip was wrong.
    const w = mountWithRouter(CompareView);
    const plans = w.findAllComponents({ name: "SitePlan" });
    expect(plans.length).toBeGreaterThan(1);

    const given = new Set(plans.map(p => p.props("scale")));
    expect(given.size).toBe(1);

    // What actually reaches the drawing: viewBox units per metre.
    const used = new Set(plans.map(p => p.vm.view.scale.toFixed(6)));
    expect(used.size).toBe(1);
    expect(Number([...used][0])).toBeCloseTo([...given][0], 6);
  });

  it("wählt den Maßstab so, dass auch das größte Grundstück hineinpasst", () => {
    const w = mountWithRouter(CompareView);
    w.findAllComponents({ name: "SitePlan" }).forEach(plan => {
      const box = boundingBox(plan.props("plot").polygon);
      const scale = plan.vm.view.scale;
      expect(box.width * scale).toBeLessThanOrEqual(plan.props("width"));
      expect(box.height * scale).toBeLessThanOrEqual(plan.props("height"));
    });
  });

  it("listet nur die ausgewählten Kandidaten", () => {
    state.data.selection = ["plot-concave"];
    expect(mountWithRouter(CompareView).findAll("tbody tr")).toHaveLength(1);
  });
});

describe("Aufnahme — Schritt Flurstück", () => {
  /** The wizard reaches stage 3 with a draft in hand; a reload has none. */
  const atParcelStage = async () => {
    const w = mountWithRouter(WizardView, { path: "/aufnahme/quelle", props: { stage: "quelle" } });
    w.vm.draft = plot();
    await w.setProps({ stage: "flurstueck" });
    return w;
  };

  it("prüft den Zuschnitt ohne Baukörper", async () => {
    // The step asks one question — is this the right parcel — and a house
    // nobody has planned yet is not part of it.
    const original = globalThis.fetch;
    globalThis.fetch = () => new Promise(() => {});   // no basemap in jsdom
    try {
      const w = await atParcelStage();
      const plan = w.findComponent({ name: "SitePlan" });
      expect(plan.props("building")).toBeNull();
      expect(plan.props("showBuilding")).toBe(false);
      expect(w.find("[data-house]").exists()).toBe(false);
      // Der Schritt trägt jetzt auch die Angaben, also endet er beim Anlegen.
      expect(w.text()).toContain("Anlegen und öffnen");
    } finally {
      globalThis.fetch = original;
    }
  });

  it("nimmt Name, Kaufpreis und Notiz im selben Schritt auf", async () => {
    // Drei Felder waren eine eigene Seite, und der Umriss, den sie beschreiben,
    // war dabei nicht zu sehen.
    const original = globalThis.fetch;
    globalThis.fetch = () => new Promise(() => {});
    try {
      const w = await atParcelStage();

      expect(w.find("#q-name").exists()).toBe(true);
      expect(w.find("#q-price").exists()).toBe(true);
      expect(w.find("#q-note").exists()).toBe(true);
      expect(w.findComponent({ name: "SitePlan" }).exists()).toBe(true);
    } finally {
      globalThis.fetch = original;
    }
  });

  it("lässt den Ausschnitt dort verschieben und zoomen", async () => {
    const original = globalThis.fetch;
    globalThis.fetch = () => new Promise(() => {});
    try {
      const w = await atParcelStage();
      const plan = w.findComponent({ name: "SitePlan" });
      expect(plan.props("navigable")).toBe(true);

      const svg = plan.vm.$refs.svg;
      svg.getBoundingClientRect = () => ({ left: 0, top: 0, width: plan.props("width"), height: plan.props("height") });
      svg.setPointerCapture = () => {};
      const before = { ...plan.vm.view };

      svg.dispatchEvent(new WheelEvent("wheel", { bubbles: true, cancelable: true, clientX: 260, clientY: 200, deltaY: -240 }));
      await nextTick();
      expect(plan.vm.view.scale).toBeGreaterThan(before.scale);

      svg.dispatchEvent(new MouseEvent("pointerdown", { bubbles: true, clientX: 260, clientY: 200 }));
      await nextTick();
      svg.dispatchEvent(new MouseEvent("pointermove", { bubbles: true, clientX: 300, clientY: 240 }));
      await nextTick();
      expect(plan.vm.view.mx).not.toBeCloseTo(before.mx, 6);
    } finally {
      globalThis.fetch = original;
    }
  });
});
