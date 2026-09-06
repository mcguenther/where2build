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
import { nextTick } from "vue";
import CadastralDistrictPicker from "../src/components/CadastralDistrictPicker.vue";
import WizardView from "../src/views/WizardView.vue";
import { state } from "../src/lib/store.js";
import { realState, realPlot, mountWithRouter } from "./helpers.js";
import directory from "./fixtures/gemarkungen.json";
import moelkau from "./fixtures/parcel-moelkau.json";
import moelkauZwei from "./fixtures/parcel-moelkau-zwei.json";
import moelkauGetrennt from "./fixtures/parcel-moelkau-getrennt.json";
import moelkauNachbar from "./fixtures/parcel-moelkau-205.json";

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
  nearby: vi.fn(),
  nearbyParcels: vi.fn()
}));
const { cadastralDistricts, resolveParcel, landValue, nearbyParcels } =
  await import("../src/lib/api.js");

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

describe("Der Schritt „Flurstück“", () => {
  /* This step seats no house: nobody has chosen one yet, so a body drawn here
     is a body the user did not put there — and its "fits nowhere" message read
     a computed nothing defined, which crashed the render and left the wizard an
     empty page under the header for exactly the plots that triggered it. */
  it("zeigt auch ein winziges Flurstück, statt von einem Baukörper zu reden", async () => {
    const wizard = mountWithRouter(WizardView, {
      path: "/aufnahme/flurstueck", props: { stage: "flurstueck" }
    });
    // A parcel too small for any footprint: 86 m² is what Lilienweg 25 measures.
    wizard.vm.draft = realPlot("moelkau");
    wizard.vm.draft.polygon = [
      { x: 0, y: 0 }, { x: 6, y: 0 }, { x: 6, y: 4 }, { x: 0, y: 4 }
    ];
    wizard.vm.draft.setbacks = wizard.vm.draft.polygon.map(() => 3);
    await nextTick();

    const plan = wizard.findComponent({ name: "SitePlan" });
    expect(plan.exists()).toBe(true);
    expect(plan.props("showBuilding")).toBe(false);
    expect(wizard.text()).toContain("Anlegen und öffnen");
    expect(wizard.text()).not.toContain("Baukörper");
    wizard.unmount();
  });
});


/**
 * A plot is a set of parcels, and this is where the user assembles it: the
 * fixtures are the backend's real answers for Lessingweg 44 alone, together
 * with 46 next door, and together with 84 two streets away — which the register
 * unions into two separate pieces.
 */
describe("Ein Grundstück aus mehreren Flurstücken", () => {
  const KEY_44 = "145592___00204____02";
  const KEY_46 = "145592___00205____02";
  const KEY_84 = "145592___00084000y02";

  /** The wizard at the parcel step, one parcel chosen, its neighbours offered. */
  const atParcelStep = async (composing = true) => {
    resolveParcel.mockResolvedValue(moelkau);
    landValue.mockRejectedValue(new Error("Kein Bodenrichtwert."));
    nearbyParcels.mockResolvedValue({ features: moelkauZwei.features });

    const w = mountWithRouter(WizardView, { path: "/aufnahme/quelle", props: { stage: "quelle" } });
    await w.find('input[value="parcel"]').setValue();
    await typeInto(w.findComponent(CadastralDistrictPicker).find("input"), "Mölkau");
    await typeInto(w.find("#q-parcel-number"), "204");
    await w.findAll("button").find(b => b.text() === "Nachschlagen").trigger("click");
    await flushPromises();
    await w.setProps({ stage: "flurstueck" });
    await flushPromises();
    w.vm.composing = composing;
    await nextTick();
    return w;
  };

  it("zentriert die Karte auf das korrigierte Flurstück, nicht auf die Koordinate", async () => {
    // „Lessingweg 44“ landet unter der Koordinate auf 205; die Lagebezeichnung
    // korrigiert auf 204. Den Ausschnitt festzuhalten wäre hier falsch — er
    // zeigte weiter genau das Flurstück, das gerade verworfen wurde.
    resolveParcel.mockResolvedValue(moelkauNachbar);
    landValue.mockRejectedValue(new Error("Kein Bodenrichtwert."));
    nearbyParcels.mockResolvedValue({ features: moelkauZwei.features });

    const w = mountWithRouter(WizardView, { path: "/aufnahme/quelle", props: { stage: "quelle" } });
    w.vm.searchedAddress = "Lessingweg 44";
    await w.find('input[value="parcel"]').setValue();
    await typeInto(w.findComponent(CadastralDistrictPicker).find("input"), "Mölkau");
    await typeInto(w.find("#q-parcel-number"), "205");
    await w.findAll("button").find(b => b.text() === "Nachschlagen").trigger("click");
    await flushPromises();
    await w.setProps({ stage: "flurstueck" });
    await flushPromises();

    expect(w.vm.corrected).toContain("204");
    expect(w.vm.holdFrame).toBe(false);
    expect(w.findComponent({ name: "SitePlan" }).props("holdFrame")).toBe(false);
    w.unmount();
  });

  it("wechselt per Klick das Flurstück, statt es dazuzunehmen", async () => {
    // Der häufige Fall: die Koordinate lag auf dem Nachbarn, ein Klick rückt das
    // gerade. Zusammensetzen ist die Ausnahme und muss angeschaltet werden.
    const w = await atParcelStep(false);
    expect(w.vm.selection).toEqual([KEY_44]);

    resolveParcel.mockResolvedValue(moelkau);
    await w.vm.chooseParcel(KEY_46);
    await flushPromises();

    expect(resolveParcel).toHaveBeenLastCalledWith({ kennzeichen: [KEY_46] });
    w.unmount();
  });

  it("nimmt im Zusammensetzen-Modus ein Flurstück dazu und rechnet beide zusammen", async () => {
    const w = await atParcelStep();
    expect(w.vm.selection).toEqual([KEY_44]);

    resolveParcel.mockResolvedValue(moelkauZwei);
    await w.vm.chooseParcel(KEY_46);
    await flushPromises();

    expect(resolveParcel).toHaveBeenLastCalledWith({ kennzeichen: [KEY_44, KEY_46] });
    expect(w.vm.selection).toEqual([KEY_44, KEY_46]);
    // Amtliche Flächen summiert, nicht die gerechnete Fläche des Umrisses.
    expect(w.vm.draft.officialArea).toBe(1299);
    expect(w.vm.draft.flurstuecke).toEqual(["204", "205"]);
    expect(w.text()).toContain("204 · 205");
    w.unmount();
  });

  it("nimmt ein zweites Flurstück auf Klick wieder heraus", async () => {
    const w = await atParcelStep();
    resolveParcel.mockResolvedValue(moelkauZwei);
    await w.vm.chooseParcel(KEY_46);
    await flushPromises();

    resolveParcel.mockResolvedValue(moelkau);
    await w.vm.chooseParcel(KEY_46);
    await flushPromises();

    expect(resolveParcel).toHaveBeenLastCalledWith({ kennzeichen: [KEY_44] });
    expect(w.vm.selection).toEqual([KEY_44]);
    expect(w.vm.draft.officialArea).toBe(650);
    w.unmount();
  });

  it("lässt das letzte Flurstück nicht abwählen und sagt warum", async () => {
    const w = await atParcelStep();
    const calls = resolveParcel.mock.calls.length;

    await w.vm.chooseParcel(KEY_44);
    await flushPromises();

    expect(resolveParcel.mock.calls.length).toBe(calls);
    expect(w.vm.selection).toEqual([KEY_44]);
    expect(w.text()).toContain("mindestens einem Flurstück");
    w.unmount();
  });

  it("markiert getrennte Flurstücke rot, statt den Klick abzulehnen", async () => {
    // Der Weg zurück zu einem ganzen Grundstück führt oft durch ein geteiltes:
    // erst das mittlere heraus, dann das ferne. Wer den Klick verweigert,
    // verschließt genau diesen Weg.
    const w = await atParcelStep();
    resolveParcel.mockResolvedValue(moelkauGetrennt);

    await w.vm.chooseParcel(KEY_84);
    await flushPromises();

    expect(w.vm.selection).toEqual([KEY_44, KEY_84]);
    expect(w.vm.detached).toEqual([KEY_84]);
    expect(w.findComponent({ name: "SitePlan" }).props("problemParcels")).toEqual([KEY_84]);
    expect(w.text()).toContain("hängen nicht mit dem übrigen Grundstück zusammen");
    // Und angelegt wird so nichts: der Lageplan hält einen Umriss.
    const create = w.findAll("button").find(b => b.text().includes("Anlegen und öffnen"));
    expect(create.attributes("disabled")).toBeDefined();
    w.unmount();
  });

  it("gibt den Weg wieder frei, sobald das getrennte Flurstück draußen ist", async () => {
    const w = await atParcelStep();
    resolveParcel.mockResolvedValue(moelkauGetrennt);
    await w.vm.chooseParcel(KEY_84);
    await flushPromises();

    resolveParcel.mockResolvedValue(moelkau);
    await w.vm.chooseParcel(KEY_84);
    await flushPromises();

    expect(w.vm.detached).toEqual([]);
    const create = w.findAll("button").find(b => b.text().includes("Anlegen und öffnen"));
    expect(create.attributes("disabled")).toBeUndefined();
    w.unmount();
  });
});
