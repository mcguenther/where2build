/**
 * The search field: what it asks, and what it refuses to ask.
 *
 * `queryInput.js` already has its own tests for the reading itself. What is
 * tested here is that the field *acts* on that reading — a leading digit costs
 * the address index no request, a coordinate costs nothing at all, and where
 * two readings stay plausible both local indexes are asked instead of one
 * being guessed.
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import PlotSearch from "../src/components/PlotSearch.vue";
import gemarkungen from "./fixtures/gemarkungen.json";

/** What `/api/geocode` answers for "Lessingweg 44", official hits first. */
const GEOCODE = {
  treffer: [
    {
      lat: 51.33655, lon: 12.44181, name: "Lessingweg 44",
      beschreibung: "04316 Leipzig · Mölkau", art: "adresse"
    }
  ],
  hinweis: "Amtliche Hauskoordinaten des GeoSN.",
  quelle: "Amtliche Hauskoordinaten (GeoSN, dl-de/by-2-0)"
};

let asked;

const answer = body => ({ ok: true, status: 200, json: () => Promise.resolve(body) });

beforeEach(() => {
  asked = [];
  vi.useFakeTimers();
  globalThis.fetch = url => {
    asked.push(String(url));
    if (String(url).includes("/geocode")) return Promise.resolve(answer(GEOCODE));
    if (String(url).includes("/gemarkungen")) return Promise.resolve(answer(gemarkungen));
    return Promise.resolve(answer({}));
  };
});

/** Type, let the debounce elapse, and let every request settle. */
async function type(field, text) {
  const input = field.find("input");
  input.element.value = text;
  await input.trigger("input");
  await vi.advanceTimersByTimeAsync(200);
  await flushPromises();
}

describe("Suchfeld", () => {
  it("erkennt eine Koordinate und fragt dafür keinen Dienst", async () => {
    const field = mount(PlotSearch);
    await type(field, "51.33652, 12.44176");

    expect(asked).toEqual([]);
    expect(field.text()).toContain("Koordinate");
    expect(field.findAll(".hit")).toHaveLength(1);
    field.unmount();
  });

  it("liest die deutsche Schreibweise mit Dezimalkomma", async () => {
    const field = mount(PlotSearch);
    await type(field, "51,33652, 12,44176");

    expect(asked).toEqual([]);
    expect(field.find(".hit__name").text()).toContain("51,33652");
    field.unmount();
  });

  it("nimmt eine UTM-33-Koordinate, wie sie im Geoportal steht", async () => {
    const field = mount(PlotSearch);
    await type(field, "321880 5690360");

    expect(asked).toEqual([]);
    expect(field.text()).toContain("UTM 33");
    // The projection lives in the backend; the field sends what was typed.
    field.find(".hit").trigger("mousedown");
    await flushPromises();
    expect(field.emitted("select")[0][0].query).toEqual({ easting: 321880, northing: 5690360 });
    field.unmount();
  });

  it("fragt den Adressindex nicht, wenn die Eingabe mit einer Ziffer beginnt", async () => {
    const field = mount(PlotSearch);
    await type(field, "204");

    expect(asked.some(url => url.includes("/geocode"))).toBe(false);
    field.unmount();
  });

  it("sagt bei einer Flurstücksnummer, welche Hälfte fehlt", async () => {
    const field = mount(PlotSearch);
    await type(field, "85/1");

    expect(field.text()).toContain("gehört die Gemarkung");
    expect(field.findAll(".hit")).toHaveLength(0);
    field.unmount();
  });

  it("fragt bei einer mehrdeutigen Eingabe beide Verzeichnisse", async () => {
    const field = mount(PlotSearch);
    await type(field, "Mölkau 204");

    expect(asked.some(url => url.includes("/geocode"))).toBe(true);
    const kinds = field.findAll(".hit__kind").map(node => node.text());
    expect(kinds).toContain("Flurstück");
    expect(kinds).toContain("Adresse");
    field.unmount();
  });

  it("gibt bei einer Adresse den amtlichen Treffer weiter", async () => {
    const field = mount(PlotSearch);
    await type(field, "Lessingweg 44");
    // "Lessingweg 44" also reads as Gemarkung + parcel number, and both rows
    // are offered — so the address is picked by its kind, not by its text.
    const address = field.findAll(".hit")
      .find(hit => hit.find(".hit__kind").text() === "Adresse");
    await address.trigger("mousedown");
    await flushPromises();

    expect(field.emitted("select")[0][0].query).toEqual({ lat: 51.33655, lon: 12.44181 });
    expect(field.emitted("select")[0][0].label).toBe("Adresse: Lessingweg 44");
    field.unmount();
  });

  it("stellt in einer Zeile die Adresse vor die Kategorie", async () => {
    // Vorher stand die Kategorie links und der Treffer rechts: die Zeile las
    // sich „Adresse … Lessingweg 44“ — die nützliche Hälfte zuletzt und am
    // weitesten weg vom Tippen.
    const field = mount(PlotSearch);
    await type(field, "Lessingweg 44");

    const row = field.findAll(".hit")
      .find(hit => hit.find(".hit__kind").text() === "Adresse");
    const parts = [...row.element.children].map(node => node.className);
    expect(parts[0]).toBe("hit__name");
    expect(parts[1]).toBe("hit__kind");
    expect(row.find(".hit__name").text()).toContain("Lessingweg 44");
    field.unmount();
  });

  it("meldet eine gewählte Gemarkung, statt sie aufzulösen", async () => {
    const field = mount(PlotSearch);
    await type(field, "Mölkau");

    const district = field.findAll(".hit").find(hit => hit.text().includes("Gemarkung"));
    expect(district).toBeTruthy();
    await district.trigger("mousedown");
    await flushPromises();

    // Half an answer: the wrapper turns it into a block and the number is
    // typed after it. Nothing is resolved, and the text is not rewritten.
    expect(field.emitted("select")).toBeUndefined();
    expect(field.emitted("district")[0][0].name).toBe("Mölkau");
    field.unmount();
  });

  it("fragt nach einer Nummer nur noch das Gemarkungsverzeichnis", async () => {
    const field = mount(PlotSearch, { props: { onlyDistricts: true } });
    await type(field, "Mölk");

    expect(asked.some(url => url.includes("/geocode"))).toBe(false);
    const kinds = field.findAll(".hit__kind").map(kind => kind.text());
    expect(kinds.length).toBeGreaterThan(0);
    expect(new Set(kinds)).toEqual(new Set(["Gemarkung"]));
    field.unmount();
  });

  it("fragt nichts, solange der Wrapper weiß, was im Feld steht", async () => {
    const field = mount(PlotSearch, { props: { quiet: true } });
    await type(field, "Lessingweg 44");

    expect(asked).toEqual([]);
    expect(field.findAll(".hit")).toHaveLength(0);
    field.unmount();
  });

  it("meldet Rückschritt im leeren Feld, damit der Block davor gehen kann", async () => {
    const field = mount(PlotSearch);
    await field.find("input").trigger("keydown", { key: "Backspace" });
    expect(field.emitted("backspace")).toHaveLength(1);

    await type(field, "M");
    await field.find("input").trigger("keydown", { key: "Backspace" });
    expect(field.emitted("backspace")).toHaveLength(1);
    field.unmount();
  });

  it("lässt eine langsame Antwort auf eine ältere Eingabe nicht gewinnen", async () => {
    const slow = new Map();
    globalThis.fetch = url => {
      asked.push(String(url));
      if (String(url).includes("/geocode")) {
        return new Promise(resolve => slow.set(asked.length, () => resolve(answer(GEOCODE))));
      }
      return Promise.resolve(answer(gemarkungen));
    };
    const field = mount(PlotSearch);

    const input = field.find("input");
    input.element.value = "Lessing";
    await input.trigger("input");
    await vi.advanceTimersByTimeAsync(200);

    input.element.value = "51.33652, 12.44176";
    await input.trigger("input");
    await vi.advanceTimersByTimeAsync(200);

    // The first request answers only now, for text nobody is looking at.
    slow.forEach(resolve => resolve());
    await flushPromises();

    const kinds = field.findAll(".hit__kind").map(node => node.text());
    expect(kinds).toEqual(["Koordinate"]);
    field.unmount();
  });
});
