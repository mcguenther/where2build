/* The bookmarklet, exercised the way it is used: clicked on a foreign page,
 * handing that page's whole document to the app in another tab.
 *
 * `tests/bookmarklet.test.js` runs the generated one-liner in jsdom and
 * `tests/wizard.test.js` runs the wizard's half, but neither can prove the
 * thing this is for: two real origins, a real `window.open`, a real
 * `postMessage` between two tabs, and `/api/listings/extract` behind it. The
 * advert is the recorded Kleinanzeigen page, served from a *different* port so
 * the handover is genuinely cross-origin — and it is the page whose coordinate
 * lives in `og:latitude`, which is what a clipboard copy leaves behind.
 *
 * Needs the built app (`npm run build`) and a backend on :8000, like
 * `screenshots.mjs`. Same absolute Playwright path, so the same caveat: it
 * only runs where that path exists.
 */
import { chromium } from "/opt/node22/lib/node_modules/playwright/index.mjs";
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { dirname, extname, join, normalize, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const dist = resolve(root, "frontend/dist");
const MIME = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css",
  ".woff2": "font/woff2", ".woff": "font/woff", ".svg": "image/svg+xml",
  ".png": "image/png", ".ico": "image/x-icon", ".webmanifest": "application/manifest+json" };

const collect = req => new Promise(r => { let b = ""; req.on("data", c => b += c); req.on("end", () => r(b)); });

/* The app, with /api going to the running backend -- the same shape as the
 * screenshot script's server. */
const app = createServer(async (req, res) => {
  const path_ = normalize(decodeURIComponent(new URL(req.url, "http://x").pathname));
  if (path_.startsWith("/api/")) {
    const answer = await fetch(`http://127.0.0.1:8000${req.url}`, {
      method: req.method, headers: { "Content-Type": "application/json" },
      body: ["GET", "HEAD"].includes(req.method) ? undefined : await collect(req)
    });
    res.writeHead(answer.status, { "Content-Type": answer.headers.get("content-type") || "application/json" });
    return void res.end(Buffer.from(await answer.arrayBuffer()));
  }
  // Read first, then answer: writing the head before the read means a missing
  // file tries to send a second set of headers from the catch.
  const file = join(dist, path_ === "/" ? "index.html" : path_);
  let body = null;
  try { body = await readFile(file); } catch { body = null; }
  if (body) {
    res.writeHead(200, { "Content-Type": MIME[extname(file)] || "application/octet-stream" });
    return void res.end(body);
  }
  if (extname(file)) return void res.writeHead(404).end("nope");
  res.writeHead(200, { "Content-Type": "text/html" });
  res.end(await readFile(join(dist, "index.html")));
});

/* The "portal": a recorded advert page, served from a DIFFERENT origin, so the
 * handover really is cross-origin the way it is in production. */
const advert = await readFile(resolve(root, "backend/tests/fixtures/inserat-kleinanzeigen.html"), "utf-8");
const portal = createServer((req, res) => {
  res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" }).end(advert);
});

await new Promise(r => app.listen(4173, r));
await new Promise(r => portal.listen(4199, r));

const APP = "http://127.0.0.1:4173";
const { bookmarkletCode } = await import(`${resolve(root, "frontend/src/lib/bookmarklet.js")}`);

const browser = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium" });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const problems = [];
const page = await ctx.newPage();
/* The advert's own blocked CDN requests are not our defects; only the app
   tab's console is. */

/* The recorded advert references the portal's own CDN, and this browser has no
   route to the internet -- `load` would never fire. Everything off our two
   origins is refused, which is also what keeps the page from phoning home. */
await ctx.route("**/*", route => {
  const host = new URL(route.request().url()).host;
  return host.startsWith("127.0.0.1:") ? route.continue() : route.abort();
});
await page.goto("http://127.0.0.1:4199/expose/170438443", { waitUntil: "domcontentloaded" });
const title = await page.title();
console.log("Portalseite geladen:", title.slice(0, 60));

// The click on the bookmark: the browser runs the javascript: URL in the page.
const opening = ctx.waitForEvent("page");
await page.evaluate(bookmarkletCode(APP));
const appTab = await opening;
appTab.on("console", m => { if (m.type() === "error") problems.push(`Konsole (App): ${m.text()}`); });
await appTab.waitForLoadState("domcontentloaded");
console.log("App-Tab geöffnet:", await appTab.url());

// The wizard should reach the search step on its own -- nothing is clicked.
try {
  await appTab.waitForSelector("details.gelesen", { timeout: 60000 });
  await appTab.click("details.gelesen > summary");
  await appTab.waitForSelector(".suggestions", { timeout: 10000 });
} catch (error) {
  problems.push(`Die übergebene Seite wurde nicht gelesen: ${error.message}`);
}

const read = Object.fromEntries(await appTab.evaluate(() =>
  [...document.querySelectorAll(".suggestion")].map(row => [
    row.querySelector(".field-label")?.textContent?.trim(),
    row.querySelector("input")?.value
  ])
));
console.log("Gelesene Werte:", JSON.stringify(read));

/* The coordinate is the whole argument for this way in: it sits in
   `og:latitude`/`og:longitude` in `<head>`, which `Strg+A` never selects. If
   this is empty the handover delivered a clipboard's worth and nothing more. */
for (const [field, expected] of [
  ["Breitengrad", "51.13430038927799"],
  ["Längengrad", "12.455584928445097"],
  ["Kaufpreis", "80000"],
  ["Grundstücksfläche", "1025"]
]) {
  if (read[field] !== expected) problems.push(`${field}: „${read[field]}" statt „${expected}"`);
}
await appTab.screenshot({ path: resolve(root, "docs/screenshots/assistent-uebergabe.png"), fullPage: true });

await browser.close();
app.close(); portal.close();
if (problems.length) { console.error("PROBLEME:\n" + problems.join("\n")); process.exit(1); }
console.log("OK");
