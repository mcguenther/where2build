/**
 * The administration area.
 *
 * Three things are worth pinning down here, and none of them is a layout.
 *
 * **The way in is drawn, never granted.** The menu entry and the page follow
 * `verwalter` out of `/api/auth/me`; every request behind them is checked on
 * the server. So the test asserts that the entry appears and disappears with
 * the flag, and that the page says *which* of the three refusals applies
 * rather than redirecting somebody away from the explanation.
 *
 * **The red button needs both confirmations.** The second one is a sentence
 * typed back, and the button stays disabled until it matches — a dialog that
 * can be clicked through twice is one dialog.
 *
 * **Nothing is invented.** An empty period says so; it never draws a line at
 * zero, and a mean over no calls is „—“ and not „0 ms“.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { flushPromises } from "@vue/test-utils";
import App from "../src/App.vue";
import AdminView from "../src/views/AdminView.vue";
import AdminStats from "../src/components/admin/AdminStats.vue";
import AdminAccounts from "../src/components/admin/AdminAccounts.vue";
import AdminOperations from "../src/components/admin/AdminOperations.vue";
import AdminDanger from "../src/components/admin/AdminDanger.vue";
import UsageChart from "../src/components/admin/UsageChart.vue";
import { state } from "../src/lib/store.js";
import { realState, mountWithRouter } from "./helpers.js";

const ok = body => ({ ok: true, status: 200, json: () => Promise.resolve(body) });
const fails = (status, detail) => ({
  ok: false,
  status,
  json: () => Promise.resolve({ detail })
});

const STATISTICS = {
  von: "2026-09-17T08:00:00Z",
  bis: "2026-09-18T08:00:00Z",
  raster: "stunde",
  zeitreihe: [
    { zeit: "2026-09-18T06:00:00Z", anfragen: 12, fehler: 0, limitiert: 0, dauer_ms: 2400, tokens_ein: 0, tokens_aus: 0 },
    { zeit: "2026-09-18T07:00:00Z", anfragen: 8, fehler: 3, limitiert: 1, dauer_ms: 3200, tokens_ein: 0, tokens_aus: 0 }
  ],
  nach_dienst: [
    { bereich: "dienst", dienst: "ALKIS", anfragen: 15, fehler: 3, limitiert: 0, dauer_ms: 4500, tokens_ein: 0, tokens_aus: 0, kosten_eur: null },
    { bereich: "modell", dienst: "test/model", anfragen: 5, fehler: 0, limitiert: 1, dauer_ms: 1100, tokens_ein: 900, tokens_aus: 300, kosten_eur: 0.0012 },
    { bereich: "suche", dienst: "bestaetigt", anfragen: 6, fehler: 0, limitiert: 0, dauer_ms: 0, tokens_ein: 0, tokens_aus: 0, kosten_eur: null },
    { bereich: "suche", dienst: "erfolglos", anfragen: 2, fehler: 0, limitiert: 0, dauer_ms: 0, tokens_ein: 0, tokens_aus: 0, kosten_eur: null }
  ],
  summe: {
    anfragen: 20, fehler: 3, limitiert: 1, dauer_ms: 5600,
    tokens_ein: 900, tokens_aus: 300, kosten_eur: 0.0012
  },
  vergleich: null,
  vergleich_summe: null,
  preise: {
    vorhanden: true,
    stand: "2026-09-18T07:00:00Z",
    usd_je_eur: 1.1481,
    kurs_stand: "2026-09-17",
    quellen: {},
    modelle: 445,
    hinweis: null
  }
};

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
  state.account = {
    eingerichtet: true,
    angemeldet: true,
    name: "Erika Musterfrau",
    kennung: "8f1c47110000000000000000000000ab",
    verwalter: true
  };
  state.sync = { active: true, busy: false, error: "", conflicts: [], savedAt: null, adoption: null };
  globalThis.fetch = serve({});
});

afterEach(() => { vi.restoreAllMocks(); });

describe("the way in", () => {
  it("shows „Verwaltung“ in the header only for an administrator", async () => {
    globalThis.fetch = serve({ "/auth/me": ok({ ...state.account }) });
    const header = mountWithRouter(App);
    await flushPromises();

    expect(header.text()).toContain("Verwaltung");

    state.account = { ...state.account, verwalter: false };
    await flushPromises();
    expect(header.find(".account__admin").exists()).toBe(false);
  });

  it("says which refusal applies instead of sending somebody away", async () => {
    state.account = { ...state.account, verwalter: false };
    globalThis.fetch = serve({ "/auth/me": ok({ ...state.account }) });

    const view = mountWithRouter(AdminView, { path: "/verwaltung" });
    await flushPromises();

    // Still on the page, and told why — a redirect would leave somebody
    // looking at the start page with no idea what happened.
    expect(view.text()).toContain("kein Verwalter");
    expect(view.text()).toContain(state.account.kennung);
  });

  it("offers to sign in when nobody is", async () => {
    state.account = { eingerichtet: true, angemeldet: false, name: null, kennung: null, verwalter: false };
    globalThis.fetch = serve({ "/auth/me": ok({ ...state.account }) });

    const view = mountWithRouter(AdminView, { path: "/verwaltung" });
    await flushPromises();

    expect(view.text()).toContain("nur angemeldet");
    expect(view.find("a.btn").exists()).toBe(true);
  });

  it("opens the area it was asked for, and falls back to the overview", async () => {
    globalThis.fetch = serve({ "/verwaltung/dienste": ok({ caches: [], cache_bytes: 0, cache_grenze_bytes: 1, kontingent_dienste: 600, kontingent_kacheln: 6000, kontingent_fenster_s: 3600, kontingent_aktiv: true, sperre_ab: 300, sperre_fenster_s: 300, sperre_dauer_min: 60, aufbewahrung_tage: 90 }) });

    const view = mountWithRouter(AdminView, { path: "/verwaltung/dienste", props: { bereich: "dienste" } });
    await flushPromises();
    expect(view.text()).toContain("Zwischenspeicher");

    const unknown = mountWithRouter(AdminView, { path: "/verwaltung/quatsch", props: { bereich: "quatsch" } });
    await flushPromises();
    expect(unknown.vm.current).toBe("uebersicht");
  });
});

describe("the statistics", () => {
  it("shows the sums and the services, and never a mean over nothing", async () => {
    globalThis.fetch = serve({ "/verwaltung/statistik": ok(STATISTICS) });

    const view = mountWithRouter(AdminStats);
    await flushPromises();

    expect(view.text()).toContain("20");
    const rows = view.findAll("tbody tr").map(row => row.text());
    expect(rows[0]).toContain("ALKIS");
    // 4500 ms over 15 calls.
    expect(rows[0]).toContain("300 ms");
    expect(view.text()).toContain("Modell");
  });

  it("says a period is empty rather than drawing a line at zero", async () => {
    const chart = mountWithRouter(UsageChart, { props: { points: [], raster: "stunde" } });

    expect(chart.text()).toContain("nichts gezählt");
    expect(chart.find("svg").exists()).toBe(false);
  });

  it("draws one bar per point, with the failures stacked on top", async () => {
    const chart = mountWithRouter(UsageChart, {
      props: { points: STATISTICS.zeitreihe, raster: "stunde" }
    });

    expect(chart.findAll("path.chart__bar--ok")).toHaveLength(2);
    // Only the second hour had failures.
    expect(chart.findAll("path.chart__bar--fail")).toHaveLength(1);
  });

  it("gives the chart every hour of the period, including the quiet ones", async () => {
    const { fillSeries } = await import("../src/lib/period.js");
    const from = new Date("2026-09-18T06:00:00");
    const to = new Date("2026-09-18T09:30:00");

    const slots = fillSeries(
      [{ zeit: new Date("2026-09-18T08:00:00").toISOString(), anfragen: 7, fehler: 1 }],
      from,
      to,
      "stunde"
    );

    // Four hours, and the gap is a zero rather than a closed-up gap: without
    // it the chart would stand yesterday's bar next to this morning's and show
    // a busy stretch that never happened.
    expect(slots).toHaveLength(4);
    expect(slots.map(slot => slot.anfragen)).toEqual([0, 0, 7, 0]);
  });

  it("carries the period into the request", async () => {
    const calls = [];
    globalThis.fetch = vi.fn(path => {
      calls.push(String(path));
      return Promise.resolve(ok(STATISTICS));
    });

    const view = mountWithRouter(AdminStats);
    await flushPromises();
    await view.findAll("button")[1].trigger("click");   // 7 Tage
    await flushPromises();

    expect(calls[0]).toContain("raster=stunde");
    expect(calls[1]).toContain("raster=tag");
    expect(calls[1]).toContain("von=");
    expect(calls[1]).toContain("bis=");
  });
});

describe("what the numbers must not claim", () => {
  it("shows a dash where no price is known, never 0,00 €", async () => {
    globalThis.fetch = serve({ "/verwaltung/statistik": ok(STATISTICS) });

    const view = mountWithRouter(AdminStats);
    await flushPromises();

    const rows = view.findAll("tbody tr").map(row => row.text());
    const cadastre = rows.find(row => row.includes("ALKIS"));
    const model = rows.find(row => row.includes("test/model"));
    expect(cadastre).toContain("—");
    expect(cadastre).not.toContain("0,00 €");
    expect(model).toContain("€");
  });

  it("reads the search outcomes out of the same numbers", async () => {
    globalThis.fetch = serve({ "/verwaltung/statistik": ok(STATISTICS) });

    const view = mountWithRouter(AdminStats);
    await flushPromises();

    // Six of eight searches were settled by an official statement.
    expect(view.text()).toContain("Suchergebnisse");
    expect(view.text()).toContain("Bestätigt");
    expect(view.text()).toContain("75 %");
  });

  it("asks for the earlier period only when the switch is on", async () => {
    const calls = [];
    globalThis.fetch = vi.fn(path => {
      calls.push(String(path));
      return Promise.resolve(ok(STATISTICS));
    });

    const view = mountWithRouter(AdminStats);
    await flushPromises();
    expect(calls[0]).toContain("vergleich=false");

    await view.find("input[type=checkbox]").setValue(true);
    await flushPromises();
    expect(calls[calls.length - 1]).toContain("vergleich=true");
  });

  it("lays the earlier period over the bars on one scale", async () => {
    const points = [
      { zeit: "2026-09-18T06:00:00Z", anfragen: 4, fehler: 0 },
      { zeit: "2026-09-18T07:00:00Z", anfragen: 6, fehler: 0 }
    ];
    const before = [
      { zeit: "2026-09-17T06:00:00Z", anfragen: 40, fehler: 0 },
      { zeit: "2026-09-17T07:00:00Z", anfragen: 20, fehler: 0 }
    ];

    const chart = mountWithRouter(UsageChart, { props: { points, vergleich: before } });

    expect(chart.find("polyline.chart__before").exists()).toBe(true);
    // One scale for both: the taller of the two sets the maximum, so today's
    // four calls do not look like a busy day.
    expect(chart.vm.max).toBe(40);
  });
});

describe("a deployment with many accounts", () => {
  const PAGE = {
    von: "2026-09-17T08:00:00Z",
    bis: "2026-09-18T08:00:00Z",
    gesamt: 431,
    offset: 0,
    limit: 25,
    konten: [
      {
        kennung: "8f1c47110000000000000000000000ab",
        anzeigename: "Erika Musterfrau",
        angelegt: "2026-09-01T10:00:00Z",
        ist_admin: false,
        grundstuecke: 2,
        freigaben: 0,
        bytes: 4096,
        anfragen: 120,
        fehler: 1,
        tokens_ein: 0,
        tokens_aus: 0,
        zuletzt_aktiv: "2026-09-18T07:00:00Z",
        gesperrt_bis: null,
        gesperrt_grund: null,
        gesperrt_automatisch: false
      }
    ]
  };

  it("asks for one page and says where in the list it is", async () => {
    const calls = [];
    globalThis.fetch = vi.fn(path => {
      calls.push(String(path));
      return Promise.resolve(ok(PAGE));
    });

    const view = mountWithRouter(AdminAccounts);
    await flushPromises();

    expect(calls[0]).toContain("limit=25");
    expect(view.text()).toContain("1–25 von 431");

    await view.findAll("button").find(button => button.text() === "Weiter").trigger("click");
    await flushPromises();
    expect(calls[calls.length - 1]).toContain("offset=25");
  });

  it("starts a new search at the top of the list", async () => {
    const calls = [];
    globalThis.fetch = vi.fn(path => {
      calls.push(String(path));
      return Promise.resolve(ok({ ...PAGE, offset: 25 }));
    });

    const view = mountWithRouter(AdminAccounts);
    await flushPromises();
    view.vm.offset = 50;
    await view.find("input[type=search]").setValue("Musterfrau");
    await view.findAll("button").find(button => button.text() === "Suchen").trigger("click");
    await flushPromises();

    const last = calls[calls.length - 1];
    expect(last).toContain("offset=0");
    expect(last).toContain("suche=Musterfrau");
  });
});

describe("the announcement", () => {
  it("stands over every page while it is switched on", async () => {
    state.account = { ...state.account, verwalter: false };
    globalThis.fetch = serve({
      "/ansage": ok({ text: "Wartung heute ab 18 Uhr.", art: "warnung", sichtbar: true }),
      "/auth/me": ok({ ...state.account })
    });

    const app = mountWithRouter(App);
    await flushPromises();

    expect(app.text()).toContain("Wartung heute ab 18 Uhr.");
    expect(app.find(".ansage--warnung").exists()).toBe(true);
  });

  it("shows nothing at all when there is nothing to say", async () => {
    globalThis.fetch = serve({ "/ansage": ok({ text: "", art: "hinweis", sichtbar: false }) });

    const app = mountWithRouter(App);
    await flushPromises();

    expect(app.find(".ansage").exists()).toBe(false);
  });
});

describe("the recurring jobs", () => {
  it("says when nothing is there to pick a run up", async () => {
    globalThis.fetch = serve({
      "/verwaltung/jobs": ok({
        jobs: [
          {
            name: "poi-index",
            zeitplan: "20 4 1 */3 *",
            warum: "Die Orte hinter /api/nearby.",
            befehl: ["python", "scripts/build_poi_index.py"],
            zuletzt: null,
            exit_code: null,
            dauer_s: null,
            laeuft: false,
            angefordert: null
          }
        ],
        scheduler_zuletzt: null,
        scheduler_laeuft: false,
        hinweis: "Zurzeit läuft kein Scheduler. Angeforderte Läufe bleiben liegen."
      }),
      "/verwaltung/dienste": ok({
        caches: [], cache_bytes: 0, cache_grenze_bytes: 100, kontingent_dienste: 600,
        kontingent_kacheln: 6000, kontingent_fenster_s: 3600, kontingent_aktiv: true,
        sperre_ab: 300, sperre_fenster_s: 300, sperre_dauer_min: 60, aufbewahrung_tage: 90
      }),
      "/verwaltung/ansage": ok({ text: "", art: "hinweis", sichtbar: false, bis: null }),
      "/health": ok({
        version: "0.1.0",
        dienste: [{ name: "alkis", konfiguriert: true, endpunkt: "https://…", hinweis: "Flurstücke." }]
      })
    });

    const view = mountWithRouter(AdminOperations);
    await flushPromises();

    expect(view.text()).toContain("kein Scheduler");
    expect(view.text()).toContain("poi-index");
    expect(view.text()).toContain("noch nie gelaufen");
  });
});

describe("the red button", () => {
  const prepared = { schluessel: "ein-schluessel", gueltig_bis: "2026-09-18T08:02:00Z", satz: "ALLES LÖSCHEN" };

  it("cannot be pressed before something is chosen", async () => {
    const view = mountWithRouter(AdminDanger);

    expect(view.find("button.btn--danger").attributes("disabled")).toBeDefined();
  });

  it("asks twice, and the second time for the sentence", async () => {
    const sent = [];
    globalThis.fetch = vi.fn((path, options) => {
      sent.push([String(path), options?.body]);
      if (String(path).includes("vorbereiten")) return Promise.resolve(ok(prepared));
      return Promise.resolve(ok({ geleert: { users: 2, plots: 5 } }));
    });

    const view = mountWithRouter(AdminDanger);
    await view.find("input[type=checkbox]").setValue(true);
    await view.find("button.btn--danger").trigger("click");
    await flushPromises();

    // Second stage: the button is there and refuses until the words match.
    expect(view.text()).toContain("Zweite Bestätigung");
    expect(view.find("button.btn--danger").attributes("disabled")).toBeDefined();

    await view.find("input[type=text]").setValue("löschen halt");
    expect(view.find("button.btn--danger").attributes("disabled")).toBeDefined();

    await view.find("input[type=text]").setValue("ALLES LÖSCHEN");
    expect(view.find("button.btn--danger").attributes("disabled")).toBeUndefined();

    await view.find("button.btn--danger").trigger("click");
    await flushPromises();

    expect(sent[0][0]).toContain("/verwaltung/datenbank/vorbereiten");
    expect(JSON.parse(sent[1][1])).toEqual({
      schluessel: "ein-schluessel",
      bestaetigung: "ALLES LÖSCHEN",
      umfang: ["konten"]
    });
    expect(view.text()).toContain("plots: 5");
  });

  it("starts over when the server refused the key", async () => {
    globalThis.fetch = vi.fn(path =>
      Promise.resolve(
        String(path).includes("vorbereiten")
          ? ok(prepared)
          : fails(400, "Diese Bestätigung ist abgelaufen.")
      )
    );

    const view = mountWithRouter(AdminDanger);
    await view.find("input[type=checkbox]").setValue(true);
    await view.find("button.btn--danger").trigger("click");
    await flushPromises();
    await view.find("input[type=text]").setValue("ALLES LÖSCHEN");
    await view.find("button.btn--danger").trigger("click");
    await flushPromises();

    expect(view.text()).toContain("abgelaufen");
    // A used key is used up, so the page is back at the first confirmation.
    expect(view.text()).not.toContain("Zweite Bestätigung");
  });
});
