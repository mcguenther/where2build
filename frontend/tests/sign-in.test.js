/**
 * Signing in without losing the page.
 *
 * The exchange used to be a full navigation away and back: three origins,
 * five redirects, and everything this browser was holding — a pasted advert,
 * a dragged building, an unsaved note — reloaded from storage on the way
 * back, or gone where it was never stored. That is a lot to ask of somebody
 * who only wanted an account so their work would be kept.
 *
 * So it runs in a window of its own. What has to hold:
 *
 * - the page does not navigate,
 * - a browser that refuses the window still gets somebody signed in,
 * - whether it worked is asked of the backend, because a window closed by
 *   hand posts nothing and a window that posts and closes is a race.
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { flushPromises } from "@vue/test-utils";
import App from "../src/App.vue";
import { state } from "../src/lib/store.js";
import { beginSignIn, reportSignedIn, DONE_PATH, SIGNED_IN } from "../src/lib/signIn.js";
import { mountWithRouter, testRouter } from "./helpers.js";

const EMPTY = { version: 3, plots: [], houseTypes: [], destinations: [], selection: [] };

const SIGNED_OUT = { eingerichtet: true, angemeldet: false, name: null, kennung: null };
const SIGNED = { eingerichtet: true, angemeldet: true, name: "Erika Musterfrau", kennung: "abc" };

/** A stand-in for the browser: what `signIn.js` is allowed to touch. */
function fakeView({ popup = { closed: false } } = {}) {
  const listeners = [];
  return {
    open: vi.fn(() => popup),
    location: { origin: "http://localhost", assign: vi.fn() },
    addEventListener: (kind, fn) => kind === "message" && listeners.push(fn),
    removeEventListener: (kind, fn) => {
      const at = listeners.indexOf(fn);
      if (at >= 0) listeners.splice(at, 1);
    },
    say: data => listeners.slice().forEach(fn => fn({ origin: "http://localhost", data })),
    listeners
  };
}

beforeEach(() => {
  localStorage.clear();
  state.data = { ...EMPTY };
  state.account = { ...SIGNED_OUT };
  state.sync = { active: false, busy: false, error: "", conflicts: [], savedAt: null, adoption: null };
  globalThis.fetch = vi.fn(() =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(state.account) })
  );
});

describe("Anmelden ohne Seitenwechsel", () => {
  it("öffnet ein eigenes Fenster und lässt die Seite stehen", async () => {
    const view = fakeView();
    const running = beginSignIn("/aufnahme/quelle", view);
    await flushPromises();

    const [url] = view.open.mock.calls[0];
    expect(url).toContain("/auth/login");
    // Das Fenster landet auf der Abschlussseite, nicht auf der Seite, von der
    // aus angemeldet wurde -- die steht ja noch.
    expect(decodeURIComponent(url)).toContain(`ziel=${DONE_PATH}`);
    expect(view.location.assign).not.toHaveBeenCalled();

    state.account = { ...SIGNED };
    view.say(SIGNED_IN);
    expect(await running).toBe(true);
  });

  it("fällt auf den alten Weg zurück, wenn das Fenster verweigert wird", async () => {
    // Ein Knopf, der nichts tut, ist schlimmer als ein Seitenwechsel.
    const view = fakeView({ popup: null });

    expect(await beginSignIn("/grundstueck/7", view)).toBe(false);
    expect(view.location.assign).toHaveBeenCalledTimes(1);
    // Und zurück geht es dorthin, wo geklickt wurde.
    expect(decodeURIComponent(view.location.assign.mock.calls[0][0])).toContain("ziel=/grundstueck/7");
  });

  it("fragt den Server, nicht die Nachricht", async () => {
    // Ein von Hand geschlossenes Fenster meldet nichts. Wer sich darauf
    // verließe, hielte eine gelungene Anmeldung für einen Abbruch.
    const popup = { closed: false };
    const view = fakeView({ popup });
    const running = beginSignIn("/", view);
    await flushPromises();

    state.account = { ...SIGNED };
    popup.closed = true;

    expect(await running).toBe(true);
  });

  it("hört auf keine Nachricht von woanders", async () => {
    const view = fakeView();
    let done = false;
    beginSignIn("/", view).then(() => { done = true; });
    await flushPromises();

    view.listeners.slice().forEach(fn => fn({ origin: "https://boese.example", data: SIGNED_IN }));
    await flushPromises();

    expect(done).toBe(false);
  });

  it("räumt den Zuhörer weg, wenn es vorbei ist", async () => {
    const view = fakeView();
    const running = beginSignIn("/", view);
    await flushPromises();
    view.say(SIGNED_IN);
    await running;

    expect(view.listeners).toHaveLength(0);
  });
});

describe("Die Abschlussseite", () => {
  it("meldet sich beim öffnenden Fenster und schließt sich", () => {
    const opener = { closed: false, postMessage: vi.fn() };
    const target = { opener, location: { origin: "http://localhost" }, close: vi.fn() };

    expect(reportSignedIn(target)).toBe(true);
    expect(opener.postMessage).toHaveBeenCalledWith(SIGNED_IN, "http://localhost");
    expect(target.close).toHaveBeenCalled();
  });

  it("sagt Bescheid, wenn es niemanden zu benachrichtigen gibt", () => {
    // Ein Lesezeichen auf diese Adresse, oder ein Browser, der aus dem
    // Fenster einen Reiter gemacht hat: dann ist hier eine Sackgasse, wenn
    // die Seite nichts anbietet.
    const target = { opener: null, location: { origin: "http://localhost" }, close: vi.fn() };

    expect(reportSignedIn(target)).toBe(false);
    expect(target.close).not.toHaveBeenCalled();
  });
});

describe("Der Knopf in der Kopfzeile", () => {
  it("navigiert nicht, sondern öffnet das Fenster", async () => {
    const opened = [];
    const original = window.open;
    // Sofort geschlossen: sonst liefe der Wächter aus signIn.js über das Ende
    // dieses Tests hinaus weiter.
    window.open = (...args) => {
      opened.push(args);
      return { closed: true };
    };
    try {
      const router = testRouter("/");
      await router.isReady();
      const app = mountWithRouter(App, { router });
      await flushPromises();

      const link = app.findAll("a.btn").find(a => a.text() === "Anmelden");
      // Der href bleibt am Element: Mittelklick und „Link öffnen in…" sollen
      // weiter funktionieren, abgefangen wird nur der gewöhnliche Klick.
      expect(link.attributes("href")).toContain("/auth/login");
      await link.trigger("click");
      await flushPromises();

      expect(opened).toHaveLength(1);
      await new Promise(resolve => setTimeout(resolve, 450));
      await flushPromises();
      app.unmount();
    } finally {
      window.open = original;
    }
  });
});
