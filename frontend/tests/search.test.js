/**
 * The parcel search in the browser: the stream, the camera, and the interface
 * that has to make a run checkable.
 *
 * The stream fixture is a real run — the reference listing put through the live
 * cadastre on 05.09.2026 — so what is asserted here is what the backend
 * actually sends, not a shape invented to match the code.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
// The recorded run, verbatim: `?raw` keeps it the text a reader would see.
import STREAM from "./fixtures/suche-grossbothen.ndjson?raw";

import {
  MIN_HALF_WIDTH_M, StepQueue, boundsOf, contains, contextOpacity,
  evidenceOpacity, frameFor, halfExtentsM, padBounds, unionBounds
} from "../src/lib/evidence.js";
import { queryFromFields, runSearch, splitLines, verdictSentence } from "../src/lib/search.js";
import { parseGermanNumber } from "../src/lib/format.js";
import ParcelSearch from "../src/components/ParcelSearch.vue";

const EVENTS = STREAM.split("\n").filter(Boolean).map(line => JSON.parse(line));
const RESULT = EVENTS[EVENTS.length - 1];

/** A square of `size` degrees about a point, as a GeoJSON polygon. */
const square = (lon, lat, size) => ({
  type: "Polygon",
  coordinates: [[
    [lon - size, lat - size], [lon + size, lat - size],
    [lon + size, lat + size], [lon - size, lat + size], [lon - size, lat - size]
  ]]
});

/** A `fetch` that answers the search endpoint with the recorded stream. */
function stubFetch(body = STREAM, { ok = true, status = 200 } = {}) {
  return vi.fn(async () => ({
    ok,
    status,
    headers: new Map(),
    json: async () => JSON.parse(body),
    text: async () => body,
    body: {
      getReader() {
        // Two chunks, split mid-line: the reader has to stitch them, and a
        // real chunked response never breaks on a line boundary either.
        const cut = Math.floor(body.length / 2);
        const parts = [body.slice(0, cut), body.slice(cut)].map(s => new TextEncoder().encode(s));
        let i = 0;
        return { read: async () => (i < parts.length ? { value: parts[i++], done: false } : { done: true }) };
      }
    }
  }));
}

describe("Der Strom", () => {
  it("setzt eine Zeile wieder zusammen, die über zwei Blöcke verteilt ankam", async () => {
    global.fetch = stubFetch();
    const seen = [];

    const result = await runSearch({ text: "x" }, event => seen.push(event));

    expect(seen).toHaveLength(EVENTS.length);
    expect(result.status).toBe("bestaetigt");
  });

  it("behält den angefangenen Rest, bis er vollständig ist", () => {
    const { lines, rest } = splitLines('{"a":1}\n{"b":2}\n{"c":');
    expect(lines).toHaveLength(2);
    expect(rest).toBe('{"c":');
  });

  it("gibt die deutsche Fehlermeldung des Dienstes weiter", async () => {
    global.fetch = stubFetch('{"detail":"Das Kataster antwortet nicht."}', { ok: false, status: 502 });

    await expect(runSearch({ text: "x" }, () => {})).rejects.toThrow("Das Kataster antwortet nicht.");
  });

  it("meldet einen Abbruch mitten im Strom, statt ihn zu verschlucken", async () => {
    // A stream that simply stops leaves a half-finished search on screen with
    // nothing saying so. The last line is the answer; without one there is none.
    const half = EVENTS.slice(0, 4).map(e => JSON.stringify(e)).join("\n") + "\n";
    global.fetch = stubFetch(half);

    await expect(runSearch({ text: "x" }, () => {})).rejects.toThrow(/kein Ergebnis/);
  });

  it("trägt einen Dienstfehler aus einer Zeile nach außen", async () => {
    const body = '{"art":"fehler","text":"Der Katasterdienst hat abgelehnt."}\n';
    global.fetch = stubFetch(body);

    await expect(runSearch({ text: "x" }, () => {})).rejects.toThrow("Der Katasterdienst hat abgelehnt.");
  });
});

describe("Der Kartenausschnitt", () => {
  it("steht nie enger als der eigene Zweifel", () => {
    // Two candidates 400 m apart. A frame around the newest clue alone would
    // hide the other one -- the mistake the first draft made.
    const candidates = [square(12.74, 51.19, 0.001), square(12.75, 51.195, 0.001)];

    const frame = frameFor({ candidates, evidence: square(12.74, 51.19, 0.0005) });

    expect(contains(frame, boundsOf(candidates))).toBe(true);
  });

  it("zeigt auch ein bestätigtes Flurstück nie ohne seine Nachbarn", () => {
    // A 30 m parcel: without a floor the camera would sit inside its own fence.
    const tiny = square(12.74, 51.19, 0.00015);

    const half = halfExtentsM(padBounds(boundsOf(tiny)));

    expect(half.x).toBeGreaterThanOrEqual(MIN_HALF_WIDTH_M);
    expect(half.y).toBeGreaterThanOrEqual(MIN_HALF_WIDTH_M);
  });

  it("geht nur enger, wenn wirklich ein Kandidat ausgeschieden ist", () => {
    const wide = padBounds(boundsOf([square(12.70, 51.18, 0.01)]));
    // Inside the wide frame: the question is whether the camera closes in on
    // it, not whether it can reach it.
    const narrow = [square(12.70, 51.18, 0.0005)];

    const held = frameFor({ candidates: narrow, previous: wide, tightened: false });
    const closed = frameFor({ candidates: narrow, previous: wide, tightened: true });

    // Nothing was ruled out, so the frame stays where it is: a camera that
    // creeps in and out on every arriving clue reads as a twitch.
    expect(held).toBe(wide);
    expect(halfExtentsM(closed).x).toBeLessThan(halfExtentsM(wide).x);
  });

  it("weitet sich immer, wenn etwas Neues nicht hineinpasst", () => {
    const previous = padBounds(boundsOf([square(12.74, 51.19, 0.0005)]));

    const frame = frameFor({
      candidates: [square(12.74, 51.19, 0.0005)],
      evidence: square(12.90, 51.30, 0.0005),
      previous,
      tightened: false
    });

    expect(contains(frame, boundsOf(square(12.90, 51.30, 0.0005)))).toBe(true);
  });

  it("blendet eine Ebene aus, die viel größer ist als der Ausschnitt", () => {
    // A district wash seen from inside it has stopped saying anything and only
    // tints -- so it fades out rather than staying at full strength.
    const district = boundsOf(square(12.74, 51.19, 0.02));
    const wide = padBounds(district);
    const close = padBounds(boundsOf(square(12.74, 51.19, 0.0006)));

    expect(contextOpacity(district, wide, { full: 0.9 })).toBeGreaterThan(0.5);
    expect(contextOpacity(district, close, { full: 0.9 })).toBe(0);
  });

  it("zeichnet ein unsicheres Indiz blasser als ein sicheres", () => {
    expect(evidenceOpacity(0.95)).toBeGreaterThan(evidenceOpacity(0.15));
  });

  it("vereinigt leere Kästen, ohne unendlich zu werden", () => {
    const box = boundsOf(square(12.74, 51.19, 0.001));
    expect(unionBounds(boundsOf(null), box)).toEqual(box);
  });
});

describe("Die Warteschlange", () => {
  let queue;
  afterEach(() => queue?.stop());

  it("ruft die Zeitgeber so auf, wie ein Browser sie annimmt", () => {
    // `this.timer = setTimeout` und dann `this.timer(…)` ruft die native
    // Funktion mit der Warteschlange als Empfänger auf — der Browser wirft
    // „Illegal invocation“, und der Lauf bleibt nach der ersten Zeile stehen.
    queue = new StepQueue({ dwell: 50 });
    queue.onStep = () => {};

    expect(() => queue.push(1)).not.toThrow();
    expect(String(queue.timer)).not.toBe(String(setTimeout));
  });

  it("lässt jedes Indiz stehen, statt sie übereinander zu werfen", () => {
    vi.useFakeTimers();
    queue = new StepQueue({ dwell: 2000 });
    const shown = [];
    queue.onStep = item => shown.push(item);

    [1, 2, 3].forEach(n => queue.push(n));

    expect(shown).toEqual([1]);
    vi.advanceTimersByTime(2000);
    expect(shown).toEqual([1, 2]);
    vi.advanceTimersByTime(2000);
    expect(shown).toEqual([1, 2, 3]);
    vi.useRealTimers();
  });

  it("überspringt die Wartezeit, wenn jemand darauf klickt", () => {
    vi.useFakeTimers();
    queue = new StepQueue({ dwell: 2000 });
    const shown = [];
    queue.onStep = item => shown.push(item);
    [1, 2, 3].forEach(n => queue.push(n));

    queue.flush();

    // Nobody waits for an animation.
    expect(shown).toEqual([1, 2, 3]);
    expect(queue.waiting).toBe(0);
    vi.useRealTimers();
  });

  it("wartet gar nicht, wenn der Browser um weniger Bewegung gebeten hat", () => {
    queue = new StepQueue({ reduced: true });
    const shown = [];
    queue.onStep = item => shown.push(item);

    [1, 2].forEach(n => queue.push(n));

    expect(shown).toEqual([1, 2]);
  });
});

describe("Der Ergebnissatz", () => {
  it("nennt beim mehrdeutigen Ausgang, was trotzdem feststeht", () => {
    const sentence = verdictSentence("mehrdeutig", 5, {
      art: "strasse",
      text: "An der Wiesenstraße in der Gemarkung Großbothen — welches der 5 Flurstücke, ist offen."
    });

    expect(sentence).toContain("5 mögliche Flurstücke");
    expect(sentence).toContain("Wiesenstraße");
  });

  it("sagt beim erfolglosen Ausgang nicht mehr, als es weiß", () => {
    const sentence = verdictSentence("erfolglos", 0, { art: "offen", text: "x" });

    expect(sentence).toContain("Kein Flurstück gefunden");
    expect(sentence).not.toContain("x");
  });
});

describe("Gelesene Werte als Suchanfrage", () => {
  /** The bug this covers made every Kleinanzeigen listing answer 422: the
   *  coordinate 51.189265 had its dot stripped as a thousands separator and
   *  went out as 51189265, which the endpoint rejects at `le=90`. */
  it("liest den Punkt einer Koordinate als Komma, nicht als Tausendertrennung", () => {
    expect(parseGermanNumber("51.189265")).toBe(51.189265);
    expect(parseGermanNumber("12.4076")).toBe(12.4076);
    expect(parseGermanNumber(51.189265)).toBe(51.189265);
  });

  it("liest den Punkt einer Fläche als Tausendertrennung", () => {
    expect(parseGermanNumber("1.025")).toBe(1025);
    expect(parseGermanNumber("1.025 m²")).toBe(1025);
    expect(parseGermanNumber("80.000 €")).toBe(80000);
    // Ein Komma entscheidet die Frage von selbst.
    expect(parseGermanNumber("1.025,50")).toBe(1025.5);
  });

  it("gibt null zurück, wo keine Zahl steht", () => {
    expect(parseGermanNumber("")).toBeNull();
    expect(parseGermanNumber(null)).toBeNull();
    expect(parseGermanNumber("auf Anfrage")).toBeNull();
  });

  it("schickt die Koordinate unverändert in die Anfrage", () => {
    const fields = [
      { key: "adresse", value: "Ortsteil Lobstädt bei Neukieritzsch" },
      { key: "lat", value: "51.189265" },
      { key: "lon", value: "12.4076" },
      { key: "grundstuecksflaeche_m2", value: "1.025" }
    ];

    const query = queryFromFields(fields);

    expect(query.lat).toBe(51.189265);
    expect(query.lon).toBe(12.4076);
    expect(query.flaeche_m2).toBe(1025);
    // Die Schreibweise bleibt erhalten: aus ihr leitet die Suche die Toleranz ab.
    expect(query.flaeche_text).toBe("1.025");
  });
});

describe("Die Suchansicht", () => {
  beforeEach(() => { global.fetch = stubFetch(); });

  /** Paced off: these assert the finished state, not the pacing, which has its
   *  own tests above. The map is not mounted in jsdom -- see below. */
  const openSearch = async () => {
    const wrapper = mount(ParcelSearch, {
      props: { query: { text: "x" }, paced: false },
      global: { stubs: { EvidenceMap: true } }
    });
    await flushPromises();
    await flushPromises();
    return wrapper;
  };

  it("zeigt das Urteil und was es gekostet hat", async () => {
    const wrapper = await openSearch();

    expect(wrapper.text()).toContain("Bestätigt");
    expect(wrapper.text()).toContain(`${RESULT.anfragen} Abfragen`);
  });

  it("führt zu jedem Indiz seinen Beleg mit", async () => {
    const wrapper = await openSearch();

    // A contradiction nobody can look up is one nobody can resolve.
    const withEvidence = EVENTS.filter(e => e.art === "indiz" && e.indiz.beleg);
    expect(withEvidence.length).toBeGreaterThan(3);
    withEvidence.forEach(event => {
      expect(wrapper.text()).toContain(event.indiz.text);
    });
  });

  it("nennt den Ort, der als entfernt beschrieben wird, und sucht nicht dort", async () => {
    const wrapper = await openSearch();

    // Grimma is named as often as Großbothen -- because the plot is 6 km away
    // from it. It stays in the protocol as evidence *against* itself.
    expect(wrapper.text()).toContain("spricht gegen diesen Ort");
  });

  it("stellt einen Widerspruch zur Wahl, statt ihn still zu entscheiden", async () => {
    const wrapper = await openSearch();
    const conflict = EVENTS.find(e => e.art === "konflikt")?.konflikt;

    expect(conflict).toBeTruthy();
    expect(wrapper.text()).toContain(conflict.frage);
    expect(wrapper.findAll(".konflikt__option").length).toBe(conflict.optionen.length);
  });

  it("führt den Verlauf in der Reihenfolge, in der er passiert ist", async () => {
    const wrapper = await openSearch();

    // Die Liste war nach Sicherheit sortiert, und die Schritte standen
    // getrennt darunter — hinterher war nicht mehr zu sehen, was zuerst kam.
    const rows = wrapper.findAll(".verlauf__schritt");
    const numbers = wrapper.findAll(".verlauf__nr").map(n => Number(n.text()));
    expect(numbers).toEqual(numbers.map((_, i) => i + 1));

    const text = rows.map(row => row.text());
    const firstPhase = EVENTS.find(e => e.art === "phase").text;
    const firstIndiz = EVENTS.find(e => e.art === "indiz").indiz.text;
    expect(text[0]).toContain(firstPhase);
    expect(text[1]).toContain(firstIndiz);

    // Und das Ergebnis steht am Ende, nicht irgendwo dazwischen.
    expect(text.at(-1)).toContain("Ergebnis");
  });

  it("führt vom letzten Eintrag zurück zum gefundenen Flurstück", async () => {
    const wrapper = await openSearch();
    const map = wrapper.findComponent({ name: "EvidenceMap" });
    const focusOn = vi.fn();
    map.vm.focusOn = focusOn;

    await wrapper.findAll(".verlauf__zeile").at(-1).trigger("click");

    expect(focusOn).toHaveBeenCalledTimes(1);
    // Die Hülle des bestätigten Flurstücks, nicht die Gemarkung darum.
    expect(focusOn.mock.calls[0][0]).toEqual(RESULT.huelle.geometry);
  });

  it("hat einen Weg zurück zum Ergebnis, auch ohne den Verlauf", async () => {
    const wrapper = await openSearch();
    const map = wrapper.findComponent({ name: "EvidenceMap" });
    const focusOn = vi.fn();
    map.vm.focusOn = focusOn;

    const back = wrapper.findAll("button").find(b => b.text() === "Zum Ergebnis");
    expect(back.attributes("disabled")).toBeUndefined();
    await back.trigger("click");

    expect(focusOn).toHaveBeenCalledTimes(1);
  });

  it("zeigt auf Wunsch wieder alles, was der Lauf gefunden hat", async () => {
    const wrapper = await openSearch();
    const map = wrapper.findComponent({ name: "EvidenceMap" });
    const focusOn = vi.fn();
    map.vm.focusOn = focusOn;

    await wrapper.findAll("button").find(b => b.text() === "Alles zeigen").trigger("click");

    const shown = focusOn.mock.calls[0][0];
    expect(Array.isArray(shown)).toBe(true);
    // Das Flurstück und die Gemarkung darum sind beide dabei.
    expect(shown.length).toBeGreaterThan(1);
  });

  it("markiert auf der Karte, worauf ein Eintrag zeigt", async () => {
    const wrapper = await openSearch();
    const map = wrapper.findComponent({ name: "EvidenceMap" });
    map.vm.focusOn = vi.fn();

    // Vorher zeigt nichts auf etwas Bestimmtes.
    expect(map.props("highlighted")).toBeNull();

    await wrapper.findAll(".verlauf__zeile").at(-1).trigger("click");

    // Ein Sprung, der nur die Kamera bewegt, kommt irgendwo an, ohne zu sagen,
    // welches der Dinge dort der Grund war.
    expect(map.props("highlighted")).toEqual(RESULT.huelle.geometry);
    expect(wrapper.find(".verlauf--gezeigt").exists()).toBe(true);
  });

  it("hebt die Markierung auf, wenn wieder alles gezeigt wird", async () => {
    const wrapper = await openSearch();
    const map = wrapper.findComponent({ name: "EvidenceMap" });
    map.vm.focusOn = vi.fn();

    await wrapper.findAll(".verlauf__zeile").at(-1).trigger("click");
    expect(map.props("highlighted")).toBeTruthy();

    await wrapper.findAll("button").find(b => b.text() === "Alles zeigen").trigger("click");

    expect(map.props("highlighted")).toBeNull();
    expect(wrapper.find(".verlauf--gezeigt").exists()).toBe(false);
  });

  it("sucht erneut, wenn ein Indiz abgewählt wird", async () => {
    const wrapper = await openSearch();
    const calls = global.fetch.mock.calls.length;

    await wrapper.findAll(".verlauf__schalter")[0].trigger("click");
    await flushPromises();

    expect(global.fetch.mock.calls.length).toBe(calls + 1);
    const sent = JSON.parse(global.fetch.mock.calls.at(-1)[1].body);
    expect(sent.verworfen).toHaveLength(1);
  });

  it("schickt die Entscheidung mit, wenn jemand einen Widerspruch auflöst", async () => {
    const wrapper = await openSearch();

    await wrapper.findAll(".konflikt__option")[1].trigger("click");
    await flushPromises();

    const sent = JSON.parse(global.fetch.mock.calls.at(-1)[1].body);
    expect(sent.entscheidungen.gemarkung).toBeTruthy();
  });

  it("wählt den einzigen Kandidaten selbst und gibt ihn beim Übernehmen weiter", async () => {
    const wrapper = await openSearch();

    const confirm = wrapper.findAll("button").find(b => /Übernehmen/.test(b.text()));
    await confirm.trigger("click");

    const [candidate] = wrapper.emitted("confirm")[0];
    expect(candidate.properties.flurstuecksnummer).toBe("790/11");
    expect(candidate.properties.gemarkung).toBe("Großbothen");
  });

  it("zeigt eine Fehlermeldung, statt still zu bleiben", async () => {
    global.fetch = stubFetch('{"detail":"Das Kataster antwortet nicht."}', { ok: false, status: 502 });

    const wrapper = await openSearch();

    expect(wrapper.text()).toContain("Das Kataster antwortet nicht.");
  });
});
