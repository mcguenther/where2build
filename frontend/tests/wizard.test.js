/**
 * The Gemarkung field in the wizard: a searchable directory, not a blank line.
 *
 * The directory is the one the service really answers with, recorded into
 * `fixtures/gemarkungen.json` — 61 of the 5 339 Saxon districts, Mölkau among
 * them. No names are invented here: a picker tested against made-up entries
 * would prove nothing about the umlaut or the key forms.
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import CadastralDistrictPicker from "../src/components/CadastralDistrictPicker.vue";
import WizardView from "../src/views/WizardView.vue";
import { state } from "../src/lib/store.js";
import { realPlot, realState, mountWithRouter } from "./helpers.js";
import directory from "./fixtures/gemarkungen.json";
import moelkau from "./fixtures/parcel-moelkau.json";

vi.mock("../src/lib/api.js", () => ({
  cadastralDistricts: vi.fn(),
  resolveParcel: vi.fn(),
  landValue: vi.fn(),
  readListing: vi.fn(),
  readPage: vi.fn(),
  readHouseType: vi.fn(),
  backendHealth: vi.fn(() => Promise.resolve(null)),
  reachability: vi.fn(),
  geocode: vi.fn(),
  nearby: vi.fn()
}));
const { cadastralDistricts, resolveParcel, landValue, readPage } = await import("../src/lib/api.js");

beforeEach(() => {
  localStorage.clear();
  state.data = realState();
  vi.clearAllMocks();
  cadastralDistricts.mockResolvedValue(directory);
});

/** One keystroke: `setValue` also fires `change`, which is the end of an
 *  entry and not what typing looks like. */
const typeInto = async (field, text) => {
  field.element.value = text;
  await field.trigger("input");
};

/** A mounted picker with the directory already in hand. */
const picker = async () => {
  const w = mount(CadastralDistrictPicker);
  await flushPromises();
  return w;
};

const search = async (text) => {
  const w = await picker();
  await typeInto(w.find("input"), text);
  return w;
};

const names = w => w.findAll("[role=option] .gemarkung__name").map(o => o.text());

describe("Gemarkung — Verzeichnis durchsuchen", () => {
  it("holt das Verzeichnis einmal und zeigt nichts, bevor getippt wird", async () => {
    const w = await picker();
    expect(cadastralDistricts).toHaveBeenCalledTimes(1);
    expect(w.findAll("[role=option]")).toHaveLength(0);
    expect(w.find("input").attributes("aria-expanded")).toBe("false");
  });

  it("filtert nach dem Namen und nennt Schlüssel und Gemeinde dazu", async () => {
    const w = await search("Mölk");
    const row = w.find("[role=option]");
    expect(names(w)).toEqual(["Mölkau"]);
    expect(row.text()).toContain("145592");
    expect(row.text()).toContain("Stadt Leipzig");
    expect(w.find("input").attributes("aria-expanded")).toBe("true");
    expect(w.find("[role=listbox]").isVisible()).toBe(true);
  });

  it("verzeiht den fehlenden Umlaut", async () => {
    expect(names(await search("Molkau"))).toEqual(["Mölkau"]);
    expect(names(await search("Grossdubrau"))).toEqual([]);      // Gemeinde, nicht Gemarkung
    expect(names(await search("Kronforstchen"))).toEqual(["Kronförstchen"]);
  });

  it("findet über die vierstellige wie über die sechsstellige Schreibweise", async () => {
    expect(names(await search("5592"))).toEqual(["Mölkau"]);
    expect(names(await search("145592"))).toEqual(["Mölkau"]);
    // Die Kurzform ohne führende Null, wie sie eine Tabelle hinterlässt.
    expect(names(await search("0419"))).toEqual(["Lauer"]);
    expect(names(await search("419"))).toEqual(["Lauer"]);
  });

  it("stellt den passendsten Treffer nach vorn", async () => {
    // "Wölkau Flur 7" beginnt damit, "Mölkau" enthält es nur.
    expect(names(await search("ölkau"))).toEqual(["Wölkau Flur 7", "Mölkau"]);
  });

  it("begrenzt die Liste und sagt, wie viel sie verschweigt", async () => {
    const w = await search("14");            // jeder sächsische Schlüssel beginnt so
    expect(w.findAll("[role=option]")).toHaveLength(50);
    expect(w.text()).toContain(`${directory.gemarkungen.length - 50} weitere Treffer`);
  });
});

describe("Gemarkung — Bedienung", () => {
  it("übernimmt einen Treffer mit Pfeiltaste und Enter", async () => {
    const w = await search("Mölk");
    const field = w.find("input");

    await field.trigger("keydown", { key: "ArrowDown" });
    expect(field.attributes("aria-activedescendant")).toBe(w.find("[role=option]").attributes("id"));
    expect(w.find("[role=option]").attributes("aria-selected")).toBe("true");

    await field.trigger("keydown", { key: "Enter" });
    expect(field.element.value).toBe("Mölkau");
    expect(w.emitted("update:modelValue").at(-1)).toEqual(["Mölkau"]);
    expect(w.emitted("select").at(-1)[0].schluessel).toBe("145592");
    expect(field.attributes("aria-expanded")).toBe("false");
  });

  it("übernimmt einen Treffer auch mit der Maus", async () => {
    const w = await search("Mölk");
    await w.find("[role=option]").trigger("mousedown");
    expect(w.emitted("select").at(-1)[0].name).toBe("Mölkau");
    expect(w.find("input").element.value).toBe("Mölkau");
  });

  it("schließt die Liste mit Escape, ohne das Getippte zu verwerfen", async () => {
    const w = await search("Mölk");
    await w.find("input").trigger("keydown", { key: "Escape" });
    expect(w.find("input").attributes("aria-expanded")).toBe("false");
    expect(w.find("[role=listbox]").isVisible()).toBe(false);
    expect(w.find("input").element.value).toBe("Mölk");
  });

  it("erkennt den ausgeschriebenen Namen ohne Klick in die Liste", async () => {
    const w = await search("Mölkau");
    expect(w.emitted("select").at(-1)[0].schluessel).toBe("145592");
    expect(w.text()).toContain("Verzeichnis: Mölkau");
  });
});

describe("Gemarkung — freie Eingabe", () => {
  it("hält fest, was nicht im Verzeichnis steht, und sperrt es nicht", async () => {
    const w = await search("Moritzburg");   // im Verzeichnisauszug nicht enthalten
    expect(w.findAll("[role=option]")).toHaveLength(0);
    expect(w.find("input").element.value).toBe("Moritzburg");
    expect(w.emitted("update:modelValue").at(-1)).toEqual(["Moritzburg"]);
    expect(w.text()).toContain("Kein Eintrag im Verzeichnis");
    expect(w.text()).toContain("Nachschlagen lässt sich das trotzdem");
    expect(w.find("input").attributes("disabled")).toBeUndefined();
  });

  it("bleibt ein benutzbares Textfeld, wenn der Dienst ausfällt", async () => {
    cadastralDistricts.mockRejectedValue(new Error("Das Gemarkungsverzeichnis ist nicht erreichbar."));
    const w = await search("Moritzburg");

    expect(w.text()).toContain("Das Gemarkungsverzeichnis ist nicht erreichbar.");
    // Kein erfundener Ersatz und kein "es gibt nichts": die Liste bleibt fort,
    // der Hinweis auf den fehlenden Eintrag auch.
    expect(w.findAll("[role=option]")).toHaveLength(0);
    expect(w.text()).not.toContain("Kein Eintrag im Verzeichnis");
    expect(w.find("input").element.value).toBe("Moritzburg");
    expect(w.emitted("update:modelValue").at(-1)).toEqual(["Moritzburg"]);
  });
});

describe("Aufnahme — Schritt Quelle", () => {
  const atSource = () =>
    mountWithRouter(WizardView, { path: "/aufnahme/quelle", props: { stage: "quelle" } });

  it("bietet das Verzeichnis erst beim Weg „Flurstück direkt“ an", async () => {
    const w = atSource();
    expect(w.findComponent(CadastralDistrictPicker).exists()).toBe(false);
    expect(cadastralDistricts).not.toHaveBeenCalled();

    await w.find('input[value="parcel"]').setValue();
    expect(w.findComponent(CadastralDistrictPicker).exists()).toBe(true);
    expect(cadastralDistricts).toHaveBeenCalledTimes(1);
  });

  it("fragt das Kataster mit dem Schlüssel des gewählten Eintrags", async () => {
    resolveParcel.mockResolvedValue(moelkau);
    landValue.mockRejectedValue(new Error("Kein Bodenrichtwert."));

    const w = atSource();
    await w.find('input[value="parcel"]').setValue();
    await flushPromises();

    const field = w.findComponent(CadastralDistrictPicker);
    await typeInto(field.find("input"), "Mölk");
    await field.find("[role=option]").trigger("mousedown");
    await typeInto(w.find("#q-parcel-number"), "85/1");
    await flushPromises();

    await w.findAll("button").find(b => b.text() === "Nachschlagen").trigger("click");
    await flushPromises();

    expect(resolveParcel).toHaveBeenCalledWith({ gemarkung: "145592", flurstuecksnummer: "85/1" });
  });

  it("schlägt auch nach, was nur getippt und nicht gewählt wurde", async () => {
    resolveParcel.mockResolvedValue(moelkau);
    landValue.mockRejectedValue(new Error("Kein Bodenrichtwert."));

    const w = atSource();
    await w.find('input[value="parcel"]').setValue();
    await flushPromises();

    await typeInto(w.findComponent(CadastralDistrictPicker).find("input"), "Moritzburg");
    await typeInto(w.find("#q-parcel-number"), "85/1");
    await flushPromises();

    await w.findAll("button").find(b => b.text() === "Nachschlagen").trigger("click");
    await flushPromises();

    expect(resolveParcel).toHaveBeenCalledWith({ gemarkung: "Moritzburg", flurstuecksnummer: "85/1" });
  });
});

describe("Aufnahme — Absenden", () => {
  const atSource = () =>
    mountWithRouter(WizardView, { path: "/aufnahme/quelle", props: { stage: "quelle" } });

  it("liest die Anzeige auch, wenn im Feld nur Enter gedrückt wurde", async () => {
    resolveParcel.mockResolvedValue(moelkau);
    landValue.mockRejectedValue(new Error("Kein Bodenrichtwert."));

    const w = atSource();
    await w.find('input[value="parcel"]').setValue();
    await flushPromises();

    await typeInto(w.findComponent(CadastralDistrictPicker).find("input"), "Moritzburg");
    await typeInto(w.find("#q-parcel-number"), "85/1");
    // Was das Drücken von Enter in einem Textfeld auslöst.
    await w.find("form").trigger("submit");
    await flushPromises();

    expect(resolveParcel).toHaveBeenCalledWith({ gemarkung: "Moritzburg", flurstuecksnummer: "85/1" });
  });

  it("liest genau einmal, wenn der Knopf geklickt wird", async () => {
    resolveParcel.mockResolvedValue(moelkau);
    landValue.mockRejectedValue(new Error("Kein Bodenrichtwert."));

    const w = atSource();
    await w.find('input[value="parcel"]').setValue();
    await flushPromises();

    await typeInto(w.findComponent(CadastralDistrictPicker).find("input"), "Moritzburg");
    await typeInto(w.find("#q-parcel-number"), "85/1");
    await w.findAll("button").find(b => b.text() === "Nachschlagen").trigger("click");
    await flushPromises();

    expect(resolveParcel).toHaveBeenCalledTimes(1);
  });

  it("schickt bei leerem Feld gar nichts los", async () => {
    const w = atSource();
    await w.find('input[value="parcel"]').setValue();
    await flushPromises();

    await w.find("form").trigger("submit");
    await flushPromises();

    expect(resolveParcel).not.toHaveBeenCalled();
  });

  it("nimmt das HTML aus der Zwischenablage mit, nicht nur den Text", async () => {
    readPage.mockResolvedValue({ felder: {}, beschreibung: "", bilder: [] });

    const w = atSource();
    await w.find('input[value="paste"]').setValue();
    await flushPromises();

    const field = w.find("#q-paste");
    const html = "<html><meta property=\"og:latitude\" content=\"51.19\"><body>Baugrundstück in Lobstädt, 1.025 m²</body></html>";
    await field.trigger("paste", {
      clipboardData: { getData: kind => (kind === "text/html" ? html : "Baugrundstück in Lobstädt, 1.025 m²") }
    });
    await typeInto(field, "Baugrundstück in Lobstädt, 1.025 m²");
    await flushPromises();

    expect(w.text()).toContain("Das HTML wurde übernommen");

    await w.find("form").trigger("submit");
    await flushPromises();

    expect(readPage).toHaveBeenCalledWith(html);
  });

  it("vergisst das HTML, sobald das Feld geleert wird", async () => {
    readPage.mockResolvedValue({ felder: {}, beschreibung: "", bilder: [] });

    const w = atSource();
    await w.find('input[value="paste"]').setValue();
    await flushPromises();

    const field = w.find("#q-paste");
    await field.trigger("paste", {
      clipboardData: { getData: () => "<html>die vorige Seite</html>" }
    });
    await typeInto(field, "die vorige Seite");
    await typeInto(field, "");
    await typeInto(field, "Ein ganz anderer Text, von Hand getippt und lang genug.");
    await flushPromises();

    await w.find("form").trigger("submit");
    await flushPromises();

    expect(readPage).toHaveBeenCalledWith("Ein ganz anderer Text, von Hand getippt und lang genug.");
  });
});


describe("Aufnahme — Flurstück und Angaben in einem Schritt", () => {
  /** The last stage, with a draft in hand. */
  const atParcelStage = async () => {
    const view = mountWithRouter(WizardView, { path: "/aufnahme/quelle", props: { stage: "quelle" } });
    view.vm.draft = {
      ...realPlot(),
      gemarkung: "Liebertwolkwitz",
      gemarkungsnummer: "145592",
      flurstuecke: ["85/1"]
    };
    await view.setProps({ stage: "flurstueck" });
    return view;
  };

  it("fragt beim Klick auf die Zeichnung, was dort liegt, und legt es dazu", async () => {
    const w = await atParcelStage();
    const before = [...w.vm.draft.flurstuecke];

    resolveParcel.mockReset();
    resolveParcel
      .mockResolvedValueOnce({
        features: [{ properties: {
          zaehler: "86", nenner: "2",
          gemarkung: "Liebertwolkwitz", gemarkungsnummer: "145592"
        } }]
      })
      .mockResolvedValueOnce(moelkau);
    landValue.mockRejectedValue(new Error("Kein Bodenrichtwert."));

    await w.findAll("button").find(b => /Flurstück hinzufügen/.test(b.text())).trigger("click");
    expect(w.findComponent({ name: "SitePlan" }).props("picking")).toBe(true);

    await w.vm.addParcelAt({ lat: 51.31, lon: 12.47 });
    await flushPromises();

    // Erst die Frage nach dem Punkt, dann das Grundstück aus allen Nummern:
    // die Vereinigung und die Summe der amtlichen Flächen kommen von dort,
    // wo sie immer herkamen.
    expect(resolveParcel).toHaveBeenCalledTimes(2);
    expect(resolveParcel.mock.calls[0][0]).toEqual({ lat: 51.31, lon: 12.47 });
    expect(resolveParcel.mock.calls[1][0].flurstuecksnummern).toEqual([...before, "86/2"]);
    expect(resolveParcel.mock.calls[1][0].gemarkung).toBe("145592");
  });

  it("nimmt dasselbe Flurstück nicht zweimal", async () => {
    const w = await atParcelStage();

    resolveParcel.mockReset();
    resolveParcel.mockResolvedValueOnce({
      features: [{ properties: {
        zaehler: "85", nenner: "1",
        gemarkung: "Liebertwolkwitz", gemarkungsnummer: "145592"
      } }]
    });

    await w.vm.addParcelAt({ lat: 51.31, lon: 12.47 });
    await flushPromises();

    // Kein zweiter Aufruf: die summierte Fläche würde sich sonst verdoppeln,
    // und auf ihr steht jeder Preisvergleich.
    expect(resolveParcel).toHaveBeenCalledTimes(1);
    expect(w.text()).toContain("gehört bereits dazu");
  });

  it("legt kein Flurstück aus einer anderen Gemarkung dazu", async () => {
    const w = await atParcelStage();

    resolveParcel.mockReset();
    resolveParcel.mockResolvedValueOnce({
      features: [{ properties: {
        zaehler: "12", nenner: null,
        gemarkung: "Mölkau", gemarkungsnummer: "140427"
      } }]
    });

    await w.vm.addParcelAt({ lat: 51.34, lon: 12.47 });
    await flushPromises();

    expect(resolveParcel).toHaveBeenCalledTimes(1);
    expect(w.text()).toContain("Mölkau");
  });

  it("nimmt Name, Kaufpreis und Notiz im selben Schritt auf", async () => {
    const w = await atParcelStage();

    // Drei Felder waren eine eigene Seite, und der Umriss, den sie beschreiben,
    // war dabei nicht zu sehen.
    expect(w.find("#q-name").exists()).toBe(true);
    expect(w.find("#q-price").exists()).toBe(true);
    expect(w.find("#q-note").exists()).toBe(true);
    expect(w.findComponent({ name: "SitePlan" }).exists()).toBe(true);
    expect(w.text()).toContain("Anlegen und öffnen");
  });
});
