/**
 * The preview at the head of the search step.
 *
 * Both answers are real: the backend's own `/api/listings/extract` run on the
 * recorded Kleinanzeigen page (`backend/tests/fixtures/inserat-kleinanzeigen.html`)
 * — once as the whole document the bookmarklet hands over, once as the body a
 * Strg+A copy brings. Nothing here is invented; where a test needs a value to
 * be missing it takes one away from a real answer.
 */
import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import ListingPreview from "../src/components/ListingPreview.vue";
import whole from "./fixtures/extract-kleinanzeigen-dokument.json";
import pasted from "./fixtures/extract-kleinanzeigen-einfuegen.json";

const LINK = "https://www.kleinanzeigen.de/s-anzeige/baugrundstueck-ca-1-025qm-direkt-bebaubar/3423861748-207-3935";

const without = (answer, ...keys) => {
  const copy = structuredClone(answer);
  for (const key of keys) {
    if (key in copy) copy[key] = Array.isArray(copy[key]) ? [] : null;
    else copy.felder[key] = { ...copy.felder[key], wert: null };
  }
  return copy;
};

const preview = (props, slot = "<p class='im-fach'>Felder</p>") =>
  mount(ListingPreview, { props: { summary: "4 von 6 Feldern belegt", ...props }, slots: { default: slot } });

describe("Vorschau eines Links", () => {
  it("zeigt Titel, Portal mit Anzeigennummer und die gelesenen Werte", () => {
    const w = preview({ response: whole, kind: "url", url: LINK });

    expect(w.find(".titel").text()).toBe("Baugrundstück - ca. 1.025qm - direkt bebaubar");
    expect(w.find(".quelle").text()).toContain("kleinanzeigen.de · Nr. 3423861748");
    expect(w.find(".fav").text()).toBe("k");
    const chips = w.findAll(".wert").map(c => c.text().replace(/\s/g, " "));
    expect(chips).toEqual(["80.000 €", "1.025 m²", "Sachsen - Neukieritzsch", "3 Bilder"]);
  });

  it("öffnet die Anzeige in einem eigenen Tab, ohne Verweis auf diese Seite", () => {
    const link = preview({ response: whole, kind: "url", url: LINK }).find("a.lk");

    expect(link.text()).toBe("Öffnen ↗");
    expect(link.attributes("href")).toBe(LINK);
    expect(link.attributes("target")).toBe("_blank");
    expect(link.attributes("rel")).toBe("noopener noreferrer");
  });

  it("lädt das Bild vom Portal ohne Referrer und erst bei Bedarf", () => {
    const img = preview({ response: whole, kind: "url", url: LINK }).find(".bild img");

    expect(img.attributes("src")).toBe(whole.bilder[0]);
    expect(img.attributes("referrerpolicy")).toBe("no-referrer");
    expect(img.attributes("loading")).toBe("lazy");
  });

  it("lässt die Fläche grau, wenn die Anzeige kein Bild hat", () => {
    const w = preview({ response: without(whole, "bilder"), kind: "url", url: LINK });

    expect(w.find(".bild").exists()).toBe(true);
    expect(w.find(".bild img").exists()).toBe(false);
    expect(w.text()).not.toContain("Bilder");
  });

  it("lässt die Fläche grau, wenn das Bild nicht lädt", async () => {
    const w = preview({ response: whole, kind: "url", url: LINK });

    await w.find(".bild img").trigger("error");

    expect(w.find(".bild").exists()).toBe(true);
    expect(w.find(".bild img").exists()).toBe(false);
  });

  it("nennt ohne erkennbare Nummer nur das Portal, und nichts, was fehlt", () => {
    const w = preview({
      response: without(whole, "titel", "kaufpreis_eur"), kind: "url", url: "https://www.example.org/expose/110185322"
    });

    expect(w.find(".quelle span:last-child").text()).toBe("example.org");
    expect(w.find(".titel").exists()).toBe(false);
    expect(w.text()).not.toContain("€");
  });
});

describe("Vorschau einer eingefügten Seite", () => {
  it("baut die Miniatur nur aus dem, was gelesen wurde, mit nummerierten Fundstellen", () => {
    const w = preview({ response: pasted, kind: "page" });

    const findings = w.findAll(".befund li:not(.fehlt)")
      .map(li => li.findAll("span").map(s => s.text()).join(" ").replace(/\s+/g, " "));
    expect(findings).toEqual([
      "1 Titel Baugrundstück - ca. 1.025qm - direkt bebaubar",
      "2 3 Bilder – die Suche liest sie nach einem Katasterauszug, wenn der Text allein nicht reicht",
      "3 Preis 80.000 €",
      "4 Ort 04575 Neukieritzsch, Sachsen",
      "5 Fläche 1.025 m²"
    ]);
    // Dieselben Nummern stehen in der Miniatur, jede an ihrer Stelle.
    expect(w.findAll(".mini .pin").map(p => p.text())).toEqual(["1", "2", "3", "4", "5"]);
    expect(w.find(".mini__titel").text()).toBe(pasted.titel);
    expect(w.find(".mini__preis").text().replace(/\s/g, " ")).toBe("80.000 €");
    // One big picture, the rest as the strip, all from the portal.
    expect(w.find(".mini__foto img").attributes("src")).toBe(pasted.bilder[0]);
    expect(w.findAll(".mini__klein img").map(i => i.attributes("src"))).toEqual(pasted.bilder.slice(1));
    // Eine Seite aus der Zwischenablage weiß nicht, von welchem Portal sie kommt.
    expect(w.find(".mini__kopf").text()).toBe("Eingefügte Seite");
  });

  it("sagt, dass die Koordinate fehlt, und bietet das Lesezeichen an", async () => {
    const w = preview({ response: pasted, kind: "page" });

    const missing = w.find(".befund li.fehlt");
    expect(missing.text()).toContain("Koordinate fehlt – der Kopf der Seite kam nicht mit.");
    await missing.find("button").trigger("click");
    expect(w.emitted("bookmarklet")).toHaveLength(1);
  });

  it("vermisst keine Koordinate, wenn das ganze Dokument kam", () => {
    const w = preview({ response: whole, kind: "page", url: LINK });

    expect(w.find(".befund li.fehlt").exists()).toBe(false);
    expect(w.find(".mini__kopf").text()).toContain("kleinanzeigen.de");
  });

  it("zählt fehlende Angaben nicht mit und nummeriert ohne Lücke", () => {
    const w = preview({ response: without(pasted, "titel", "kaufpreis_eur"), kind: "page" });

    const labels = w.findAll(".befund li:not(.fehlt) b").map(b => b.text());
    expect(labels).toEqual(["3 Bilder", "Ort", "Fläche"]);
    expect(w.findAll(".befund li:not(.fehlt) .pin").map(p => p.text())).toEqual(["1", "2", "3"]);
    expect(w.find(".mini__titel").exists()).toBe(false);
    expect(w.find(".mini__preis").exists()).toBe(false);
  });

  it("grauen ein Bild der Leiste aus, das nicht lädt, statt es zu brechen", async () => {
    const w = preview({ response: pasted, kind: "page" });

    await w.findAll(".mini__klein img")[0].trigger("error");

    expect(w.findAll(".mini__klein")).toHaveLength(pasted.bilder.length - 1);
    expect(w.findAll(".mini__klein img")).toHaveLength(pasted.bilder.length - 2);
  });
});

describe("Klappkasten der gelesenen Werte", () => {
  it("behält die Klassen, auf die Skript und Bilderlauf warten", () => {
    const w = preview({ response: pasted, kind: "page", summary: "4 von 6 Feldern belegt" });

    const fold = w.find("details.gelesen");
    expect(fold.exists()).toBe(true);
    expect(fold.classes()).not.toContain("gelesen--lesezeichen");
    expect(fold.find(".gelesen__titel").text()).toBe("Gelesene Werte");
    expect(fold.find(".gelesen__zahl").text()).toBe("4 von 6 Feldern belegt");
    expect(fold.find(".im-fach").exists()).toBe(true);
    expect(fold.attributes("open")).toBeUndefined();
  });

  it("zeigt bei getipptem Text nur den Klappkasten", () => {
    const w = preview({ response: pasted, kind: "prose" });

    expect(w.find(".karte").exists()).toBe(false);
    expect(w.find(".mini").exists()).toBe(false);
    expect(w.find("details.gelesen").exists()).toBe(true);
  });

  it("zeichnet ohne belegte Werte keinen leeren Kasten", () => {
    const w = preview({ response: pasted, kind: "prose", summary: "" });

    expect(w.html()).toBe("<!--v-if-->");
  });
});
