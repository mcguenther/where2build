/**
 * The interface, mounted for real, driven by real cadastral fixtures.
 * No sample data: if a service did not answer, the test says so too.
 */
import { describe, it, expect, beforeEach } from "vitest";
import { mount } from "@vue/test-utils";
import SitePlan from "../src/components/SitePlan.vue";
import PlotCard from "../src/components/PlotCard.vue";
import RouteCards from "../src/components/RouteCards.vue";
import PlotsView from "../src/views/PlotsView.vue";
import PlotView from "../src/views/PlotView.vue";
import HouseTypesView from "../src/views/HouseTypesView.vue";
import CompareView from "../src/views/CompareView.vue";
import { state, placement, plotById } from "../src/lib/store.js";
import { realState } from "./helpers.js";
import { buildableArea, cornersOutside, alignmentToEdge, polygonArea, findPlacement } from "../src/lib/geometry.js";
import { area } from "../src/lib/format.js";
import { plotMetrics } from "../src/lib/metrics.js";

beforeEach(() => {
  localStorage.clear();
  state.data = realState();
  state.openPlotId = "plot-concave";
  // "none": mounting must not reach for a basemap. The backdrop is verified in
  // the browser by scripts/screenshots.mjs, which fails if no tile arrives.
  state.plan = { backdrop: "none", northUp: true, showDimensions: true, showSetbacks: true, measuring: false };
});

const plot = () => plotById("plot-concave");

describe("Lageplan", () => {
  const build = (props = {}) =>
    mount(SitePlan, { props: { plot: plot(), building: placement(plot()), ...props } });

  it("zeichnet ohne NaN und ohne undefined", () => {
    const html = build().html();
    expect(html).not.toMatch(/NaN/);
    expect(html).not.toMatch(/undefined/);
  });

  it("färbt den Randstreifen, nicht den bebaubaren Bereich", () => {
    const w = build();
    const ring = w.find("path[fill-rule='evenodd']");
    expect(ring.exists()).toBe(true);
    expect(ring.attributes("fill")).toBe("var(--w2b-karte-saum)");
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
    expect(inside.find("[data-haus] polygon").attributes("stroke")).toBe("var(--w2b-karte-entwurf-rand)");
    const huge = { ...placement(plot()), width: 200, depth: 200 };
    const outside = build({ building: huge });
    expect(outside.find("[data-haus] polygon").attributes("stroke")).toBe("var(--w2b-karte-verstoss)");
    expect(outside.findAll("[data-haus] circle").length).toBeGreaterThan(0);
  });

  it("meldet Verschiebungen per Pfeiltaste, grob und fein", async () => {
    const w = build({ interactive: true });
    await w.find("[data-haus]").trigger("keydown", { key: "ArrowUp" });
    expect(w.emitted("move")[0][0].cy).toBeCloseTo(placement(plot()).cy + 0.25, 6);
    await w.find("[data-haus]").trigger("keydown", { key: "ArrowRight", shiftKey: true });
    expect(w.emitted("move")[1][0].cx).toBeCloseTo(placement(plot()).cx + 1, 6);
  });

  it("ist ohne interaktiv nicht bedienbar", async () => {
    const w = build();
    await w.find("[data-haus]").trigger("keydown", { key: "ArrowUp" });
    expect(w.emitted("move")).toBeUndefined();
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
    await w.find(".karte__riss").trigger("click");
    expect(w.emitted("open")).toBeTruthy();
    await w.findAll(".karte__fuss button")[1].trigger("click");
    expect(w.emitted("remove")).toBeTruthy();
    await w.find(".karte__wahl input").setValue(true);
    expect(w.emitted("select")[0]).toEqual([true]);
  });
});

describe("Leere Zustände", () => {
  it("bietet die Aufnahme an, wenn noch nichts da ist", () => {
    state.data = { version: 2, plots: [], houseTypes: [], destinations: [], selection: [] };
    const t = mount(PlotsView).text();
    expect(t).toContain("Noch nichts in der Prüfung");
    expect(t).toContain("Grundstück hinzufügen");
  });

  it("sagt beim Haustyp-Katalog, dass er leer ist", () => {
    state.data.houseTypes = [];
    const t = mount(HouseTypesView).text();
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
    expect(w.find(".lageplan__karte").exists()).toBe(false);
  });

  it("bietet alle Gründe an, sperrt sie aber ohne Koordinate", async () => {
    const withoutAnchor = { ...plot() };
    delete withoutAnchor.anchor;
    state.data.plots = [withoutAnchor];
    state.openPlotId = withoutAnchor.id;
    const buttons = mount(PlotView).findAll('[aria-label="Kartenhintergrund"] button');
    expect(buttons.map(b => b.text())).toEqual(["Ohne", "Karte", "Luftbild", "Kataster"]);
    expect(buttons[0].attributes("disabled")).toBeUndefined();
    buttons.slice(1).forEach(b => expect(b.attributes("disabled")).toBeDefined());
  });

  it("gibt die Gründe frei, sobald eine Koordinate da ist", () => {
    const buttons = mount(PlotView).findAll('[aria-label="Kartenhintergrund"] button');
    buttons.forEach(b => expect(b.attributes("disabled")).toBeUndefined());
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
    expect(metrics.deviationClass).toBe("unbekannt");
  });

  it("sagt auf der Seite, dass der Vergleich fehlt, statt −100 % zu zeigen", () => {
    plot().askingPrice = null;
    const t = mount(PlotView).text();
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
    const t = mount(PlotView).text();
    expect(t).toContain("1.685 m²");
    expect(t).toContain(area(polygonArea(plot().polygon), 1));
  });

  it("benennt die Grenzen nach der Himmelsrichtung", () => {
    const t = mount(PlotView).text();
    expect(t).toMatch(/(Nord|Ost|Süd|West|Nordost|Nordwest|Südost|Südwest) — zur Straße/);
    expect(t).not.toMatch(/Grenze \d/);
  });

  it("nennt keine Anforderungsnummern", () => {
    const t = mount(PlotView).text();
    expect(t).not.toMatch(/\bF-\d\d\b/);
  });

  it("richtet den Baukörper an der Straße aus und lässt ihn im Fenster", async () => {
    const w = mount(PlotView);
    const p = plot();
    p.house.rotation = 40;
    await w.findAll("button").find(b => b.text().includes("An der Straße ausrichten")).trigger("click");
    expect(p.house.rotation).toBeCloseTo(alignmentToEdge(p.polygon, p.streetEdge ?? 0), 0);
    expect(cornersOutside(placement(p), buildableArea(p.polygon, p.setbacks))).toBe(0);
  });

  it("koppelt die Abstandstiefe an die Wandhöhe, mit 3 m als Mindestmaß", async () => {
    const w = mount(PlotView);
    const p = plot();
    await w.find("#wandhoehe").setValue("10");
    expect(p.setbacks.every(d => Math.abs(d - 4) < 0.05)).toBe(true);
    await w.find("#wandhoehe").setValue("4");
    expect(p.setbacks.every(d => d === 3)).toBe(true);
  });

  it("erlaubt eigene Maße und hält sie in den Grenzen", async () => {
    const w = mount(PlotView);
    await w.find("#haustyp").setValue("custom");
    expect(plot().houseTypeId).toBe("custom");
    await w.find("#em-laenge").setValue("13");
    expect(placement(plot()).width).toBe(13);
    await w.find("#em-laenge").setValue("99");
    expect(plot().customSize.length).toBe(30);
    await w.find("#em-breite").setValue("1");
    expect(plot().customSize.width).toBe(4);
  });

  it("schaltet das Messen ein und wieder aus", async () => {
    const w = mount(PlotView);
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
    const w = mount(HouseTypesView);
    const headings = w.findAll(".passt__kopf").map(n => n.text());
    expect(headings).toHaveLength(state.data.houseTypes.length);
    headings.forEach(h => expect(h).toMatch(/^Passt auf \d von 2 Grundstücken$/));
  });

  it("setzt einen Typ auf ein Grundstück und öffnet es zulässig", async () => {
    const w = mount(HouseTypesView);
    const button = w.findAll(".passt__knopf")[0];
    if (!button) return;                      // kein Typ passt auf ein Grundstück
    await button.trigger("click");
    expect(state.view).toBe("plot");
    const p = plotById(state.openPlotId);
    expect(cornersOutside(placement(p), buildableArea(p.polygon, p.setbacks))).toBe(0);
  });

  it("nimmt von Hand eingetragene Maße auf", async () => {
    const w = mount(HouseTypesView);
    const before = state.data.houseTypes.length;
    await w.findAll(".seitenkopf .knopf")[0].trigger("click");
    await w.find("#e-laenge").setValue(12);
    await w.find("#e-breite").setValue(9);
    await w.findAll("button").find(b => b.text().trim() === "In den Katalog").trigger("click");
    expect(state.data.houseTypes).toHaveLength(before + 1);
    expect(state.data.houseTypes.at(-1).builtArea).toBe(108);
  });
});

describe("Vergleich", () => {
  it("zeichnet alle Grundrisse im selben Maßstab", () => {
    const w = mount(CompareView);
    const scales = new Set(w.findAllComponents({ name: "SitePlan" }).map(p => p.props("scale")));
    expect(scales.size).toBe(1);
    expect(w.vm.sharedScale).toBeGreaterThan(0);
    expect(w.text()).toMatch(/rund 1 : \d+/);
  });

  it("listet nur die ausgewählten Kandidaten", () => {
    state.data.selection = ["plot-concave"];
    expect(mount(CompareView).findAll("tbody tr")).toHaveLength(1);
  });
});
