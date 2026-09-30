/**
 * What the folded description marks before anything is sent.
 *
 * The text is the recorded Kleinanzeigen advert's own description; the
 * directory is the recorded one. The marks decide nothing, so what is tested
 * is mostly what they must *not* do: mark a word that only resembles a place.
 */
import { describe, it, expect } from "vitest";
import { markText, wordCount, MARK_LABELS } from "../src/lib/textMarks.js";
import gemarkungen from "./fixtures/gemarkungen.json";

const directory = gemarkungen.gemarkungen;
const marked = (result, kind) => result.segments.filter(s => s.kind === kind).map(s => s.text);

describe("markText", () => {
  it("findet die Fläche in der Schreibweise der Anzeige", () => {
    const result = markText("Das Grundstück hat ca. 1.025 qm und liegt ruhig.");
    expect(marked(result, "area")).toEqual(["ca. 1.025 qm"]);
    expect(result.kinds).toEqual(["area"]);
  });

  it("markiert Planungsrecht nur, wo es so dasteht", () => {
    const result = markText("entsprechend §34 BauGB ist eine Bebauung möglich");
    expect(marked(result, "law")).toEqual(["§34 BauGB"]);
  });

  it("findet einen Gemarkungsnamen aus dem Verzeichnis", () => {
    const name = directory.find(entry => entry.name === "Mölkau").name;
    const result = markText(`Baugrundstück in ${name}, ruhige Seitenstraße`, directory);
    expect(marked(result, "place")).toEqual([name]);
  });

  it("markiert ohne Verzeichnis keinen Ort", () => {
    expect(markText("Baugrundstück in Mölkau").kinds).toEqual([]);
  });

  it("markiert kein kleingeschriebenes Wort, auch wenn es wie ein Ort heißt", () => {
    const result = markText("mölkau steht hier klein", directory);
    expect(marked(result, "place")).toEqual([]);
  });

  it("setzt den Text aus den Stücken unverändert wieder zusammen", () => {
    const text = "Hier könnte Ihr neues Eigenheim stehen... §34 BauGB, ca. 1.025 qm in Mölkau.";
    const result = markText(text, directory);
    expect(result.segments.map(s => s.text).join("")).toBe(text);
    expect(result.first).toBe(text.indexOf("§34"));
  });

  it("nennt die Arten in fester Reihenfolge", () => {
    const result = markText("Mölkau, §35 BauGB, 800 m²", directory);
    expect(result.kinds).toEqual(Object.keys(MARK_LABELS));
  });
});

describe("wordCount", () => {
  it("zählt Wörter, nicht Zeichen", () => {
    expect(wordCount("Das Grundstück hat ca. 1.025 qm.")).toBe(6);
    expect(wordCount("")).toBe(0);
  });
});
