/**
 * The thumbnails' ground is asked for before a list or a comparison draws it.
 * That only helps if the prefetch asks for *exactly* the tiles the drawing
 * will: one zoom step or one column off and every tile is a cold request
 * again, with nothing on screen to tell. So these tests compare against what
 * the mounted drawings really render, not against a second copy of the maths.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import PlotThumbnail from "../src/components/PlotThumbnail.vue";
import CompareView from "../src/views/CompareView.vue";
import App from "../src/App.vue";
import { state, addPlot } from "../src/lib/store.js";
import {
  CARD_FRAME, COMPARE_FRAME, sharedThumbnailScale, thumbnailTiles, thumbnailTileUrls, wantedThumbnailTiles
} from "../src/lib/thumbnail.js";
import { prefetchTiles, resetPrefetch } from "../src/lib/tileGround.js";
import { realState, realPlot, mountWithRouter, testRouter } from "./helpers.js";

/* Where a tile goes as well as which one: the cover is the frame's diagonal on
   every side, so a centre a few metres off still asks for the same tiles —
   and would draw them in the wrong place. */
const rendered = wrapper =>
  wrapper.findAll(".site-plan__tile-ground image").map(image => ({
    href: image.attributes("href"),
    x: Number(image.attributes("x")).toFixed(2),
    y: Number(image.attributes("y")).toFixed(2)
  }));
const placed = tiles => tiles.map(tile => ({ href: tile.href, x: tile.x.toFixed(2), y: tile.y.toFixed(2) }));

/* Records what would have gone to the network. jsdom fetches no images, so
   without this a prefetch that never ran would pass as well as one that did. */
let requested;
class RecordingImage {
  set src(url) { requested.push({ url, priority: this.fetchPriority }); }
}

beforeEach(() => {
  localStorage.clear();
  state.data = realState();
  // Mölkau 204 turned to its second edge: a plot that is not north-up is the
  // case where a prefetch that forgot the rotation would ask for other tiles.
  state.data.plots.push(realPlot("moelkau", { streetEdge: 2 }));
  state.plan = { backdrop: "none", northUp: true, showDimensions: true, showSetbacks: true, measuring: false };
  requested = [];
  resetPrefetch();
  vi.stubGlobal("Image", RecordingImage);
});

afterEach(() => vi.unstubAllGlobals());

describe("Vorladen der Vorschaukacheln", () => {
  it("nennt für jede Karte genau die Kacheln, die ihr Vorschaubild zeichnet", () => {
    for (const plot of state.data.plots) {
      const drawn = rendered(mount(PlotThumbnail, { props: { plot } }));
      expect(drawn.length).toBeGreaterThan(0);
      expect(placed(thumbnailTiles(plot, CARD_FRAME))).toEqual(drawn);
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
    state.data.selection = [];
    const cardsOnly = wantedThumbnailTiles(state.data.plots, []);
    const withComparison = wantedThumbnailTiles(state.data.plots, state.data.plots.map(plot => plot.id));
    expect(withComparison.length).toBeGreaterThan(cardsOnly.length);
    expect(withComparison).toEqual(expect.arrayContaining(cardsOnly));
  });

  it("fragt jede Kachel einmal an, mit niedriger Priorität", () => {
    const urls = thumbnailTileUrls(state.data.plots[0], CARD_FRAME);
    expect(prefetchTiles(urls)).toBe(urls.length);
    expect(prefetchTiles(urls)).toBe(0);
    expect(requested.map(r => r.url)).toEqual(urls);
    expect(requested.every(r => r.priority === "low")).toBe(true);
  });

  it("lädt beim Start vor und wieder, sobald ein Grundstück dazukommt", async () => {
    globalThis.fetch = vi.fn(() => Promise.resolve({
      ok: true, status: 200,
      json: () => Promise.resolve({ eingerichtet: true, angemeldet: false })
    }));
    const router = testRouter("/");
    await router.isReady();
    const view = mountWithRouter(App, { router });
    await flushPromises();
    await flushPromises();

    const atStart = new Set(requested.map(r => r.url));
    for (const url of wantedThumbnailTiles(state.data.plots, state.data.selection)) {
      expect(atStart.has(url)).toBe(true);
    }

    const plot = addPlot({ ...realPlot("large"), id: "plot-large-neu" });
    await flushPromises();
    const added = requested.map(r => r.url).filter(url => !atStart.has(url));
    expect(added).toEqual(expect.arrayContaining(thumbnailTileUrls(plot, CARD_FRAME)));
    view.unmount();
  });
});
