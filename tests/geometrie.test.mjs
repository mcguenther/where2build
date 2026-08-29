/* Prüft die Geometrie, auf der alle Kennzahlen im Lageplan beruhen.
   Die Funktionen werden aus mockup/app.html gezogen — eine Quelle, kein Duplikat. */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const wurzel = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const quelle = readFileSync(resolve(wurzel, "mockup/app.html"), "utf8");

/* Den Rechenteil aus der Seite herauslösen und als Modul auswerten. */
const von = quelle.indexOf("const flaeche = p =>");
const bis = quelle.indexOf("/* ══════════════════ Zeichnen");
assert.ok(von > 0 && bis > von, "Rechenteil in mockup/app.html nicht gefunden");
const code = quelle.slice(von, bis).replace(/const nf = [^\n]+\n/, "");
const M = await import("data:text/javascript," + encodeURIComponent(
  code + "\nexport { flaeche, kanten, umfang, bebauungsfenster, minRechteck, imPolygon, abstandZumRand, rechteckEcken, FLURSTUECK, FLAECHE_AMTLICH };"
));

const QUADRAT = [{x:0,y:0},{x:10,y:0},{x:10,y:10},{x:0,y:10}];

test("Flächenformel trifft ein bekanntes Quadrat", () => {
  assert.equal(M.flaeche(QUADRAT), 100);
});

test("gerechnete Fläche weicht plausibel von der amtlichen ab", () => {
  const gerechnet = M.flaeche(M.FLURSTUECK);
  assert.ok(gerechnet > 780 && gerechnet < 810, `unerwartet: ${gerechnet}`);
  const abweichung = Math.abs(gerechnet - M.FLAECHE_AMTLICH);
  assert.ok(abweichung > 0, "amtliche und gerechnete Fläche dürfen nicht identisch sein");
  assert.ok(abweichung < 15, `Abweichung zu groß: ${abweichung} m²`);
});

test("Innenversatz um 3 m verkleinert das Quadrat auf 4 x 4 m", () => {
  const f = M.bebauungsfenster(QUADRAT, [3,3,3,3]);
  assert.equal(f.length, 4);
  assert.ok(Math.abs(M.flaeche(f) - 16) < 1e-6, `Fläche ${M.flaeche(f)}`);
});

test("Tiefe je Grenzsegment wirkt einzeln", () => {
  const f = M.bebauungsfenster(QUADRAT, [5,3,3,3]);          // nur die Südgrenze tiefer
  assert.ok(Math.abs(M.flaeche(f) - 4 * 2) < 1e-6, `Fläche ${M.flaeche(f)}`);
});

test("zu tiefer Versatz lässt kein Bebauungsfenster übrig", () => {
  assert.deepEqual(M.bebauungsfenster(QUADRAT, [6,6,6,6]), []);
});

test("Bebauungsfenster liegt vollständig im Flurstück", () => {
  const f = M.bebauungsfenster(M.FLURSTUECK, [3,3,3,3]);
  assert.ok(f.length >= 3);
  for (const p of f) assert.ok(M.abstandZumRand(p, M.FLURSTUECK) > 2.99, "Punkt zu nah an der Grenze");
});

test("Rechteckigkeit: Quadrat ist 1, das Flurstück knapp darunter", () => {
  assert.ok(Math.abs(M.flaeche(QUADRAT) / M.minRechteck(QUADRAT).flaeche - 1) < 1e-9);
  const r = M.flaeche(M.FLURSTUECK) / M.minRechteck(M.FLURSTUECK).flaeche;
  assert.ok(r > 0.9 && r < 1, `Rechteckigkeit ${r}`);
});

test("Kantenlängen des Flurstücks stimmen mit der Anzeige überein", () => {
  const l = M.kanten(M.FLURSTUECK).map(k => +k.laenge.toFixed(2));
  assert.deepEqual(l, [22.62, 34.04, 22.74, 36.24]);
});

test("Baukörper: 96,88 m² bei Verhältnis 1,35 ergibt rund 11,4 x 8,5 m", () => {
  const A = 96.88, v = 1.35;
  const b = Math.sqrt(A * v), t = A / b;
  assert.ok(Math.abs(b - 11.4) < 0.1, `Breite ${b}`);
  assert.ok(Math.abs(t - 8.5) < 0.1, `Tiefe ${t}`);
  assert.ok(Math.abs(b * t - A) < 1e-9, "Fläche muss erhalten bleiben");
});

test("Kollisionsprüfung schlägt an, sobald der Baukörper hinausgeschoben wird", () => {
  const f = M.bebauungsfenster(M.FLURSTUECK, [3,3,3,3]);
  const drin  = M.rechteckEcken({ cx:10.8, cy:15.0, b:11.4, t:8.5, rot:-4 });
  const raus  = M.rechteckEcken({ cx:10.8, cy:32.0, b:11.4, t:8.5, rot:-4 });
  assert.equal(drin.filter(e => !M.imPolygon(e, f)).length, 0, "Startlage muss zulässig sein");
  assert.ok(raus.filter(e => !M.imPolygon(e, f)).length > 0, "Verschiebung nach Norden muss anschlagen");
});

test("Drehung erhält die Grundfläche des Baukörpers", () => {
  const A = h => M.flaeche(M.rechteckEcken(h));
  const a0 = A({ cx:10.8, cy:15, b:11.4, t:8.5, rot:0 });
  const a1 = A({ cx:10.8, cy:15, b:11.4, t:8.5, rot:37 });
  assert.ok(Math.abs(a0 - a1) < 1e-9, `${a0} vs ${a1}`);
});
