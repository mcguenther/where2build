/** State, persistence and the JSON exchange. */
import { describe, it, expect, beforeEach } from "vitest";
import {
  state, validate, load, save, clear, exportJson, importJson,
  plotById, houseTypeById, houseFootprint, placement, centreOf,
  addPlot, removePlot, toggleSelection, addHouseType, removeHouseType,
  addDestination, removeDestination, applyTheme, CUSTOM_SIZE,
  DEFAULT_FOOTPRINT, seatHouse, autoSeatHouse
} from "../src/lib/store.js";
import { SCHEMA_VERSION } from "../src/lib/sample.js";
import { realState, realStateV1, realPlot, realHouseType, realRoutes } from "./helpers.js";
import { buildableArea, cornersOutside, alignmentToEdge, rectangleCorners, pointInPolygon }
  from "../src/lib/geometry.js";

const square = [{ x: 0, y: 0 }, { x: 20, y: 0 }, { x: 20, y: 30 }, { x: 0, y: 30 }];

beforeEach(() => {
  localStorage.clear();
  state.data = realState();
});

describe("Prüfung beim Einlesen", () => {
  it("nimmt einen vollständigen Stand an", () => {
    const d = validate(realState());
    expect(d.plots).toHaveLength(2);
    expect(d.houseTypes.length).toBeGreaterThan(0);
    expect(d.destinations.length).toBeGreaterThan(0);
  });

  it("weist zurück, was keine Grundstücke enthält", () => {
    expect(() => validate(null)).toThrow(/Objekt/);
    expect(() => validate({})).toThrow(/plots/);
    expect(() => validate({ plots: "nein" })).toThrow(/plots/);
  });

  it("weist Grundstücke ohne brauchbare Geometrie zurück", () => {
    expect(() => validate({ plots: [{ name: "ohne Polygon" }] })).toThrow(/Geometrie/);
    expect(() => validate({ plots: [{ polygon: [{ x: 1 }] }] })).toThrow(/Geometrie/);
  });

  it("ergänzt fehlende Felder mit vernünftigen Werten", () => {
    const d = validate({ plots: [{ polygon: square }] });
    const p = d.plots[0];
    expect(p.id).toBeTruthy();
    expect(p.setbacks).toEqual([3, 3, 3, 3]);
    expect(p.ratio).toBe(1.35);
    expect(p.wallHeight).toBe(6.4);
    expect(p.house.cx).toBeCloseTo(10, 6);
    expect(p.house.cy).toBeCloseTo(15, 6);
    expect(p.routes).toEqual({});
  });

  it("begrenzt unsinnige Werte statt sie zu übernehmen", () => {
    const d = validate({ plots: [{
      polygon: square, setbacks: [99, -5, 3, 3], ratio: 9, wallHeight: 99,
      customSize: { length: 500, width: 0.2 }
    }] });
    const p = d.plots[0];
    expect(p.setbacks).toEqual([20, 0, 3, 3]);
    expect(p.ratio).toBe(2.2);
    expect(p.wallHeight).toBe(12);
    expect(p.customSize).toEqual({ length: 30, width: 4 });
  });

  it("wirft Haustypen außerhalb der Plausibilitätsgrenzen weg", () => {
    const d = validate({
      plots: [{ polygon: square }],
      houseTypes: [{ id: "a", builtArea: 25 }, { id: "b", builtArea: 500 }, { id: "c", builtArea: 96.88 }]
    });
    expect(d.houseTypes.map(h => h.id)).toEqual(["c"]);
  });

  it("behält nur Auswahl-Kennungen, die es auch gibt", () => {
    const d = validate({ plots: [{ polygon: square, id: "plot-1" }], selection: ["plot-1", "gibt-es-nicht"] });
    expect(d.selection).toEqual(["plot-1"]);
  });
});

describe("Schema-Fassungen", () => {
  it("schreibt beim Ausgeben immer die aktuelle Fassung", () => {
    expect(SCHEMA_VERSION).toBe(2);
    expect(validate(realState()).version).toBe(2);
    expect(JSON.parse(exportJson()).version).toBe(2);
  });

  it("nimmt eine Datei aus einer neueren Fassung nicht an", () => {
    const future = { ...realState(), version: 3 };
    expect(() => validate(future)).toThrow(/neueren Fassung/);
    expect(() => validate(future)).toThrow(/Version 3/);
  });

  it("liest eine Fassung 2 unverändert, ohne sie durch die Umschreibung zu schicken", () => {
    const d = validate(realState());
    expect(d.plots[0].officialArea).toBe(realState().plots[0].officialArea);
    expect(d.plots[0].gemarkung).toBeTruthy();
  });

  it("übernimmt aus einer Fassung 1 jedes Grundstück, jeden Haustyp und jedes Ziel", () => {
    const d = validate(realStateV1());
    expect(d.version).toBe(2);
    expect(d.plots).toHaveLength(2);
    expect(d.houseTypes).toHaveLength(1);
    expect(d.destinations).toHaveLength(1);
    expect(d.selection).toEqual(["plot-convex", "plot-concave"]);
  });

  it("benennt die Felder eines Grundstücks um, ohne einen Wert zu verlieren", () => {
    const before = realStateV1().grundstuecke[0];
    const after = validate(realStateV1()).plots[0];
    expect(after.officialArea).toBe(before.flaecheAmtlich);
    expect(after.askingPrice).toBe(before.kaufpreis);
    expect(after.anchor).toEqual(before.anker);
    expect(after.setbacks).toEqual(before.tiefen);
    expect(after.wallHeight).toBe(before.wandhoehe);
    expect(after.ratio).toBe(before.verhaeltnis);
    expect(after.streetEdge).toBe(before.strassenkante);
    expect(after.northOffset).toBe(before.nordVersatz);
    expect(after.house).toEqual(before.haus);
    expect(after.municipality).toBe(before.ort);
    expect(after.note).toBe(before.notiz);
    expect(after.brwReferenceDate).toBe(before.brwStichtag);
    // The authority's own field names never changed.
    expect(after.gemarkung).toBe(before.gemarkung);
    expect(after.bodenrichtwert).toBe(before.bodenrichtwert);
    expect(after.flurstuecke).toEqual(before.flurstuecke);
    expect(after.kennzeichen).toBe(before.kennzeichen);
    // And nothing German is left behind on the migrated object.
    expect(Object.keys(after)).not.toContain("flaecheAmtlich");
    expect(Object.keys(after)).not.toContain("tiefen");
    expect(Object.keys(after)).not.toContain("wege");
  });

  it("benennt die Felder eines Haustyps um", () => {
    const before = realStateV1().haustypen[0];
    const after = validate(realStateV1()).houseTypes[0];
    expect(after.builtArea).toBe(before.bebauteFlaeche);
    expect(after.livingArea).toBe(before.wohnflaeche);
    expect(after.manufacturer).toBe(before.hersteller);
    expect(after.roofShape).toBe(before.dachform);
    expect(after.readAt).toBe(before.gelesenAm);
    expect(after.custom).toBe(before.eigen);
  });

  it("benennt Adresse und Treffer eines Ziels um", () => {
    const v1 = realStateV1();
    v1.ziele[0].lat = 51.34;
    v1.ziele[0].lon = 12.38;
    v1.ziele[0].treffer = "Nonnenstraße 39";
    const after = validate(v1).destinations[0];
    expect(after.address).toBe("Nonnenstraße 39, Leipzig");
    expect(after.match).toBe("Nonnenstraße 39");
  });

  it("rettet die Wege samt Geometrie über die Umbenennung", () => {
    const v1 = realStateV1();
    v1.grundstuecke[0].wege = Object.fromEntries(Object.entries(realRoutes()).map(([id, route]) => [
      id, { modi: route.modes, berechnet_am: route.calculatedAt, quelle: route.source }
    ]));
    v1.ziele = [{ id: "zl-hbf", name: "Leipzig Hauptbahnhof", adresse: "", lat: 51.3459, lon: 12.3833 }];

    const route = validate(v1).plots[0].routes["zl-hbf"];
    expect(Object.keys(route.modes).sort()).toEqual(["bike", "car", "transit"]);
    expect(route.modes.car.duration_s).toBe(754);
    expect(route.modes.car.geometry.coordinates).toHaveLength(455);
    expect(route.source).toMatch(/^MOTIS/);
    expect(route.calculatedAt).toBe("2026-08-29T20:22:00.000Z");
  });

  it("übersetzt die Kennung für eigene Maße mit", () => {
    const v1 = realStateV1();
    v1.grundstuecke[0].haustypId = "eigen";
    v1.grundstuecke[0].eigenmass = { laenge: 13, breite: 9 };
    const p = validate(v1).plots[0];
    expect(p.houseTypeId).toBe(CUSTOM_SIZE);
    expect(p.customSize).toEqual({ length: 13, width: 9 });
    expect(houseFootprint(p)).toMatchObject({ width: 13, depth: 9, custom: true });
  });

  it("hält eine Fassung-1-Datei über eine volle Runde durch Ausgeben und Einlesen", () => {
    importJson(JSON.stringify(realStateV1()));
    const again = validate(JSON.parse(exportJson()));
    expect(again.version).toBe(2);
    expect(again.plots).toHaveLength(2);
    expect(again.houseTypes).toHaveLength(1);
    expect(again.destinations).toHaveLength(1);
  });

  it("liest einen Stand ohne Versionsangabe an seinen Feldnamen ab", () => {
    const withoutVersion = realStateV1();
    delete withoutVersion.version;
    expect(validate(withoutVersion).plots).toHaveLength(2);

    const current = realState();
    delete current.version;
    expect(validate(current).plots).toHaveLength(2);
  });

  it("holt einen alten Eintrag aus dem Browser-Speicher herauf", () => {
    localStorage.setItem("where2build.v1", JSON.stringify(realStateV1()));
    state.data = { version: SCHEMA_VERSION, plots: [], houseTypes: [], destinations: [], selection: [] };
    load();
    expect(state.data.version).toBe(2);
    expect(state.data.plots).toHaveLength(2);
    expect(state.data.plots[0].officialArea).toBeGreaterThan(0);
  });
});

describe("Nachbarschaft im Dokument", () => {
  /* The „Nachbarn" switch was a stored flag; the tab that replaced it loads
     when opened, so the flag is dropped on the way in. The readings chosen
     per Grenzbebauung are the user's and survive a round trip. */
  it("wirft den alten Schalter „Nachbarn“ weg", () => {
    const raw = realState();
    raw.plots[0].showNeighbours = true;
    const d = validate(raw);
    expect("showNeighbours" in d.plots[0]).toBe(false);
  });

  it("behält die gewählte Lesart je Gebäude und nur bekannte Werte", () => {
    const raw = realState();
    raw.plots[0].neighbourReadings = { DEBE01: "boundary", DEBE02: "setback", DEBE03: "vielleicht", "": "boundary" };
    const p = validate(raw).plots[0];
    expect(p.neighbourReadings).toEqual({ DEBE01: "boundary", DEBE02: "setback" });
  });

  it("legt kein leeres Feld an, wo niemand gewählt hat", () => {
    const raw = realState();
    raw.plots[0].neighbourReadings = { DEBE03: 42 };
    raw.plots[1].neighbourReadings = "boundary";
    const d = validate(raw);
    expect("neighbourReadings" in d.plots[0]).toBe(false);
    expect("neighbourReadings" in d.plots[1]).toBe(false);
  });

  it("übersteht Ausgeben und Einlesen samt Lesart", () => {
    state.data.plots[0].neighbourReadings = { DEBE01: "boundary" };
    state.data.plots[0].showNeighbours = true;
    const text = exportJson();
    importJson(text);
    expect(state.data.plots[0].neighbourReadings).toEqual({ DEBE01: "boundary" });
    expect(state.data.plots[0].showNeighbours).toBeUndefined();
  });

  it("holt einen gespeicherten Stand mit dem alten Schalter aus dem Browser herauf", () => {
    const raw = realState();
    raw.plots[0].showNeighbours = true;
    raw.plots[0].neighbourReadings = { DEBE01: "boundary" };
    save();
    const key = Object.keys(localStorage)[0];
    localStorage.setItem(key, JSON.stringify(raw));
    load();
    expect(state.data.plots[0].showNeighbours).toBeUndefined();
    expect(state.data.plots[0].neighbourReadings).toEqual({ DEBE01: "boundary" });
  });
});

describe("Ausgeben und Einlesen", () => {
  it("übersteht eine Runde ohne Verlust", () => {
    const before = exportJson();
    importJson(before);
    expect(JSON.parse(exportJson()).plots).toHaveLength(2);
  });

  it("meldet unbrauchbares JSON auf Deutsch und lässt den Stand unberührt", () => {
    for (const rubbish of ["kein json", "{}", '{"plots":"nein"}', ""]) {
      expect(() => importJson(rubbish)).toThrow();
    }
    expect(state.data.plots).toHaveLength(2);
  });

  it("ersetzt den Stand bei gültiger Eingabe", () => {
    const smaller = { ...realState(), plots: [realPlot("convex")] };
    importJson(JSON.stringify(smaller));
    expect(state.data.plots).toHaveLength(1);
  });
});

describe("Speicher im Browser", () => {
  it("legt ab und liest zurück", () => {
    state.data.plots[0].wallHeight = 7.7;
    save();
    state.data = realState();
    load();
    expect(state.data.plots[0].wallHeight).toBe(7.7);
  });

  it("überlebt einen kaputten Eintrag", () => {
    localStorage.setItem("where2build.v1", "{kaputt");
    load();
    expect(state.data.plots).toHaveLength(2);
  });

  it("läuft weiter, wenn der Speicher verweigert wird", () => {
    const original = Storage.prototype.setItem;
    Storage.prototype.setItem = () => { throw new Error("QuotaExceeded"); };
    expect(() => save()).not.toThrow();
    expect(() => applyTheme("dark")).not.toThrow();
    Storage.prototype.setItem = original;
  });

});

describe("Baukörper aus dem Haustyp", () => {
  it("nimmt die Außenmaße, wenn das Datenblatt sie liefert", () => {
    const plot = plotById("plot-convex");
    addHouseType({ id: "ht-mass", manufacturer: "Von Hand eingetragen", name: "12 × 9 m",
      builtArea: 108, length: 12, width: 9, ratio: 12 / 9, custom: true });
    plot.houseTypeId = "ht-mass";
    expect(houseFootprint(plot)).toMatchObject({ width: 12, depth: 9, estimated: false });
  });

  it("schätzt aus der bebauten Fläche, wenn nicht", () => {
    const plot = plotById("plot-concave");
    const f = houseFootprint(plot);          // ELK All in One 159, ohne Außenmaße
    expect(f.estimated).toBe(true);
    expect(f.width * f.depth).toBeCloseTo(96.88, 6);
    expect(f.width / f.depth).toBeCloseTo(1.35, 6);
  });

  it("nimmt eigene Maße, wenn welche eingetragen sind", () => {
    const plot = plotById("plot-concave");
    plot.houseTypeId = CUSTOM_SIZE;
    plot.customSize = { length: 13, width: 9 };
    expect(houseFootprint(plot)).toMatchObject({ width: 13, depth: 9, custom: true });
  });

  it("setzt die Platzierung aus Maßen und Lage zusammen", () => {
    const plot = plotById("plot-concave");
    const p = placement(plot);
    expect(p).toMatchObject({ cx: plot.house.cx, cy: plot.house.cy, rotation: plot.house.rotation });
    expect(Number.isFinite(p.width) && Number.isFinite(p.depth)).toBe(true);
  });

  it("centreOf liefert cx/cy, nicht x/y — sonst wird die Lage NaN", () => {
    expect(centreOf(square)).toEqual({ cx: 10, cy: 15, rotation: 0 });
  });
});

describe("Grundstücke, Haustypen und Ziele verwalten", () => {
  it("nimmt ein Grundstück auf und wählt es gleich aus", () => {
    const fresh = { ...validate({ plots: [{ polygon: square, id: "plot-neu" }] }).plots[0] };
    addPlot(fresh);
    expect(state.data.plots).toHaveLength(3);
    expect(state.data.selection).toContain("plot-neu");
  });

  it("entfernt ein Grundstück samt Auswahl", () => {
    removePlot("plot-convex");
    expect(plotById("plot-convex")).toBeNull();
    expect(state.data.selection).not.toContain("plot-convex");
  });

  it("nimmt Kandidaten in die Auswahl und wieder heraus", () => {
    toggleSelection("plot-convex", false);
    expect(state.data.selection).not.toContain("plot-convex");
    toggleSelection("plot-convex", true);
    expect(state.data.selection).toContain("plot-convex");
    toggleSelection("plot-convex", true);   // doppelt bleibt einfach
    expect(state.data.selection.filter(id => id === "plot-convex")).toHaveLength(1);
  });

  it("lässt Grundstücke auf einen übrigen Haustyp zurückfallen", () => {
    addHouseType({ id: "ht-zweit", manufacturer: "Von Hand eingetragen", name: "10 × 8 m",
      builtArea: 80, length: 10, width: 8, ratio: 1.25, custom: true });
    const plot = plotById("plot-concave");
    expect(plot.houseTypeId).toBe("ht-elk");
    removeHouseType("ht-elk");
    expect(houseTypeById("ht-elk")).toBeNull();
    expect(plot.houseTypeId).toBe("ht-zweit");
  });

  it("setzt den Haustyp auf nichts, wenn der letzte entfernt wird", () => {
    removeHouseType("ht-elk");
    expect(state.data.houseTypes).toEqual([]);
    expect(plotById("plot-concave").houseTypeId).toBeNull();
  });

  it("löscht mit einem Ziel auch die Wege dorthin", () => {
    const plot = plotById("plot-concave");
    plot.routes["zl-arbeit"] = { auto: 12, rad: 20 };   // wie sie das Routing ablegt
    removeDestination("zl-arbeit");
    expect(plot.routes["zl-arbeit"]).toBeUndefined();
  });

  it("legt neue Ziele mit eigener Kennung an", () => {
    const a = addDestination();
    const b = addDestination();
    expect(a.id).not.toBe(b.id);
  });

  it("nimmt einen eigenen Haustyp in den Katalog", () => {
    const before = state.data.houseTypes.length;
    addHouseType({ id: "ht-eigen", manufacturer: "Eigene Maße", name: "12 × 9 m", builtArea: 108,
      length: 12, width: 9, ratio: 12 / 9, custom: true });
    expect(state.data.houseTypes).toHaveLength(before + 1);
  });

  it("leert den Speicher vollständig", () => {
    clear();
    expect(state.data.plots).toEqual([]);
    expect(state.data.houseTypes).toEqual([]);
    expect(state.data.version).toBe(SCHEMA_VERSION);
  });
});

describe("Darstellung", () => {
  it("stempelt die Wahl an das Wurzelelement und merkt sie sich", () => {
    applyTheme("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    applyTheme("light");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    applyTheme("system");
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
    expect(localStorage.getItem("where2build.theme")).toBe("system");
  });
});

/* The two parcels are the two answers. "concave" is 1685 m² and holds the ELK
 * house easily; "convex" is a 34,9 x 12,0 m strip whose envelope is 6 m deep
 * after the setbacks, so a house 8,47 m wide fits nowhere on it at any angle.
 * Both are recorded parcels, which is why the impossible case needs no invented
 * one. */
describe("Baukörper setzen", () => {
  it("setzt den Baukörper vollständig in das Bebauungsfenster", () => {
    const plot = realPlot("concave");
    const seat = seatHouse(plot);
    expect(seat).not.toBeNull();
    const { width, depth } = houseFootprint(plot);
    expect(cornersOutside({ ...seat, width, depth }, buildableArea(plot.polygon, plot.setbacks))).toBe(0);
  });

  it("richtet ihn an der Straßenfront aus", () => {
    const plot = realPlot("concave");
    expect(seatHouse(plot).rotation).toBeCloseTo(alignmentToEdge(plot.polygon, plot.streetEdge), 1);
  });

  it("setzt ihn auch auf dem großen Flurstück ins Fenster", () => {
    const plot = realPlot("large");
    const seat = seatHouse(plot);
    const { width, depth } = houseFootprint(plot);
    expect(cornersOutside({ ...seat, width, depth }, buildableArea(plot.polygon, plot.setbacks))).toBe(0);
  });

  it("antwortet mit null, wenn der Umriss auf den Streifen nirgends passt", () => {
    // 8,47 m Haustiefe in einem 6 m tiefen Fenster.
    expect(seatHouse(realPlot("convex"))).toBeNull();
  });

  it("lässt bei einem Flurstück ohne Bebauungsfenster die Lage unverändert", () => {
    const plot = realPlot("concave");
    plot.setbacks = plot.polygon.map(() => 20);
    const before = { ...plot.house };
    expect(autoSeatHouse(plot)).toBe(false);
    expect(plot.house).toEqual(before);
  });

  it("verschiebt den Baukörper und meldet den Erfolg", () => {
    const plot = realPlot("concave");
    plot.house = { cx: 0, cy: 0, rotation: 0 };
    expect(autoSeatHouse(plot)).toBe(true);
    expect(plot.house).not.toEqual({ cx: 0, cy: 0, rotation: 0 });
    expect(rectangleCorners({ ...plot.house, ...footprintOf(plot) })
      .every(c => pointInPolygon(c, buildableArea(plot.polygon, plot.setbacks)))).toBe(true);
  });

  /* The 1583 x 198 m strip a district address resolves to: millions of grid
     cells at a fixed step, and the answer still has to arrive. */
  it("bleibt auf dem 1583-Meter-Streifen in erträglicher Zeit", () => {
    const started = Date.now();
    expect(seatHouse(realPlot("many-corners"))).not.toBeNull();
    expect(Date.now() - started).toBeLessThan(4000);
  });

  const footprintOf = plot => {
    const f = houseFootprint(plot);
    return { width: f.width, depth: f.depth };
  };
});

describe("Haustyp eines Grundstücks", () => {
  it("nimmt für ein Grundstück ohne bekannten Haustyp dessen eigene Maße", () => {
    const raw = realState();
    raw.plots[0].houseTypeId = null;
    delete raw.plots[0].customSize;
    const plot = validate(raw).plots[0];
    expect(plot.houseTypeId).toBe(CUSTOM_SIZE);
    expect(plot.customSize).toEqual(DEFAULT_FOOTPRINT);
  });

  it("fängt auch einen Verweis auf einen gelöschten Haustyp auf", () => {
    const raw = realState();
    raw.plots[0].houseTypeId = "ht-gibt-es-nicht";
    expect(validate(raw).plots[0].houseTypeId).toBe(CUSTOM_SIZE);
  });

  it("lässt einen vorhandenen Haustyp in Ruhe", () => {
    expect(validate(realState()).plots[0].houseTypeId).toBe("ht-elk");
  });

  it("zeichnet ohne Haustyp denselben Umriss, den die Felder anbieten", () => {
    const plot = { ...realPlot("convex"), houseTypeId: CUSTOM_SIZE, customSize: undefined };
    const f = houseFootprint(plot);
    expect([f.width, f.depth]).toEqual([DEFAULT_FOOTPRINT.length, DEFAULT_FOOTPRINT.width]);
  });
});

describe("Straßenseite im gespeicherten Stand", () => {
  const withFront = front => {
    const data = realState();
    data.plots[0].streetFront = front;
    return validate(data).plots[0];
  };

  it("behält eine gefundene Straße und eine leere Antwort, verwirft Unsinn", () => {
    expect(withFront({ street: "Kirchstraße", length: 27.6 }).streetFront).toEqual({ street: "Kirchstraße", length: 27.6 });
    expect(withFront(null).streetFront).toBeNull();
    // Unset means "never asked", so the next load asks.
    expect("streetFront" in withFront({ street: 4 })).toBe(false);
    expect("streetFront" in withFront(undefined)).toBe(false);
  });
});
