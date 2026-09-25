/**
 * The thumbnails' ground is one image the backend composes, and it is built
 * before a list or a comparison draws it. That only helps if the backend is
 * told *exactly* the block the drawing will ask for: one zoom step or one
 * column off and it is a cold request again, with nothing on screen to tell.
 * So these tests compare against what the mounted drawings really render, not
 * against a second copy of the maths.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import PlotThumbnail from "../src/components/PlotThumbnail.vue";
import CompareView from "../src/views/CompareView.vue";
import App from "../src/App.vue";
import { state, addPlot } from "../src/lib/store.js";
import {
  CARD_FRAME, COMPARE_FRAME, sharedThumbnailScale, thumbnailGround, wantedThumbnailGrounds
} from "../src/lib/thumbnail.js";
import { MAX_WARM_BLOCKS, blockUrl, resetWarmBlocks, warmBlocks } from "../src/lib/tileGround.js";
import { realState, realPlot, mountWithRouter, testRouter } from "./helpers.js";

/* Where the image goes as well as which one: the cover is the frame's
   diagonal on every side, so a centre a few metres off still asks for the
   same block — and would draw it in the wrong place. A URL-only comparison
   passed with the rotation deleted. */
const rendered = wrapper =>
  wrapper.findAll(".site-plan__tile-ground image").map(image => ({
    href: image.attributes("href"),
    x: Number(image.attributes("x")).toFixed(2),
    y: Number(image.attributes("y")).toFixed(2),
    width: Number(image.attributes("width")).toFixed(2),
    height: Number(image.attributes("height")).toFixed(2)
  }));
const placed = ground => ({
  href: ground.href,
  x: ground.x.toFixed(2), y: ground.y.toFixed(2),
  width: ground.width.toFixed(2), height: ground.height.toFixed(2)
});

beforeEach(() => {
  localStorage.clear();
  state.data = realState();
  // Mölkau 204 turned to its second edge: a plot that is not north-up is the
  // case where a warm-up that forgot the rotation would name another block.
  state.data.plots.push(realPlot("moelkau", { streetEdge: 2 }));
  state.plan = { backdrop: "none", northUp: true, showDimensions: true, showSetbacks: true, measuring: false };
  resetWarmBlocks();
});

afterEach(() => vi.unstubAllGlobals());

describe("Vorwärmen der Vorschaubilder", () => {
  it("zeichnet je Karte genau ein Bild, und zwar den Block, der vorgewärmt wird", () => {
    for (const plot of state.data.plots) {
      const drawn = rendered(mount(PlotThumbnail, { props: { plot } }));
      expect(drawn).toHaveLength(1);
      const ground = thumbnailGround(plot, CARD_FRAME);
      expect([placed(ground)]).toEqual(drawn);
      expect(blockUrl(ground.ref)).toBe(drawn[0].href);
      // The block covers what separate tiles did: whole tiles, at least 2 x 2
      // for a frame's diagonal on every side.
      expect(ground.ref.ost - ground.ref.west + 1).toBeGreaterThanOrEqual(2);
      expect(ground.ref.sued - ground.ref.nord + 1).toBeGreaterThanOrEqual(2);
    }
  });

  it("zeichnet das gedrehte Grundstück dorthin, wohin seine Drehung es legt", () => {
    const turned = state.data.plots.find(plot => plot.id.includes("moelkau"));
    const drawn = rendered(mount(PlotThumbnail, { props: { plot: turned } }));
    const upright = rendered(mount(PlotThumbnail, { props: { plot: { ...turned, streetEdge: 0 } } }));
    // A different turn is a different centre, and the image has to follow it.
    expect(drawn[0]).not.toEqual(upright[0]);
    expect([placed(thumbnailGround(turned, CARD_FRAME))]).toEqual(drawn);
  });

  it("zeichnet im Vergleich die Blöcke im gemeinsamen Maßstab", () => {
    state.data.selection = state.data.plots.map(plot => plot.id);
    const drawn = rendered(mountWithRouter(CompareView));
    const shared = sharedThumbnailScale(state.data.plots, COMPARE_FRAME.width, COMPARE_FRAME.height);
    const predicted = state.data.plots.map(plot => placed(thumbnailGround(plot, COMPARE_FRAME, shared)));
    expect(drawn).toHaveLength(state.data.plots.length);
    expect(predicted).toEqual(drawn);
    const warmed = wantedThumbnailGrounds(state.data.plots, state.data.selection).map(blockUrl);
    expect(warmed).toEqual(expect.arrayContaining(drawn.map(ground => ground.href)));
  });

  it("nimmt die Vergleichsblöcke nur für ausgewählte Grundstücke dazu", () => {
    const cardsOnly = wantedThumbnailGrounds(state.data.plots, []);
    const withComparison = wantedThumbnailGrounds(state.data.plots, state.data.plots.map(plot => plot.id));
    expect(cardsOnly).toHaveLength(state.data.plots.length);
    expect(withComparison.length).toBeGreaterThan(cardsOnly.length);
    expect(withComparison).toEqual(expect.arrayContaining(cardsOnly));
  });

  it("nennt dem Backend jeden Block einmal und in Portionen, die es annimmt", async () => {
    const refs = Array.from({ length: MAX_WARM_BLOCKS + 10 }, (_, i) =>
      ({ ebene: "umgebung", z: 17, west: 70000 + i, nord: 43715, ost: 70002 + i, sued: 43717 }));
    const send = vi.fn(() => Promise.resolve({}));

    expect(await warmBlocks(refs, send)).toBe(refs.length);
    expect(await warmBlocks(refs, send)).toBe(0);
    expect(send.mock.calls.map(([batch]) => batch.length)).toEqual([MAX_WARM_BLOCKS, 10]);
  });

  it("fragt nach einem Fehler beim nächsten Mal wieder", async () => {
    const refs = wantedThumbnailGrounds(state.data.plots);
    const failing = vi.fn(() => Promise.reject(new Error("offline")));
    await warmBlocks(refs, failing);

    const send = vi.fn(() => Promise.resolve({}));
    expect(await warmBlocks(refs, send)).toBe(refs.length);
  });

  it("meldet beim Start und bei jedem neuen Grundstück, ohne selbst Bilder zu laden", async () => {
    const warmed = [];
    const downloads = [];
    globalThis.fetch = vi.fn((url, options = {}) => {
      if (url === "/api/tiles/warm") warmed.push(...JSON.parse(options.body).bloecke);
      else if (String(url).startsWith("/api/tiles/")) downloads.push(url);
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

    const atStart = new Set(warmed.map(blockUrl));
    for (const ref of wantedThumbnailGrounds(state.data.plots, state.data.selection)) {
      expect(atStart.has(blockUrl(ref))).toBe(true);
    }

    const plot = addPlot({ ...realPlot("large"), id: "plot-large-neu" });
    await flushPromises();
    const added = warmed.map(blockUrl).filter(href => !atStart.has(href));
    // Its card, and whatever comparison blocks a changed shared scale moved.
    expect(added).toContain(thumbnailGround(plot, CARD_FRAME).href);
    expect(downloads).toEqual([]);
    view.unmount();
  });
});

describe("Einblenden des Vorschaubilds", () => {
  const groundOf = wrapper => wrapper.find(".site-plan__tile-ground image");

  it("bleibt verborgen, bis das Bild ganz geladen ist, und erscheint dann auf einmal", async () => {
    const wrapper = mount(PlotThumbnail, { props: { plot: state.data.plots[0] } });
    expect(groundOf(wrapper).classes()).not.toContain("is-loaded");
    expect(groundOf(wrapper).attributes("data-ground")).toBe("loading");

    await groundOf(wrapper).trigger("load");
    expect(groundOf(wrapper).classes()).toContain("is-loaded");
    expect(groundOf(wrapper).attributes("data-ground")).toBe("ready");
  });

  it("beginnt verborgen, wenn sich der Ausschnitt ändert", async () => {
    const wrapper = mount(PlotThumbnail, { props: { plot: state.data.plots[0] } });
    await groundOf(wrapper).trigger("load");
    const before = groundOf(wrapper).attributes("href");

    await wrapper.setProps({ width: COMPARE_FRAME.width, height: COMPARE_FRAME.height });
    expect(groundOf(wrapper).attributes("href")).not.toBe(before);
    expect(groundOf(wrapper).classes()).not.toContain("is-loaded");
  });

  it("lässt nach einem Fehler die flache Fläche stehen, ohne Bildsymbol", async () => {
    const wrapper = mount(PlotThumbnail, { props: { plot: state.data.plots[0] } });
    await groundOf(wrapper).trigger("error");
    expect(wrapper.find(".site-plan__tile-ground").exists()).toBe(false);
    expect(wrapper.find("svg > rect").exists()).toBe(true);
  });
});
