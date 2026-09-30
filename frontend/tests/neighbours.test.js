/**
 * The „Nachbarschaft" tab of the plot view.
 *
 * Against what the services really answered for Mölkau, Flurstück 204
 * (Lessingweg 44): `neighbours-moelkau-alkis.json`, 71 outlines from
 * ave:GebaeudeBauwerk; `neighbours-moelkau.json`, 59 from OpenStreetMap;
 * `planung-moelkau.json`, RAPIS with no plan and an FNP Wohnbaufläche; and
 * `planung-zweinaundorf-e215.json`, a plot inside B-Plan E-215. The street
 * edge is settled from `verkehr-moelkau.json` the way the app settles it.
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { nextTick } from "vue";
import { flushPromises } from "@vue/test-utils";

vi.mock("../src/lib/api.js", () => ({
  // The cap the module exports next to the call that sends it. A factory
  // that omits a named export makes every importer fail at *import* time,
  // which shows up as unrelated component errors.
  PAGE_LIMIT: 3000000,
  neighbourBuildings: vi.fn(),
  planning: vi.fn(),
  reachability: vi.fn(() => Promise.reject(new Error("nicht Teil dieses Tests"))),
  nearby: vi.fn(() => new Promise(() => {})),
  // The location record on the same page; these tests are not about it.
  siteChecks: vi.fn(() => new Promise(() => {}))
}));

import SitePlan from "../src/components/SitePlan.vue";
import PlotView from "../src/views/PlotView.vue";
import { state, plotById, CUSTOM_SIZE } from "../src/lib/store.js";
import { streetFront } from "../src/lib/streetFront.js";
import { findPlacement, alignmentToEdge, polygonEdges, buildableArea } from "../src/lib/geometry.js";
import { READING_BOUNDARY } from "../src/lib/neighbourhood.js";
import { realState, realPlot, mountWithRouter } from "./helpers.js";
import osm from "./fixtures/neighbours-moelkau.json";
import cadastre from "./fixtures/neighbours-moelkau-alkis.json";
import streets from "./fixtures/verkehr-moelkau.json";
import planningNone from "./fixtures/planung-moelkau.json";
import planningE215 from "./fixtures/planung-zweinaundorf-e215.json";
import elk from "./fixtures/housetype-elk.json";

const { neighbourBuildings, planning } = await import("../src/lib/api.js");

const ID = "plot-moelkau";
const plot = () => plotById(ID);

beforeEach(() => {
  localStorage.clear();
  state.data = realState();
  const moelkau = realPlot("moelkau");
  const front = streetFront(moelkau.polygon, moelkau.anchor, streets.features, moelkau.lagebezeichnung);
  moelkau.streetEdge = front.edge;
  moelkau.streetFront = { street: front.street, length: front.length };
  state.data.plots.push(moelkau);
  state.plan = { backdrop: "none", northUp: true, showDimensions: true, showSetbacks: true, measuring: false };
  neighbourBuildings.mockReset();
  neighbourBuildings.mockResolvedValue(cadastre);
  planning.mockReset();
  planning.mockResolvedValue(planningNone);
});

const mountPlot = (id = ID) => {
  const w = mountWithRouter(PlotView, { props: { id }, attach: true });
  const svg = w.find("svg.site-plan").element;
  svg.getBoundingClientRect = () => ({ left: 0, top: 0, width: 820, height: 620 });
  svg.setPointerCapture = () => {};
  return w;
};
const tab = (w, name) => w.findAll('[role="tab"]').find(t => t.text() === name);
const openTab = async w => {
  await tab(w, "Nachbarschaft").trigger("click");
  await flushPromises();
  await nextTick();
  return w;
};
const plan = w => w.findComponent(SitePlan);
const finding = (w, title) => w.findAll("#pane-neighbourhood .befund").find(b => b.find(".befund__titel").text() === title);

describe("Der Reiter Nachbarschaft", () => {
  it("steht als dritter Reiter neben Grundstück und Bebauung, ohne Schalter im Plan", () => {
    const w = mountPlot();
    expect(w.findAll('[role="tab"]').map(t => t.text())).toEqual(["Grundstück", "Bebauung", "Nachbarschaft"]);
    expect(w.find(".side-tabs__mark--neighbourhood").exists()).toBe(true);
    // The old switch in the plan bar is gone.
    expect(w.findAll(".plan-bar button").map(b => b.text())).not.toContain("Nachbarn");
  });

  it("fragt nichts, bis er geöffnet wird", () => {
    const w = mountPlot();
    expect(neighbourBuildings).not.toHaveBeenCalled();
    expect(planning).not.toHaveBeenCalled();
    expect(plan(w).props("neighbourhood")).toBeNull();
    expect(plan(w).props("frame")).toBe("plot");
    expect(w.find("#nachbarschaft").exists()).toBe(false);
  });

  it("holt Umrisse und Planungsrecht beim Öffnen, einmal je Grundstück", async () => {
    const w = await openTab(mountPlot());

    expect(neighbourBuildings).toHaveBeenCalledTimes(1);
    expect(neighbourBuildings).toHaveBeenCalledWith(plot().anchor.lat, plot().anchor.lon);
    expect(planning).toHaveBeenCalledTimes(1);
    const ring = planning.mock.calls[0][0];
    // The parcel outline, closed, in [lon, lat] — the body /api/site-checks takes.
    expect(ring).toHaveLength(plot().polygon.length + 1);
    expect(ring[0]).toEqual(ring[ring.length - 1]);
    expect(ring[0][0]).toBeCloseTo(12.44, 1);

    expect(plan(w).props("neighbourhood")).not.toBeNull();
    expect(plan(w).props("frame")).toBe("neighbours");

    await tab(w, "Grundstück").trigger("click");
    expect(plan(w).props("neighbourhood")).toBeNull();
    expect(plan(w).props("frame")).toBe("plot");

    await openTab(w);
    expect(neighbourBuildings).toHaveBeenCalledTimes(1);
    expect(planning).toHaveBeenCalledTimes(1);
  });

  it("lässt sich mit den Pfeiltasten erreichen wie die anderen Reiter", async () => {
    const w = mountPlot();
    await tab(w, "Bebauung").trigger("click");
    await tab(w, "Bebauung").trigger("keydown", { key: "ArrowRight" });
    await flushPromises();
    expect(tab(w, "Nachbarschaft").attributes("aria-selected")).toBe("true");
    expect(w.find("#pane-neighbourhood").element.style.display).not.toBe("none");
    expect(neighbourBuildings).toHaveBeenCalledTimes(1);
  });

  it("zeigt den deutschen Grund, wenn der Dienst nicht antwortet, und fragt beim nächsten Öffnen neu", async () => {
    neighbourBuildings.mockRejectedValueOnce(new Error("Das Liegenschaftskataster antwortet nicht."));
    const w = await openTab(mountPlot());

    expect(w.find("#pane-neighbourhood").text()).toContain("Das Liegenschaftskataster antwortet nicht.");
    expect(plan(w).props("neighbourhood")).toBeNull();
    // The planning answer does not depend on the outlines.
    expect(w.find("#pane-neighbourhood").text()).toContain("wahrscheinlich § 34 BauGB");

    await tab(w, "Grundstück").trigger("click");
    await openTab(w);
    expect(neighbourBuildings).toHaveBeenCalledTimes(2);
    expect(plan(w).props("neighbourhood")).not.toBeNull();
  });

  it("behauptet nichts, wenn dort kein Gebäude erfasst ist", async () => {
    neighbourBuildings.mockResolvedValue({ ...osm, gebaeude: [] });
    const w = await openTab(mountPlot());
    expect(w.find("#pane-neighbourhood").text()).toContain("kein Gebäude erfasst");
    expect(w.find("#nachbarschaft").exists()).toBe(false);
  });

  it("nennt OpenStreetMap, wenn die Umrisse von dort kommen", async () => {
    neighbourBuildings.mockResolvedValue(osm);
    const w = await openTab(mountPlot());
    expect(w.find("#pane-neighbourhood").text()).toContain("Umrisse aus OpenStreetMap, ohne Wandhöhen.");
  });

  it("fragt ohne Koordinate nicht ins Leere", async () => {
    state.data.plots.push({ ...realPlot("moelkau"), id: "plot-ohne-anker", anchor: null });
    const w = await openTab(mountPlot("plot-ohne-anker"));
    expect(w.find("#pane-neighbourhood").text()).toContain("Ohne Koordinate lassen sich keine Nachbargebäude finden.");
    expect(neighbourBuildings).not.toHaveBeenCalled();
    expect(planning).not.toHaveBeenCalled();
  });
});

describe("Befunde und Plan zeigen aufeinander", () => {
  it("nummeriert die Befunde wie die Marken im Plan", async () => {
    const w = await openTab(mountPlot());
    const numbers = w.findAll("#pane-neighbourhood .nummer").map(n => n.text());
    expect(numbers).toEqual(["1", "2", "3", "4"]);
    expect(finding(w, "Lessingweg 42").find(".chip").text()).toBe("an der Grenze");
    expect(finding(w, "Lessingweg 46").find(".chip").text()).toBe("Überdeckung");
    const markers = w.findAll(".nb-marker");
    expect(markers.map(m => m.attributes("data-marker"))).toEqual(["1", "2", "3", "4"]);
    expect(markers[0].attributes("aria-label")).toBe("1: Lessingweg 42");
  });

  it("markiert beim Überfahren beide Seiten und hält die Wahl nach einem Klick", async () => {
    const w = await openTab(mountPlot());
    const n42 = finding(w, "Lessingweg 42");
    const id = n42.attributes("data-building");

    await n42.trigger("pointerenter");
    expect(plan(w).props("activeBuilding")).toBe(id);
    expect(w.find(`.nb-marker[data-building="${id}"]`).classes()).toContain("is-active");
    await n42.trigger("pointerleave");
    expect(plan(w).props("activeBuilding")).toBeNull();

    // A click on the marker in the plan pins the finding in the list.
    await w.find(`.nb-marker[data-building="${id}"]`).trigger("click");
    expect(finding(w, "Lessingweg 42").classes()).toContain("is-active");
    // A click on the plan beside the house leaves the tab open.
    expect(tab(w, "Nachbarschaft").attributes("aria-selected")).toBe("true");
    await w.find(`.nb-marker[data-building="${id}"]`).trigger("click");
    expect(finding(w, "Lessingweg 42").classes()).not.toContain("is-active");
  });

  it("zeichnet die Umrisse, die Zonen und die Grenzbebauung, das Fenster bleibt", async () => {
    const w = mountPlot();
    const envelopeBefore = w.find('polygon[stroke-dasharray="6 4"]').attributes("points");
    await openTab(w);
    expect(w.findAll(".nb-building").length).toBe(71);
    expect(w.findAll(".nb-building--own").length).toBe(1);
    expect(w.findAll("[data-zone]").length).toBe(2);
    expect(w.findAll(".nb-built").length).toBe(1);
    expect(w.findAll(".nb-reach-edge").length).toBeGreaterThan(0);
    // The dashed § 6 envelope never moves: same metres; the frame changed, so
    // compare the analysis' envelope with the plot's own.
    expect(plan(w).props("neighbourhood").envelope.area).toBeCloseTo(312.9, 1);
    expect(envelopeBefore).toBeTruthy();
  });
});

describe("Die Lesart der Grenzbebauung", () => {
  it("steht auf „Abstand nötig“, sagt warum, und merkt sich die andere am Grundstück", async () => {
    const w = await openTab(mountPlot());
    const n42 = () => finding(w, "Lessingweg 42");
    const id = n42().attributes("data-building");
    const buttons = () => n42().findAll(".lesart button");
    expect(buttons().map(b => b.text())).toEqual(["Abstand nötig", "An die Grenze darf gebaut werden"]);
    expect(buttons()[0].attributes("aria-pressed")).toBe("true");
    expect(n42().text()).toContain("die vorsichtige Lesart zeigt nie mehr bebaubare Fläche");
    expect(plan(w).props("neighbourhood").zones.map(z => z.address)).toContain("Lessingweg 42");
    expect(w.findAll(".nb-maybe")).toHaveLength(0);

    await buttons()[1].trigger("click");
    expect(plot().neighbourReadings).toEqual({ [id]: READING_BOUNDARY });
    // Stored with the plot, the way every other plot setting is.
    const stored = Object.keys(localStorage).map(k => localStorage.getItem(k)).join("");
    expect(stored).toContain(`"neighbourReadings":{"${id}":"boundary"}`);
    expect(plan(w).props("neighbourhood").zones.map(z => z.address)).toEqual(["Lessingweg 46"]);
    expect(w.findAll(".nb-maybe")).toHaveLength(1);
    expect(n42().text()).toContain("An die Grenze darf gebaut werden: Dann braucht eine Wand");
    expect(buttons()[1].attributes("aria-pressed")).toBe("true");

    await buttons()[0].trigger("click");
    expect(plot().neighbourReadings).toBeUndefined();
    expect(plan(w).props("neighbourhood").zones.map(z => z.address)).toContain("Lessingweg 42");
  });

  it("kommt mit der gespeicherten Lesart wieder", async () => {
    const first = await openTab(mountPlot());
    const id = finding(first, "Lessingweg 42").attributes("data-building");
    first.unmount();
    plot().neighbourReadings = { [id]: READING_BOUNDARY };

    const w = await openTab(mountPlot());
    expect(finding(w, "Lessingweg 42").findAll(".lesart button")[1].attributes("aria-pressed")).toBe("true");
    expect(w.findAll(".nb-maybe")).toHaveLength(1);
  });
});

describe("Grenze ansehen und Im Schnitt", () => {
  it("öffnet immer nur eine Ansicht und zeigt im Plan, wohin sie schaut", async () => {
    const w = await openTab(mountPlot());
    const open = () => w.findAll("#pane-neighbourhood .aufklapp");
    const button = (title, text) => finding(w, title).findAll(".knopf").find(b => b.text() === text);

    await button("Lessingweg 42", "Grenze ansehen").trigger("click");
    expect(open()).toHaveLength(1);
    expect(finding(w, "Lessingweg 42").find(".aufklapp svg").exists()).toBe(true);
    expect(plan(w).props("neighbourHighlight")).toEqual({ boundary: expect.any(String) });
    expect(w.find(".nb-edge-highlight").exists()).toBe(true);

    await button("Lessingweg 46", "Im Schnitt").trigger("click");
    expect(open()).toHaveLength(1);
    expect(finding(w, "Lessingweg 46").find(".aufklapp").text()).toContain("Schnitt");
    expect(finding(w, "Lessingweg 46").find(".aufklapp").text()).toContain("Höhe unbekannt");
    // The section's figures are the finding's: 2,33 m gap, 0,67 m into the envelope.
    expect(finding(w, "Lessingweg 46").find(".befund__text").text()).toContain("2,33 m vor unserer Grenze");
    expect(finding(w, "Lessingweg 46").find(".aufklapp").text()).toContain("2,33 m");
    expect(finding(w, "Lessingweg 46").find(".aufklapp").text()).toContain("0,67 m ins Fenster");
    expect(plan(w).props("neighbourHighlight")).toEqual({ section: expect.any(Number) });
    expect(w.find(".nb-section__line").exists()).toBe(true);
    // A section never states a height.
    expect(finding(w, "Lessingweg 46").find(".aufklapp").text()).not.toMatch(/\d m hoch|Höhe \d/);

    await finding(w, "Lessingweg 46").find(".aufklapp__kopf button").trigger("click");
    expect(open()).toHaveLength(0);
    expect(plan(w).props("neighbourHighlight")).toBeNull();
  });

  it("öffnet mit einem Klick auf eine Grenze im Schlüsselbild deren Streifen", async () => {
    const w = await openTab(mountPlot());
    const n42 = finding(w, "Lessingweg 42");
    const boundary = plan(w).props("neighbourhood").buildings.find(b => b.id === n42.attributes("data-building")).facing.boundary;

    await w.find(`.kg-seg[data-boundary="${boundary}"]`).trigger("click");
    expect(finding(w, "Lessingweg 42").find(".aufklapp").exists()).toBe(true);
    expect(w.find(`.kg-seg[data-boundary="${boundary}"]`).classes()).toContain("is-open");

    // The street: nothing stands at it, so the strip opens under the key.
    await w.find('.kg-seg[data-boundary="street"]').trigger("keydown", { key: "Enter" });
    expect(w.findAll("#pane-neighbourhood .aufklapp")).toHaveLength(1);
    expect(w.find(".aufklapp--oben").text()).toContain("Kein Gebäude steht näher als 3 m an dieser Grenze");
  });

  it("legt die ausführliche Analyse als Abschnitt unter den Plan", async () => {
    const w = await openTab(mountPlot());
    const detail = w.find("#nachbarschaft");
    expect(detail.find("h2").text()).toBe("Nachbarschaft im Detail");
    const analysis = plan(w).props("neighbourhood");
    expect(detail.findAll(".grenzzeile")).toHaveLength(analysis.boundaries.length);
    expect(detail.findAll(".schnitt-block").length).toBe(analysis.sections.length + 1);
    expect(detail.text()).toContain("Umgebung nach § 34 BauGB");
    expect(w.find('#pane-neighbourhood a[href="#nachbarschaft"]').text()).toBe("Alle Grenzen und Schnitte ↓");
  });
});

describe("Ausschnitt", () => {
  it("rahmt die Nachbarn, auf Wunsch die Straße, und kehrt beim Verlassen zum Grundstück zurück", async () => {
    const w = mountPlot();
    const plotScale = plan(w).vm.view.scale;
    await openTab(w);
    const zoom = () => w.findAll(".plan-zoom button");
    expect(zoom().map(b => b.text())).toEqual(["Grundstück", "Nachbarn", "Straße"]);
    expect(zoom()[1].attributes("aria-pressed")).toBe("true");
    const neighboursScale = plan(w).vm.view.scale;
    expect(neighboursScale).toBeLessThan(plotScale);

    await zoom()[2].trigger("click");
    expect(plan(w).props("frame")).toBe("street");
    expect(plan(w).vm.view.scale).toBeLessThan(neighboursScale);
    expect(w.find(".nb-band").exists()).toBe(true);
    expect(w.findAll(".nb-building.is-band").length).toBe(6);
    // The band's labels stay off the house numbers they would hide.
    const labels = w.findAll(".nb-label").map(l => ({
      text: l.text(), x: Number(l.attributes("x")), y: Number(l.attributes("y"))
    }));
    const reference = labels.find(l => l.text === "Straßengrenze, verlängert");
    expect(reference).toBeTruthy();
    for (const other of labels.filter(l => l !== reference && /^\d/.test(l.text) && !l.text.endsWith(" m"))) {
      const apart = Math.abs(other.x - reference.x) > (reference.text.length + other.text.length) * 3.3
        || Math.abs(other.y - reference.y) > 13;
      expect(apart, `„${other.text}“ unter dem Straßenlabel`).toBe(true);
    }

    await tab(w, "Bebauung").trigger("click");
    expect(plan(w).props("frame")).toBe("plot");
    expect(plan(w).vm.view.scale).toBeCloseTo(plotScale, 6);
    expect(w.find(".plan-zoom").exists()).toBe(false);
  });

  it("fährt den Ausschnitt, statt zu springen, und springt unter „weniger Bewegung“", async () => {
    const frames = [];
    const motion = { matches: false };
    vi.stubGlobal("matchMedia", () => motion);
    vi.stubGlobal("requestAnimationFrame", cb => { frames.push(cb); return frames.length; });
    vi.stubGlobal("cancelAnimationFrame", () => {});
    try {
      const w = await openTab(mountPlot());
      const sitePlan = plan(w).vm;
      await nextTick();
      frames.length = 0;
      const start = sitePlan.view.scale;
      await w.findAll(".plan-zoom button")[2].trigger("click");
      const target = sitePlan.targetFit.scale;
      expect(target).toBeLessThan(start);
      // Half-way: between the two, on the way.
      const t0 = performance.now();
      frames.shift()(t0 + 280);
      expect(sitePlan.view.scale).toBeLessThan(start);
      expect(sitePlan.view.scale).toBeGreaterThan(target);
      frames.shift()(t0 + 10000);
      expect(sitePlan.view.scale).toBeCloseTo(target, 9);

      motion.matches = true;
      await w.findAll(".plan-zoom button")[0].trigger("click");
      expect(sitePlan.view.scale).toBeCloseTo(sitePlan.targetFit.scale, 9);
      expect(sitePlan.tweenFit).toBeNull();
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("springt vom Befund zur Straße", async () => {
    const w = await openTab(mountPlot());
    const band = w.findAll("#pane-neighbourhood .befund").find(b => b.text().startsWith("Umgebung (§ 34 BauGB)"));
    await band.findAll(".knopf").find(b => b.text() === "Auf der Straße zeigen").trigger("click");
    expect(plan(w).props("frame")).toBe("street");
  });
});

describe("Der Baukörper in drei Zuständen", () => {
  const builtArea = elk.felder.bebaute_flaeche_m2.wert;
  const width = Math.sqrt(builtArea * 1.75), depth = builtArea / width;

  /** The house at a spot the analysis picks, with dimensions typed in. */
  const place = (w, near) => {
    const analysis = plan(w).props("neighbourhood");
    const left = analysis.boundaries.find(g => g.kind === "left").edges[0];
    const rotation = alignmentToEdge(plot().polygon, left);
    const seat = findPlacement(analysis.envelope.ring, width, depth, { rotation, near: near(analysis), step: 0.1 });
    plot().confineHouse = false;
    plot().houseTypeId = CUSTOM_SIZE;
    plot().customSize = { length: width, width: depth };
    plot().house = { cx: seat.cx, cy: seat.cy, rotation: seat.rotation };
    return seat;
  };
  const notice = w => w.find(".house-check");
  const streetMiddle = () => {
    const e = polygonEdges(plot().polygon)[plot().streetEdge];
    return { x: (e.a.x + e.b.x) / 2, y: (e.a.y + e.b.y) / 2 };
  };

  it("sagt ohne Nachbarn, was das Fenster allein sagen kann", async () => {
    const w = mountPlot();
    const edges = polygonEdges(plot().polygon);
    const longest = edges.indexOf([...edges].sort((a, b) => b.length - a.length)[0]);
    const rotation = alignmentToEdge(plot().polygon, longest);
    const seat = findPlacement(buildableArea(plot().polygon, plot().setbacks), width, depth,
      { rotation, near: streetMiddle(), step: 0.1 });
    plot().confineHouse = false;
    plot().houseTypeId = CUSTOM_SIZE;
    plot().customSize = { length: width, width: depth };
    plot().house = { cx: seat.cx, cy: seat.cy, rotation };
    await nextTick();
    expect(notice(w).classes()).toContain("notice--good");
    expect(notice(w).text()).toMatch(/^Baukörper liegt im Bebauungsfenster\. Geringster Grenzabstand/);
    plot().house = { ...plot().house, cx: seat.cx + 40 };
    await nextTick();
    expect(notice(w).classes()).toContain("notice--error");
    expect(notice(w).text()).toMatch(/Gebäudeecken? (liegt|liegen) außerhalb/);
  });

  it("wird amber, wo das Haus in eine 6-m-Zone reicht – eine Frage an die Bauaufsicht", async () => {
    const w = await openTab(mountPlot());
    place(w, a => a.buildings.find(b => b.address === "Lessingweg 46").centre);
    await nextTick();
    expect(notice(w).classes()).toContain("notice--zone");
    expect(notice(w).attributes("data-house-status")).toBe("zone");
    expect(notice(w).find("b").text()).toBe("Baukörper liegt im Bebauungsfenster,");
    expect(notice(w).text()).toMatch(/reicht aber \d+,\d\d m in die 6-m-Zone zu Lessingweg/);
    expect(notice(w).text()).toContain("eine Frage an die Bauaufsicht");
    expect(w.find("[data-house] polygon[data-house-status]").attributes("data-house-status")).toBe("zone");
    // It stays amber on the other tabs: the check is always on.
    await tab(w, "Grundstück").trigger("click");
    expect(notice(w).classes()).toContain("notice--zone");
  });

  it("wird grün, wo die Lesart „an die Grenze“ die Zone nimmt", async () => {
    const w = await openTab(mountPlot());
    place(w, streetMiddle);
    await nextTick();
    expect(notice(w).classes()).toContain("notice--zone");
    await finding(w, "Lessingweg 42").findAll(".lesart button")[1].trigger("click");
    expect(notice(w).classes()).toContain("notice--good");
    expect(notice(w).text()).toContain("Baukörper liegt im Bebauungsfenster.");
  });

  it("wird rot, sobald eine Ecke das Fenster verlässt", async () => {
    const w = await openTab(mountPlot());
    const seat = place(w, streetMiddle);
    const m = streetMiddle();
    plot().house = { ...plot().house, cx: seat.cx + (m.x - seat.cx) * 0.6, cy: seat.cy + (m.y - seat.cy) * 0.6 };
    await nextTick();
    expect(notice(w).classes()).toContain("notice--error");
    expect(notice(w).text()).toMatch(/Gebäudeecken? (liegt|liegen) außerhalb des Bebauungsfensters\./);
    expect(w.find("[data-house] polygon[data-house-status]").attributes("data-house-status")).toBe("outside");
  });
});

describe("Planungsrecht", () => {
  it("sagt ohne Treffer, was RAPIS führt, nie „kein Bebauungsplan“", async () => {
    const w = await openTab(mountPlot());
    const text = w.find("#pane-neighbourhood").text();
    expect(text).toContain("In RAPIS kein Bebauungsplan verzeichnet – wahrscheinlich § 34 BauGB. "
      + "Verbindlich ist die städtebauliche Auskunft der Stadt.");
    expect(text).not.toMatch(/(^|[^S] )Kein Bebauungsplan/);
    expect(text).toContain("Wohnbaufläche (FNP der Stadt Leipzig, Fortschreibung, bekannt gemacht am 16.05.2015).");
    const credit = w.find('#pane-neighbourhood a[href="https://rapis.sachsen.de"]');
    expect(credit.text()).toBe("RAPIS Sachsen 09/2026, Landesdirektion Sachsen — dl-de/by-2-0");
    expect(text).toContain("Datenstand 28.09.2026");
    expect(text).toContain("Auskunft gibt die Stadt Leipzig, Amt für Bauordnung und Denkmalpflege");
    expect(text).toContain("22–70 € je Grundstück, etwa vier Wochen");
  });

  it("nennt den Bebauungsplan, in dessen Geltungsbereich das Grundstück liegt", async () => {
    planning.mockResolvedValue(planningE215);
    const w = await openTab(mountPlot());
    const text = w.find("#pane-neighbourhood").text();
    expect(text).toContain("Liegt im Geltungsbereich von B-Pl. E-215 Wohngebiet Zweinaundf.Str. (laut RAPIS Sachsen).");
    expect(text).toContain("Art der Nutzung: Wohnbaufläche (W).");
    expect(text).not.toContain("wahrscheinlich § 34");
  });

  it("zeigt bei einem Fehler den Grund des Backends und keinen Schluss daraus", async () => {
    planning.mockRejectedValue(new Error("RAPIS Sachsen antwortet nicht. Die Bauleitplanung lässt sich gerade nicht abfragen."));
    const w = await openTab(mountPlot());
    const text = w.find("#pane-neighbourhood").text();
    expect(text).toContain("RAPIS Sachsen antwortet nicht.");
    expect(text).not.toContain("kein Bebauungsplan");
    expect(text).not.toContain("§ 34 BauGB. Verbindlich");
    // Where Baulasten are kept does not depend on RAPIS.
    expect(text).toContain("Baulasten stehen nicht im Kataster");
  });
});
