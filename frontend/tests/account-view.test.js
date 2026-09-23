/**
 * The account page.
 *
 * It exists for one reason above the others: until it did, nothing could
 * remove the `users` row, and that row carries the display name the provider
 * granted. So the deletion is what is pinned down hardest here — that it asks
 * first, that it does not quietly throw away the browser's own work along with
 * the account, and that afterwards nobody is left signed in to something that
 * is gone.
 *
 * The other half is the disclosure. It has to be the whole of what is held, so
 * the test reads the fields rather than the headline.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { flushPromises } from "@vue/test-utils";
import AccountView from "../src/views/AccountView.vue";
import { state } from "../src/lib/store.js";
import { realState, mountWithRouter } from "./helpers.js";

const HELD = {
  anbieter: "https://auth.example.org",
  kennung: "f3d01e1d76062d58716a4fc940044dc6",
  anbieter_kennung: "8f1c-4711",
  anzeigename: "Erika Musterfrau",
  angelegt: "2026-09-01T10:00:00Z",
  grundstuecke: 2,
  groesse_bytes: 4096
};

const ok = body => ({ ok: true, status: 200, json: () => Promise.resolve(body) });
const fails = status => ({
  ok: false,
  status,
  json: () => Promise.resolve({ detail: `HTTP ${status}` })
});

/** Answer by path, so a test says what the server holds rather than what the
 *  component happens to call first. */
function serve(routes) {
  return vi.fn(path => {
    const match = Object.keys(routes).find(key => String(path).includes(key));
    return Promise.resolve(match ? routes[match] : ok({}));
  });
}

beforeEach(() => {
  localStorage.clear();
  state.data = realState();
  state.account = { eingerichtet: true, angemeldet: true, name: "Erika Musterfrau", kennung: "8f1c-4711" };
  state.sync = { active: true, busy: false, error: "", conflicts: [], savedAt: null, adoption: null };
  globalThis.fetch = serve({ "/account": ok(HELD) });
});

afterEach(() => {
  if (open_) { open_.unmount(); open_ = null; }
  vi.restoreAllMocks();
});

/* Die zuletzt geöffnete Seite, damit sie vor der nächsten abgebaut wird.
   Seit die Seite auf `state.account.angemeldet` hört, sieht eine liegen
   gebliebene Instanz die Zustandswechsel der folgenden Tests noch mit und
   holt dort ein Konto nach — was dann als Aufruf in einem Test auftaucht, der
   von dieser Seite gar nichts mehr wissen will. */
let open_ = null;

async function open() {
  if (open_) open_.unmount();
  open_ = mountWithRouter(AccountView, { path: "/konto" });
  await flushPromises();
  return open_;
}

describe("Kontoseite", () => {
  it("zeigt vollständig, was gespeichert ist", async () => {
    const view = await open();

    const text = view.text();
    expect(text).toContain("Erika Musterfrau");
    expect(text).toContain("https://auth.example.org");
    expect(text).toContain("8f1c-4711");
    expect(text).toContain("4.0 KiB");
    // Die Behauptung der Vollständigkeit steht daneben, also muss sie stimmen.
    expect(text).toContain("Das ist vollständig");
  });

  it("holt den Stand nach, wenn die Anmeldung erst nach dem Aufbau feststeht", async () => {
    // Beim direkten Aufruf von /konto ist `angemeldet` noch false, wenn diese
    // Seite entsteht — die Antwort auf „wer ist angemeldet" kommt später. Ohne
    // das Nachziehen blieb die Seite leer, ohne Fehler und ohne Hinweis.
    state.account = { eingerichtet: true, angemeldet: false, name: null, kennung: null };
    const view = await open();
    expect(view.text()).not.toContain("Erika Musterfrau");

    state.account = { eingerichtet: true, angemeldet: true, name: "Erika Musterfrau", kennung: "f3d0" };
    await flushPromises();

    expect(view.text()).toContain("Kennung dieses Kontos");
  });

  it("trennt die beiden Kennungen und sagt, welche der Betreiber braucht", async () => {
    // Beide hießen „Kennung", und die Seite zeigte nur die des Anbieters —
    // wer sie in ADMIN_ACCOUNTS eintrug, bekam keinen Zugang und keine
    // Erklärung dazu.
    const view = await open();

    const text = view.text();
    expect(text).toContain("Kennung beim Anbieter");
    expect(text).toContain("8f1c-4711");
    expect(text).toContain("Kennung dieses Kontos");
    expect(text).toContain("f3d01e1d76062d58716a4fc940044dc6");
    expect(text).toContain("ADMIN_ACCOUNTS");
  });

  it("sagt es, wenn der Anbieter keinen Namen mitgab", async () => {
    globalThis.fetch = serve({ "/account": ok({ ...HELD, anzeigename: null }) });
    const view = await open();

    expect(view.text()).toContain("vom Anbieter nicht mitgegeben");
  });

  it("nennt einen leeren Stand einen Zustand, keinen Fehler", async () => {
    // Die Zeile entsteht erst beim ersten Schreiben. Ein Konto voller Nullen
    // wäre eine Behauptung, die niemand gemacht hat.
    globalThis.fetch = serve({ "/account": fails(404) });
    const view = await open();

    expect(view.text()).toContain("Es ist noch nichts gespeichert");
    expect(view.find(".notice--error").exists()).toBe(false);
  });

  it("behandelt einen Betrieb ohne Serverspeicher nicht als Störung", async () => {
    globalThis.fetch = serve({ "/account": fails(503) });
    const view = await open();

    expect(view.find(".notice--error").exists()).toBe(false);
  });

  it("löscht erst nach Rückfrage", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    const view = await open();

    await view.findAll("button").find(b => b.text().includes("endgültig")).trigger("click");
    await flushPromises();

    expect(confirm).toHaveBeenCalled();
    const calls = globalThis.fetch.mock.calls.map(([path, options]) => `${options?.method ?? "GET"} ${path}`);
    expect(calls.some(call => call.startsWith("DELETE"))).toBe(false);
  });

  it("löscht das Konto und lässt den Stand in diesem Browser stehen", async () => {
    // Wer sein Konto löschen will, will nicht zwingend seine Arbeit wegwerfen.
    // Die beiden zu vermengen wäre eine böse Überraschung.
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const before = state.data.plots.length;
    expect(before).toBeGreaterThan(0);

    globalThis.fetch = serve({
      "/account": ok(HELD),
      "/auth/me": ok({ eingerichtet: true, angemeldet: false, name: null, kennung: null })
    });
    const view = await open();

    await view.findAll("button").find(b => b.text().includes("endgültig")).trigger("click");
    await flushPromises();

    const calls = globalThis.fetch.mock.calls.map(([path, options]) => `${options?.method ?? "GET"} ${path}`);
    expect(calls.some(call => call.startsWith("DELETE") && call.endsWith("/account"))).toBe(true);
    expect(state.data.plots.length).toBe(before);
  });

  it("bietet abgemeldet den Weg hinein statt einer leeren Seite", async () => {
    state.account = { eingerichtet: true, angemeldet: false, name: null, kennung: null };
    const view = await open();

    expect(view.find("a.btn").attributes("href")).toContain("/auth/login");
    // Und fragt gar nicht erst nach einem Konto, das es nicht gibt.
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it("sagt ohne Anbieter, dass es hier keine Konten gibt", async () => {
    state.account = { eingerichtet: false, angemeldet: false, name: null, kennung: null };
    const view = await open();

    expect(view.text()).toContain("keine Anmeldung eingerichtet");
    expect(view.find("a.btn").exists()).toBe(false);
  });
});
