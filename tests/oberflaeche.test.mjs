/* Fährt das Mockup im echten Browser: Navigation, Speicherung, Datenaustausch,
   die farbige Markierung des Randstreifens und der Kontrast beider Darstellungen. */
import { test, before, after, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { chromium } from "/opt/node22/lib/node_modules/playwright/index.mjs";
import { resolve, dirname } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const wurzel = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const adresse = pathToFileURL(resolve(wurzel, "mockup/index.html")).href;
const umgebung = t => /ERR_CONNECTION|ERR_NAME_NOT_RESOLVED|ERR_FAILED|Failed to load resource|fonts\.(googleapis|gstatic)/.test(t);

let browser, ctx, seite, fehler;
before(async () => { browser = await chromium.launch(); });
after(async () => { await browser.close(); });
beforeEach(async () => {
  if (ctx) await ctx.close();
  ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  /* Schriften kommen aus dem Netz; in abgeschotteten Umgebungen hängt der Abruf
     und macht jeden Testlauf langsam. Für die Prüfungen hier sind sie ohne Belang. */
  await ctx.route(/fonts\.(googleapis|gstatic)\.com/, r => r.abort());
  seite = await ctx.newPage();
  fehler = [];
  seite.on("pageerror", e => fehler.push(e.message));
  seite.on("console", m => { if (m.type() === "error" && !umgebung(m.text())) fehler.push(m.text()); });
  await seite.goto(adresse, { waitUntil: "load" });
});
const sichtbar = () => seite.$$eval(".ansicht", ns => ns.filter(n => !n.hidden).map(n => n.id));

test("die Seite lädt ohne Skriptfehler und zeigt genau eine Ansicht", async () => {
  assert.deepEqual(fehler, [], fehler.join(" | "));
  assert.deepEqual(await sichtbar(), ["a-uebersicht"]);
  assert.equal(await seite.$$eval(".gkarte:not(.leerkarte)", n => n.length), 4);
});

test("jeder Bereich der Kopfleiste ist erreichbar", async () => {
  for (const [ort, id] of [["haustypen","a-haustypen"],["ziele","a-ziele"],["daten","a-daten"],["uebersicht","a-uebersicht"]]) {
    await seite.click(`.orte [data-ort="${ort}"]`);
    assert.deepEqual(await sichtbar(), [id], `Bereich ${ort}`);
  }
  assert.deepEqual(fehler, [], fehler.join(" | "));
});

test("von der Übersicht ins Detail und über die Brotkrume zurück", async () => {
  await seite.click(".gkarte .knopf");
  assert.deepEqual(await sichtbar(), ["a-grundstueck"]);
  assert.equal(await seite.textContent("#krume-name"), "Muldentalstraße");
  await seite.click('#a-grundstueck .krume [data-ort="uebersicht"]');
  assert.deepEqual(await sichtbar(), ["a-uebersicht"]);
});

test("Kennzahlen sind gerechnet, nicht als Strich stehengeblieben", async () => {
  await seite.click(".gkarte .knopf");
  const werte = await seite.$$eval("#k-flaeche-gerechnet,#k-front,#k-rechteckig,#k-mrr,#k-hausmass,#k-grz,#k-jem2",
    ns => ns.map(n => n.textContent.trim()));
  for (const w of werte) assert.ok(w && w !== "—", `leere Kennzahl "${w}"`);
  assert.match(await seite.textContent("#k-flaeche-gerechnet"), /795,3 m²/);
  assert.match(await seite.textContent("#k-jem2"), /235,66 €/);
});

test("markiert wird der Randstreifen, nicht der bebaubare Bereich", async () => {
  await seite.click(".gkarte .knopf");
  const ring = await seite.$eval("#buehne path[fill-rule='evenodd']", n => ({
    regel: n.getAttribute("fill-rule"), fuellung: n.getAttribute("fill"), d: n.getAttribute("d")
  }));
  assert.equal(ring.regel, "evenodd", "ohne evenodd wäre die Mitte mitgefärbt");
  assert.equal(ring.fuellung, "var(--saum)");
  assert.equal((ring.d.match(/M/g) || []).length, 2, "Außen- und Innenring gehören in einen Pfad");
  /* Der bebaubare Bereich selbst darf keine eigene Füllung tragen. */
  const fenster = await seite.$$eval("#buehne polygon[stroke-dasharray='7 5']", ns => ns.map(n => n.getAttribute("fill")));
  assert.ok(fenster.length && fenster.every(f => f === "none"), `Fensterfüllung: ${fenster}`);
});

test("Abstandsflächen lassen sich je Grenze setzen und schlagen an", async () => {
  await seite.click(".gkarte .knopf");
  const namen = await seite.$$eval("#segment-zeilen .kante", n => n.map(x => x.textContent.trim()));
  assert.equal(namen.length, 4);
  assert.match(namen[0], /zur Straße$/);
  for (const n of namen) assert.doesNotMatch(n, /^Grenze \d/, `Grenze nicht benannt: ${n}`);
  const felder = seite.locator("#segment-zeilen input");
  for (let i = 0; i < await felder.count(); i++) {
    await felder.nth(i).fill("9"); await felder.nth(i).dispatchEvent("input");
  }
  await seite.waitForTimeout(150);
  assert.equal(await seite.$eval("#statusbanner", n => n.classList.contains("ok")), false);
  assert.match(await seite.textContent("#statustext"), /außerhalb des Bebauungsfensters/);
});

test("Auswahl steuert den Vergleich, Abwählen nimmt heraus", async () => {
  assert.match(await seite.textContent("#auswahl-zaehler"), /4 Grundstücke/);
  await seite.uncheck(".gkarte:first-of-type .wahl input");
  assert.match(await seite.textContent("#auswahl-zaehler"), /3 Grundstücke/);
  await seite.click("#k-vergleichen");
  assert.deepEqual(await sichtbar(), ["a-vergleich"]);
  assert.equal(await seite.$$eval("#vgl-zeilen tr", n => n.length), 3);
  await seite.click('#a-vergleich .krume [data-ort="uebersicht"]');
  await seite.click("#k-keine");
  assert.equal(await seite.isDisabled("#k-vergleichen"), true, "unter zwei Kandidaten kein Vergleich");
});

test("ein Grundstück lässt sich aufnehmen und wieder entfernen", async () => {
  await seite.click("#k-aufnahme");
  await seite.click('[data-lesen="url"]');
  assert.ok(await seite.isVisible("#gelesen"));
  const belege = await seite.$$eval(".vorschlag .quelle", n => n.map(x => x.textContent.trim()));
  assert.ok(belege.every(b => b.length > 5), "jedes Feld braucht eine Quellenangabe");
  await seite.click("#k-uebernehmen");
  assert.deepEqual(await sichtbar(), ["a-grundstueck"]);
  await seite.click('#a-grundstueck .krume [data-ort="uebersicht"]');
  assert.equal(await seite.$$eval(".gkarte:not(.leerkarte)", n => n.length), 5);
  seite.once("dialog", d => d.accept());
  await seite.click(".gkarte:nth-of-type(5) [data-weg]");
  await seite.waitForTimeout(150);
  assert.equal(await seite.$$eval(".gkarte:not(.leerkarte)", n => n.length), 4);
});

test("der Stand überlebt das Neuladen", async () => {
  await seite.click(".gkarte .knopf");
  const feld = seite.locator("#segment-zeilen input").first();
  await feld.fill("4.7"); await feld.dispatchEvent("input");
  await seite.waitForTimeout(150);
  await seite.reload({ waitUntil: "load" });
  await seite.click(".gkarte .knopf");
  assert.equal(await seite.inputValue("#segment-zeilen input"), "4.7");
});

test("Ausgeben und Einlesen erhalten den Stand", async () => {
  await seite.click('.orte [data-ort="daten"]');
  const j = await seite.inputValue("#d-aus");
  const d = JSON.parse(j);
  assert.equal(d.grundstuecke.length, 4);
  assert.ok(d.haustypen.length && d.ziele.length);
  assert.ok(d.grundstuecke[0].polygon.every(p => typeof p.x === "number"));

  const geaendert = structuredClone(d);
  geaendert.grundstuecke = geaendert.grundstuecke.slice(0, 2);
  geaendert.grundstuecke[0].name = "Umbenannt";
  await seite.fill("#d-ein", JSON.stringify(geaendert));
  await seite.click("#k-einlesen");
  assert.match(await seite.textContent("#m-ein"), /2 Grundstücke/);
  await seite.click('.orte [data-ort="uebersicht"]');
  assert.equal(await seite.$$eval(".gkarte:not(.leerkarte)", n => n.length), 2);
  assert.match(await seite.textContent(".gkarte h3"), /Umbenannt/);
});

test("unbrauchbares JSON wird abgelehnt, statt den Stand zu zerstören", async () => {
  await seite.click('.orte [data-ort="daten"]');
  for (const müll of ['{"grundstuecke":"nein"}', "{}", "kein json", '{"grundstuecke":[{"name":"ohne Geometrie"}]}']) {
    await seite.fill("#d-ein", müll);
    await seite.click("#k-einlesen");
    assert.ok(await seite.$eval("#m-ein", n => n.classList.contains("fehler")), `angenommen: ${müll}`);
  }
  await seite.click('.orte [data-ort="uebersicht"]');
  assert.equal(await seite.$$eval(".gkarte:not(.leerkarte)", n => n.length), 4, "der Stand muss unberührt bleiben");
});

test("die Haustyp-Karte prüft, wo der Baukörper hinpasst", async () => {
  await seite.click('.orte [data-ort="haustypen"]');
  const ueber = await seite.$$eval(".passt .ueberschrift", n => n.map(x => x.textContent));
  assert.equal(ueber.length, 4);
  for (const u of ueber) assert.match(u, /^Passt auf \d von 4 Grundstücken$/);
  assert.ok(ueber.some(u => !u.startsWith("Passt auf 4")), "ein zu großer Typ muss auch auffallen");
  /* Use Case B: neuen Haustyp auf einem Grundstück ausprobieren */
  await seite.click(".htkarte:last-of-type .passt .reihe button");
  assert.deepEqual(await sichtbar(), ["a-grundstueck"]);
  assert.ok(await seite.$eval("#statusbanner", n => n.classList.contains("ok")),
    "die vorgeschlagene Lage muss zulässig sein");
});

test("Kartenausrichtung dreht die Szene, der Nordpfeil hält dagegen", async () => {
  await seite.click(".gkarte .knopf");
  const dreh = () => seite.$eval("#buehne g[transform^='rotate']", n => n.getAttribute("transform"));
  assert.match(await dreh(), /^rotate\(0,/);
  await seite.click('[data-nord="1"]');
  assert.match(await dreh(), /^rotate\(17,/);
});

test("beide Darstellungen setzen Grund und Text und trennen sich deutlich", async () => {
  const messen = async w => {
    await seite.click(`[data-theme-set="${w}"]`);
    await seite.waitForTimeout(150);
    return seite.evaluate(() => ({
      grund: getComputedStyle(document.body).backgroundColor,
      text: getComputedStyle(document.body).color,
      saum: getComputedStyle(document.documentElement).getPropertyValue("--saum").trim()
    }));
  };
  const hell = await messen("light"), dunkel = await messen("dark");
  const mittel = c => c.match(/\d+/g).slice(0, 3).map(Number).reduce((a, b) => a + b, 0) / 3;
  assert.ok(mittel(hell.grund) > 180 && mittel(dunkel.grund) < 40, "Papier hell, Lichtpause wirklich dunkel");
  assert.ok(mittel(hell.text) < 90 && mittel(dunkel.text) > 170, "Text muss gegen den Grund stehen");
  assert.ok(hell.saum && dunkel.saum && hell.saum !== dunkel.saum, "der Randstreifen braucht je Darstellung einen eigenen Wert");
});

test("keine Farbe ist nur hinter einer Medienabfrage definiert", async () => {
  const tokens = await seite.evaluate(() => {
    const namen = [...document.styleSheets].flatMap(s => { try { return [...s.cssRules]; } catch { return []; } })
      .filter(r => r.selectorText === ":root").flatMap(r => [...r.style].filter(n => n.startsWith("--")));
    const cs = getComputedStyle(document.documentElement);
    return namen.map(n => [n, cs.getPropertyValue(n).trim()]);
  });
  assert.ok(tokens.length > 20, `nur ${tokens.length} Tokens`);
  for (const [name, wert] of tokens) assert.ok(wert !== "", `${name} ist im Grundzustand leer`);
});

test("nichts läuft seitlich aus dem Bild — auch nicht auf dem Telefon", async () => {
  const ueberlauf = () => seite.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  for (const ort of ["haustypen", "ziele", "daten", "uebersicht"]) {
    await seite.click(`.orte [data-ort="${ort}"]`);
    assert.ok(await ueberlauf() <= 1, `${ort}: ${await ueberlauf()}px Überlauf`);
  }
  await seite.click(".gkarte .knopf");
  assert.ok(await ueberlauf() <= 1, `Detail: ${await ueberlauf()}px Überlauf`);
  await seite.setViewportSize({ width: 390, height: 844 });
  await seite.waitForTimeout(200);
  assert.ok(await ueberlauf() <= 1, `Detail auf 390px: ${await ueberlauf()}px Überlauf`);
  assert.ok(await seite.isVisible("#buehne"));
});

test("der Baukörper ist mit der Tastatur verschiebbar", async () => {
  await seite.click(".gkarte .knopf");
  const vorher = await seite.textContent("#statustext");
  await seite.focus("#hauskoerper");
  for (let i = 0; i < 26; i++) await seite.keyboard.press("Shift+ArrowUp");
  await seite.waitForTimeout(150);
  assert.notEqual(await seite.textContent("#statustext"), vorher);
  assert.match(await seite.textContent("#statustext"), /außerhalb des Bebauungsfensters/);
});

test("Muster-Kennungen kollidieren nicht zwischen Lageplan und Druckblatt", async () => {
  await seite.click(".gkarte .knopf");
  const doppelt = await seite.evaluate(() => {
    const ids = [...document.querySelectorAll("[id]")].map(n => n.id);
    return [...new Set(ids.filter((v, i) => ids.indexOf(v) !== i))];
  });
  assert.deepEqual(doppelt, [], `doppelte Kennungen: ${doppelt}`);
});
