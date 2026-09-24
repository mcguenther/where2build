/**
 * The thumbnails' ground is put into the backend's cache before a list or a
 * comparison draws it. That only helps if the backend is told *exactly* the
 * tiles the drawing will ask for: one zoom step or one column off and every
 * tile is a cold request again, with nothing on screen to tell. So these tests
 * compare against what the mounted drawings really render, not against a
 * second copy of the maths.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import PlotThumbnail from "../src/components/PlotThumbnail.vue";
import CompareView from "../src/views/CompareView.vue";
import App from "../src/App.vue";
import { state, addPlot } from "../src/lib/store.js";
import { tileUrl } from "../src/lib/routes.js";
import {
  CARD_FRAME, COMPARE_FRAME, sharedThumbnailScale, thumbnailTiles, thumbnailTileRefs, wantedThumbnailTiles
} from "../src/lib/thumbnail.js";
import { MAX_WARM_TILES, resetWarmTiles, warmTiles } from "../src/lib/tileGround.js";
import { realState, realPlot, mountWithRouter, testRouter } from "./helpers.js";

/* Where a tile goes as well as which one: the cover is the frame's diagonal on
   every side, so a centre a few metres off still asks for the same tiles —
   and would draw them in the wrong place. A URL-only comparison passed with
   the rotation deleted. */
const rendered = wrapper =>
  wrapper.findAll(".site-plan__tile-ground image").map(image => ({
    href: image.attributes("href"),
    x: Number(image.attributes("x")).toFixed(2),
    y: Number(image.attributes("y")).toFixed(2)
  }));
const placed = tiles => tiles.map(tile => ({ href: tile.href, x: tile.x.toFixed(2), y: tile.y.toFixed(2) }));
const hrefOf = ref => tileUrl(ref, ref.ebene);

beforeEach(() => {
  localStorage.clear();
  state.data = realState();
  // Mölkau 204 turned to its second edge: a plot that is not north-up is the
  // case where a warm-up that forgot the rotation would name other tiles.
  state.data.plots.push(realPlot("moelkau", { streetEdge: 2 }));
  state.plan = { backdrop: "none", northUp: true, showDimensions: true, showSetbacks: true, measuring: false };
  resetWarmTiles();
});

afterEach(() => vi.unstubAllGlobals());

describe("Vorwärmen der Vorschaukacheln", () => {
  it("nennt für jede Karte genau die Kacheln, die ihr Vorschaubild zeichnet", () => {
    for (const plot of state.data.plots) {
      const drawn = rendered(mount(PlotThumbnail, { props: { plot } }));
      expect(drawn.length).toBeGreaterThan(0);
      expect(placed(thumbnailTiles(plot, CARD_FRAME))).toEqual(drawn);
      expect(thumbnailTileRefs(plot, CARD_FRAME).map(hrefOf)).toEqual(drawn.map(tile => tile.href));
    }
  });

  it("nennt für den Vergleich die Kacheln im gemeinsamen Maßstab", () => {
    state.data.selection = state.data.plots.map(plot => plot.id);
    const drawn = rendered(mountWithRouter(CompareView));
    const shared = sharedThumbnailScale(state.data.plots, COMPARE_FRAME.width, COMPARE_FRAME.height);
    const predicted = state.data.plots.flatMap(plot => placed(thumbnailTiles(plot, COMPARE_FRAME, shared)));
    expect(drawn.length).toBeGreaterThan(0);
    expect(predicted).toEqual(drawn);
  });

  it("nimmt die Vergleichskacheln nur für ausgewählte Grundstücke dazu", () => {
    const cardsOnly = wantedThumbnailTiles(state.data.plots, []);
    const withComparison = wantedThumbnailTiles(state.data.plots, state.data.plots.map(plot => plot.id));
    expect(withComparison.length).toBeGreaterThan(cardsOnly.length);
    expect(withComparison).toEqual(expect.arrayContaining(cardsOnly));
  });

  it("nennt dem Backend jede Kachel einmal und in Portionen, die es annimmt", async () => {
    const refs = Array.from({ length: MAX_WARM_TILES + 10 }, (_, i) => ({ ebene: "umgebung", z: 17, x: 70000 + i, y: 43715 }));
    const send = vi.fn(() => Promise.resolve({}));

    expect(await warmTiles(refs, send)).toBe(refs.length);
    expect(await warmTiles(refs, send)).toBe(0);
    expect(send.mock.calls.map(([batch]) => batch.length)).toEqual([MAX_WARM_TILES, 10]);
  });

  it("fragt nach einem Fehler beim nächsten Mal wieder", async () => {
    const refs = thumbnailTileRefs(state.data.plots[0], CARD_FRAME);
    const failing = vi.fn(() => Promise.reject(new Error("offline")));
    await warmTiles(refs, failing);

    const send = vi.fn(() => Promise.resolve({}));
    expect(await warmTiles(refs, send)).toBe(refs.length);
  });

  it("meldet beim Start und bei jedem neuen Grundstück, ohne selbst Kacheln zu laden", async () => {
    const warmed = [];
    const tileDownloads = [];
    globalThis.fetch = vi.fn((url, options = {}) => {
      if (url === "/api/tiles/warm") warmed.push(...JSON.parse(options.body).kacheln);
      else if (String(url).startsWith("/api/tiles/")) tileDownloads.push(url);
      return Promise.resolve({
        ok: true, status: 200,
        json: () => Promise.resolve({ eingerichtet: true, angemeldet: false })
      });
    });
    const router = testRouter("/");
    await router.isReady();
    const view = mountWithRouter(App, { router });
    await flushPromises();
    await flushPromises();

    const atStart = new Set(warmed.map(hrefOf));
    for (const ref of wantedThumbnailTiles(state.data.plots, state.data.selection)) {
      expect(atStart.has(hrefOf(ref))).toBe(true);
    }

    const plot = addPlot({ ...realPlot("large"), id: "plot-large-neu" });
    await flushPromises();
    const added = warmed.map(hrefOf).filter(href => !atStart.has(href));
    expect(added).toEqual(expect.arrayContaining(thumbnailTileRefs(plot, CARD_FRAME).map(hrefOf)));
    expect(tileDownloads).toEqual([]);
    view.unmount();
  });
});
