/**
 * The destinations page: what a new destination starts as, and what a stored
 * one looks like.
 *
 * The geocoder is mocked, but not invented: every candidate below is one of the
 * two places the recorded MOTIS answer in tests/fixtures/ actually routes to,
 * with the coordinates that answer carries.
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { nextTick } from "vue";
import DestinationsView from "../src/views/DestinationsView.vue";
import {
  state, validate, exportJson, addDestination, locateDestination, destinationName, UNNAMED_DESTINATION
} from "../src/lib/store.js";
import { SCHEMA_VERSION } from "../src/lib/sample.js";
import { realState, realPlot, realRoutes, realDestinations, mountWithRouter } from "./helpers.js";
import { zubringerOf } from "../src/lib/routes.js";

vi.mock("../src/lib/api.js", () => ({
  geocode: vi.fn(),
  nearby: vi.fn(() => Promise.reject(new Error("nicht Teil dieses Tests"))),
  reachability: vi.fn(() => Promise.reject(new Error("nicht Teil dieses Tests")))
}));
const { geocode } = await import("../src/lib/api.js");

const HBF = "zl-hbf";
/* The slot the document is stored in. Named here rather than imported: what a
   test checks is that nothing surprising reaches the browser's store. */
const STORAGE_KEY = "where2build.v1";

/** The recorded destinations, with the routes the fixture computed to them. */
const locatedState = () => validate({
  version: SCHEMA_VERSION,
  plots: [{ ...realPlot("convex"), routes: realRoutes() }],
  houseTypes: [],
  destinations: realDestinations(),
  selection: []
});

/** A geocoder answer built from the recorded destinations. */
const answerWith = (...destinations) => ({
  treffer: destinations.map(d => ({
    name: d.match, beschreibung: d.address, lat: d.lat, lon: d.lon, art: "sonstiges"
  })),
  hinweis: "Bitte den Treffer prüfen.",
  quelle: "MOTIS / Transitous (DELFI-GTFS, OpenStreetMap)"
});

const open = (options = {}) => mountWithRouter(DestinationsView, { path: "/ziele", ...options });

const clickText = (wrapper, label) =>
  wrapper.findAll("button").find(b => b.text().trim() === label).trigger("click");

const editButtons = wrapper =>
  wrapper.findAll("button").filter(b => (b.attributes("aria-label") || "").includes("bearbeiten"));

beforeEach(() => {
  localStorage.clear();
  state.data = realState();
  geocode.mockReset();
});

describe("Ein neues Ziel", () => {
  it("kommt mit leerem Namensfeld, in dem „Neues Ziel“ nur als Vorschlag steht", async () => {
    state.data.destinations = [];
    const w = open();

    await clickText(w, "Erstes Ziel anlegen");
    const created = state.data.destinations[0];
    const nameField = w.find(`#n-${created.id}`);

    expect(created.name).toBe("");
    expect(nameField.element.value).toBe("");
    expect(nameField.attributes("placeholder")).toBe("Neues Ziel");
  });

  it("schreibt „Neues Ziel“ nirgends in das Dokument", async () => {
    state.data.destinations = [];
    const w = open();

    await clickText(w, "Erstes Ziel anlegen");

    expect(exportJson()).not.toContain("Neues Ziel");
    expect(localStorage.getItem(STORAGE_KEY)).not.toContain("Neues Ziel");
  });

  it("bleibt ohne Koordinate direkt bearbeitbar und sagt, was noch fehlt", () => {
    const w = open();
    expect(w.findAll('input[type="text"]')).toHaveLength(2);   // Name und Adresse
    expect(editButtons(w)).toHaveLength(0);
    expect(w.text()).toContain("Noch nicht verortet");
  });

  it("wird beim Übernehmen eines Treffers zum abgelegten Eintrag", async () => {
    const [hbf] = realDestinations();
    geocode.mockResolvedValue(answerWith(hbf));
    const w = open();
    const target = state.data.destinations[0];

    await w.find(`#a-${target.id}`).setValue(hbf.address);
    await clickText(w, "Nachschlagen");
    await nextTick();

    expect(target.lat).toBe(hbf.lat);
    expect(w.findAll('input[type="text"]')).toHaveLength(0);
    expect(w.text()).toContain("Gespeichert");
  });
});

describe("Ein verortetes Ziel", () => {
  beforeEach(() => { state.data = locatedState(); });

  it("steht als Eintrag da, nicht als Formular", () => {
    const w = open();

    expect(w.findAll('input[type="text"]')).toHaveLength(0);
    expect(w.findAll(".destination-record")).toHaveLength(2);
    const text = w.text();
    expect(text).toContain("Leipzig Hauptbahnhof");
    expect(text).toContain("Willy-Brandt-Platz 5, Leipzig");
    expect(text).toContain("51.34590, 12.38330");
    expect(text).toContain("Gespeichert");
  });

  it("benennt im Bearbeiten-Knopf das Ziel, um das es geht", () => {
    const labels = editButtons(open()).map(b => b.attributes("aria-label"));
    expect(labels).toEqual(["„Leipzig Hauptbahnhof“ bearbeiten", "„Grundschule Liebertwolkwitz“ bearbeiten"]);
  });

  it("öffnet die Felder erst auf Knopfdruck und setzt den Cursor in den Namen", async () => {
    // Attached: focus is a property of the document, not of the wrapper.
    const w = open({ attach: true });

    await editButtons(w)[0].trigger("click");
    await nextTick();

    expect(w.find(`#n-${HBF}`).element.value).toBe("Leipzig Hauptbahnhof");
    expect(document.activeElement.id).toBe(`n-${HBF}`);
    w.unmount();
  });

  it("verliert nichts, wenn die Bearbeitung ohne Änderung endet", async () => {
    const w = open();

    await editButtons(w)[0].trigger("click");
    await clickText(w, "Fertig");

    expect(state.data.destinations[0].lat).toBe(51.3459);
    expect(state.data.plots[0].routes[HBF]).toBeTruthy();
    expect(w.findAll(".destination-record")).toHaveLength(2);
  });

  it("verliert auch nichts, wenn eine geänderte Adresse verworfen wird", async () => {
    const w = open();

    await editButtons(w)[0].trigger("click");
    await w.find(`#a-${HBF}`).setValue("Nonnenstraße 39, Leipzig");
    await clickText(w, "Abbrechen");

    expect(state.data.destinations[0].address).toBe("Willy-Brandt-Platz 5, Leipzig");
    expect(state.data.destinations[0].lat).toBe(51.3459);
    expect(state.data.plots[0].routes[HBF]).toBeTruthy();
  });

  it("kündigt den Verlust der Verortung an, bevor die neue Adresse greift", async () => {
    const w = open();

    await editButtons(w)[0].trigger("click");
    await w.find(`#a-${HBF}`).setValue("Nonnenstraße 39, Leipzig");

    const warning = w.find(".notice--warn");
    expect(warning.exists()).toBe(true);
    expect(warning.text()).toContain("verworfen");
    expect(warning.text()).toContain("Wege");
    // Announced, and nothing lost yet.
    expect(state.data.destinations[0].lat).toBe(51.3459);
    expect(state.data.plots[0].routes[HBF]).toBeTruthy();
  });

  it("gibt Koordinate und Wege erst mit der übernommenen Adresse auf", async () => {
    const w = open();

    await editButtons(w)[0].trigger("click");
    await w.find(`#a-${HBF}`).setValue("Nonnenstraße 39, Leipzig");
    await clickText(w, "Fertig");

    const destination = state.data.destinations[0];
    expect(destination.address).toBe("Nonnenstraße 39, Leipzig");
    expect(destination.lat).toBeUndefined();
    expect(destination.match).toBeUndefined();
    expect(state.data.plots[0].routes[HBF]).toBeUndefined();
    expect(w.text()).toContain("Noch nicht verortet");
  });

  it("ändert einen Namen, ohne die Verortung anzutasten", async () => {
    const w = open();

    await editButtons(w)[0].trigger("click");
    await w.find(`#n-${HBF}`).setValue("Bahnhof");
    await clickText(w, "Fertig");

    expect(state.data.destinations[0].name).toBe("Bahnhof");
    expect(state.data.destinations[0].lat).toBe(51.3459);
    expect(state.data.plots[0].routes[HBF]).toBeTruthy();
  });
});

describe("Ein Ziel ohne Namen", () => {
  it("heißt überall gleich, wo es angezeigt wird", () => {
    expect(destinationName({ id: "dest-1", name: "" })).toBe(UNNAMED_DESTINATION);
    expect(destinationName({ id: "dest-1", name: "   " })).toBe(UNNAMED_DESTINATION);
    expect(destinationName({ id: "dest-1", name: "Arbeit" })).toBe("Arbeit");
  });

  it("steht mit diesem Namen im Eintrag und in der Rückfrage vor dem Entfernen", async () => {
    const [hbf] = realDestinations();
    state.data.destinations = [{ ...hbf, name: "" }];
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    const w = open();

    expect(w.find(".destination-record__name").text()).toBe(UNNAMED_DESTINATION);
    expect(editButtons(w)[0].attributes("aria-label")).toBe(`„${UNNAMED_DESTINATION}“ bearbeiten`);

    await clickText(w, "Entfernen");
    expect(confirm.mock.calls[0][0]).toContain(UNNAMED_DESTINATION);
    confirm.mockRestore();
  });

  it("übernimmt beim Verorten den Namen, den der Geocoder gefunden hat", () => {
    state.data.destinations = [];
    const created = addDestination();

    locateDestination(created.id, { lat: 51.3459, lon: 12.3833, match: "Leipzig Hauptbahnhof" });

    expect(created.name).toBe("Leipzig Hauptbahnhof");
  });

  it("überlebt die Prüfung des Speichers samt der Wege dorthin", () => {
    const checked = validate({
      version: SCHEMA_VERSION,
      plots: [{ ...realPlot("convex"), routes: realRoutes() }],
      houseTypes: [],
      destinations: realDestinations().map(d => ({ ...d, name: "" })),
      selection: []
    });

    expect(checked.destinations).toHaveLength(2);
    expect(checked.destinations[0].name).toBe("");
    expect(checked.plots[0].routes[HBF]).toBeTruthy();
  });
});

describe("Zubringer zum ÖPNV", () => {
  it("steht auf Automatisch, solange nichts festgelegt wurde", () => {
    const w = mountWithRouter(DestinationsView);
    const picker = w.find("select");
    expect(picker.exists()).toBe(true);
    expect(picker.element.value).toBe("automatic");
    expect(w.text()).toContain("zehn Minuten");
  });

  it("lässt sich am fertigen Datensatz ändern, ohne ihn zu öffnen", async () => {
    // The two destinations the recorded routes actually lead to; both located.
    state.data.destinations = realDestinations();
    const w = mountWithRouter(DestinationsView);
    expect(w.findAll(".destination-record").length).toBe(2);

    await w.findAll("select")[0].setValue("bike");
    expect(state.data.destinations[0].zubringer).toBe("bike");
    // Still a filed record: nothing about the place itself was touched.
    expect(state.data.destinations[0].lat).toEqual(expect.any(Number));
    expect(w.findAll(".destination-record").length).toBe(2);
  });

  it("löscht das Feld wieder, wenn auf Automatisch zurückgestellt wird", async () => {
    const w = mountWithRouter(DestinationsView);
    await w.findAll("select")[0].setValue("car");
    expect(state.data.destinations[0].zubringer).toBe("car");

    await w.findAll("select")[0].setValue("automatic");
    expect("zubringer" in state.data.destinations[0]).toBe(false);
  });

  /* The failure this pins down is silent: the picker works, and the choice is
     gone after a reload because `validate` rebuilt the destination without it. */
  it("überlebt Speichern und Einlesen", () => {
    const raw = realState();
    raw.destinations[0].zubringer = "bike";
    const read = validate(JSON.parse(JSON.stringify(raw)));
    expect(read.destinations[0].zubringer).toBe("bike");
  });

  it("wirft einen unbekannten Wert weg, statt ihn weiterzureichen", () => {
    const raw = realState();
    raw.destinations[0].zubringer = "helikopter";
    const read = validate(JSON.parse(JSON.stringify(raw)));
    expect("zubringer" in read.destinations[0]).toBe(false);
    expect(zubringerOf(read.destinations[0])).toBe("automatic");
  });
});
