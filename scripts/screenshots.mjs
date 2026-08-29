/* Screenshots of every view, light and dark, plus a narrow viewport and the
 * print rendering. Runs against the built app on a static server — no manual
 * steps, so the images always match the current code. */
import { chromium } from "/opt/node22/lib/node_modules/playwright/index.mjs";
import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize } from "node:path";

const wurzel = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const dist = resolve(wurzel, "frontend/dist");
const ausgabe = resolve(wurzel, "docs/screenshots");
mkdirSync(ausgabe, { recursive: true });

const TYPEN = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css",
  ".woff2": "font/woff2", ".woff": "font/woff", ".svg": "image/svg+xml",
  ".png": "image/png", ".ico": "image/x-icon", ".webmanifest": "application/manifest+json" };

/* /api goes to the FastAPI backend when it happens to be running, so the
 * screenshots show the real integration rather than the fallback example. */
const server = createServer(async (req, res) => {
  const pfad = normalize(decodeURIComponent(new URL(req.url, "http://x").pathname)).replace(/^(\.\.[/\\])+/, "");
  if (pfad.startsWith("/api/")) {
    try {
      const antwort = await fetch(`http://127.0.0.1:8000${req.url}`, {
        method: req.method,
        headers: { "Content-Type": "application/json" },
        body: ["GET", "HEAD"].includes(req.method) ? undefined : await sammle(req)
      });
      res.writeHead(antwort.status, { "Content-Type": antwort.headers.get("content-type") || "application/json" });
      res.end(Buffer.from(await antwort.arrayBuffer()));
    } catch {
      res.writeHead(503, { "Content-Type": "application/json" }).end('{"detail":"Backend nicht erreichbar"}');
    }
    return;
  }
  let datei = join(dist, pfad === "/" ? "index.html" : pfad);
  try {
    const inhalt = await readFile(datei);
    res.writeHead(200, { "Content-Type": TYPEN[extname(datei)] || "application/octet-stream" });
    res.end(inhalt);
  } catch {
    res.writeHead(404).end("not found");
  }
});
await new Promise(r => server.listen(4173, r));

function sammle(req) {
  return new Promise(fertig => {
    const teile = [];
    req.on("data", t => teile.push(t));
    req.on("end", () => fertig(Buffer.concat(teile)));
  });
}
const adresse = "http://127.0.0.1:4173/";

const browser = await chromium.launch({
  // Software WebGL: the sandbox has no GPU, and MapLibre needs a context.
  args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"]
});

/* The basemap goes through our own /api/basemap proxy, like in production —
 * so a tile that never arrives is a real defect, not a sandbox quirk. */
let vektorkacheln = 0;
const kachelnZaehlen = seite =>
  seite.on("response", r => { if (/\/api\/basemap\/.*\.pbf/.test(r.url()) && r.status() < 400) vektorkacheln++; });

/* There is no example data any more: every screenshot needs a plot that was
 * really resolved through ALKIS first. This is the app's own add flow. */
async function grundstueckAnlegen(seite) {
  await seite.click(".seitenkopf .knopf");
  await seite.getByText("Flurstück direkt").click();
  await seite.fill("#q-gemarkung", "Liebertwolkwitz");
  await seite.fill("#q-nummer", "85/1");
  await seite.getByRole("button", { name: "Nachschlagen" }).click();
  await seite.waitForSelector(".assistent__vorschau, .lageplan", { timeout: 60000 });
}

const gemacht = [];
const fehler = [];

async function schuss(seite, name, modus, zusatz = "") {
  await seite.waitForTimeout(340);
  // A layout that pushes the page sideways is a defect, and no screenshot shows it.
  const ueber = await seite.evaluate(() =>
    document.documentElement.scrollWidth - document.documentElement.clientWidth);
  if (ueber > 1) fehler.push(`${name}/${modus}: ${ueber}px waagerechter Überlauf`);
  const datei = `${name}-${modus}${zusatz}.png`;
  await seite.screenshot({ path: resolve(ausgabe, datei), fullPage: true });
  gemacht.push(datei);
}

for (const [modus, breite, hoehe, schmal] of [["hell", 1440, 1000, false], ["dunkel", 1440, 1000, false], ["dunkel", 402, 900, true]]) {
  const ctx = await browser.newContext({ viewport: { width: breite, height: hoehe }, deviceScaleFactor: 2 });
  const seite = await ctx.newPage();
  kachelnZaehlen(seite);
  seite.on("pageerror", e => fehler.push(`${modus}/${breite}: ${e.message}`));
  const erwartet = t => /Failed to load resource/.test(t);   // /api/* 404 when the backend is down — the documented fallback
  seite.on("console", m => { if (m.type() === "error" && !erwartet(m.text())) fehler.push(`${modus}/${breite}: ${m.text()}`); });
  await seite.goto(adresse, { waitUntil: "load" });
  await seite.evaluate(() => document.fonts.ready);
  await seite.click(`.darstellung button:nth-child(${modus === "hell" ? 1 : 2})`);
  await seite.waitForTimeout(200);

  // The empty state is a real state and worth a picture: this is what the app
  // looks like before anything has been resolved.
  await schuss(seite, "uebersicht-leer", modus, schmal ? "-schmal" : "");

  await seite.click(".seitenkopf .knopf");                      // Grundstück hinzufügen
  await schuss(seite, "assistent-1", modus, schmal ? "-schmal" : "");
  await seite.getByText("Flurstück direkt").click();
  await seite.fill("#q-gemarkung", "Liebertwolkwitz");
  await seite.fill("#q-nummer", "85/1");
  await schuss(seite, "assistent-2", modus, schmal ? "-schmal" : "");
  await seite.getByRole("button", { name: "Nachschlagen" }).click();
  await seite.waitForSelector(".lageplan", { timeout: 60000 });
  await schuss(seite, "assistent-3", modus, schmal ? "-schmal" : "");
  await seite.getByRole("button", { name: "Passt" }).click();
  await schuss(seite, "assistent-4", modus, schmal ? "-schmal" : "");
  await seite.getByRole("button", { name: "Anlegen und öffnen" }).click();

  await seite.waitForTimeout(6000);                             // Kacheln laden lassen
  await schuss(seite, "grundstueck", modus, schmal ? "-schmal" : "");
  if (!schmal) {
    await seite.getByRole("button", { name: "Luftbild" }).click();
    await seite.waitForTimeout(4000);
    await schuss(seite, "grundstueck-luftbild", modus);
    await seite.getByRole("button", { name: "Karte" }).click();
    await seite.waitForTimeout(2000);
  }
  await seite.click(".krume button");

  await seite.click('.orte button:nth-child(2)');               // Haustypen
  await schuss(seite, "haustypen", modus, schmal ? "-schmal" : "");
  if (!schmal) {
    // A destination, looked up for real: the picker is the point here, because
    // this geocoder answers "Am Kirschberg" with Bavaria as readily as Saxony.
    await seite.click('.orte button:nth-child(3)');             // Ziele
    await seite.getByRole("button", { name: /Ziel hinzufügen|Erstes Ziel anlegen/ }).first().click();
    const felder = await seite.locator("input[type=text]").all();
    await felder[0].fill("Bahnhof");
    await felder[1].fill("Bahnhof Wurzen");
    await seite.getByRole("button", { name: "Nachschlagen" }).click();
    await seite.waitForSelector(".trefferliste__wahl", { timeout: 60000 });
    await schuss(seite, "ziele-treffer", modus);
    await seite.locator(".trefferliste__wahl").first().click();
    await schuss(seite, "ziele", modus);

    // And the routes that follow from it, drawn from the geometry MOTIS sends.
    await seite.click('.orte button:nth-child(1)');
    await seite.click(".karte .knopf");
    await seite.getByRole("button", { name: "Wege berechnen" }).click();
    await seite.waitForSelector(".weg-karte polyline", { timeout: 60000 });
    await seite.waitForTimeout(600);
    await schuss(seite, "grundstueck-wege", modus);
    await seite.click(".krume button");

    await seite.click('.orte button:nth-child(4)');             // Daten
    await schuss(seite, "daten", modus);
  }
  await ctx.close();
}

/* The print rendering, as the browser would lay it out on paper. */
const ctx = await browser.newContext({ viewport: { width: 1240, height: 1754 }, deviceScaleFactor: 2 });
const seite = await ctx.newPage();
kachelnZaehlen(seite);
await seite.goto(adresse, { waitUntil: "load" });
await seite.evaluate(() => document.fonts.ready);
await grundstueckAnlegen(seite);
await seite.getByRole("button", { name: "Passt" }).click();
await seite.getByRole("button", { name: "Anlegen und öffnen" }).click();
await seite.waitForTimeout(6000);
await seite.emulateMedia({ media: "print" });
await seite.waitForTimeout(300);
await seite.screenshot({ path: resolve(ausgabe, "grundstueck-druck.png"), fullPage: true });
gemacht.push("grundstueck-druck.png");
await ctx.close();

await browser.close();
server.close();

// A blank basemap is the defect this project spent the longest on: MapLibre
// asks for no tile at all when its worker is missing, and says nothing.
if (!vektorkacheln) {
  fehler.push("Keine einzige Vektorkachel geladen — der Kartenhintergrund ist blind.");
}

if (fehler.length) {
  console.error("Skriptfehler:\n  " + [...new Set(fehler)].join("\n  "));
  process.exit(1);
}
console.log(`${gemacht.length} Aufnahmen in docs/screenshots/:\n  ` + gemacht.join("\n  "));
