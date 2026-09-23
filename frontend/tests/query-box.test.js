/**
 * The one field the start page offers.
 *
 * `queryInput.js` decides what was typed and `PlotSearch` offers the rows; what
 * is tested here is the layer above both — the chips that say how the input was
 * read, the click that overrules that reading, and the two things the box hands
 * on: `resolve` when the cadastre can simply be asked, `read` when the text has
 * to be read first. The box resolves nothing itself, so nothing here asserts an
 * answer from a service; the directory is the recorded one.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import QueryBox from "../src/components/QueryBox.vue";
import gemarkungen from "./fixtures/gemarkungen.json";

/** The one district in the recorded directory this test types. */
const MOELKAU = gemarkungen.gemarkungen.find(entry => entry.name === "Mölkau");

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

const answer = body => ({ ok: true, status: 200, json: () => Promise.resolve(body) });

beforeEach(() => {
  vi.useFakeTimers();
  globalThis.fetch = url => {
    if (String(url).includes("/geocode")) return Promise.resolve(answer(GEOCODE));
    if (String(url).includes("/gemarkungen")) return Promise.resolve(answer(gemarkungen));
    return Promise.resolve(answer({}));
  };
});

afterEach(() => {
  vi.useRealTimers();
});

/** Type into the one field, let the debounce elapse and every request settle. */
async function type(box, text) {
  const input = box.find(".search__field input");
  input.element.value = text;
  await input.trigger("input");
  await vi.advanceTimersByTimeAsync(200);
  await flushPromises();
}

/** A chip by its German name. A fixed one carries the ✕ that takes it back. */
const chip = (box, name) =>
  box.findAll(".kind").find(button => button.text().replace("✕", "").trim() === name);

const button = box => box.find(".query-box__field button");

describe("QueryBox", () => {
  it("zeigt an einer Adresse den Chip „Adresse“ als gelesen", async () => {
    const box = mount(QueryBox);
    await type(box, "Lessingweg 44");

    expect(chip(box, "Adresse").attributes("data-state")).toBe("read");
    // Read, not decided: nothing was pressed, so nothing is fixed.
    expect(chip(box, "Adresse").attributes("aria-pressed")).toBe("false");
    expect(chip(box, "Koordinate").attributes("data-state")).toBe("off");
    box.unmount();
  });

  it("legt eine Lesart auf Klick fest und gibt sie auf den zweiten wieder frei", async () => {
    const box = mount(QueryBox);
    await type(box, "Lessingweg 44");

    await chip(box, "Koordinate").trigger("click");
    expect(chip(box, "Koordinate").attributes("data-state")).toBe("set");
    expect(chip(box, "Koordinate").attributes("aria-pressed")).toBe("true");
    // While one is insisted on, what was merely read no longer lights up.
    expect(chip(box, "Adresse").attributes("data-state")).toBe("off");

    await chip(box, "Koordinate").trigger("click");
    expect(chip(box, "Koordinate").attributes("data-state")).toBe("off");
    expect(chip(box, "Adresse").attributes("data-state")).toBe("read");
    box.unmount();
  });

  it("gibt festgelegten Text als „prose“ weiter, statt ihn nachzuschlagen", async () => {
    const box = mount(QueryBox);
    await type(box, "Lessingweg 44");
    await chip(box, "Beschreibungstext").trigger("click");

    await button(box).trigger("click");
    await flushPromises();

    expect(box.emitted("resolve")).toBeUndefined();
    const [payload] = box.emitted("read")[0];
    expect(payload.kind).toBe("prose");
    expect(payload.text).toBe("Lessingweg 44");
    box.unmount();
  });

  it("klappt bei einer nackten Nummer das Feldpaar auf und übernimmt sie", async () => {
    const box = mount(QueryBox);
    await type(box, "85/1");
    await flushPromises();

    // Without a district the number is nothing, so the second half unfolds --
    // and retyping the number there is work the reading already did.
    expect(box.find(".query-box__pair").exists()).toBe(true);
    expect(box.find("#q-parcel-number").element.value).toBe("85/1");
    box.unmount();
  });

  it("fragt mit Gemarkung und Nummer das Liegenschaftskataster", async () => {
    const box = mount(QueryBox);
    await type(box, "85/1");
    await flushPromises();

    // The directory answers on the key; the name is what gets typed.
    const district = box.find(".gemarkung input");
    district.element.value = MOELKAU.name;
    await district.trigger("input");
    await flushPromises();

    await button(box).trigger("click");
    await flushPromises();

    expect(box.emitted("read")).toBeUndefined();
    const [payload] = box.emitted("resolve")[0];
    expect(payload.query).toEqual({ gemarkung: MOELKAU.schluessel, flurstuecksnummer: "85/1" });
    expect(payload.label).toBe(`Flurstück: ${MOELKAU.name} 85/1`);
    box.unmount();
  });

  it("nimmt die alte Flurstücksnummer nicht mit in die nächste Suche", async () => {
    const box = mount(QueryBox);
    await type(box, "85/1");
    await flushPromises();
    expect(box.find("#q-parcel-number").element.value).toBe("85/1");

    // Emptying the field is a fresh start. Leaving the number behind asked the
    // cadastre for 85/1 while the field said 204 -- a real parcel, a wrong
    // answer, and nothing on screen to show it.
    await type(box, "");
    await flushPromises();
    expect(box.find(".query-box__pair").exists()).toBe(false);

    await type(box, "204");
    await flushPromises();
    expect(box.find("#q-parcel-number").element.value).toBe("204");

    const district = box.find(".gemarkung input");
    district.element.value = MOELKAU.name;
    await district.trigger("input");
    await flushPromises();
    await button(box).trigger("click");
    await flushPromises();

    const [payload] = box.emitted("resolve")[0];
    expect(payload.query.flurstuecksnummer).toBe("204");
    box.unmount();
  });

  it("behauptet nicht, die Gemarkung fehle, wenn sie dasteht", async () => {
    // Der Hinweis benennt, was fehlt. Wer ihn über einem gefüllten Feld stehen
    // lässt, widerspricht sich: die Lesart der Suchzeile ändert sich nämlich
    // nicht, wenn das Paar darunter vollständig wird.
    const box = mount(QueryBox);
    await type(box, "85/1");
    await flushPromises();
    expect(box.find(".query-box__note").text()).toContain("Ohne Gemarkung");

    const district = box.find(".gemarkung input");
    district.element.value = MOELKAU.name;
    await district.trigger("input");
    await flushPromises();

    expect(box.find(".query-box__note").exists()).toBe(false);
    box.unmount();
  });

  describe("Enter", () => {
    const enter = field => field.trigger("keydown", { key: "Enter" });

    it("schickt einen Link aus dem Suchfeld ab, ohne dass der Knopf geklickt wird", async () => {
      const box = mount(QueryBox);
      await type(box, "https://www.kleinanzeigen.de/s-anzeige/baugrundstueck/123");

      await enter(box.find(".search__field input"));
      await flushPromises();

      const [payload] = box.emitted("read")[0];
      expect(payload.kind).toBe("url");
      box.unmount();
    });

    it("wartet auf die Adresse, wenn Enter vor der Antwort kommt", async () => {
      const box = mount(QueryBox);
      const input = box.find(".search__field input");
      // With the postcode, so only the address index has a row to offer.
      input.element.value = "Lessingweg 44, 04316 Leipzig";
      await input.trigger("input");
      // Straight after the keystroke: the lookup has not even been asked yet.
      await enter(input);
      expect(box.emitted("resolve")).toBeUndefined();

      await vi.advanceTimersByTimeAsync(200);
      await flushPromises();

      const [payload] = box.emitted("resolve")[0];
      expect(payload.query).toEqual({ lat: 51.33655, lon: 12.44181 });
      box.unmount();
    });

    it("nimmt bei mehreren Adressen die oberste", async () => {
      globalThis.fetch = url => {
        if (String(url).includes("/geocode")) {
          return Promise.resolve(answer({ ...GEOCODE, treffer: [
            ...GEOCODE.treffer,
            { lat: 51.2, lon: 12.3, name: "Lessingweg", beschreibung: "04316 Leipzig", art: "adresse" }
          ] }));
        }
        return Promise.resolve(answer(gemarkungen));
      };
      const box = mount(QueryBox);
      await type(box, "Lessingweg 44, 04316 Leipzig");
      expect(box.findAll(".hit")).toHaveLength(2);

      await enter(box.find(".search__field input"));
      expect(box.emitted("resolve")[0][0].query).toEqual({ lat: 51.33655, lon: 12.44181 });
      box.unmount();
    });

    it("rät zwischen Flurstück und Adresse nicht, sondern hebt die erste Zeile hervor", async () => {
      globalThis.fetch = url => {
        if (String(url).includes("/geocode")) {
          return Promise.resolve(answer({ ...GEOCODE, treffer: [
            ...GEOCODE.treffer,
            { lat: 51.2, lon: 12.3, name: "Lessingweg 44", beschreibung: "04420 Markranstädt", art: "adresse" }
          ] }));
        }
        return Promise.resolve(answer(gemarkungen));
      };
      const box = mount(QueryBox);
      await type(box, "Lessingweg 44");
      const input = box.find(".search__field input");

      await enter(input);
      expect(box.emitted("resolve")).toBeUndefined();
      // Three rows -- the parcel reading and two addresses -- and the first
      // one highlighted, not taken.
      expect(box.findAll(".hit")).toHaveLength(3);
      expect(box.findAll(".hit")[0].classes()).toContain("is-active");

      // The second Enter is a choice somebody saw.
      await enter(input);
      expect(box.emitted("resolve")).toHaveLength(1);
      box.unmount();
    });

    it("fragt aus dem Feld der Flurstücksnummer das Kataster", async () => {
      const box = mount(QueryBox);
      await type(box, "85/1");
      const district = box.find(".gemarkung input");
      district.element.value = MOELKAU.name;
      await district.trigger("input");
      await flushPromises();

      await enter(box.find("#q-parcel-number"));
      await flushPromises();

      expect(box.emitted("resolve")[0][0].query)
        .toEqual({ gemarkung: MOELKAU.schluessel, flurstuecksnummer: "85/1" });
      box.unmount();
    });

    it("nimmt in der Gemarkung erst die markierte Zeile und schickt danach ab", async () => {
      const box = mount(QueryBox);
      await type(box, "85/1");
      const district = box.find(".gemarkung input");
      district.element.value = "Mölk";
      await district.trigger("input");
      await flushPromises();
      await district.trigger("keydown", { key: "ArrowDown" });

      await enter(district);
      expect(district.element.value).toBe(MOELKAU.name);
      expect(box.emitted("resolve")).toBeUndefined();

      await enter(district);
      await flushPromises();
      expect(box.emitted("resolve")[0][0].query.flurstuecksnummer).toBe("85/1");
      box.unmount();
    });
  });
});
