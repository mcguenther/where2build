/* Screenshots of every view, light and dark, plus a narrow viewport and the
 * print rendering. Runs against the built app on a static server — no manual
 * steps, so the images always match the current code. */
import { chromium } from "/opt/node22/lib/node_modules/playwright/index.mjs";
import { mkdirSync, readFileSync } from "node:fs";
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

/* The Gemarkung is picked from the register now, not typed into a blank line:
 * the field carries a generated id, so it is addressed by its label, and the
 * entry only counts once one of the offered districts is chosen. */
async function pickDistrict(page, name) {
  // The label alone is ambiguous: the source radio and the result list carry it too.
  await page.getByRole("combobox", { name: "Gemarkung" }).fill(name);
  await page.waitForSelector(".gemarkung__treffer", { timeout: 30000 });
  await page.locator(".gemarkung__treffer").first().click();
}

/* The one field everything goes into. Named rather than repeated: it is the
 * way in on the start page and in every step of the wizard, and the old
 * per-source ids (#q-text, #q-paste) are gone with the sources. */
const QUERY_FIELD = ".query-box input[role=\"combobox\"]";

/* There is no example data any more: every screenshot needs a plot that was
 * really resolved through ALKIS first. This is the app's own way in, from the
 * start page: a bare parcel number is read as one, which unfolds the district
 * beside it, and the start page hands the pair to the wizard. Starting here
 * rather than at „Grundstück hinzufügen" is not only shorter -- it is the
 * route a person takes, and it exercises the hand-off. */
async function addPlot(page) {
  await page.fill(QUERY_FIELD, "85/1");
  await page.waitForSelector("#q-parcel-number", { timeout: 10000 });
  await pickDistrict(page, "Liebertwolkwitz");
  await page.getByRole("button", { name: "Grundstück finden" }).click();
  await page.waitForSelector(".wizard__preview, .site-plan", { timeout: 60000 });
}

const taken = [];
const problems = [];

/* A real listing's description, from the case in
   docs/research/flurstueck-identifikation.md. It names three places, an area
   and a street, and resolves to Flurstück 790/11 in Gemarkung Großbothen. */
const LISTING =
  "Baugrundstück in ruhiger Lage am Ortsrand von Großbothen, einem OT von Grimma. "
  + "Das Grundstück ist 502 m² groß und liegt an der Wiesenstraße. "
  + "Über die B107 erreichen Sie die ca. 6 km entfernte Kreisstadt Grimma. "
  + "Sehenswert sind das Kloster Nimbschen und die Schiffsmühle in Höfgen.";

/* An advert this tool cannot serve, and the picture of it saying so. Advert
 * 3381469778, shortened: the location field names Sachsen-Anhalt, „Brehna" is
 * in no Saxon Gemarkung, and „Schulen in Roitzsch" names one that is — 100 km
 * away, holding a parcel of exactly the stated 600 m². The run used to find
 * it. */
const FOREIGN_LISTING =
  "Ihr Traum vom Eigenheim: 600 m² Baugrundstück in Brehna. "
  + "Sachsen-Anhalt - Brehna. "
  + "Das Grundstück liegt im Geltungsbereich des Bebauungsplans „Wiesewitz/Goethestraße“ "
  + "OT Brehna der Gemeinde Sandersdorf-Brehna. "
  + "Kindergarten und Grundschule finden sich im Ort, weiterführende Schulen in "
  + "Roitzsch oder Bitterfeld sind in 10 bis 15 Autominuten erreichbar.";

/* A saved advert, exactly as the portal served it — the same file the backend
   tests read. Pasting it is what a person does with Strg+A, Strg+C on a portal
   that refuses a server-side fetch, and everything the next step shows is read
   out of this markup without a model. */
const PASTED_PAGE = readFileSync(
  new URL("../backend/tests/fixtures/inserat-kleinanzeigen.html", import.meta.url), "utf8"
);

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

/** Put a whole page into a field the way a person does — with one paste.
 *
 *  Not `page.fill`: Playwright inserts the text through the input pipeline, and
 *  171 kB of markup takes ~27 s of it, which sits right under the default
 *  timeout and fails whenever the machine is busy. A paste is also the truer
 *  action — it is the one the product is built around, `text/html` and all, so
 *  this exercises `takePaste` instead of going round it. */
async function pasteInto(page, selector, text) {
  await page.waitForSelector(selector, { state: "visible" });
  await page.$eval(selector, (el, value) => {
    const data = new DataTransfer();
    data.setData("text/plain", value);
    data.setData("text/html", value);
    el.focus();
    el.dispatchEvent(new ClipboardEvent("paste", { clipboardData: data, bubbles: true, cancelable: true }));
    el.value = value;
    el.dispatchEvent(new Event("input", { bubbles: true }));
  }, text);
}

/** Click a section by its name. Positional selectors break the moment the
 *  navigation grows an entry -- which is exactly what happened when the start
 *  page arrived. */
async function nav(page, name) {
  await page.locator(".main-nav a").filter({ hasText: name }).first().click();
  await page.waitForTimeout(150);
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

// The narrow pass runs in the light theme like the wide one: it is the
// default a phone arrives in, and having the only phone-width pictures be dark
// meant nobody ever looked at the layout most people see.
for (const [mode, width, height, narrow] of [["hell", 1440, 1000, false], ["dunkel", 1440, 1000, false], ["hell", 402, 900, true]]) {
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

  // The start page before anything has been resolved: the field, and what the
  // thing is for. This is the first thing anybody sees.
  await shot(page, "start-leer", mode, narrow ? "-schmal" : "");

  /* The overview, still empty. A real state and worth its own picture.
     Reached by its route rather than by the navigation: with nothing entered
     the start page carries no sections at all -- every one of them would lead
     to an empty page with a zero beside it -- so there is no link here to
     click. Every later `nav()` in this run has a stand behind it and finds
     the sections where they belong. */
  await page.goto(`${address}grundstuecke`, { waitUntil: "load" });
  await page.waitForTimeout(300);
  await shot(page, "uebersicht-leer", mode, narrow ? "-schmal" : "");

  await page.click(".page-head .btn");                      // Grundstück hinzufügen
  await shot(page, "assistent-1", mode, narrow ? "-schmal" : "");

  /* The search, on the way past: this is the step between a listing and a
     parcel, and the only one whose whole point is showing its working. It
     needs no model — the text is read with patterns and the Gemarkung
     register — so it runs here even without an LLM key. */
  // Nothing is switched on first: a few sentences are read as a description
  // text by themselves, and the chip says so. Typed prose goes through the
  // same reader as a pasted page, and straight on into the search: what was
  // read rides along folded shut inside that step.
  await page.fill(QUERY_FIELD, LISTING);
  await page.getByRole("button", { name: "Grundstück finden" }).click();
  await page.waitForSelector(".suche", { timeout: 30000 });
  await page.waitForTimeout(1500);
  await shot(page, "suche-laeuft", mode, narrow ? "-schmal" : "");
  /* Mid-run, once the districts are drawn but before a parcel is named: this
     is the picture that shows whether the evidence reads against a photograph
     at all, and it is the state a viewer spends the longest looking at. */
  await page.waitForTimeout(2500);
  await shot(page, "suche-indizien", mode, narrow ? "-schmal" : "");
  try {
    await page.waitForSelector(".suche__urteil--bestaetigt, .suche__urteil--mehrdeutig, .suche__urteil--erfolglos", { timeout: 90000 });
    // Let the queue play the run out; it spends a fixed budget over the
    // backlog, and the picture is of a settled map — so this has to outlast
    // BUDGET_MS plus the last flight, not merely the verdict.
    await page.waitForTimeout(15000);
  } catch {
    problems.push(`${mode}/${width}: die Suche kam zu keinem Ergebnis`);
  }
  await shot(page, "suche-ergebnis", mode, narrow ? "-schmal" : "");

  /* And a listing this tool cannot serve. It costs no cadastre request at all:
     the location field names the state, and every Saxon answer would be
     somebody else's parcel. */
  await page.click(".breadcrumb a");
  await page.click(".page-head .btn");
  await page.fill(QUERY_FIELD, FOREIGN_LISTING);
  await page.getByRole("button", { name: "Grundstück finden" }).click();
  try {
    await page.waitForSelector(".suche__urteil--erfolglos", { timeout: 60000 });
    await page.waitForTimeout(4000);
  } catch {
    problems.push(`${mode}/${width}: das Inserat außerhalb Sachsens wurde nicht als solches erkannt`);
  }
  await shot(page, "suche-ausserhalb", mode, narrow ? "-schmal" : "");

  /* The pasted page, and what was read off it. This is the way in for a portal
     that refuses a server-side fetch, and it needs no model either: price,
     area, coordinate and pictures come out of the markup. The list is folded
     away inside the search now, so the picture is of it opened. */
  await page.click(".breadcrumb a");
  await page.click(".page-head .btn");
  await pasteInto(page, QUERY_FIELD, PASTED_PAGE);
  await page.getByRole("button", { name: "Grundstück finden" }).click();
  try {
    await page.waitForSelector("details.gelesen", { timeout: 30000 });
    await page.click("details.gelesen > summary");
    await page.waitForSelector(".suggestions", { timeout: 5000 });
  } catch {
    problems.push(`${mode}/${width}: die eingefügte Seite wurde nicht gelesen`);
  }
  await shot(page, "assistent-werte", mode, narrow ? "-schmal" : "");

  await page.click(".breadcrumb a");
  await page.click(".page-head .btn");
  // A bare number is read as a parcel number, which is the one reading that
  // unfolds a second field: without a district the number is not unique.
  await page.fill(QUERY_FIELD, "85/1");
  await page.waitForSelector("#q-parcel-number", { timeout: 10000 });
  await pickDistrict(page, "Liebertwolkwitz");
  await shot(page, "assistent-2", mode, narrow ? "-schmal" : "");
  await page.getByRole("button", { name: "Grundstück finden" }).click();
  await page.waitForSelector(".site-plan", { timeout: 60000 });
  /* The last step: the outline, what is being taken over, and the three fields
     that used to be a page of their own. It is a picture of the ground, so
     without waiting for the tiles a cold cache photographs the drawing on empty
     paper and calls it a clean run. */
  await mapSettled(page, `${mode}/${width} Flurstückswahl`);
  await shot(page, "assistent-3", mode, narrow ? "-schmal" : "");

  /* Every step of the wizard has an address of its own, so the browser's back
   * button steps back one step instead of leaving the wizard. The parcel step
   * is the last one — it carries the fields the cadastre cannot supply — so
   * back from it is the source step. */
  await page.goBack();
  await page.waitForTimeout(200);
  const steppedBackTo = new URL(page.url()).pathname;
  if (steppedBackTo !== "/aufnahme/quelle") {
    problems.push(`${mode}/${width}: Zurück führte von „Flurstück“ nach ${steppedBackTo}`);
  }
  await page.goForward();
  await page.waitForSelector("#q-name", { timeout: 10000 });

  await page.getByRole("button", { name: "Anlegen und öffnen" }).click();

  await page.waitForTimeout(6000);                             // Kacheln laden lassen
  await shot(page, "grundstueck", mode, narrow ? "-schmal" : "");

  /* Teilen, abgemeldet. There is no identity provider in this run, so what the
   * panel shows is the invitation into an account — which is the state most
   * visitors meet, and the one worth checking reads as an offer rather than as
   * a broken button. The switches themselves need a session; they are covered
   * by the unit tests and by a walk against a throwaway provider. */
  await page.getByRole("button", { name: "Teilen" }).click();
  await page.waitForSelector(".share", { timeout: 10000 });
  await shot(page, "teilen", mode, narrow ? "-schmal" : "");
  await page.getByRole("button", { name: "Schließen" }).click();

  if (!narrow) {
    await page.getByRole("button", { name: "Luftbild" }).click();
    await page.waitForTimeout(4000);
    await shot(page, "grundstueck-luftbild", mode);
    await page.getByRole("button", { name: "Karte" }).click();
    await page.waitForTimeout(2000);
  }

  /* The location record: eleven checks against the authority services, asked
   * with the parcel outline. Waited on either outcome — with no backend on
   * :8000 the list shows the German failure sentence, and that is a state
   * worth photographing too. */
  await page.getByRole("link", { name: "Standort prüfen" }).click();
  await page.waitForSelector(".checks__list, .checks .notice--error", { timeout: 90000 });
  await page.waitForTimeout(3000);
  await shot(page, "standort", mode, narrow ? "-schmal" : "");
  if (!narrow) {
    // The noise layer over the ground: the one raster in this app that does
    // not come from a WMS, because that service speaks no Web Mercator.
    await page.getByRole("button", { name: "Lärm" }).click();
    await mapSettled(page, `${mode}/${width} Lärmschleier`);
    await shot(page, "standort-laerm", mode);
  }
  await page.click(".breadcrumb a:nth-child(3)");
  await page.waitForSelector(".plot-page", { timeout: 20000 });

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

  await nav(page, "Haustypen");
  await shot(page, "haustypen", mode, narrow ? "-schmal" : "");
  if (!narrow) {
    // A destination, looked up for real: the picker is the point here, because
    // this geocoder answers "Am Kirschberg" with Bavaria as readily as Saxony.
    await nav(page, "Ziele");
    await page.getByRole("button", { name: /Ziel hinzufügen|Erstes Ziel anlegen/ }).first().click();
    const fields = await page.locator("input[type=text]").all();
    await fields[0].fill("Bahnhof");
    await fields[1].fill("Bahnhof Wurzen");
    await page.getByRole("button", { name: "Nachschlagen" }).click();
    await page.waitForSelector(".match-list__option", { timeout: 60000 });
    await shot(page, "ziele-treffer", mode);
    await page.locator(".match-list__option").first().click();
    await shot(page, "ziele", mode);

    // The start page with a stand behind it: the greeting changes and the
    // last plots stand under the field.
    await nav(page, "Start");
    await page.waitForSelector(".plot-card");
    await shot(page, "start", mode);

    // The overview with something on it, and the comparison mode that has to be
    // asked for. "uebersicht-leer" is the empty state and shows neither.
    await nav(page, "Grundstücke");
    await page.waitForSelector(".plot-card");
    await shot(page, "uebersicht", mode);
    await page.getByRole("button", { name: "Vergleichen" }).click();
    await page.waitForSelector(".selection-bar");
    await shot(page, "uebersicht-vergleich", mode);
    await page.getByRole("button", { name: "Fertig" }).click();

    // And the routes that follow from it, drawn from the geometry MOTIS sends.
    // The page asks for them itself now -- there is no button to press, and a
    // wait for one sat there until it timed out.
    await page.click(".plot-card .btn");
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
    // Bike and car arrive after the walk does, so the table is photographed
    // once its cells have stopped being placeholders. Bounded: a router that
    // cannot answer leaves the skeletons standing, and that is a picture worth
    // having rather than a run that never ends.
    await page
      .waitForFunction(() => !document.querySelector(".skeleton-cell"), null, { timeout: 60000 })
      .catch(() => {});
    // The map stands beside that list on the same page: house, ground around
    // it, and every place that was found. The wait is on a marker, not on the
    // canvas -- an empty map would otherwise pass as a picture.
    await page.waitForSelector(".surroundings__poi", { timeout: 60000 });
    // Not a timeout: the map says when every tile for this view has arrived.
    // Waiting on a clock photographed a quarter-drawn basemap.
    await mapSettled(page, `${mode}/${width} Umgebungskarte`);
    await shot(page, "grundstueck-umgebung", mode);
    if (!narrow && mode === "hell") {
      await page.getByRole("button", { name: "Mit Zielen" }).click();
      await mapSettled(page, `${mode}/${width} Umgebungskarte mit Zielen`);
      await shot(page, "grundstueck-umgebung-ziele", mode);
    }
    await page.click(".breadcrumb a");

    await nav(page, "Daten");
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
await page.getByRole("button", { name: "Anlegen und öffnen" }).click();
await page.waitForTimeout(6000);
await page.emulateMedia({ media: "print" });
await page.waitForTimeout(300);
await page.screenshot({ path: resolve(outDir, "grundstueck-druck.png"), fullPage: true });
taken.push("grundstueck-druck.png");
/* A flat screenshot cannot show where the page actually breaks; the PDF can. */
await page.pdf({ path: resolve(outDir, "grundstueck-druck.pdf"), format: "A4", preferCSSPageSize: true });
taken.push("grundstueck-druck.pdf");

/* And the location sheet, which prints the other way round — the record leads,
   the map follows it. Eleven checks are taller than one page, so the PDF is
   the part that shows whether the breaks land between rows. */
await page.emulateMedia({ media: null });
await page.getByRole("link", { name: "Standort prüfen" }).click();
await page.waitForSelector(".checks__list, .checks .notice--error", { timeout: 90000 });
await page.waitForTimeout(2000);
await page.emulateMedia({ media: "print" });
await page.waitForTimeout(300);
await page.screenshot({ path: resolve(outDir, "standort-druck.png"), fullPage: true });
taken.push("standort-druck.png");
await page.pdf({ path: resolve(outDir, "standort-druck.pdf"), format: "A4", preferCSSPageSize: true });
taken.push("standort-druck.pdf");
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
