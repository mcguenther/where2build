/**
 * Choosing the parcel, rather than letting a coordinate choose it.
 *
 * An address coordinate sits on the building the register recorded, which is
 * not always inside the parcel being sold: the geocoder's point for Lessingweg
 * 44 in Mölkau lands inside number 46, 0,3 m from the boundary of the parcel
 * whose Lagebezeichnung is the address searched for. Two answers to that, both
 * tested here — the cadastre's own Lagebezeichnung settles it where it can, and
 * the neighbours are on the map either way.
 */
import { describe, it, expect, beforeEach } from "vitest";
import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import SitePlan from "../src/components/SitePlan.vue";
import { parcelForAddress } from "../src/lib/plots.js";
import { toWgs84 } from "../src/lib/projection.js";
import { state } from "../src/lib/store.js";
import { realState, realPlot } from "./helpers.js";

/** Two parcels as `/api/parcels/nearby` answers, in the register's spelling. */
const parcel = (zaehler, lage, ring) => ({
  type: "Feature",
  properties: {
    kennzeichen: `1455920000${zaehler}____`, zaehler: String(zaehler), nenner: null,
    gemarkung: "Mölkau", lagebezeichnung: lage, flaeche_amtlich_m2: 650
  },
  geometry: { type: "Polygon", coordinates: [ring] }
});

/** A small square around a centre, closed, in WGS84. */
const square = (lon, lat, size = 0.0004) => [
  [lon - size, lat - size], [lon + size, lat - size],
  [lon + size, lat + size], [lon - size, lat + size], [lon - size, lat - size]
];

const NEIGHBOURS = [
  parcel(205, "Lessingweg 46", square(12.4418, 51.3366)),
  parcel(204, "Lessingweg 44", square(12.4419, 51.3365)),
  parcel(203, "Lessingweg; Lessingweg 42", square(12.4420, 51.3364))
];

beforeEach(() => {
  localStorage.clear();
  state.data = realState();
  state.plan = { backdrop: "none", northUp: true, showDimensions: true, showSetbacks: true, measuring: false };
});

describe("parcelForAddress", () => {
  it("nennt das Flurstück, dessen Lagebezeichnung die Adresse ist", () => {
    expect(parcelForAddress(NEIGHBOURS, "Lessingweg 44").properties.zaehler).toBe("204");
  });

  it("liest eine mehrteilige Lagebezeichnung als Liste", () => {
    expect(parcelForAddress(NEIGHBOURS, "Lessingweg 42").properties.zaehler).toBe("203");
  });

  it("hält eine Hausnummer für ganz, nicht für einen Anfang", () => {
    // "Lessingweg 4" darf nicht für "Lessingweg 44" oder "46" antworten.
    expect(parcelForAddress(NEIGHBOURS, "Lessingweg 4")).toBeNull();
  });

  it("rät nicht, wenn zwei Flurstücke dieselbe Adresse tragen", () => {
    const doppelt = [parcel(1, "Weg 1", square(12.44, 51.33)), parcel(2, "Weg 1", square(12.45, 51.33))];
    expect(parcelForAddress(doppelt, "Weg 1")).toBeNull();
  });

  it("antwortet ohne Adresse mit nichts", () => {
    expect(parcelForAddress(NEIGHBOURS, "")).toBeNull();
    expect(parcelForAddress(NEIGHBOURS, null)).toBeNull();
  });
});

describe("Flurstücksauswahl im Lageplan", () => {
  const build = () => mount(SitePlan, {
    props: {
      plot: realPlot("moelkau"), building: null, showBuilding: false, navigable: true,
      parcels: NEIGHBOURS, chosenParcels: [NEIGHBOURS[1].properties.kennzeichen]
    }
  });

  it("zeichnet jedes Flurstück mit seiner Nummer", () => {
    const plan = build();
    const labels = plan.findAll(".site-plan__choice-label").map(n => n.text());
    expect(plan.findAll(".site-plan__choice")).toHaveLength(3);
    expect(labels).toContain("204");
    expect(labels).toContain("205");
    plan.unmount();
  });

  it("hebt das gewählte Flurstück hervor, statt es zu übermalen", () => {
    const plan = build();
    const chosen = plan.findAll(".site-plan__choice").filter(n => n.classes("is-chosen"));
    expect(chosen).toHaveLength(1);
    plan.unmount();
  });

  /** Press on one parcel, release somewhere. The press starts at the polygon
   *  and bubbles to the drawing's own handler; the release is what decides,
   *  because panning captures the pointer and a prevented pointerdown never
   *  becomes a click. */
  const press = async (plan, number, at) => {
    const svg = plan.vm.$refs.svg;
    svg.getBoundingClientRect = () => ({ left: 0, top: 0, width: 640, height: 420 });
    svg.setPointerCapture = () => {};
    plan.findAll(".site-plan__choice")
      .find(node => node.attributes("data-number") === number)
      .element.dispatchEvent(new MouseEvent("pointerdown", { bubbles: true, cancelable: true, ...at }));
    await nextTick();
    return svg;
  };

  const release = async (svg, at) => {
    svg.dispatchEvent(new MouseEvent("pointerup", { bubbles: true, ...at }));
    await nextTick();
  };

  it("wählt bei Drücken und Loslassen an derselben Stelle", async () => {
    const plan = build();
    const svg = await press(plan, "205", { clientX: 100, clientY: 100 });
    await release(svg, { clientX: 101, clientY: 100 });

    expect(plan.emitted("choose")?.[0]).toEqual([NEIGHBOURS[0].properties.kennzeichen]);
    plan.unmount();
  });

  it("wählt nicht, wenn der Zeiger dabei gezogen hat", async () => {
    // Sonst verschöbe jedes Verschieben des Ausschnitts die Auswahl.
    const plan = build();
    const svg = await press(plan, "205", { clientX: 100, clientY: 100 });
    await release(svg, { clientX: 160, clientY: 140 });

    expect(plan.emitted("choose")).toBeUndefined();
    plan.unmount();
  });

  it("überlässt die Nummern der Katasterkarte, wo sie den Grund zeichnet", async () => {
    const plan = build();
    expect(plan.findAll(".site-plan__choice-label").length).toBeGreaterThan(0);

    await plan.setProps({ backdrop: "cadastre" });
    // Ohne WebGL kommt in jsdom keine Karte hoch, und dann beschriftet der
    // Lageplan selbst: die Regel hängt am vorhandenen Grund, nicht am
    // gewünschten.
    plan.vm.mapUnavailable = false;
    await nextTick();

    expect(plan.vm.groundNamesParcels).toBe(true);
    expect(plan.findAll(".site-plan__choice-label")).toHaveLength(0);
    // Anklickbar bleibt jedes: beschriftet ist es dann von der Karte.
    expect(plan.findAll(".site-plan__choice")).toHaveLength(3);
    plan.unmount();
  });

  it("schreibt zwei Nummern nicht übereinander", () => {
    // Zwei Nummern an derselben Stelle lesen sich als eine dritte: „292/2“
    // über „293/5“ ergab „29293/5“. Das gewählte behält seine.
    const chosen = parcel(204, "Lessingweg 44", square(12.4419, 51.3365));
    const twin = parcel(2041, "Lessingweg 44a", square(12.4419, 51.3365, 0.00042));
    const plan = mount(SitePlan, {
      props: {
        plot: realPlot("moelkau"), building: null, showBuilding: false,
        parcels: [twin, chosen], chosenParcels: [chosen.properties.kennzeichen]
      }
    });

    expect(plan.findAll(".site-plan__choice")).toHaveLength(2);
    const labels = plan.findAll(".site-plan__choice-label").map(n => n.text());
    expect(labels).toEqual(["204"]);
    plan.unmount();
  });

  it("lässt die Karte stehen, wenn ein anderes Flurstück gewählt wird", async () => {
    // Sonst sieht der Schritt vor und nach dem Klick gleich aus: die Karte
    // zentriert auf den neuen Umriss, und die Nachbarn, mit denen gerade
    // verglichen wurde, sind woanders.
    const plan = mount(SitePlan, {
      props: {
        plot: realPlot("moelkau"), building: null, showBuilding: false, holdFrame: true,
        parcels: NEIGHBOURS, chosenParcels: [NEIGHBOURS[1].properties.kennzeichen]
      }
    });
    await nextTick();
    const before = { ...plan.vm.view };

    // Ein anderes Flurstück: eigener Umriss, eigener Anker, dieselbe Stelle.
    const other = realPlot("moelkau");
    other.id = "andere";
    other.anchor = { lat: other.anchor.lat + 0.0004, lon: other.anchor.lon + 0.0004 };
    other.polygon = other.polygon.map(p => ({ x: p.x + 12, y: p.y - 9 }));
    await plan.setProps({ plot: other });
    await nextTick();

    // Gleicher Maßstab, und die Mitte ist geografisch dieselbe geblieben.
    expect(plan.vm.view.scale).toBeCloseTo(before.scale, 6);
    const centre = toWgs84([{ x: plan.vm.view.mx, y: plan.vm.view.my }], other.anchor)[0];
    const was = toWgs84([{ x: before.mx, y: before.my }], realPlot("moelkau").anchor)[0];
    expect(centre[0]).toBeCloseTo(was[0], 9);
    expect(centre[1]).toBeCloseTo(was[1], 9);
    plan.unmount();
  });

  it("rahmt ohne hold-frame wieder auf das neue Flurstück", async () => {
    const plan = mount(SitePlan, {
      props: { plot: realPlot("moelkau"), building: null, showBuilding: false }
    });
    await nextTick();
    const before = { ...plan.vm.view };

    const other = realPlot("moelkau");
    other.id = "andere";
    other.polygon = other.polygon.map(p => ({ x: p.x + 40, y: p.y - 40 }));
    await plan.setProps({ plot: other });
    await nextTick();

    expect(plan.vm.view.mx).not.toBeCloseTo(before.mx, 3);
    plan.unmount();
  });

  it("zeichnet ohne Auswahl nichts davon", () => {
    const plan = mount(SitePlan, { props: { plot: realPlot("moelkau"), building: null } });
    expect(plan.findAll(".site-plan__choice")).toHaveLength(0);
    plan.unmount();
  });
});
