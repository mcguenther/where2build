/**
 * The "In der Umgebung" panel, against a recorded real answer.
 *
 * Liebertwolkwitz, fetched live on 2026-08-29 with the OSM index absent — which
 * is the state a fresh checkout is in, and the one that most easily produces a
 * lie: six categories the server has no data for must never read as "there is
 * no school near this plot".
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import NearbyPanel from "../src/components/NearbyPanel.vue";
import { realPlot } from "./helpers.js";
import recorded from "./fixtures/nearby-liebertwolkwitz.json";

vi.mock("../src/lib/api.js", () => ({
  nearby: vi.fn(() => Promise.resolve(recorded))
}));
const { nearby } = await import("../src/lib/api.js");

const plot = () => realPlot("convex");

beforeEach(() => { nearby.mockClear(); });

describe("Umgebung", () => {
  it("fragt nichts ab, bevor jemand danach fragt", () => {
    const w = mount(NearbyPanel, { props: { plot: plot() } });
    expect(nearby).not.toHaveBeenCalled();
    expect(w.text()).toContain("Fußweg, nicht als Luftlinie");
  });

  it("verlangt eine Koordinate", () => {
    const ohneAnker = { ...plot() };
    delete ohneAnker.anchor;
    const w = mount(NearbyPanel, { props: { plot: ohneAnker } });
    expect(w.text()).toContain("Ohne Koordinate");
    expect(w.find("button").attributes("disabled")).toBeDefined();
  });

  it("zeigt die gefundenen Orte mit Gehzeit und Fußweglänge", async () => {
    const w = mount(NearbyPanel, { props: { plot: plot() } });
    await w.find("button").trigger("click");
    await flushPromises();

    // Recorded values, not chosen ones: the bus stop at the market is 68 s away.
    expect(w.text()).toContain("Liebertwolkwitzer Markt");
    expect(w.text()).toContain("Bus");
    expect(w.text()).toContain("Fußweg");
    expect(w.findAll("tbody tr")).toHaveLength(recorded.treffer.length);
  });

  it("trennt „kein Datenbestand“ von „nichts gefunden“", async () => {
    const w = mount(NearbyPanel, { props: { plot: plot() } });
    await w.find("button").trigger("click");
    await flushPromises();
    const text = w.text();

    // Six categories have no index on this server; one was searched and empty.
    expect(text).toContain("Kein Datenbestand für");
    expect(text).toContain("Schule");
    expect(text).toContain("Das heißt nicht, dass es dort nichts gibt");
    expect(text).toContain("Nichts gefunden für");
    expect(text).toContain("S-Bahn");
  });

  it("nennt die Quelle der Angaben", async () => {
    const w = mount(NearbyPanel, { props: { plot: plot() } });
    await w.find("button").trigger("click");
    await flushPromises();
    expect(w.text()).toContain("OpenStreetMap");
    expect(w.text()).toContain("MOTIS");
  });

  it("zeigt die Fehlermeldung des Dienstes, nicht eine eigene", async () => {
    nearby.mockRejectedValueOnce(new Error("Der Routendienst ist derzeit nicht erreichbar."));
    const w = mount(NearbyPanel, { props: { plot: plot() } });
    await w.find("button").trigger("click");
    await flushPromises();
    expect(w.text()).toContain("Der Routendienst ist derzeit nicht erreichbar.");
    expect(w.findAll("tbody tr")).toHaveLength(0);
  });

  it("vergisst das Ergebnis beim Wechsel des Grundstücks", async () => {
    const w = mount(NearbyPanel, { props: { plot: plot() } });
    await w.find("button").trigger("click");
    await flushPromises();
    expect(w.findAll("tbody tr").length).toBeGreaterThan(0);

    await w.setProps({ plot: realPlot("concave") });
    expect(w.findAll("tbody tr")).toHaveLength(0);
  });
});
