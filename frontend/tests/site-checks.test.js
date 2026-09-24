/**
 * From the authorities' answer to the sentences on the page.
 *
 * The fixture is the backend's real answer for Flurstück 204 in Mölkau, the
 * plot the whole research was measured on — two overlapping noise bands, a
 * Landschaftsschutzgebiet a few hundred metres off, the BK50 wording, air
 * capacity LK_IV, and Leipzig-Mitte answering from 4,6 km because three nearer
 * stations carry no values.
 *
 * What these tests pin is the part that would be easy to get wrong quietly: a
 * failed service reading as a clean result, a class key reaching the screen
 * untranslated, or a check disappearing from the list because nobody can
 * answer it.
 */
import { describe, it, expect } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { nextTick } from "vue";
import answer from "./fixtures/standort-moelkau.json";
import { siteFindings, siteTally, noiseOnPlot } from "../src/lib/siteChecks.js";
import { GOOD, NOTE, OPEN } from "../src/lib/findings.js";
import CheckList from "../src/components/CheckList.vue";
import PlotView from "../src/views/PlotView.vue";
import { state } from "../src/lib/store.js";
import { realState, realPlot, mountWithRouter, testRouter } from "./helpers.js";

const find = (checks, id) => checks.find(c => c.id === id);
const withBlock = (name, block) => ({ ...answer, [name]: { ...answer[name], ...block } });

describe("siteFindings", () => {
  const checks = siteFindings(answer);

  it("names every check, including the ones nobody can answer", () => {
    expect(checks.map(c => c.id).sort()).toEqual([
      "altlasten", "baugrund", "hangneigung", "hochwasser", "laerm",
      "luftqualitaet", "mobilfunk", "radon", "schutzgebiet", "starkregen",
      "trinkwasserschutz"
    ]);
  });

  it("reports the span across the parcel, not a single value", () => {
    const noise = find(checks, "laerm");
    expect(noise.finding.value).toBe("50–59 dB(A)");
    expect(noise.finding.status).toBe(NOTE);
    expect(noise.finding.text).toContain("Straßenverkehr, tags 50–59 dB(A).");
    expect(noise.finding.text).toContain("Nachts 45–49 dB(A).");
    // The one thing a point query could never have said.
    expect(noise.finding.text).toContain("schneidet mehrere Bänder");
  });

  it("puts the noise band in everyday terms, with its source", () => {
    const reading = find(checks, "laerm").finding.interpretation;
    expect(reading.label).toBe("deutlich hörbar");
    expect(reading.notes.some(n => n.includes("53 dB(A)"))).toBe(true);
    expect(reading.source).toContain("UBA-Positionspapier");
  });

  it("names the nearest protected area by its own category and a bracket", () => {
    const protection = find(checks, "schutzgebiet").finding;
    expect(protection.status).toBe(GOOD);
    expect(protection.text).toContain("Nächstes Landschaftsschutzgebiet");
    expect(protection.text).toContain("Östliche Rietzschke - Stünz");
    expect(protection.value).toMatch(/–\d+ m entfernt$/);
  });

  it("counts more than one neighbour in the plural", () => {
    const many = siteFindings(withBlock("schutzgebiet", { weitere_im_umkreis: 3 }));
    expect(find(many, "schutzgebiet").finding.text).toContain("3 weitere liegen");
    const one = siteFindings(withBlock("schutzgebiet", { weitere_im_umkreis: 1 }));
    expect(find(one, "schutzgebiet").finding.text).toContain("Ein weiteres liegt");
  });

  it("turns the soil map's own wording into what it means for building", () => {
    const ground = find(checks, "baugrund").finding;
    expect(ground.text).toContain("Gemischter Boden");
    expect(ground.text).toContain("Luftkapazität hoch");
    expect(ground.text).toContain("Bohrungen im Umkreis von 300 m");
    // Never a bearing-capacity claim.
    expect(ground.text).toContain("ersetzt keine Baugrunduntersuchung");
  });

  it("keeps the class key out of the sentence and the wording behind a disclosure", () => {
    const ground = find(checks, "baugrund");
    expect(ground.finding.text).not.toContain("LK_IV");
    expect(ground.detail).toContain("Hortisol");
  });

  it("says when the drilling record did not answer, rather than showing a zero", () => {
    const silent = siteFindings(withBlock("baugrund", {
      bohrungen_gefragt: false, bohrungen_umkreis: 0, bohrungen_naher_umkreis: 0
    }));
    const ground = find(silent, "baugrund").finding;
    expect(ground.text).toContain("Gemischter Boden");
    expect(ground.text).toContain("nicht geantwortet");
    // Never "0 Bohrungen": that would be a statement about the neighbourhood.
    expect(ground.text).not.toMatch(/0 Bohrungen/);
  });

  it("says why the station that answered is not the nearest one", () => {
    const air = find(checks, "luftqualitaet").finding;
    expect(air.text).toContain("Leipzig-Mitte");
    expect(air.text).toMatch(/nähere Stationen? liefer[nt] keine Messwerte/);
  });

  it("marks a plot without noise values as something to look at", () => {
    const unmapped = siteFindings(withBlock("laerm", {
      tag: { strasse: [], strassenbahn: [], flughafen: [] },
      nacht: { strasse: [] },
      kartiert_umkreis: false,
      umkreis_m: 2000
    }));
    const finding = find(unmapped, "laerm").finding;
    expect(finding.status).toBe(NOTE);
    expect(finding.value).toBe("keine Lärmdaten");
    expect(finding.text).toContain("Im Umkreis von 2 km");

    const nearby = siteFindings(withBlock("laerm", {
      tag: { strasse: [] }, nacht: { strasse: [] }, kartiert_umkreis: true
    }));
    expect(find(nearby, "laerm").finding.status).toBe(NOTE);
    expect(find(nearby, "laerm").finding.value).toBe("keine Lärmdaten");
  });

  it("shows a failed service as open, never as a clean result", () => {
    const broken = siteFindings(withBlock("radon", { fehler: "Der Dienst antwortet nicht." }));
    const radon = find(broken, "radon").finding;
    expect(radon.status).toBe(OPEN);
    expect(radon.text).toBe("Der Dienst antwortet nicht.");
    expect(radon.text).not.toContain("nicht betroffen");
  });

  it("sorts what needs attention to the front and the unanswered to the back", () => {
    const statuses = checks.map(c => c.finding.status);
    expect(statuses.indexOf(NOTE)).toBeLessThan(statuses.indexOf(GOOD));
    expect(statuses.lastIndexOf(GOOD)).toBeLessThan(statuses.indexOf(OPEN));
  });

  it("counts instead of scoring", () => {
    const tally = siteTally(checks);
    expect(tally.counts.good + tally.counts.note + tally.counts.open).toBe(checks.length);
    expect(tally.counts.open).toBeGreaterThanOrEqual(3);
    expect(tally.text).toMatch(/ohne Befund/);
  });

  it("answers nothing for nothing", () => {
    expect(siteFindings(null)).toEqual([]);
    expect(siteTally([]).text).toBe("");
  });
});

describe("noiseOnPlot", () => {
  it("says yes where the plot sits in a band", () => {
    expect(noiseOnPlot(answer)).toBe(true);
  });

  it("says no where the plot sits in no band, mapped surroundings or not", () => {
    const nearby = withBlock("laerm", { tag: { strasse: [], strassenbahn: [], flughafen: [] }, kartiert_umkreis: true });
    expect(noiseOnPlot(nearby)).toBe(false);
    const unmapped = withBlock("laerm", { tag: { strasse: [], strassenbahn: [], flughafen: [] }, kartiert_umkreis: false });
    expect(noiseOnPlot(unmapped)).toBe(false);
  });

  it("does not know while there is no answer or the survey failed", () => {
    expect(noiseOnPlot(withBlock("laerm", { fehler: "Der Lärmdienst antwortet nicht." }))).toBe(null);
    expect(noiseOnPlot(null)).toBe(null);
  });
});

describe("Prüfliste", () => {
  const mountList = (plot, fetcher) => {
    globalThis.fetch = fetcher;
    return mount(CheckList, { props: { plot, auto: true } });
  };

  it("fragt mit dem Umring des Flurstücks, nicht mit einem Punkt", async () => {
    let body = null;
    const list = mountList(realPlot("moelkau"), (url, options) => {
      body = JSON.parse(options.body);
      return Promise.resolve({ ok: true, json: () => Promise.resolve(answer) });
    });
    await flushPromises();

    expect(body.ring.length).toBeGreaterThan(3);
    // A closed ring of [lon, lat] pairs in Saxony.
    expect(body.ring[0]).toEqual(body.ring[body.ring.length - 1]);
    expect(body.ring[0][0]).toBeGreaterThan(11);
    expect(body.ring[0][1]).toBeGreaterThan(50);
    list.unmount();
  });

  it("zeigt die Zähler statt eines Gesamtwerts", async () => {
    const list = mountList(realPlot("moelkau"), () =>
      Promise.resolve({ ok: true, json: () => Promise.resolve(answer) }));
    await flushPromises();
    await nextTick();

    const text = list.text();
    expect(text).toContain("ohne Befund");
    expect(text).toContain("zu beachten");
    expect(text).toContain("offen");
    expect(text).toMatch(/Kein Gesamtwert/);
    // No score anywhere, in any spelling.
    expect(text).not.toMatch(/\d+\s*\/\s*100/);
    list.unmount();
  });

  it("öffnet nur die Gruppe mit dem schwersten Befund, die übrigen auf Klick", async () => {
    const list = mountList(realPlot("moelkau"), () =>
      Promise.resolve({ ok: true, json: () => Promise.resolve(answer) }));
    await flushPromises();
    await nextTick();

    const groups = list.findAll(".checks__group");
    expect(groups.map(g => g.attributes("data-status"))).toEqual([NOTE, GOOD, OPEN]);
    const folded = () => list.findAll(".checks__group").map(g => g.classes("checks__group--folded"));
    expect(folded()).toEqual([false, true, true]);
    // Lärm und Baugrund sind die beiden, die etwas sagen.
    expect(groups[0].findAll(".check").map(c => c.find(".check__name").text())).toEqual(["Lärm", "Baugrund"]);

    const more = list.find(".checks__more button");
    expect(more.text()).toBe("Alle 11 Prüfungen zeigen");
    expect(more.attributes("aria-expanded")).toBe("false");
    expect(list.find(".checks__more-hint").text()).toMatch(/ohne Befund · 3 offen/);

    await more.trigger("click");
    expect(folded()).toEqual([false, false, false]);
    expect(more.text()).toBe("Nur „Zu beachten“ zeigen");
    expect(more.attributes("aria-expanded")).toBe("true");
    list.unmount();
  });

  it("zeigt ohne Befund zum Beachten die sauberen Prüfungen, nicht die offenen", async () => {
    const clean = {
      // A band below 55 dB(A): the one noise answer with nothing to note.
      ...withBlock("laerm", { tag: { strasse: ["Lden5054"], strassenbahn: [], flughafen: [] } }),
      baugrund: { ...answer.baugrund, fehler: "Die Bodenkarte antwortet nicht." }
    };
    const list = mountList(realPlot("moelkau"), () =>
      Promise.resolve({ ok: true, json: () => Promise.resolve(clean) }));
    await flushPromises();
    await nextTick();

    const open = list.findAll(".checks__group:not(.checks__group--folded)");
    expect(open.map(g => g.attributes("data-status"))).toEqual([GOOD]);
    expect(list.find(".checks__more button").text()).toBe("Alle 11 Prüfungen zeigen");
    list.unmount();
  });

  it("färbt jede Karte nach ihrem Befund und sagt ihn zusätzlich in Worten", async () => {
    const list = mountList(realPlot("moelkau"), () =>
      Promise.resolve({ ok: true, json: () => Promise.resolve(answer) }));
    await flushPromises();
    await nextTick();

    // Die Farbe hängt am Status der Karte; die Überschrift der Gruppe sagt
    // dasselbe für alle, die Amber nicht von Grün unterscheiden.
    list.findAll(".check").forEach(card =>
      expect([NOTE, GOOD, OPEN]).toContain(card.attributes("data-status")));
    expect(list.findAll(".checks__group-head").map(h => h.text().replace(/\s+/g, " ")))
      .toEqual(["! Zu beachten 2", "✓ Ohne Befund 6", "? Offen 3"]);
    list.unmount();
  });

  it("zeigt beim Warten die Zeilen, die kommen, statt nur eines Satzes", async () => {
    // Acht Dienste brauchen Sekunden; ein kleiner Hinweistext sieht in der
    // Zeit aus wie eine Seite, die fertig ist und nichts gefunden hat.
    const list = mountList(realPlot("moelkau"), () => new Promise(() => {}));
    await nextTick();

    expect(list.findAll(".skeleton__row").length).toBeGreaterThan(2);
    expect(list.text()).toContain("Das dauert einen Moment.");
    // Die Platzhalter sind für das Auge, nicht für den Screenreader.
    expect(list.find(".skeleton").attributes("aria-hidden")).toBe("true");
    expect(list.find(".checks__waiting").attributes("role")).toBe("status");
    list.unmount();
  });

  it("zeigt den deutschen Satz des Dienstes, wenn der Abruf scheitert", async () => {
    const list = mountList(realPlot("moelkau"), () =>
      Promise.resolve({
        ok: false, status: 502,
        json: () => Promise.resolve({ detail: "Der Umweltdatendienst ist nicht erreichbar." })
      }));
    await flushPromises();
    await nextTick();

    expect(list.text()).toContain("Der Umweltdatendienst ist nicht erreichbar.");
    list.unmount();
  });

  it("fragt ohne Koordinate gar nicht erst", async () => {
    const plot = realPlot("moelkau");
    delete plot.anchor;
    let asked = false;
    const list = mountList(plot, () => { asked = true; return Promise.resolve({ ok: true, json: () => ({}) }); });
    await nextTick();

    expect(asked).toBe(false);
    expect(list.text()).toContain("Ohne Flurstücksumriss");
    list.unmount();
  });
});

describe("Standort auf der Grundstücksseite", () => {
  it("steht als Abschnitt auf der Grundstücksseite, vor den Wegen", () => {
    state.data = realState();
    const plot = state.data.plots.find(p => p.anchor);
    globalThis.fetch = () => new Promise(() => {});

    const view = mountWithRouter(PlotView, { props: { id: plot.id } });
    const section = view.find("#standort");
    expect(section.exists()).toBe(true);
    expect(section.text()).toContain("Was der Standort mitbringt");
    expect(section.find(".checks").exists()).toBe(true);
    const headings = view.findAll("h2").map(h => h.text());
    expect(headings.indexOf("Was der Standort mitbringt")).toBeLessThan(headings.indexOf("Wege von hier"));
    view.unmount();
  });

  it("legt den Lärm über die Karte, bis die Prüfung sagt, dass dort nichts kartiert ist", async () => {
    state.data = realState();
    const plot = state.data.plots.find(p => p.anchor);
    const unmapped = withBlock("laerm", {
      tag: { strasse: [], strassenbahn: [], flughafen: [] },
      nacht: { strasse: [], strassenbahn: [], flughafen: [] },
      kartiert_umkreis: false
    });
    globalThis.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve(unmapped) });

    const view = mountWithRouter(PlotView, { props: { id: plot.id } });
    const noise = () => view.findAll("#standort button").find(b => b.text() === "Lärm");
    expect(noise().attributes("aria-pressed")).toBe("true");

    await flushPromises();
    await nextTick();
    expect(noise().attributes("aria-pressed")).toBe("false");
    expect(view.find("#standort .key").exists()).toBe(false);

    // Von Hand eingeschaltet bleibt er an, auch nach einer erneuten Prüfung.
    await noise().trigger("click");
    expect(noise().attributes("aria-pressed")).toBe("true");
    await view.findAll("#standort button").find(b => b.text() === "Neu prüfen").trigger("click");
    await flushPromises();
    expect(noise().attributes("aria-pressed")).toBe("true");
    view.unmount();
  });

  it("graut die Karte aus und sagt es, wenn am Grundstück kein Lärmwert liegt", async () => {
    state.data = realState();
    const plot = state.data.plots.find(p => p.anchor);
    // Kartiert im Umkreis, aber kein Band am Grundstück: genau der Fall, der
    // früher grün und ruhig aussah.
    const nearby = withBlock("laerm", {
      tag: { strasse: [], strassenbahn: [], flughafen: [] },
      nacht: { strasse: [], strassenbahn: [], flughafen: [] },
      kartiert_umkreis: true
    });
    let reply = nearby;
    globalThis.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve(reply) });

    const view = mountWithRouter(PlotView, { props: { id: plot.id } });
    // Vor der Antwort weiß niemand etwas: nichts ausgegraut, kein Hinweis.
    expect(view.find(".location__no-noise").exists()).toBe(false);

    await flushPromises();
    await nextTick();
    const frame = () => view.find(".location__frame");
    expect(frame().classes()).toContain("location__frame--no-noise");
    expect(view.find(".location__no-noise").text()).toContain("Keine Lärmwerte am Grundstück");

    // Die Ebene von Hand an: Farbe zurück, der Hinweis bleibt.
    await view.findAll("#standort button").find(b => b.text() === "Lärm").trigger("click");
    expect(frame().classes()).not.toContain("location__frame--no-noise");
    expect(view.find(".location__no-noise").exists()).toBe(true);
    view.unmount();

    reply = answer;
    const loud = mountWithRouter(PlotView, { props: { id: plot.id } });
    await flushPromises();
    await nextTick();
    expect(loud.find(".location__no-noise").exists()).toBe(false);
    expect(loud.find(".location__frame").classes()).not.toContain("location__frame--no-noise");
    loud.unmount();
  });

  it("sagt bei fehlender Koordinate, warum nichts gefragt werden kann", () => {
    const plot = realPlot("moelkau");
    delete plot.anchor;
    state.data = { ...realState(), plots: [plot] };
    let asked = false;
    globalThis.fetch = () => { asked = true; return new Promise(() => {}); };

    const view = mountWithRouter(PlotView, { props: { id: plot.id } });
    expect(view.find("#standort").text()).toContain("keine Koordinate hinterlegt");
    expect(view.find("#standort .checks").exists()).toBe(false);
    expect(asked).toBe(false);
    view.unmount();
  });

  it("führt die alte Adresse der Standortseite zu ihrem Abschnitt", async () => {
    const router = testRouter("/");
    await router.push("/grundstueck/plot-moelkau/standort");
    expect(router.currentRoute.value.name).toBe("plot");
    expect(router.currentRoute.value.params.id).toBe("plot-moelkau");
    expect(router.currentRoute.value.hash).toBe("#standort");
  });
});
