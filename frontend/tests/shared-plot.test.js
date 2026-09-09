/**
 * A plot somebody shared, seen by whoever opens the link.
 *
 * Two properties matter more than the layout. The page must not write the
 * document into this browser's store — it is somebody else's plot, and putting
 * it into the reader's own list would be worse than showing nothing. And it
 * must ask no service anything: a link that gets passed around would otherwise
 * spend the request budget of whoever is behind the proxy, on the cadastre, for
 * every reader.
 *
 * The slug is checked too, because the whole point of cutting the route that
 * way is that links already sent keep working when a readable part is added.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { flushPromises } from "@vue/test-utils";
import SharedPlotView from "../src/views/SharedPlotView.vue";
import { state } from "../src/lib/store.js";
import { realPlot, realState, mountWithRouter, testRouter } from "./helpers.js";

const SHARED = () => {
  const plot = realPlot("convex");
  return {
    dokument: {
      ...plot,
      officialArea: 502,
      askingPrice: 60000,
      bodenrichtwert: 100,
      placedBuilding: { width: 11.4, depth: 8.5, cx: 0, cy: 0, rotation: 0 },
      houseTypeName: "ELK All in One 159"
    },
    angelegt: "2026-09-01T10:00:00Z",
    laeuft_ab: "2026-11-30T10:00:00Z"
  };
};

const ok = body => ({ ok: true, status: 200, json: () => Promise.resolve(body) });

beforeEach(() => {
  localStorage.clear();
  state.data = realState();
  // "none" would be truer to a card, but this view asks for a map: the backdrop
  // must not start a MapLibre instance in jsdom.
  state.plan = { backdrop: "none", northUp: true, showDimensions: true, showSetbacks: true, measuring: false };
  globalThis.fetch = vi.fn(() => Promise.resolve(ok(SHARED())));
});

afterEach(() => { vi.restoreAllMocks(); });

async function open(path = "/geteilt/AbCdEf123456789012") {
  const router = testRouter(path);
  await router.isReady();
  const view = mountWithRouter(SharedPlotView, { router, props: router.currentRoute.value.params });
  await flushPromises();
  return view;
}

describe("Geteiltes Grundstück", () => {
  it("zeigt das Grundstück aus der Momentaufnahme", async () => {
    const view = await open();

    const text = view.text();
    expect(text).toContain("502 m²");
    expect(text).toContain("ELK All in One 159");
    // Und sagt, dass es eine Momentaufnahme ist, samt Ablauf.
    expect(text).toContain("Momentaufnahme");
    expect(text).toContain("30.11.2026");
  });

  it("schreibt nichts in den Stand dieses Browsers", async () => {
    // Ein fremdes Grundstück in der eigenen Liste wäre schlimmer als nichts.
    const before = state.data.plots.length;
    await open();

    expect(state.data.plots.length).toBe(before);
    expect(state.data.plots.some(p => p.officialArea === 502)).toBe(false);
  });

  it("fragt genau einen Dienst, nämlich die Freigabe selbst", async () => {
    // Ein Link, der herumgereicht wird, darf nicht für jeden Leser das
    // Abrufkontingent beim Kataster verbrauchen.
    await open();

    const calls = globalThis.fetch.mock.calls.map(([path]) => String(path));
    expect(calls).toHaveLength(1);
    expect(calls[0]).toContain("/shares/AbCdEf123456789012");
  });

  it("liest denselben Link mit lesbarem Zusatz", async () => {
    // Der Zusatz ist Beiwerk; der Schlüssel ist die ganze Adresse. Sonst
    // brechen später alle schon verschickten Links.
    await open("/geteilt/AbCdEf123456789012/wiesenstrasse-grossbothen");

    const calls = globalThis.fetch.mock.calls.map(([path]) => String(path));
    expect(calls[0]).toContain("/shares/AbCdEf123456789012");
    expect(calls[0]).not.toContain("wiesenstrasse");
  });

  it("sagt es, wenn der Link abgelaufen oder zurückgezogen ist", async () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({ ok: false, status: 404, json: () => Promise.resolve({ detail: "Diesen geteilten Link gibt es nicht mehr." }) })
    );
    const view = await open();

    expect(view.text()).toContain("nicht mehr");
    // Und bietet den Weg in die eigene Prüfung an, statt eine Sackgasse zu sein.
    expect(view.find("a.btn").exists()).toBe(true);
  });

  it("lässt einen nicht geteilten Preis ganz weg, statt Striche zu zeigen", async () => {
    // Ein Strich liest sich wie fehlende Daten, nicht wie eine Entscheidung —
    // und lädt dazu ein, den Rest der Seite auch anzuzweifeln.
    const without = SHARED();
    delete without.dokument.askingPrice;
    globalThis.fetch = vi.fn(() => Promise.resolve(ok(without)));
    const view = await open();

    const terms = view.findAll(".value-list dt").map(dt => dt.text());
    expect(terms).not.toContain("Kaufpreis");
    expect(terms).not.toContain("Preis je m²");
    expect(terms).not.toContain("Gegen den Richtwert");
    // Der Bodenrichtwert bleibt: er ist ein amtlicher Wert des Ortes.
    expect(terms).toContain("Bodenrichtwert");
  });

  it("zeigt kein leeres Hausfeld, wenn das Haus nicht geteilt wurde", async () => {
    const bare = SHARED();
    delete bare.dokument.placedBuilding;
    delete bare.dokument.houseTypeName;
    globalThis.fetch = vi.fn(() => Promise.resolve(ok(bare)));
    const view = await open();

    expect(view.text()).not.toContain("Was daraufpasst");
  });

  it("zeigt Wege nur mit ihren Namen und nach Dauer geordnet", async () => {
    const withWays = SHARED();
    withWays.dokument.routes = {
      "zl-schule": { modes: { transit: { erreichbar: true, duration_s: 1800 } } },
      "zl-arbeit": { modes: { transit: { erreichbar: true, duration_s: 600 },
                              bike: { erreichbar: true, duration_s: 900 } } }
    };
    withWays.dokument.sharedDestinations = [
      { id: "zl-arbeit", name: "Arbeit" }, { id: "zl-schule", name: "Schule" }
    ];
    globalThis.fetch = vi.fn(() => Promise.resolve(ok(withWays)));
    const view = await open();

    const rows = view.findAll(".value-list dt").map(dt => dt.text());
    // Das schnellere Ziel zuerst, und beide mit Namen statt mit ihrer Kennung.
    expect(rows.indexOf("Arbeit")).toBeLessThan(rows.indexOf("Schule"));
    expect(view.text()).not.toContain("zl-arbeit");
  });

  it("zeigt gar keinen Wege-Abschnitt, wenn nichts geteilt wurde", async () => {
    const view = await open();

    expect(view.text()).not.toContain("Fahrplan");
  });

  it("zeigt die Notiz nur, wenn sie mitgeschickt wurde", async () => {
    const view = await open();
    expect(view.text()).not.toContain("Notiz");

    const withNote = SHARED();
    withNote.dokument.note = "Verkäufer wirkt in Eile";
    globalThis.fetch = vi.fn(() => Promise.resolve(ok(withNote)));
    const shown = await open();

    expect(shown.text()).toContain("Verkäufer wirkt in Eile");
  });
});
