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

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const dist = resolve(root, "frontend/dist");
const outDir = resolve(root, "docs/screenshots");
mkdirSync(outDir, { recursive: true });

const MIME = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css",
  ".woff2": "font/woff2", ".woff": "font/woff", ".svg": "image/svg+xml",
  ".png": "image/png", ".ico": "image/x-icon", ".webmanifest": "application/manifest+json" };

/* /api goes to the FastAPI backend when it happens to be running, so the
 * screenshots show the real integration rather than the fallback example. */
const server = createServer(async (req, res) => {
  const path_ = normalize(decodeURIComponent(new URL(req.url, "http://x").pathname)).replace(/^(\.\.[/\\])+/, "");
  if (path_.startsWith("/api/")) {
    try {
      const answer = await fetch(`http://127.0.0.1:8000${req.url}`, {
        method: req.method,
        headers: { "Content-Type": "application/json" },
        body: ["GET", "HEAD"].includes(req.method) ? undefined : await collect(req)
      });
      res.writeHead(answer.status, { "Content-Type": answer.headers.get("content-type") || "application/json" });
      res.end(Buffer.from(await answer.arrayBuffer()));
    } catch {
      res.writeHead(503, { "Content-Type": "application/json" }).end('{"detail":"Backend nicht erreichbar"}');
    }
    return;
  }
  const send = async file => {
    const content = await readFile(file);
    res.writeHead(200, { "Content-Type": MIME[extname(file)] || "application/octet-stream" });
    res.end(content);
  };
  const file = join(dist, path_ === "/" ? "index.html" : path_);
  try {
    await send(file);
  } catch {
    /* The app routes in history mode, so `/grundstueck/…` is a page, not a
     * file: every static host has to answer an unknown path with index.html or
     * a deep link 404s. A path that names a file extension stays a 404, so a
     * missing asset still shows up as one. */
    if (extname(file)) return void res.writeHead(404).end("not found");
    try {
      await send(join(dist, "index.html"));
    } catch {
      res.writeHead(404).end("not found");
    }
  }
});
await new Promise(r => server.listen(4173, r));

function collect(req) {
  return new Promise(done => {
    const parts = [];
    req.on("data", t => parts.push(t));
    req.on("end", () => done(Buffer.concat(parts)));
  });
}
const address = "http://127.0.0.1:4173/";

const browser = await chromium.launch({
  // Software WebGL: the sandbox has no GPU, and MapLibre needs a context.
  args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"]
});

/* The basemap goes through our own /api/basemap proxy, like in production —
 * so a tile that never arrives is a real defect, not a sandbox quirk. */
let vectorTiles = 0;
const countTiles = page =>
  page.on("response", r => { if (/\/api\/basemap\/.*\.pbf/.test(r.url()) && r.status() < 400) vectorTiles++; });

/* There is no example data any more: every screenshot needs a plot that was
 * really resolved through ALKIS first. This is the app's own add flow. */
async function addPlot(page) {
  await page.click(".page-head .btn");
  await page.getByText("Flurstück direkt").click();
  await page.fill("#q-cadastral-district", "Liebertwolkwitz");
  await page.fill("#q-parcel-number", "85/1");
  await page.getByRole("button", { name: "Nachschlagen" }).click();
  await page.waitForSelector(".wizard__preview, .site-plan", { timeout: 60000 });
}

const taken = [];
const problems = [];

/* The map reports when every tile for the current view has arrived. A tile
 * that 502s never lets it, and a whole screenshot run must not hang on one --
 * so the wait is bounded and says what it settled for. */
async function mapSettled(page, what) {
  try {
    await page.waitForSelector('[data-map-ready="true"]', { timeout: 45000 });
  } catch {
    problems.push(`${what}: Kartenkacheln kamen nicht vollständig an`);
    await page.waitForTimeout(2000);
  }
}

async function shot(page, name, mode, zusatz = "") {
  await page.waitForTimeout(340);
  // A layout that pushes the page sideways is a defect, and no screenshot shows it.
  const overflow = await page.evaluate(() =>
    document.documentElement.scrollWidth - document.documentElement.clientWidth);
  if (overflow > 1) problems.push(`${name}/${mode}: ${overflow}px waagerechter Überlauf`);
  const file = `${name}-${mode}${zusatz}.png`;
  await page.screenshot({ path: resolve(outDir, file), fullPage: true });
  taken.push(file);
}

for (const [mode, width, height, narrow] of [["hell", 1440, 1000, false], ["dunkel", 1440, 1000, false], ["dunkel", 402, 900, true]]) {
  const ctx = await browser.newContext({ viewport: { width: width, height: height }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  countTiles(page);
  page.on("pageerror", e => problems.push(`${mode}/${width}: ${e.message}`));
  const expected = t => /Failed to load resource/.test(t);   // /api/* 404 when the backend is down — the documented fallback
  page.on("console", m => { if (m.type() === "error" && !expected(m.text())) problems.push(`${mode}/${width}: ${m.text()}`); });
  await page.goto(address, { waitUntil: "load" });
  await page.evaluate(() => document.fonts.ready);
  await page.click(`.theme-switch button:nth-child(${mode === "hell" ? 1 : 2})`);
  await page.waitForTimeout(200);

  // The empty state is a real state and worth a picture: this is what the app
  // looks like before anything has been resolved.
  await shot(page, "uebersicht-leer", mode, narrow ? "-schmal" : "");

  await page.click(".page-head .btn");                      // Grundstück hinzufügen
  await shot(page, "assistent-1", mode, narrow ? "-schmal" : "");
  await page.getByText("Flurstück direkt").click();
  await page.fill("#q-cadastral-district", "Liebertwolkwitz");
  await page.fill("#q-parcel-number", "85/1");
  await shot(page, "assistent-2", mode, narrow ? "-schmal" : "");
  await page.getByRole("button", { name: "Nachschlagen" }).click();
  await page.waitForSelector(".site-plan", { timeout: 60000 });
  await shot(page, "assistent-3", mode, narrow ? "-schmal" : "");
  await page.getByRole("button", { name: "Passt" }).click();
  await shot(page, "assistent-4", mode, narrow ? "-schmal" : "");

  /* Every step of the wizard has an address of its own, so the browser's back
   * button steps back one step instead of leaving the wizard. */
  await page.goBack();
  await page.waitForTimeout(200);
  const steppedBackTo = new URL(page.url()).pathname;
  if (steppedBackTo !== "/aufnahme/flurstueck") {
    problems.push(`${mode}/${width}: Zurück führte von „Angaben“ nach ${steppedBackTo}`);
  }
  await page.goForward();
  await page.waitForSelector("#q-name", { timeout: 10000 });

  await page.getByRole("button", { name: "Anlegen und öffnen" }).click();

  await page.waitForTimeout(6000);                             // Kacheln laden lassen
  await shot(page, "grundstueck", mode, narrow ? "-schmal" : "");

  if (!narrow) {
    await page.getByRole("button", { name: "Luftbild" }).click();
    await page.waitForTimeout(4000);
    await shot(page, "grundstueck-luftbild", mode);
    await page.getByRole("button", { name: "Karte" }).click();
    await page.waitForTimeout(2000);
  }

  /* The point of the addresses: the plot has one of its own, and reloading it
   * comes back to the same page instead of the overview. This is also what
   * exercises the server's history-mode fallback above. */
  const plotAddress = page.url();
  if (!/\/grundstueck\/[^/]+$/.test(plotAddress)) {
    problems.push(`${mode}/${width}: das Grundstück hat keine eigene Adresse (${plotAddress})`);
  }
  await page.reload({ waitUntil: "load" });
  await page.waitForSelector(".plot-page", { timeout: 20000 });
  if (page.url() !== plotAddress) {
    problems.push(`${mode}/${width}: nach dem Neuladen auf ${page.url()} statt ${plotAddress}`);
  }

  await page.click(".breadcrumb a");

  await page.click('.main-nav a:nth-child(2)');               // Haustypen
  await shot(page, "haustypen", mode, narrow ? "-schmal" : "");
  if (!narrow) {
    // A destination, looked up for real: the picker is the point here, because
    // this geocoder answers "Am Kirschberg" with Bavaria as readily as Saxony.
    await page.click('.main-nav a:nth-child(3)');             // Ziele
    await page.getByRole("button", { name: /Ziel hinzufügen|Erstes Ziel anlegen/ }).first().click();
    const fields = await page.locator("input[type=text]").all();
    await fields[0].fill("Bahnhof");
    await fields[1].fill("Bahnhof Wurzen");
    await page.getByRole("button", { name: "Nachschlagen" }).click();
    await page.waitForSelector(".match-list__option", { timeout: 60000 });
    await shot(page, "ziele-treffer", mode);
    await page.locator(".match-list__option").first().click();
    await shot(page, "ziele", mode);

    // The overview with something on it, and the comparison mode that has to be
    // asked for. "uebersicht-leer" is the empty state and shows neither.
    await page.click('.main-nav a:nth-child(1)');
    await page.waitForSelector(".plot-card");
    await shot(page, "uebersicht", mode);
    await page.getByRole("button", { name: "Vergleichen" }).click();
    await page.waitForSelector(".selection-bar");
    await shot(page, "uebersicht-vergleich", mode);
    await page.getByRole("button", { name: "Fertig" }).click();

    // And the routes that follow from it, drawn from the geometry MOTIS sends.
    await page.click(".plot-card .btn");
    await page.getByRole("button", { name: "Wege berechnen" }).click();
    await page.waitForSelector(".route-card polyline", { timeout: 60000 });
    await page.waitForTimeout(600);
    // The cards themselves: this is the only picture that carries them, and
    // since they gained a raster ground the flat sketch is no longer what
    // they look like.
    await shot(page, "grundstueck-wege", mode);
    // And the surroundings: transit stops are live, the OSM categories say
    // plainly that this server has no index for them. The panel starts its own
    // search on this page now, so there is nothing to click -- and the button
    // that is there reads "Neu suchen", which is what a wait for "Nachsehen"
    // sat out until it timed out.
    await page.waitForSelector(".nearby__list tbody tr", { timeout: 60000 });
    await shot(page, "grundstueck-umgebung", mode);

    // The map of the same thing: house, ground around it, and every place that
    // was found. The wait is on a marker, not on the canvas -- an empty map
    // would otherwise pass as a picture.
    await page.getByRole("link", { name: "Auf der Umgebungskarte ansehen" }).click();
    await page.waitForSelector(".surroundings__poi", { timeout: 60000 });
    // Not a timeout: the map says when every tile for this view has arrived.
    // Waiting on a clock photographed a quarter-drawn basemap.
    await mapSettled(page, `${mode}/${width} Umgebungskarte`);
    await shot(page, "umgebungskarte", mode);
    if (!narrow && mode === "hell") {
      await page.getByRole("button", { name: "Mit Zielen" }).click();
      await mapSettled(page, `${mode}/${width} Umgebungskarte mit Zielen`);
      await shot(page, "umgebungskarte-ziele", mode);
    }
    await page.click(".breadcrumb a");

    await page.click('.main-nav a:nth-child(4)');             // Daten
    await shot(page, "daten", mode);
  }
  await ctx.close();
}

/* The print rendering, as the browser would lay it out on paper. */
/* A4 at 96 dpi. At the old 1240 px the shot was 1.76x the real 186 mm column,
   which flattered the layout and hid how tight it actually is. */
const ctx = await browser.newContext({ viewport: { width: 794, height: 1123 }, deviceScaleFactor: 2 });
const page = await ctx.newPage();
countTiles(page);
await page.goto(address, { waitUntil: "load" });
await page.evaluate(() => document.fonts.ready);
await addPlot(page);
await page.getByRole("button", { name: "Passt" }).click();
await page.getByRole("button", { name: "Anlegen und öffnen" }).click();
await page.waitForTimeout(6000);
await page.emulateMedia({ media: "print" });
await page.waitForTimeout(300);
await page.screenshot({ path: resolve(outDir, "grundstueck-druck.png"), fullPage: true });
taken.push("grundstueck-druck.png");
/* A flat screenshot cannot show where the page actually breaks; the PDF can. */
await page.pdf({ path: resolve(outDir, "grundstueck-druck.pdf"), format: "A4", preferCSSPageSize: true });
taken.push("grundstueck-druck.pdf");
await ctx.close();

await browser.close();
server.close();

// A blank basemap is the defect this project spent the longest on: MapLibre
// asks for no tile at all when its worker is missing, and says nothing.
if (!vectorTiles) {
  problems.push("Keine einzige Vektorkachel geladen — der Kartenhintergrund ist blind.");
}

if (problems.length) {
  console.error("Skriptfehler:\n  " + [...new Set(problems)].join("\n  "));
  process.exit(1);
}
console.log(`${taken.length} Aufnahmen in docs/screenshots/:\n  ` + taken.join("\n  "));
