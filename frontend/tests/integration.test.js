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
import { plotFromCadastre } from "../src/lib/plots.js";
import { houseTypeFromResponse } from "../src/lib/houseTypes.js";
import { polygonArea, buildableArea, distanceToBoundary } from "../src/lib/geometry.js";

const BASE = process.env.W2B_API ?? "http://127.0.0.1:8000/api";
let reachable = false;
let health = null;

const post = async (path, payload) => {
  const r = await fetch(BASE + path, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload)
  });
  return { status: r.status, body: await r.json().catch(() => null) };
};
const get = async path => {
  const r = await fetch(BASE + path);
  return { status: r.status, body: await r.json().catch(() => null) };
};
/** `dienste` and `konfiguriert` are the health endpoint's own field names. */
const configured = name => health?.dienste?.find(d => d.name === name)?.konfiguriert === true;

beforeAll(async () => {
  try {
    const r = await fetch(`${BASE}/health`, { signal: AbortSignal.timeout(4000) });
    reachable = r.ok;
    health = await r.json();
  } catch {
    reachable = false;
  }
  if (!reachable) console.warn(`\n  Backend unter ${BASE} nicht erreichbar — Integrationstests übersprungen.\n`);
});

describe.runIf(!process.env.W2B_SKIP_INTEGRATION)("Kataster, live", () => {
  it("löst ein Flurstück über Gemarkung und Nummer auf", async ({ skip }) => {
    if (!reachable) skip();
    const { status, body } = await post("/parcels/resolve", { gemarkung: "Liebertwolkwitz", flurstuecksnummer: "85/1" });
    expect(status, JSON.stringify(body)).toBe(200);
    const plot = plotFromCadastre(body);
    expect(plot.gemarkung).toBe("Liebertwolkwitz");
    expect(plot.flurstuecke).toContain("85/1");
    expect(plot.officialArea).toBeGreaterThan(0);
  });

  it("liefert Geometrie, die in Sachsen liegt", async ({ skip }) => {
    if (!reachable) skip();
    const { body } = await post("/parcels/resolve", { lat: 51.28291, lon: 12.4628 });
    const plot = plotFromCadastre(body);
    expect(plot.anchor.lat).toBeGreaterThan(50.1);
    expect(plot.anchor.lat).toBeLessThan(51.7);
    expect(plot.anchor.lon).toBeGreaterThan(11.8);
    expect(plot.anchor.lon).toBeLessThan(15.1);
  });

  it("amtliche und computede Fläche liegen nah beieinander, sind aber nicht gleich", async ({ skip }) => {
    if (!reachable) skip();
    const { body } = await post("/parcels/resolve", { gemarkung: "Liebertwolkwitz", flurstuecksnummer: "85/1" });
    const plot = plotFromCadastre(body);
    const computed = polygonArea(plot.polygon);
    const difference = Math.abs(plot.officialArea - computed);
    expect(difference).toBeGreaterThan(0);
    expect(difference / plot.officialArea).toBeLessThan(0.02);
  });

  it("das Bebauungsfenster hält auch am echten Umriss den Abstand ein", async ({ skip }) => {
    if (!reachable) skip();
    const { body } = await post("/parcels/resolve", { gemarkung: "Liebertwolkwitz", flurstuecksnummer: "85/1" });
    const plot = plotFromCadastre(body);
    const envelope = buildableArea(plot.polygon, plot.setbacks);
    expect(envelope.length).toBeGreaterThan(2);
    envelope.forEach(p => expect(distanceToBoundary(p, plot.polygon)).toBeGreaterThanOrEqual(3 - 1e-6));
  });

  it("nimmt auch die Schreibweise mit Buchstaben-Nenner an", async ({ skip }) => {
    if (!reachable) skip();
    const { status } = await post("/parcels/resolve", { gemarkung: "Liebertwolkwitz", flurstuecksnummer: "41/e" });
    expect([200, 404]).toContain(status);   // 404 ist zulässig, 422 wäre ein Parserfehler
  });

  it("antwortet auf Unsinn mit einer deutschen Meldung, nicht mit einem Stacktrace", async ({ skip }) => {
    if (!reachable) skip();
    const { status, body } = await post("/parcels/resolve", {});
    expect(status).toBeGreaterThanOrEqual(400);
    expect(JSON.stringify(body)).not.toMatch(/Traceback|File \"/);
    expect(JSON.stringify(body)).toMatch(/[äöüßA-Za-z]{6,}/);
  });
});

describe.runIf(!process.env.W2B_SKIP_INTEGRATION)("Seiten auslesen, live", () => {
  it("trennt bebaute Fläche und Wohnfläche auf einer echten Herstellerseite", async ({ skip }) => {
    if (!reachable || !configured("llm")) skip();
    const { status, body } = await post("/housetypes/extract", {
      url: "https://www.elkhaus.de/einfamilienhaus/all-in-one-159/"
    });
    expect(status, JSON.stringify(body)).toBe(200);
    const houseType = houseTypeFromResponse(body);
    expect(houseType.manufacturer).toMatch(/ELK/i);
    expect(houseType.builtArea).toBeGreaterThan(30);
    expect(houseType.builtArea).toBeLessThan(400);
    // Der teuerste Fehler des Projekts wäre, hier die Wohnfläche zu bekommen.
    expect(houseType.builtArea).toBeLessThan(houseType.livingArea);
  }, 240000);

  it("gibt zurück, was gelesen wurde — und nicht irgendeinen anderen Haustyp", async ({ skip }) => {
    if (!reachable || !configured("llm")) skip();
    const { body } = await post("/housetypes/extract", {
      url: "https://www.elkhaus.de/einfamilienhaus/all-in-one-159/"
    });
    const houseType = houseTypeFromResponse(body);
    expect(houseType.name).toMatch(/159/);
    expect(houseType.source).toContain("elkhaus.de");
  }, 240000);

  it("ruft immobilienscout24.de gar nicht erst ab und sagt, was stattdessen zu tun ist", async ({ skip }) => {
    if (!reachable) skip();
    const { status, body } = await post("/listings/extract", {
      url: "https://www.immobilienscout24.de/expose/110185322"
    });
    expect(status).toBeGreaterThanOrEqual(400);
    expect(body.detail).toMatch(/einfüg/i);
  });
});

describe.runIf(!process.env.W2B_SKIP_INTEGRATION)("Bodenrichtwert, live", () => {
  it("liefert einen Wert je Quadratmeter oder eine klare Absage", async ({ skip }) => {
    if (!reachable) skip();
    const { status, body } = await get("/landvalue?lat=51.3397&lon=12.3731");
    if (status === 200) {
      expect(body.euro_per_sqm).toBeGreaterThan(0);
      expect(body.euro_per_sqm).toBeLessThan(5000);
    } else {
      expect(body.detail).toBeTruthy();
      expect(JSON.stringify(body)).not.toMatch(/Traceback/);
    }
  });
});
