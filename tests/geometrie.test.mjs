/* Prüft die Rechenkerne, auf denen alle Kennzahlen beruhen.
   Die Funktionen werden aus mockup/app.html gezogen — eine Quelle, kein Duplikat. */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const wurzel = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const quelle = readFileSync(resolve(wurzel, "mockup/app.html"), "utf8");
const von = quelle.indexOf("const flaeche = p =>");
const bis = quelle.indexOf("/* ══════════════════ Beispieldaten");
assert.ok(von > 0 && bis > von, "Rechenteil in mockup/app.html nicht gefunden");
const M = await import("data:text/javascript," + encodeURIComponent(quelle.slice(von, bis) +
  "\nexport { flaeche, kanten, schwerpunkt, bebauungsfenster, minRechteck, imPolygon, abstandZumRand, rechteckEcken, passtIns };"));

const QUADRAT = [{x:0,y:0},{x:10,y:0},{x:10,y:10},{x:0,y:10}];
const LIEBERTWOLKWITZ = [{x:0,y:0},{x:22.6,y:.9},{x:24.3,y:34.9},{x:1.6,y:36.2}];

test("Flächenformel trifft ein bekanntes Quadrat", () => {
  assert.equal(M.flaeche(QUADRAT), 100);
});

test("gerechnete Fläche weicht plausibel von der amtlichen ab", () => {
  const g = M.flaeche(LIEBERTWOLKWITZ);
  assert.ok(Math.abs(g - 795.3) < .1, `gerechnet ${g}`);
  const abw = Math.abs(802 - g);
  assert.ok(abw > 0 && abw < 15, `Abweichung ${abw} m² unplausibel`);
});

test("Innenversatz um 3 m verkleinert das Quadrat auf 4 × 4 m", () => {
  const f = M.bebauungsfenster(QUADRAT, [3,3,3,3]);
  assert.equal(f.length, 4);
  assert.ok(Math.abs(M.flaeche(f) - 16) < 1e-6, `Fläche ${M.flaeche(f)}`);
});

test("Tiefe je Grenzsegment wirkt einzeln", () => {
  const f = M.bebauungsfenster(QUADRAT, [5,3,3,3]);   // nur die Südgrenze tiefer
  assert.ok(Math.abs(M.flaeche(f) - 8) < 1e-6, `Fläche ${M.flaeche(f)}`);
});

test("zu tiefer Versatz lässt kein Bebauungsfenster übrig", () => {
  assert.deepEqual(M.bebauungsfenster(QUADRAT, [6,6,6,6]), []);
});

test("Bebauungsfenster hält überall den Abstand ein", () => {
  const f = M.bebauungsfenster(LIEBERTWOLKWITZ, [3,3,3,3]);
  assert.ok(f.length >= 3);
  for (const p of f) assert.ok(M.abstandZumRand(p, LIEBERTWOLKWITZ) > 2.99, "Punkt zu nah an der Grenze");
});

test("Rechteckigkeit: Quadrat ist 1, Liebertwolkwitz knapp darunter", () => {
  assert.ok(Math.abs(M.flaeche(QUADRAT) / M.minRechteck(QUADRAT).flaeche - 1) < 1e-9);
  const r = M.flaeche(LIEBERTWOLKWITZ) / M.minRechteck(LIEBERTWOLKWITZ).flaeche;
  assert.ok(Math.abs(r - .965) < .003, `Rechteckigkeit ${r}`);
});

test("Kantenlängen stimmen mit der Anzeige überein", () => {
  assert.deepEqual(M.kanten(LIEBERTWOLKWITZ).map(k => +k.laenge.toFixed(2)), [22.62, 34.04, 22.74, 36.24]);
});

test("Baukörper: 96,88 m² bei Verhältnis 1,35 ergibt rund 11,4 × 8,5 m", () => {
  const A = 96.88, b = Math.sqrt(A * 1.35), t = A / b;
  assert.ok(Math.abs(b - 11.4) < .1 && Math.abs(t - 8.5) < .1, `${b} × ${t}`);
  assert.ok(Math.abs(b * t - A) < 1e-9, "Fläche muss erhalten bleiben");
});

test("Drehung erhält die Grundfläche", () => {
  const A = h => M.flaeche(M.rechteckEcken(h));
  assert.ok(Math.abs(A({cx:10,cy:15,b:11.4,t:8.5,rot:0}) - A({cx:10,cy:15,b:11.4,t:8.5,rot:37})) < 1e-9);
});

test("Kollisionsprüfung schlägt an, sobald der Baukörper hinausrutscht", () => {
  const f = M.bebauungsfenster(LIEBERTWOLKWITZ, [3,3,3,3]);
  const drin = M.rechteckEcken({cx:10.8, cy:15, b:11.4, t:8.5, rot:-4});
  const raus = M.rechteckEcken({cx:10.8, cy:32, b:11.4, t:8.5, rot:-4});
  assert.equal(drin.filter(e => !M.imPolygon(e, f)).length, 0, "Startlage muss zulässig sein");
  assert.ok(raus.filter(e => !M.imPolygon(e, f)).length > 0, "Verschiebung nach Norden muss anschlagen");
});

test("Passt-Prüfung findet eine Lage und erkennt zu große Körper", () => {
  const f = M.bebauungsfenster(QUADRAT, [1,1,1,1]);        // Fenster 8 × 8 m
  const lage = M.passtIns(f, 7, 5);
  assert.ok(lage, "7 × 5 m muss in ein 8 × 8 m Fenster passen");
  assert.ok(M.rechteckEcken({ ...lage, b:7, t:5 }).every(p => M.imPolygon(p, f)), "gefundene Lage muss zulässig sein");
  assert.equal(M.passtIns(f, 9, 9), null, "9 × 9 m darf nicht hineinpassen");
});

test("Drehung wird bei der Passt-Prüfung genutzt", () => {
  const schmal = M.bebauungsfenster([{x:0,y:0},{x:9,y:0},{x:9,y:26},{x:0,y:26}], [.5,.5,.5,.5]); // 8 × 25 m
  assert.ok(M.passtIns(schmal, 20, 6), "20 × 6 m passt nur quer gestellt");
});
