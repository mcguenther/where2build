/* Pulling a listing page into this sandbox, so a fixture can be recorded and a
 * link dropped into a chat can actually be read here.
 *
 * This is a development tool and it stays one. The product's way in is the
 * user's own browser — the bookmarklet in `frontend/src/lib/bookmarklet.js`,
 * which needs no portal's permission because the page is already open. What
 * this script does instead is drive a real browser from the sandbox, which
 * gets past a challenge a server-side fetch cannot, and that is exactly the
 * kind of thing `docs/research/immobilienscout24-zugang.md` § 5.5 argues does
 * not belong in a deployed product. Recording a fixture is not deploying.
 *
 * It never solves a CAPTCHA. Where a portal puts a human check in front of the
 * page (immowelt does), the script says so and offers the routes that do not
 * touch it: the portal's own result list, and the handover.
 *
 * Measured routes are in `docs/research/inserate-im-sandbox-lesen.md`.
 *
 *   node scripts/fetch-listing.mjs <url> [options]
 *
 *     --out <datei>     where the HTML goes (default: ./inserat-<portal>.html)
 *     --text            also flatten the page to text and print it
 *     --liste <url>     an immowelt result list to look the exposé up in;
 *                       may be given more than once
 *     --mode <route>    auto (default), plain, browser or liste
 *     --timeout <s>     how long the browser may wait for a challenge (60)
 *
 * The Playwright import is the same absolute sandbox path the other scripts
 * use, so the same caveat holds: it runs where that path exists.
 */
import { spawnSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import { resolve } from "node:path";

const BROWSER_HEADERS = {
  "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
  "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
  "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
  "Upgrade-Insecure-Requests": "1",
};

/* Each wall below was answered by a live portal on 17.09.2026 and the marker
 * is what that answer actually contained. `human` is the distinction that
 * decides everything: a challenge a browser passes by itself, against a check
 * that wants a person — and there the script stops. */
const WALLS = [
  { name: "DataDome-CAPTCHA", human: true,
    test: html => /geo\.captcha-delivery\.com|'rt':'c'/.test(html) },
  { name: "DataDome-Sperre", human: true,
    test: html => /var dd=\{|Please enable JS and disable any ad blocker/.test(html) },
  { name: "AWS-WAF-Prüfung", human: false,
    test: html => /Ich bin kein Roboter|awswaf|challenge\.js/.test(html) },
  { name: "IP-Bereich gesperrt", human: true,
    test: html => /IP-Bereich vorübergehend gesperrt/.test(html) },
];

/* Size decides alongside the marker, because a marker alone would risk
 * discarding a served page that merely mentions the challenge it passed.
 * Every wall answer measured was under 4 kB; the exposé behind one was 3,4 MB. */
const WALL_MAX_BYTES = 20000;
const wallIn = html =>
  (html.length < WALL_MAX_BYTES && WALLS.find(wall => wall.test(html))) || null;

const flatten = html => html
  .replace(/<(script|style|noscript)\b[^>]*>[\s\S]*?<\/\1>/gi, " ")
  .replace(/<[^>]+>/g, "\n")
  .replace(/&nbsp;/g, " ").replace(/&amp;/g, "&").replace(/&quot;/g, '"')
  .replace(/&#(\d+);/g, (_, n) => String.fromCharCode(Number(n)))
  .split("\n").map(line => line.trim()).filter(Boolean).join("\n")
  .replace(/\n{3,}/g, "\n\n");

const titleOf = html => (html.match(/<title[^>]*>([^<]*)/i) || [, ""])[1].trim();

async function plainFetch(url) {
  const answer = await fetch(url, { headers: BROWSER_HEADERS, redirect: "follow" });
  const html = await answer.text();
  return { route: "plain", status: answer.status, html };
}

/* Headful, and that is the whole point: the same Chromium in headless mode
 * sits on ImmoScout's challenge page for thirty seconds and never leaves it,
 * while under Xvfb the challenge resolves by itself in under five. */
async function browserFetch(url, timeoutMs) {
  const { chromium } = await import("/opt/node22/lib/node_modules/playwright/index.mjs");
  const browser = await chromium.launch({
    headless: false,
    proxy: process.env.HTTPS_PROXY ? { server: process.env.HTTPS_PROXY } : undefined,
    args: ["--no-sandbox", "--window-size=1280,900"],
  });
  try {
    const context = await browser.newContext({
      locale: "de-DE", timezoneId: "Europe/Berlin", viewport: { width: 1280, height: 900 },
    });
    const page = await context.newPage();
    const answer = await page.goto(url, { waitUntil: "domcontentloaded", timeout: timeoutMs });
    const status = answer ? answer.status() : 0;
    let html = await page.content();
    const deadline = Date.now() + timeoutMs;
    for (let wall = wallIn(html); wall && !wall.human && Date.now() < deadline; wall = wallIn(html)) {
      await page.waitForTimeout(2000);
      html = await page.content();
    }
    return { route: "browser", status, html };
  } finally {
    await browser.close();
  }
}

/* immowelt serves its result lists and protects its exposés, so a listing that
 * cannot be opened can still be read off the list it stands in. What arrives
 * is the card: price, area, district, and the description cut after roughly
 * 170 characters. The list is one page — narrow the place until the exposé is
 * on it, `…/suche/leipzig-baalsdorf/grundstuecke/kaufen` rather than the city. */
async function fromList(exposeId, listUrls) {
  for (const listUrl of listUrls) {
    const { status, html } = await plainFetch(listUrl);
    if (status !== 200) {
      console.log(`  ${listUrl} → HTTP ${status}`);
      continue;
    }
    const at = html.indexOf(`expose/${exposeId}`);
    if (at < 0) {
      const count = new Set(html.match(/expose\/[0-9a-f-]{36}/g) || []).size;
      console.log(`  ${listUrl} → ${count} Inserate, das gesuchte nicht dabei`);
      continue;
    }
    const rest = html.slice(at + 40);
    const next = rest.search(/expose\/[0-9a-f-]{36}/);
    const opens = html.lastIndexOf("<a ", at);
    const card = html.slice(opens < 0 ? at : opens, next < 0 ? at + 9000 : at + 40 + next);
    const headline = (card.match(/ title="([^"]{10,200})"/) || [, ""])[1];
    return { route: "liste", status: 200, html: card, listUrl, title: headline };
  }
  return null;
}

const args = process.argv.slice(2);
const TAKES_VALUE = ["--out", "--liste", "--mode", "--timeout"];
/* The first bare argument is the URL — bare meaning it is not a flag and not
 * some flag's value, or `--mode browser <url>` would be fetched as "browser". */
const url = args.find((arg, i) => !arg.startsWith("--") && !TAKES_VALUE.includes(args[i - 1]));
const option = (name, fallback) => {
  const at = args.indexOf(`--${name}`);
  return at < 0 ? fallback : args[at + 1];
};
const every = name => args.flatMap((arg, i) => (arg === `--${name}` ? [args[i + 1]] : []));

if (!url) {
  console.error("Aufruf: node scripts/fetch-listing.mjs <url> [--out datei] [--text] [--liste url] [--mode auto|plain|browser|liste] [--timeout s]");
  process.exit(2);
}

const mode = option("mode", "auto");

/* Under Xvfb before the first request, not around the browser call: re-running
 * the process from there would repeat every route that has already run. */
if (!process.env.DISPLAY && (mode === "auto" || mode === "browser")) {
  const under = spawnSync("xvfb-run", ["-a", process.execPath, ...process.argv.slice(1)],
    { stdio: "inherit" });
  process.exit(under.status ?? 1);
}
const timeoutMs = Number(option("timeout", 60)) * 1000;
const host = new URL(url).hostname.replace(/^www\./, "").split(".")[0];
const out = resolve(option("out", `inserat-${host}.html`));
const exposeId = (url.match(/expose\/([0-9a-f-]{36})/) || [])[1];

let result = null;

if (mode === "plain" || mode === "auto") {
  result = await plainFetch(url);
  const wall = wallIn(result.html);
  console.log(`Direkt geladen: HTTP ${result.status}, ${result.html.length} Zeichen${wall ? `, abgewiesen (${wall.name})` : ""}`);
  if (wall || result.status >= 400) result = mode === "plain" ? result : null;
}

if (!result && (mode === "browser" || mode === "auto")) {
  console.log("Versuche es im Browser …");
  result = await browserFetch(url, timeoutMs);
  const wall = wallIn(result.html);
  console.log(`Im Browser: HTTP ${result.status}, ${result.html.length} Zeichen${wall ? `, abgewiesen (${wall.name})` : ""}`);
  if (wall) {
    if (wall.human) {
      console.log(`\n${wall.name}: Das Portal verlangt hier einen Menschen. Der bleibt unangetastet —`);
      console.log("dieses Skript löst keine Captchas.");
    }
    result = null;
  }
}

const listUrls = every("liste");
if (!result && exposeId && (mode === "liste" || mode === "auto") && listUrls.length) {
  console.log("Suche das Inserat in der Ergebnisliste …");
  result = await fromList(exposeId, listUrls);
}

if (!result) {
  console.error("\nKein Weg hat die Seite geliefert. Was jetzt geht:");
  if (exposeId && !listUrls.length) {
    console.error("  • --liste https://www.immowelt.de/suche/<ort>/grundstuecke/kaufen — die Liste");
    console.error("    liefert das Portal auch dann, wenn es das Exposé sperrt (Preis, Fläche,");
    console.error("    Stadtteil, Beschreibungsanfang).");
  }
  console.error("  • Das Inserat im eigenen Browser öffnen und mit dem Bookmarklet übergeben,");
  console.error("    oder die Seite als HTML speichern und die Datei hierher geben.");
  process.exit(1);
}

writeFileSync(out, result.html);
console.log(`\nWeg „${result.route}“${result.listUrl ? ` über ${result.listUrl}` : ""}`);
console.log(`Titel: ${result.title || titleOf(result.html) || "—"}`);
console.log(`Gespeichert: ${out} (${result.html.length} Zeichen)`);

if (args.includes("--text")) {
  const text = flatten(result.html);
  writeFileSync(out.replace(/\.html?$/, "") + ".txt", text);
  console.log("\n--- Text ---\n" + text);
}
