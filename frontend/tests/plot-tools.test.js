/**
 * The two tools on the plot page that act on their own: saving a self-measured
 * house type under a name, and the surroundings panel that no longer waits for
 * a click. Both are driven through the mounted view, with the backend mocked —
 * nothing here invents a number, the recorded Liebertwolkwitz answer does.
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { flushPromises } from "@vue/test-utils";
import { nextTick } from "vue";
import PlotView from "../src/views/PlotView.vue";
import { state, plotById } from "../src/lib/store.js";
import { realState, realPlot, mountWithRouter } from "./helpers.js";
import recorded from "./fixtures/nearby-liebertwolkwitz.json";

vi.mock("../src/lib/api.js", () => ({
  // The cap the module exports next to the call that sends it. A factory
  // that omits a named export makes every importer fail at *import* time,
  // which shows up as unrelated component errors.
  PAGE_LIMIT: 3000000,
  nearby: vi.fn(() => Promise.resolve(recorded)),
  reachability: vi.fn(() => Promise.reject(new Error("nicht Teil dieses Tests"))),
  // The location record on the same page; these tests are not about it.
  siteChecks: vi.fn(() => new Promise(() => {}))
}));
const { nearby } = await import("../src/lib/api.js");

beforeEach(() => {
  localStorage.clear();
  state.data = realState();
  // "none": mounting must not reach for a basemap.
  state.plan = { backdrop: "none", northUp: true, showDimensions: true, showSetbacks: true, measuring: false };
  nearby.mockClear();
  nearby.mockResolvedValue(recorded);
});

const clickText = (wrapper, label) =>
  wrapper.findAll("button").find(b => b.text().trim() === label).trigger("click");

/** The plot page with the custom-size fields open, which is where the button is. */
const withCustomSize = async ({ attach = false } = {}) => {
  const w = mountWithRouter(PlotView, { props: { id: "plot-concave" }, attach });
  await w.find("#house-type").setValue("custom");
  return w;
};

describe("Eigene Maße benennen", () => {
  it("legt beim Klick noch keinen Haustyp an, sondern fragt nach dem Namen", async () => {
    const w = await withCustomSize();
    const before = state.data.houseTypes.length;

    await clickText(w, "Als Haustyp in den Katalog");

    expect(state.data.houseTypes).toHaveLength(before);
    expect(plotById("plot-concave").houseTypeId).toBe("custom");
    expect(w.find("#house-type-name").exists()).toBe(true);
  });

  it("schlägt das Maß als Namen vor und setzt den Cursor hinein", async () => {
    // Attached: focus is a property of the document, not of the wrapper.
    const w = await withCustomSize({ attach: true });
    await w.find("#custom-length").setValue("13");
    await w.find("#custom-width").setValue("9");

    await clickText(w, "Als Haustyp in den Katalog");
    await nextTick();

    const field = w.find("#house-type-name");
    expect(field.element.value).toBe("13,0 × 9,0 m");
    expect(document.activeElement).toBe(field.element);
  });

  it("nimmt den getippten Namen und wählt den Typ gleich aus", async () => {
    const w = await withCustomSize();
    await w.find("#custom-length").setValue("13");
    await w.find("#custom-width").setValue("9");
    const before = state.data.houseTypes.length;

    await clickText(w, "Als Haustyp in den Katalog");
    await w.find("#house-type-name").setValue("Unser Haus");
    await clickText(w, "Speichern");

    expect(state.data.houseTypes).toHaveLength(before + 1);
    const saved = state.data.houseTypes.at(-1);
    expect(saved.name).toBe("Unser Haus");
    expect(saved.manufacturer).toBe("Eigene Maße");
    expect(saved.custom).toBe(true);
    expect(saved.builtArea).toBe(117);
    expect(saved.length).toBe(13);
    expect(saved.width).toBe(9);

    // The point of the whole step: the plot now carries it, and the select says so.
    expect(plotById("plot-concave").houseTypeId).toBe(saved.id);
    await nextTick();
    expect(w.find("#house-type").element.value).toBe(saved.id);
    expect(w.text()).toContain("Eigene Maße Unser Haus");
  });

  it("bestätigt mit der Eingabetaste", async () => {
    const w = await withCustomSize();
    const before = state.data.houseTypes.length;

    await clickText(w, "Als Haustyp in den Katalog");
    const field = w.find("#house-type-name");
    await field.setValue("Bungalow Nord");
    await field.trigger("keyup.enter");

    expect(state.data.houseTypes).toHaveLength(before + 1);
    expect(state.data.houseTypes.at(-1).name).toBe("Bungalow Nord");
    expect(w.find("#house-type-name").exists()).toBe(false);
  });

  it("legt beim Abbrechen nichts an", async () => {
    const w = await withCustomSize();
    const before = state.data.houseTypes.length;

    await clickText(w, "Als Haustyp in den Katalog");
    await w.find("#house-type-name").setValue("Doch nicht");
    await clickText(w, "Abbrechen");

    expect(state.data.houseTypes).toHaveLength(before);
    expect(plotById("plot-concave").houseTypeId).toBe("custom");
    expect(w.find("#house-type-name").exists()).toBe(false);
    // And the way back in is where it was.
    expect(w.findAll("button").some(b => b.text().trim() === "Als Haustyp in den Katalog")).toBe(true);
  });

  it("bricht mit Escape ab", async () => {
    const w = await withCustomSize();
    const before = state.data.houseTypes.length;

    await clickText(w, "Als Haustyp in den Katalog");
    await w.find("#house-type-name").trigger("keyup.esc");

    expect(state.data.houseTypes).toHaveLength(before);
    expect(w.find("#house-type-name").exists()).toBe(false);
  });

  it("fällt bei leerem Namen auf das Maß zurück, statt einen namenlosen Eintrag anzulegen", async () => {
    const w = await withCustomSize();
    await w.find("#custom-length").setValue("13");
    await w.find("#custom-width").setValue("9");

    await clickText(w, "Als Haustyp in den Katalog");
    await w.find("#house-type-name").setValue("   ");
    await clickText(w, "Speichern");

    expect(state.data.houseTypes.at(-1).name).toBe("13,0 × 9,0 m");
  });
});

describe("Umgebung auf der Grundstücksseite", () => {
  /* Every test gets its own plot id: the panel remembers per plot and session
     what it already asked for, and that memory is the feature under test. */
  const ownPlot = id => {
    const plot = { ...realPlot("convex"), id };
    state.data.plots = [plot];
    return plot;
  };

  it("füllt sich ohne Klick", async () => {
    ownPlot("plot-auto-1");
    const w = mountWithRouter(PlotView, { props: { id: "plot-auto-1" } });
    await flushPromises();

    expect(nearby).toHaveBeenCalledTimes(1);
    expect(w.text()).toContain("Liebertwolkwitzer Markt");
    expect(w.text()).not.toContain("Nachsehen");
  });

  it("fragt beim erneuten Zeichnen und beim erneuten Öffnen kein zweites Mal", async () => {
    ownPlot("plot-auto-2");
    const w = mountWithRouter(PlotView, { props: { id: "plot-auto-2" } });
    await flushPromises();
    expect(nearby).toHaveBeenCalledTimes(1);

    w.vm.$forceUpdate();
    await flushPromises();
    for (let i = 0; i < 5; i++) await nextTick();
    expect(nearby).toHaveBeenCalledTimes(1);

    // Dieselbe Seite noch einmal geöffnet — der Fahrplandienst hat die Antwort
    // schon gegeben, und eine zweite Runde kostet ihn eine Anfrage je Haltestelle.
    const again = mountWithRouter(PlotView, { props: { id: "plot-auto-2" } });
    await flushPromises();
    expect(nearby).toHaveBeenCalledTimes(1);
    expect(again.text()).toContain("Liebertwolkwitzer Markt");
  });

  it("zeigt einen fehlgeschlagenen Selbstlauf an, ohne ihn zu wiederholen", async () => {
    ownPlot("plot-auto-3");
    nearby.mockRejectedValue(new Error("Der Routendienst ist derzeit nicht erreichbar."));

    const w = mountWithRouter(PlotView, { props: { id: "plot-auto-3" } });
    await flushPromises();
    for (let i = 0; i < 10; i++) await nextTick();

    expect(nearby).toHaveBeenCalledTimes(1);
    expect(w.text()).toContain("Der Routendienst ist derzeit nicht erreichbar.");

    // Auch ein erneutes Öffnen versucht es nicht von allein wieder.
    mountWithRouter(PlotView, { props: { id: "plot-auto-3" } });
    await flushPromises();
    expect(nearby).toHaveBeenCalledTimes(1);

    // Von Hand geht es weiter — der Knopf bleibt der Weg zum zweiten Versuch.
    nearby.mockResolvedValue(recorded);
    await clickText(w, "Neu suchen");
    await flushPromises();
    expect(nearby).toHaveBeenCalledTimes(2);
    expect(w.text()).toContain("Liebertwolkwitzer Markt");
  });

  it("sucht ohne Koordinate gar nicht", async () => {
    const plot = ownPlot("plot-auto-4");
    delete plot.anchor;

    const w = mountWithRouter(PlotView, { props: { id: "plot-auto-4" } });
    await flushPromises();

    expect(nearby).not.toHaveBeenCalled();
    expect(w.text()).toContain("Ohne Koordinate gibt es keinen Punkt");
  });
});
