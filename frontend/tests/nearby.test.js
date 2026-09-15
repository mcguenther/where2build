/**
 * The "In der Umgebung" panel, against a recorded real answer.
 *
 * Liebertwolkwitz, fetched live on 2026-08-31 with the OSM index absent — which
 * is the state a fresh checkout is in, and the one that most easily produces a
 * lie: six categories the server has no data for must never read as "there is
 * no school near this plot".
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import NearbyPanel from "../src/components/NearbyPanel.vue";
import { realPlot } from "./helpers.js";
import recorded from "./fixtures/nearby-liebertwolkwitz.json";
/* The real `/api/reachability` answer for those same six places, asked from
 * this plot's own anchor on 06.09.2026 with `modes: ["bike", "car"]`. The
 * `geometry` of each row is dropped — the panel shows minutes, and the
 * polylines were 213 kB of fixture nobody reads. */
import routed from "./fixtures/reachability-umgebung-liebertwolkwitz.json";

vi.mock("../src/lib/api.js", () => ({
  // The cap the module exports next to the call that sends it. A factory
  // that omits a named export makes every importer fail at *import* time,
  // which shows up as unrelated component errors.
  PAGE_LIMIT: 3000000,
  nearby: vi.fn(() => Promise.resolve(recorded)),
  reachability: vi.fn(() => Promise.resolve(routed))
}));
const { nearby, reachability } = await import("../src/lib/api.js");

const plot = () => realPlot("convex");

beforeEach(() => {
  nearby.mockClear();
  reachability.mockClear();
  reachability.mockResolvedValue(routed);
});

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

  it("fragt die Linien mit ab", async () => {
    // Ohne dieses Flag antwortet der Dienst mit `linien: null` — und die Tafel
    // wüsste dann nur, dass hier „ein Bus“ hält, nicht welcher.
    const w = mount(NearbyPanel, { props: { plot: plot() } });
    await w.find("button").trigger("click");
    await flushPromises();
    expect(nearby).toHaveBeenCalledWith(expect.anything(), { linien: true });
  });

  it("nennt die Linien, die an einer Haltestelle halten", async () => {
    const w = mount(NearbyPanel, { props: { plot: plot() } });
    await w.find("button").trigger("click");
    await flushPromises();

    // Aufgezeichnete Werte: am Liebertwolkwitzer Markt hält die 143, am
    // Bahnhof der RB113 nach Geithain.
    const chips = w.findAll(".nearby__line").map(el => el.text());
    recorded.treffer
      .flatMap(hit => hit.linien ?? [])
      .forEach(line => expect(chips).toContain(line));
    expect(chips).toContain("143");
    expect(chips).toContain("RB113");
  });

  it("sagt „nicht abgefragt“, statt eine Haltestelle ohne Linie dastehen zu lassen", async () => {
    // Der Dienst hört nach einer festen Zahl von Haltestellen auf, Linien
    // nachzuschlagen. Das ist nicht dasselbe wie „hier hält keine Linie“.
    const capped = structuredClone(recorded);
    capped.treffer = capped.treffer.map((hit, i) => (i ? { ...hit, linien: null } : hit));
    nearby.mockResolvedValueOnce(capped);

    const w = mount(NearbyPanel, { props: { plot: plot() } });
    await w.find("button").trigger("click");
    await flushPromises();

    // Nach Fußweg sortiert, also über den Namen gesucht statt über die Reihe.
    const rowFor = name => w.findAll("tbody tr").find(r => r.text().includes(name));
    const withLines = rowFor(capped.treffer[0].name);
    const capped1 = capped.treffer.find((hit, i) => i && hit.name !== capped.treffer[0].name);

    expect(withLines.findAll(".nearby__line").length).toBeGreaterThan(0);
    expect(rowFor(capped1.name).text()).toContain("Linien nicht abgefragt");
    expect(rowFor(capped1.name).findAll(".nearby__line")).toHaveLength(0);
  });

  it("sortiert die Zeilen nach Fußweg, nicht nach Kategorie", async () => {
    // Der Dienst ordnet innerhalb einer Kategorie; über die Kategorien hinweg
    // stand vorher die Reihenfolge der Kategorienliste — ein Supermarkt vier
    // Minuten entfernt landete unter einer Schule zwanzig Minuten entfernt.
    const w = mount(NearbyPanel, { props: { plot: plot() } });
    await w.find("button").trigger("click");
    await flushPromises();

    const byName = Object.fromEntries(recorded.treffer.map(t => [t.name, t]));
    const shown = w.findAll("tbody tr")
      .map(row => Object.keys(byName).find(name => row.text().includes(name)))
      .filter(Boolean)
      .map(name => byName[name].duration_s ?? Infinity);

    expect(shown.length).toBeGreaterThan(1);
    expect([...shown].sort((a, b) => a - b)).toEqual(shown);
  });

  it("stellt neben den Fußweg die Zeit mit Rad und Auto", async () => {
    const w = mount(NearbyPanel, { props: { plot: plot() } });
    await w.find("button").trigger("click");
    await flushPromises();
    await flushPromises();

    // Eine zweite Anfrage, für genau die Orte, die die erste gefunden hat.
    expect(reachability).toHaveBeenCalledTimes(1);
    expect(reachability.mock.calls[0][2]).toEqual(["bike", "car"]);
    expect(reachability.mock.calls[0][1]).toHaveLength(recorded.treffer.length);

    const head = w.findAll("thead th").map(th => th.text());
    expect(head).toEqual(["Ziel", "zu Fuß", "Rad", "Auto", "Strecke"]);

    // Aufgezeichnete Werte: Meusdorf ist 1326 s mit dem Rad und 422 s mit dem Auto.
    const row = w.findAll("tbody tr").find(r => r.text().includes("Leipzig, Meusdorf"));
    const cells = row.findAll("td").map(td => td.text());
    expect(cells[2]).toBe("22 min");
    expect(cells[3]).toBe("7 min");
    expect(w.findAll(".skeleton-cell")).toHaveLength(0);
  });

  it("zeigt in den beiden Spalten Platzhalter, solange gerechnet wird", async () => {
    let answer;
    reachability.mockReturnValueOnce(new Promise(done => { answer = done; }));
    const w = mount(NearbyPanel, { props: { plot: plot() } });
    await w.find("button").trigger("click");
    await flushPromises();

    // Zwei Zellen je Zeile, und nichts, was wie ein Ergebnis aussieht.
    expect(w.findAll(".skeleton-cell")).toHaveLength(recorded.treffer.length * 2);
    answer(routed);
    await flushPromises();
    expect(w.findAll(".skeleton-cell")).toHaveLength(0);
  });

  it("lässt die Fußwege stehen, wenn Rad und Auto nicht zu berechnen sind", async () => {
    // Der Ausweg, den der Nutzer verlangt hat: eine gescheiterte Routenberechnung
    // darf die gemessenen Fußwege und Strecken nicht mitnehmen.
    reachability.mockRejectedValueOnce(new Error("Der Routing-Dienst ist nicht erreichbar."));
    const w = mount(NearbyPanel, { props: { plot: plot() } });
    await w.find("button").trigger("click");
    await flushPromises();
    await flushPromises();

    expect(w.findAll("tbody tr")).toHaveLength(recorded.treffer.length);
    expect(w.text()).toContain("Fußweg");
    expect(w.text()).toContain("Der Routing-Dienst ist nicht erreichbar.");
    const row = w.findAll("tbody tr").find(r => r.text().includes("Leipzig, Meusdorf"));
    expect(row.findAll("td")[2].text()).toBe("—");
    expect(row.findAll("td")[2].attributes("title")).toContain("nicht erreichbar");
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
    links.forEach(a => {
      const href = a.attributes("href");
      // Die Zeilen stehen nach Fußweg sortiert, also wird der Treffer über
      // seinen Namen gesucht statt über die Position.
      const i = recorded.treffer.findIndex(t => t.name === a.text());
      expect(i).toBeGreaterThanOrEqual(0);
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
