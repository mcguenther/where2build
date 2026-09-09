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
  // Signing in is a fact about the deployment, and most of these tests are
  // about one that has no accounts at all.
  state.account = { eingerichtet: false, angemeldet: false, name: null, kennung: null };
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

  it("grüßt mit dem Namen, sobald jemand angemeldet ist", async () => {
    state.account = { eingerichtet: true, angemeldet: true, name: "Sam Jordan", kennung: "abc" };
    const view = await open();

    expect(view.text()).toContain("Willkommen zurück, Sam Jordan");
    view.unmount();
  });

  it("grüßt ohne Namen, wenn der Anbieter keinen mitgibt", async () => {
    state.account = { eingerichtet: true, angemeldet: true, name: null, kennung: "abc" };
    const view = await open();

    const text = view.text();
    expect(text).toContain("Willkommen zurück");
    expect(text).not.toContain("Willkommen zurück,");
    view.unmount();
  });

  it("bietet die Anmeldung an, wo es eine gibt", async () => {
    state.account = { eingerichtet: true, angemeldet: false, name: null, kennung: null };
    const view = await open();

    const offer = view.find(".hero__account");
    expect(offer.exists()).toBe(true);
    // Nicht nur ein Satz darüber, sondern der Weg selbst: die Kopfzeile ist im
    // frischen Zustand reduziert, und mitten auf der Seite sucht man zuerst.
    expect(offer.find("a").attributes("href")).toContain("/auth/login");
    expect(offer.text()).toContain("Konto anlegen");
    view.unmount();
  });

  it("sagt, dass keine Anmeldung eingerichtet ist, statt zu schweigen", async () => {
    // Der Zustand, in dem die Kopfzeile nichts zeigen kann. Vorher stand
    // nirgends etwas, und das las sich wie eine kaputte Anmeldung statt wie
    // eine, die es in diesem Betrieb nicht gibt.
    const view = await open();

    const offer = view.find(".hero__account");
    expect(offer.exists()).toBe(true);
    expect(offer.find("a").exists()).toBe(false);
    expect(offer.text()).toContain("nicht eingerichtet");
    view.unmount();
  });

  it("behauptet nicht mehr, der Serverspeicher sei noch nicht gebaut", async () => {
    // Der Satz war stehen geblieben, nachdem der Speicher fertig war -- eine
    // fertige Funktion, die die eigene Seite als fehlend meldet.
    state.sync = { active: true, busy: false, error: "", conflicts: [], savedAt: null, adoption: null };
    // Der Satz steht im Zweig ohne Grundstücke, also im leeren Stand.
    state.data.plots = [];
    const view = await open();

    const note = view.find(".home__storage").text();
    expect(note).toContain("im Konto");
    expect(note).not.toContain("noch nicht gebaut");
    view.unmount();
  });

  it("sagt es, wenn die Anmeldung abgebrochen ist, ohne den Weg zu versperren", async () => {
    // The query has to be on the route before the first render, so the router
    // is made ready here rather than pushed and hoped for.
    const router = testRouter("/?anmeldung=fehlgeschlagen");
    await router.isReady();
    const view = await open({ router });

    expect(view.text()).toContain("Die Anmeldung kam nicht zustande");
    // The field is the point of the page and stays usable either way.
    expect(view.findComponent(QueryBox).exists()).toBe(true);
    view.unmount();
  });
});
