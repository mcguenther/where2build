/**
 * The column beside the plan: the plot on one tab, the house laid on it on the
 * other. A click on the house opens the building tab and marks the footprint;
 * a click anywhere else on the plan goes back to the plot. A drag does neither.
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { nextTick } from "vue";
import PlotView from "../src/views/PlotView.vue";
import { state, plotById } from "../src/lib/store.js";
import { priceStage, PRICE_BAND } from "../src/lib/metrics.js";
import { realState, mountWithRouter } from "./helpers.js";

vi.mock("../src/lib/api.js", () => ({
  PAGE_LIMIT: 3000000,
  nearby: vi.fn(() => new Promise(() => {})),
  reachability: vi.fn(() => Promise.reject(new Error("nicht Teil dieses Tests"))),
  siteChecks: vi.fn(() => new Promise(() => {}))
}));

beforeEach(() => {
  localStorage.clear();
  state.data = realState();
  state.plan = { backdrop: "none", northUp: true, showDimensions: true, showSetbacks: true, measuring: false };
});

const mountPlot = () => {
  const w = mountWithRouter(PlotView, { props: { id: "plot-concave" }, attach: true });
  const svg = w.find("svg.site-plan").element;
  svg.getBoundingClientRect = () => ({ left: 0, top: 0, width: 820, height: 620 });
  svg.setPointerCapture = () => {};
  return w;
};
const pane = (w, id) => w.find(`#pane-${id}`).element;
const shown = el => el.style.display !== "none";
const press = (el, x, y) => el.dispatchEvent(new MouseEvent("pointerdown", { bubbles: true, clientX: x, clientY: y }));
const release = (el, x, y) => el.dispatchEvent(new MouseEvent("pointerup", { bubbles: true, clientX: x, clientY: y }));

describe("Reiter neben dem Plan", () => {
  it("zeigt zuerst das Grundstück, und der Baukörper steht im zweiten Reiter", () => {
    const w = mountPlot();
    const tabs = w.findAll('[role="tab"]').map(t => t.text());
    expect(tabs).toEqual(["Grundstück", "Bebauung"]);
    expect(shown(pane(w, "plot"))).toBe(true);
    expect(shown(pane(w, "building"))).toBe(false);
    // Hidden, not removed: the fields exist for print and keep what is typed.
    expect(w.find("#pane-building #house-type").exists()).toBe(true);
  });

  it("öffnet mit einem Klick auf das Haus den Reiter Bebauung und markiert es", async () => {
    const w = mountPlot();
    const house = w.find("[data-house] polygon").element;
    press(house, 300, 220);
    release(house, 301, 221);
    await nextTick();
    expect(shown(pane(w, "building"))).toBe(true);
    expect(w.find(".site-plan__selection").exists()).toBe(true);
    expect(w.find("[data-house]").attributes("aria-pressed")).toBe("true");
  });

  it("geht mit einem Klick neben das Haus zurück zum Grundstück", async () => {
    const w = mountPlot();
    const house = w.find("[data-house] polygon").element;
    press(house, 300, 220);
    release(house, 300, 220);
    await nextTick();
    const svg = w.find("svg.site-plan").element;
    press(svg, 20, 20);
    release(svg, 20, 20);
    await nextTick();
    expect(shown(pane(w, "plot"))).toBe(true);
    expect(w.find(".site-plan__selection").exists()).toBe(false);
  });

  it("wechselt beim Ziehen nicht den Reiter", async () => {
    const w = mountPlot();
    const house = w.find("[data-house] polygon").element;
    press(house, 300, 220);
    house.dispatchEvent(new MouseEvent("pointermove", { bubbles: true, clientX: 330, clientY: 240 }));
    release(house, 330, 240);
    await nextTick();
    expect(shown(pane(w, "plot"))).toBe(true);
  });

  it("öffnet und schließt den Reiter auch über das Schild auf dem Plan", async () => {
    const w = mountPlot();
    const chip = w.find(".house-chip");
    expect(chip.text()).toContain("Haus");
    await chip.find("button").trigger("click");
    expect(shown(pane(w, "building"))).toBe(true);
    expect(chip.find("button").text()).toBe("Fertig");
    await chip.find("button").trigger("click");
    expect(shown(pane(w, "plot"))).toBe(true);
  });

  it("führt den Hinweis zur Abstandsfläche im Kasten, nicht als Warnkasten", () => {
    const w = mountPlot();
    expect(w.find(".callout").exists()).toBe(false);
    expect(w.find("#pane-plot .hint-fold--caution summary").text()).toBe("Vereinfacht gerechnet, keine Prüfung");
    expect(w.find("#pane-plot").text()).toContain("§ 15 Abs. 2 ImmoWertV");
  });
});

describe("Preis gegen Bodenrichtwert", () => {
  it("teilt die Abweichung in drei Stufen am gezeichneten Band", () => {
    expect(PRICE_BAND).toBe(0.15);
    expect(priceStage(null)).toBeNull();
    expect(priceStage(-20.9)).toBe("below");
    expect(priceStage(-4.3)).toBe("within");
    expect(priceStage(15)).toBe("within");
    expect(priceStage(34.5)).toBe("above");
  });

  /** The plot's asking price set so the offer lands `share` off the land value. */
  const priced = async share => {
    const plot = plotById("plot-concave");
    plot.askingPrice = Math.round(plot.officialArea * plot.bodenrichtwert * (1 + share));
    const w = mountPlot();
    await nextTick();
    return w;
  };

  it("färbt Chip und Zeile grün, wenn das Angebot deutlich darunter liegt", async () => {
    const w = await priced(-0.209);
    expect(w.find("#pane-plot .panel__head .chip--good").text()).toBe("unter Richtwert");
    const line = w.find(".price-verdict");
    expect(line.classes()).toContain("price-verdict--below");
    // The magnitude alone: "−20,9 % unter" said the direction twice.
    expect(line.text()).toContain("20,9 % unter dem Bodenrichtwert");
    expect(line.text()).not.toContain("−");
  });

  it("bleibt neutral im Rahmen der Zone", async () => {
    const w = await priced(-0.043);
    expect(w.find(".price-verdict").classes()).toContain("price-verdict--within");
    expect(w.find(".price-verdict").text()).toContain("im Rahmen der Zone");
    const head = w.findAll("#pane-plot .panel__head").find(h => h.text().startsWith("Preis"));
    expect(head.text()).toContain("im Rahmen");
  });

  it("färbt Chip und Zeile rot, wenn das Angebot deutlich darüber liegt", async () => {
    const w = await priced(0.345);
    expect(w.find("#pane-plot .panel__head .chip--error").text()).toBe("über Richtwert");
    expect(w.find(".price-verdict").classes()).toContain("price-verdict--above");
  });

  it("zeigt ohne Kaufpreis weder Chip noch Zeile, nur den Satz dazu", async () => {
    const plot = plotById("plot-concave");
    plot.askingPrice = null;
    const w = mountPlot();
    expect(w.find(".price-verdict").exists()).toBe(false);
    expect(w.find("#pane-plot").text()).toContain("Ohne Kaufpreis");
  });
});

describe("Hinweise hinter einer Klappe", () => {
  it("klappt die Erklärtexte je Kasten weg und nennt ihre Zahl", () => {
    const w = mountPlot();
    const folds = w.findAll("#pane-plot .hint-fold");
    folds.forEach(f => expect(f.element.open).toBe(false));
    const heads = folds.map(f => f.find("summary").text().replace(/\s+/g, " "));
    expect(heads).toContain("Hinweise 1");                               // Grundstück
    expect(heads.some(h => /^Hinweise [12]$/.test(h))).toBe(true);       // Preis
    expect(heads).toContain("Vereinfacht gerechnet, keine Prüfung");
    expect(w.find("#pane-building .hint-fold summary").text()).toContain("So bedienen Sie den Baukörper");
  });
});
