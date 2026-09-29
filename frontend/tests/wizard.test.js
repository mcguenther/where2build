/**
 * The wizard: the one field of its first step, the search, and the parcel step.
 *
 * The directory is the one the service really answers with, recorded into
 * `fixtures/gemarkungen.json` — 61 of the 5 339 Saxon districts, Mölkau among
 * them. The matching itself is tested in `districts.test.js`.
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { nextTick } from "vue";
import WizardView from "../src/views/WizardView.vue";
import { state } from "../src/lib/store.js";
import { realPlot, realState, mountWithRouter, testRouter } from "./helpers.js";
import {
  HANDOVER_QUERY, HANDOVER_READY, HANDOVER_PAGE
} from "../src/lib/bookmarklet.js";
import directory from "./fixtures/gemarkungen.json";
import moelkau from "./fixtures/parcel-moelkau.json";
import moelkauZwei from "./fixtures/parcel-moelkau-zwei.json";
import moelkauGetrennt from "./fixtures/parcel-moelkau-getrennt.json";
import moelkauNachbar from "./fixtures/parcel-moelkau-205.json";
import pasted from "./fixtures/extract-kleinanzeigen-einfuegen.json";

vi.mock("../src/lib/api.js", () => ({
  // The cap the module exports next to the call that sends it. A factory
  // that omits a named export makes every importer fail at *import* time,
  // which shows up as unrelated component errors.
  PAGE_LIMIT: 3000000,
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
const { cadastralDistricts, resolveParcel, landValue, readPage, nearbyParcels, geocode } =
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

/** The recorded `/api/geocode` answer for "Lessingweg 44" — the same one
 *  `query-box.test.js` types, official Hauskoordinaten first. */
const LESSINGWEG_44 = {
  treffer: [
    {
      lat: 51.33655, lon: 12.44181, name: "Lessingweg 44",
      beschreibung: "04316 Leipzig · Mölkau", art: "adresse"
    }
  ],
  hinweis: "Amtliche Hauskoordinaten des GeoSN.",
  quelle: "Amtliche Hauskoordinaten (GeoSN, dl-de/by-2-0)"
};

/** The wizard's one field. There is no choice of way in any more: what was
 *  typed is read, and the reading decides what unfolds. */
const intoQuery = (w, text) => typeInto(w.find(".search__field input"), text);

/** The suggestions arrive behind a keystroke debounce. */
const settle = async () => {
  await new Promise(resolve => setTimeout(resolve, 150));
  await flushPromises();
};

const findButton = (w, label) => w.findAll("button").find(b => b.text() === label);

/** Overrule the reading through the marker's menu, by the reading's name. */
const fixReading = async (w, name) => {
  await w.find(".marker").trigger("click");
  const item = w.findAll(".menu__item").find(b => b.find("span").exists() && b.find("span").text() === name);
  await item.trigger("click");
};

/** Look a parcel up the way the field takes it: the number, a space that makes
 *  it a block, then the Gemarkung — and one button asks the cadastre, taking
 *  the directory's row for the name, or the name as typed when there is none. */
const lookUpParcel = async (w, { district, number }) => {
  // With the first letter: a number without a denominator becomes a block
  // only once a letter follows it.
  await intoQuery(w, `${number} ${district.charAt(0)}`);
  await flushPromises();
  await intoQuery(w, district);
  await settle();
  await findButton(w, "Grundstück finden").trigger("click");
  await settle();
};

describe("Aufnahme — Schritt Quelle", () => {
  const atSource = () =>
    mountWithRouter(WizardView, { path: "/aufnahme/quelle", props: { stage: "quelle" } });

  /* The directory is 490 kB, and it is fetched only once what is typed can
     be a Gemarkung: a bare number cannot be one, a letter after it can. */
  it("lädt das Verzeichnis erst, wenn eine Gemarkung getippt wird", async () => {
    const w = atSource();
    expect(cadastralDistricts).not.toHaveBeenCalled();

    await intoQuery(w, "85/1 ");
    await settle();
    expect(cadastralDistricts).not.toHaveBeenCalled();

    await intoQuery(w, "Mölk");
    await settle();
    expect(cadastralDistricts).toHaveBeenCalledTimes(1);
  });

  it("fragt das Kataster mit dem Schlüssel des gewählten Eintrags", async () => {
    resolveParcel.mockResolvedValue(moelkau);
    landValue.mockRejectedValue(new Error("Kein Bodenrichtwert."));

    const w = atSource();
    await intoQuery(w, "85/1 ");
    await intoQuery(w, "Mölk");
    await settle();
    const row = w.findAll(".hit").find(hit => hit.find(".hit__name").text() === "Mölkau");
    await row.trigger("mousedown");
    await flushPromises();

    await findButton(w, "Grundstück finden").trigger("click");
    await flushPromises();

    expect(resolveParcel).toHaveBeenCalledWith({ gemarkung: "145592", flurstuecksnummer: "85/1" });
  });

  it("schlägt nach, wenn das Verzeichnis nicht erreichbar ist, statt das Feld zu sperren", async () => {
    cadastralDistricts.mockRejectedValue(new Error("Das Gemarkungsverzeichnis ist nicht erreichbar."));
    resolveParcel.mockResolvedValue(moelkau);
    landValue.mockRejectedValue(new Error("Kein Bodenrichtwert."));

    const w = atSource();
    await lookUpParcel(w, { district: "Mölkau", number: "85/1" });

    expect(resolveParcel).toHaveBeenCalledWith({ gemarkung: "Mölkau", flurstuecksnummer: "85/1" });
  });

  it("schlägt auch nach, was nur getippt und nicht gewählt wurde", async () => {
    resolveParcel.mockResolvedValue(moelkau);
    landValue.mockRejectedValue(new Error("Kein Bodenrichtwert."));

    const w = atSource();
    await lookUpParcel(w, { district: "Moritzburg", number: "85/1" });

    expect(resolveParcel).toHaveBeenCalledWith({ gemarkung: "Moritzburg", flurstuecksnummer: "85/1" });
  });

  it("lässt die Lesart über die Marke festlegen, wenn sie nicht abzulesen ist", async () => {
    resolveParcel.mockResolvedValue(moelkau);
    landValue.mockRejectedValue(new Error("Kein Bodenrichtwert."));

    // "Moritzburg 85" liest sich als Adresse wie als Flurstück; die Marke
    // sagt es, und ihr Menü entscheidet, statt dass eine der beiden geraten wird.
    const w = atSource();
    await intoQuery(w, "Moritzburg 85");
    await settle();
    expect(w.find(".marker").text()).toBe("2 Lesarten");

    await fixReading(w, "Flurstück");
    await findButton(w, "Grundstück finden").trigger("click");
    await flushPromises();

    expect(resolveParcel).toHaveBeenCalledWith({ gemarkung: "Moritzburg", flurstuecksnummer: "85" });
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


describe("Aufnahme — Absenden", () => {
  const atSource = () =>
    mountWithRouter(WizardView, { path: "/aufnahme/quelle", props: { stage: "quelle" } });

  it("schlägt nach, wenn im Suchfeld nur Enter gedrückt wurde", async () => {
    resolveParcel.mockResolvedValue(moelkau);
    landValue.mockRejectedValue(new Error("Kein Bodenrichtwert."));

    const w = atSource();
    // „Mölkau 204“ lässt genau eine Zeile stehen; Enter nimmt sie, ohne dass
    // der Knopf daneben gedrückt werden muss.
    await intoQuery(w, "Mölkau 204");
    // Pressed before the lookup answered: Enter waits for it rather than
    // taking whatever row happens to stand there already.
    await w.find(".search__field input").trigger("keydown", { key: "Enter" });
    expect(resolveParcel).not.toHaveBeenCalled();
    await settle();

    expect(resolveParcel).toHaveBeenCalledWith({ gemarkung: "Mölkau", flurstuecksnummer: "204" });
  });

  it("liest genau einmal, wenn der Knopf geklickt wird", async () => {
    resolveParcel.mockResolvedValue(moelkau);
    landValue.mockRejectedValue(new Error("Kein Bodenrichtwert."));

    const w = atSource();
    await lookUpParcel(w, { district: "Moritzburg", number: "85/1" });

    expect(resolveParcel).toHaveBeenCalledTimes(1);
  });

  it("schickt bei leerem Feld gar nichts los", async () => {
    const w = atSource();

    // Der Knopf ist gesperrt, und Enter im leeren Feld nimmt keine Zeile.
    expect(findButton(w, "Grundstück finden").attributes("disabled")).toBeDefined();
    await findButton(w, "Grundstück finden").trigger("click");
    await w.find(".search__field input").trigger("keydown", { key: "Enter" });
    await flushPromises();

    expect(resolveParcel).not.toHaveBeenCalled();
  });

  it("nimmt das HTML aus der Zwischenablage mit, nicht nur den Text", async () => {
    readPage.mockResolvedValue({ felder: {}, beschreibung: "", bilder: [] });

    const w = atSource();
    const field = w.find(".search__field input");
    const html = "<html><meta property=\"og:latitude\" content=\"51.19\"><body>Baugrundstück in Lobstädt, 1.025 m²</body></html>";
    await field.trigger("paste", {
      clipboardData: { getData: kind => (kind === "text/html" ? html : "Baugrundstück in Lobstädt, 1.025 m²") }
    });
    await typeInto(field, "Baugrundstück in Lobstädt, 1.025 m²");
    await flushPromises();

    // Dass die Seite und nicht bloß ihr Text angekommen ist, sagt die Marke.
    expect(w.find(".marker").text()).toBe("Anzeigenseite");

    await findButton(w, "Grundstück finden").trigger("click");
    await flushPromises();

    expect(readPage).toHaveBeenCalledWith(html);
  });

  it("vergisst das HTML, sobald das Feld geleert wird", async () => {
    readPage.mockResolvedValue({ felder: {}, beschreibung: "", bilder: [] });

    const w = atSource();
    const field = w.find(".search__field input");
    await field.trigger("paste", {
      clipboardData: { getData: () => "<html>die vorige Seite</html>" }
    });
    await typeInto(field, "die vorige Seite");
    await typeInto(field, "");
    await typeInto(field, "Ein ganz anderer Text, von Hand getippt und lang genug.");
    await flushPromises();

    expect(w.find(".marker").text()).not.toBe("Anzeigenseite");

    // Von Hand getippt und zu kurz, um sich selbst als Beschreibung zu
    // verraten: die Marke legt die Lesart fest.
    await fixReading(w, "Beschreibungstext");
    await findButton(w, "Grundstück finden").trigger("click");
    await flushPromises();

    expect(readPage).toHaveBeenCalledWith("Ein ganz anderer Text, von Hand getippt und lang genug.");
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
    await lookUpParcel(w, { district: "Mölkau", number: "204" });
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
    geocode.mockResolvedValue(LESSINGWEG_44);

    const w = mountWithRouter(WizardView, { path: "/aufnahme/quelle", props: { stage: "quelle" } });
    await intoQuery(w, "Lessingweg 44");
    await settle();
    // Die Adresszeile, nicht die Flurstückszeile: nur sie führt die Adresse
    // mit, gegen die das Kataster seine Lagebezeichnung prüft.
    const row = w.findAll(".hit").find(hit => hit.find(".hit__kind").text() === "Adresse");
    await row.trigger("mousedown");
    await flushPromises();
    await w.setProps({ stage: "flurstueck" });
    await flushPromises();

    expect(w.vm.searchedAddress).toBe("Lessingweg 44");
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


describe("Aufnahme — beide Textwege enden im selben Schritt", () => {
  const atSource = () =>
    mountWithRouter(WizardView, { path: "/aufnahme/quelle", props: { stage: "quelle" } });

  const answer = {
    felder: {
      grundstuecksflaeche_m2: { wert: 1300, quelle_url: null },
      kaufpreis_eur: { wert: 125000, quelle_url: null },
      adresse: { wert: "Sachsen - Rötha", quelle_url: null }
    },
    beschreibung: "Baugrundstück im Ortsteil Oelzschau, zugehörig zur Stadt Rötha.",
    bilder: []
  };

  it("liest getippten Text über dieselbe Stelle wie eine eingefügte Seite", async () => {
    readPage.mockResolvedValue(answer);

    const w = atSource();
    await intoQuery(w, answer.beschreibung);
    await fixReading(w, "Beschreibungstext");
    await findButton(w, "Grundstück finden").trigger("click");
    await flushPromises();

    expect(readPage).toHaveBeenCalledWith(answer.beschreibung);
    // Durch denselben Leser wie eine eingefügte Seite — und weiter, ohne
    // Zwischenschritt: die gelesenen Werte fahren zusammengeklappt mit.
    expect(w.vm.readFields.map(f => f.key)).toContain("grundstuecksflaeche_m2");
    expect(w.vm.description).toContain("Oelzschau");
    expect(w.vm.searchQuery).not.toBeNull();
    expect(w.vm.returnStage).toBe("suche");
  });

  it("führt bei der Fläche die Einheit mit, ohne sie in das Feld zu schreiben", async () => {
    readPage.mockResolvedValue(answer);

    const w = atSource();
    await intoQuery(w, answer.beschreibung);
    await fixReading(w, "Beschreibungstext");
    await findButton(w, "Grundstück finden").trigger("click");
    await flushPromises();

    const area = w.vm.readFields.find(f => f.key === "grundstuecksflaeche_m2");
    expect(area.unit).toBe("m²");
    // Nicht im Wert: das ist die Zahl, die ans Kataster geht.
    expect(String(area.value)).not.toContain("m²");
    expect(w.vm.readFields.find(f => f.key === "kaufpreis_eur").unit).toBe("€");
    // A name is not a unit: only the fields that have one carry one.
    expect(w.vm.readFields.find(f => f.key === "adresse").unit).toBe("");
  });
});


/**
 * The wizard's half of the handover. The bookmarklet's half — and the fact
 * that the generated one-liner runs at all — is in `bookmarklet.test.js`.
 */
describe("Aufnahme — Seite aus dem Browser übernommen", () => {
  const answer = {
    felder: {
      adresse: { wert: "Wiesenstraße, 04668 Großbothen", quelle: "gelesen" },
      lat: { wert: 51.189265, quelle: "gelesen" },
      lon: { wert: 12.85, quelle: "gelesen" },
      grundstuecksflaeche_m2: { wert: 502, quelle: "gelesen" },
      kaufpreis_eur: { wert: 60000, quelle: "gelesen" }
    },
    weg: "eingefuegter-text",
    beschreibung: "Am Ortsrand von Großbothen, einem OT von Grimma. Flurstück 790/11.",
    bilder: []
  };

  /** The tab the bookmarklet opened: an address carrying the nonce, and an
   *  opener to answer.
   *
   *  The router has to be *ready* before it is handed to `mount`, and that is
   *  not a detail: `router.push` is async, so at install time `currentRoute`
   *  is still the start location and vue-router pushes the history's own — `/`
   *  — which lands after ours and wins. The component then sees an empty
   *  query. No existing test noticed because every view takes its state from
   *  props, and this is the first one that reads the address itself. */
  const opened = async (nonce = "1757403600123456") => {
    const opener = { postMessage: vi.fn() };
    Object.defineProperty(window, "opener", { value: opener, writable: true, configurable: true });
    const router = testRouter(`/aufnahme/quelle?${HANDOVER_QUERY}=${nonce}`);
    await router.isReady();
    const w = mountWithRouter(WizardView, { router, props: { stage: "quelle" } });
    await flushPromises();
    return { w, opener, nonce };
  };

  /** A message as the other tab sends it. `source` is a prototype getter, so
   *  it has to be shadowed — which is the check the wizard leans on. */
  const from = (source, data) => {
    const event = new MessageEvent("message", { data });
    Object.defineProperty(event, "source", { value: source });
    return event;
  };

  afterEach(() => {
    Object.defineProperty(window, "opener", { value: null, writable: true, configurable: true });
  });

  it("meldet sich beim Tab, der es geöffnet hat, und wartet", async () => {
    const { w, opener, nonce } = await opened();

    expect(opener.postMessage).toHaveBeenCalledWith(
      { w2b: HANDOVER_READY, [HANDOVER_QUERY]: nonce },
      "*"
    );
    // Statt des Feldes steht da, worauf gewartet wird — niemand hat etwas zu tun.
    expect(w.text()).toContain("Warten auf die Seite");
    expect(w.find(".query-box").exists()).toBe(false);
    expect(readPage).not.toHaveBeenCalled();
  });

  it("liest die übergebene Seite, ohne dass noch etwas geklickt wird", async () => {
    readPage.mockResolvedValue(answer);
    resolveParcel.mockResolvedValue(moelkau);

    const { w, opener, nonce } = await opened();

    const html = '<html><head><meta property="og:latitude" content="51.189265">'
      + "</head><body>Baugrundstück 502 m²</body></html>";
    window.dispatchEvent(from(opener, {
      w2b: HANDOVER_PAGE, [HANDOVER_QUERY]: nonce, url: "https://portal.example/expose/1", html
    }));
    await flushPromises();

    // Genau das, was der Browser vor sich hatte — mit Kopf, den das Kopieren verliert.
    expect(readPage).toHaveBeenCalledWith(html);
    expect(w.vm.handover.url).toBe("https://portal.example/expose/1");
    expect(w.vm.readFields.find(f => f.key === "kaufpreis_eur").value).toBe(60000);
  });

  it("nimmt keine Nachricht mit falscher Nonce und keine aus einem anderen Fenster", async () => {
    const { opener, nonce } = await opened();

    const html = "<html><body>x</body></html>";
    window.dispatchEvent(from(opener, {
      w2b: HANDOVER_PAGE, [HANDOVER_QUERY]: "fremd", html
    }));
    window.dispatchEvent(from({ postMessage: vi.fn() }, {
      w2b: HANDOVER_PAGE, [HANDOVER_QUERY]: nonce, html
    }));
    await flushPromises();

    expect(readPage).not.toHaveBeenCalled();
  });

  it("zeigt ohne öffnenden Tab einfach das Feld", async () => {
    // Von Hand aufgerufen, oder der andere Tab ist fort: es gibt niemanden,
    // der antworten könnte. Dann ist das gewöhnliche Feld die Antwort, und es
    // muss dazu nichts sagen.
    Object.defineProperty(window, "opener", { value: null, writable: true, configurable: true });
    const router = testRouter(`/aufnahme/quelle?${HANDOVER_QUERY}=1757403600123456`);
    await router.isReady();
    const w = mountWithRouter(WizardView, { router, props: { stage: "quelle" } });
    await flushPromises();

    expect(w.vm.handoverWaiting).toBe(false);
    expect(w.find(".query-box").exists()).toBe(true);
    expect(w.text()).not.toContain("Warten auf die Seite");
  });

  it("bietet das Lesezeichen mit der eigenen Adresse an, ohne dass jemand einen Weg wählt", async () => {
    // Es gibt keine Wege mehr, unter denen es sich verstecken könnte: ein Feld,
    // und darunter der Klappkasten. Wer mit einer ImmoScout-Adresse kommt,
    // findet ihn also, ohne den Hinweis gelesen zu haben.
    const w = mountWithRouter(WizardView, { path: "/aufnahme/quelle", props: { stage: "quelle" } });
    await flushPromises();

    const link = w.find("details.gelesen--lesezeichen a.btn");
    expect(link.exists()).toBe(true);
    const href = link.attributes("href");
    expect(href.startsWith("javascript:")).toBe(true);
    expect(decodeURI(href)).toContain(JSON.stringify(window.location.origin));
  });

  it("verwechselt den eigenen Klappkasten nicht mit dem der Suche", async () => {
    // Beide heißen `details.gelesen`. Ein Skript, das auf einen wartet, würde
    // sonst den der Einstiegsseite treffen und auf eine Liste warten, die dort
    // nie kommt — genau das ist beim Zusammenführen fast passiert.
    const w = mountWithRouter(WizardView, { path: "/aufnahme/quelle", props: { stage: "quelle" } });
    await flushPromises();

    expect(w.findAll("details.gelesen:not(.gelesen--lesezeichen)")).toHaveLength(0);
  });
});


/**
 * The head of the search step: what was read, as the advert looked, with the
 * editable values folded underneath — one box, not a preview and a list.
 * The answer is the real extract of the recorded Kleinanzeigen page, copied
 * with Strg+A (so without `<head>` and its coordinate).
 */
describe("Aufnahme — Vorschau der gelesenen Anzeige im Suchschritt", () => {
  const read = async (payload, answer) => {
    readPage.mockResolvedValue(answer);
    const w = mountWithRouter(WizardView, {
      path: "/aufnahme/quelle", props: { stage: "quelle" }, stubs: { ParcelSearch: true }
    });
    await flushPromises();
    await w.vm.readPayload(payload);
    await w.setProps({ stage: "suche" });
    await flushPromises();
    return w;
  };

  it("steht als Erstes im Schritt und trägt den Klappkasten mit den Werten", async () => {
    const w = await read({ kind: "page", text: "", html: "<html><body>…</body></html>" }, pasted);

    const section = w.find("section.stack");
    expect(section.element.firstElementChild.classList.contains("listing-preview")).toBe(true);
    expect(w.find(".listing-preview .mini").exists()).toBe(true);
    const fold = w.find(".listing-preview details.gelesen");
    expect(fold.exists()).toBe(true);
    expect(fold.find(".gelesen__zahl").text()).toBe(w.vm.readSummary);
    // Genau ein Klappkasten der Suche, und die Felder darin sind noch dieselben.
    expect(w.findAll("details.gelesen:not(.gelesen--lesezeichen)")).toHaveLength(1);
    expect(fold.findAll(".suggestion input")).toHaveLength(w.vm.readFields.length);
    expect(w.text()).toContain("Koordinate fehlt");
  });

  it("startet die Suche aus dem Klappkasten neu, wie zuvor", async () => {
    const w = await read({ kind: "page", text: "", html: "<html><body>…</body></html>" }, pasted);
    const before = w.vm.searchRun;

    await w.find(".listing-preview details.gelesen .suggestion input")
      .trigger("keydown", { key: "Enter" });
    expect(w.vm.searchRun).toBe(before + 1);

    await findButton(w, "Suche mit diesen Werten neu starten").trigger("click");
    expect(w.vm.searchRun).toBe(before + 2);
  });

  it("zeigt bei getipptem Text keine Vorschau, nur die Werte", async () => {
    const w = await read({ kind: "prose", text: "Baugrundstück in Lobstädt", html: "" }, pasted);

    expect(w.find(".listing-preview .mini").exists()).toBe(false);
    expect(w.find(".listing-preview .karte").exists()).toBe(false);
    expect(w.find(".listing-preview details.gelesen").exists()).toBe(true);
  });

  it("führt über „Lesezeichen nimmt ihn mit“ zurück zum Einstieg", async () => {
    const w = await read({ kind: "page", text: "", html: "<html><body>…</body></html>" }, pasted);
    const back = vi.spyOn(w.vm, "stepBack");

    await findButton(w, "Lesezeichen nimmt ihn mit").trigger("click");
    expect(back).toHaveBeenCalledWith("quelle");
  });
});
