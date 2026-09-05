/**
 * The vector backdrop and the palette it is drawn in.
 *
 * A drawing sits *on* the backdrop: a near-white ground under a dark page is a
 * glare source with the plot outline lost in it. The variant is decided here,
 * in the browser, because only the browser knows what "system" resolved to.
 */
import { describe, it, expect, beforeEach } from "vitest";
import { vectorStyle } from "../src/lib/basemap.js";
import { state, darkTheme, watchSystemTheme } from "../src/lib/store.js";

/** Just enough of a style document for `vectorStyle` to hand back. */
const STYLE = { version: 8, glyphs: "/api/basemap/fonts/{fontstack}/{range}.pbf", sources: {}, layers: [] };

const answerWithStyle = () => {
  const fetched = [];
  globalThis.fetch = url => {
    fetched.push(String(url));
    return Promise.resolve({ ok: true, json: () => Promise.resolve(structuredClone(STYLE)) });
  };
  return fetched;
};

/** A `matchMedia` that answers one fixed way and records its listeners. */
const systemPrefers = dark => {
  const listeners = [];
  window.matchMedia = query => ({
    media: query,
    matches: query.includes("dark") ? dark : !dark,
    addEventListener: (_, fn) => listeners.push(fn),
    removeEventListener: () => {}
  });
  return listeners;
};

describe("Die Palette des Kartenhintergrunds", () => {
  beforeEach(() => {
    state.theme = "system";
    state.systemDark = false;
    watchSystemTheme.attached = false;
    delete window.matchMedia;
  });

  it("fragt hell an, solange die Oberfläche hell ist", async () => {
    const fetched = answerWithStyle();
    await vectorStyle();
    expect(fetched[0]).toContain("variant=light");
  });

  it("fragt dunkel an, sobald die Oberfläche dunkel ist", async () => {
    state.theme = "dark";
    const fetched = answerWithStyle();
    await vectorStyle();
    expect(fetched[0]).toContain("variant=dark");
  });

  it("folgt der Systemeinstellung, wenn niemand gewählt hat", () => {
    systemPrefers(true);
    watchSystemTheme();
    expect(darkTheme()).toBe(true);

    // An explicit choice outranks the system, in both directions.
    state.theme = "light";
    expect(darkTheme()).toBe(false);
  });

  it("merkt, wenn das System die Einstellung wechselt", () => {
    const listeners = systemPrefers(false);
    watchSystemTheme();
    expect(darkTheme()).toBe(false);

    listeners.forEach(fn => fn({ matches: true }));
    expect(darkTheme()).toBe(true);
  });

  it("bleibt hell, wo der Browser die Frage gar nicht beantwortet", () => {
    // jsdom has no `matchMedia` at all; that must not throw on start-up.
    expect(() => watchSystemTheme()).not.toThrow();
    expect(darkTheme()).toBe(false);
  });

  it("hängt sich nur einmal an die Systemeinstellung", () => {
    const listeners = systemPrefers(false);
    watchSystemTheme();
    watchSystemTheme();
    expect(listeners).toHaveLength(1);
  });

  it("meldet einen Stil, der nicht kommt, statt ewig zu warten", async () => {
    globalThis.fetch = () => Promise.resolve({ ok: false, status: 502 });
    await expect(vectorStyle()).rejects.toThrow(/502/);
  });
});
