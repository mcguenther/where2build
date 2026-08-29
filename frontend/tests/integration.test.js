/**
 * Against the running backend and the real services behind it.
 *
 * These are the tests that would have caught a wrong endpoint, a changed schema
 * or a portal that started blocking us — none of which a fixture can notice.
 * They are deliberately kept out of `npm test`: run them with
 * `npm run test:integration` while the backend is up.
 *
 * Skipped, loudly, when the backend is not reachable.
 */
import { describe, it, expect, beforeAll } from "vitest";
import { plotAusKataster } from "../src/lib/plots.js";
import { haustypAusAntwort } from "../src/lib/houseTypes.js";
import { polygonArea, buildableArea, distanceToBoundary } from "../src/lib/geometry.js";

const BASIS = process.env.W2B_API ?? "http://127.0.0.1:8000/api";
let erreichbar = false;
let zustand = null;

const post = async (pfad, koerper) => {
  const r = await fetch(BASIS + pfad, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(koerper)
  });
  return { status: r.status, koerper: await r.json().catch(() => null) };
};
const get = async pfad => {
  const r = await fetch(BASIS + pfad);
  return { status: r.status, koerper: await r.json().catch(() => null) };
};
const dienst = name => zustand?.dienste?.find(d => d.name === name)?.konfiguriert === true;

beforeAll(async () => {
  try {
    const r = await fetch(`${BASIS}/health`, { signal: AbortSignal.timeout(4000) });
    erreichbar = r.ok;
    zustand = await r.json();
  } catch {
    erreichbar = false;
  }
  if (!erreichbar) console.warn(`\n  Backend unter ${BASIS} nicht erreichbar — Integrationstests übersprungen.\n`);
});

describe.runIf(!process.env.W2B_SKIP_INTEGRATION)("Kataster, live", () => {
  it("löst ein Flurstück über Gemarkung und Nummer auf", async ({ skip }) => {
    if (!erreichbar) skip();
    const { status, koerper } = await post("/parcels/resolve", { gemarkung: "Liebertwolkwitz", flurstuecksnummer: "85/1" });
    expect(status, JSON.stringify(koerper)).toBe(200);
    const plot = plotAusKataster(koerper);
    expect(plot.gemarkung).toBe("Liebertwolkwitz");
    expect(plot.flurstuecke).toContain("85/1");
    expect(plot.flaecheAmtlich).toBeGreaterThan(0);
  });

  it("liefert Geometrie, die in Sachsen liegt", async ({ skip }) => {
    if (!erreichbar) skip();
    const { koerper } = await post("/parcels/resolve", { lat: 51.28291, lon: 12.4628 });
    const plot = plotAusKataster(koerper);
    expect(plot.anker.lat).toBeGreaterThan(50.1);
    expect(plot.anker.lat).toBeLessThan(51.7);
    expect(plot.anker.lon).toBeGreaterThan(11.8);
    expect(plot.anker.lon).toBeLessThan(15.1);
  });

  it("amtliche und gerechnete Fläche liegen nah beieinander, sind aber nicht gleich", async ({ skip }) => {
    if (!erreichbar) skip();
    const { koerper } = await post("/parcels/resolve", { gemarkung: "Liebertwolkwitz", flurstuecksnummer: "85/1" });
    const plot = plotAusKataster(koerper);
    const gerechnet = polygonArea(plot.polygon);
    const abweichung = Math.abs(plot.flaecheAmtlich - gerechnet);
    expect(abweichung).toBeGreaterThan(0);
    expect(abweichung / plot.flaecheAmtlich).toBeLessThan(0.02);
  });

  it("das Bebauungsfenster hält auch am echten Umriss den Abstand ein", async ({ skip }) => {
    if (!erreichbar) skip();
    const { koerper } = await post("/parcels/resolve", { gemarkung: "Liebertwolkwitz", flurstuecksnummer: "85/1" });
    const plot = plotAusKataster(koerper);
    const fenster = buildableArea(plot.polygon, plot.tiefen);
    expect(fenster.length).toBeGreaterThan(2);
    fenster.forEach(p => expect(distanceToBoundary(p, plot.polygon)).toBeGreaterThanOrEqual(3 - 1e-6));
  });

  it("nimmt auch die Schreibweise mit Buchstaben-Nenner an", async ({ skip }) => {
    if (!erreichbar) skip();
    const { status } = await post("/parcels/resolve", { gemarkung: "Liebertwolkwitz", flurstuecksnummer: "41/e" });
    expect([200, 404]).toContain(status);   // 404 ist zulässig, 422 wäre ein Parserfehler
  });

  it("antwortet auf Unsinn mit einer deutschen Meldung, nicht mit einem Stacktrace", async ({ skip }) => {
    if (!erreichbar) skip();
    const { status, koerper } = await post("/parcels/resolve", {});
    expect(status).toBeGreaterThanOrEqual(400);
    expect(JSON.stringify(koerper)).not.toMatch(/Traceback|File \"/);
    expect(JSON.stringify(koerper)).toMatch(/[äöüßA-Za-z]{6,}/);
  });
});

describe.runIf(!process.env.W2B_SKIP_INTEGRATION)("Seiten auslesen, live", () => {
  it("trennt bebaute Fläche und Wohnfläche auf einer echten Herstellerseite", async ({ skip }) => {
    if (!erreichbar || !dienst("llm")) skip();
    const { status, koerper } = await post("/housetypes/extract", {
      url: "https://www.elkhaus.de/einfamilienhaus/all-in-one-159/"
    });
    expect(status, JSON.stringify(koerper)).toBe(200);
    const typ = haustypAusAntwort(koerper);
    expect(typ.hersteller).toMatch(/ELK/i);
    expect(typ.bebauteFlaeche).toBeGreaterThan(30);
    expect(typ.bebauteFlaeche).toBeLessThan(400);
    // Der teuerste Fehler des Projekts wäre, hier die Wohnfläche zu bekommen.
    expect(typ.bebauteFlaeche).toBeLessThan(typ.wohnflaeche);
  }, 240000);

  it("gibt zurück, was gelesen wurde — und nicht irgendeinen anderen Haustyp", async ({ skip }) => {
    if (!erreichbar || !dienst("llm")) skip();
    const { koerper } = await post("/housetypes/extract", {
      url: "https://www.elkhaus.de/einfamilienhaus/all-in-one-159/"
    });
    const typ = haustypAusAntwort(koerper);
    expect(typ.name).toMatch(/159/);
    expect(typ.quelle).toContain("elkhaus.de");
  }, 240000);

  it("ruft immobilienscout24.de gar nicht erst ab und sagt, was stattdessen zu tun ist", async ({ skip }) => {
    if (!erreichbar) skip();
    const { status, koerper } = await post("/listings/extract", {
      url: "https://www.immobilienscout24.de/expose/110185322"
    });
    expect(status).toBeGreaterThanOrEqual(400);
    expect(koerper.detail).toMatch(/einfüg/i);
  });
});

describe.runIf(!process.env.W2B_SKIP_INTEGRATION)("Bodenrichtwert, live", () => {
  it("liefert einen Wert je Quadratmeter oder eine klare Absage", async ({ skip }) => {
    if (!erreichbar) skip();
    const { status, koerper } = await get("/landvalue?lat=51.3397&lon=12.3731");
    if (status === 200) {
      expect(koerper.euro_per_sqm).toBeGreaterThan(0);
      expect(koerper.euro_per_sqm).toBeLessThan(5000);
    } else {
      expect(koerper.detail).toBeTruthy();
      expect(JSON.stringify(koerper)).not.toMatch(/Traceback/);
    }
  });
});
