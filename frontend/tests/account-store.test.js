/**
 * The account's copy of the document.
 *
 * What matters here is the third state. Signed out and no store behind the
 * deployment look the same from the browser, and both mean the app works
 * exactly as it always has; only a signed-in account with a store changes
 * anything, and even then this browser keeps its own copy.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { state, loadFromAccount, adoptLocal, declineAdoption, save, flushSave } from "../src/lib/store.js";
import { realState, realPlot } from "./helpers.js";

const json = (status, body) => ({
  ok: status < 400,
  status,
  json: () => Promise.resolve(body)
});

/** A backend that answers from a table of routes, and records what it got. */
function backend(routes) {
  const calls = [];
  globalThis.fetch = (path, options = {}) => {
    const method = options.method || "GET";
    calls.push({ path, method, body: options.body ? JSON.parse(options.body) : null });
    const answer = routes[`${method} ${path}`] ?? routes[path];
    if (!answer) return Promise.resolve(json(404, { detail: "Nicht gefunden." }));
    return Promise.resolve(typeof answer === "function" ? answer(calls.length) : answer);
  };
  return calls;
}

const signedIn = () => {
  state.account = { eingerichtet: true, angemeldet: true, name: "Sam Jordan", kennung: "abc" };
};

beforeEach(() => {
  localStorage.clear();
  state.data = realState();
  state.account = { eingerichtet: false, angemeldet: false, name: null, kennung: null };
  state.sync = { active: false, busy: false, error: "", conflicts: [], savedAt: null, adoption: null };
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Der Stand im Konto", () => {
  it("bleibt aus, solange niemand angemeldet ist", async () => {
    const calls = backend({});
    await loadFromAccount();

    expect(state.sync.active).toBe(false);
    expect(calls).toHaveLength(0);
    expect(state.sync.adoption).toBeNull();
  });

  it("bleibt aus, wenn diese Installation gar keinen Speicher hat, und sagt nichts von einem Fehler", async () => {
    signedIn();
    backend({ "/api/plots": json(503, { detail: "Kein Serverspeicher eingerichtet." }) });
    await loadFromAccount();

    // 503 heißt „gibt es hier nicht", und das ist kein Fehlschlag: die App war
    // von Anfang an eine, die im Browser bleibt.
    expect(state.sync.active).toBe(false);
    expect(state.sync.error).toBe("");
  });

  it("übernimmt den Stand aus dem Konto, wenn dort einer liegt", async () => {
    signedIn();
    // `realPlot` vergibt die id selbst (sie kommt aus dem Kataster-Fixture),
    // also wird sie danach gesetzt.
    const stored = { ...realPlot("convex"), id: "vom-server", name: "Aus dem Konto" };
    backend({
      "/api/plots": json(200, { eintraege: [{ id: stored.id, geaendert_am: "2026-09-09T00:00:00Z", dokument: stored }] }),
      "/api/settings": json(200, { geaendert_am: "2026-09-09T00:00:00Z", dokument: { version: 2, houseTypes: [], destinations: [], selection: [] } })
    });
    await loadFromAccount();

    expect(state.sync.active).toBe(true);
    expect(state.data.plots.map(p => p.id)).toEqual(["vom-server"]);
    expect(state.sync.adoption).toBeNull();
  });

  it("fragt beim leeren Konto, ob der Stand dieses Browsers mitkommt", async () => {
    signedIn();
    backend({
      "/api/plots": json(200, { eintraege: [] }),
      "/api/settings": json(200, { geaendert_am: null, dokument: {} })
    });
    await loadFromAccount();

    expect(state.sync.adoption).toEqual({ plots: 2 });
    // Und nichts ist verloren: der lokale Stand steht unverändert da.
    expect(state.data.plots).toHaveLength(2);
  });

  it("fragt nicht noch einmal, wenn schon abgelehnt wurde", async () => {
    signedIn();
    backend({
      "/api/plots": json(200, { eintraege: [] }),
      "/api/settings": json(200, { geaendert_am: null, dokument: {} })
    });
    await loadFromAccount();
    declineAdoption();
    await loadFromAccount();

    expect(state.sync.adoption).toBeNull();
  });

  it("schreibt beim Übernehmen jedes Grundstück und den Rest", async () => {
    signedIn();
    const calls = backend({
      "/api/plots": json(200, { eintraege: [] }),
      "/api/settings": json(200, { geaendert_am: null, dokument: {} }),
      "PUT /api/settings": json(200, { geaendert_am: "2026-09-09T01:00:00Z" }),
      [`PUT /api/plots/${realState().plots[0].id}`]: json(200, { geaendert_am: "2026-09-09T01:00:00Z" }),
      [`PUT /api/plots/${realState().plots[1].id}`]: json(200, { geaendert_am: "2026-09-09T01:00:00Z" })
    });
    await loadFromAccount();
    await adoptLocal();

    const puts = calls.filter(c => c.method === "PUT");
    expect(puts.map(c => c.path)).toContain("/api/settings");
    expect(puts.filter(c => c.path.startsWith("/api/plots/"))).toHaveLength(2);
    // Neu heißt gegen `null` geschrieben: so lehnt der Server ab, statt etwas
    // zu überschreiben, das jemand anders schon dorthin gelegt hat.
    expect(puts.every(c => c.body.geaendert_am === null)).toBe(true);
    expect(state.sync.adoption).toBeNull();
  });

  it("zeigt einen Konflikt, statt den fremden Stand zu überschreiben", async () => {
    signedIn();
    const mine = state.data.plots[0];
    const theirs = { ...mine, name: "Anderswo geändert" };
    backend({
      "/api/plots": json(200, { eintraege: [{ id: mine.id, geaendert_am: "2026-09-09T00:00:00Z", dokument: mine }] }),
      "/api/settings": json(200, { geaendert_am: "2026-09-09T00:00:00Z", dokument: { version: 2, houseTypes: [], destinations: [], selection: [] } }),
      [`PUT /api/plots/${mine.id}`]: json(409, {
        detail: "Dieses Grundstück wurde anderswo geändert.",
        aktuell: { id: mine.id, geaendert_am: "2026-09-09T02:00:00Z", dokument: theirs }
      })
    });
    await loadFromAccount();

    state.data.plots[0].name = "Hier geändert";
    save();
    await flushSave();

    expect(state.sync.conflicts).toHaveLength(1);
    expect(state.sync.conflicts[0].aktuell.dokument.name).toBe("Anderswo geändert");
    // Nichts wurde still ersetzt: was hier steht, steht weiter hier.
    expect(state.data.plots[0].name).toBe("Hier geändert");
  });

  it("schreibt ohne Konto nur in diesen Browser", async () => {
    const calls = backend({});
    save();
    await flushSave();

    expect(calls).toHaveLength(0);
    expect(JSON.parse(localStorage.getItem("where2build.v1")).plots).toHaveLength(2);
  });
});
