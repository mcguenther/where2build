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
import { siteFindings, siteTally } from "../src/lib/siteChecks.js";
import { GOOD, NOTE, OPEN } from "../src/lib/findings.js";
import CheckList from "../src/components/CheckList.vue";
import LocationView from "../src/views/LocationView.vue";
import { state } from "../src/lib/store.js";
import { realState, realPlot, mountWithRouter } from "./helpers.js";

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

  it("distinguishes an unmapped plot from a quiet one", () => {
    const unmapped = siteFindings(withBlock("laerm", {
      tag: { strasse: [], strassenbahn: [], flughafen: [] },
      nacht: { strasse: [] },
      kartiert_umkreis: false
    }));
    const finding = find(unmapped, "laerm").finding;
    expect(finding.status).toBe(OPEN);
    expect(finding.value).toBe("nicht kartiert");
    expect(finding.text).toContain("keine Aussage über die Ruhe");

    const quiet = siteFindings(withBlock("laerm", {
      tag: { strasse: [] }, nacht: { strasse: [] }, kartiert_umkreis: true
    }));
    expect(find(quiet, "laerm").finding.status).toBe(GOOD);
    expect(find(quiet, "laerm").finding.value).toBe("unter 45 dB(A)");
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

describe("Standortansicht", () => {
  it("nennt ein Grundstück, das dieser Browser nicht kennt, beim Namen", () => {
    state.data = realState();
    const view = mountWithRouter(LocationView, {
      path: "/grundstueck/gibtsnicht/standort",
      props: { id: "gibtsnicht" }
    });
    expect(view.text()).toContain("nicht in diesem Browser");
  });

  it("sagt bei fehlender Koordinate, warum nichts gefragt werden kann", () => {
    const plot = realPlot("moelkau");
    delete plot.anchor;
    state.data = { ...realState(), plots: [plot] };
    globalThis.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve(answer) });

    const view = mountWithRouter(LocationView, {
      path: `/grundstueck/${plot.id}/standort`,
      props: { id: plot.id }
    });
    expect(view.text()).toContain("keine Koordinate hinterlegt");
  });
});
