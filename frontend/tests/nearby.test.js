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

  it("übernimmt die Begründung des Dienstes, statt eine eigene zu behaupten", async () => {
    // The panel used to print a fixed "kein Datenbestand" sentence for every
    // unavailable category. With a rate limit or a runtime error that sentence
    // is simply false — the service knows which of the two happened.
    const refused = structuredClone(recorded);
    refused.kategorien = refused.kategorien.map(c => c.kategorie === "schule"
      ? { ...c, verfuegbar: false, anzahl: 0,
          hinweis: "Die Umgebungssuche wurde wegen zu vieler Zugriffe abgewiesen (HTTP 429)." }
      : c);
    nearby.mockResolvedValueOnce(refused);

    const w = mount(NearbyPanel, { props: { plot: plot() } });
    await w.find("button").trigger("click");
    await flushPromises();

    expect(w.text()).toContain("wegen zu vieler Zugriffe abgewiesen");
    expect(w.text()).toContain("Schule");
  });

  it("fasst Kategorien mit derselben Begründung zu einer Zeile zusammen", async () => {
    const w = mount(NearbyPanel, { props: { plot: plot() } });
    await w.find("button").trigger("click");
    await flushPromises();

    // Six categories share one reason in the recording; one line, not six.
    const lines = w.findAll(".nearby__hint").map(p => p.text());
    const noData = lines.filter(t => t.includes("kein Datenbestand"));
    expect(noData).toHaveLength(1);
    ["Schule", "Kita", "Park", "Spielplatz", "Supermarkt", "Arzt"]
      .forEach(name => expect(noData[0]).toContain(name));
  });

  it("zeigt bei einem Halt, welche Verkehrsmittel dort fahren", async () => {
    const w = mount(NearbyPanel, { props: { plot: plot() } });
    await w.find("button").trigger("click");
    await flushPromises();
    // A stop merged across categories would otherwise lose its "also S-Bahn".
    const withKind = recorded.treffer.filter(t => t.art && t.art !== "Bus");
    if (withKind.length) expect(w.text()).toContain(withKind[0].art);
  });

  it("trennt „kein Datenbestand“ von „nichts gefunden“", async () => {
    const w = mount(NearbyPanel, { props: { plot: plot() } });
    await w.find("button").trigger("click");
    await flushPromises();
    const text = w.text();

    // Six categories have no index on this server; one was searched and empty.
    // The wording is the service's own, so assert on what it actually said.
    const noData = recorded.kategorien.find(c => c.verfuegbar === false).hinweis;
    expect(text).toContain(noData);
    expect(text).toContain("Schule");
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

describe("Nachprüfbarkeit der Umgebung", () => {
  it("verlinkt jeden gefundenen Ort als Fußweg vom Grundstück aus", async () => {
    const site = plot();
    const w = mount(NearbyPanel, { props: { plot: site } });
    await w.find("button").trigger("click");
    await flushPromises();

    const links = w.findAll("a.nearby__name");
    expect(links.length).toBe(recorded.treffer.length);
    links.forEach((a, i) => {
      const href = a.attributes("href");
      // A marker on the destination answers "where is it", but the row claims a
      // walking distance -- and that claim is only checkable as a route.
      expect(href).toContain("openstreetmap.org/directions");
      expect(href).toContain("fossgis_osrm_foot");
      // Both ends, in order: from this plot, to the place that was found.
      expect(href).toContain(`route=${site.anchor.lat.toFixed(6)},${site.anchor.lon.toFixed(6)}`);
      expect(href).toContain(`%3B${recorded.treffer[i].lat.toFixed(6)},${recorded.treffer[i].lon.toFixed(6)}`);
      expect(href.indexOf(site.anchor.lat.toFixed(6)))
        .toBeLessThan(href.indexOf(recorded.treffer[i].lat.toFixed(6)));
      expect(a.attributes("rel")).toContain("noopener");
    });
  });
});
