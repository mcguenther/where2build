/* Nimmt alle Bereiche in beiden Darstellungen auf. Ohne Server, gegen die gebaute Datei. */
import { chromium } from "/opt/node22/lib/node_modules/playwright/index.mjs";
import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const wurzel = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const ausgabe = resolve(wurzel, "docs/screenshots");
mkdirSync(ausgabe, { recursive: true });
const adresse = pathToFileURL(resolve(wurzel, "mockup/index.html")).href;

const browser = await chromium.launch();
const gemacht = [];
const fehler = [];

for (const [modus, breite, hoehe] of [["light", 1440, 1000], ["dark", 1440, 1000], ["dark", 430, 900]]) {
  const mobil = breite < 700;
  const ctx = await browser.newContext({ viewport: { width: breite, height: hoehe }, deviceScaleFactor: 2, colorScheme: modus });
  await ctx.route(/fonts\.(googleapis|gstatic)\.com/, r => r.continue());
  const seite = await ctx.newPage();
  seite.on("pageerror", e => fehler.push(`${modus}/${breite}: ${e.message}`));
  await seite.goto(adresse, { waitUntil: "load" });
  await seite.evaluate(() => document.fonts.ready);
  await seite.click(`[data-theme-set="${modus}"]`);
  await seite.waitForTimeout(250);

  const schuss = async name => {
    await seite.waitForTimeout(320);
    const datei = `${name}-${modus}${mobil ? "-mobil" : ""}.png`;
    await seite.screenshot({ path: resolve(ausgabe, datei), fullPage: true });
    gemacht.push(datei);
  };

  await schuss("uebersicht");
  if (!mobil) { await seite.click("#k-aufnahme"); await seite.click('[data-lesen="url"]'); await schuss("aufnahme"); await seite.click("#k-aufnahme"); }
  await seite.click(".gkarte .knopf");                 // erstes Grundstück öffnen
  await schuss("grundstueck");
  await seite.click('#a-grundstueck .krume [data-ort="uebersicht"]');
  if (!mobil) { await seite.click("#k-vergleichen"); await schuss("vergleich"); await seite.click('#a-vergleich .krume [data-ort="uebersicht"]'); }
  await seite.click('.orte [data-ort="haustypen"]'); await schuss("haustypen");
  if (!mobil) { await seite.click('.orte [data-ort="ziele"]'); await schuss("ziele");
                await seite.click('.orte [data-ort="daten"]'); await schuss("daten"); }
  await ctx.close();
}
await browser.close();
if (fehler.length) { console.error("Skriptfehler:\n  " + fehler.join("\n  ")); process.exit(1); }
console.log(`${gemacht.length} Aufnahmen in docs/screenshots/:\n  ` + gemacht.join("\n  "));
