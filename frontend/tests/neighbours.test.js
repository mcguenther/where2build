/**
 * The neighbour hint in the plot view.
 *
 * Against `fixtures/neighbours-moelkau.json` — what `/api/neighbours` really
 * answered for Mölkau, Flurstück 204: 59 building outlines from OpenStreetMap,
 * two of them closer to this plot's boundary than the 3 m § 6 SächsBO asks of
 * them. The marking is a hint, not a finding, and the wording has to say so.
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { nextTick } from "vue";

vi.mock("../src/lib/api.js", () => ({
  // The cap the module exports next to the call that sends it. A factory
  // that omits a named export makes every importer fail at *import* time,
  // which shows up as unrelated component errors.
  PAGE_LIMIT: 3000000,
  neighbourBuildings: vi.fn(),
  reachability: vi.fn()
}));

import SitePlan from "../src/components/SitePlan.vue";
import PlotView from "../src/views/PlotView.vue";
import { state, plotById, save } from "../src/lib/store.js";
import { realState, realPlot, mountWithRouter } from "./helpers.js";
import answer from "./fixtures/neighbours-moelkau.json";
import fromCadastre from "./fixtures/neighbours-moelkau-alkis.json";

const { neighbourBuildings } = await import("../src/lib/api.js");

const ID = "plot-moelkau";
const plot = () => plotById(ID);

beforeEach(() => {
  localStorage.clear();
  state.data = realState();
  state.data.plots.push(realPlot("moelkau"));
  state.plan = { backdrop: "none", northUp: true, showDimensions: true, showSetbacks: true, measuring: false };
  neighbourBuildings.mockReset();
  neighbourBuildings.mockResolvedValue(answer);
});

const turnOn = async w => {
  await w.findAll("button").find(b => b.text() === "Nachbarn").trigger("click");
  await nextTick();
  await nextTick();
  return w;
};

describe("Nachbargebäude als Hinweis", () => {
  it("ist aus, bis danach gefragt wird", () => {
    const w = mountWithRouter(PlotView, { props: { id: ID } });

    expect(w.findAll("button").find(b => b.text() === "Nachbarn").attributes("aria-pressed"))
      .toBe("false");
    expect(neighbourBuildings).not.toHaveBeenCalled();
    expect(w.findComponent(SitePlan).props("neighbourDepths")).toBeNull();
  });

  it("holt die Umrisse einmal und vertieft die betroffenen Grenzabschnitte", async () => {
    const w = await turnOn(mountWithRouter(PlotView, { props: { id: ID } }));

    expect(neighbourBuildings).toHaveBeenCalledTimes(1);
    expect(neighbourBuildings).toHaveBeenCalledWith(plot().anchor.lat, plot().anchor.lon);

    const depths = w.findComponent(SitePlan).props("neighbourDepths");
    expect(depths).toHaveLength(plot().polygon.length);
    expect(depths.filter((d, i) => d > plot().setbacks[i] + 1e-9)).toHaveLength(2);
  });

  it("sagt dazu, dass es ein Hinweis ist und keine Prüfung", async () => {
    const w = await turnOn(mountWithRouter(PlotView, { props: { id: ID } }));

    const text = w.text();
    expect(text).toContain("Abstandsfläche des Nachbargebäudes");
    expect(text).toContain("Bauaufsicht");
    expect(text).toContain("OpenStreetMap");
    // The premise the statute does not carry must not be stated as one.
    expect(text).not.toContain("müssen Sie");
    expect(text).toContain("§ 6 SächsBO verlangt das nicht von uns");
  });

  it("nennt das Kataster, wenn die Umrisse von dort kommen", async () => {
    // Dieselbe Stelle, amtlich beantwortet: 71 Umrisse aus ave:GebaeudeBauwerk,
    // ohne dass irgendetwas eingerichtet werden musste.
    neighbourBuildings.mockResolvedValue(fromCadastre);

    const w = await turnOn(mountWithRouter(PlotView, { props: { id: ID } }));

    const text = w.text();
    expect(text).toContain("Liegenschaftskataster");
    expect(text).not.toContain("OpenStreetMap");
    expect(text).toContain("§ 6 SächsBO verlangt das nicht von uns");
  });

  it("bleibt eingeschaltet und holt die Umrisse beim nächsten Aufruf erneut", async () => {
    await turnOn(mountWithRouter(PlotView, { props: { id: ID } }));
    expect(plot().showNeighbours).toBe(true);
    save();

    const again = mountWithRouter(PlotView, { props: { id: ID } });
    await nextTick();
    await nextTick();

    expect(neighbourBuildings).toHaveBeenCalledTimes(2);
    expect(again.findComponent(SitePlan).props("neighbourDepths")).not.toBeNull();
  });

  it("zeigt den deutschen Grund, wenn der Dienst nicht antwortet", async () => {
    neighbourBuildings.mockRejectedValue(
      new Error("Für die Nachbargebäude ist keine OpenStreetMap-Quelle eingerichtet.")
    );

    const w = await turnOn(mountWithRouter(PlotView, { props: { id: ID } }));

    expect(w.text()).toContain("keine OpenStreetMap-Quelle eingerichtet");
    expect(w.findComponent(SitePlan).props("neighbourDepths")).toBeNull();
  });

  it("behauptet nichts, wenn in OpenStreetMap kein Gebäude erfasst ist", async () => {
    neighbourBuildings.mockResolvedValue({ ...answer, gebaeude: [] });

    const w = await turnOn(mountWithRouter(PlotView, { props: { id: ID } }));

    expect(w.text()).toContain("kein Gebäude erfasst");
    expect(w.findComponent(SitePlan).props("neighbourDepths")).toBeNull();
  });

  it("bleibt ohne Koordinate unbedienbar, statt ins Leere zu fragen", () => {
    const withoutAnchor = { ...realPlot("moelkau"), id: "plot-ohne-anker", anchor: null };
    state.data.plots.push(withoutAnchor);

    const w = mountWithRouter(PlotView, { props: { id: "plot-ohne-anker" } });

    expect(w.findAll("button").find(b => b.text() === "Nachbarn").attributes("disabled"))
      .toBeDefined();
  });
});
