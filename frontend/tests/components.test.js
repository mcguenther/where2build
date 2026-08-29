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
import { echterStand } from "./hilfe.js";
import { buildableArea, cornersOutside, alignmentToEdge, polygonArea, findPlacement } from "../src/lib/geometry.js";
import { area } from "../src/lib/format.js";
import { plotMetrics } from "../src/lib/metrics.js";

beforeEach(() => {
  localStorage.clear();
  state.daten = echterStand();
  state.offenesGrundstueck = "gs-konkav";
  // "ohne": mounting must not reach for a basemap. The backdrop is verified in
  // the browser by scripts/screenshots.mjs, which fails if no tile arrives.
  state.plan = { grund: "ohne", genordet: true, masse: true, saum: true, messen: false };
});

const plot = () => plotById("gs-konkav");

describe("Lageplan", () => {
  const bauen = (props = {}) =>
    mount(SitePlan, { props: { plot: plot(), koerper: placement(plot()), ...props } });

  it("zeichnet ohne NaN und ohne undefined", () => {
    const html = bauen().html();
    expect(html).not.toMatch(/NaN/);
    expect(html).not.toMatch(/undefined/);
  });

  it("färbt den Randstreifen, nicht den bebaubaren Bereich", () => {
    const w = bauen();
    const ring = w.find("path[fill-rule='evenodd']");
    expect(ring.exists()).toBe(true);
    expect(ring.attributes("fill")).toBe("var(--w2b-karte-saum)");
    expect(ring.attributes("d").match(/M/g)).toHaveLength(2);
    expect(w.find("polygon[stroke-dasharray='6 4']").attributes("fill")).toBe("none");
  });

  it("lässt den Randstreifen abschalten", () => {
    expect(bauen({ saum: false }).find("path[fill-rule='evenodd']").exists()).toBe(false);
  });

  it("verzichtet in der Miniatur auf Maßketten und Maßstabsleiste", () => {
    const gross = bauen(), klein = bauen({ kompakt: true });
    expect(gross.findAll("marker").length).toBeGreaterThan(0);
    expect(gross.text()).toMatch(/\d+,\d\d m/);
    expect(klein.text()).not.toMatch(/\d+,\d\d m/);
    expect(klein.text()).not.toContain("20 m");
  });

  it("steht genordet gerade und dreht auf die Straßenfront", () => {
    expect(bauen({ genordet: true }).find("g[transform^='rotate']").attributes("transform")).toMatch(/^rotate\(0,/);
    const parallel = bauen({ genordet: false });
    const winkel = Number(parallel.find("g[transform^='rotate']").attributes("transform").match(/rotate\(([-\d.]+),/)[1]);
    expect(winkel).toBeCloseTo(alignmentToEdge(plot().polygon, plot().strassenkante ?? 0), 1);
  });

  it("markiert den Verstoß, sobald der Baukörper hinausragt", () => {
    const fenster = buildableArea(plot().polygon, plot().tiefen);
    const lage = findPlacement(fenster, 11.44, 8.47);
    expect(lage).not.toBeNull();
    const drin = bauen({ koerper: { ...lage, width: 11.44, depth: 8.47 } });
    expect(drin.find("[data-haus] polygon").attributes("stroke")).toBe("var(--w2b-karte-entwurf-rand)");
    const weit = { ...placement(plot()), width: 200, depth: 200 };
    const raus = bauen({ koerper: weit });
    expect(raus.find("[data-haus] polygon").attributes("stroke")).toBe("var(--w2b-karte-verstoss)");
    expect(raus.findAll("[data-haus] circle").length).toBeGreaterThan(0);
  });

  it("meldet Verschiebungen per Pfeiltaste, grob und fein", async () => {
    const w = bauen({ interaktiv: true });
    await w.find("[data-haus]").trigger("keydown", { key: "ArrowUp" });
    expect(w.emitted("verschieben")[0][0].cy).toBeCloseTo(placement(plot()).cy + 0.25, 6);
    await w.find("[data-haus]").trigger("keydown", { key: "ArrowRight", shiftKey: true });
    expect(w.emitted("verschieben")[1][0].cx).toBeCloseTo(placement(plot()).cx + 1, 6);
  });

  it("ist ohne interaktiv nicht bedienbar", async () => {
    const w = bauen();
    await w.find("[data-haus]").trigger("keydown", { key: "ArrowUp" });
    expect(w.emitted("verschieben")).toBeUndefined();
  });
});

describe("Messwerkzeug", () => {
  const bauen = () => mount(SitePlan, {
    props: { plot: plot(), koerper: placement(plot()), interaktiv: true, messen: true },
    attachTo: document.body
  });

  /** Dispatch a real pointer event: test-utils cannot set clientX on a MouseEvent. */
  const klick = async (w, punkt) => {
    const flaeche = w.vm.$refs.flaeche;
    flaeche.getBoundingClientRect = () => ({ left: 0, top: 0, width: w.props("breite"), height: w.props("hoehe") });
    flaeche.setPointerCapture = () => {};
    flaeche.dispatchEvent(new MouseEvent("pointerdown", {
      bubbles: true, clientX: w.vm.px(punkt.x), clientY: w.vm.py(punkt.y)
    }));
    await w.vm.$nextTick();
  };

  it("misst die Strecke zwischen zwei angeklickten Punkten", async () => {
    const w = bauen();
    await klick(w, { x: 0, y: 0 });
    await klick(w, { x: 30, y: 40 });     // 3-4-5, also 50 m
    const [, zweite] = w.emitted("gemessen");
    expect(zweite[0].punkte).toHaveLength(2);
    expect(zweite[0].laenge).toBeCloseTo(50, 1);
    expect(w.text()).toContain("50,0");
  });

  it("summiert einen Streckenzug über mehrere Abschnitte", async () => {
    const w = bauen();
    for (const p of [{ x: 0, y: 0 }, { x: 30, y: 40 }, { x: 30, y: 0 }]) await klick(w, p);
    const letzte = w.emitted("gemessen").at(-1)[0];
    expect(letzte.laenge).toBeCloseTo(90, 1);
    expect(w.text()).toContain("gesamt");
  });

  it("verschiebt beim Messen nicht den Baukörper", async () => {
    const w = bauen();
    await klick(w, { x: 0, y: 0 });
    expect(w.emitted("verschieben")).toBeUndefined();
  });

  it("räumt die Messung weg, sobald der Modus endet", async () => {
    const w = bauen();
    await klick(w, { x: 0, y: 0 });
    expect(w.vm.messpunkte).toHaveLength(1);
    await w.setProps({ messen: false });
    expect(w.vm.messpunkte).toEqual([]);
  });
});

describe("Grundstückskarte", () => {
  it("zeigt die amtlichen Zahlen des echten Flurstücks", () => {
    const w = mount(PlotCard, { props: { plot: plot(), gewaehlt: true } });
    expect(w.text()).toContain("1.685 m²");
    expect(w.text()).toMatch(/\d+,\d\d €/);
    expect(w.text()).toMatch(/komplex|rechteckig/);
  });

  it("meldet Öffnen, Entfernen und Auswahl", async () => {
    const w = mount(PlotCard, { props: { plot: plot(), gewaehlt: false } });
    await w.find(".karte__riss").trigger("click");
    expect(w.emitted("oeffnen")).toBeTruthy();
    await w.findAll(".karte__fuss button")[1].trigger("click");
    expect(w.emitted("entfernen")).toBeTruthy();
    await w.find(".karte__wahl input").setValue(true);
    expect(w.emitted("auswaehlen")[0]).toEqual([true]);
  });
});

describe("Leere Zustände", () => {
  it("bietet die Aufnahme an, wenn noch nichts da ist", () => {
    state.daten = { version: 1, grundstuecke: [], haustypen: [], ziele: [], auswahl: [] };
    const t = mount(PlotsView).text();
    expect(t).toContain("Noch nichts in der Prüfung");
    expect(t).toContain("Grundstück hinzufügen");
  });

  it("sagt beim Haustyp-Katalog, dass er leer ist", () => {
    state.daten.haustypen = [];
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
    state.daten.ziele[0].lat = 51.3397;
    state.daten.ziele[0].lon = 12.3731;
    const w = mount(RouteCards, { props: { plot: plot() } });
    expect(w.text()).toContain("Noch nicht berechnet");
    expect(w.text()).not.toMatch(/\d+ min/);
    expect(w.find("polyline").exists()).toBe(false);
  });

  it("sagt es, wenn keine Ziele hinterlegt sind", () => {
    state.daten.ziele = [];
    expect(mount(RouteCards, { props: { plot: plot() } }).text()).toContain("Noch keine Ziele");
  });
});

describe("Kartenhintergrund", () => {
  it("legt ohne ausgewählten Grund gar keine Karte an", () => {
    // Every backdrop is a MapLibre instance. The small plans on cards and in
    // the comparison must not each start one.
    const w = mount(SitePlan, { props: { plot: plot(), koerper: placement(plot()) } });
    expect(w.props("grund")).toBe("ohne");
    expect(w.find(".lageplan__karte").exists()).toBe(false);
  });

  it("bietet alle Gründe an, sperrt sie aber ohne Koordinate", async () => {
    const ohneAnker = { ...plot() };
    delete ohneAnker.anker;
    state.daten.grundstuecke = [ohneAnker];
    state.offenesGrundstueck = ohneAnker.id;
    const knoepfe = mount(PlotView).findAll('[aria-label="Kartenhintergrund"] button');
    expect(knoepfe.map(k => k.text())).toEqual(["Ohne", "Karte", "Luftbild", "Kataster"]);
    expect(knoepfe[0].attributes("disabled")).toBeUndefined();
    knoepfe.slice(1).forEach(k => expect(k.attributes("disabled")).toBeDefined());
  });

  it("gibt die Gründe frei, sobald eine Koordinate da ist", () => {
    const knoepfe = mount(PlotView).findAll('[aria-label="Kartenhintergrund"] button');
    knoepfe.forEach(k => expect(k.attributes("disabled")).toBeUndefined());
  });
});

describe("Preis ohne Kaufpreis", () => {
  it("rechnet nichts aus, was es nicht gibt", () => {
    // ALKIS knows the parcel; only the listing knows the asking price. Without
    // it the old code printed "0,00 €" and "-100 % under the land value".
    const ohnePreis = { ...plot(), kaufpreis: null };
    const werte = plotMetrics(ohnePreis);
    expect(werte.jeQuadratmeter).toBeNull();
    expect(werte.abweichung).toBeNull();
    expect(werte.abweichungKlasse).toBe("unbekannt");
  });

  it("sagt auf der Seite, dass der Vergleich fehlt, statt −100 % zu zeigen", () => {
    plot().kaufpreis = null;
    const t = mount(PlotView).text();
    expect(t).toContain("Ohne Kaufpreis lässt sich das Angebot nicht");
    expect(t).toContain("Kaufpreis—");        // an em dash, not a number
    expect(t).toContain("Angebot je m²—");
    expect(t).not.toMatch(/−\d+,\d %/);       // no deviation invented from a gap
  });

  it("beschriftet die Karte des Grundstücks entsprechend", () => {
    plot().kaufpreis = null;
    const t = mount(PlotCard, { props: { plot: plot(), gewaehlt: false } }).text();
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
    p.haus.rotation = 40;
    await w.findAll("button").find(b => b.text().includes("An der Straße ausrichten")).trigger("click");
    expect(p.haus.rotation).toBeCloseTo(alignmentToEdge(p.polygon, p.strassenkante ?? 0), 0);
    expect(cornersOutside(placement(p), buildableArea(p.polygon, p.tiefen))).toBe(0);
  });

  it("koppelt die Abstandstiefe an die Wandhöhe, mit 3 m als Mindestmaß", async () => {
    const w = mount(PlotView);
    const p = plot();
    await w.find("#wandhoehe").setValue("10");
    expect(p.tiefen.every(t => Math.abs(t - 4) < 0.05)).toBe(true);
    await w.find("#wandhoehe").setValue("4");
    expect(p.tiefen.every(t => t === 3)).toBe(true);
  });

  it("erlaubt eigene Maße und hält sie in den Grenzen", async () => {
    const w = mount(PlotView);
    await w.find("#haustyp").setValue("eigen");
    expect(plot().haustypId).toBe("eigen");
    await w.find("#em-laenge").setValue("13");
    expect(placement(plot()).width).toBe(13);
    await w.find("#em-laenge").setValue("99");
    expect(plot().eigenmass.laenge).toBe(30);
    await w.find("#em-breite").setValue("1");
    expect(plot().eigenmass.breite).toBe(4);
  });

  it("schaltet das Messen ein und wieder aus", async () => {
    const w = mount(PlotView);
    const knopf = w.findAll("button").find(b => b.text().trim() === "Messen");
    await knopf.trigger("click");
    expect(state.plan.messen).toBe(true);
    expect(w.text()).toContain("Auf den Plan klicken");
    await knopf.trigger("click");
    expect(state.plan.messen).toBe(false);
  });
});

describe("Haustypen", () => {
  it("prüft je Grundstück, ob der Baukörper passt", () => {
    const w = mount(HouseTypesView);
    const kopfzeilen = w.findAll(".passt__kopf").map(n => n.text());
    expect(kopfzeilen).toHaveLength(state.daten.haustypen.length);
    kopfzeilen.forEach(z => expect(z).toMatch(/^Passt auf \d von 2 Grundstücken$/));
  });

  it("setzt einen Typ auf ein Grundstück und öffnet es zulässig", async () => {
    const w = mount(HouseTypesView);
    const knopf = w.findAll(".passt__knopf")[0];
    if (!knopf) return;                       // kein Typ passt auf ein Grundstück
    await knopf.trigger("click");
    expect(state.ansicht).toBe("grundstueck");
    const p = plotById(state.offenesGrundstueck);
    expect(cornersOutside(placement(p), buildableArea(p.polygon, p.tiefen))).toBe(0);
  });

  it("nimmt von Hand eingetragene Maße auf", async () => {
    const w = mount(HouseTypesView);
    const vorher = state.daten.haustypen.length;
    await w.findAll(".seitenkopf .knopf")[0].trigger("click");
    await w.find("#e-laenge").setValue(12);
    await w.find("#e-breite").setValue(9);
    await w.findAll("button").find(b => b.text().trim() === "In den Katalog").trigger("click");
    expect(state.daten.haustypen).toHaveLength(vorher + 1);
    expect(state.daten.haustypen.at(-1).bebauteFlaeche).toBe(108);
  });
});

describe("Vergleich", () => {
  it("zeichnet alle Grundrisse im selben Maßstab", () => {
    const w = mount(CompareView);
    const massstaebe = new Set(w.findAllComponents({ name: "SitePlan" }).map(p => p.props("massstab")));
    expect(massstaebe.size).toBe(1);
    expect(w.vm.gemeinsamerMassstab).toBeGreaterThan(0);
    expect(w.text()).toMatch(/rund 1 : \d+/);
  });

  it("listet nur die ausgewählten Kandidaten", () => {
    state.daten.auswahl = ["gs-konkav"];
    expect(mount(CompareView).findAll("tbody tr")).toHaveLength(1);
  });
});
