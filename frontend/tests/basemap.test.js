/**
 * The vector backdrop and the palette it is drawn in.
 *
 * A drawing sits *on* the backdrop: a near-white ground under a dark page is a
 * glare source with the plot outline lost in it. The variant is decided here,
 * in the browser, because only the browser knows what "system" resolved to.
 */
import { describe, it, expect, beforeEach } from "vitest";
import { vectorStyle, withOverlay, NOISE_BANDS } from "../src/lib/basemap.js";
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

describe("Der Lärmschleier über dem Hintergrund", () => {
  /** A style with one source and one layer, as a backdrop hands one over. */
  const backdrop = () => ({
    version: 8,
    sources: { grund: { type: "raster", tiles: ["/api/tiles/dop/{z}/{x}/{y}.png"] } },
    layers: [{ id: "grund", type: "raster", source: "grund" }]
  });

  it("legt die Ebene über den Grund, nicht an seine Stelle", () => {
    const style = withOverlay(backdrop(), "laerm");

    expect(style.layers.map(l => l.id)).toEqual(["grund", "laerm"]);
    expect(style.sources.grund).toBeTruthy();
    // Through our own proxy: the noise service speaks no Web Mercator, so the
    // browser could not fetch these tiles itself.
    expect(style.sources.laerm.tiles[0]).toContain("/api/tiles/laerm/{z}/{x}/{y}.png");
  });

  it("nimmt über dem Luftbild die Deckkraft zurück", () => {
    const overMap = withOverlay(backdrop(), "laerm", "map");
    const overAerial = withOverlay(backdrop(), "laerm", "aerial");

    const opacity = style => style.layers.at(-1).paint["raster-opacity"];
    expect(opacity(overAerial)).toBeLessThan(opacity(overMap));
  });

  it("lässt einen unbekannten Namen den Stil unverändert", () => {
    const style = backdrop();
    expect(withOverlay(style, "gibtsnicht")).toBe(style);
    expect(withOverlay(style, null)).toBe(style);
  });

  it("nennt in der Legende nur die Bänder, die auch gezeichnet werden", () => {
    // The data carries Lden4549; the service's own renderer has no entry for
    // it, so the key must not claim a colour the map never draws.
    expect(NOISE_BANDS.laerm[0].label).toBe("50–54");
    expect(NOISE_BANDS.laerm.map(b => b.label)).not.toContain("45–49");
    expect(NOISE_BANDS.laerm.every(band => /^rgb\(/.test(band.colour))).toBe(true);
  });
});
