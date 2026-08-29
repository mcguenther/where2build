/* Nimmt das Mockup in beiden Darstellungen und allen Reitern auf.
   Läuft gegen die gebaute Datei mockup/index.html — kein Server nötig. */
import { chromium } from "/opt/node22/lib/node_modules/playwright/index.mjs";
import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const wurzel = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const ausgabe = resolve(wurzel, "docs/screenshots");
mkdirSync(ausgabe, { recursive: true });

const REITER = [
  ["lageplan", "tab-lageplan"], ["einwerfen", "tab-einwerfen"], ["haustyp", "tab-haustyp"],
  ["wege", "tab-wege"], ["vergleich", "tab-vergleich"], ["druck", "tab-druck"]
];

const browser = await chromium.launch();
const gemacht = [];

for (const [darstellung, breite, hoehe] of [["light", 1440, 1000], ["dark", 1440, 1000], ["dark", 430, 900]]) {
  const ctx = await browser.newContext({ viewport: { width: breite, height: hoehe }, deviceScaleFactor: 2, colorScheme: darstellung });
  const seite = await ctx.newPage();
  await seite.goto(pathToFileURL(resolve(wurzel, "mockup/index.html")).href, { waitUntil: "load" });
  await seite.evaluate(() => document.fonts.ready);
  await seite.click(`[data-theme-set="${darstellung}"]`);
  await seite.waitForTimeout(250);

  const mobil = breite < 700;
  for (const [name, tabId] of REITER) {
    if (mobil && !["lageplan", "wege"].includes(name)) continue;
    await seite.click("#" + tabId);
    await seite.waitForTimeout(300);
    const datei = `${name}-${darstellung}${mobil ? "-mobil" : ""}.png`;
    await seite.screenshot({ path: resolve(ausgabe, datei), fullPage: true });
    gemacht.push(datei);
  }
  await ctx.close();
}

await browser.close();
console.log(`${gemacht.length} Aufnahmen in docs/screenshots/:\n  ` + gemacht.join("\n  "));
