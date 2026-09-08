/**
 * The way in.
 *
 * Without a stand the page has to say what the thing is for; with one it has to
 * say what came in last and get out of the way. And whatever is typed into the
 * field is not resolved here — the wizard owns every step after the input, so
 * the page puts the input down (`lib/handoff.js`) and navigates into the first
 * stage. That handover is the part worth pinning down: it is the only path from
 * the field to an answer.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { flushPromises } from "@vue/test-utils";
import HomeView from "../src/views/HomeView.vue";
import QueryBox from "../src/components/QueryBox.vue";
import PlotCard from "../src/components/PlotCard.vue";
import { state } from "../src/lib/store.js";
import { takeHandoff } from "../src/lib/handoff.js";
import { realState, realPlot, mountWithRouter, testRouter } from "./helpers.js";

const answer = body => ({ ok: true, status: 200, json: () => Promise.resolve(body) });

beforeEach(() => {
  localStorage.clear();
  state.data = realState();
  // "none": a backdrop is a MapLibre instance, and the card thumbnails must not
  // each start one — nor reach for the network from jsdom.
  state.plan = { backdrop: "none", northUp: true, showDimensions: true, showSetbacks: true, measuring: false };
  // `created()` asks whether the backend is up; nothing else here is fetched.
  globalThis.fetch = () => Promise.resolve(answer({ status: "ok" }));
  // Module state, and one input at a time: a leftover from an earlier test
  // would be picked up by the next wizard that starts.
  takeHandoff();
});

afterEach(() => {
  vi.restoreAllMocks();
});

/** Mounted where it lives, with the health check settled. */
async function open(options = {}) {
  const view = mountWithRouter(HomeView, { path: "/", ...options });
  await flushPromises();
  return view;
}

describe("Startseite", () => {
  it("erklärt ohne Grundstücke, was hier passiert, und zeigt keine Karten", async () => {
    state.data.plots = [];
    state.data.selection = [];
    const view = await open();

    expect(view.findAll(".steps__item")).toHaveLength(3);
    const text = view.text();
    expect(text).toContain("Das Flurstück finden");
    expect(text).toContain("Prüfen, was darauf passt");
    expect(text).toContain("Wege messen");

    expect(view.findAllComponents(PlotCard)).toHaveLength(0);
    expect(text).not.toContain("Weitermachen");
    view.unmount();
  });

  it("bietet mit Grundstücken das Weitermachen an, mit höchstens drei Karten", async () => {
    state.data.plots = [
      realPlot("convex"), realPlot("concave"), realPlot("large"),
      realPlot("many-corners"), realPlot("moelkau")
    ];
    const view = await open();

    expect(view.text()).toContain("Weitermachen");
    // Enough to pick up where one left off; the list is one click away.
    expect(view.findAllComponents(PlotCard)).toHaveLength(3);
    expect(view.text()).toContain("Alle 5 Grundstücke");
    expect(view.find(".steps").exists()).toBe(false);
    view.unmount();
  });

  it("stellt die zuletzt aufgenommenen nach vorn", async () => {
    // `readAt` is when the parcel was read from the cadastre — the only date
    // the document carries, which is why the heading says "hinzugefügt".
    const [oldest, newest] = state.data.plots;
    oldest.readAt = "2026-08-29T09:00:00.000Z";
    newest.readAt = "2026-09-05T18:30:00.000Z";
    const view = await open();

    const shown = view.findAllComponents(PlotCard).map(card => card.props("plot").id);
    expect(shown).toEqual([newest.id, oldest.id]);
    view.unmount();
  });

  it("legt eine aufgelöste Eingabe für die Aufnahme ab und geht dorthin", async () => {
    const router = testRouter("/");
    await router.isReady();
    const view = await open({ router });

    const payload = {
      query: { gemarkung: "145592", flurstuecksnummer: "204" },
      label: "Flurstück: Mölkau 204",
      address: null
    };
    view.findComponent(QueryBox).vm.$emit("resolve", payload);
    await flushPromises();

    expect(router.currentRoute.value.fullPath).toBe("/aufnahme/quelle");
    // The page resolves nothing itself; it hands the input over untouched.
    expect(takeHandoff()).toEqual({ resolve: payload });
    view.unmount();
  });
});
