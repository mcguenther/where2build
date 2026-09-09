/**
 * Making a shared link.
 *
 * The property this file exists for: nothing optional travels unless somebody
 * switched it on. A link is public — the token is the whole of the access — so
 * the default has to be the least it can be, and a switch that quietly starts
 * on would put a price or a note in front of strangers.
 *
 * The other half is the signed-out case. Sharing needs a server to hold the
 * copy, so it needs an account; a disabled button with no reason is not an
 * answer, and neither is hiding the button so nobody learns the feature exists.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { flushPromises } from "@vue/test-utils";
import SharePanel from "../src/components/SharePanel.vue";
import { state } from "../src/lib/store.js";
import { realPlot, realState, realRoutes, realDestinations, mountWithRouter } from "./helpers.js";

const ok = body => ({ ok: true, status: 200, json: () => Promise.resolve(body) });

let plot;

beforeEach(() => {
  localStorage.clear();
  state.data = realState();
  state.account = { eingerichtet: true, angemeldet: true, name: "Erika", kennung: "abc" };
  plot = { ...realPlot("convex"), note: "Verkäufer in Eile", routes: realRoutes() };
  state.data.destinations = realDestinations();
  globalThis.fetch = vi.fn(() =>
    Promise.resolve(ok({ id: "AbCdEf123456789012", angelegt: "2026-09-09T10:00:00Z", laeuft_ab: "2026-12-08T10:00:00Z" }))
  );
});

afterEach(() => { vi.restoreAllMocks(); });

const open = () => mountWithRouter(SharePanel, { path: "/grundstueck/plot-convex", props: { plot } });

/** What the panel actually sent. */
const sent = () => JSON.parse(globalThis.fetch.mock.calls[0][1].body);

async function shareWith(view, switches = []) {
  for (const name of switches) {
    const box = view.findAll("label").find(l => l.text().includes(name)).find("input");
    await box.setValue(true);
  }
  await view.findAll("button").find(b => b.text().includes("Link erzeugen")).trigger("click");
  await flushPromises();
}

describe("Teilen", () => {
  it("teilt ohne Zutun nichts Optionales", async () => {
    const view = await open();
    await shareWith(view);

    const { dokument, umfang } = sent();
    expect(umfang).toEqual({ preis: false, haus: false, wege: false, notiz: false });
    // Und die Anreicherungen entstehen gar nicht erst.
    expect(dokument.placedBuilding).toBeUndefined();
    expect(dokument.sharedDestinations).toBeUndefined();
    view.unmount();
  });

  it("legt die Ziele erst auf die Leitung, wenn sie geteilt werden", async () => {
    // Alles zu schicken und auf das Wegschneiden im Backend zu vertrauen würde
    // funktionieren — und dabei fremde Adressen über die Leitung schicken für
    // einen Link, der sie gar nicht trägt.
    const view = await open();
    await shareWith(view, ["Ziele und Wegezeiten"]);

    const { dokument, umfang } = sent();
    expect(umfang.wege).toBe(true);
    expect(dokument.sharedDestinations.map(d => d.name)).toContain("Leipzig Hauptbahnhof");
    view.unmount();
  });

  it("löst den Baukörper auf, weil eine Momentaufnahme nichts nachschlagen kann", async () => {
    const view = await open();
    await shareWith(view, ["Geplantes Haus"]);

    const { dokument, umfang } = sent();
    expect(umfang.haus).toBe(true);
    expect(dokument.placedBuilding).toMatchObject({ width: expect.any(Number), depth: expect.any(Number) });
    view.unmount();
  });

  it("sagt hinterher, was mitgegangen ist", async () => {
    const view = await open();
    await shareWith(view, ["Kaufpreis", "Notiz"]);

    const text = view.text();
    expect(text).toContain("Zusätzlich mitgeteilt");
    expect(text).toContain("kaufpreis");
    expect(text).toContain("notiz");
    view.unmount();
  });

  it("sagt bei nichts Zusätzlichem, dass nur die Eckdaten mitgingen", async () => {
    const view = await open();
    await shareWith(view);

    expect(view.text()).toContain("nur Lage, Fläche und Bodenrichtwert");
    view.unmount();
  });

  it("sagt vorher, dass eine Vorschaukarte mitgeht", async () => {
    // Das Bild reist mit dem Link, ohne dass jemand es anklickt — wer teilt,
    // soll das vorher wissen und nicht erst im fremden Chatfenster sehen.
    const view = await open();

    expect(view.text()).toContain("Vorschaukarte");
    view.unmount();
  });

  it("lädt abgemeldet freundlich zum Konto ein, statt den Knopf zu sperren", async () => {
    state.account = { eingerichtet: true, angemeldet: false, name: null, kennung: null };
    const view = await open();

    expect(view.text()).toContain("Zum Teilen braucht es ein Konto");
    expect(view.find("a.btn").attributes("href")).toContain("/auth/login");
    // Und fragt nichts an, was ohnehin abgelehnt würde.
    expect(globalThis.fetch).not.toHaveBeenCalled();
    view.unmount();
  });

  it("sagt ohne Anbieter, dass Teilen hier nicht eingerichtet ist", async () => {
    state.account = { eingerichtet: false, angemeldet: false, name: null, kennung: null };
    const view = await open();

    expect(view.text()).toContain("nicht eingerichtet");
    // Kein Anmeldeknopf, der ins Leere führt.
    expect(view.find("a.btn").exists()).toBe(false);
    view.unmount();
  });
});
