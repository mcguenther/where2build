/**
 * The vector backdrop and the palette it is drawn in.
 *
 * A drawing sits *on* the backdrop: a near-white ground under a dark page is a
 * glare source with the plot outline lost in it. The variant is decided here,
 * in the browser, because only the browser knows what "system" resolved to.
 */
import { describe, it, expect, beforeEach } from "vitest";
import { PARCEL_OUTLINE_MIN_ZOOM, aerialCadastreStyle, vectorStyle } from "../src/lib/basemap.js";
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

describe("Luftbild mit Kataster", () => {
  it("legt Foto, Straßen und Flurstücksgrenzen in dieser Reihenfolge übereinander", () => {
    const style = aerialCadastreStyle();

    // Die Reihenfolge ist der ganze Trick: das Foto unten, die Straßen
    // darüber, die Grenzen zuoberst.
    expect(style.layers.map(l => l.id)).toEqual(["dop", "strassen", "flurstuecke"]);
    style.layers.forEach(layer => expect(layer.type).toBe("raster"));
  });

  it("holt jede Ebene durch das eigene Backend", () => {
    const style = aerialCadastreStyle();

    Object.entries(style.sources).forEach(([name, source]) => {
      expect(source.tiles[0]).toContain(`/api/tiles/${name}/`);
      expect(source.attribution).toContain("GeoSN");
    });
  });

  it("fragt die Flurstücksgrenzen erst da, wo der Dienst sie zeichnet", () => {
    const style = aerialCadastreStyle();

    // adv_alkis_flurstuecke trägt MaxScaleDenominator 2000 und antwortet
    // darüber mit einer leeren PNG statt mit einem Fehler: z18 ist 1:2133 und
    // leer, z19 ist 1:1066 und zeichnet. Gemessen an Flurstück 790/11.
    expect(PARCEL_OUTLINE_MIN_ZOOM).toBe(19);
    expect(style.sources.flurstuecke.minzoom).toBe(PARCEL_OUTLINE_MIN_ZOOM);
    expect(style.layers.find(l => l.id === "flurstuecke").minzoom).toBe(PARCEL_OUTLINE_MIN_ZOOM);
    // Das Foto und die Straßen dagegen zeichnen auf jeder Stufe.
    expect(style.sources.dop.minzoom).toBeUndefined();
    expect(style.sources.strassen.minzoom).toBeUndefined();
  });
});
