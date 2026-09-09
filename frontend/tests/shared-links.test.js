/**
 * The links already handed out for one plot, and the way back out of them.
 *
 * The property worth a test file: a shared link is public for ninety days, so
 * being unable to *see* one is the part that hurts. Without this section the
 * only way to undo a slip was to wait it out.
 *
 * And the section has to be absent when there is nothing — a panel that is
 * always there and usually empty is furniture, and this one sits at the foot
 * of a page that is already long.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { flushPromises } from "@vue/test-utils";
import SharedLinks from "../src/components/SharedLinks.vue";
import { state } from "../src/lib/store.js";
import { realPlot, realState, mountWithRouter } from "./helpers.js";

const ok = body => ({ ok: true, status: 200, json: () => Promise.resolve(body) });

const ENTRY = {
  id: "AbCdEf123456789012",
  angelegt: "2026-09-09T10:00:00Z",
  laeuft_ab: "2026-12-08T10:00:00Z",
  name: "Wiesenstraße",
  grundstueck: "plot-convex",
  umfang: { preis: true, haus: false, wege: false, notiz: false }
};

let plot;

beforeEach(() => {
  localStorage.clear();
  state.data = realState();
  state.account = { eingerichtet: true, angemeldet: true, name: "Erika", kennung: "abc" };
  plot = realPlot("convex");
  globalThis.fetch = vi.fn(() => Promise.resolve(ok({ eintraege: [ENTRY] })));
});

afterEach(() => { vi.restoreAllMocks(); });

async function open() {
  const view = mountWithRouter(SharedLinks, { path: "/grundstueck/plot-convex", props: { plot } });
  await flushPromises();
  return view;
}

describe("Vergebene Links", () => {
  it("zeigt einen Link mit Datum, Ablauf und Umfang", async () => {
    const view = await open();

    const text = view.text();
    expect(text).toContain("Vergebene Links");
    expect(text).toContain("09.09.2026");
    expect(text).toContain("08.12.2026");
    expect(text).toContain("Kaufpreis");
    view.unmount();
  });

  it("zieht einen Link zurück und nimmt ihn aus der Liste", async () => {
    const view = await open();
    globalThis.fetch = vi.fn(() => Promise.resolve({ ok: true, status: 204, json: () => Promise.resolve({}) }));

    await view.findAll("button").find(b => b.text().includes("Zurückziehen")).trigger("click");
    await flushPromises();

    const [path, options] = globalThis.fetch.mock.calls[0];
    expect(String(path)).toContain("/shares/AbCdEf123456789012");
    expect(options.method).toBe("DELETE");
    // Und die Sektion verschwindet wieder, weil nichts mehr offen ist.
    expect(view.text()).not.toContain("Vergebene Links");
    view.unmount();
  });

  it("zeigt nur die Links dieses Grundstücks", async () => {
    // Die Antwort trägt alle Freigaben des Kontos; auf einer Grundstücksseite
    // wären fremde Links Rauschen — und verwirrend obendrein.
    globalThis.fetch = vi.fn(() =>
      Promise.resolve(ok({ eintraege: [{ ...ENTRY, id: "Fremd1234567890abcd", grundstueck: "plot-concave" }] }))
    );
    const view = await open();

    expect(view.text()).not.toContain("Vergebene Links");
    view.unmount();
  });

  it("fragt abgemeldet gar nicht erst", async () => {
    state.account = { eingerichtet: true, angemeldet: false, name: null, kennung: null };
    const view = await open();

    expect(globalThis.fetch).not.toHaveBeenCalled();
    expect(view.text()).toBe("");
    view.unmount();
  });

  it("sagt bei einem Link ohne Zusatz, was trotzdem drinsteht", async () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve(ok({ eintraege: [{ ...ENTRY, umfang: { preis: false, haus: false, wege: false, notiz: false } }] }))
    );
    const view = await open();

    expect(view.text()).toContain("Lage, Fläche und Bodenrichtwert");
    view.unmount();
  });

  it("bleibt still, wenn die Liste nicht zu holen ist", async () => {
    // Ein Fehler hier ist kein Grund, die Grundstücksseite mit einer Meldung
    // zu behängen: die Seite handelt nicht vom Teilen.
    globalThis.fetch = vi.fn(() => Promise.reject(new Error("Serverspeicher nicht eingerichtet")));
    const view = await open();

    expect(view.text()).toBe("");
    view.unmount();
  });
});
