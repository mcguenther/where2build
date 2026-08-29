/* Fährt das Mockup im echten Browser und prüft, was der Nutzer sieht:
   Reiter, Darstellungswechsel, Kontrast, Kollisionsprüfung, Umbruchfehler. */
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { chromium } from "/opt/node22/lib/node_modules/playwright/index.mjs";
import { resolve, dirname } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const wurzel = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const adresse = pathToFileURL(resolve(wurzel, "mockup/index.html")).href;

let browser, seite, fehler;
before(async () => {
  browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  seite = await ctx.newPage();
  fehler = [];
  seite.on("pageerror", e => fehler.push(e.message));
  // Schriften kommen von fonts.googleapis.com; in abgeschotteten Umgebungen scheitert das.
  const umgebung = t => /ERR_CONNECTION|ERR_NAME_NOT_RESOLVED|fonts\.(googleapis|gstatic)/.test(t);
  seite.on("console", m => { if (m.type() === "error" && !umgebung(m.text())) fehler.push(m.text()); });
  await seite.goto(adresse, { waitUntil: "load" });
});
after(async () => { await browser.close(); });

test("die Seite lädt ohne Skriptfehler", () => {
  assert.deepEqual(fehler, [], fehler.join(" | "));
});

test("alle sechs Reiter sind erreichbar und zeigen genau eine Tafel", async () => {
  const ids = await seite.$$eval('[role="tab"]', ts => ts.map(t => t.id));
  assert.equal(ids.length, 6);
  for (const id of ids) {
    await seite.click("#" + id);
    const sichtbar = await seite.$$eval(".tafel", ts => ts.filter(t => !t.hidden).length);
    assert.equal(sichtbar, 1, `nach ${id} sind ${sichtbar} Tafeln sichtbar`);
  }
  await seite.click("#tab-lageplan");
});

test("Kennzahlen sind gerechnet, nicht als Strich stehengeblieben", async () => {
  const werte = await seite.$$eval(
    "#k-flaeche-gerechnet,#k-front,#k-rechteckig,#k-verhaeltnis,#k-mrr,#k-hausmass,#k-grz,#k-grenzpunkte",
    ns => ns.map(n => n.textContent.trim()));
  for (const w of werte) assert.ok(w && w !== "—", `leere Kennzahl: "${w}"`);
  assert.match(await seite.textContent("#k-flaeche-gerechnet"), /795,3 m²/);
  assert.match(await seite.textContent("#k-front"), /22,62 m/);
});

test("Startlage meldet keinen Verstoß", async () => {
  assert.ok(await seite.$eval("#statusbanner", n => n.classList.contains("ok")));
  assert.match(await seite.textContent("#statustext"), /liegt im Bebauungsfenster/);
});

test("zu tiefe Abstandsfläche lässt die Prüfung anschlagen", async () => {
  const felder = seite.locator("#segment-zeilen input");
  for (let i = 0; i < await felder.count(); i++) {
    await felder.nth(i).fill("9");
    await felder.nth(i).dispatchEvent("input");
  }
  await seite.waitForTimeout(120);
  assert.equal(await seite.$eval("#statusbanner", n => n.classList.contains("ok")), false,
    "Banner müsste bei 9 m Abstandsfläche auf Verstoß stehen");
  assert.match(await seite.textContent("#statustext"), /außerhalb des Bebauungsfensters/);
  for (let i = 0; i < await felder.count(); i++) {
    await felder.nth(i).fill("3");
    await felder.nth(i).dispatchEvent("input");
  }
  await seite.waitForTimeout(120);
  assert.ok(await seite.$eval("#statusbanner", n => n.classList.contains("ok")));
});

test("Seitenverhältnis-Regler erhält die bebaute Fläche", async () => {
  const lies = async () => (await seite.textContent("#k-hausmass"))
    .replace(/\s|m/g, "").split("×").map(t => parseFloat(t.replace(",", ".")));
  const [b0, t0] = await lies();
  await seite.locator("#r-verhaeltnis").fill("2");
  await seite.waitForTimeout(120);
  const [b1, t1] = await lies();
  assert.ok(b1 > b0, "breiter werden");
  assert.ok(Math.abs(b0 * t0 - b1 * t1) < 0.5, `Fläche driftet: ${b0 * t0} → ${b1 * t1}`);
  await seite.locator("#r-verhaeltnis").fill("1.35");
  await seite.waitForTimeout(120);
});

test("Kartenausrichtung dreht die Szene, der Nordpfeil hält dagegen", async () => {
  const drehung = () => seite.$eval("#buehne g[transform^='rotate']", n => n.getAttribute("transform"));
  assert.match(await drehung(), /rotate\(0,/);
  await seite.click('[data-nord="1"]');
  await seite.waitForTimeout(120);
  assert.match(await drehung(), /rotate\(17,/);
  await seite.click('[data-nord="0"]');
});

test("beide Darstellungen setzen Vorder- und Hintergrund und trennen sich deutlich", async () => {
  const messen = async w => {
    await seite.click(`[data-theme-set="${w}"]`);
    await seite.waitForTimeout(150);
    return seite.evaluate(() => {
      const s = getComputedStyle(document.body);
      const zahl = getComputedStyle(document.querySelector(".kennliste .v")).color;
      return { grund: s.backgroundColor, text: s.color, zahl };
    });
  };
  const hell = await messen("light"), dunkel = await messen("dark");
  for (const t of [hell, dunkel]) {
    assert.ok(!/rgba\(0, 0, 0, 0\)|transparent/.test(t.grund), "Hintergrund muss gesetzt sein");
    assert.ok(t.text && t.zahl, "Textfarbe muss gesetzt sein");
  }
  assert.notEqual(hell.grund, dunkel.grund, "die Darstellungen müssen sich unterscheiden");

  const hell2 = c => c.match(/\d+/g).slice(0, 3).map(Number).reduce((a, b) => a + b, 0) / 3;
  assert.ok(hell2(hell.grund) > 180, "Papier muss hell sein");
  assert.ok(hell2(dunkel.grund) < 40, "Lichtpause muss wirklich dunkel sein");
  assert.ok(hell2(hell.text) < 90 && hell2(dunkel.text) > 170, "Text muss jeweils gegen den Grund stehen");
  await seite.click('[data-theme-set="system"]');
});

test("keine Farbe ist nur hinter einer Medienabfrage definiert", async () => {
  /* Der klassische Artefakt-Fehler: ein Wert lebt nur im dark-Block und fehlt im ungestempelten Zustand. */
  const tokens = await seite.evaluate(() => {
    const namen = [...document.styleSheets].flatMap(s => { try { return [...s.cssRules]; } catch { return []; } })
      .filter(r => r.selectorText === ":root")
      .flatMap(r => [...r.style].filter(n => n.startsWith("--")));
    const cs = getComputedStyle(document.documentElement);
    return namen.map(n => [n, cs.getPropertyValue(n).trim()]);
  });
  assert.ok(tokens.length > 15, `nur ${tokens.length} Tokens gefunden`);
  for (const [name, wert] of tokens) assert.ok(wert !== "", `${name} ist im Grundzustand leer`);
});

test("nichts läuft seitlich aus dem Bild", async () => {
  for (const id of ["tab-lageplan", "tab-einwerfen", "tab-haustyp", "tab-wege", "tab-vergleich", "tab-druck"]) {
    await seite.click("#" + id);
    await seite.waitForTimeout(150);
    const ueber = await seite.evaluate(() =>
      document.documentElement.scrollWidth - document.documentElement.clientWidth);
    assert.ok(ueber <= 1, `${id}: waagerechter Überlauf von ${ueber}px`);
  }
});

test("auf dem Telefon bleibt die Seite bedienbar", async () => {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const klein = await ctx.newPage();
  await klein.goto(adresse, { waitUntil: "load" });
  const ueber = await klein.evaluate(() =>
    document.documentElement.scrollWidth - document.documentElement.clientWidth);
  assert.ok(ueber <= 1, `waagerechter Überlauf von ${ueber}px bei 390px Breite`);
  assert.ok(await klein.isVisible("#buehne"));
  await ctx.close();
});

test("der Baukörper ist mit der Tastatur erreichbar und verschiebbar", async () => {
  await seite.click("#tab-lageplan");
  const vorher = await seite.textContent("#statustext");
  await seite.focus("#hauskoerper");
  for (let i = 0; i < 24; i++) await seite.keyboard.press("Shift+ArrowUp");
  await seite.waitForTimeout(150);
  assert.notEqual(await seite.textContent("#statustext"), vorher, "Pfeiltasten müssen den Baukörper bewegen");
  assert.match(await seite.textContent("#statustext"), /außerhalb des Bebauungsfensters/);
});
