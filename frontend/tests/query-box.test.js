/**
 * The one field the start page offers.
 *
 * `queryInput.js` decides what was typed and `PlotSearch` offers the rows; what
 * is tested here is the layer above both — the marker that says how the input
 * was read and the menu that overrules it, the moments at which text becomes a
 * block, and the two things the box hands on: `resolve` when the cadastre can
 * simply be asked, `read` when the text has to be read first. The box resolves
 * nothing itself, so nothing here asserts an answer from a service; the
 * directory is the recorded one.
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

/** Paste into the field the way a browser does: the event, then the text. */
async function paste(box, text, html = "") {
  const input = box.find(".search__field input");
  await input.trigger("paste", {
    clipboardData: { getData: kind => (kind === "text/html" ? html : text) }
  });
  input.element.value = text;
  await input.trigger("input");
  await vi.advanceTimersByTimeAsync(200);
  await flushPromises();
}

const marker = box => box.find(".marker");
const findButton = box => box.find(".btn--large");
const menuItem = (box, name) =>
  box.findAll(".menu__item").find(item => item.find("span").exists() && item.find("span").text() === name)
  ?? box.findAll(".menu__item").find(item => item.text() === name);
const enterKey = field => field.trigger("keydown", { key: "Enter" });

describe("QueryBox", () => {
  describe("Lesart am Feldrand", () => {
    it("zeigt an einem Straßennamen die Lesart „Adresse“", async () => {
      const box = mount(QueryBox);
      await type(box, "Lessingweg");
      expect(marker(box).text()).toBe("Adresse");
      box.unmount();
    });

    it("sagt bei „Lessingweg 44“, dass es zwei Lesarten gibt, statt eine zu raten", async () => {
      const box = mount(QueryBox);
      await type(box, "Lessingweg 44");
      expect(marker(box).text()).toBe("2 Lesarten");
      box.unmount();
    });

    it("zeigt ohne Eingabe keine Lesart", () => {
      const box = mount(QueryBox);
      expect(marker(box).exists()).toBe(false);
      box.unmount();
    });

    it("bietet unmögliche Lesarten ausgegraut und mit Grund an", async () => {
      const box = mount(QueryBox);
      await type(box, "Lessingweg 44");
      await marker(box).trigger("click");

      const coordinate = menuItem(box, "Koordinate");
      expect(coordinate.attributes("disabled")).toBeDefined();
      expect(coordinate.text()).toContain("keine zwei Zahlen");
      expect(menuItem(box, "Eingefügte Anzeige").text()).toContain("kein HTML dabei");
      expect(menuItem(box, "Adresse").attributes("disabled")).toBeUndefined();
      box.unmount();
    });

    it("legt eine Lesart über das Menü fest und gibt den Text dann als solche weiter", async () => {
      const box = mount(QueryBox);
      await type(box, "Lessingweg 44");
      await marker(box).trigger("click");
      await menuItem(box, "Beschreibungstext").trigger("click");

      expect(marker(box).text()).toBe("Beschreibung");
      expect(marker(box).classes()).toContain("marker--fixed");
      await findButton(box).trigger("click");
      await flushPromises();

      expect(box.emitted("resolve")).toBeUndefined();
      const [payload] = box.emitted("read")[0];
      expect(payload.kind).toBe("prose");
      expect(payload.text).toBe("Lessingweg 44");
      box.unmount();
    });

    it("gibt eine festgelegte Lesart mit der erkannten wieder frei", async () => {
      const box = mount(QueryBox);
      await type(box, "Lessingweg");
      await marker(box).trigger("click");
      await menuItem(box, "Beschreibungstext").trigger("click");
      await marker(box).trigger("click");
      await menuItem(box, "Adresse").trigger("click");

      expect(marker(box).text()).toBe("Adresse");
      expect(marker(box).classes()).not.toContain("marker--fixed");
      box.unmount();
    });
  });

  describe("Link und Seite", () => {
    const url = "https://www.kleinanzeigen.de/s-anzeige/ruhiges-grundstueck-fuer-ein-kleines-haus/3520842196-207-4244";

    /* A link copied out of a browser, a mail or a chat usually carries
     * `text/html` beside it — `<a href="…">…</a>`. That markup used to switch
     * the reading to „Seite“, the link went to the server as pasted text, and
     * the server found nothing in it: a 503 for an advert whose page answers
     * perfectly well. Reported on 24.09.2026 with Firefox 156. */
    it("liest einen eingefügten Link als Link, auch wenn HTML mitkommt", async () => {
      const box = mount(QueryBox);
      await paste(box, url, `<a href="${url}">${url}</a>`);

      expect(marker(box).text()).toBe("Link");
      await findButton(box).trigger("click");
      const [payload] = box.emitted("read")[0];
      expect(payload.kind).toBe("url");
      expect(payload.text).toBe(url);
      box.unmount();
    });

    it("zeigt einen eingefügten Link als Pille mit Portal und Anzeigennummer", async () => {
      const box = mount(QueryBox);
      await paste(box, url);

      const pill = box.find(".pill");
      expect(pill.text()).toContain("kleinanzeigen.de");
      expect(pill.text()).toContain("3520842196");
      expect(box.find(".search__field input").element.style.display).toBe("none");
      box.unmount();
    });

    it("macht aus einem getippten Link erst mit Enter eine Pille", async () => {
      const box = mount(QueryBox);
      await type(box, "https://www.kleinanzeigen.de/s-anzeige/baugrundstueck/123456789");
      expect(box.find(".pill").exists()).toBe(false);

      await enterKey(box.find(".search__field input"));
      await flushPromises();
      expect(box.emitted("read")[0][0].kind).toBe("url");
      expect(box.find(".pill").exists()).toBe(true);
      box.unmount();
    });

    it("nimmt die Pille mit dem Kreuz zurück und leert das Feld ganz", async () => {
      const box = mount(QueryBox);
      await paste(box, url, `<a href="${url}">${url}</a>`);
      await box.find(".pill__remove").trigger("click");

      expect(box.find(".pill").exists()).toBe(false);
      expect(box.find(".search__field input").element.value).toBe("");
      expect(marker(box).exists()).toBe(false);
      box.unmount();
    });

    it("liest eine eingefügte ganze Seite weiter als Seite", async () => {
      const box = mount(QueryBox);
      const page = "<html><body><h1>Baugrundstück</h1><p>Grundstücksfläche 590 m²</p></body></html>";
      await paste(box, "Baugrundstück Grundstücksfläche 590 m²", page);

      expect(marker(box).text()).toBe("Anzeigenseite");
      expect(box.find(".pill").text()).toContain("Anzeigenseite");
      await findButton(box).trigger("click");
      const [payload] = box.emitted("read")[0];
      expect(payload.kind).toBe("page");
      expect(payload.html).toBe(page);
      box.unmount();
    });

    it("nennt bei einer eingefügten Seite das Portal, von dem sie stammt", async () => {
      const box = mount(QueryBox);
      const page = `<div><img src="https://img.kleinanzeigen.de/api/v1/prod-ads/images/aa/1.jpg">
        <a href="https://www.kleinanzeigen.de/s-anzeige/x/1">x</a></div>`;
      await paste(box, "Baugrundstück", page);
      expect(box.find(".pill").text()).toContain("kleinanzeigen.de");
      box.unmount();
    });
  });

  describe("Flurstück in beiden Reihenfolgen", () => {
    it("macht aus einer Nummer am Anfang mit dem Leerzeichen einen Block", async () => {
      const box = mount(QueryBox);
      await type(box, "204/3 ");

      expect(box.find(".pill").text()).toContain("204/3");
      expect(marker(box).text()).toContain("Gemarkung fehlt");
      expect(findButton(box).attributes("disabled")).toBeDefined();
      expect(box.find(".search__field input").attributes("placeholder")).toBe("Gemarkung …");
      box.unmount();
    });

    it("wartet bei einer Nummer ohne Nenner auf den Buchstaben danach", async () => {
      const box = mount(QueryBox);
      await type(box, "204 ");
      expect(box.find(".pill").exists()).toBe(false);

      await type(box, "204 M");
      expect(box.find(".pill").text()).toContain("204");
      expect(box.find(".search__field input").element.value).toBe("M");
      box.unmount();
    });

    it("liest „3044 85/1“ als Schlüssel und Nummer, nicht als Nummer und Namen", async () => {
      const box = mount(QueryBox);
      await type(box, "3044 85/1");
      expect(box.find(".pill").exists()).toBe(false);
      box.unmount();
    });

    it("bietet nach der Nummer nur Gemarkungen an und fragt dann das Kataster", async () => {
      const box = mount(QueryBox);
      await type(box, "85/1 ");
      await type(box, "Mölk");

      const kinds = box.findAll(".hit__kind").map(kind => kind.text());
      expect(new Set(kinds)).toEqual(new Set(["Gemarkung"]));
      const row = box.findAll(".hit").find(hit => hit.find(".hit__name").text() === MOELKAU.name);
      await row.trigger("mousedown");
      await flushPromises();

      expect(box.find(".pill").text()).toContain(MOELKAU.name);
      expect(box.find(".pill").text()).toContain("85/1");
      expect(marker(box).text()).toBe("Flurstück");
      await findButton(box).trigger("click");
      await flushPromises();

      expect(box.emitted("read")).toBeUndefined();
      const [payload] = box.emitted("resolve")[0];
      expect(payload.query).toEqual({ gemarkung: MOELKAU.schluessel, flurstuecksnummer: "85/1" });
      expect(payload.label).toBe(`Flurstück: ${MOELKAU.name} 85/1`);
      box.unmount();
    });

    it("macht aus einer gewählten Gemarkung einen Block und nimmt die Nummer danach", async () => {
      const box = mount(QueryBox);
      await type(box, "Mölk");
      const row = box.findAll(".hit").find(hit => hit.find(".hit__kind").text() === "Gemarkung"
        && hit.find(".hit__name").text() === MOELKAU.name);
      await row.trigger("mousedown");
      await flushPromises();

      expect(box.find(".pill").text()).toContain(MOELKAU.name);
      expect(marker(box).text()).toContain("Nummer fehlt");

      await type(box, "204/3");
      await enterKey(box.find(".search__field input"));
      await flushPromises();
      expect(box.emitted("resolve")[0][0].query)
        .toEqual({ gemarkung: MOELKAU.schluessel, flurstuecksnummer: "204/3" });
      box.unmount();
    });

    it("macht aus dem genauen Namen beim Tippen keinen Block", async () => {
      // „Mölkau“ kann noch „Mölkauer Straße“ werden, „Altstadt“ noch
      // „Altstadt Borna“: erst die Auswahl entscheidet.
      const box = mount(QueryBox);
      await type(box, "Mölkau ");
      expect(box.find(".pill").exists()).toBe(false);
      box.unmount();
    });

    it("nimmt mit Rückschritt im leeren Feld den letzten Block zurück", async () => {
      const box = mount(QueryBox);
      await type(box, "85/1 ");
      expect(box.find(".pill").exists()).toBe(true);

      await box.find(".search__field input").trigger("keydown", { key: "Backspace" });
      expect(box.find(".pill").exists()).toBe(false);
      box.unmount();
    });

    it("nimmt die alte Flurstücksnummer nicht mit in die nächste Suche", async () => {
      // Leaving a number behind asked the cadastre for 85/1 while the field
      // said 204 -- a real parcel, a wrong answer, and nothing on screen to
      // show it.
      const box = mount(QueryBox);
      await type(box, "85/1 ");
      await box.find(".pill__remove").trigger("click");
      await type(box, "204 M");
      await type(box, "Mölk");
      const row = box.findAll(".hit").find(hit => hit.find(".hit__name").text() === MOELKAU.name);
      await row.trigger("mousedown");
      await flushPromises();
      await findButton(box).trigger("click");

      expect(box.emitted("resolve")[0][0].query.flurstuecksnummer).toBe("204");
      box.unmount();
    });

    it("nimmt nach der Nummer mit Enter die Gemarkung und fragt gleich das Kataster", async () => {
      const box = mount(QueryBox);
      await type(box, "85/1 ");
      await type(box, MOELKAU.name);
      await enterKey(box.find(".search__field input"));
      await flushPromises();

      expect(box.emitted("resolve")[0][0].query)
        .toEqual({ gemarkung: MOELKAU.schluessel, flurstuecksnummer: "85/1" });
      box.unmount();
    });

    it("schickt eine Gemarkung, die nicht im Verzeichnis steht, so wie getippt", async () => {
      // Moritzburg fehlt im Verzeichnisauszug; das Verzeichnis ist eine
      // Hilfe, keine Sperre.
      const box = mount(QueryBox);
      await type(box, "85/1 ");
      await type(box, "Moritzburg");
      await findButton(box).trigger("click");
      await flushPromises();

      expect(box.emitted("resolve")[0][0].query)
        .toEqual({ gemarkung: "Moritzburg", flurstuecksnummer: "85/1" });
      box.unmount();
    });

    it("liest „Mölkau 204/3“ in einem Zug als Flurstück", async () => {
      const box = mount(QueryBox);
      await type(box, `${MOELKAU.name} 204/3`);
      expect(marker(box).text()).toBe("Flurstück");
      box.unmount();
    });
  });

  describe("Koordinate", () => {
    it("zeigt eine getippte Koordinate erst nach Enter als Pille und löst sie erst danach auf", async () => {
      const box = mount(QueryBox);
      await type(box, "51.33652, 12.44176");
      expect(box.find(".pill").exists()).toBe(false);

      const input = box.find(".search__field input");
      await enterKey(input);
      await flushPromises();
      expect(box.find(".pill").text()).toContain("51,33652° N");
      expect(box.emitted("resolve")).toBeUndefined();

      await findButton(box).trigger("click");
      expect(box.emitted("resolve")[0][0].query).toEqual({ lat: 51.33652, lon: 12.44176 });
      box.unmount();
    });

    it("zeigt unter der Pille die Karte und fragt nach dem Verschieben den neuen Punkt an", async () => {
      const box = mount(QueryBox);
      await paste(box, "51.33652, 12.44176");
      const preview = box.findComponent({ name: "CoordinatePreview" });
      expect(preview.exists()).toBe(true);
      expect(preview.props()).toMatchObject({ lat: 51.33652, lon: 12.44176 });

      preview.vm.$emit("move", { lat: 51.3366, lon: 12.4419 });
      await flushPromises();
      expect(box.find(".pill").text()).toContain("51,33660° N");
      await findButton(box).trigger("click");
      expect(box.emitted("resolve")[0][0].query).toEqual({ lat: 51.3366, lon: 12.4419 });
      box.unmount();
    });

    it("zeigt vor Enter keine Karte, damit beim Tippen nichts springt", async () => {
      const box = mount(QueryBox);
      await type(box, "51.33652, 12.44176");
      expect(box.findComponent({ name: "CoordinatePreview" }).exists()).toBe(false);
      box.unmount();
    });

    it("macht eine eingefügte Koordinate sofort zur Pille", async () => {
      const box = mount(QueryBox);
      await paste(box, "51.33652, 12.44176");
      expect(box.find(".pill").text()).toContain("12,44176° O");
      expect(marker(box).text()).toBe("Koordinate");
      box.unmount();
    });

    it("sagt in der Marke, wenn Breite und Länge getauscht gelesen wurden", async () => {
      const box = mount(QueryBox);
      await type(box, "12.44176, 51.33652");
      expect(marker(box).text()).toContain("getauscht");
      box.unmount();
    });
  });

  describe("Beschreibungstext", () => {
    const description = "Hier könnte Ihr neues Eigenheim stehen. Ein ruhiges Grundstück am Ortsrand, "
      + "sonnig gelegen und gut erschlossen, mit Blick ins Grüne und kurzen Wegen zur Schule. "
      + `Entsprechend §34 BauGB ist eine Bebauung möglich. Das Grundstück hat ca. 1.025 qm und liegt in ${"Mölkau"}.`;

    it("klappt einen eingefügten Text ein und markiert, was der Browser schon erkennt", async () => {
      const box = mount(QueryBox);
      await paste(box, description);

      expect(marker(box).text()).toBe("Beschreibung");
      const marks = box.findAll(".prose__text mark").map(mark => mark.text());
      expect(marks).toContain("§34 BauGB");
      expect(marks).toContain("ca. 1.025 qm");
      expect(marks).toContain("Mölkau");
      expect(box.find(".prose__count").text()).toMatch(/\d+ Wörter/);
      box.unmount();
    });

    it("beginnt den eingeklappten Text bei der ersten Markierung", async () => {
      const box = mount(QueryBox);
      await paste(box, description);
      const folded = box.find(".prose__text").text();
      expect(folded.startsWith("…")).toBe(true);
      expect(folded).not.toContain("Hier könnte");

      await box.findAll(".link-button")[0].trigger("click");
      expect(box.find(".prose__text").text()).toContain("Hier könnte");
      box.unmount();
    });

    it("gibt den Text zum Bearbeiten zurück ins Feld", async () => {
      const box = mount(QueryBox);
      await paste(box, description);
      await box.findAll(".link-button")[1].trigger("click");

      expect(box.find(".prose").exists()).toBe(false);
      const input = box.find(".search__field input");
      expect(input.element.style.display).not.toBe("none");
      expect(input.element.value).toBe(description);
      box.unmount();
    });
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
  });
});
