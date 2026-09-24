/**
 * The column beside the plan: the plot on one tab, the house laid on it on the
 * other. A click on the house opens the building tab and marks the footprint;
 * a click anywhere else on the plan goes back to the plot. A drag does neither.
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { nextTick } from "vue";
import PlotView from "../src/views/PlotView.vue";
import { state } from "../src/lib/store.js";
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
    expect(w.find("#pane-plot .caveat summary").text()).toBe("Vereinfacht gerechnet, keine Prüfung");
    expect(w.find("#pane-plot").text()).toContain("§ 15 Abs. 2 ImmoWertV");
  });
});
