/** State, persistence and the JSON exchange. */
import { describe, it, expect, beforeEach, vi } from "vitest";
import {
  state, validate, load, save, resetToSample, exportJson, importJson,
  plotById, houseTypeById, houseFootprint, placement, centreOf,
  addPlot, removePlot, toggleSelection, addHouseType, removeHouseType,
  addDestination, removeDestination, applyTheme, EIGENMASS
} from "../src/lib/store.js";
import { sampleState } from "../src/lib/sample.js";

const quadrat = [{ x: 0, y: 0 }, { x: 20, y: 0 }, { x: 20, y: 30 }, { x: 0, y: 30 }];

beforeEach(() => {
  localStorage.clear();
  state.daten = sampleState();
});

describe("Prüfung beim Einlesen", () => {
  it("nimmt einen vollständigen Stand an", () => {
    const d = validate(sampleState());
    expect(d.grundstuecke).toHaveLength(4);
    expect(d.haustypen.length).toBeGreaterThan(0);
    expect(d.ziele.length).toBeGreaterThan(0);
  });

  it("weist zurück, was keine Grundstücke enthält", () => {
    expect(() => validate(null)).toThrow(/Objekt/);
    expect(() => validate({})).toThrow(/grundstuecke/);
    expect(() => validate({ grundstuecke: "nein" })).toThrow(/grundstuecke/);
  });

  it("weist Grundstücke ohne brauchbare Geometrie zurück", () => {
    expect(() => validate({ grundstuecke: [{ name: "ohne Polygon" }] })).toThrow(/Geometrie/);
    expect(() => validate({ grundstuecke: [{ polygon: [{ x: 1 }] }] })).toThrow(/Geometrie/);
  });

  it("ergänzt fehlende Felder mit vernünftigen Werten", () => {
    const d = validate({ grundstuecke: [{ polygon: quadrat }] });
    const p = d.grundstuecke[0];
    expect(p.id).toBeTruthy();
    expect(p.tiefen).toEqual([3, 3, 3, 3]);
    expect(p.verhaeltnis).toBe(1.35);
    expect(p.wandhoehe).toBe(6.4);
    expect(p.haus.cx).toBeCloseTo(10, 6);
    expect(p.haus.cy).toBeCloseTo(15, 6);
    expect(p.wege).toEqual({});
  });

  it("begrenzt unsinnige Werte statt sie zu übernehmen", () => {
    const d = validate({ grundstuecke: [{
      polygon: quadrat, tiefen: [99, -5, 3, 3], verhaeltnis: 9, wandhoehe: 99,
      eigenmass: { laenge: 500, breite: 0.2 }
    }] });
    const p = d.grundstuecke[0];
    expect(p.tiefen).toEqual([20, 0, 3, 3]);
    expect(p.verhaeltnis).toBe(2.2);
    expect(p.wandhoehe).toBe(12);
    expect(p.eigenmass).toEqual({ laenge: 30, breite: 4 });
  });

  it("wirft Haustypen außerhalb der Plausibilitätsgrenzen weg", () => {
    const d = validate({
      grundstuecke: [{ polygon: quadrat }],
      haustypen: [{ id: "a", bebauteFlaeche: 25 }, { id: "b", bebauteFlaeche: 500 }, { id: "c", bebauteFlaeche: 96.88 }]
    });
    expect(d.haustypen.map(h => h.id)).toEqual(["c"]);
  });

  it("behält nur Auswahl-Kennungen, die es auch gibt", () => {
    const d = validate({ grundstuecke: [{ polygon: quadrat, id: "gs-1" }], auswahl: ["gs-1", "gibt-es-nicht"] });
    expect(d.auswahl).toEqual(["gs-1"]);
  });
});

describe("Ausgeben und Einlesen", () => {
  it("übersteht eine Runde ohne Verlust", () => {
    const vorher = exportJson();
    importJson(vorher);
    expect(JSON.parse(exportJson()).grundstuecke).toHaveLength(4);
  });

  it("meldet unbrauchbares JSON auf Deutsch und lässt den Stand unberührt", () => {
    for (const muell of ["kein json", "{}", '{"grundstuecke":"nein"}', ""]) {
      expect(() => importJson(muell)).toThrow();
    }
    expect(state.daten.grundstuecke).toHaveLength(4);
  });

  it("ersetzt den Stand bei gültiger Eingabe", () => {
    const klein = { ...sampleState(), grundstuecke: sampleState().grundstuecke.slice(0, 2) };
    importJson(JSON.stringify(klein));
    expect(state.daten.grundstuecke).toHaveLength(2);
  });
});

describe("Speicher im Browser", () => {
  it("legt ab und liest zurück", () => {
    state.daten.grundstuecke[0].wandhoehe = 7.7;
    save();
    state.daten = sampleState();
    load();
    expect(state.daten.grundstuecke[0].wandhoehe).toBe(7.7);
  });

  it("überlebt einen kaputten Eintrag", () => {
    localStorage.setItem("where2build.v1", "{kaputt");
    load();
    expect(state.daten.grundstuecke).toHaveLength(4);
  });

  it("läuft weiter, wenn der Speicher verweigert wird", () => {
    const original = Storage.prototype.setItem;
    Storage.prototype.setItem = () => { throw new Error("QuotaExceeded"); };
    expect(() => save()).not.toThrow();
    expect(() => applyTheme("dark")).not.toThrow();
    Storage.prototype.setItem = original;
  });

  it("stellt die Beispieldaten wieder her", () => {
    removePlot(state.daten.grundstuecke[0].id);
    expect(state.daten.grundstuecke).toHaveLength(3);
    resetToSample();
    expect(state.daten.grundstuecke).toHaveLength(4);
  });
});

describe("Baukörper aus dem Haustyp", () => {
  it("nimmt die Außenmaße, wenn das Datenblatt sie liefert", () => {
    const plot = plotById("gs-zuckelhausen");
    plot.haustypId = "ht-stadt134";
    const k = houseFootprint(plot);
    expect(k).toMatchObject({ width: 10.4, depth: 7.5, estimated: false });
  });

  it("schätzt aus der bebauten Fläche, wenn nicht", () => {
    const plot = plotById("gs-liebertwolkwitz");
    const k = houseFootprint(plot);          // ELK All in One 159, ohne Außenmaße
    expect(k.estimated).toBe(true);
    expect(k.width * k.depth).toBeCloseTo(96.88, 6);
    expect(k.width / k.depth).toBeCloseTo(1.35, 6);
  });

  it("nimmt eigene Maße, wenn welche eingetragen sind", () => {
    const plot = plotById("gs-liebertwolkwitz");
    plot.haustypId = EIGENMASS;
    plot.eigenmass = { laenge: 13, breite: 9 };
    expect(houseFootprint(plot)).toMatchObject({ width: 13, depth: 9, eigen: true });
  });

  it("setzt die Platzierung aus Maßen und Lage zusammen", () => {
    const p = placement(plotById("gs-liebertwolkwitz"));
    expect(p).toMatchObject({ cx: 10.8, cy: 15, rotation: -4 });
    expect(Number.isFinite(p.width) && Number.isFinite(p.depth)).toBe(true);
  });

  it("centreOf liefert cx/cy, nicht x/y — sonst wird die Lage NaN", () => {
    expect(centreOf(quadrat)).toEqual({ cx: 10, cy: 15, rotation: 0 });
  });
});

describe("Grundstücke, Haustypen und Ziele verwalten", () => {
  it("nimmt ein Grundstück auf und wählt es gleich aus", () => {
    const neu = { ...validate({ grundstuecke: [{ polygon: quadrat, id: "gs-neu" }] }).grundstuecke[0] };
    addPlot(neu);
    expect(state.daten.grundstuecke).toHaveLength(5);
    expect(state.daten.auswahl).toContain("gs-neu");
  });

  it("entfernt ein Grundstück samt Auswahl", () => {
    removePlot("gs-holzhausen");
    expect(plotById("gs-holzhausen")).toBeNull();
    expect(state.daten.auswahl).not.toContain("gs-holzhausen");
  });

  it("nimmt Kandidaten in die Auswahl und wieder heraus", () => {
    toggleSelection("gs-holzhausen", false);
    expect(state.daten.auswahl).not.toContain("gs-holzhausen");
    toggleSelection("gs-holzhausen", true);
    expect(state.daten.auswahl).toContain("gs-holzhausen");
    toggleSelection("gs-holzhausen", true);   // doppelt bleibt einfach
    expect(state.daten.auswahl.filter(id => id === "gs-holzhausen")).toHaveLength(1);
  });

  it("lässt Grundstücke auf einen übrigen Haustyp zurückfallen", () => {
    const plot = plotById("gs-liebertwolkwitz");
    expect(plot.haustypId).toBe("ht-elk159");
    removeHouseType("ht-elk159");
    expect(houseTypeById("ht-elk159")).toBeNull();
    expect(plot.haustypId).toBe(state.daten.haustypen[0].id);
  });

  it("löscht mit einem Ziel auch die Wege dorthin", () => {
    const plot = plotById("gs-liebertwolkwitz");
    expect(plot.wege["zl-arbeit"]).toBeTruthy();
    removeDestination("zl-arbeit");
    expect(plot.wege["zl-arbeit"]).toBeUndefined();
  });

  it("legt neue Ziele mit eigener Kennung an", () => {
    const a = addDestination();
    const b = addDestination();
    expect(a.id).not.toBe(b.id);
  });

  it("nimmt einen eigenen Haustyp in den Katalog", () => {
    const vorher = state.daten.haustypen.length;
    addHouseType({ id: "ht-eigen", hersteller: "Eigene Maße", name: "12 × 9 m", bebauteFlaeche: 108,
      laenge: 12, breite: 9, verhaeltnis: 12 / 9, eigen: true });
    expect(state.daten.haustypen).toHaveLength(vorher + 1);
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
