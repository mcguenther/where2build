/**
 * The header, and the two things it must never get wrong.
 *
 * **The way into an account is in every state.** The header steps back on the
 * way in — the sections all lead to empty pages there — and the sign-in must
 * not step back with it. It was worse than that before: where a deployment has
 * no provider the header showed nothing and the page said nothing either, so a
 * sign-in that simply does not exist here looked like one that is broken.
 *
 * **Clearing everything out puts somebody back at the start.** Adding plots and
 * destinations and then deleting them left the navigation standing with every
 * counter at zero, which is furniture around an empty app rather than a
 * greeting.
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { flushPromises } from "@vue/test-utils";
import App from "../src/App.vue";
import { state } from "../src/lib/store.js";
import { realState, mountWithRouter, testRouter } from "./helpers.js";

const EMPTY = { version: 3, plots: [], houseTypes: [], destinations: [], selection: [] };

beforeEach(() => {
  localStorage.clear();
  state.data = { ...EMPTY };
  state.account = { eingerichtet: true, angemeldet: false, name: null, kennung: null };
  state.sync = { active: false, busy: false, error: "", conflicts: [], savedAt: null, adoption: null };
  // `created()` asks the backend who is signed in; the state is set per test,
  // so the answer must not overwrite it.
  globalThis.fetch = vi.fn(() =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(state.account) })
  );
});

/** The shell, on a route, with its two start-up calls settled. */
async function open(path = "/") {
  const router = testRouter(path);
  await router.isReady();
  const view = mountWithRouter(App, { router });
  await flushPromises();
  await flushPromises();
  return view;
}

const nav = view => view.find(".main-nav");
const signIn = view => view.findAll("a.btn").find(a => a.text() === "Anmelden");
const signOut = view => view.findAll("button").find(b => b.text() === "Abmelden");

describe("Kopfzeile", () => {
  it("tritt auf der Startseite zurück, solange nichts angelegt ist", async () => {
    const view = await open("/");

    expect(nav(view).exists()).toBe(false);
    // Die Marke bleibt: sie ist der Weg zurück, wenn die Bereiche fehlen.
    expect(view.find(".brand").exists()).toBe(true);
    view.unmount();
  });

  it("lässt die Anmeldung stehen, wenn die Navigation weicht", async () => {
    // Der Punkt der ganzen Datei: der reduzierte Kopf darf den einen Weg, der
    // dort noch etwas tut, nicht mitnehmen.
    const view = await open("/");

    expect(nav(view).exists()).toBe(false);
    expect(signIn(view)).toBeTruthy();
    expect(signIn(view).attributes("href")).toContain("/auth/login");
    view.unmount();
  });

  it("holt die Navigation zurück, sobald etwas angelegt ist", async () => {
    // Ein einzelnes Ziel genügt: die Anwendung ist dann in Benutzung, und die
    // Bereiche führen wieder irgendwohin.
    state.data = { ...EMPTY, destinations: [{ id: "zl-1", name: "Arbeit" }] };
    const view = await open("/");

    expect(nav(view).exists()).toBe(true);
    expect(signIn(view)).toBeTruthy();
    view.unmount();
  });

  it("begrüßt nach dem Löschen wieder wie am Anfang", async () => {
    // Der gemeldete Fehler: Grundstücke und Ziele angelegt, wieder gelöscht,
    // und die Leiste stand weiter da -- mit lauter Nullen darin.
    state.data = realState();
    const view = await open("/");
    expect(nav(view).exists()).toBe(true);

    state.data = { ...EMPTY };
    await flushPromises();

    expect(nav(view).exists()).toBe(false);
    view.unmount();
  });

  it("zeigt die Bereiche überall außer auf der Startseite", async () => {
    // Auch im frischen Zustand: von einer anderen Seite sind die Bereiche der
    // Weg zurück, und die auszublenden wäre eine Sackgasse.
    const view = await open("/daten");

    expect(nav(view).exists()).toBe(true);
    view.unmount();
  });

  it("zeigt angemeldet den Namen und den Weg hinaus", async () => {
    state.account = { eingerichtet: true, angemeldet: true, name: "Erika Musterfrau", kennung: "abc" };
    const view = await open("/");

    expect(signOut(view)).toBeTruthy();
    expect(view.find(".account__name").text()).toBe("Erika Musterfrau");
    // Angemeldet ist ein Stand für sich: die Bereiche gehören dazu, auch wenn
    // noch kein Grundstück darin liegt.
    expect(nav(view).exists()).toBe(true);
    view.unmount();
  });

  it("verspricht keine Anmeldung, wo es keine gibt", async () => {
    // Ohne Anbieter gibt es nichts zu drücken, also steht hier auch nichts --
    // gesagt wird es auf der Startseite, siehe home-view.test.js.
    state.account = { eingerichtet: false, angemeldet: false, name: null, kennung: null };
    const view = await open("/");

    expect(signIn(view)).toBeUndefined();
    expect(signOut(view)).toBeUndefined();
    view.unmount();
  });
});
