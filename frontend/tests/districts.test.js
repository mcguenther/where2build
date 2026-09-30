/**
 * Matching against the cadastral district directory.
 *
 * The directory is the one the service really answers with, recorded into
 * `fixtures/gemarkungen.json` — 61 of the 5 339 Saxon districts, Mölkau among
 * them. No names are invented here: matching tested against made-up entries
 * would prove nothing about the umlaut or the key forms. These cases were the
 * picker's until the Gemarkung became a block in the one search field; the
 * matching is the same, so they stay.
 */
import { describe, it, expect } from "vitest";
import { searchDistricts } from "../src/lib/districts.js";
import directory from "./fixtures/gemarkungen.json";

const names = typed => searchDistricts(directory.gemarkungen, typed).hits.map(entry => entry.name);

describe("Gemarkung — Verzeichnis durchsuchen", () => {
  it("findet nichts, bevor etwas getippt ist", () => {
    expect(names("")).toEqual([]);
  });

  it("filtert nach dem Namen und führt Schlüssel und Gemeinde mit", () => {
    const [hit] = searchDistricts(directory.gemarkungen, "Mölk").hits;
    expect(names("Mölk")).toEqual(["Mölkau"]);
    expect(hit.schluessel).toBe("145592");
    expect(hit.gemeinde).toBe("Stadt Leipzig");
  });

  it("verzeiht den fehlenden Umlaut", () => {
    expect(names("Molkau")).toEqual(["Mölkau"]);
    expect(names("Grossdubrau")).toEqual([]);      // Gemeinde, nicht Gemarkung
    expect(names("Kronforstchen")).toEqual(["Kronförstchen"]);
  });

  it("findet über die vierstellige wie über die sechsstellige Schreibweise", () => {
    expect(names("5592")).toEqual(["Mölkau"]);
    expect(names("145592")).toEqual(["Mölkau"]);
    // Die Kurzform ohne führende Null, wie sie eine Tabelle hinterlässt.
    expect(names("0419")).toEqual(["Lauer"]);
    expect(names("419")).toEqual(["Lauer"]);
  });

  it("stellt den passendsten Treffer nach vorn", () => {
    // "Wölkau Flur 7" beginnt damit, "Mölkau" enthält es nur.
    expect(names("ölkau")).toEqual(["Wölkau Flur 7", "Mölkau"]);
  });

  it("begrenzt die Liste und sagt, wie viele es insgesamt sind", () => {
    const result = searchDistricts(directory.gemarkungen, "14");   // jeder sächsische Schlüssel beginnt so
    expect(result.hits).toHaveLength(50);
    expect(result.total).toBe(directory.gemarkungen.length);
  });
});
