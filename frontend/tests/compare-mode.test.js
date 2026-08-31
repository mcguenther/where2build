/**
 * Comparing is the rare errand, opening a plot the common one. These tests pin
 * that down: the overview offers no checkboxes until "Vergleichen" is pressed,
 * and the selection it collects belongs to the stored document, not to the
 * button — leaving the mode hides the ticks, it does not undo them.
 */
import { describe, it, expect, beforeEach } from "vitest";
import { flushPromises } from "@vue/test-utils";
import { state } from "../src/lib/store.js";
import PlotsView from "../src/views/PlotsView.vue";
import { realState, mountWithRouter, testRouter } from "./helpers.js";

beforeEach(() => {
  localStorage.clear();
  state.data = realState();
  state.data.selection = [];
  // "none": a backdrop is a MapLibre instance, and the card thumbnails must not
  // each start one — nor reach for the network from jsdom.
  state.plan = { backdrop: "none", northUp: true, showDimensions: true, showSetbacks: true, measuring: false };
});

const compareToggle = view => view.find(".compare-toggle");
const checkboxes = view => view.findAll(".plot-card__select input");

describe("Vergleichsmodus", () => {
  it("zeigt ohne ihn weder Haken noch Auswahl-Leiste", () => {
    const w = mountWithRouter(PlotsView);
    expect(checkboxes(w)).toHaveLength(0);
    expect(w.find(".selection-bar").exists()).toBe(false);
    expect(w.text()).not.toContain("ausgewählt");
    expect(compareToggle(w).attributes("aria-pressed")).toBe("false");
  });

  it("holt sie mit „Vergleichen“ hervor und räumt sie wieder weg", async () => {
    const w = mountWithRouter(PlotsView);

    await compareToggle(w).trigger("click");
    expect(checkboxes(w)).toHaveLength(state.data.plots.length);
    expect(w.find(".selection-bar").exists()).toBe(true);
    expect(compareToggle(w).attributes("aria-pressed")).toBe("true");

    await compareToggle(w).trigger("click");
    expect(checkboxes(w)).toHaveLength(0);
    expect(w.find(".selection-bar").exists()).toBe(false);
    expect(compareToggle(w).attributes("aria-pressed")).toBe("false");
  });

  it("öffnet den Lageplan, wenn eine Karte im Normalmodus angeklickt wird", async () => {
    const router = testRouter("/");
    await router.isReady();
    const w = mountWithRouter(PlotsView, { router });

    await w.find(".plot-card__plan").trigger("click");
    // `push` is not awaited by the handler; the navigation settles a tick later.
    await flushPromises();

    expect(router.currentRoute.value.name).toBe("plot");
    expect(router.currentRoute.value.params.id).toBe("plot-convex");
  });

  it("schreibt einen gesetzten Haken in die Auswahl des Dokuments", async () => {
    const w = mountWithRouter(PlotsView);
    await compareToggle(w).trigger("click");

    await checkboxes(w)[1].setValue(true);
    expect(state.data.selection).toEqual(["plot-concave"]);

    await checkboxes(w)[1].setValue(false);
    expect(state.data.selection).toEqual([]);
  });

  it("sagt beim Einschalten, was als Nächstes zu tun ist", async () => {
    const w = mountWithRouter(PlotsView);
    await compareToggle(w).trigger("click");

    const bar = w.find(".selection-bar");
    expect(bar.text()).toContain("Nichts ausgewählt");
    expect(bar.find("[aria-live]").exists()).toBe(true);
    // Nothing selected is not a dead end, but it is not a comparison either.
    const open = bar.findAll("button").find(b => b.text() === "Vergleich öffnen");
    expect(open.attributes("disabled")).toBeDefined();
  });

  it("behält die Auswahl, wenn der Modus verlassen wird", async () => {
    const w = mountWithRouter(PlotsView);
    await compareToggle(w).trigger("click");
    await checkboxes(w)[0].setValue(true);
    await checkboxes(w)[1].setValue(true);

    await compareToggle(w).trigger("click");   // "Fertig" does the same
    expect(w.find(".selection-bar").exists()).toBe(false);
    expect(state.data.selection).toEqual(["plot-convex", "plot-concave"]);

    await compareToggle(w).trigger("click");
    expect(checkboxes(w).every(box => box.element.checked)).toBe(true);
  });

  it("zeigt eine gespeicherte Auswahl, sobald der Modus angeschaltet ist", () => {
    // The way back from /vergleich: the ticks are still there, they are just
    // not shown until asked for.
    state.data.selection = ["plot-convex", "plot-concave"];
    const w = mountWithRouter(PlotsView);

    return compareToggle(w).trigger("click").then(() => {
      expect(w.find(".selection-bar").text()).toContain("2 Grundstücke ausgewählt");
      expect(checkboxes(w)).toHaveLength(2);
      expect(checkboxes(w).every(c => c.element.checked)).toBe(true);
    });
  });

  it("bietet den Vergleich gar nicht an, solange die Liste leer ist", () => {
    state.data.plots = [];
    const w = mountWithRouter(PlotsView);
    expect(compareToggle(w).exists()).toBe(false);
    expect(w.find(".selection-bar").exists()).toBe(false);
  });
});

describe("Was den Modus nicht anschaltet", () => {
  /* `addPlot` adds every new plot to the selection, so "es ist etwas
     ausgewählt" is true for anyone who has ever added one — starting the mode
     on that would mean it never appears to be off. */
  it("bleibt aus, obwohl die Auswahl des Dokuments gefüllt ist", () => {
    // What `addPlot` leaves behind after two plots have been added.
    state.data.selection = ["plot-convex", "plot-concave"];
    const w = mountWithRouter(PlotsView);
    expect(w.findAll("input[type=checkbox]")).toHaveLength(0);
    expect(w.find(".selection-bar").exists()).toBe(false);
  });
});
