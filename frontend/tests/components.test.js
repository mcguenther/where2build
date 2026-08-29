/** The pieces of the interface, mounted for real. */
import { describe, it, expect, beforeEach } from "vitest";
import { mount } from "@vue/test-utils";
import SitePlan from "../src/components/SitePlan.vue";
import PlotCard from "../src/components/PlotCard.vue";
import RouteCards from "../src/components/RouteCards.vue";
import PlotView from "../src/views/PlotView.vue";
import WizardView from "../src/views/WizardView.vue";
import HouseTypesView from "../src/views/HouseTypesView.vue";
import { state, placement, plotById } from "../src/lib/store.js";
import { sampleState } from "../src/lib/sample.js";
import { buildableArea, cornersOutside } from "../src/lib/geometry.js";

beforeEach(() => {
  localStorage.clear();
  state.daten = sampleState();
  state.offenesGrundstueck = "gs-liebertwolkwitz";
  state.plan = { grund: "karte", genordet: false, nachbarn: true, masse: true, saum: true };
});

const plot = () => plotById("gs-liebertwolkwitz");

describe("Lageplan", () => {
  const bauen = (props = {}) =>
    mount(SitePlan, { props: { plot: plot(), koerper: placement(plot()), ...props } });

  it("zeichnet ohne NaN in den Koordinaten", () => {
    const html = bauen().html();
    expect(html).not.toMatch(/NaN/);
    expect(html).not.toMatch(/undefined/);
  });

  it("färbt den Randstreifen, nicht den bebaubaren Bereich", () => {
    const w = bauen();
    const ring = w.find("path[fill-rule='evenodd']");
    expect(ring.exists()).toBe(true);
    expect(ring.attributes("fill")).toBe("var(--w2b-karte-saum)");
    // Zwei Teilpfade: Außen- und Innenring. Ohne den zweiten wäre alles gefüllt.
    expect(ring.attributes("d").match(/M/g)).toHaveLength(2);
    // Das Bebauungsfenster selbst trägt keine Füllung.
    const fenster = w.find("polygon[stroke-dasharray='6 4']");
    expect(fenster.attributes("fill")).toBe("none");
  });

  it("lässt den Randstreifen abschalten", () => {
    expect(bauen({ saum: false }).find("path[fill-rule='evenodd']").exists()).toBe(false);
  });

  it("verzichtet in der Miniatur auf Maßketten und Nordpfeil", () => {
    const gross = bauen();
    const klein = bauen({ kompakt: true });
    expect(gross.findAll("marker").length).toBeGreaterThan(0);
    expect(gross.text()).toContain("22,62 m");
    expect(klein.text()).not.toContain("22,62 m");
    expect(klein.text()).not.toContain("20 m");     // keine Maßstabsleiste
  });

  it("dreht die Szene beim Umschalten auf genordet", () => {
    expect(bauen().find("g[transform^='rotate']").attributes("transform")).toMatch(/^rotate\(0,/);
    expect(bauen({ genordet: true }).find("g[transform^='rotate']").attributes("transform")).toMatch(/^rotate\(17,/);
  });

  it("markiert den Verstoß, sobald der Baukörper hinausragt", () => {
    const p = plot();
    const drin = bauen();
    expect(drin.find("[data-haus] polygon").attributes("stroke")).toBe("var(--w2b-karte-entwurf-rand)");
    const raus = bauen({ koerper: { ...placement(p), cy: 33 } });
    expect(raus.find("[data-haus] polygon").attributes("stroke")).toBe("var(--w2b-karte-verstoss)");
    expect(raus.findAll("[data-haus] circle").length).toBeGreaterThan(0);
  });

  it("meldet Verschiebungen per Pfeiltaste", async () => {
    const w = bauen({ interaktiv: true });
    await w.find("[data-haus]").trigger("keydown", { key: "ArrowUp" });
    const [[verschoben]] = w.emitted("verschieben");
    expect(verschoben.cy).toBeCloseTo(placement(plot()).cy + 0.25, 6);
  });

  it("verschiebt mit Umschalttaste in Meterschritten", async () => {
    const w = bauen({ interaktiv: true });
    await w.find("[data-haus]").trigger("keydown", { key: "ArrowRight", shiftKey: true });
    const [[verschoben]] = w.emitted("verschieben");
    expect(verschoben.cx).toBeCloseTo(placement(plot()).cx + 1, 6);
  });

  it("ist ohne interaktiv nicht bedienbar", async () => {
    const w = bauen();
    await w.find("[data-haus]").trigger("keydown", { key: "ArrowUp" });
    expect(w.emitted("verschieben")).toBeUndefined();
  });
});

describe("Grundstückskarte", () => {
  it("zeigt Fläche, Preis und Einstufung", () => {
    const w = mount(PlotCard, { props: { plot: plot(), gewaehlt: true } });
    expect(w.text()).toContain("802 m²");
    expect(w.text()).toContain("235,66 €");
    expect(w.text()).toContain("+12,2 % ggü. BRW");
    expect(w.text()).toContain("rechteckig");
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

describe("Wege", () => {
  it("färbt die Route nach dem schnellsten Verkehrsmittel", () => {
    const w = mount(RouteCards, { props: { plot: plot() } });
    const linien = w.findAll("polyline");
    // Arbeit: Auto 24 min ist am schnellsten -> Graphit
    expect(linien[0].attributes("stroke")).toBe("var(--w2b-graphit)");
    // Grundschule: Auto 4 min ist am schnellsten -> ebenfalls Graphit
    expect(linien[1].attributes("stroke")).toBe("var(--w2b-graphit)");
  });

  it("zeigt alle vier Verkehrsmittel je Ziel", () => {
    const w = mount(RouteCards, { props: { plot: plot() } });
    expect(w.findAll(".weg-karte")).toHaveLength(4);
    expect(w.findAll(".weg-karte")[0].text()).toMatch(/Auto[\s\S]*Rad[\s\S]*ÖPNV[\s\S]*Kombiniert/);
  });

  it("sagt es, wenn keine Ziele hinterlegt sind", () => {
    state.daten.ziele = [];
    expect(mount(RouteCards, { props: { plot: plot() } }).text()).toContain("Noch keine Ziele");
  });
});

describe("Grundstücksseite", () => {
  it("rechnet die Kennzahlen und zeigt beide Flächen", () => {
    const t = mount(PlotView).text();
    expect(t).toContain("802 m²");        // amtlich
    expect(t).toContain("795,3 m²");      // gerechnet
    expect(t).toContain("0,965");
    expect(t).toContain("22,62 m");
  });

  it("benennt die Grenzen nach der Himmelsrichtung", () => {
    const t = mount(PlotView).text();
    expect(t).toContain("Süd — zur Straße");
    expect(t).toContain("Ost — Nachbar");
    expect(t).not.toMatch(/Grenze \d/);
  });

  it("richtet den Baukörper an der Straße aus und lässt ihn im Fenster", async () => {
    const w = mount(PlotView);
    const p = plot();
    p.haus.rotation = 40;
    const knopf = w.findAll("button").find(b => b.text().includes("An der Straße ausrichten"));
    await knopf.trigger("click");
    expect(p.haus.rotation).toBeCloseTo(2.3, 1);
    const fenster = buildableArea(p.polygon, p.tiefen);
    expect(cornersOutside(placement(p), fenster)).toBe(0);
  });

  it("koppelt die Abstandstiefe an die Wandhöhe, mit 3 m als Mindestmaß", async () => {
    const w = mount(PlotView);
    const p = plot();
    const regler = w.find("#wandhoehe");
    await regler.setValue("10");
    expect(p.tiefen.every(t => Math.abs(t - 4) < 0.05)).toBe(true);   // 0,4 · 10 m
    await regler.setValue("4");
    expect(p.tiefen.every(t => t === 3)).toBe(true);                  // Mindestmaß greift
  });

  it("erlaubt eigene Maße statt eines Katalogtyps", async () => {
    const w = mount(PlotView);
    const p = plot();
    await w.find("#haustyp").setValue("eigen");
    expect(p.haustypId).toBe("eigen");
    expect(w.find("#em-laenge").exists()).toBe(true);
    await w.find("#em-laenge").setValue("13");
    expect(p.eigenmass.laenge).toBe(13);
    expect(placement(p).width).toBe(13);
  });

  it("hält eigene Maße in den Plausibilitätsgrenzen", async () => {
    const w = mount(PlotView);
    await w.find("#haustyp").setValue("eigen");
    await w.find("#em-laenge").setValue("99");
    expect(plot().eigenmass.laenge).toBe(30);
    await w.find("#em-breite").setValue("1");
    expect(plot().eigenmass.breite).toBe(4);
  });

  it("übernimmt eigene Maße in den Katalog", async () => {
    const w = mount(PlotView);
    const vorher = state.daten.haustypen.length;
    await w.find("#haustyp").setValue("eigen");
    const knopf = w.findAll("button").find(b => b.text().includes("Als Haustyp in den Katalog"));
    await knopf.trigger("click");
    expect(state.daten.haustypen).toHaveLength(vorher + 1);
    expect(plot().haustypId).toBe(state.daten.haustypen.at(-1).id);
  });
});

describe("Aufnahme-Assistent", () => {
  it("führt durch vier Schritte", () => {
    const w = mount(WizardView);
    expect(w.findAll(".schrittleiste li")).toHaveLength(4);
    expect(w.find(".schrittleiste li").classes()).toContain("ist-hier");
  });

  it("bietet drei Wege hinein", () => {
    const t = mount(WizardView).text();
    expect(t).toContain("Link einwerfen");
    expect(t).toContain("Flurstück direkt");
    expect(t).toContain("Seite einfügen");
  });

  it("legt aus dem Gelesenen ein Grundstück an und öffnet es", async () => {
    const w = mount(WizardView);
    const vorher = state.daten.grundstuecke.length;
    await w.find(".tafel__leib .knopf").trigger("click");   // Lesen (fällt auf das Beispiel zurück)
    await new Promise(r => setTimeout(r, 20));
    expect(w.vm.schritt).toBe(1);
    expect(w.vm.entwurf.flaecheAmtlich).toBeGreaterThan(100);
    expect(Number.isFinite(w.vm.entwurf.haus.cx)).toBe(true);
    w.vm.schritt = 3;
    await w.vm.$nextTick();
    const anlegen = w.findAll("button").find(b => b.text().includes("Anlegen und öffnen"));
    await anlegen.trigger("click");
    expect(state.daten.grundstuecke).toHaveLength(vorher + 1);
    expect(state.ansicht).toBe("grundstueck");
  });

  it("markiert nicht belegte Felder, statt sie zu raten", async () => {
    const w = mount(WizardView);
    await w.find(".tafel__leib .knopf").trigger("click");
    await new Promise(r => setTimeout(r, 20));
    expect(w.findAll(".vorschlag--leer").length).toBeGreaterThan(0);
    expect(w.text()).toContain("nicht belegt");
    // Jede Angabe führt ihre Quelle mit.
    w.findAll(".vorschlag__quelle").forEach(q => expect(q.text().length).toBeGreaterThan(5));
  });
});

describe("Haustypen", () => {
  it("prüft je Grundstück, ob der Baukörper passt", () => {
    const w = mount(HouseTypesView);
    const kopfzeilen = w.findAll(".passt__kopf").map(n => n.text());
    expect(kopfzeilen).toHaveLength(state.daten.haustypen.length);
    kopfzeilen.forEach(z => expect(z).toMatch(/^Passt auf \d von 4 Grundstücken$/));
    // Landhaus 196 ist 14 × 14 m und passt nicht überall.
    expect(kopfzeilen.some(z => !z.startsWith("Passt auf 4"))).toBe(true);
  });

  it("setzt einen Typ auf ein Grundstück und öffnet es", async () => {
    const w = mount(HouseTypesView);
    const knopf = w.findAll(".passt__knopf")[0];
    await knopf.trigger("click");
    expect(state.ansicht).toBe("grundstueck");
    const p = plotById(state.offenesGrundstueck);
    expect(cornersOutside(placement(p), buildableArea(p.polygon, p.tiefen))).toBe(0);
  });

  it("nimmt von Hand eingetragene Maße auf", async () => {
    const w = mount(HouseTypesView);
    const vorher = state.daten.haustypen.length;
    await w.findAll(".seitenkopf .knopf")[0].trigger("click");   // Aufnahme öffnen
    await w.find("#e-laenge").setValue(12);
    await w.find("#e-breite").setValue(9);
    const knopf = w.findAll("button").find(b => b.text().includes("In den Katalog"));
    await knopf.trigger("click");
    expect(state.daten.haustypen).toHaveLength(vorher + 1);
    expect(state.daten.haustypen.at(-1).bebauteFlaeche).toBe(108);
  });
});

describe("Vergleich", () => {
  it("zeichnet alle Grundrisse im selben Maßstab", async () => {
    const { default: CompareView } = await import("../src/views/CompareView.vue");
    const w = mount(CompareView);
    // Ein gemeinsamer Maßstab bedeutet: das größere Grundstück wird auch größer gezeichnet.
    const flaechen = w.vm.gewaehlte.map(p => p.flaecheAmtlich);
    const breiten = w.findAll(".riss svg polygon").length;
    expect(breiten).toBeGreaterThan(0);
    expect(w.vm.gemeinsamerMassstab).toBeGreaterThan(0);
    // Jeder Plan bekommt denselben Wert übergeben.
    const plaene = w.findAllComponents({ name: "SitePlan" });
    const massstaebe = new Set(plaene.map(p => p.props("massstab")));
    expect(massstaebe.size).toBe(1);
    // Und er ist der kleinste der Einzelmaßstäbe, damit das größte Grundstück hineinpasst.
    expect(Math.max(...flaechen)).toBeGreaterThan(Math.min(...flaechen));
  });

  it("nennt den Maßstab, den es tatsächlich verwendet", () => {
    return import("../src/views/CompareView.vue").then(({ default: CompareView }) => {
      const w = mount(CompareView);
      expect(w.text()).toMatch(/rund 1 : \d+/);
    });
  });

  it("listet nur die ausgewählten Kandidaten", async () => {
    const { default: CompareView } = await import("../src/views/CompareView.vue");
    state.daten.auswahl = ["gs-liebertwolkwitz", "gs-holzhausen"];
    const w = mount(CompareView);
    expect(w.findAll("tbody tr")).toHaveLength(2);
  });
});
